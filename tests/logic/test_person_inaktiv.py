"""Tests für inaktive Personen und Grenzen der Ausnahme (ARCHITEKTUR.md 4.3, 4.4)."""

from __future__ import annotations

from datetime import time

import pytest

from custom_components.homewake.logic.person import PersonStatus, TagInfo
from tests.logic.test_person_wecken import (
    DIENSTAG,
    GEWECKT,
    LEER,
    MITTWOCH,
    VOR_DEM_WECKEN,
    eingaben,
    lokal,
    rechne,
)

# ---------------------------------------------------------------- Inaktiv (E8, E19)


def test_inaktiv_zeigt_zeiten_mit_status_inaktiv() -> None:
    """Ohne Raum: Zeiten wie nach Plan, Status Inaktiv, Grund „kein Raum“ (E8)."""
    r = rechne(eingaben(raum_zugeordnet=False), LEER, DIENSTAG, "04:00")
    assert r.naechster_wecker == lokal(DIENSTAG, "06:15")
    assert r.naechstes_tagesende == lokal(DIENSTAG, "22:00")
    assert (r.status, r.grund) == (PersonStatus.INAKTIV, "kein_raum")


def test_inaktiv_ignoriert_ausnahme_und_loescht_sie() -> None:
    """Ohne Raum zählt eine aktive Ausnahme nicht und soll gelöscht werden (E8)."""
    e = eingaben(raum_zugeordnet=False, ausnahme_aktiv=True, ausnahme_zeit=time(5, 0))
    r = rechne(e, LEER, DIENSTAG, "04:00")
    assert r.naechster_wecker == lokal(DIENSTAG, "06:15")
    assert r.status is PersonStatus.INAKTIV
    assert r.ausnahme_loeschen
    assert not r.zustand.naechster_ist_ausnahme


def test_inaktiv_ohne_ausnahme_loescht_nichts() -> None:
    """Ohne aktive Ausnahme gibt es bei Inaktiv nichts zu löschen."""
    r = rechne(eingaben(raum_zugeordnet=False), LEER, DIENSTAG, "04:00")
    assert not r.ausnahme_loeschen


def test_inaktiv_wird_trotzdem_wach() -> None:
    """Auch ohne Raum schaltet „wach“ zur Weckzeit normal (E19)."""
    r = rechne(eingaben(raum_zugeordnet=False), VOR_DEM_WECKEN, DIENSTAG, "06:15")
    assert r.wach
    assert r.jetzt_geweckt
    assert r.naechster_wecker == lokal(MITTWOCH, "06:15")


# ------------------------------------------------ Ausnahme ab Tagesende (E18)


@pytest.mark.parametrize(
    "uhrzeit",
    [time(23, 0), time(22, 0)],
    ids=["nach_tagesende", "genau_tagesende"],
)
def test_ausnahme_ab_tagesende_zaehlt_nicht(uhrzeit: time) -> None:
    """Eine Ausnahme ab dem Tagesende (22:00) ihres Tags wird ignoriert (E18)."""
    e = eingaben(ausnahme_aktiv=True, ausnahme_zeit=uhrzeit)
    r = rechne(e, LEER, DIENSTAG, "04:00")
    assert r.naechster_wecker == lokal(DIENSTAG, "06:15")
    assert r.status is PersonStatus.WERKTAG
    assert not r.ausnahme_loeschen


def test_ausnahme_kurz_vor_tagesende_zaehlt() -> None:
    """Eine Ausnahme 21:59 liegt vor dem Tagesende 22:00 und zählt."""
    e = eingaben(ausnahme_aktiv=True, ausnahme_zeit=time(21, 59))
    r = rechne(e, LEER, DIENSTAG, "04:00")
    assert r.naechster_wecker == lokal(DIENSTAG, "21:59")
    assert r.status is PersonStatus.AUSNAHME


def test_ausnahme_morgen_nach_dem_tagesende_von_morgen_zaehlt_nicht() -> None:
    """Abends gesetzt 22:30, morgen endet der Tag um 22:00: ignoriert (E18)."""
    e = eingaben(ausnahme_aktiv=True, ausnahme_zeit=time(22, 30))
    r = rechne(e, GEWECKT, DIENSTAG, "23:00")
    assert r.naechster_wecker == lokal(MITTWOCH, "06:15")
    assert r.status is PersonStatus.WERKTAG


def test_ausnahme_am_freien_tag_gilt_das_standard_tagesende() -> None:
    """Am Feiertag endet der Tag mit Standard (21:00); Ausnahme 21:30 zählt nicht."""
    e = eingaben(
        heute=TagInfo(feiertag="Fronleichnam"),
        ausnahme_aktiv=True,
        ausnahme_zeit=time(21, 30),
    )
    r = rechne(e, LEER, DIENSTAG, "04:00")
    assert r.naechster_wecker == lokal(DIENSTAG, "08:00")
    assert r.status is PersonStatus.FEIERTAG


# ---------------------------------------------------------------- Meldung „ignoriert“


def test_ignorierte_ausnahme_wird_gemeldet() -> None:
    """Zählt eine aktive Ausnahme wegen E18 nicht, meldet das Ergebnis es."""
    e = eingaben(ausnahme_aktiv=True, ausnahme_zeit=time(23, 0))
    assert rechne(e, LEER, DIENSTAG, "04:00").ausnahme_ignoriert


def test_gueltige_ausnahme_ist_nicht_ignoriert() -> None:
    """Eine gültige Ausnahme (auch erst morgen, E17) gilt nicht als ignoriert."""
    e = eingaben(ausnahme_aktiv=True, ausnahme_zeit=time(5, 30))
    assert not rechne(e, LEER, DIENSTAG, "06:00").ausnahme_ignoriert


def test_ausgeschaltete_ausnahme_ist_nicht_ignoriert() -> None:
    """Ohne aktive Ausnahme gibt es nichts zu melden."""
    e = eingaben(ausnahme_aktiv=False, ausnahme_zeit=time(23, 0))
    assert not rechne(e, LEER, DIENSTAG, "04:00").ausnahme_ignoriert


def test_ausnahme_morgen_ab_tagesende_ist_ignoriert() -> None:
    """Abends gesetzt 22:30, morgen endet der Tag um 22:00: ignoriert (E17, E18)."""
    e = eingaben(ausnahme_aktiv=True, ausnahme_zeit=time(22, 30))
    assert rechne(e, GEWECKT, DIENSTAG, "23:00").ausnahme_ignoriert


def test_inaktive_person_meldet_keine_ignorierte_ausnahme() -> None:
    """Bei Inaktiv wird die Ausnahme gelöscht, nicht als ignoriert gemeldet."""
    e = eingaben(raum_zugeordnet=False, ausnahme_aktiv=True, ausnahme_zeit=time(23, 0))
    r = rechne(e, LEER, DIENSTAG, "04:00")
    assert not r.ausnahme_ignoriert
    assert r.ausnahme_loeschen
