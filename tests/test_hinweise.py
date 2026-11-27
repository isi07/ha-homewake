"""Tests für die Reparatur-Hinweise „Raum verloren“ und „Zeitplan ungültig“ (5.5, E46).

Phase 8: Fällt eine Person auf „kein Raum“ zurück, weil ihr Raum gelöscht oder
nicht mehr zuordenbar ist, erscheint ein Hinweis pro Person (E11). Ein Raum mit
unlesbarem Standardplan nimmt seinen Personen den Raum dagegen nicht weg; er
selbst ist nicht verfügbar, und ein Hinweis bittet ums Neu-Speichern (E46).
"""

from __future__ import annotations

from datetime import timedelta
from types import MappingProxyType

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import async_fire_time_changed

from custom_components.homewake.const import DOMAIN
from tests.test_person_sensoren import einrichten, person, zustand
from tests.test_raum_sensoren import RAUM_PLAN, optionen, raum, waehle_raum


def hinweis(hass: HomeAssistant, issue_id: str) -> ir.IssueEntry | None:
    """Reparatur-Hinweis von HomeWake oder None."""
    return ir.async_get(hass).async_get_issue(DOMAIN, issue_id)


def daten_aendern(
    hass: HomeAssistant, entry: ConfigEntry, sid: str, **aenderungen: object
) -> None:
    """Daten eines Untereintrags ändern (wie der Konfigurieren-Dialog)."""
    sub = entry.subentries[sid]
    hass.config_entries.async_update_subentry(
        entry, sub, data=MappingProxyType(dict(sub.data) | aenderungen)
    )


