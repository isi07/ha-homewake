"""Tests für die Diagnose-Datei (Quality Scale ``diagnostics``, Phase 8b).

Die Diagnose enthält Eintrag, Untereinträge, Speicher, letztes Ergebnis und den
Stand der Hintergrund-Abrufe. Namen, Kalender und Schule werden geschwärzt; vom
Urlaub nur heute und morgen (was der aktuelle Lauf nutzt).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from custom_components.homewake.const import DOMAIN
from custom_components.homewake.coordinator import HomeWakeCoordinator
from custom_components.homewake.diagnostics import (
    async_get_config_entry_diagnostics,
)
from tests.test_person_sensoren import einrichten
from tests.test_raum_sensoren import raum, waehle_raum
from tests.test_schulferien import (
    ANTWORT,
    SCHLUESSEL,
    SCHULE,
    URL,
    person_mit_schule,
)

GESCHWAERZT = "**REDACTED**"


async def diagnose_einrichten(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> HomeWakeCoordinator:
    """Vater (Schule, Urlaubskalender) im Schlafzimmer, Mittwoch 23.12.2026."""
    aioclient_mock.get(URL, json=ANTWORT)
    vater = person_mit_schule("p1", "Vater")
    vater["data"] = dict(vater["data"]) | {"urlaubskalender": "calendar.urlaub_vater"}
    entry = await einrichten(
        hass,
        freezer,
        vater,
        raum(
            "r1",
            "Schlafzimmer",
            bereich="schlafzimmer_vater",
            lichter=["light.nachttisch_vater"],
            lautsprecher="media_player.sonos_vater",
        ),
        jetzt="2026-12-23 04:00:00+01:00",
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    await hass.async_block_till_done(wait_background_tasks=True)
    coordinator: HomeWakeCoordinator = entry.runtime_data
    return coordinator


async def diagnose(hass: HomeAssistant, coordinator: HomeWakeCoordinator) -> Any:
    """Diagnose wie beim Herunterladen, einmal durch JSON (muss speicherbar sein)."""
    daten = await async_get_config_entry_diagnostics(hass, coordinator.config_entry)
    return json.loads(json.dumps(daten))


async def test_diagnose_enthaelt_eintrag_speicher_und_ergebnis(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Die Diagnose zeigt Aufbau, Speicher, letztes Ergebnis und Abrufe."""
    coordinator = await diagnose_einrichten(hass, freezer, aioclient_mock)
    diag = await diagnose(hass, coordinator)
    assert diag["eintrag"]["version"] == 1
    assert diag["eintrag"]["data"] == {}
    assert diag["untereintraege"]["p1"]["typ"] == "person"
    assert diag["untereintraege"]["r1"]["typ"] == "raum"
    assert diag["untereintraege"]["r1"]["data"]["zuordenbar"] is True
    assert diag["speicher"]["personen"]["p1"]["bedienung"]["raum_id"] == "r1"
    ergebnis = diag["ergebnis"]
    assert ergebnis["personen"]["p1"]["status"] == "schulferien"
    assert ergebnis["personen"]["p1"]["grund"] == "Weihnachten"
    assert ergebnis["raeume"]["r1"]["quelle"] == "personen"
    assert ergebnis["naechste_aenderung"].startswith("2026-12-23")
    assert diag["lauf"]["letzter_lauf_erfolgreich"] is True
    # Schule anonym, Ferien sichtbar
    schulen = diag["speicher"]["schulferien"]
    assert list(schulen) == ["schule_1"]
    assert schulen["schule_1"]["ferien"]
    assert diag["schulen"]["schule_1"]["hinweis"] is False


async def test_diagnose_schwaerzt_namen_kalender_und_schule(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Weder Personen- und Raumnamen noch Kalender oder Schule stehen im Text."""
    coordinator = await diagnose_einrichten(hass, freezer, aioclient_mock)
    diag = await diagnose(hass, coordinator)
    text = json.dumps(diag, ensure_ascii=False)
    for geheim in (
        "Vater",
        "Schlafzimmer",
        "calendar.urlaub_vater",
        "schlafzimmer_vater",
        "light.nachttisch_vater",
        "media_player.sonos_vater",
        str(SCHULE["kennung"]),
        str(SCHULE["name"]),
        "Frankfurt am Main",
        "Frankfurt am Main",
    ):
        assert geheim not in text, geheim
    assert diag["untereintraege"]["p1"]["title"] == GESCHWAERZT
    assert diag["untereintraege"]["p1"]["data"]["schule"] == GESCHWAERZT
    assert diag["untereintraege"]["p1"]["data"]["urlaubskalender"] == GESCHWAERZT
    assert diag["ergebnis"]["raeume"]["r1"]["weckende"] == GESCHWAERZT
    assert diag["ergebnis"]["raeume"]["r1"]["im_raum"] == GESCHWAERZT
    assert diag["speicher"]["personen"]["p1"]["schul_nummer"] == "schule_1"


async def test_diagnose_zeigt_urlaub_nur_heute_und_morgen(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Vom gespeicherten Urlaub erscheinen nur heute und morgen."""
    coordinator = await diagnose_einrichten(hass, freezer, aioclient_mock)
    coordinator._urlaub["p1"] = {
        date(2026, 12, 22): True,
        date(2026, 12, 23): False,
        date(2026, 12, 24): True,
        date(2026, 12, 25): True,
    }
    diag = await diagnose(hass, coordinator)
    assert diag["speicher"]["personen"]["p1"]["urlaub"] == {
        "2026-12-23": False,
        "2026-12-24": True,
    }


async def test_diagnose_ohne_ergebnis(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Fehlt ein Ergebnis (z. B. Lauf gescheitert), bleibt die Diagnose lesbar."""
    coordinator = await diagnose_einrichten(hass, freezer, aioclient_mock)
    coordinator.data = None  # type: ignore[assignment]
    diag = await diagnose(hass, coordinator)
    assert diag["ergebnis"] is None


async def test_schulferien_hinweis_verraet_die_schule_nicht(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """HA hängt die Hinweis-IDs ungeschwärzt an die Diagnose: ohne Kennung (E49)."""
    coordinator = await diagnose_einrichten(hass, freezer, aioclient_mock)
    coordinator._schul_hinweis_zeigen(SCHLUESSEL, "Ludwig-Börne-Schule")
    ids = [i for d, i in ir.async_get(hass).issues if d == DOMAIN]
    assert any(i.startswith("schulferien_veraltet_") for i in ids)
    for issue_id in ids:
        assert str(SCHULE["kennung"]) not in issue_id
