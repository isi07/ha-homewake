"""HomeWake: Wecker fürs Zuhause in Home Assistant."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import CONF_LAUTSPRECHER, CONF_LICHTER, DOMAIN
from .coordinator import STORE_VERSION, HomeWakeConfigEntry, HomeWakeCoordinator

_LOGGER = logging.getLogger(__name__)

# Nur über die UI einzurichten (kein YAML)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Gebaute Dashboard-Karte, mitgeliefert und von HomeWake angemeldet (E68, E69)
KARTE_URL = "/homewake/homewake-card.js"
KARTE_DATEI = Path(__file__).parent / "frontend" / "homewake-card.js"

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]


def _struktur(entry: HomeWakeConfigEntry) -> dict[str, tuple[str, str, Any, bool]]:
    """Untereinträge mit Typ, Titel, Lautsprecher und ob Lichter eingetragen sind.

    Ändert sich das, wird neu geladen (5.4): neue Geräte/Entities (z. B. die
    Taste „Wecken beenden“ beim ersten Licht), und die Beobachtung der
    Lautsprecher wird neu angemeldet.
    """
    return {
        sid: (
            sub.subentry_type,
            sub.title,
            sub.data.get(CONF_LAUTSPRECHER),
            bool(sub.data.get(CONF_LICHTER)),
        )
        for sid, sub in entry.subentries.items()
    }


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Beim Start von HA einmal: die Dashboard-Karte anmelden (E69)."""
    await _karte_anmelden(hass)
    return True


def _pruefsumme(datei: Path) -> str | None:
    """Kurze Prüfsumme der Datei; None, wenn sie fehlt (läuft im Executor)."""
    try:
        return hashlib.sha256(datei.read_bytes()).hexdigest()[:12]
    except OSError:
        return None


async def _karte_anmelden(hass: HomeAssistant) -> None:
    """Karte als statische Datei bereitstellen und als Zusatz-Modul laden lassen.

    Die Prüfsumme in der Adresse sorgt dafür, dass der Browser nach einem
    Update die neue Fassung lädt statt der zwischengespeicherten. Fehlt die
    Datei, läuft HomeWake ohne Karte weiter.
    """
    pruefsumme = await hass.async_add_executor_job(_pruefsumme, KARTE_DATEI)
    if pruefsumme is None:
        _LOGGER.warning("Dashboard-Karte fehlt: %s", KARTE_DATEI)
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(KARTE_URL, str(KARTE_DATEI), cache_headers=True)]
    )
    add_extra_js_url(hass, f"{KARTE_URL}?v={pruefsumme}")


async def async_setup_entry(hass: HomeAssistant, entry: HomeWakeConfigEntry) -> bool:
    """Richtet HomeWake aus einem Config-Eintrag ein."""
    coordinator = HomeWakeCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    struktur = _struktur(entry)

    async def _geaendert(hass: HomeAssistant, entry: HomeWakeConfigEntry) -> None:
        """Neu/entfernt/umbenannt → neu laden; sonst nur neu rechnen."""
        if _struktur(entry) != struktur:
            hass.config_entries.async_schedule_reload(entry.entry_id)
        else:
            await coordinator.async_request_refresh()

    entry.async_on_unload(entry.add_update_listener(_geaendert))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HomeWakeConfigEntry) -> bool:
    """Entlädt einen HomeWake-Config-Eintrag."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: HomeWakeConfigEntry) -> None:
    """Löscht beim Entfernen von HomeWake auch seine Speicherdatei (5.3)."""
    store: Store[dict[str, Any]] = Store(
        hass, STORE_VERSION, f"{DOMAIN}.{entry.entry_id}"
    )
    await store.async_remove()
