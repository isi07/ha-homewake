"""Tests für den Sollzustand einer Person beim Start (ARCHITEKTUR.md 4.3, E15)."""

from __future__ import annotations

from datetime import date, time

from custom_components.homewake.logic.person import PersonZustand, TagInfo
from tests.logic.test_person_wecken import (
    DIENSTAG,
    LEER,
    MITTWOCH,
    eingaben,
    lokal,
    rechne,
)

FREITAG_DAVOR = date(2026, 7, 10)
MONTAG = date(2026, 7, 13)


def test_erster_start_mitten_am_tag_ist_wach() -> None:
    """Erster Start um 10:00: wach, heute um 06:15 geweckt, kein Wecken melden."""
    r = rechne(eingaben(), LEER, DIENSTAG, "10:00")
    assert r.wach
    assert r.geweckt_um == lokal(DIENSTAG, "06:15")
    assert not r.jetzt_geweckt
    assert r.naechster_wecker == lokal(MITTWOCH, "06:15")
    assert r.naechstes_tagesende == lokal(DIENSTAG, "22:00")
    assert r.tagesbeginn_heute == lokal(DIENSTAG, "06:15")


def test_erster_start_nach_dem_tagesende_schlaeft() -> None:
    """Erster Start um 23:00: nicht wach, heute zählt als geweckt, Wecker morgen."""
    r = rechne(eingaben(), LEER, DIENSTAG, "23:00")
    assert not r.wach
    assert not r.jetzt_geweckt
    assert r.geweckt_um == lokal(DIENSTAG, "06:15")
    assert r.naechster_wecker == lokal(MITTWOCH, "06:15")


def test_mehrere_tage_aus_rechnet_den_heutigen_zustand() -> None:
    """Zuletzt angekündigter Wecker vom Freitag, jetzt Dienstag 10:00: wach."""
    zustand = PersonZustand(naechster_wecker=lokal(FREITAG_DAVOR, "06:15"))
    r = rechne(eingaben(), zustand, DIENSTAG, "10:00")
    assert r.wach
    assert r.geweckt_um == lokal(DIENSTAG, "06:15")
    assert not r.jetzt_geweckt


def test_veralteter_wacher_zustand_vor_dem_wecken_schlaeft() -> None:
    """Gespeichert „wach seit Freitag“, jetzt Dienstag 04:00: schläft, Wecker 06:15."""
    zustand = PersonZustand(
        wach=True,
        geweckt_um=lokal(FREITAG_DAVOR, "06:15"),
        naechster_wecker=lokal(MONTAG, "06:15"),
    )
    r = rechne(eingaben(), zustand, DIENSTAG, "04:00")
    assert not r.wach
    assert not r.jetzt_geweckt
    assert r.naechster_wecker == lokal(DIENSTAG, "06:15")


def test_gestern_angekuendigter_wecker_weckt_heute_nicht_nachtraeglich() -> None:
    """Wecker von gestern verpasst, jetzt heute 05:00: kein Wecken, Wecker 06:15."""
    zustand = PersonZustand(naechster_wecker=lokal(MONTAG, "06:15"))
    r = rechne(eingaben(), zustand, DIENSTAG, "05:00")
    assert not r.wach
    assert not r.jetzt_geweckt
    assert r.naechster_wecker == lokal(DIENSTAG, "06:15")


def test_sollzustand_am_freien_tag_nutzt_standardzeile() -> None:
    """Erster Start an einem Feiertag um 09:00: geweckt um 08:00 (Standard)."""
    e = eingaben(heute=TagInfo(feiertag="Fronleichnam"))
    r = rechne(e, LEER, DIENSTAG, "09:00")
    assert r.wach
    assert r.geweckt_um == lokal(DIENSTAG, "08:00")


def test_sollzustand_mit_heute_vorbeier_ausnahme_verschiebt_sie_auf_morgen() -> None:
    """Erster Start 10:00 mit Ausnahme 05:00: wach nach Plan, Ausnahme gilt morgen."""
    e = eingaben(ausnahme_aktiv=True, ausnahme_zeit=time(5, 0))
    r = rechne(e, LEER, DIENSTAG, "10:00")
    assert r.wach
    assert not r.ausnahme_loeschen
    assert r.naechster_wecker == lokal(MITTWOCH, "05:00")
