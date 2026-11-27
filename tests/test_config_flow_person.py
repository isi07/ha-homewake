"""Tests für den Dialog „Person hinzufügen/ändern“ (Untereintrag, 3.6, 5.4)."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigSubentryDataWithId, SubentryFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.homewake.const import DOMAIN, SUBENTRY_PERSON

STANDARD = {"beginn": "08:00:00", "ende": "21:00:00"}
MONTAG = {"beginn": "06:15:00", "ende": "22:00:00"}
LEERER_PLAN = {
    "standard": STANDARD,
    "montag": {},
    "dienstag": {},
    "mittwoch": {},
    "donnerstag": {},
    "freitag": {},
    "samstag": {},
    "sonntag": {},
}


def haus(hass: HomeAssistant, *personen: ConfigSubentryDataWithId) -> MockConfigEntry:
    """HomeWake-Haupteintrag mit optionalen Personen."""
    entry = MockConfigEntry(domain=DOMAIN, title="HomeWake", subentries_data=personen)
    entry.add_to_hass(hass)
    return entry


def person(titel: str, zeitplan: dict[str, Any], sid: str) -> ConfigSubentryDataWithId:
    """Daten eines Personen-Untereintrags."""
    return ConfigSubentryDataWithId(
        data={"zeitplan": zeitplan},
        subentry_type=SUBENTRY_PERSON,
        title=titel,
        unique_id=None,
        subentry_id=sid,
    )


async def starte(hass: HomeAssistant, entry: MockConfigEntry) -> SubentryFlowResult:
    """Startet den Dialog „Person hinzufügen“."""
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_PERSON), context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def test_person_anlegen(hass: HomeAssistant) -> None:
    """Name und Zeitplan ergeben einen Untereintrag mit vollständigem Zeitplan."""
    entry = haus(hass)
    result = await starte(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"name": "Vater", "standard": STANDARD, "montag": MONTAG},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Vater"
    assert result["data"] == {"zeitplan": LEERER_PLAN | {"montag": MONTAG}}


async def test_wochentag_nur_mit_beginn_ist_ein_fehler(hass: HomeAssistant) -> None:
    """Nur Beginn ohne Ende an einem Wochentag zeigt einen Fehler am Abschnitt."""
    result = await starte(hass, haus(hass))
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"name": "Vater", "standard": STANDARD, "dienstag": {"beginn": "06:00:00"}},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"dienstag": "beide_oder_keiner"}


async def test_standard_ende_vor_beginn_ist_ein_fehler(hass: HomeAssistant) -> None:
    """Ein Standard-Ende vor dem Beginn zeigt einen Fehler am Abschnitt."""
    result = await starte(hass, haus(hass))
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"name": "Vater", "standard": {"beginn": "21:00:00", "ende": "08:00:00"}},
    )
    assert result["errors"] == {"standard": "ende_vor_beginn"}


async def test_doppelter_name_ist_ein_fehler(hass: HomeAssistant) -> None:
    """Eine Person mit demselben Namen gibt es schon: Fehler am Namen."""
    entry = haus(hass, person("Vater", LEERER_PLAN, "p1"))
    result = await starte(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "vater ", "standard": STANDARD}
    )
    assert result["errors"] == {"name": "name_vergeben"}


async def test_person_aendern(hass: HomeAssistant) -> None:
    """Im Ändern-Dialog lassen sich Name und Zeitplan anpassen."""
    entry = haus(hass, person("Vater", LEERER_PLAN, "p1"))
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_PERSON),
        context={"source": "reconfigure", "subentry_id": "p1"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"name": "Papa", "standard": STANDARD, "montag": MONTAG},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    sub = entry.subentries["p1"]
    assert sub.title == "Papa"
    assert sub.data == {"zeitplan": LEERER_PLAN | {"montag": MONTAG}}


async def test_aendern_mit_eigenem_namen_ist_kein_fehler(hass: HomeAssistant) -> None:
    """Beim Ändern darf die Person ihren bisherigen Namen behalten."""
    entry = haus(hass, person("Vater", LEERER_PLAN, "p1"))
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_PERSON),
        context={"source": "reconfigure", "subentry_id": "p1"},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Vater", "standard": STANDARD}
    )
    assert result["type"] is FlowResultType.ABORT


async def test_standard_leer_zeigt_eigene_meldung(hass: HomeAssistant) -> None:
    """Fehlt die Standard-Zeile, erscheint die verständliche eigene Meldung."""
    result = await starte(hass, haus(hass))
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Vater", "standard": {}}
    )
    assert result["errors"] == {"standard": "standard_pflicht"}


async def test_aendern_mit_fehler_zeigt_formular_erneut(hass: HomeAssistant) -> None:
    """Fehler im Ändern-Dialog: Formular erscheint erneut, nichts wird gespeichert."""
    entry = haus(
        hass, person("Vater", LEERER_PLAN, "p1"), person("Mutter", LEERER_PLAN, "p2")
    )
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_PERSON),
        context={"source": "reconfigure", "subentry_id": "p1"},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"name": "Mutter", "standard": STANDARD, "montag": {"ende": "22:00:00"}},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"name": "name_vergeben", "montag": "beide_oder_keiner"}
    assert entry.subentries["p1"].title == "Vater"


# ---------------------------------------------------------------- Urlaubskalender


async def test_person_mit_urlaubskalender_anlegen(hass: HomeAssistant) -> None:
    """Der optionale Urlaubskalender wird im Untereintrag gespeichert."""
    entry = haus(hass)
    result = await starte(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Vater",
            "urlaubskalender": "calendar.urlaub_vater",
            "standard": STANDARD,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "zeitplan": LEERER_PLAN,
        "urlaubskalender": "calendar.urlaub_vater",
    }


async def test_urlaubskalender_im_aendern_dialog(hass: HomeAssistant) -> None:
    """Ändern: Kalender ist vorbelegt; leer lassen entfernt ihn."""
    sub = person("Vater", LEERER_PLAN, "p1")
    sub["data"] = {"zeitplan": LEERER_PLAN, "urlaubskalender": "calendar.urlaub"}
    entry = haus(hass, sub)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_PERSON),
        context={"source": "reconfigure", "subentry_id": "p1"},
    )
    schema = result["data_schema"]
    assert schema is not None
    vorschlag = {
        str(k): k.description.get("suggested_value")
        for k in schema.schema
        if k.description
    }
    assert vorschlag["urlaubskalender"] == "calendar.urlaub"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Vater", "standard": STANDARD}
    )
    assert result["type"] is FlowResultType.ABORT
    assert entry.subentries["p1"].data == {"zeitplan": LEERER_PLAN}
