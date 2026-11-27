"""Tests für die Dawn/Dusk-Klemmung (ARCHITEKTUR.md 4.6, E25).

Nachgebaut aus dem alten Projekt: tests/test_dawn_dusk_klemmung.py.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.homewake.logic.klemmung import (
    klemme_tagesbeginn,
    klemme_tagesende,
)

BERLIN = ZoneInfo("Europe/Berlin")
TAG = date(2026, 7, 13)
STUNDE = timedelta(minutes=60)


def lokal(uhrzeit: str, tag: date = TAG) -> datetime:
    """Berliner Ortszeitpunkt am Testtag."""
    return datetime.combine(tag, time.fromisoformat(uhrzeit), tzinfo=BERLIN)


# ---------------------------------------------------------------- Tagesbeginn (Dawn)


@pytest.mark.parametrize(
    ("dawn", "erwartet"),
    [
        ("06:00", "06:30"),
        ("06:30", "06:30"),
        ("07:00", "07:00"),
        ("07:30", "07:30"),
        ("09:00", "07:30"),
    ],
    ids=[
        "dawn_vor_weckzeit_bleibt_weckzeit",
        "dawn_genau_weckzeit_zaehlt_als_vorher",
        "dawn_im_fenster_wird_uebernommen",
        "dawn_genau_fensterende",
        "dawn_nach_fenster_wird_gedeckelt",
    ],
)
def test_tagesbeginn_klemmung(dawn: str, erwartet: str) -> None:
    """Tagesbeginn = Weckzeit, Dawn oder Weckzeit+Fenster (4.6, Morgen-Logik)."""
    assert klemme_tagesbeginn(lokal("06:30"), lokal(dawn), STUNDE) == lokal(erwartet)


@pytest.mark.parametrize("dawn", ["05:00", "06:30", "08:00"])
def test_tagesbeginn_fenster_null_bleibt_weckzeit(dawn: str) -> None:
    """Bei Fenster 0 bleibt der Tagesbeginn immer die Weckzeit."""
    ergebnis = klemme_tagesbeginn(lokal("06:30"), lokal(dawn), timedelta(0))
    assert ergebnis == lokal("06:30")


def test_tagesbeginn_ohne_dawn_bleibt_ungeklemmt() -> None:
    """Fehlt Dawn, wird nicht geklemmt (E25; bisher blieb der alte Wert stehen)."""
    assert klemme_tagesbeginn(lokal("06:30"), None, STUNDE) == lokal("06:30")


# ---------------------------------------------------------------- Tagesende (Dusk)


@pytest.mark.parametrize(
    ("dusk", "erwartet"),
    [
        ("19:00", "20:00"),
        ("20:00", "20:00"),
        ("20:30", "20:30"),
        ("21:00", "21:00"),
        ("22:00", "21:00"),
    ],
    ids=[
        "dusk_frueh_wird_auf_fensterstart_gedeckelt",
        "dusk_genau_fensterstart_zaehlt_als_frueh",
        "dusk_im_fenster_wird_uebernommen",
        "dusk_genau_tagesende",
        "dusk_spaet_bleibt_tagesende",
    ],
)
def test_tagesende_klemmung(dusk: str, erwartet: str) -> None:
    """Tagesende = Ende-Fenster, Dusk oder Ende (4.6, Abend-Logik)."""
    assert klemme_tagesende(lokal("21:00"), lokal(dusk), STUNDE) == lokal(erwartet)


@pytest.mark.parametrize("dusk", ["18:00", "21:00", "23:00"])
def test_tagesende_fenster_null_bleibt_tagesende(dusk: str) -> None:
    """Bei Fenster 0 bleibt das Tagesende immer unverändert."""
    ergebnis = klemme_tagesende(lokal("21:00"), lokal(dusk), timedelta(0))
    assert ergebnis == lokal("21:00")


def test_tagesende_ohne_dusk_bleibt_ungeklemmt() -> None:
    """Fehlt Dusk, wird nicht geklemmt (E25)."""
    assert klemme_tagesende(lokal("21:00"), None, STUNDE) == lokal("21:00")


# ---------------------------------------------------------------- Grenzfälle


def test_fenster_ueber_die_zeitumstellung_rechnet_echte_minuten() -> None:
    """01:30 + 60 min am 29.03.2026 ist real 03:30 Sommerzeit, nicht 02:30."""
    tag = date(2026, 3, 29)
    ergebnis = klemme_tagesbeginn(lokal("01:30", tag), lokal("05:00", tag), STUNDE)
    assert ergebnis.astimezone(UTC) == datetime(2026, 3, 29, 1, 30, tzinfo=UTC)
    assert ergebnis.utcoffset() == timedelta(hours=2)


def test_ergebnis_traegt_die_zeitzone_der_weckzeit() -> None:
    """Auch wenn Dawn in UTC kommt, liegt das Ergebnis in der Zeitzone der Weckzeit."""
    dawn_utc = lokal("07:00").astimezone(UTC)
    ergebnis = klemme_tagesbeginn(lokal("06:30"), dawn_utc, STUNDE)
    assert ergebnis == lokal("07:00")
    assert ergebnis.tzinfo is BERLIN


def test_negatives_fenster_ist_ein_fehler() -> None:
    """Ein negatives Klemm-Fenster ist ungültig."""
    with pytest.raises(ValueError):
        klemme_tagesbeginn(lokal("06:30"), lokal("07:00"), timedelta(minutes=-1))
    with pytest.raises(ValueError):
        klemme_tagesende(lokal("21:00"), lokal("20:00"), timedelta(minutes=-1))
