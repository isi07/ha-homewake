"""Ergebnisse für die Diagnose-Datei in einfache JSON-Werte umwandeln (Phase 8b).

Die Ergebnisse der Fachlogik sind Datenklassen mit Zeitpunkten, Enums und
Mengen. Für die Diagnose werden daraus Dicts, Listen und Texte.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Any


def als_json(wert: Any) -> Any:
    """Wandelt einen Wert rekursiv in JSON-fähige Werte um.

    Datenklassen werden Dicts, Zeitpunkte ISO-Text, Enums ihr Wert, Mengen
    sortierte Listen, Tupel Listen; Schlüssel von Dicts werden Text.
    """
    if is_dataclass(wert) and not isinstance(wert, type):
        wert = {f.name: getattr(wert, f.name) for f in fields(wert)}
    if isinstance(wert, Enum):
        wert = wert.value
    if isinstance(wert, datetime | date | time):
        return wert.isoformat()
    if isinstance(wert, Mapping):
        return {str(als_json(k)): als_json(v) for k, v in wert.items()}
    if isinstance(wert, set | frozenset):
        return sorted(als_json(v) for v in wert)
    if isinstance(wert, list | tuple):
        return [als_json(v) for v in wert]
    return wert
