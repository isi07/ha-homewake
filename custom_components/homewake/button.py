"""Taste „Wecken beenden“ pro Raum (ARCHITEKTUR.md 3.7, E53, E60)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, SUBENTRY_RAUM
from .coordinator import HomeWakeConfigEntry
from .entity import HomeWakeRaumEntity

PARALLEL_UPDATES = 0

SCHLUESSEL = "wecken_beenden"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HomeWakeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Legt die Taste für jeden Raum mit Lichtern oder Lautsprecher an."""
    coordinator = entry.runtime_data
    ent_reg = er.async_get(hass)
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_RAUM:
            continue
        sid = subentry.subentry_id
        if coordinator.hat_aktorik(sid):
            async_add_entities(
                [WeckenBeendenTaste(coordinator, subentry, SCHLUESSEL)],
                config_subentry_id=sid,
            )
        elif eid := ent_reg.async_get_entity_id(
            "button", DOMAIN, f"{sid}_{SCHLUESSEL}"
        ):
            # Keine Aktorik mehr: Taste nicht verwaist stehen lassen (5.4).
            ent_reg.async_remove(eid)


class WeckenBeendenTaste(HomeWakeRaumEntity, ButtonEntity):
    """Schaltet Licht und Radio des Raums sofort aus (E60).

    Nur, was noch so ist, wie HomeWake es gesetzt hat (E50); laufende
    Versuche und der Aus-Auftrag entfallen. Ohne laufendes Wecken passiert
    nichts. Auch in Automationen über ``button.press`` nutzbar.
    """

    @property
    def available(self) -> bool:
        """Immer verfügbar: Ausschalten soll auch ohne Rechenergebnis gehen."""
        return True

    async def async_press(self) -> None:
        """Wecken des Raums beenden."""
        self.coordinator.wecken_beenden(self._sid)
