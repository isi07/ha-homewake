"""Gemeinsame Basis der HomeWake-Entities (ARCHITEKTUR.md 3.8, 5.4)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .coordinator import HomeWakeCoordinator
from .logic.person import PersonErgebnis
from .logic.raum import RaumErgebnis


class HomeWakeEntity(CoordinatorEntity[HomeWakeCoordinator]):
    """Entity eines Untereintrags: ein Gerät pro Person bzw. Raum.

    Anzeigename = Gerätename + Entity-Name aus der Übersetzung; die Entity-ID
    erzeugt HA daraus (ARCHITEKTUR.md 3.8). unique_id: ``<Untereintrag>_<Schlüssel>``.
    """

    _attr_has_entity_name = True
    _modell = ""

    def __init__(
        self,
        coordinator: HomeWakeCoordinator,
        subentry: ConfigSubentry,
        schluessel: str,
    ) -> None:
        """Verbindet die Entity mit Coordinator und Untereintrag."""
        super().__init__(coordinator)
        self._sid = subentry.subentry_id
        self._attr_translation_key = schluessel
        self._attr_unique_id = f"{subentry.subentry_id}_{schluessel}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            manufacturer=NAME,
            model=self._modell,
            entry_type=DeviceEntryType.SERVICE,
        )


class HomeWakePersonEntity(HomeWakeEntity):
    """Entity einer Person."""

    _modell = "Person"

    @property
    def ergebnis(self) -> PersonErgebnis | None:
        """Ergebnis dieser Person aus dem letzten Lauf (None = nicht berechnet)."""
        return self.coordinator.data.personen.get(self._sid)

    @property
    def available(self) -> bool:
        """Verfügbar, wenn der Coordinator lief und die Person berechnet wurde."""
        return super().available and self.ergebnis is not None


class HomeWakeRaumEntity(HomeWakeEntity):
    """Entity eines Raums."""

    _modell = "Raum"

    @property
    def ergebnis(self) -> RaumErgebnis | None:
        """Ergebnis dieses Raums aus dem letzten Lauf (None = nicht berechnet)."""
        return self.coordinator.data.raeume.get(self._sid)

    @property
    def available(self) -> bool:
        """Verfügbar, wenn der Coordinator lief und der Raum berechnet wurde."""
        return super().available and self.ergebnis is not None
