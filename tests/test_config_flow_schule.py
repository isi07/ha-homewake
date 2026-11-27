"""Tests für die Schulauswahl im Personen-Dialog (ARCHITEKTUR.md 3.6, E40).

mehr-schulferien.de wird mit ``aioclient_mock`` nachgebaut. Die Kette:
Anbieter (mehr-schulferien.de) → Bundesland → Landkreis → Ort → Schule.
"""

from __future__ import annotations

from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigSubentryDataWithId, SubentryFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from custom_components.homewake.anbieter.mehr_schulferien import BASIS
from custom_components.homewake.const import SUBENTRY_PERSON
from tests.test_config_flow_person import LEERER_PLAN, STANDARD, haus, starte

SLUG = "60311-ludwig-boerne-schule"
NAME = "Ludwig-Börne-Schule (Lange Straße 30-36)"
PFAD = ["Deutschland", "Hessen", "Frankfurt am Main", "Frankfurt am Main"]
WAEHLEN = "Choose a school (provider and school follow after “OK” in the next steps)"
GESPEICHERT = {
    "anbieter": "mehr_schulferien",
    "kennung": SLUG,
    "name": NAME,
    "pfad": PFAD,
}


def liste(*eintraege: tuple[str, str], strasse: str | None = None) -> dict[str, Any]:
    """Antwort der API mit einer Liste von Orten oder Schulen."""
    daten = []
    for slug, name in eintraege:
        eintrag: dict[str, Any] = {"slug": slug, "name": name, "id": 1}
        if strasse is not None:
            eintrag["address"] = {"street": strasse, "city": "Frankfurt am Main"}
        daten.append(eintrag)
    return {"data": daten, "meta": {"api_version": "2.1"}}


def api(aioclient_mock: AiohttpClientMocker) -> None:
    """Die vier Listen der Kette für Frankfurt am Main."""
    aioclient_mock.get(
        f"{BASIS}/federal-states",
        json=liste(("hessen", "Hessen"), ("bayern", "Bayern")),
    )
    aioclient_mock.get(
        f"{BASIS}/counties?federal_state=hessen",
        json=liste(("frankfurt-am-main", "Frankfurt am Main")),
    )
    aioclient_mock.get(
        f"{BASIS}/cities?county=frankfurt-am-main",
        json=liste(("frankfurt-am-main", "Frankfurt am Main")),
    )
    aioclient_mock.get(
        f"{BASIS}/schools?city=frankfurt-am-main",
        json={
            "data": [
                {
                    "slug": SLUG,
                    "name": "Ludwig-Börne-Schule",
                    "address": {"street": "Lange Straße 30-36"},
                },
                {"slug": "60325-goethe-gymnasium", "name": "Goethe-Gymnasium"},
                {"name": "ohne Kennung"},
                "kaputt",
            ]
        },
    )


def optionen(result: SubentryFlowResult, feld: str) -> list[Any]:
    """Auswahl-Optionen eines Formularfelds."""
    schema = result["data_schema"]
    assert schema is not None
    for schluessel, selector in schema.schema.items():
        if schluessel == feld:
            return list(selector.config["options"])
    raise AssertionError(feld)


async def bis_zur_schule(
    hass: HomeAssistant, result: SubentryFlowResult
) -> SubentryFlowResult:
    """Anbieter, Bundesland, Landkreis und Ort wählen; liefert „schule“."""
    flow = result["flow_id"]
    assert result["step_id"] == "anbieter"
    assert optionen(result, "anbieter") == [
        {"value": "mehr_schulferien", "label": "mehr-schulferien.de"}
    ]
    result = await hass.config_entries.subentries.async_configure(
        flow, {"anbieter": "mehr_schulferien"}
    )
    assert result["step_id"] == "bundesland"
    assert optionen(result, "bundesland") == [
        {"value": "bayern", "label": "Bayern"},
        {"value": "hessen", "label": "Hessen"},
    ]
    result = await hass.config_entries.subentries.async_configure(
        flow, {"bundesland": "hessen"}
    )
    assert result["step_id"] == "kreis"
    result = await hass.config_entries.subentries.async_configure(
        flow, {"kreis": "frankfurt-am-main"}
    )
    assert result["step_id"] == "ort"
    result = await hass.config_entries.subentries.async_configure(
        flow, {"ort": "frankfurt-am-main"}
    )
    assert result["step_id"] == "schule"
    return result


