"""Feiertage über die Bibliothek ``holidays`` (offline, ARCHITEKTUR.md 3.5, E9).

Alle Funktionen hier sind blockierend (die Bibliothek lädt Daten und
Übersetzungen von der Platte) und werden im Executor aufgerufen.
"""

from __future__ import annotations

from datetime import date

from holidays import country_holidays, list_supported_countries


def laender() -> list[str]:
    """Länder-Codes, für die es Feiertage gibt (ohne Aliase)."""
    return sorted(list_supported_countries(include_aliases=False))


def regionen(land: str) -> dict[str, str]:
    """Regionen (z. B. Bundesländer) eines Landes: Code → Anzeigename."""
    obj = country_holidays(land)
    namen = obj.get_subdivision_aliases() if obj.subdivisions_aliases else {}
    return {
        code: ", ".join(namen.get(code) or []) or code
        for code in list_supported_countries(include_aliases=False).get(land, [])
    }


def feiertage(
    land: str, bundesland: str | None, jahr: int, sprache: str
) -> dict[date, str]:
    """Feiertage eines Jahres mit Namen in der HA-Sprache (falls unterstützt)."""
    unterstuetzt = list(country_holidays(land).supported_languages)
    passend = _sprache(sprache, unterstuetzt)
    obj = country_holidays(land, subdiv=bundesland, years=jahr, language=passend)
    return {tag: str(name) for tag, name in obj.items()}


def _sprache(sprache: str, unterstuetzt: list[str]) -> str | None:
    """Passende Sprache der Bibliothek zur HA-Sprache, sonst None (Landessprache).

    Reihenfolge: genau, mit Unterstrich, Grundsprache, „Grundsprache_…“.
    """
    kandidaten = [sprache, sprache.replace("-", "_")]
    basis = sprache.split("-", maxsplit=1)[0].split("_", maxsplit=1)[0]
    kandidaten.append(basis)
    for kandidat in kandidaten:
        if kandidat in unterstuetzt:
            return kandidat
    return next((s for s in unterstuetzt if s.split("_")[0] == basis), None)
