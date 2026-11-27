"""Tests für den Urlaub aus einem Kalender (ARCHITEKTUR.md 3.6, E38).

Urlaub gilt ganztägig: Ein Tag ist Urlaub, wenn ein Kalendereintrag ihn
berührt. Ganztägige Einträge haben ein exklusives Ende (HA-Kalender).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.homewake.logic.urlaub import (
    Termin,
    beruehrt,
    termine_aus_antwort,
    urlaub_an,
)

BERLIN = ZoneInfo("Europe/Berlin")
HEUTE = date(2026, 11, 26)
MORGEN = date(2026, 11, 27)


def dt(text: str) -> datetime:
    """Zeitpunkt in Berliner Zeit aus ``YYYY-MM-DD HH:MM``."""
    return datetime.fromisoformat(text).replace(tzinfo=BERLIN)


# ---------------------------------------------------------------- ganztägig


@pytest.mark.parametrize(
    ("beginn", "ende", "tag", "erwartet"),
    [
        # Ein-Tages-Urlaub am 26.: Ende ist der 27. (exklusiv)
        (date(2026, 11, 26), date(2026, 11, 27), HEUTE, True),
        (date(2026, 11, 26), date(2026, 11, 27), MORGEN, False),
        # mehrtägig 24.-27. (Ende 28.)
        (date(2026, 11, 24), date(2026, 11, 28), HEUTE, True),
        (date(2026, 11, 24), date(2026, 11, 28), MORGEN, True),
        (date(2026, 11, 24), date(2026, 11, 28), date(2026, 11, 28), False),
        (date(2026, 11, 24), date(2026, 11, 28), date(2026, 11, 23), False),
        # Ende gleich Beginn (eigentlich ungültig): gilt als der eine Tag
        (date(2026, 11, 26), date(2026, 11, 26), HEUTE, True),
        (date(2026, 11, 26), date(2026, 11, 26), MORGEN, False),
    ],
)
def test_ganztaegig(beginn: date, ende: date, tag: date, erwartet: bool) -> None:
    """Ganztägig: ``beginn <= tag < ende``."""
    assert beruehrt(Termin(beginn, ende), tag) is erwartet


# ---------------------------------------------------------------- mit Uhrzeit


@pytest.mark.parametrize(
    ("beginn", "ende", "tag", "erwartet"),
    [
        # endet heute 18:00: heute ist Urlaub (anders als bisher, E38)
        ("2026-11-20 08:00", "2026-11-26 18:00", HEUTE, True),
        ("2026-11-20 08:00", "2026-11-26 18:00", MORGEN, False),
        # beginnt heute abends: heute zählt schon
        ("2026-11-26 20:00", "2026-11-30 10:00", HEUTE, True),
        # kurzer Termin morgen früh
        ("2026-11-27 09:00", "2026-11-27 10:00", HEUTE, False),
        ("2026-11-27 09:00", "2026-11-27 10:00", MORGEN, True),
        # endet genau um Mitternacht: der Folgetag zählt nicht
        ("2026-11-25 08:00", "2026-11-26 00:00", HEUTE, False),
        # beginnt genau um Mitternacht
        ("2026-11-27 00:00", "2026-11-27 06:00", HEUTE, False),
        ("2026-11-27 00:00", "2026-11-27 06:00", MORGEN, True),
        # über Mitternacht
        ("2026-11-26 23:00", "2026-11-27 01:00", HEUTE, True),
        ("2026-11-26 23:00", "2026-11-27 01:00", MORGEN, True),
        # ohne Dauer: zählt am Tag des Zeitpunkts
        ("2026-11-26 12:00", "2026-11-26 12:00", HEUTE, True),
        ("2026-11-26 00:00", "2026-11-26 00:00", HEUTE, True),
        ("2026-11-26 00:00", "2026-11-26 00:00", date(2026, 11, 25), False),
    ],
)
def test_mit_uhrzeit(beginn: str, ende: str, tag: date, erwartet: bool) -> None:
    """Mit Uhrzeit: der Tag zählt, wenn der Termin ihn berührt."""
    assert beruehrt(Termin(dt(beginn), dt(ende)), tag) is erwartet


def test_termin_gilt_in_seiner_eigenen_zeitzone_utc() -> None:
    """Ein Termin in UTC gilt an seinem eingetragenen Tag (E38).

    23:30 UTC ist in Berlin schon der nächste Tag; zählen soll aber der Tag,
    an dem der Termin eingetragen ist, nicht der umgerechnete.
    """
    beginn = datetime(2026, 11, 26, 23, 30, tzinfo=UTC)
    termin = Termin(beginn, beginn + timedelta(minutes=20))
    assert beruehrt(termin, HEUTE) is True
    assert beruehrt(termin, MORGEN) is False


def test_termin_gilt_in_seiner_eigenen_zeitzone_tokio() -> None:
    """Urlaub in Tokio am 27.: zählt am 27., obwohl er in Berlin am 26. beginnt."""
    tokio = ZoneInfo("Asia/Tokyo")
    termin = Termin(
        datetime(2026, 11, 27, 1, 0, tzinfo=tokio),
        datetime(2026, 11, 27, 23, 0, tzinfo=tokio),
    )
    assert beruehrt(termin, HEUTE) is False
    assert beruehrt(termin, MORGEN) is True


def test_mehrtaegig_ueber_die_zeitumstellung_mit_festem_offset() -> None:
    """Wie aus HA: Beginn mit +02:00, Ende mit +01:00 (Zeitumstellung dazwischen)."""
    termin = Termin(
        datetime.fromisoformat("2026-10-23T18:00:00+02:00"),
        datetime.fromisoformat("2026-10-27T10:00:00+01:00"),
    )
    assert beruehrt(termin, date(2026, 10, 22)) is False
    assert beruehrt(termin, date(2026, 10, 23)) is True
    assert beruehrt(termin, date(2026, 10, 27)) is True
    assert beruehrt(termin, date(2026, 10, 28)) is False


def test_zeitumstellung() -> None:
    """Am Tag der Zeitumstellung (25 Stunden) zählt ein Termin um 23:30."""
    tag = date(2026, 10, 25)
    termin = Termin(dt("2026-10-25 23:30"), dt("2026-10-25 23:45"))
    assert beruehrt(termin, tag) is True
    assert beruehrt(termin, tag + timedelta(days=1)) is False


# ---------------------------------------------------------------- mehrere


def test_urlaub_an_prueft_alle_termine() -> None:
    """Auch ein zweiter Termin zählt (bisher sah HA nur einen, E38)."""
    termine = [
        Termin(dt("2026-11-26 09:00"), dt("2026-11-26 10:00")),  # kurz heute
        Termin(date(2026, 11, 27), date(2026, 12, 1)),  # Urlaub ab morgen
    ]
    assert urlaub_an(termine, HEUTE) is True
    assert urlaub_an(termine, MORGEN) is True
    assert urlaub_an(termine, date(2026, 12, 1)) is False


def test_ohne_termine_kein_urlaub() -> None:
    """Keine Termine → kein Urlaub."""
    assert urlaub_an([], HEUTE) is False


# ---------------------------------------------------------------- Antwort lesen


def test_termine_aus_antwort() -> None:
    """Liest ganztägige und Termine mit Uhrzeit aus ``calendar.get_events``."""
    antwort = [
        {"start": "2026-11-27", "end": "2026-11-28", "summary": "Urlaub"},
        {
            "start": "2026-11-26T09:00:00+01:00",
            "end": "2026-11-26T10:00:00+01:00",
            "summary": "Arzt",
        },
    ]
    assert termine_aus_antwort(antwort, zeitzone=BERLIN) == [
        Termin(date(2026, 11, 27), date(2026, 11, 28)),
        Termin(dt("2026-11-26 09:00"), dt("2026-11-26 10:00")),
    ]


def test_termin_ohne_zeitzone_gilt_in_ha_zeit() -> None:
    """Ein Zeitpunkt ohne Offset wird in der HA-Zeitzone gelesen."""
    antwort = [{"start": "2026-11-26T09:00:00", "end": "2026-11-26T10:00:00"}]
    [termin] = termine_aus_antwort(antwort, zeitzone=BERLIN)
    assert termin == Termin(dt("2026-11-26 09:00"), dt("2026-11-26 10:00"))
    assert isinstance(termin.beginn, datetime)
    assert termin.beginn.tzinfo is not None


@pytest.mark.parametrize(
    "eintrag",
    [
        {"start": "2026-11-26"},  # kein Ende
        {"end": "2026-11-26"},  # kein Beginn
        {"start": "kaputt", "end": "2026-11-27"},
        {"start": 5, "end": "2026-11-27"},
        {"start": "2026-11-28", "end": "2026-11-27"},  # Ende vor Beginn
        {
            "start": "2026-11-26T10:00:00+01:00",
            "end": "2026-11-26T09:00:00+01:00",
        },
        {"start": "2026-11-26", "end": "2026-11-27T10:00:00+01:00"},  # gemischt
        "kein dict",
    ],
)
def test_kaputte_eintraege_werden_uebersprungen(eintrag: object) -> None:
    """Unlesbare Einträge fallen weg, die übrigen zählen weiter."""
    gut = {"start": "2026-11-26", "end": "2026-11-27"}
    assert termine_aus_antwort([eintrag, gut], zeitzone=BERLIN) == [
        Termin(date(2026, 11, 26), date(2026, 11, 27))
    ]
