"""Uhrzeit-Entities von HomeWake: Ausnahme-Weckzeit (Bedienung, 3.6)."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SUBENTRY_PERSON
from .coordinator import HomeWakeConfigEntry
from .entity import HomeWakePersonEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HomeWakeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Legt pro Person die Ausnahme-Weckzeit an."""
    coordinator = entry.runtime_data
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_PERSON:
            continue
        async_add_entities(
            [AusnahmeZeit(coordinator, subentry, "ausnahme_zeit")],
            config_subentry_id=subentry.subentry_id,
        )


class AusnahmeZeit(HomeWakePersonEntity, TimeEntity):
    """Uhrzeit der Ausnahme; bei aktiver Ausnahme wird sie geprüft (E18).

    Ohne eigene Uhrzeit zeigt sie den Beginn der Standard-Zeile (E63).
    """

    @property
    def native_value(self) -> time | None:
        """Eigene Uhrzeit oder der Standard-Beginn."""
        return self.coordinator.ausnahme_zeit(self._sid)

    async def async_set_value(self, value: time) -> None:
        """Uhrzeit setzen (geprüft, wenn die Ausnahme an ist)."""
        await self.coordinator.async_setze_bedienung(self._sid, ausnahme_zeit=value)