async def entprellt(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Zweite Änderung kurz nach der ersten: HA rechnet erst nach der Pause neu."""
    freezer.tick(timedelta(seconds=15))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


# ------------------------------------------------------- Raum verloren (E11)


async def test_raum_geloescht_zeigt_hinweis_bis_wieder_ein_raum_gewaehlt_ist(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Raum gelöscht → Hinweis für die Person; neuer Raum → Hinweis weg."""
    entry = await einrichten(
        hass,
        freezer,
        person("p1", "Vater"),
        raum("r1", "Schlafzimmer"),
        raum("r2", "Gästezimmer"),
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    assert hinweis(hass, "raum_verloren_p1") is None
    assert hass.config_entries.async_remove_subentry(entry, "r1")
    await hass.async_block_till_done()
    issue = hinweis(hass, "raum_verloren_p1")
    assert issue is not None
    assert issue.translation_key == "raum_verloren"
    assert issue.translation_placeholders == {"person": "Vater"}
    assert issue.config_entry_id == entry.entry_id
    assert issue.severity is ir.IssueSeverity.WARNING
    assert not issue.is_fixable
    await waehle_raum(hass, "p1", "Gästezimmer")
    assert hinweis(hass, "raum_verloren_p1") is None


async def test_raum_nicht_mehr_zuordenbar_zeigt_hinweis(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Wird der Raum „nicht zuordenbar“, erscheint der Hinweis ebenfalls."""
    entry = await einrichten(
        hass, freezer, person("p1", "Vater"), raum("r1", "Schlafzimmer")
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    daten_aendern(hass, entry, "r1", zuordenbar=False)
    await hass.async_block_till_done()
    assert hinweis(hass, "raum_verloren_p1") is not None
    daten_aendern(hass, entry, "r1", zuordenbar=True)
    await entprellt(hass, freezer)
    await waehle_raum(hass, "p1", "Schlafzimmer")
    assert hinweis(hass, "raum_verloren_p1") is None


async def test_person_ohne_raum_bekommt_keinen_hinweis(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Wer nie einen Raum hatte, bekommt keinen Hinweis."""
    await einrichten(hass, freezer, person("p1", "Vater"), raum("r1", "Flur"))
    assert hinweis(hass, "raum_verloren_p1") is None


async def test_hinweis_uebersteht_neuladen_und_verschwindet_danach(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Nach einem Neuladen bleibt der Hinweis und verschwindet mit neuem Raum."""
    entry = await einrichten(
        hass,
        freezer,
        person("p1", "Vater"),
        raum("r1", "Schlafzimmer"),
        raum("r2", "Gästezimmer"),
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    assert hass.config_entries.async_remove_subentry(entry, "r1")
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hinweis(hass, "raum_verloren_p1") is not None
    await waehle_raum(hass, "p1", "Gästezimmer")
    assert hinweis(hass, "raum_verloren_p1") is None


async def test_person_geloescht_entfernt_ihren_hinweis(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Wird die Person gelöscht, verschwindet ihr Hinweis."""
    entry = await einrichten(
        hass,
        freezer,
        person("p1", "Vater"),
        person("p2", "Mutter"),
        raum("r1", "Schlafzimmer"),
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    assert hass.config_entries.async_remove_subentry(entry, "r1")
    await hass.async_block_till_done()
    assert hinweis(hass, "raum_verloren_p1") is not None
    assert hass.config_entries.async_remove_subentry(entry, "p1")
    await hass.async_block_till_done()
    assert hinweis(hass, "raum_verloren_p1") is None


async def test_alter_hinweis_einer_person_mit_raum_wird_beim_start_entfernt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Steht noch ein Hinweis von früher, obwohl die Person einen Raum hat: weg."""
    entry = await einrichten(
        hass, freezer, person("p1", "Vater"), raum("r1", "Schlafzimmer")
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    ir.async_create_issue(
        hass,
        DOMAIN,
        "raum_verloren_p1",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="raum_verloren",
        translation_placeholders={"person": "Vater"},
    )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hinweis(hass, "raum_verloren_p1") is None


# --------------------------------------------------- Zeitplan ungültig (E46)


async def test_raum_mit_ungueltigem_plan_behaelt_seine_personen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Kaputter Raum-Plan: Person behält Raum und bleibt aktiv, Raum nicht verfügbar."""
    entry = await einrichten(
        hass, freezer, person("p1", "Vater"), raum("r1", "Schlafzimmer")
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    daten_aendern(hass, entry, "r1", zeitplan={})
    await hass.async_block_till_done()
    assert zustand(hass, "select", "p1", "raum") == "Schlafzimmer"
    assert optionen(hass, "p1") == ["kein_raum", "Schlafzimmer"]
    assert zustand(hass, "sensor", "p1", "status") == "werktag"
    assert zustand(hass, "sensor", "r1", "weckzeit") == STATE_UNAVAILABLE
    assert hinweis(hass, "raum_verloren_p1") is None
    issue = hinweis(hass, "zeitplan_ungueltig_r1")
    assert issue is not None
    assert issue.translation_key == "zeitplan_ungueltig_raum"
    assert issue.translation_placeholders == {"name": "Schlafzimmer"}
    assert issue.config_entry_id == entry.entry_id
    # Repariert: Hinweis weg, Raum rechnet wieder
    daten_aendern(hass, entry, "r1", zeitplan=RAUM_PLAN)
    await entprellt(hass, freezer)
    assert hinweis(hass, "zeitplan_ungueltig_r1") is None
    assert zustand(hass, "sensor", "r1", "weckzeit") != STATE_UNAVAILABLE


async def test_nicht_zuordenbarer_raum_mit_ungueltigem_plan_nimmt_den_raum(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ist der kaputte Raum zugleich nicht zuordenbar, gilt E11 wie bisher."""
    entry = await einrichten(
        hass, freezer, person("p1", "Vater"), raum("r1", "Schlafzimmer")
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    daten_aendern(hass, entry, "r1", zeitplan={}, zuordenbar=False)
    await hass.async_block_till_done()
    assert zustand(hass, "select", "p1", "raum") == "kein_raum"
    assert hinweis(hass, "raum_verloren_p1") is not None


async def test_person_mit_ungueltigem_plan_zeigt_hinweis(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Kaputter Personen-Plan: Hinweis pro Person, verschwindet nach dem Löschen."""
    entry = await einrichten(
        hass, freezer, person("p1", "Kaputt", zeitplan={}), person("p2", "Mutter")
    )
    issue = hinweis(hass, "zeitplan_ungueltig_p1")
    assert issue is not None
    assert issue.translation_key == "zeitplan_ungueltig_person"
    assert issue.translation_placeholders == {"name": "Kaputt"}
    assert hinweis(hass, "zeitplan_ungueltig_p2") is None
    assert hass.config_entries.async_remove_subentry(entry, "p1")
    await hass.async_block_till_done()
    assert hinweis(hass, "zeitplan_ungueltig_p1") is None


async def test_alter_zeitplan_hinweis_wird_beim_start_entfernt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ein Hinweis von früher verschwindet, wenn der Plan beim Start gültig ist."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        "zeitplan_ungueltig_p1",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="zeitplan_ungueltig_person",
        translation_placeholders={"name": "Vater"},
    )
    await einrichten(hass, freezer, person("p1", "Vater"))
    assert hinweis(hass, "zeitplan_ungueltig_p1") is None


async def test_bewusst_kein_raum_gewaehlt_entfernt_den_hinweis(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Wählt der Nutzer ausdrücklich „kein Raum“, ist der Hinweis erledigt."""
    entry = await einrichten(
        hass, freezer, person("p1", "Vater"), raum("r1", "Schlafzimmer")
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    assert hass.config_entries.async_remove_subentry(entry, "r1")
    await hass.async_block_till_done()
    assert hinweis(hass, "raum_verloren_p1") is not None
    await waehle_raum(hass, "p1", "kein_raum")
    assert hinweis(hass, "raum_verloren_p1") is None


async def test_kaputter_zeitplan_hinweis_bleibt_ueber_neuladen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Bleibt der Plan kaputt, bleibt derselbe Hinweis (ein Ignorieren hält)."""
    entry = await einrichten(hass, freezer, person("p1", "Kaputt", zeitplan={}))
    ir.async_get(hass).async_ignore(DOMAIN, "zeitplan_ungueltig_p1", ignore=True)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    issue = hinweis(hass, "zeitplan_ungueltig_p1")
    assert issue is not None
    assert issue.dismissed_version is not None


async def test_zeitplan_hinweis_eines_geloeschten_untereintrags_wird_entfernt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ein Hinweis zu einem Untereintrag, den es nicht mehr gibt, verschwindet."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        "zeitplan_ungueltig_weg",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="zeitplan_ungueltig_raum",
        translation_placeholders={"name": "Keller"},
    )
    await einrichten(hass, freezer, person("p1", "Vater"))
    assert hinweis(hass, "zeitplan_ungueltig_weg") is None
