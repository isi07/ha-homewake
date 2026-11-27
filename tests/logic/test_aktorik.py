"""Tests für die Aktorik-Logik (ARCHITEKTUR.md 4.7, E28, E50 bis E54).

Enthält die Regressionsfälle aus dem alten Projekt
(``tests/test_sonos_reihenfolge.py``): Personen-Favorit vor Standard-Favorit,
fehlende ``source_list`` gilt als ungültig, kein Play ohne gültige Quelle,
kein Lautsprecher/keine Lichter → nichts schalten, Elevations-Schwelle mit ≤.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.homewake.logic.aktorik import (
    AktorikEingaben,
    AktorikKonfig,
    AusAuftrag,
    GeraetZustand,
    LichtBefehl,
    RadioBefehl,
    Schaltplan,
    aus_auftrag_beginnen,
    erreichbar,
    schaltplan,
    waehle_quelle,
    was_ausschalten,
)

TZ = ZoneInfo("Europe/Berlin")
WECKZEIT = datetime(2026, 11, 27, 6, 30, tzinfo=TZ)
QUELLEN = ("hr3", "SWR3", "YOU FM")

KONFIG = AktorikKonfig(
    lichter=("light.decke", "light.nachttisch"),
    helligkeit=80,
    elevation=-3.0,
    dauer=timedelta(minutes=45),
    lautsprecher="media_player.sonos",
    lautstaerke=30,
)


def eingaben(**aenderungen: object) -> AktorikEingaben:
    """Licht und Radio gewünscht, Favorit der Person „SWR3“, dunkel."""
    basis = AktorikEingaben(
        konfig=KONFIG,
        licht=True,
        radio=True,
        favorit="SWR3",
        standard_favorit="hr3",
        geweckt_um=WECKZEIT,
        sonnenhoehe=-10.0,
    )
    return replace(basis, **aenderungen)  # type: ignore[arg-type]


# ---------------------------------------------------------------- Quelle (4.7)


def test_personen_favorit_gilt_wenn_in_source_list() -> None:
    """Regression: Favorit der Person steht in der Liste → er gilt."""
    assert waehle_quelle("SWR3", "hr3", QUELLEN) == "SWR3"


def test_standard_favorit_wenn_personen_favorit_ungueltig() -> None:
    """Regression: Personen-Favorit nicht in der Liste → Standard-Favorit."""
    assert waehle_quelle("Bayern 3", "hr3", QUELLEN) == "hr3"


def test_standard_favorit_wenn_person_keinen_favoriten_hat() -> None:
    """Person ohne Favorit → Standard-Favorit."""
    assert waehle_quelle(None, "hr3", QUELLEN) == "hr3"


def test_weder_personen_noch_standard_favorit_gueltig_spielt_den_ersten() -> None:
    """E56 (statt bisher still): beide ungültig → erster Eintrag der Liste."""
    assert waehle_quelle("Bayern 3", "Antenne", QUELLEN) == "hr3"


def test_ohne_jeden_favoriten_spielt_der_erste() -> None:
    """E56: Weder Person noch Raum haben einen Favoriten → erster der Liste."""
    assert waehle_quelle(None, None, QUELLEN) == "hr3"


def test_fehlende_source_list_gilt_als_ungueltig() -> None:
    """Regression: Lautsprecher ohne Liste → keine Quelle, kein Absturz."""
    assert waehle_quelle("SWR3", "hr3", ()) is None


def test_favorit_wird_exakt_verglichen() -> None:
    """Backlog 9: exakter Vergleich; „swr3“ gilt nicht als „SWR3“."""
    assert waehle_quelle("swr3", None, QUELLEN) == "hr3"


# ---------------------------------------------------------------- Schaltplan


def test_licht_und_radio_mit_personen_favorit() -> None:
    """Licht mit Helligkeit, Radio mit Lautstärke 0..1 und Favoriten, Aus nach Dauer.

    Versucht wird bis 15 Minuten nach dem Wecken (E52, E28).
    """
    plan = schaltplan(eingaben(), jetzt=WECKZEIT)
    assert plan == Schaltplan(
        licht=LichtBefehl(lichter=("light.decke", "light.nachttisch"), helligkeit=80),
        radio=RadioBefehl(
            lautsprecher="media_player.sonos",
            lautstaerke=0.3,
            favorit="SWR3",
            standard_favorit="hr3",
        ),
        aus_um=WECKZEIT + timedelta(minutes=45),
        versuche_bis=WECKZEIT + timedelta(minutes=15),
    )


def test_quelle_wird_beim_versuch_aus_der_aktuellen_liste_gewaehlt() -> None:
    """A2: Die Quelle hängt an der ``source_list`` zum Zeitpunkt des Versuchs."""
    plan = schaltplan(eingaben(), jetzt=WECKZEIT)
    assert plan is not None
    assert plan.radio is not None
    assert plan.radio.quelle(QUELLEN) == "SWR3"
    assert plan.radio.quelle(("hr3",)) == "hr3"
    assert plan.radio.quelle(()) is None


def test_versuche_enden_spaetestens_zum_aus_zeitpunkt() -> None:
    """E52: Bei kurzer Dauer enden die Versuche schon mit dem Ausschalten."""
    konfig = replace(KONFIG, dauer=timedelta(minutes=2))
    plan = schaltplan(eingaben(konfig=konfig), jetzt=WECKZEIT)
    assert plan is not None
    assert plan.versuche_bis == WECKZEIT + timedelta(minutes=2)


def test_nichts_gewuenscht_ergibt_keinen_plan() -> None:
    """Weder Licht noch Radio gewünscht → nichts tun."""
    assert schaltplan(eingaben(licht=False, radio=False), jetzt=WECKZEIT) is None


@pytest.mark.parametrize(
    ("hoehe", "licht_an"),
    [(-10.0, True), (-3.0, True), (-2.9, False), (5.0, False)],
)
def test_licht_nur_bis_zur_elevations_schwelle(hoehe: float, licht_an: bool) -> None:
    """Regression: Licht nur, wenn die Sonnenhöhe ≤ Schwelle ist (E51)."""
    plan = schaltplan(eingaben(radio=False, sonnenhoehe=hoehe), jetzt=WECKZEIT)
    assert (plan is not None and plan.licht is not None) is licht_an


def test_licht_nicht_gewuenscht() -> None:
    """Regression: Licht-Wunsch aus → kein Licht, Radio trotzdem."""
    plan = schaltplan(eingaben(licht=False), jetzt=WECKZEIT)
    assert plan is not None
    assert plan.licht is None
    assert plan.radio is not None


def test_keine_lichter_eingetragen() -> None:
    """Regression: Licht gewünscht, aber keine Lichter im Raum → kein Licht."""
    konfig = replace(KONFIG, lichter=())
    plan = schaltplan(eingaben(konfig=konfig, radio=False), jetzt=WECKZEIT)
    assert plan is None


def test_kein_lautsprecher_eingetragen() -> None:
    """Regression: Radio gewünscht, aber kein Lautsprecher → kein Radio."""
    konfig = replace(KONFIG, lautsprecher=None)
    plan = schaltplan(eingaben(konfig=konfig, licht=False), jetzt=WECKZEIT)
    assert plan is None


def test_ohne_favoriten_spielt_das_radio_den_ersten() -> None:
    """E56: Radio auch ohne Favoriten; es spielt der erste Eintrag der Liste."""
    plan = schaltplan(
        eingaben(licht=False, favorit=None, standard_favorit=None), jetzt=WECKZEIT
    )
    assert plan is not None
    assert plan.radio is not None
    assert plan.radio.quelle(QUELLEN) == "hr3"


def test_aus_auftrag_beginnt_leer() -> None:
    """A2: Der Aus-Auftrag füllt sich erst mit dem, was wirklich geschaltet wurde."""
    plan = schaltplan(eingaben(), jetzt=WECKZEIT)
    assert plan is not None
    assert aus_auftrag_beginnen(plan, None) == AusAuftrag(
        um=WECKZEIT + timedelta(minutes=45)
    )


def test_neues_wecken_behaelt_die_geraete_eines_offenen_auftrags() -> None:
    """Ein noch offener Auftrag gibt seine Geräte weiter, der Zeitpunkt ist neu."""
    plan = schaltplan(eingaben(), jetzt=WECKZEIT)
    assert plan is not None
    alt = AusAuftrag(
        um=WECKZEIT,
        lichter=("light.decke",),
        lautsprecher="media_player.sonos",
        quelle="hr3",
    )
    assert aus_auftrag_beginnen(plan, alt) == replace(alt, um=plan.aus_um)


def test_nachholen_bis_15_minuten() -> None:
    """E28: bis einschließlich 15 Minuten nach dem Wecken wird geschaltet."""
    spaeter = WECKZEIT + timedelta(minutes=15)
    plan = schaltplan(eingaben(), jetzt=spaeter)
    assert plan is not None
    # E54 (2): Aus-Timer ab dem Schaltzeitpunkt; Versuche nur bis +15 min
    assert plan.aus_um == spaeter + timedelta(minutes=45)
    assert plan.versuche_bis == spaeter


def test_nach_15_minuten_wird_nicht_mehr_geschaltet() -> None:
    """E28: mehr als 15 Minuten zu spät → nichts schalten."""
    jetzt = WECKZEIT + timedelta(minutes=15, seconds=1)
    assert schaltplan(eingaben(), jetzt=jetzt) is None


def test_jetzt_ohne_zeitzone_wird_abgelehnt() -> None:
    """„jetzt“ muss zeitzonenbehaftet sein (Architektur-Regel 2)."""
    with pytest.raises(ValueError, match="zeitzonenbehaftet"):
        schaltplan(eingaben(), jetzt=WECKZEIT.replace(tzinfo=None))


def test_lautstaerke_und_helligkeit_an_den_grenzen() -> None:
    """Lautstärke 0 % bleibt 0,0; Helligkeit wird ganzzahlig übernommen."""
    konfig = replace(KONFIG, lautstaerke=0, helligkeit=1)
    plan = schaltplan(eingaben(konfig=konfig), jetzt=WECKZEIT)
    assert plan is not None
    assert plan.radio is not None
    assert plan.radio.lautstaerke == 0.0
    assert plan.licht is not None
    assert plan.licht.helligkeit == 1


# ------------------------------------------------------- Ausschalten (E50, E54)

AUFTRAG = AusAuftrag(
    um=WECKZEIT + timedelta(minutes=45),
    lichter=("light.decke", "light.nachttisch"),
    lautsprecher="media_player.sonos",
    quelle="SWR3",
)


def test_alles_noch_wie_gesetzt_wird_ausgeschaltet() -> None:
    """Licht an, Lautsprecher spielt die Weck-Quelle → alles aus."""
    lichter, stoppen = was_ausschalten(
        AUFTRAG,
        {
            "light.decke": GeraetZustand("on"),
            "light.nachttisch": GeraetZustand("on"),
            "media_player.sonos": GeraetZustand("playing", "SWR3"),
        },
    )
    assert lichter == ("light.decke", "light.nachttisch")
    assert stoppen is True


def test_vom_menschen_ausgeschaltetes_licht_bleibt_aus() -> None:
    """E50: ein Licht, das schon aus ist, wird nicht angefasst."""
    lichter, _ = was_ausschalten(
        AUFTRAG,
        {
            "light.decke": GeraetZustand("off"),
            "light.nachttisch": GeraetZustand("on"),
            "media_player.sonos": GeraetZustand("playing", "SWR3"),
        },
    )
    assert lichter == ("light.nachttisch",)


@pytest.mark.parametrize(
    "zustand",
    [
        GeraetZustand("playing", "hr3"),  # andere Quelle gewählt
        GeraetZustand("paused", "SWR3"),
        GeraetZustand("idle", None),
        GeraetZustand("off", None),
    ],
)
def test_lautsprecher_mit_anderem_zustand_bleibt(zustand: GeraetZustand) -> None:
    """E50: spielt der Lautsprecher nicht mehr die Weck-Quelle, bleibt er."""
    _, stoppen = was_ausschalten(AUFTRAG, {"media_player.sonos": zustand})
    assert stoppen is False


@pytest.mark.parametrize(
    "zustand",
    [
        GeraetZustand("unavailable"),
        GeraetZustand("unknown"),
        GeraetZustand("playing", None),  # spielt, meldet aber keine Quelle
    ],
)
def test_unklarer_lautsprecher_wird_trotzdem_gestoppt(zustand: GeraetZustand) -> None:
    """E54 (3): unklarer Zustand → trotzdem ausschalten."""
    _, stoppen = was_ausschalten(AUFTRAG, {"media_player.sonos": zustand})
    assert stoppen is True


def test_unklare_oder_fehlende_geraete_werden_trotzdem_ausgeschaltet() -> None:
    """E54 (3): Licht nicht verfügbar oder ganz weg → trotzdem ausschalten."""
    lichter, stoppen = was_ausschalten(
        AUFTRAG, {"light.decke": GeraetZustand("unavailable")}
    )
    assert lichter == ("light.decke", "light.nachttisch")
    assert stoppen is True


def test_auftrag_ohne_lautsprecher_stoppt_nichts() -> None:
    """Wurde keine Quelle gespielt, wird auch nichts gestoppt."""
    auftrag = replace(AUFTRAG, lautsprecher=None, quelle=None)
    _, stoppen = was_ausschalten(auftrag, {})
    assert stoppen is False


@pytest.mark.parametrize(
    ("zustand", "ergebnis"),
    [
        (None, False),  # fehlt in HA
        ("unavailable", False),
        ("unknown", True),  # da, nur Zustand unbekannt: schalten
        ("off", True),
        ("playing", True),
    ],
)
def test_erreichbar(zustand: str | None, ergebnis: bool) -> None:
    """A2: Fehlt ein Gerät oder ist es nicht verfügbar, wird später neu versucht."""
    assert erreichbar(zustand) is ergebnis
