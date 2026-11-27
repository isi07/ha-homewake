"""Antwort von mehr-schulferien.de lesen (ARCHITEKTUR.md 3.6, E41, E44).

Die Ferien einer Schule kommen von ``/api/v2.1/schools/<slug>/periods`` als
einfache JSON-Daten herein; abgerufen wird in ``anbieter/mehr_schulferien.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from .schulferien import Ferien

NAME_ERSATZ = "Schulferien"


def _datum(wert: object) -> date | None:
    """Datum aus ``YYYY-MM-DD``, sonst None."""
    if not isinstance(wert, str):
        return None
    try:
        return date.fromisoformat(wert)
    except ValueError:
        return None


def ferien_aus_antwort(antwort: object) -> list[Ferien]:
    """Schulferien aus der Antwort der API, nach Beginn sortiert.

    Nur Einträge mit ``is_school_vacation`` zählen (Feiertage kommen aus
    ``holidays``, E9). Unlesbare Einträge werden übersprungen. Fehlt die Liste
    ``data`` ganz, ist die Antwort kaputt: ValueError, damit die gespeicherten
    Ferien nicht durch „keine Ferien“ ersetzt werden.
    """
    eintraege = antwort.get("data") if isinstance(antwort, Mapping) else None
    if not isinstance(eintraege, list):
        msg = "Antwort ohne Liste 'data'"
        raise ValueError(msg)
    ferien: list[Ferien] = []
    for eintrag in eintraege:
        if not isinstance(eintrag, Mapping):
            continue
        if eintrag.get("is_school_vacation") is not True:
            continue
        beginn = _datum(eintrag.get("starts_on"))
        ende = _datum(eintrag.get("ends_on"))
        name = eintrag.get("name")
        if beginn is None or ende is None or ende < beginn:
            continue
        if not isinstance(name, str):
            continue
        ferien.append(Ferien(beginn, ende, name.strip() or NAME_ERSATZ))
    return sorted(ferien, key=lambda f: (f.beginn, f.ende, f.name))
