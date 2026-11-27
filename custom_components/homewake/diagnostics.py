"""Diagnose-Datei von HomeWake (Quality Scale ``diagnostics``).

Enthält Eintrag, Untereinträge, Speicher, das letzte Ergebnis, den Stand der
Hintergrund-Abrufe und des Schaltens (offene Aus-Aufträge, Geräte im erneuten
Versuch, gezählt pro Raum). Geschwärzt werden Namen von Personen und Räumen,
Urlaubskalender, Schule, HA-Bereich und die Geräte der Räume; vom Urlaub
erscheinen nur heute und morgen, Schulen nur unter einer laufenden Nummer.
Sichtbar bleiben Radio-Favoriten und die Quelle eines offenen Aus-Auftrags
(Sendernamen, E49).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import (
    CONF_BEREICH,
    CONF_LAUTSPRECHER,
    CONF_LICHTER,
    CONF_SCHULE,
    CONF_URLAUBSKALENDER,
)
from .coordinator import HomeWakeConfigEntry

ZU_SCHWAERZEN = {
    "title",  # Name der Person bzw. des Raums
    "weckende",  # Namen der weckenden Personen
    "im_raum",  # Namen der Personen im Raum
    CONF_URLAUBSKALENDER,
    CONF_SCHULE,
    CONF_BEREICH,
    CONF_LICHTER,
    CONF_LAUTSPRECHER,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HomeWakeConfigEntry
) -> dict[str, Any]:
    """Diagnose-Daten eines HomeWake-Eintrags, sensible Werte geschwärzt."""
    return async_redact_data(entry.runtime_data.diagnose(), ZU_SCHWAERZEN)
