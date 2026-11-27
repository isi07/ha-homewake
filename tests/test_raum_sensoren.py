"""Tests für Raum-Sensoren und die Raum-Auswahl der Person (Phase 2, 3.6, 3.7)."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigSubentryDataWithId
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.homewake.const import SUBENTRY_RAUM
from tests.test_person_sensoren import (
    PLAN,
    einrichten,
    entity_id,
    person,
    vorspulen,
    zustand,
)

RAUM_PLAN = {
    "standard": {"beginn": "07:00:00", "ende": "22:30:00"},
    **{
        tag: {"beginn": "06:00:00", "ende": "22:15:00"}
        for tag in ("montag", "dienstag", "mittwoch", "donnerstag", "freitag")
    },
    "samstag": {},
    "sonntag": {},
}
RAUM_SENSOREN = (
    "weckzeit",
    "tagesbeginn",
    "tagesende",
    "weckzeit_morgen",
    "tagesbeginn_morgen",
    "tagesende_morgen",
)


def raum(sid: str, titel: str, **daten: Any) -> ConfigSubentryDataWithId:
    """Raum-Untereintrag mit Standardplan Mo-Fr 06:00-22:15."""
    return ConfigSubentryDataWithId(
        data={
            "bereich": None,
            "zeitplan": RAUM_PLAN,
            "zuordenbar": True,
            "klemm_beginn": 60,
            "klemm_ende": 60,
            "lichter": [],
            "helligkeit": 100,
            "elevation": -3.0,
            "dauer": 45,
            "lautsprecher": None,
            "lautstaerke": 30,
        }
        | daten,
        subentry_type=SUBENTRY_RAUM,
        title=titel,
        unique_id=None,
        subentry_id=sid,
    )


async def waehle_raum(hass: HomeAssistant, sid: str, option: str) -> None:
    """Wählt in der Raum-Auswahl einer Person eine Option."""
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id(hass, "select", sid, "raum"), "option": option},
        blocking=True,
    )
    await hass.async_block_till_done()


def optionen(hass: HomeAssistant, sid: str) -> list[str]:
    """Optionen der Raum-Auswahl einer Person."""
    state = hass.states.get(entity_id(hass, "select", sid, "raum"))
    assert state is not None
    return list(state.attributes["options"])


# ---------------------------------------------------------------- Raum-Sensoren


async def test_raum_bekommt_geraet_und_entities(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ein Raum bekommt sechs Zeit-Sensoren sowie „Wach“ und „Tag“."""
    await einrichten(hass, freezer, raum("r1", "Schlafzimmer"))
    ent_reg = er.async_get(hass)
    for schluessel in RAUM_SENSOREN:
        eintrag = ent_reg.async_get(entity_id(hass, "sensor", "r1", schluessel))
        assert eintrag is not None
        assert eintrag.config_subentry_id == "r1"
    for schluessel in ("wach", "tag"):
        entity_id(hass, "binary_sensor", "r1", schluessel)


