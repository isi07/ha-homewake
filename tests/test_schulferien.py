"""Tests für die Schulferien pro Person (ARCHITEKTUR.md 3.6, 5.5, E40-E42).

mehr-schulferien.de wird mit ``aioclient_mock`` nachgebaut (keine echte
Verbindung). Der Abruf läuft als Hintergrund-Aufgabe; darum warten die Tests mit
``wait_background_tasks=True``.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from unittest.mock import patch

import aiohttp
import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigSubentryDataWithId
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from custom_components.homewake.anbieter.mehr_schulferien import BASIS
from custom_components.homewake.const import DOMAIN, SUBENTRY_PERSON
from custom_components.homewake.coordinator import schul_hinweis_id
from custom_components.homewake.sensor import StatusSensor
from tests.test_person_sensoren import PLAN, einrichten, entity_id, zustand
from tests.test_raum_sensoren import raum, waehle_raum

SLUG = "60311-ludwig-boerne-schule"
SCHULE = {
    "anbieter": "mehr_schulferien",
    "kennung": SLUG,
    "name": "Ludwig-Börne-Schule",
    "pfad": ["Deutschland", "Hessen", "Frankfurt am Main", "Frankfurt am Main"],
}
SCHLUESSEL = f"mehr_schulferien:{SLUG}"
URL = f"{BASIS}/schools/{SLUG}/periods"
# Mittwoch, Weihnachtsferien ab heute; Werktag 06:15, Standard 08:00 (= 07:00 UTC)
JETZT = "2026-12-23 04:00:00+01:00"
WERKTAG_WECKER = "2026-12-23T05:15:00+00:00"
STANDARD_WECKER = "2026-12-23T07:00:00+00:00"

ANTWORT: dict[str, Any] = {
    "data": [
        {
            "id": 4647,
            "name": "1. Weihnachtstag",
            "type": "public_holiday",
            "starts_on": "2026-12-25",
            "ends_on": "2026-12-25",
            "is_public_holiday": True,
            "is_school_vacation": False,
        },
        {
            "id": 5145,
            "name": "Weihnachten",
            "type": "school_vacation",
            "starts_on": "2026-12-23",
            "ends_on": "2027-01-12",
            "is_public_holiday": False,
            "is_school_vacation": True,
        },
    ],
    "meta": {"api_version": "2.1"},
}


def person_mit_schule(
    sid: str, titel: str, schule: dict[str, Any] | None = SCHULE
) -> ConfigSubentryDataWithId:
    """Personen-Untereintrag mit Werktagsplan und Schule."""
    daten: dict[str, Any] = {"zeitplan": PLAN}
    if schule is not None:
        daten["schule"] = schule
    return ConfigSubentryDataWithId(
        data=daten,
        subentry_type=SUBENTRY_PERSON,
        title=titel,
        unique_id=None,
        subentry_id=sid,
    )


async def haus(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    *personen: ConfigSubentryDataWithId,
    jetzt: str = JETZT,
) -> MockConfigEntry:
    """HomeWake mit Personen im Schlafzimmer; wartet auf den Abruf."""
    entry = await einrichten(
        hass, freezer, *personen, raum("r1", "Schlafzimmer"), jetzt=jetzt
    )
    for person in personen:
        await waehle_raum(hass, person["subentry_id"], "Schlafzimmer")
    await hass.async_block_till_done(wait_background_tasks=True)
    return entry


async def vorspulen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, zeitpunkt: str
) -> None:
    """Zeit vorspulen, Timer auslösen und auf Hintergrund-Aufgaben warten."""
    freezer.move_to(zeitpunkt)
    async_fire_time_changed(hass, datetime.fromisoformat(zeitpunkt))
    await hass.async_block_till_done(wait_background_tasks=True)


def grund(hass: HomeAssistant, sid: str = "p1") -> Any:
    """Attribut „grund“ des Status-Sensors."""
    state = hass.states.get(entity_id(hass, "sensor", sid, "status"))
    assert state is not None
    return state.attributes.get("grund")


def hinweis(hass: HomeAssistant, schluessel: str = SCHLUESSEL) -> ir.IssueEntry | None:
    """Reparatur-Hinweis „Schulferien-Daten veraltet“ einer Schule (E42)."""
    return ir.async_get(hass).async_get_issue(DOMAIN, schul_hinweis_id(schluessel))


def abrufe(aioclient_mock: AiohttpClientMocker) -> list[Any]:
    """Alle Abfragen der Ferien (Methode, URL, Daten, Header)."""
    return [c for c in aioclient_mock.mock_calls if str(c[1]).startswith(URL)]


def antwort_setzen(aioclient_mock: AiohttpClientMocker, **kwargs: Any) -> None:
    """Antwort für die Ferien-Abfrage ersetzen (Aufrufliste bleibt erhalten)."""
    aioclient_mock._mocks.clear()
    aioclient_mock.get(URL, **kwargs)


# ---------------------------------------------------------------- Wirkung


async def test_schulferien_heute(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Ferientag: Status „schulferien“ mit Namen, Wecker zur Standard-Zeile."""
    aioclient_mock.get(URL, json=ANTWORT)
    await haus(hass, freezer, person_mit_schule("p1", "Kind1"))
    assert zustand(hass, "sensor", "p1", "status") == "schulferien"
    assert grund(hass) == "Weihnachten"
    assert zustand(hass, "sensor", "p1", "naechster_wecker") == STANDARD_WECKER


