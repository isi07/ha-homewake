"""Auswahl-Entities von HomeWake: Raum einer Person (Bedienung, ARCHITEKTUR.md 3.6)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, SUBENTRY_PERSON, SUBENTRY_RAUM
from .coordinator import HomeWakeConfigEntry
from .entity import HomeWakePersonEntity, HomeWakeRaumEntity

PARALLEL_UPDATES = 0
KEIN_RAUM = "kein_raum"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HomeWakeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Legt Raum- und Favoriten-Auswahl pro Person, Standard-Favorit pro Raum an."""
    coordinator = entry.runtime_data
    ent_reg = er.async_get(hass)
    for subentry in entry.subentries.values():
        sid = subentry.subentry_id
        if subentry.subentry_type == SUBENTRY_RAUM:
            if coordinator.lautsprecher(sid) is not None:
                async_add_entities(
                    [StandardFavoritAuswahl(coordinator, subentry, "standard_favorit")],
                    config_subentry_id=sid,
                )
            elif eid := ent_reg.async_get_entity_id(
                "select", DOMAIN, f"{sid}_standard_favorit"
            ):
                # Lautsprecher entfernt: Auswahl nicht verwaist stehen lassen (5.4).
                ent_reg.async_remove(eid)
            continue
        if subentry.subentry_type != SUBENTRY_PERSON:
            continue
        async_add_entities(
            [
                RaumAuswahl(coordinator, subentry, "raum"),
                FavoritAuswahl(coordinator, subentry, "favorit"),
            ],
            config_subentry_id=sid,
        )


class RaumAuswahl(HomeWakePersonEntity, SelectEntity):
    """Raum der Person: „kein Raum“ oder einer der zuordenbaren Räume (E11).

    Gespeichert wird die ID des Raums, angezeigt sein Name.
    """

    def _raeume(self) -> dict[str, str]:
        """Zuordenbare Räume aus dem letzten Lauf: Name → ID."""
        return {name: rid for rid, name in self.coordinator.zuordenbare_raeume.items()}

    @property
    def options(self) -> list[str]:
        """„kein Raum“ und die Namen der zuordenbaren Räume (wie im letzten Lauf)."""
        return [KEIN_RAUM, *sorted(self._raeume(), key=str.casefold)]

    @property
    def current_option(self) -> str | None:
        """Name des aktuellen Raums oder „kein Raum“."""
        e = self.ergebnis
        if e is None:
            return None
        rid = self.coordinator.raum_id(self._sid)
        return self.coordinator.zuordenbare_raeume.get(rid or "", KEIN_RAUM)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """ID des Raums, für den Sprung in der Karte (E70).

        None bei „kein Raum“ und wie ``current_option`` auch, wenn der
        gespeicherte Raum nicht (mehr) zuordenbar ist.
        """
        rid = self.coordinator.raum_id(self._sid)
        if rid not in self.coordinator.zuordenbare_raeume:
            rid = None
        return {"raum_id": rid}

    async def async_select_option(self, option: str) -> None:
        """Raum wählen und neu rechnen.

        Ungültige Optionen lehnt HA schon vorher ab (SelectEntity prüft gegen
        ``options``); „kein Raum“ ergibt None.
        """
        await self.coordinator.async_setze_raum(self._sid, self._raeume().get(option))


KEIN_FAVORIT = "kein_favorit"


def _favoriten_optionen(quellen: list[str], gewaehlt: str | None) -> list[str]:
    """„kein Favorit“, die Quellen und (falls nicht enthalten) der gewählte Wert."""
    optionen = [KEIN_FAVORIT, *quellen]
    if gewaehlt and gewaehlt not in optionen:
        optionen.append(gewaehlt)
    return optionen


class FavoritAuswahl(HomeWakePersonEntity, SelectEntity):
    """Radio-Favorit der Person aus den Quellen des Lautsprechers im Raum (E33)."""

    def _gewaehlt(self) -> str | None:
        """Gespeicherter Favorit (aktueller Bedienwert)."""
        return self.coordinator.bedienung(self._sid).favorit

    @property
    def options(self) -> list[str]:
        """Quellen des Lautsprechers im Raum der Person."""
        raum = self.coordinator.raum_id(self._sid)
        return _favoriten_optionen(self.coordinator.quellen(raum), self._gewaehlt())

    @property
    def current_option(self) -> str | None:
        """Gewählter Favorit oder „kein Favorit“."""
        if self.ergebnis is None:
            return None
        return self._gewaehlt() or KEIN_FAVORIT

    async def async_select_option(self, option: str) -> None:
        """Favorit wählen."""
        await self.coordinator.async_setze_bedienung(
            self._sid, favorit=None if option == KEIN_FAVORIT else option
        )


class StandardFavoritAuswahl(HomeWakeRaumEntity, SelectEntity):
    """Standard-Favorit eines Raums (Bedienung, E33), nur mit Lautsprecher."""

    @property
    def options(self) -> list[str]:
        """Quellen des Raum-Lautsprechers."""
        return _favoriten_optionen(
            self.coordinator.quellen(self._sid),
            self.coordinator.standard_favorit(self._sid),
        )

    @property
    def current_option(self) -> str | None:
        """Gewählter Standard-Favorit oder „kein Favorit“."""
        return self.coordinator.standard_favorit(self._sid) or KEIN_FAVORIT

    async def async_select_option(self, option: str) -> None:
        """Standard-Favorit wählen."""
        await self.coordinator.async_setze_standard_favorit(
            self._sid, None if option == KEIN_FAVORIT else option
        )