async def test_schule_waehlen(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Neue Person mit Schule: vier Auswahlschritte, gespeichert Kennung und Name."""
    api(aioclient_mock)
    result = await starte(hass, haus(hass))
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"name": "Kind1", "standard": STANDARD, "schulferien": "waehlen"},
    )
    assert result["type"] is FlowResultType.FORM
    result = await bis_zur_schule(hass, result)
    assert optionen(result, "schule") == [
        {"value": "60325-goethe-gymnasium", "label": "Goethe-Gymnasium"},
        {"value": SLUG, "label": NAME},
    ]
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"schule": SLUG}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Kind1"
    assert result["data"] == {
        "zeitplan": LEERER_PLAN,
        "schule": GESPEICHERT,
    }


async def test_ohne_schule_kein_abruf(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Standard „keine Schule“: gleich gespeichert, nichts abgerufen."""
    result = await starte(hass, haus(hass))
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Vater", "standard": STANDARD}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert "schule" not in result["data"]
    assert aioclient_mock.call_count == 0


async def test_keine_verbindung_wiederholen_oder_ohne_schule(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Seite nicht erreichbar: Fehler, erneut versuchen, oder ohne Schule speichern."""
    aioclient_mock.get(f"{BASIS}/federal-states", exc=aiohttp.ClientError())
    result = await starte(hass, haus(hass))
    flow = result["flow_id"]
    result = await hass.config_entries.subentries.async_configure(
        flow, {"name": "Kind1", "standard": STANDARD, "schulferien": "waehlen"}
    )
    result = await hass.config_entries.subentries.async_configure(
        flow, {"anbieter": "mehr_schulferien"}
    )
    assert result["step_id"] == "bundesland"
    assert result["errors"] == {"base": "keine_verbindung"}
    assert result["description_placeholders"] == {"anbieter": "mehr-schulferien.de"}
    result = await hass.config_entries.subentries.async_configure(
        flow, {"ohne_schule": False}
    )
    assert result["errors"] == {"base": "keine_verbindung"}
    assert aioclient_mock.call_count == 2  # erneut versucht
    result = await hass.config_entries.subentries.async_configure(
        flow, {"ohne_schule": True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"zeitplan": LEERER_PLAN}


async def test_ort_ohne_schulen(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Ein Ort ohne Schulen: Hinweis statt leerer Liste."""
    api(aioclient_mock)
    aioclient_mock._mocks.pop()
    aioclient_mock.get(f"{BASIS}/schools?city=frankfurt-am-main", json={"data": []})
    result = await starte(hass, haus(hass))
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"name": "Kind1", "standard": STANDARD, "schulferien": "waehlen"},
    )
    result = await bis_zur_schule(hass, result)
    assert result["errors"] == {"base": "leer"}


def person_mit_schule(sid: str = "p1") -> ConfigSubentryDataWithId:
    """Bestehende Person mit Schule."""
    return ConfigSubentryDataWithId(
        data={"zeitplan": LEERER_PLAN, "schule": GESPEICHERT},
        subentry_type=SUBENTRY_PERSON,
        title="Kind1",
        unique_id=None,
        subentry_id=sid,
    )


async def aendern(hass: HomeAssistant, entry: MockConfigEntry) -> SubentryFlowResult:
    """Startet „Person ändern“ für p1."""
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_PERSON),
        context={"source": "reconfigure", "subentry_id": "p1"},
    )
    assert result["step_id"] == "reconfigure"
    return result


async def test_aendern_schule_behalten(hass: HomeAssistant) -> None:
    """Beim Ändern ist „Schule behalten“ vorgewählt; die Schule bleibt."""
    entry = haus(hass, person_mit_schule())
    result = await aendern(hass, entry)
    assert optionen(result, "schulferien") == [
        {
            "value": "behalten",
            "label": "Keep current school (mehr-schulferien.de): Deutschland → "
            f"Hessen → Frankfurt am Main → Frankfurt am Main → {NAME}",
        },
        {"value": "keine", "label": "No school"},
        {"value": "waehlen", "label": WAEHLEN},
    ]
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Kind1", "standard": STANDARD}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.subentries["p1"].data["schule"] == GESPEICHERT


