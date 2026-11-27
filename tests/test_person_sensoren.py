"""Tests für Coordinator, Speicher, Timer und Personen-Sensoren (ARCHITEKTUR.md 5)."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any
from unittest.mock import patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigSubentry, ConfigSubentryDataWithId
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.homewake.const import DOMAIN, SUBENTRY_PERSON
from custom_components.homewake.coordinator import HomeWakeCoordinator

PLAN = {
    "standard": {"beginn": "08:00:00", "ende": "21:00:00"},
    **{
        tag: {"beginn": "06:15:00", "ende": "22:00:00"}
        for tag in ("montag", "dienstag", "mittwoch", "donnerstag", "freitag")
    },
    "samstag": {},
    "sonntag": {},
}
SCHLUESSEL = {
    "sensor": ("naechster_wecker", "naechstes_tagesende", "status"),
    "binary_sensor": ("wach",),
}


def person(sid: str, titel: str, zeitplan: Any = None) -> ConfigSubentryDataWithId:
    """Personen-Untereintrag mit Werktagsplan 06:15-22:00."""
    return ConfigSubentryDataWithId(
        data={"zeitplan": PLAN if zeitplan is None else zeitplan},
        subentry_type=SUBENTRY_PERSON,
        title=titel,
        unique_id=None,
        subentry_id=sid,
    )


async def einrichten(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    *personen: ConfigSubentryDataWithId,
    jetzt: str = "2026-07-14 04:00:00+02:00",  # Dienstag
) -> MockConfigEntry:
    """Richtet HomeWake mit Personen in Berliner Zeit ein."""
    await hass.config.async_set_time_zone("Europe/Berlin")
    hass.config.latitude, hass.config.longitude = 50.1106, 8.6821  # Frankfurt am Main
    freezer.move_to(jetzt)
    entry = MockConfigEntry(domain=DOMAIN, title="HomeWake", subentries_data=personen)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def entity_id(hass: HomeAssistant, domain: str, sid: str, schluessel: str) -> str:
    """Entity-ID über die unique_id (unabhängig von Sprache und Namen)."""
    eid = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{sid}_{schluessel}")
    assert eid is not None
    return eid


def zustand(hass: HomeAssistant, domain: str, sid: str, schluessel: str) -> str:
    """Aktueller Zustand einer HomeWake-Entity."""
    state = hass.states.get(entity_id(hass, domain, sid, schluessel))
    assert state is not None
    return state.state


async def vorspulen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, zeitpunkt: str
) -> None:
    """Zeit vorspulen und fällige Timer auslösen."""
    freezer.move_to(zeitpunkt)
    async_fire_time_changed(hass, datetime.fromisoformat(zeitpunkt))
    await hass.async_block_till_done()


# ---------------------------------------------------------------- Einrichten


async def test_setup_legt_entities_am_geraet_der_person_an(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Pro Person entstehen ein Gerät und vier Entities mit fester unique_id."""
    entry = await einrichten(hass, freezer, person("p1", "Vater"))
    geraet = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, "p1"), entry.entry_id
    )
    assert geraet is not None
    assert geraet.name == "Vater"
    ent_reg = er.async_get(hass)
    for domain, schluessel_liste in SCHLUESSEL.items():
        for schluessel in schluessel_liste:
            eintrag = ent_reg.async_get(entity_id(hass, domain, "p1", schluessel))
            assert eintrag is not None
            assert eintrag.device_id == geraet.id
            assert eintrag.config_subentry_id == "p1"
            assert eintrag.translation_key == schluessel
    assert entry.runtime_data is not None