async def test_raum_ohne_person_nimmt_standardplan(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ohne Personen: Weckzeit 06:00 heute, morgen ebenso (Standardplan)."""
    await einrichten(hass, freezer, raum("r1", "Flur"))
    assert zustand(hass, "sensor", "r1", "weckzeit") == "2026-07-14T04:00:00+00:00"
    # Tagesende 22:15, an die Abenddämmerung (~22:12) geklemmt (Fenster 60 min)
    ende = zustand(hass, "sensor", "r1", "tagesende")
    assert "2026-07-14T19:15:00+00:00" < ende <= "2026-07-14T20:15:00+00:00"
    assert (
        zustand(hass, "sensor", "r1", "weckzeit_morgen") == "2026-07-15T04:00:00+00:00"
    )
    state = hass.states.get(entity_id(hass, "sensor", "r1", "weckzeit"))
    assert state is not None
    assert state.attributes["quelle"] == "standardplan"
    assert state.attributes["personen"] == []


async def test_raum_wach_und_tag_zur_weckzeit(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Zur Weckzeit schalten „Wach“ und (ohne Dämmerung) „Tag“ ein."""
    await einrichten(hass, freezer, raum("r1", "Flur"))
    assert zustand(hass, "binary_sensor", "r1", "wach") == STATE_OFF
    await vorspulen(hass, freezer, "2026-07-14T06:00:00+02:00")
    assert zustand(hass, "binary_sensor", "r1", "wach") == STATE_ON
    assert zustand(hass, "binary_sensor", "r1", "tag") == STATE_ON


async def test_raum_zustand_uebersteht_neuladen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Der eingefrorene Raum-Wert bleibt nach dem Neuladen erhalten."""
    entry = await einrichten(hass, freezer, raum("r1", "Flur"))
    await vorspulen(hass, freezer, "2026-07-14T06:00:00+02:00")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert zustand(hass, "binary_sensor", "r1", "wach") == STATE_ON
    assert zustand(hass, "sensor", "r1", "weckzeit") == "2026-07-14T04:00:00+00:00"


# ---------------------------------------------------------------- Raum-Auswahl


async def test_raum_auswahl_bietet_zuordenbare_raeume(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Die Auswahl zeigt „kein Raum“ und nur zuordenbare Räume."""
    await einrichten(
        hass,
        freezer,
        person("p1", "Vater"),
        raum("r1", "Schlafzimmer"),
        raum("r2", "Flur", zuordenbar=False),
    )
    assert optionen(hass, "p1") == ["kein_raum", "Schlafzimmer"]
    assert zustand(hass, "select", "p1", "raum") == "kein_raum"


async def test_person_in_raum_setzen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Raum wählen: Person wird aktiv, der Raum übernimmt ihre Weckzeit."""
    await einrichten(hass, freezer, person("p1", "Vater"), raum("r1", "Schlafzimmer"))
    await waehle_raum(hass, "p1", "Schlafzimmer")
    assert zustand(hass, "select", "p1", "raum") == "Schlafzimmer"
    assert zustand(hass, "sensor", "p1", "status") == "werktag"
    assert zustand(hass, "sensor", "r1", "weckzeit") == "2026-07-14T04:15:00+00:00"
    state = hass.states.get(entity_id(hass, "sensor", "r1", "weckzeit"))
    assert state is not None
    assert state.attributes["personen"] == ["Vater"]
    assert state.attributes["quelle"] == "personen"


async def test_raum_auswahl_uebersteht_neuladen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Die gewählte Raum-Zuordnung wird gespeichert."""
    entry = await einrichten(
        hass, freezer, person("p1", "Vater"), raum("r1", "Schlafzimmer")
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert zustand(hass, "select", "p1", "raum") == "Schlafzimmer"


async def test_unbekannte_option_wird_abgelehnt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Eine Option, die es nicht gibt, wird mit einem Fehler abgelehnt."""
    await einrichten(hass, freezer, person("p1", "Vater"), raum("r1", "Schlafzimmer"))
    with pytest.raises(ServiceValidationError):
        await waehle_raum(hass, "p1", "Keller")


async def test_raum_entfernen_setzt_person_auf_kein_raum(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Wird der Raum entfernt, ist die Person wieder ohne Raum und inaktiv."""
    entry = await einrichten(
        hass, freezer, person("p1", "Vater"), raum("r1", "Schlafzimmer")
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    assert hass.config_entries.async_remove_subentry(entry, "r1")
    await hass.async_block_till_done()
    assert zustand(hass, "select", "p1", "raum") == "kein_raum"
    assert zustand(hass, "sensor", "p1", "status") == "inaktiv"


async def test_raum_nicht_mehr_zuordenbar(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Wird ein Raum nicht zuordenbar, fällt die Person auf „kein Raum“ (E11)."""
    entry = await einrichten(
        hass, freezer, person("p1", "Vater"), raum("r1", "Schlafzimmer")
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    sub = entry.subentries["r1"]
    hass.config_entries.async_update_subentry(
        entry, sub, data=MappingProxyType(dict(sub.data) | {"zuordenbar": False})
    )
    await hass.async_block_till_done()
    assert zustand(hass, "select", "p1", "raum") == "kein_raum"
    assert optionen(hass, "p1") == ["kein_raum"]
    assert zustand(hass, "sensor", "p1", "status") == "inaktiv"


async def test_personen_plan_bleibt_unberuehrt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Personen ohne Raum rechnen weiter wie in Phase 1."""
    await einrichten(hass, freezer, person("p1", "Vater", zeitplan=PLAN))
    assert zustand(hass, "sensor", "p1", "status") == "inaktiv"


async def test_raum_umbenennen_behaelt_zuordnung(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Umbenennen lädt neu; die Auswahl zeigt den neuen Namen, die Zuordnung bleibt."""
    entry = await einrichten(
        hass, freezer, person("p1", "Vater"), raum("r1", "Schlafzimmer")
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    hass.config_entries.async_update_subentry(
        entry, entry.subentries["r1"], title="OG Schlafzimmer"
    )
    await hass.async_block_till_done()
    assert zustand(hass, "select", "p1", "raum") == "OG Schlafzimmer"
    assert zustand(hass, "sensor", "p1", "status") == "werktag"


async def test_weckende_bleiben_nach_dem_wecken_stehen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Quelle und Weckende frieren mit der Weckzeit ein (E47)."""
    await einrichten(hass, freezer, person("p1", "Vater"), raum("r1", "Flur"))
    await waehle_raum(hass, "p1", "Flur")
    await vorspulen(hass, freezer, "2026-07-14T06:15:00+02:00")
    await waehle_raum(hass, "p1", "kein_raum")
    state = hass.states.get(entity_id(hass, "sensor", "r1", "weckzeit"))
    assert state is not None
    assert state.attributes["personen"] == []
    assert state.attributes["weckende"] == ["Vater"]
    assert state.attributes["quelle"] == "personen"