async def test_aendern_schule_entfernen(hass: HomeAssistant) -> None:
    """„Keine Schule“ entfernt die Schule aus der Person."""
    entry = haus(hass, person_mit_schule())
    result = await aendern(hass, entry)
    await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"name": "Kind1", "standard": STANDARD, "schulferien": "keine"},
    )
    assert "schule" not in entry.subentries["p1"].data


async def test_aendern_neue_schule(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Beim Ändern eine andere Schule wählen."""
    api(aioclient_mock)
    entry = haus(hass, person_mit_schule())
    result = await aendern(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"name": "Kind1", "standard": STANDARD, "schulferien": "waehlen"},
    )
    result = await bis_zur_schule(hass, result)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"schule": "60325-goethe-gymnasium"}
    )
    assert result["reason"] == "reconfigure_successful"
    assert entry.subentries["p1"].data["schule"] == {
        "anbieter": "mehr_schulferien",
        "kennung": "60325-goethe-gymnasium",
        "name": "Goethe-Gymnasium",
        "pfad": PFAD,
    }


async def test_aendern_ohne_verbindung_behaelt_alte_schule(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Schulwahl beim Ändern abgebrochen: die bisherige Schule bleibt."""
    aioclient_mock.get(f"{BASIS}/federal-states", status=500)
    entry = haus(hass, person_mit_schule())
    result = await aendern(hass, entry)
    flow = result["flow_id"]
    await hass.config_entries.subentries.async_configure(
        flow, {"name": "Kind1", "standard": STANDARD, "schulferien": "waehlen"}
    )
    result = await hass.config_entries.subentries.async_configure(
        flow, {"anbieter": "mehr_schulferien"}
    )
    result = await hass.config_entries.subentries.async_configure(
        flow, {"ohne_schule": True}
    )
    assert result["reason"] == "reconfigure_successful"
    assert entry.subentries["p1"].data["schule"] == GESPEICHERT


async def test_aendern_ohne_schule_bietet_kein_behalten(hass: HomeAssistant) -> None:
    """Ohne bisherige Schule gibt es kein „behalten“."""
    entry = haus(
        hass,
        ConfigSubentryDataWithId(
            data={"zeitplan": LEERER_PLAN},
            subentry_type=SUBENTRY_PERSON,
            title="Kind1",
            unique_id=None,
            subentry_id="p1",
        ),
    )
    result = await aendern(hass, entry)
    assert optionen(result, "schulferien") == [
        {"value": "keine", "label": "No school"},
        {"value": "waehlen", "label": WAEHLEN},
    ]


async def test_neu_ohne_behalten(hass: HomeAssistant) -> None:
    """Beim Anlegen gibt es kein „behalten“; „wählen“ erklärt den nächsten Schritt."""
    result = await starte(hass, haus(hass))
    assert optionen(result, "schulferien") == [
        {"value": "keine", "label": "No school"},
        {"value": "waehlen", "label": WAEHLEN},
    ]


async def test_behalten_auf_deutsch(hass: HomeAssistant) -> None:
    """Die Beschriftung folgt der HA-Sprache."""
    hass.config.language = "de"
    result = await aendern(hass, haus(hass, person_mit_schule()))
    assert optionen(result, "schulferien")[0]["label"] == (
        "Bisherige Schule behalten (mehr-schulferien.de): Deutschland → Hessen → "
        f"Frankfurt am Main → Frankfurt am Main → {NAME}"
    )


async def test_behalten_unbekannter_anbieter(hass: HomeAssistant) -> None:
    """Ein nicht mehr bekannter Anbieter steht mit seinem Schlüssel da."""
    person = person_mit_schule()
    person["data"] = {
        "zeitplan": LEERER_PLAN,
        "schule": {**GESPEICHERT, "anbieter": "alter_dienst"},
    }
    result = await aendern(hass, haus(hass, person))
    assert "(alter_dienst)" in optionen(result, "schulferien")[0]["label"]