async def test_abfrage_ein_jahr_ab_heute(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Abgefragt wird heute bis heute + 365 Tage (E41)."""
    aioclient_mock.get(URL, json=ANTWORT)
    await haus(hass, freezer, person_mit_schule("p1", "Kind1"))
    (aufruf,) = abrufe(aioclient_mock)
    assert aufruf[1].query == {"start_date": "2026-12-23", "end_date": "2027-12-23"}


async def test_ohne_schule_kein_abruf(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Ohne Schule gelten keine Schulferien, es wird nichts abgerufen."""
    aioclient_mock.get(URL, json=ANTWORT)
    await haus(hass, freezer, person_mit_schule("p1", "Vater", schule=None))
    assert zustand(hass, "sensor", "p1", "status") == "werktag"
    assert zustand(hass, "sensor", "p1", "naechster_wecker") == WERKTAG_WECKER
    assert aioclient_mock.call_count == 0


async def test_nur_eigene_schule(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Schulferien gelten nur für Personen mit dieser Schule."""
    aioclient_mock.get(URL, json=ANTWORT)
    await haus(
        hass,
        freezer,
        person_mit_schule("p1", "Kind1"),
        person_mit_schule("p2", "Vater", schule=None),
    )
    assert zustand(hass, "sensor", "p1", "status") == "schulferien"
    assert zustand(hass, "sensor", "p2", "status") == "werktag"


async def test_gleiche_schule_ein_abruf(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Zwei Kinder auf derselben Schule: ein Abruf für beide (E41)."""
    aioclient_mock.get(URL, json=ANTWORT)
    await haus(
        hass,
        freezer,
        person_mit_schule("p1", "Kind1"),
        person_mit_schule("p2", "Kind2"),
    )
    assert len(abrufe(aioclient_mock)) == 1
    assert zustand(hass, "sensor", "p2", "status") == "schulferien"


async def test_schulferien_ab_morgen(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Nach dem Tagesende zählt morgen: erster Ferientag → Standard-Zeile morgen."""
    aioclient_mock.get(URL, json=ANTWORT)
    await haus(
        hass,
        freezer,
        person_mit_schule("p1", "Kind1"),
        jetzt="2026-12-22 22:30:00+01:00",
    )
    assert zustand(hass, "sensor", "p1", "status") == "schulferien"
    assert zustand(hass, "sensor", "p1", "naechster_wecker") == STANDARD_WECKER


# ---------------------------------------------------------------- Abruf-Takt


async def test_taeglicher_abruf(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Innerhalb von 24 h kein zweiter Abruf, danach einer (E41)."""
    aioclient_mock.get(URL, json=ANTWORT)
    await haus(hass, freezer, person_mit_schule("p1", "Kind1"))
    await vorspulen(hass, freezer, "2026-12-24 03:59:00+01:00")
    assert len(abrufe(aioclient_mock)) == 1
    await vorspulen(hass, freezer, "2026-12-24 04:09:00+01:00")
    assert len(abrufe(aioclient_mock)) == 2


async def test_neue_schule_wird_sofort_abgerufen(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Bekommt eine Person eine Schule, wird gleich abgerufen (nur neu rechnen)."""
    aioclient_mock.get(URL, json=ANTWORT)
    entry = await haus(hass, freezer, person_mit_schule("p1", "Kind1", schule=None))
    assert zustand(hass, "sensor", "p1", "status") == "werktag"
    sub = entry.subentries["p1"]
    hass.config_entries.async_update_subentry(
        entry, sub, data={**sub.data, "schule": SCHULE}
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert zustand(hass, "sensor", "p1", "status") == "schulferien"


# ---------------------------------------------------------------- Ausfall


@pytest.mark.parametrize(
    "fehler",
    [
        {"exc": aiohttp.ClientError()},
        {"exc": TimeoutError()},
        {"status": 500},
        {"status": 404, "json": {"errors": []}},
        {"text": "kein json"},
        {"json": {"meta": {}}},
    ],
    ids=["verbindung", "timeout", "server", "nicht_gefunden", "kein_json", "ohne_data"],
)
async def test_erster_start_ohne_netz(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
    fehler: dict[str, Any],
) -> None:
    """Ohne gespeicherte Daten und ohne Abruf: keine Schulferien (E41)."""
    aioclient_mock.get(URL, **fehler)
    await haus(hass, freezer, person_mit_schule("p1", "Kind1"))
    assert zustand(hass, "sensor", "p1", "status") == "werktag"
    assert zustand(hass, "sensor", "p1", "naechster_wecker") == WERKTAG_WECKER
    assert hinweis(hass) is None  # erst nach 30 Minuten


async def test_ohne_daten_hinweis_nach_30_minuten_und_erholung(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Hinweis nach 30 min ohne Daten; neuer Versuch erst nach 1 h; dann weg (E42)."""
    aioclient_mock.get(URL, exc=aiohttp.ClientError())
    await haus(hass, freezer, person_mit_schule("p1", "Kind1"))
    assert caplog.text.count("nicht abrufbar") == 1
    await vorspulen(hass, freezer, "2026-12-23 04:29:00+01:00")
    assert hinweis(hass) is None
    await vorspulen(hass, freezer, "2026-12-23 04:39:00+01:00")
    eintrag = hinweis(hass)
    assert eintrag is not None
    assert eintrag.severity is ir.IssueSeverity.WARNING
    assert eintrag.translation_placeholders == {
        "schule": "Ludwig-Börne-Schule",
        "anbieter": "mehr-schulferien.de",
    }
    assert len(abrufe(aioclient_mock)) == 1  # noch keine Stunde vorbei
    assert caplog.text.count("nicht abrufbar") == 1  # Warnung nur beim Wechsel

    antwort_setzen(aioclient_mock, json=ANTWORT)
    await vorspulen(hass, freezer, "2026-12-23 05:09:00+01:00")
    assert len(abrufe(aioclient_mock)) == 2
    assert hinweis(hass) is None
    assert zustand(hass, "sensor", "p1", "status") == "schulferien"
    assert "wieder abrufbar" in caplog.text


async def test_ausfall_nutzt_gespeicherte_daten_nach_neustart(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
    hass_storage: dict[str, Any],
) -> None:
    """Gespeicherte Ferien gelten über einen Neustart weiter, auch ohne Netz."""
    aioclient_mock.get(URL, json=ANTWORT)
    entry = await haus(hass, freezer, person_mit_schule("p1", "Kind1"))
    gespeichert = hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]
    assert gespeichert["schulferien"][SCHLUESSEL]["ferien"] == [
        ["2026-12-23", "2027-01-12", "Weihnachten"]
    ]

    antwort_setzen(aioclient_mock, exc=aiohttp.ClientError())
    freezer.move_to("2026-12-28 04:00:00+01:00")  # Montag, Daten 5 Tage alt
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(abrufe(aioclient_mock)) == 2
    assert zustand(hass, "sensor", "p1", "status") == "schulferien"
    assert hinweis(hass) is not None  # älter als 3 Tage und Abruf scheitert


async def test_hinweis_nach_drei_tagen(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Mit Daten erst ein Hinweis, wenn 3 Tage kein Abruf geklappt hat (E42)."""
    aioclient_mock.get(URL, json=ANTWORT)
    await haus(hass, freezer, person_mit_schule("p1", "Kind1"))
    antwort_setzen(aioclient_mock, status=503)
    await vorspulen(hass, freezer, "2026-12-24 04:09:00+01:00")  # 1. Fehlschlag
    assert hinweis(hass) is None
    assert zustand(hass, "sensor", "p1", "status") == "schulferien"
    await vorspulen(hass, freezer, "2026-12-26 03:59:00+01:00")
    assert hinweis(hass) is None
    await vorspulen(hass, freezer, "2026-12-26 04:09:00+01:00")
    assert hinweis(hass) is not None


async def test_schule_entfernt_raeumt_auf(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
    hass_storage: dict[str, Any],
) -> None:
    """Schule aus der Person entfernt: Daten und Hinweis verfallen (E41, E42)."""
    aioclient_mock.get(URL, exc=aiohttp.ClientError())
    entry = await haus(hass, freezer, person_mit_schule("p1", "Kind1"))
    await vorspulen(hass, freezer, "2026-12-23 04:39:00+01:00")
    assert hinweis(hass) is not None
    sub = entry.subentries["p1"]
    hass.config_entries.async_update_subentry(entry, sub, data={"zeitplan": PLAN})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hinweis(hass) is None
    await vorspulen(hass, freezer, "2026-12-23 04:49:00+01:00")
    gespeichert = hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]
    assert gespeichert["schulferien"] == {}


async def test_alter_hinweis_ohne_schule_wird_beim_start_entfernt(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Ein Hinweis aus der Zeit vor dem Neustart zu einer alten Schule verschwindet."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        "schulferien_veraltet_alte-schule",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="schulferien_veraltet",
    )
    aioclient_mock.get(URL, json=ANTWORT)
    await haus(hass, freezer, person_mit_schule("p1", "Kind1"))
    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, "schulferien_veraltet_alte-schule")
        is None
    )
    assert hinweis(hass) is None


@pytest.mark.parametrize(
    "schule",
    [
        {"name": "X"},
        {"anbieter": "mehr_schulferien", "name": "X"},
        {"anbieter": "gibt_es_nicht", "kennung": "x"},
    ],
    ids=["ohne_alles", "ohne_kennung", "unbekannter_anbieter"],
)
async def test_kaputte_schule_wird_ignoriert(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
    schule: dict[str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Kaputte Schul-Daten: wie ohne Schule, kein Abruf, einmal im Log."""
    await haus(hass, freezer, person_mit_schule("p1", "Kind1", schule=schule))
    await vorspulen(hass, freezer, "2026-12-23 04:09:00+01:00")
    assert caplog.text.count("Schule von Kind1 ist ungültig") == 1
    assert zustand(hass, "sensor", "p1", "status") == "werktag"
    assert aioclient_mock.call_count == 0


# ---------------------------------------------------------------- async-Fälle


class Haengend:
    """Antwort, die erst nach ``freigeben()`` kommt (Abruf hängt im Netz)."""

    def __init__(self, aioclient_mock: AiohttpClientMocker) -> None:
        """Merkt sich, wohin die Antwort gehört."""
        self.frei = asyncio.Event()
        self.mock = aioclient_mock

    async def __call__(self, method: str, url: Any, data: Any) -> Any:
        """Wartet, dann die echte Antwort."""
        await self.frei.wait()
        return AiohttpClientMockResponse(method, url, json=ANTWORT)


async def test_lauf_wartet_nicht_auf_das_netz(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Hängt der Abruf, ist trotzdem schon gerechnet; danach gilt „schulferien“."""
    haengend = Haengend(aioclient_mock)
    aioclient_mock.get(URL, side_effect=haengend)
    entry = await einrichten(
        hass, freezer, person_mit_schule("p1", "Kind1"), raum("r1", "S"), jetzt=JETZT
    )
    await hass.async_block_till_done()  # ohne Hintergrund-Aufgaben
    assert zustand(hass, "sensor", "p1", "naechster_wecker") == WERKTAG_WECKER
    haengend.frei.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert zustand(hass, "sensor", "p1", "naechster_wecker") == STANDARD_WECKER
    assert entry.runtime_data is not None


async def test_entladen_waehrend_des_abrufs(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
    hass_storage: dict[str, Any],
) -> None:
    """Entladen bricht einen hängenden Abruf ab; er schreibt danach nichts mehr."""
    haengend = Haengend(aioclient_mock)
    aioclient_mock.get(URL, side_effect=haengend)
    entry = await einrichten(
        hass, freezer, person_mit_schule("p1", "Kind1"), jetzt=JETZT
    )
    assert await hass.config_entries.async_unload(entry.entry_id)
    haengend.frei.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    gespeichert = hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]
    assert gespeichert["schulferien"][SCHLUESSEL]["abgerufen"] is None


async def test_unerwarteter_fehler_mit_traceback(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ein Programmierfehler wird als Ausfall behandelt, aber mit Traceback geloggt."""
    aioclient_mock.get(URL, json=ANTWORT)
    with patch(
        "custom_components.homewake.anbieter.mehr_schulferien.ferien_aus_antwort",
        side_effect=KeyError("kaputt"),
    ):
        await haus(hass, freezer, person_mit_schule("p1", "Kind1"))
    assert zustand(hass, "sensor", "p1", "status") == "werktag"
    eintrag = next(r for r in caplog.records if "nicht abrufbar" in r.message)
    assert eintrag.exc_info is not None


async def test_zweite_schule_waehrend_des_abrufs(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Kommt während eines Abrufs eine Schule dazu, wird sie gleich danach geholt."""
    haengend = Haengend(aioclient_mock)
    aioclient_mock.get(URL, side_effect=haengend)
    andere = f"{BASIS}/schools/andere-schule/periods"
    aioclient_mock.get(andere, json=ANTWORT)
    entry = await einrichten(
        hass,
        freezer,
        person_mit_schule("p1", "Kind1"),
        person_mit_schule("p2", "Kind2", schule=None),
        jetzt=JETZT,
    )
    await hass.async_block_till_done()
    sub = entry.subentries["p2"]
    hass.config_entries.async_update_subentry(
        entry,
        sub,
        data={
            **sub.data,
            "schule": {"anbieter": "mehr_schulferien", "kennung": "andere-schule"},
        },
    )
    await hass.async_block_till_done()
    haengend.frei.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert any(str(c[1]).startswith(andere) for c in aioclient_mock.mock_calls)


# ---------------------------------------------------------------- Anzeige


async def test_status_zeigt_schule_und_ferien(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Schule, geladene Ferien und Stand stehen als Attribute am Status-Sensor."""
    aioclient_mock.get(URL, json=ANTWORT)
    await haus(hass, freezer, person_mit_schule("p1", "Kind1"))
    state = hass.states.get(entity_id(hass, "sensor", "p1", "status"))
    assert state is not None
    assert state.attributes["schule"] == (
        "Deutschland → Hessen → Frankfurt am Main → Frankfurt am Main → "
        "Ludwig-Börne-Schule"
    )
    assert state.attributes["schulferien"] == [
        {"name": "Weihnachten", "beginn": "2026-12-23", "ende": "2027-01-12"}
    ]
    assert state.attributes["schulferien_stand"] == datetime.fromisoformat(JETZT)


async def test_vergangene_ferien_nicht_angezeigt(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Vorbei ist vorbei: abgelaufene Ferien verschwinden aus der Liste."""
    aioclient_mock.get(URL, json=ANTWORT)
    await haus(hass, freezer, person_mit_schule("p1", "Kind1"))
    antwort_setzen(aioclient_mock, exc=aiohttp.ClientError())
    await vorspulen(hass, freezer, "2027-01-13 04:09:00+01:00")
    state = hass.states.get(entity_id(hass, "sensor", "p1", "status"))
    assert state is not None
    assert state.attributes["schulferien"] == []


async def test_ohne_schule_keine_schul_attribute(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Ohne Schule gibt es die Attribute nicht."""
    await haus(hass, freezer, person_mit_schule("p1", "Vater", schule=None))
    state = hass.states.get(entity_id(hass, "sensor", "p1", "status"))
    assert state is not None
    assert "schule" not in state.attributes
    assert "schulferien" not in state.attributes


def test_schul_attribute_werden_nicht_aufgezeichnet() -> None:
    """Die Ferienliste landet nicht in der Verlaufs-Datenbank (Recorder)."""
    assert {"schule", "schulferien", "schulferien_stand"} <= (
        StatusSensor._unrecorded_attributes
    )
