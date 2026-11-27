"""Sensoren von HomeWake: Personen (ARCHITEKTUR.md 3.6)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SUBENTRY_PERSON, SUBENTRY_RAUM
from .coordinator import HomeWakeConfigEntry, HomeWakeCoordinator
from .entity import HomeWakePersonEntity, HomeWakeRaumEntity
from .logic.person import PersonStatus
from .logic.raum import RaumErgebnis

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HomeWakeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Legt die Sensoren pro Person und Raum an (am Gerät des Untereintrags)."""
    coordinator = entry.runtime_data
    for subentry in entry.subentries.values():
        if subentry.subentry_type == SUBENTRY_RAUM:
            async_add_entities(
                [
                    RaumWeckzeitSensor(coordinator, subentry, "weckzeit"),
                    *(
                        RaumZeitSensor(coordinator, subentry, schluessel)
                        for schluessel in RAUM_ZEITEN
                        if schluessel != "weckzeit"
                    ),
                ],
                config_subentry_id=subentry.subentry_id,
            )
            continue
        if subentry.subentry_type != SUBENTRY_PERSON:
            continue
        async_add_entities(
            [
                NaechsterWeckerSensor(coordinator, subentry, "naechster_wecker"),
                NaechstesTagesendeSensor(coordinator, subentry, "naechstes_tagesende"),
                StatusSensor(coordinator, subentry, "status"),
            ],
            config_subentry_id=subentry.subentry_id,
        )


class NaechsterWeckerSensor(HomeWakePersonEntity, SensorEntity):
    """Nächster Wecker der Person."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        """Zeitpunkt des nächsten Weckers."""
        e = self.ergebnis
        return e.naechster_wecker if e else None


class NaechstesTagesendeSensor(HomeWakePersonEntity, SensorEntity):
    """Nächstes Tagesende der Person."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        """Zeitpunkt des nächsten Tagesendes."""
        e = self.ergebnis
        return e.naechstes_tagesende if e else None


class StatusSensor(HomeWakePersonEntity, SensorEntity):
    """Status der Person für den nächsten Wecker (4.1, 4.4)."""

    _attr_device_class = SensorDeviceClass.ENUM
    # Schule und Ferienliste nicht bei jeder Statusänderung in den Verlauf
    _unrecorded_attributes = frozenset({"schule", "schulferien", "schulferien_stand"})

    @property
    def options(self) -> list[str]:
        """Mögliche Status-Werte."""
        return [status.value for status in PersonStatus]

    @property
    def native_value(self) -> str | None:
        """Status als Schlüssel (übersetzt über ``translation_key``)."""
        e = self.ergebnis
        return e.status.value if e else None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Grund, Licht/Radio, Kandidat, Tagesbeginn/-ende heute/morgen (E16).

        Dazu Status und Grund für heute und morgen (Karte, E70). Mit Schule
        zusätzlich Schule, geladene Ferien und Stand (E40, E41).
        """
        e = self.ergebnis
        if e is None:
            return None
        schule = self.coordinator.schul_anzeige(self._sid) or {}
        return schule | {
            "grund": e.grund,
            "licht": e.licht_radio.licht,
            "radio": e.licht_radio.radio,
            "kandidat": e.kandidat_tag.value,
            "tagesbeginn_heute": e.tagesbeginn_heute,
            "tagesende_heute": e.tagesende_heute,
            "tagesbeginn_morgen": e.tagesbeginn_morgen,
            "tagesende_morgen": e.tagesende_morgen,
            "status_heute": e.status_heute.value,
            "grund_heute": e.grund_heute,
            "status_morgen": e.status_morgen.value,
            "grund_morgen": e.grund_morgen,
        }


# ---------------------------------------------------------------- Räume


RAUM_ZEITEN: dict[str, Callable[[RaumErgebnis], datetime]] = {
    "weckzeit": lambda e: e.weckzeit,
    "tagesbeginn": lambda e: e.tagesbeginn,
    "tagesende": lambda e: e.tagesende,
    "weckzeit_morgen": lambda e: e.weckzeit_morgen,
    "tagesbeginn_morgen": lambda e: e.tagesbeginn_morgen,
    "tagesende_morgen": lambda e: e.tagesende_morgen,
}


class RaumZeitSensor(HomeWakeRaumEntity, SensorEntity):
    """Zeitpunkt eines Raums (heute bzw. morgen) laut ``RAUM_ZEITEN``."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: HomeWakeCoordinator,
        subentry: ConfigSubentry,
        schluessel: str,
    ) -> None:
        """Wählt die Zeit-Funktion zum Schlüssel."""
        super().__init__(coordinator, subentry, schluessel)
        self._wert = RAUM_ZEITEN[schluessel]

    @property
    def native_value(self) -> datetime | None:
        """Zeitpunkt aus dem Raum-Ergebnis."""
        e = self.ergebnis
        return self._wert(e) if e else None


class RaumWeckzeitSensor(RaumZeitSensor):
    """Weckzeit des Raums heute, mit Personen, Licht/Radio und Quelle."""

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Personen, weckende Personen, Licht/Radio/Favorit, Quelle (3.7)."""
        e = self.ergebnis
        if e is None:
            return None
        return {
            "personen": list(e.personen),
            "weckende": list(e.weckende),
            "licht": e.licht,
            "radio": e.radio,
            "favorit": e.favorit,
            "quelle": e.quelle.value,
        }
