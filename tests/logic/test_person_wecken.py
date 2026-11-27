"""Tests für Wecken, Tagesende und nächsten Wecker (ARCHITEKTUR.md 4.3)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from custom_components.homewake.logic.person import (
    KandidatTag,
    LichtRadio,
    PersonEingaben,
    PersonErgebnis,
    PersonStatus,
    PersonZustand,
    Profil,
    TagInfo,
    berechne_person,
)
from custom_components.homewake.logic.zeitplan import Zeitfenster, Zeitplan

BERLIN = ZoneInfo("Europe/Berlin")

DIENSTAG = date(2026, 7, 14)
MITTWOCH = date(2026, 7, 15)


def fenster(b: str, e: str) -> Zeitfenster:
    """Baut ein Zeitfenster aus zwei Uhrzeiten im Format HH:MM."""
    return Zeitfenster(time.fromisoformat(b), time.fromisoformat(e))


def lokal(tag: date, uhrzeit: str) -> datetime:
    """Bildet aus Datum und Uhrzeit einen Berliner Ortszeitpunkt."""
    return datetime.combine(tag, time.fromisoformat(uhrzeit), tzinfo=BERLIN)


def woche(werktag: Zeitfenster) -> Zeitplan:
    """Zeitplan mit gleicher Zeit Mo-Fr, Wochenende leer, Standard 08:00-21:00."""
    return Zeitplan(
        standard=fenster("08:00", "21:00"),
        wochentage=(werktag,) * 5 + (None, None),
    )


ZEITPLAN = woche(fenster("06:15", "22:00"))


def eingaben(**aenderungen: object) -> PersonEingaben:
    """Eingaben einer Person mit Werktag 06:15-22:00, ohne Ausnahme."""
    basis = PersonEingaben(zeitplan=ZEITPLAN, heute=TagInfo(), morgen=TagInfo())
    return replace(basis, **aenderungen)  # type: ignore[arg-type]


def rechne(
    e: PersonEingaben, zustand: PersonZustand, tag: date, uhrzeit: str
) -> PersonErgebnis:
    """Ruft berechne_person mit Berliner Ortszeit auf."""
    return berechne_person(e, zustand, jetzt=lokal(tag, uhrzeit), zeitzone=BERLIN)


LEER = PersonZustand()
VOR_DEM_WECKEN = PersonZustand(naechster_wecker=lokal(DIENSTAG, "06:15"))
GEWECKT = PersonZustand(
    wach=True,
    geweckt_um=lokal(DIENSTAG, "06:15"),
    naechster_wecker=lokal(MITTWOCH, "06:15"),
)


# ---------------------------------------------------------------- Normalfall


def test_vor_dem_wecken_steht_der_heutige_wecker_an() -> None:
    """Um 04:00 ist der nächste Wecker heute 06:15, die Person schläft."""
    r = rechne(eingaben(), LEER, DIENSTAG, "04:00")
    assert r.naechster_wecker == lokal(DIENSTAG, "06:15")
    assert r.kandidat_tag is KandidatTag.HEUTE
    assert r.naechstes_tagesende == lokal(DIENSTAG, "22:00")
    assert (r.status, r.grund, r.profil) == (
        PersonStatus.WERKTAG,
        "dienstag",
        Profil.ZEITPLAN,
    )
    assert not r.wach
    assert not r.jetzt_geweckt


def test_wecker_genau_erreicht_weckt_und_springt_auf_morgen() -> None:
    """Genau zur Weckzeit: wach, Wecker morgen (ersetzt die 15-Sekunden-Toleranz)."""
    r = rechne(eingaben(), VOR_DEM_WECKEN, DIENSTAG, "06:15")
    assert r.wach
    assert r.jetzt_geweckt
    assert r.geweckt_um == lokal(DIENSTAG, "06:15")
    assert r.naechster_wecker == lokal(MITTWOCH, "06:15")
    assert r.kandidat_tag is KandidatTag.MORGEN
    assert r.naechstes_tagesende == lokal(DIENSTAG, "22:00")


def test_verspaeteter_lauf_weckt_mit_eigentlichem_weckzeitpunkt() -> None:
    """Läuft HomeWake erst 06:16, zählt als Weckzeitpunkt trotzdem 06:15 (E20)."""
    r = rechne(eingaben(), VOR_DEM_WECKEN, DIENSTAG, "06:16")
    assert r.wach
    assert r.jetzt_geweckt
    assert r.geweckt_um == lokal(DIENSTAG, "06:15")


def test_lauf_nach_dem_wecken_weckt_nicht_erneut() -> None:
    """Ein späterer Lauf meldet kein neues Wecken, die Person bleibt wach."""
    r = rechne(eingaben(), GEWECKT, DIENSTAG, "06:30")
    assert r.wach
    assert not r.jetzt_geweckt
    assert r.naechster_wecker == lokal(MITTWOCH, "06:15")


def test_tagesende_erreicht_beendet_wach() -> None:
    """Zum Tagesende ist die Person nicht mehr wach; nächstes Tagesende morgen."""
    r = rechne(eingaben(), GEWECKT, DIENSTAG, "22:00")
    assert not r.wach
    assert r.naechstes_tagesende == lokal(MITTWOCH, "22:00")


def test_wecken_und_tagesende_in_einem_lauf() -> None:
    """War HA über Weckzeit und Tagesende aus, greifen beide Übergänge (E15)."""
    r = rechne(eingaben(), VOR_DEM_WECKEN, DIENSTAG, "23:00")
    assert r.jetzt_geweckt
    assert r.geweckt_um == lokal(DIENSTAG, "06:15")
    assert not r.wach
    assert r.naechster_wecker == lokal(MITTWOCH, "06:15")


def test_neuer_zustand_spiegelt_das_ergebnis() -> None:
    """Der neue Zustand enthält wach, geweckt_um und den angekündigten Wecker."""
    r = rechne(eingaben(), VOR_DEM_WECKEN, DIENSTAG, "06:15")
    assert r.zustand == PersonZustand(
        wach=True,
        geweckt_um=lokal(DIENSTAG, "06:15"),
        naechster_wecker=lokal(MITTWOCH, "06:15"),
        naechster_ist_ausnahme=False,
    )


# ---------------------------------------------------------------- Änderungen am Tag


def test_zeitplan_nach_dem_wecken_spaeter_weckt_heute_nicht_erneut() -> None:
    """Heutige Zeit nach dem Wecken auf später gelegt: kein zweites Wecken."""
    e = eingaben(zeitplan=woche(fenster("07:00", "22:00")))
    r = rechne(e, GEWECKT, DIENSTAG, "06:30")
    assert r.wach
    assert r.naechster_wecker == lokal(MITTWOCH, "07:00")


def test_tagesende_nach_dem_wecken_frueher_wirkt_sofort() -> None:
    """Ein nach dem Wecken vorgezogenes Tagesende gilt (4.3 Regel 2)."""
    e = eingaben(zeitplan=woche(fenster("06:15", "20:00")))
    r = rechne(e, GEWECKT, DIENSTAG, "21:00")
    assert not r.wach


# ---------------------------------------------------------------- Ausnahme


def test_ausnahme_heute_ersetzt_den_heutigen_wecker() -> None:
    """Eine Ausnahme heute 05:00 ist der nächste Wecker, Tagesende aus dem Plan."""
    e = eingaben(ausnahme_aktiv=True, ausnahme_zeit=time(5, 0))
    r = rechne(e, LEER, DIENSTAG, "04:00")
    assert r.naechster_wecker == lokal(DIENSTAG, "05:00")
    assert (r.status, r.grund, r.profil) == (
        PersonStatus.AUSNAHME,
        None,
        Profil.AUSNAHME,
    )
    assert r.naechstes_tagesende == lokal(DIENSTAG, "22:00")
    assert r.zustand.naechster_ist_ausnahme


def test_ausnahme_spaeter_als_plan_ersetzt_ihn_trotzdem() -> None:
    """Eine Ausnahme 07:30 ersetzt den Plan 06:15 (länger schlafen)."""
    e = eingaben(ausnahme_aktiv=True, ausnahme_zeit=time(7, 30))
    r = rechne(e, LEER, DIENSTAG, "04:00")
    assert r.naechster_wecker == lokal(DIENSTAG, "07:30")


def test_falle_ausnahme_geweckt_wird_geloescht() -> None:
    """Weckt die Ausnahme, meldet das Ergebnis, dass sie gelöscht werden soll."""
    e = eingaben(ausnahme_aktiv=True, ausnahme_zeit=time(5, 0))
    zustand = PersonZustand(
        naechster_wecker=lokal(DIENSTAG, "05:00"), naechster_ist_ausnahme=True
    )
    r = rechne(e, zustand, DIENSTAG, "05:00")
    assert r.wach
    assert r.ausnahme_loeschen
    assert r.naechster_wecker == lokal(MITTWOCH, "06:15")
    assert not r.zustand.naechster_ist_ausnahme


def test_falle_nach_geloeschter_ausnahme_bleibt_person_wach() -> None:
    """Nach Wecken 05:00 und Löschen der Ausnahme bleibt die Person wach (Falle)."""
    zustand = PersonZustand(
        wach=True,
        geweckt_um=lokal(DIENSTAG, "05:00"),
        naechster_wecker=lokal(MITTWOCH, "06:15"),
    )
    r = rechne(eingaben(), zustand, DIENSTAG, "05:30")
    assert r.wach
    assert not r.jetzt_geweckt
    assert r.naechster_wecker == lokal(MITTWOCH, "06:15")
    assert r.naechstes_tagesende == lokal(DIENSTAG, "22:00")
    assert r.tagesbeginn_heute == lokal(DIENSTAG, "05:00")


def test_ausnahme_heute_vorbei_heutiger_plan_bleibt() -> None:
    """Um 06:00 Ausnahme 05:30 gesetzt: heute weckt der Plan 06:15 (E17)."""
    e = eingaben(ausnahme_aktiv=True, ausnahme_zeit=time(5, 30))
    r = rechne(e, LEER, DIENSTAG, "06:00")
    assert r.naechster_wecker == lokal(DIENSTAG, "06:15")
    assert r.status is PersonStatus.WERKTAG
    assert not r.zustand.naechster_ist_ausnahme
    assert r.tagesbeginn_morgen == lokal(MITTWOCH, "05:30")


def test_plan_wecken_loescht_morgige_ausnahme_nicht() -> None:
    """Weckt der Plan, bleibt die Ausnahme für morgen stehen (E17)."""
    e = eingaben(ausnahme_aktiv=True, ausnahme_zeit=time(5, 30))
    r = rechne(e, VOR_DEM_WECKEN, DIENSTAG, "06:15")
    assert r.wach
    assert not r.ausnahme_loeschen
    assert r.naechster_wecker == lokal(MITTWOCH, "05:30")
    assert r.status is PersonStatus.AUSNAHME
    assert r.kandidat_tag is KandidatTag.MORGEN


def test_ausnahme_abends_gesetzt_gilt_morgen() -> None:
    """Abends gesetzte Ausnahme 05:00 ist der Wecker morgen."""
    e = eingaben(ausnahme_aktiv=True, ausnahme_zeit=time(5, 0))
    zustand = replace(GEWECKT, wach=False)
    r = rechne(e, zustand, DIENSTAG, "23:00")
    assert r.naechster_wecker == lokal(MITTWOCH, "05:00")
    assert r.status is PersonStatus.AUSNAHME
    assert r.kandidat_tag is KandidatTag.MORGEN


def test_inaktive_ausnahme_mit_uhrzeit_zaehlt_nicht() -> None:
    """Eine ausgeschaltete Ausnahme mit Uhrzeit wird ignoriert."""
    e = eingaben(ausnahme_aktiv=False, ausnahme_zeit=time(5, 0))
    r = rechne(e, LEER, DIENSTAG, "04:00")
    assert r.naechster_wecker == lokal(DIENSTAG, "06:15")


# ---------------------------------------------------------------- Datums-Bug / Tage


def test_datums_bug_heute_frei_morgen_werktag_alles_von_morgen() -> None:
    """Regression Datums-Bug: nach dem Wecken am freien Tag alles von morgen."""
    e = eingaben(heute=TagInfo(feiertag="Fronleichnam"))
    zustand = PersonZustand(
        wach=True,
        geweckt_um=lokal(DIENSTAG, "08:00"),
        naechster_wecker=lokal(MITTWOCH, "06:15"),
    )
    r = rechne(e, zustand, DIENSTAG, "09:00")
    assert r.naechster_wecker == lokal(MITTWOCH, "06:15")
    assert (r.status, r.grund) == (PersonStatus.WERKTAG, "mittwoch")


def test_heute_werktag_morgen_feiertag_nimmt_standard_von_morgen() -> None:
    """Nach dem Wecken am Werktag gilt für morgen (Feiertag) die Standard-Zeile."""
    e = eingaben(morgen=TagInfo(feiertag="Allerheiligen"))
    r = rechne(e, GEWECKT, DIENSTAG, "06:30")
    assert r.naechster_wecker == lokal(MITTWOCH, "08:00")
    assert (r.status, r.grund, r.profil) == (
        PersonStatus.FEIERTAG,
        "Allerheiligen",
        Profil.STANDARD,
    )


def test_tagesbeginn_und_tagesende_heute_und_morgen() -> None:
    """Attribute heute/morgen kommen aus dem jeweiligen Tagesplan (E16)."""
    e = eingaben(morgen=TagInfo(urlaub=True))
    r = rechne(e, LEER, DIENSTAG, "04:00")
    assert (r.tagesbeginn_heute, r.tagesende_heute) == (
        lokal(DIENSTAG, "06:15"),
        lokal(DIENSTAG, "22:00"),
    )
    assert (r.tagesbeginn_morgen, r.tagesende_morgen) == (
        lokal(MITTWOCH, "08:00"),
        lokal(MITTWOCH, "21:00"),
    )


# ---------------------------------------------------------------- Licht/Radio


PROFILE = {
    Profil.ZEITPLAN: LichtRadio(licht=True, radio=False),
    Profil.STANDARD: LichtRadio(licht=False, radio=True),
    Profil.AUSNAHME: LichtRadio(licht=True, radio=True),
}


@pytest.mark.parametrize(
    ("aenderungen", "erwartet"),
    [
        ({}, PROFILE[Profil.ZEITPLAN]),
        ({"heute": TagInfo(urlaub=True)}, PROFILE[Profil.STANDARD]),
        (
            {"ausnahme_aktiv": True, "ausnahme_zeit": time(5, 0)},
            PROFILE[Profil.AUSNAHME],
        ),
    ],
    ids=["zeitplan", "standard", "ausnahme"],
)
def test_licht_radio_folgt_dem_profil(
    aenderungen: dict[str, object], erwartet: LichtRadio
) -> None:
    """Licht/Radio fürs nächste Wecken kommen aus dem Profil des Weckers (E7)."""
    e = eingaben(licht_radio=PROFILE, **aenderungen)
    assert rechne(e, LEER, DIENSTAG, "04:00").licht_radio == erwartet


def test_fehlendes_profil_heisst_licht_und_radio_aus() -> None:
    """Ohne Angaben zu einem Profil sind Licht und Radio aus."""
    assert rechne(eingaben(), LEER, DIENSTAG, "04:00").licht_radio == LichtRadio()


# ---------------------------------------------------------------- Zeit/Zeitzone


def test_jetzt_ohne_zeitzone_ist_ein_fehler() -> None:
    """„jetzt“ muss zeitzonenbehaftet sein (nur Zeitpunkte mit Zeitzone)."""
    naiv = datetime(2026, 7, 14, 4, 0)  # noqa: DTZ001
    with pytest.raises(ValueError):
        berechne_person(eingaben(), LEER, jetzt=naiv, zeitzone=BERLIN)


def test_jetzt_in_utc_wird_richtig_eingeordnet() -> None:
    """„jetzt“ in UTC (wie HA es liefert) wird mit Berliner Zeiten verglichen."""
    jetzt = datetime(2026, 7, 14, 4, 15, tzinfo=UTC)  # = 06:15 MESZ
    r = berechne_person(eingaben(), VOR_DEM_WECKEN, jetzt=jetzt, zeitzone=BERLIN)
    assert r.wach
    assert r.naechster_wecker == lokal(MITTWOCH, "06:15")


def test_wecken_am_tag_der_zeitumstellung() -> None:
    """Am 29.03.2026 (Sonntag, Standard 08:00) wird zur Ortszeit 08:00 geweckt."""
    sonntag = date(2026, 3, 29)
    zustand = PersonZustand(naechster_wecker=lokal(sonntag, "08:00"))
    jetzt = datetime(2026, 3, 29, 6, 0, tzinfo=UTC)  # = 08:00 MESZ
    r = berechne_person(eingaben(), zustand, jetzt=jetzt, zeitzone=BERLIN)
    assert r.wach
    assert r.geweckt_um == lokal(sonntag, "08:00")
    assert r.naechster_wecker == lokal(date(2026, 3, 30), "06:15")