async def test_werte_vor_dem_wecken(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Um 04:00: Wecker heute 06:15, Tagesende 22:00, inaktiv (noch kein Raum)."""
    await einrichten(hass, freezer, person("p1", "Vater"))
    assert (
        zustand(hass, "sensor", "p1", "naechster_wecker") == "2026-07-14T04:15:00+00:00"
    )
    assert (
        zustand(hass, "sensor", "p1", "naechstes_tagesende")
        == "2026-07-14T20:00:00+00:00"
    )
    assert zustand(hass, "sensor", "p1", "status") == "inaktiv"
    assert zustand(hass, "binary_sensor", "p1", "wach") == STATE_OFF


async def test_status_attribute(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Der Status-Sensor trägt Grund, Kandidat und Tagesbeginn/-ende heute/morgen."""
    await einrichten(hass, freezer, person("p1", "Vater"))
    state = hass.states.get(entity_id(hass, "sensor", "p1", "status"))
    assert state is not None
    attrs = state.attributes
    assert attrs["grund"] == "kein_raum"
    assert attrs["kandidat"] == "heute"
    assert attrs["tagesbeginn_heute"] == datetime.fromisoformat(
        "2026-07-14T06:15:00+02:00"
    )
    assert attrs["tagesende_morgen"] == datetime.fromisoformat(
        "2026-07-15T22:00:00+02:00"
    )


# ---------------------------------------------------------------- Zeitplaner


async def test_wecken_zur_weckzeit(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Zur Weckzeit schaltet „Wach“ ein und der Wecker springt auf morgen."""
    await einrichten(hass, freezer, person("p1", "Vater"))
    await vorspulen(hass, freezer, "2026-07-14T06:15:00+02:00")
    assert zustand(hass, "binary_sensor", "p1", "wach") == STATE_ON
    assert (
        zustand(hass, "sensor", "p1", "naechster_wecker") == "2026-07-15T04:15:00+00:00"
    )


async def test_zustand_uebersteht_neuladen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Nach dem Wecken bleibt „Wach“ auch nach Neuladen erhalten (Speicher, E32)."""
    entry = await einrichten(hass, freezer, person("p1", "Vater"))
    await vorspulen(hass, freezer, "2026-07-14T06:15:00+02:00")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert zustand(hass, "binary_sensor", "p1", "wach") == STATE_ON
    assert (
        zustand(hass, "sensor", "p1", "naechster_wecker") == "2026-07-15T04:15:00+00:00"
    )


async def test_wecken_wird_ohne_verzoegerung_gespeichert(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    """Nach dem Wecken steht „geweckt“ gleich im Speicher, ohne Entladen (E32).

    Die Uhr wird danach nur um 0,1 s weitergestellt: Ein verzögertes
    Speichern (1 s) wäre also noch nicht geschrieben.
    """
    entry = await einrichten(hass, freezer, person("p1", "Vater"))
    await vorspulen(hass, freezer, "2026-07-14T06:15:00+02:00")
    freezer.tick(timedelta(seconds=0.1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    gespeichert = hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]["personen"]["p1"]
    assert gespeichert["zustand"]["wach"] is True


async def test_sicherheitslauf_holt_verpassten_timer_nach(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Fällt der genaue Timer aus, rechnet der Sicherheitslauf um :19 nach (E29)."""
    entry = await einrichten(hass, freezer, person("p1", "Vater"))
    # bis 06:09 laufen fällige Sicherheitsläufe, danach fällt der Timer aus
    await vorspulen(hass, freezer, "2026-07-14T06:09:00+02:00")
    entry.runtime_data.timer_abmelden()
    await vorspulen(hass, freezer, "2026-07-14T06:16:00+02:00")
    assert zustand(hass, "binary_sensor", "p1", "wach") == STATE_OFF
    await vorspulen(hass, freezer, "2026-07-14T06:19:00+02:00")
    assert zustand(hass, "binary_sensor", "p1", "wach") == STATE_ON


# ---------------------------------------------------------------- Änderungen


async def test_geaenderter_zeitplan_wirkt_sofort(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ein geänderter Zeitplan wird ohne Neustart übernommen."""
    entry = await einrichten(hass, freezer, person("p1", "Vater"))
    neu = PLAN | {"dienstag": {"beginn": "05:30:00", "ende": "22:00:00"}}
    hass.config_entries.async_update_subentry(
        entry, entry.subentries["p1"], data={"zeitplan": neu}
    )
    await hass.async_block_till_done()
    assert (
        zustand(hass, "sensor", "p1", "naechster_wecker") == "2026-07-14T03:30:00+00:00"
    )


async def test_entfernen_einer_person_raeumt_auf(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    """Person entfernen: Gerät, Entities und Speicher-Eintrag verschwinden (5.4)."""
    entry = await einrichten(
        hass, freezer, person("p1", "Vater"), person("p2", "Mutter")
    )
    await vorspulen(hass, freezer, "2026-07-14T06:15:00+02:00")  # speichert sofort
    assert hass.config_entries.async_remove_subentry(entry, "p1")
    await hass.async_block_till_done()
    await vorspulen(hass, freezer, "2026-07-14T06:16:00+02:00")

    ent_reg = er.async_get(hass)
    assert er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    assert all(
        e.config_subentry_id == "p2"
        for e in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    )
    assert (
        dr.async_get(hass).async_get_device_by_identifier(
            (DOMAIN, "p1"), entry.entry_id
        )
        is None
    )
    await hass.async_block_till_done()
    gespeichert = hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]["personen"]
    assert "p1" not in gespeichert
    assert "p2" in gespeichert


async def test_neue_person_bekommt_entities(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Eine neu hinzugefügte Person bekommt Gerät und Entities (Neuladen, 5.4)."""
    entry = await einrichten(hass, freezer, person("p1", "Vater"))
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data=MappingProxyType({"zeitplan": PLAN}),
            subentry_type=SUBENTRY_PERSON,
            title="Mutter",
            unique_id=None,
            subentry_id="p2",
        ),
    )
    await hass.async_block_till_done()
    assert (
        zustand(hass, "sensor", "p2", "naechster_wecker") == "2026-07-14T04:15:00+00:00"
    )


@pytest.mark.parametrize(
    "kaputt", [{}, {"standard": {}}], ids=["leer", "ohne_standard"]
)
async def test_ungueltiger_zeitplan_macht_die_person_nicht_verfuegbar(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kaputt: dict[str, Any]
) -> None:
    """Ein kaputter Zeitplan legt nicht alles lahm; die Person ist nicht verfügbar."""
    await einrichten(
        hass, freezer, person("p1", "Kaputt", zeitplan=kaputt), person("p2", "Mutter")
    )
    assert zustand(hass, "sensor", "p1", "naechster_wecker") == STATE_UNAVAILABLE
    assert (
        zustand(hass, "sensor", "p2", "naechster_wecker") == "2026-07-14T04:15:00+00:00"
    )


# ---------------------------------------------------------------- Entladen, Fehler


async def test_nach_dem_entladen_laeuft_nichts_mehr(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    """Nach dem Entladen feuern weder Timer noch Sicherheitslauf; Speicher aktuell."""
    entry = await einrichten(hass, freezer, person("p1", "Vater"))
    await vorspulen(hass, freezer, "2026-07-14T06:15:00+02:00")
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    eid = entity_id(hass, "binary_sensor", "p1", "wach")
    with patch.object(HomeWakeCoordinator, "_async_update_data") as lauf:
        await vorspulen(hass, freezer, "2026-07-14T06:19:00+02:00")
        await vorspulen(hass, freezer, "2026-07-14T22:00:00+02:00")
    lauf.assert_not_called()
    state = hass.states.get(eid)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE
    gespeichert = hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]["personen"]["p1"]
    assert gespeichert["zustand"]["wach"] is True


async def test_fehler_im_lauf_macht_entities_unverfuegbar_und_heilt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ein Fehler im Lauf → nicht verfügbar; der nächste Lauf bringt alles zurück."""
    entry = await einrichten(hass, freezer, person("p1", "Vater"))
    with patch(
        "custom_components.homewake.coordinator.berechne_haus",
        side_effect=RuntimeError("kaputt"),
    ):
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert zustand(hass, "binary_sensor", "p1", "wach") == STATE_UNAVAILABLE
    await vorspulen(hass, freezer, "2026-07-14T04:09:00+02:00")  # Sicherheitslauf
    assert zustand(hass, "binary_sensor", "p1", "wach") == STATE_OFF


async def test_zeitzone_geaendert_rechnet_neu(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ändert sich die HA-Zeitzone, wird neu gerechnet."""
    await einrichten(hass, freezer, person("p1", "Vater"))
    await hass.config.async_update(time_zone="Europe/London")
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=11))  # Entprellung abwarten
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    # 06:15 Londoner Zeit = 05:15 UTC
    assert (
        zustand(hass, "sensor", "p1", "naechster_wecker") == "2026-07-14T05:15:00+00:00"
    )


async def test_umbenennen_aendert_den_geraetenamen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Umbenennen lädt neu und ändert den Gerätenamen (5.4)."""
    entry = await einrichten(hass, freezer, person("p1", "Vater"))
    hass.config_entries.async_update_subentry(
        entry, entry.subentries["p1"], title="Papa"
    )
    await hass.async_block_till_done()
    geraet = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, "p1"), entry.entry_id
    )
    assert geraet is not None
    assert geraet.name == "Papa"
    assert (
        zustand(hass, "sensor", "p1", "naechster_wecker") == "2026-07-14T04:15:00+00:00"
    )


async def test_loeschen_entfernt_den_speicher(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    """Wird HomeWake gelöscht, verschwindet auch seine Speicherdatei (Entfernen)."""
    entry = await einrichten(hass, freezer, person("p1", "Vater"))
    await vorspulen(hass, freezer, "2026-07-14T06:15:00+02:00")
    await hass.async_block_till_done()
    assert f"{DOMAIN}.{entry.entry_id}" in hass_storage
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert f"{DOMAIN}.{entry.entry_id}" not in hass_storage
