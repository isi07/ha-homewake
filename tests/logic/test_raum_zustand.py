"""Tests für Raum-Zustand, Wecken und Einfrieren (ARCHITEKTUR.md 4.5, E21 bis E24).

Nachgebaut aus dem alten Projekt: test_raum_default_toleranz.py,
test_dawn_klemmung_anker_rollover.py (v12), test_dawn_klemmung_mehrpersonen.py
(v13) und test_raum_licht_radio_einfrieren.py (v15).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from custom_components.homewake.logic.raum import (
    RaumEingaben,
    RaumErgebnis,
    RaumKonfig,
    RaumQuelle,
    RaumWecken,
    RaumZustand,
    Sonne,
    berechne_raum,
)
from tests.logic.test_raum_tag import (
    BERLIN,
    DIENSTAG,
    MITTWOCH,
    STANDARDPLAN,
    eingaben,
    lokal,
    person,
)

MONTAG = date(2026, 7, 13)


def rechne(
    e: RaumEingaben, zustand: RaumZustand, uhrzeit: str, tag: date = DIENSTAG
) -> RaumErgebnis:
    """berechne_raum zu einer Berliner Ortszeit."""
    return berechne_raum(e, zustand, jetzt=lokal(tag, uhrzeit), zeitzone=BERLIN)


def angekuendigt(uhrzeit: str, tag: date = DIENSTAG, **werte: object) -> RaumZustand:
    """Zustand vom Vorabend/früher am Tag: nur eine Ankündigung."""
    return RaumZustand(
        datum=tag,
        angekuendigt=RaumWecken(zeit=lokal(tag, uhrzeit), **werte),  # type: ignore[arg-type]
    )


VATER = person("Vater", ("06:30", "22:00"), licht=True, radio=True, favorit="WDR 2")
MUTTER = person("Mutter", ("08:00", "21:30"))
DAWN = Sonne(dawn=lokal(DIENSTAG, "06:58:58"), dusk=lokal(DIENSTAG, "20:30"))
SCHLAFZIMMER = replace(eingaben(VATER, MUTTER), sonne_heute=DAWN)


# ------------------------------------------------------ Ankündigung und Wecken


def test_vor_dem_wecken_wird_heute_angekuendigt() -> None:
    """Vor der Weckzeit kündigt der Raum das heutige Wecken mit Licht/Radio an."""
    r = rechne(SCHLAFZIMMER, RaumZustand(), "04:00")
    assert r.zustand.angekuendigt == RaumWecken(
        zeit=lokal(DIENSTAG, "06:30"),
        licht=True,
        radio=True,
        favorit="WDR 2",
        quelle=RaumQuelle.PERSONEN,
        weckende=("Vater",),
    )
    assert r.zustand.datum == DIENSTAG
    assert not r.jetzt_geweckt


def test_angekuendigte_weckzeit_erreicht_weckt() -> None:
    """Zur angekündigten Zeit: gerade geweckt, mit den angekündigten Werten."""
    zustand = angekuendigt("06:30", licht=True, radio=True, favorit="WDR 2")
    r = rechne(SCHLAFZIMMER, zustand, "06:30")
    assert r.jetzt_geweckt
    assert r.geweckt_um == lokal(DIENSTAG, "06:30")
    assert r.wach
    assert (r.licht, r.radio, r.favorit) == (True, True, "WDR 2")


def test_nach_dem_wecken_wird_morgen_angekuendigt() -> None:
    """Nach dem Wecken kündigt der Raum das Wecken von morgen an."""
    r = rechne(SCHLAFZIMMER, angekuendigt("06:30"), "06:30")
    assert r.zustand.angekuendigt is not None
    assert r.zustand.angekuendigt.zeit == lokal(MITTWOCH, "06:15")


def test_verspaeteter_lauf_weckt_mit_eigentlicher_zeit() -> None:
    """Neustart 06:31 mit Ankündigung 06:30: gerade geweckt, geweckt um 06:30 (E20)."""
    r = rechne(SCHLAFZIMMER, angekuendigt("06:30"), "06:31")
    assert r.jetzt_geweckt
    assert r.geweckt_um == lokal(DIENSTAG, "06:30")


def test_spaeterer_lauf_weckt_nicht_erneut() -> None:
    """Ein Lauf nach dem Wecken meldet kein neues Wecken."""
    erster = rechne(SCHLAFZIMMER, angekuendigt("06:30"), "06:30")
    zweiter = rechne(SCHLAFZIMMER, erster.zustand, "07:00")
    assert not zweiter.jetzt_geweckt
    assert zweiter.geweckt_um == lokal(DIENSTAG, "06:30")


# ---------------------------------------------------------------- Einfrieren (4.5, v15)


def test_licht_radio_aus_ankuendigung_auch_wenn_person_schon_gerollt() -> None:
    """v15: Beim Wecken gelten die angekündigten Werte, nicht die schon gerollten."""
    gerollt = replace(VATER, naechster_wecker=lokal(MITTWOCH, "06:15"))
    e = replace(SCHLAFZIMMER, personen=(gerollt, MUTTER))
    zustand = angekuendigt("06:30", licht=True, radio=True, favorit="WDR 2")
    r = rechne(e, zustand, "06:30")
    assert (r.licht, r.radio, r.favorit) == (True, True, "WDR 2")


def test_licht_radio_bleiben_nach_dem_wecken_bis_mitternacht() -> None:
    """v15: Nach dem Wecken bleiben Licht/Radio/Favorit eingefroren."""
    erster = rechne(SCHLAFZIMMER, angekuendigt("06:30", licht=True), "06:30")
    ohne_licht = replace(
        SCHLAFZIMMER,
        personen=(
            replace(VATER, licht_radio=replace(VATER.licht_radio, licht=False)),
            MUTTER,
        ),
    )
    r = rechne(ohne_licht, erster.zustand, "12:00")
    assert r.licht


def test_tagesbeginn_friert_nach_erreichen_ein() -> None:
    """Nach Erreichen bleibt der Tagesbeginn, auch wenn sich Dawn noch ändert."""
    erster = rechne(SCHLAFZIMMER, angekuendigt("06:30"), "07:00")
    assert erster.tagesbeginn == lokal(DIENSTAG, "06:58:58")
    spaeter = replace(SCHLAFZIMMER, sonne_heute=Sonne(dawn=lokal(DIENSTAG, "07:10")))
    r = rechne(spaeter, erster.zustand, "08:00")
    assert r.tagesbeginn == lokal(DIENSTAG, "06:58:58")


def test_tagesende_friert_nach_erreichen_ein() -> None:
    """Nach Erreichen bleibt das Tagesende, auch wenn die Person es später legt."""
    erster = rechne(SCHLAFZIMMER, angekuendigt("06:30"), "20:31")
    assert erster.tagesende == lokal(DIENSTAG, "20:30")
    laenger = replace(SCHLAFZIMMER, personen=(person("Vater", ("06:30", "23:30")),))
    r = rechne(laenger, erster.zustand, "21:00")
    assert r.tagesende == lokal(DIENSTAG, "20:30")
    assert not r.wach
    assert not r.tag


def test_vor_erreichen_wandern_die_werte_mit() -> None:
    """Vor dem Wecken ist alles live: neue Personenzeit → neue Raum-Weckzeit."""
    erster = rechne(SCHLAFZIMMER, RaumZustand(), "04:00")
    frueher = replace(
        SCHLAFZIMMER, personen=(person("Vater", ("05:45", "22:00")), MUTTER)
    )
    r = rechne(frueher, erster.zustand, "04:30")
    assert r.weckzeit == lokal(DIENSTAG, "05:45")
    assert r.zustand.angekuendigt is not None
    assert r.zustand.angekuendigt.zeit == lokal(DIENSTAG, "05:45")


# ---------------------------------------------------- v13: Mehrpersonen-Anker


def test_mehrpersonen_anker_bleibt_auf_erreichter_weckzeit() -> None:
    """v13: Vater 06:30 geweckt, danach nur Mutter 08:00: Beginn bleibt 06:58:58."""
    geweckt = rechne(SCHLAFZIMMER, angekuendigt("06:30"), "06:30:01")
    nur_mutter = replace(SCHLAFZIMMER, personen=(MUTTER,))
    r = rechne(nur_mutter, geweckt.zustand, "06:31:11")
    assert r.weckzeit == lokal(DIENSTAG, "06:30")
    assert r.tagesbeginn == lokal(DIENSTAG, "06:58:58")
    assert r.wach
    assert not r.tag


# ------------------------------------------- v12, ehemals 15-Sekunden-Toleranz


@pytest.mark.parametrize(
    "jetzt",
    ["06:00:00", "06:00:00.075", "06:00:16", "06:01:11"],
    ids=["genau", "75ms_spaeter", "16s_spaeter", "1min_spaeter"],
)
def test_lauf_kurz_nach_der_weckzeit_springt_nicht_auf_morgen(jetzt: str) -> None:
    """Läufe kurz nach 06:00 behalten Weckzeit und Tagesbeginn von heute.

    Ersetzt die 15-Sekunden-Toleranz des alten Systems (test_raum_default_toleranz.py,
    v12): Ob geweckt wurde, steht im Zustand, nicht in einem Zeitfenster.
    """
    e = replace(eingaben(), sonne_heute=Sonne(dawn=lokal(DIENSTAG, "06:05:13")))
    r = rechne(e, angekuendigt("06:00"), jetzt)
    assert r.weckzeit == lokal(DIENSTAG, "06:00")
    assert r.tagesbeginn == lokal(DIENSTAG, "06:05:13")


def test_standardplan_tagesende_bleibt_heute_nach_erreichen() -> None:
    """v12: Ende 22:15, Fenster 75, Dusk 20:45:28 → um 22:16 weiter 21:00 heute."""
    konfig = RaumKonfig(standardplan=STANDARDPLAN, klemm_ende=timedelta(minutes=75))
    e = replace(
        eingaben(konfig=konfig),
        sonne_heute=Sonne(dusk=lokal(DIENSTAG, "20:45:28")),
    )
    erster = rechne(e, angekuendigt("06:00"), "21:00")
    r = rechne(e, erster.zustand, "22:16")
    assert r.tagesende == lokal(DIENSTAG, "21:00")
    assert r.tagesende_roh == lokal(DIENSTAG, "22:15")


# ---------------------------------------------------------------- Tageswechsel (E21)


def test_zustand_von_gestern_wird_verworfen() -> None:
    """Eingefrorene Werte von gestern gelten heute nicht mehr."""
    gestern = RaumZustand(
        datum=MONTAG,
        geweckt=RaumWecken(zeit=lokal(MONTAG, "06:30"), licht=True),
        tagesbeginn=lokal(MONTAG, "06:58"),
        tagesende=lokal(MONTAG, "20:30"),
        angekuendigt=RaumWecken(zeit=lokal(DIENSTAG, "06:30")),
    )
    r = rechne(SCHLAFZIMMER, gestern, "04:00")
    assert not r.wach
    assert r.geweckt_um is None
    assert r.weckzeit == lokal(DIENSTAG, "06:30")
    assert r.zustand.datum == DIENSTAG
    assert r.zustand.geweckt is None


def test_weckzeit_kurz_nach_mitternacht_wird_gemeldet() -> None:
    """Am Vorabend angekündigt 00:05, Lauf um 00:05: gerade geweckt."""
    frueh = person("Frueh", ("00:05", "21:00"))
    e = eingaben(frueh)
    gestern = RaumZustand(
        datum=MONTAG,
        geweckt=RaumWecken(zeit=lokal(MONTAG, "00:05")),
        angekuendigt=RaumWecken(zeit=lokal(DIENSTAG, "00:05")),
    )
    r = rechne(e, gestern, "00:05")
    assert r.jetzt_geweckt
    assert r.geweckt_um == lokal(DIENSTAG, "00:05")


def test_veraltete_ankuendigung_weckt_nicht() -> None:
    """Eine Ankündigung für einen früheren Tag weckt heute nicht."""
    alt = RaumZustand(
        datum=MONTAG, angekuendigt=RaumWecken(zeit=lokal(MONTAG, "06:30"))
    )
    r = rechne(SCHLAFZIMMER, alt, "04:00")
    assert not r.jetzt_geweckt
    assert not r.wach


# ---------------------------------------------------------------- Sollzustand (E23)


def test_neustart_ohne_zustand_mitten_am_tag() -> None:
    """Neustart 07:00 ohne Zustand: still geweckt, wach und Tag, kein Wecken."""
    r = rechne(SCHLAFZIMMER, RaumZustand(), "07:00")
    assert r.wach
    assert r.tag
    assert not r.jetzt_geweckt
    assert r.geweckt_um == lokal(DIENSTAG, "06:30")


def test_person_kommt_nach_eigenem_wecken_dazu() -> None:
    """Person (06:15 schon geweckt) kommt um 07:00 dazu: still geweckt, kein Licht."""
    vorher = rechne(
        eingaben(), RaumZustand(), "05:00"
    )  # leerer Raum, Standardplan 06:00
    neu = person(
        "Neu", ("06:15", "22:00"), licht=True, naechster=lokal(MITTWOCH, "06:15")
    )
    # Standardplan 06:00 wäre um 06:00 angekündigt gewesen; HA war aus bis 07:00.
    zustand = replace(vorher.zustand, angekuendigt=None)
    r = rechne(eingaben(neu), zustand, "07:00")
    assert not r.jetzt_geweckt
    assert r.wach


# ------------------------------------------- Quelle und Weckende einfrieren (E47)


def test_ankuendigung_enthaelt_quelle_und_weckende() -> None:
    """Die Ankündigung trägt Quelle und weckende Personen mit (E47)."""
    r = rechne(SCHLAFZIMMER, RaumZustand(), "04:00")
    assert r.zustand.angekuendigt is not None
    assert r.zustand.angekuendigt.quelle is RaumQuelle.PERSONEN
    assert r.zustand.angekuendigt.weckende == ("Vater",)


def test_quelle_und_weckende_bleiben_nach_dem_wecken_bis_mitternacht() -> None:
    """Verlässt die weckende Person nach dem Wecken den Raum, bleibt die Anzeige."""
    erster = rechne(SCHLAFZIMMER, RaumZustand(), "04:00")
    geweckt = rechne(SCHLAFZIMMER, erster.zustand, "06:30")
    assert geweckt.weckende == ("Vater",)
    ohne_vater = replace(SCHLAFZIMMER, personen=(MUTTER,))
    r = rechne(ohne_vater, geweckt.zustand, "12:00")
    assert r.quelle is RaumQuelle.PERSONEN
    assert r.weckende == ("Vater",)
    assert r.personen == ("Mutter",)  # wer jetzt im Raum ist, bleibt live
    leer = rechne(replace(SCHLAFZIMMER, personen=()), geweckt.zustand, "12:00")
    assert leer.quelle is RaumQuelle.PERSONEN
    assert leer.weckende == ("Vater",)


def test_vor_dem_wecken_wandern_quelle_und_weckende_mit() -> None:
    """Vor der Weckzeit sind Quelle und Weckende live (wie die Weckzeit)."""
    erster = rechne(SCHLAFZIMMER, RaumZustand(), "04:00")
    r = rechne(replace(SCHLAFZIMMER, personen=()), erster.zustand, "05:00")
    assert r.quelle is RaumQuelle.STANDARDPLAN
    assert r.weckende == ()
