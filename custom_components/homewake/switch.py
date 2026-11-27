"""Schalter von HomeWake: Ausnahme und Licht/Radio je Profil (Bedienung, 3.6)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SUBENTRY_PERSON
from .coordinator import HomeWakeConfigEntry, HomeWakeCoordinator
from .entity import HomeWakePersonEntity
from .logic.haus import PersonBedienung
from .logic.person import LichtRadio, Profil

PARALLEL_UPDATES = 0

# Schlüssel → (Profil, Licht oder Radio)  (E7)
LICHT_RADIO: dict[str, tuple[Profil, str]] = {
    f"{art}_{profil.value}": (profil, art)
    for profil in (Profil.ZEITPLAN, Profil.STANDARD, Profil.AUSNAHME)
    for art in ("licht", "radio")
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HomeWakeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Legt pro Person den Ausnahme-Schalter und sechs Licht/Radio-Schalter an."""
    coordinator = entry.runtime_data
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_PERSON:
            continue
        async_add_entities(
            [
                AusnahmeSchalter(coordinator, subentry, "ausnahme"),
                *(
                    LichtRadioSchalter(coordinator, subentry, schluessel)
                    for schluessel in LICHT_RADIO
                ),
            ],
            config_subentry_id=subentry.subentry_id,
        )


class _BedienSchalter(HomeWakePersonEntity, SwitchEntity):
    """Gemeinsame Basis: liest die Bedienwerte aus dem letzten Lauf."""

    @property
    def bedienung(self) -> PersonBedienung:
        """Bedienwerte der Person aus dem letzten Lauf."""
        return self.coordinator.data.bedienung.get(self._sid, PersonBedienung())


class AusnahmeSchalter(_BedienSchalter):
    """Ausnahme an/aus; Einschalten wird geprüft (E8, E18)."""

    @property
    def is_on(self) -> bool:
        """Ob die Ausnahme aktiv ist."""
        return self.bedienung.ausnahme_aktiv

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Ausnahme einschalten (geprüft)."""
        await self.coordinator.async_setze_bedienung(self._sid, ausnahme_aktiv=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Ausnahme ausschalten."""
        await self.coordinator.async_setze_bedienung(self._sid, ausnahme_aktiv=False)


class LichtRadioSchalter(_BedienSchalter):
    """Licht bzw. Radio für ein Profil (Zeitplan, Standard, Ausnahme)."""

    def __init__(
        self,
        coordinator: HomeWakeCoordinator,
        subentry: ConfigSubentry,
        schluessel: str,
    ) -> None:
        """Merkt sich Profil und Art (Licht/Radio) zum Schlüssel."""
        super().__init__(coordinator, subentry, schluessel)
        self._profil, self._art = LICHT_RADIO[schluessel]

    @property
    def is_on(self) -> bool:
        """Ob Licht bzw. Radio in diesem Profil eingeschaltet wird."""
        lr = self.bedienung.licht_radio.get(self._profil, LichtRadio())
        return lr.licht if self._art == "licht" else lr.radio

    async def _setze(self, an: bool) -> None:
        """Wert im Profil setzen (der Coordinator liest den aktuellen Stand)."""
        await self.coordinator.async_setze_licht_radio(
            self._sid, self._profil, self._art, an
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Einschalten."""
        await self._setze(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Ausschalten."""
        await self._setze(False)
