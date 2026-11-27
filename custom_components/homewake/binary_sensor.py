"""Binärsensoren von HomeWake: „Wach“ der Personen (ARCHITEKTUR.md 3.6)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SUBENTRY_PERSON, SUBENTRY_RAUM
from .coordinator import HomeWakeConfigEntry
from .entity import HomeWakePersonEntity, HomeWakeRaumEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HomeWakeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Legt „Wach“ pro Person an (am Gerät des Untereintrags)."""
    coordinator = entry.runtime_data
    for subentry in entry.subentries.values():
        if subentry.subentry_type == SUBENTRY_RAUM:
            async_add_entities(
                [
                    RaumWachSensor(coordinator, subentry, "wach"),
                    RaumTagSensor(coordinator, subentry, "tag"),
                ],
                config_subentry_id=subentry.subentry_id,
            )
            continue
        if subentry.subentry_type != SUBENTRY_PERSON:
            continue
        async_add_entities(
            [WachSensor(coordinator, subentry, "wach")],
            config_subentry_id=subentry.subentry_id,
        )


class WachSensor(HomeWakePersonEntity, BinarySensorEntity):
    """Ob die Person gerade wach ist (zwischen Wecken und Tagesende)."""

    @property
    def is_on(self) -> bool | None:
        """Wach ja/nein."""
        e = self.ergebnis
        return e.wach if e else None


class RaumWachSensor(HomeWakeRaumEntity, BinarySensorEntity):
    """Ob im Raum „wach“ ist (Weckzeit bis vor das geklemmte Tagesende)."""

    @property
    def is_on(self) -> bool | None:
        """Wach ja/nein."""
        e = self.ergebnis
        return e.wach if e else None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """``wecken_bis``: Aus-Zeitpunkt, solange ein Aus-Auftrag läuft (E64)."""
        if (bis := self.coordinator.wecken_bis(self._sid)) is None:
            return None
        return {"wecken_bis": bis}


class RaumTagSensor(HomeWakeRaumEntity, BinarySensorEntity):
    """Ob im Raum „Tag“ ist (für Rollläden, z. B. Adaptive Cover Pro)."""

    @property
    def is_on(self) -> bool | None:
        """Tag ja/nein."""
        e = self.ergebnis
        return e.tag if e else None
