"""Tests für das Umwandeln von Ergebnissen in JSON für die Diagnose (Phase 8b)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import StrEnum
from zoneinfo import ZoneInfo

from custom_components.homewake.logic.diagnose import als_json

BERLIN = ZoneInfo("Europe/Berlin")


class Farbe(StrEnum):
    """Beispiel-Enum."""

    ROT = "rot"


@dataclass(frozen=True)
class Innen:
    """Verschachtelter Wert."""

    wann: datetime
    farbe: Farbe = Farbe.ROT


@dataclass(frozen=True)
class Aussen:
    """Wert mit allem, was in Ergebnissen vorkommt."""

    innen: Innen
    tag: date
    uhr: time | None
    namen: tuple[str, ...] = ()
    menge: frozenset[str] = frozenset()
    nach_farbe: dict[Farbe, Innen] = field(default_factory=dict)


def test_als_json_wandelt_alles_in_einfache_werte() -> None:
    """Zeitpunkte als ISO-Text, Enums als Wert, Mengen sortiert, Schlüssel als Text."""
    wann = datetime(2026, 7, 14, 6, 30, tzinfo=BERLIN)
    wert = Aussen(
        innen=Innen(wann=wann),
        tag=date(2026, 7, 14),
        uhr=time(6, 30),
        namen=("Mutter", "Vater"),
        menge=frozenset({"b", "a"}),
        nach_farbe={Farbe.ROT: Innen(wann=wann)},
    )
    assert als_json(wert) == {
        "innen": {"wann": "2026-07-14T06:30:00+02:00", "farbe": "rot"},
        "tag": "2026-07-14",
        "uhr": "06:30:00",
        "namen": ["Mutter", "Vater"],
        "menge": ["a", "b"],
        "nach_farbe": {"rot": {"wann": "2026-07-14T06:30:00+02:00", "farbe": "rot"}},
    }


def test_als_json_laesst_einfache_werte_stehen() -> None:
    """None, Zahlen, Texte und Wahrheitswerte bleiben, wie sie sind."""
    assert als_json([None, 1, 1.5, "x", True]) == [None, 1, 1.5, "x", True]
