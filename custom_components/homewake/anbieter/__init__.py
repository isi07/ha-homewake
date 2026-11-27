"""Anbieter für Schulferien (ARCHITEKTUR.md 3.6, E44).

Ein Anbieter beschreibt, wie eine Schule gewählt wird (Auswahlschritte mit
Listen) und wie ihre Ferien abgerufen werden. Der Rest von HomeWake (Dialog,
Coordinator, Speicher, Hinweis) kennt nur Anbieter + Kennung. Einen weiteren
Dienst ergänzen: neue Datei hier, Eintrag in ``ANBIETER``, Übersetzungen für
seine Schritte.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date

from homeassistant.core import HomeAssistant

from ..logic.schulferien import Ferien


class AnbieterFehler(Exception):
    """Anbieter nicht erreichbar oder Antwort unbrauchbar."""


@dataclass(frozen=True, slots=True)
class Anbieter:
    """Ein Dienst, der Schulferien liefert.

    ``stufen`` sind die Auswahlschritte im Dialog (Schritt-IDs), der letzte
    wählt die Schule. ``liste(hass, stufe, auswahl)`` liefert Kennung → Name
    einer Stufe, gefiltert nach der Wahl der vorigen (``None`` bei der ersten).
    ``pfad_anfang`` steht vor dem Auswahlweg (z. B. das Land).
    """

    titel: str
    stufen: tuple[str, ...]
    pfad_anfang: tuple[str, ...]
    liste: Callable[[HomeAssistant, str, str | None], Awaitable[dict[str, str]]]
    ferien: Callable[[HomeAssistant, str, date, date], Awaitable[list[Ferien]]]


def _alle() -> dict[str, Anbieter]:
    """Alle Anbieter: Schlüssel → Anbieter (Import hier, um Kreise zu vermeiden)."""
    from . import mehr_schulferien  # noqa: PLC0415

    return {"mehr_schulferien": mehr_schulferien.ANBIETER}


ANBIETER: dict[str, Anbieter] = _alle()
