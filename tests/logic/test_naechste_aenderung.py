"""Tests für „nächste Änderung“ von Person und Raum (Zeitplaner, E21).

Der spätere Zeitplaner in HA weckt HomeWake genau zu diesem Zeitpunkt. Er liegt
immer nach „jetzt“ und nie nach der nächsten lokalen Mitternacht.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta

import pytest

from custom_components.homewake.logic.raum import RaumZustand, berechne_raum
from custom_components.homewake.logic.zeitplan import naechste_mitternacht
from tests.logic.test_person_wecken import (
    GEWECKT,
    LEER,
    VOR_DEM_WECKEN,
    eingaben,
    rechne,
)
from tests.logic.test_raum_tag import BERLIN, DIENSTAG, MITTWOCH, lokal
from tests.logic.test_raum_zustand import SCHLAFZIMMER, angekuendigt

# ---------------------------------------------------------------- Mitternacht


def test_naechste_mitternacht_ist_beginn_des_folgetags() -> None:
    """Um 23:00 ist die nächste Mitternacht 00:00 des Folgetags."""
    jetzt = lokal(DIENSTAG, "23:00")
    assert naechste_mitternacht(jetzt, BERLIN) == lokal(MITTWOCH, "00:00")


def test_naechste_mitternacht_genau_um_mitternacht_ist_die_folgende() -> None:
    """Genau um 00:00 ist die nächste Mitternacht die des nächsten Tages."""
    jetzt = lokal(DIENSTAG, "00:00")
    assert naechste_mitternacht(jetzt, BERLIN) == lokal(MITTWOCH, "00:00")


def test_naechste_mitternacht_nach_sommerzeitende() -> None:
    """Am 25.10.2026 (25 Stunden) liegt Mitternacht 25 echte Stunden nach 00:00."""
    tag = date(2026, 10, 25)
    beginn = datetime.combine(tag, time(0), tzinfo=BERLIN)
    m = naechste_mitternacht(beginn, BERLIN)
    assert m == datetime.combine(date(2026, 10, 26), time(0), tzinfo=BERLIN)
    assert m.timestamp() - beginn.timestamp() == timedelta(hours=25).total_seconds()


# ---------------------------------------------------------------- Person


@pytest.mark.parametrize(
    ("zustand", "uhrzeit", "erwartet"),
    [
        (LEER, "04:00", lokal(DIENSTAG, "06:15")),
        (VOR_DEM_WECKEN, "06:15", lokal(DIENSTAG, "22:00")),
        (GEWECKT, "12:00", lokal(DIENSTAG, "22:00")),
        (GEWECKT, "22:00", lokal(MITTWOCH, "00:00")),
        (replace(GEWECKT, wach=False), "23:00", lokal(MITTWOCH, "00:00")),
    ],
    ids=[
        "vor_dem_wecken_wecker",
        "gerade_geweckt_tagesende",
        "tagsueber_tagesende",
        "tagesende_erreicht_mitternacht",
        "abends_mitternacht",
    ],
)
def test_person_naechste_aenderung(
    zustand: object, uhrzeit: str, erwartet: datetime
) -> None:
    """Nächste Änderung einer Person: Wecker, Tagesende oder Mitternacht."""
    r = rechne(eingaben(), zustand, DIENSTAG, uhrzeit)  # type: ignore[arg-type]
    assert r.naechste_aenderung == erwartet


# ---------------------------------------------------------------- Raum


@pytest.mark.parametrize(
    ("uhrzeit", "erwartet"),
    [
        ("04:00", lokal(DIENSTAG, "06:30")),
        ("06:45", lokal(DIENSTAG, "06:58:58")),
        ("07:00", lokal(DIENSTAG, "20:30")),
        ("21:00", lokal(MITTWOCH, "00:00")),
    ],
    ids=["vor_dem_wecken", "vor_tagesbeginn", "tagsueber", "abends"],
)
def test_raum_naechste_aenderung(uhrzeit: str, erwartet: datetime) -> None:
    """Nächste Änderung eines Raums: Weckzeit, Tagesbeginn, Tagesende, Mitternacht."""
    r = berechne_raum(
        SCHLAFZIMMER,
        angekuendigt("06:30"),
        jetzt=lokal(DIENSTAG, uhrzeit),
        zeitzone=BERLIN,
    )
    assert r.naechste_aenderung == erwartet


def test_raum_naechste_aenderung_liegt_immer_nach_jetzt() -> None:
    """Über den ganzen Tag liegt die nächste Änderung nach jetzt, bis Mitternacht."""
    zustand = RaumZustand()
    for minute in range(0, 24 * 60, 7):
        jetzt = lokal(DIENSTAG, "00:00") + timedelta(minutes=minute)
        r = berechne_raum(SCHLAFZIMMER, zustand, jetzt=jetzt, zeitzone=BERLIN)
        assert jetzt.timestamp() < r.naechste_aenderung.timestamp()
        assert r.naechste_aenderung.timestamp() <= lokal(MITTWOCH, "00:00").timestamp()
        zustand = r.zustand
