"""Tests für das Schalten von Licht und Radio in HA (ARCHITEKTUR.md 4.7).

Die Aktionen von ``light`` und ``media_player`` werden hier nur
mitgeschrieben. Die Mitschrift ahmt ein Gerät nach: Ein eingeschaltetes Licht
ist danach „on“, ein Lautsprecher spielt nach Play die gewählte Quelle.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import MockConfigEntry

from custom_components.homewake.const import DOMAIN
from custom_components.homewake.coordinator import HomeWakeCoordinator
from custom_components.homewake.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.homewake.logic.aktorik import RadioBefehl, Schaltplan
from tests.test_bedienung import schalte
from tests.test_person_sensoren import einrichten, entity_id, person, vorspulen
from tests.test_raum_sensoren import raum, waehle_raum

LICHT = "light.test_licht"
LAUTSPRECHER = "media_player.test_sonos"
FAVORITEN = ["hr3", "SWR3", "YOU FM"]
WINTER = "2026-11-24 04:00:00+01:00"  # Dienstag, um 06:15 noch dunkel
SOMMER = "2026-07-14 04:00:00+02:00"  # Dienstag, um 06:15 schon hell

type Aufruf = tuple[str, str, dict[str, Any]]


def mitschreiben(hass: HomeAssistant, fehler: set[str] | None = None) -> list[Aufruf]:
    """Meldet Licht- und Lautsprecher-Aktionen an, die nur mitschreiben.

    Aktionen in ``fehler`` (z. B. ``"light.turn_on"``) scheitern wie ein nicht
    erreichbares Gerät.
    """
    aufrufe: list[Aufruf] = []
    quelle: dict[str, str] = {}

    async def handler(call: ServiceCall) -> None:
        name = f"{call.domain}.{call.service}"
        daten = dict(call.data)
        aufrufe.append((call.domain, call.service, daten))
        if fehler and name in fehler:
            msg = "Gerät nicht erreichbar"
            raise HomeAssistantError(msg)
        ids = daten.get("entity_id")
        ids = [ids] if isinstance(ids, str) else list(ids or [])
        for eid in ids:
            state = hass.states.get(eid)
            attrs = dict(state.attributes) if state else {}
            if name == "light.turn_on":
                hass.states.async_set(eid, "on", attrs)
            elif name == "light.turn_off":
                hass.states.async_set(eid, "off", attrs)
            elif name == "media_player.select_source":
                quelle[eid] = daten["source"]
            elif name == "media_player.media_play":
                attrs["source"] = quelle.get(eid)
                hass.states.async_set(eid, "playing", attrs)
            elif name == "media_player.media_stop":
                hass.states.async_set(eid, "idle", attrs)

    for domain, service in (
        ("light", "turn_on"),
        ("light", "turn_off"),
        ("media_player", "volume_set"),
        ("media_player", "select_source"),
        ("media_player", "media_play"),
        ("media_player", "media_stop"),
    ):
        hass.services.async_register(domain, service, handler)
    return aufrufe


def namen(aufrufe: list[Aufruf]) -> list[str]:
    """Nur die Namen der Aktionen in Reihenfolge."""
    return [f"{d}.{s}" for d, s, _ in aufrufe]


async def aufbau(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    *,
    jetzt: str = WINTER,
    favorit: str | None = "SWR3",
    **raum_daten: Any,
) -> MockConfigEntry:
    """Vater im Schlafzimmer mit Licht und Lautsprecher; Licht und Radio an."""
    hass.states.async_set(LICHT, "off")
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": FAVORITEN})
    entry = await einrichten(
        hass,
        freezer,
        person("p1", "Vater"),
        raum(
            "r1",
            "Schlafzimmer",
            **(
                {"lichter": [LICHT], "helligkeit": 80, "lautsprecher": LAUTSPRECHER}
                | raum_daten
            ),
        ),
        jetzt=jetzt,
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    await schalte(hass, "p1", "licht_zeitplan", True)
    await schalte(hass, "p1", "radio_zeitplan", True)
    if favorit is not None:
        await hass.services.async_call(
            "select",
            "select_option",
            {
                "entity_id": entity_id(hass, "select", "p1", "favorit"),
                "option": favorit,
            },
            blocking=True,
        )
        await hass.async_block_till_done()
    return entry


def tag(jetzt: str, uhrzeit: str) -> str:
    """Zeitpunkt am Tag von ``jetzt`` (gleicher Offset)."""
    datum, _, rest = jetzt.partition(" ")
    return f"{datum} {uhrzeit}{rest[8:]}"


# ---------------------------------------------------------------- Einschalten


async def test_wecken_schaltet_licht_und_radio_in_reihenfolge(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Zur Weckzeit: Licht mit Helligkeit, dann Lautstärke → Quelle → Play (4.7)."""
    aufrufe = mitschreiben(hass)
    await aufbau(hass, freezer)
    assert aufrufe == []
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert aufrufe == [
        ("light", "turn_on", {"entity_id": LICHT, "brightness_pct": 80}),
        (
            "media_player",
            "volume_set",
            {"entity_id": LAUTSPRECHER, "volume_level": 0.3},
        ),
        (
            "media_player",
            "select_source",
            {"entity_id": LAUTSPRECHER, "source": "SWR3"},
        ),
        ("media_player", "media_play", {"entity_id": LAUTSPRECHER}),
    ]


async def test_standard_favorit_wenn_person_keinen_hat(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ohne Favorit der Person spielt der Standard-Favorit des Raums."""
    aufrufe = mitschreiben(hass)
    await aufbau(hass, freezer, favorit=None)
    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": entity_id(hass, "select", "r1", "standard_favorit"),
            "option": "hr3",
        },
        blocking=True,
    )
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert (
        "media_player",
        "select_source",
        {"entity_id": LAUTSPRECHER, "source": "hr3"},
    ) in aufrufe


async def test_ohne_favoriten_spielt_der_erste_der_liste(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """E56: Kein Favorit, kein Standard-Favorit → erster Eintrag der Liste."""
    aufrufe = mitschreiben(hass)
    await aufbau(hass, freezer, favorit=None)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert (
        "media_player",
        "select_source",
        {"entity_id": LAUTSPRECHER, "source": "hr3"},
    ) in aufrufe
    assert namen(aufrufe)[-1] == "media_player.media_play"


async def test_hell_kein_licht(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Im Sommer ist die Sonne um 06:15 über -3°: kein Licht, Radio schon (E51)."""
    aufrufe = mitschreiben(hass)
    await aufbau(hass, freezer, jetzt=SOMMER)
    await vorspulen(hass, freezer, tag(SOMMER, "06:15:00"))
    assert namen(aufrufe) == [
        "media_player.volume_set",
        "media_player.select_source",
        "media_player.media_play",
    ]


async def test_standard_favorit_aenderung_rechnet_neu(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """3.7: Eine Änderung des Standard-Favoriten lässt neu rechnen."""
    entry = await aufbau(hass, freezer)
    coordinator: HomeWakeCoordinator = entry.runtime_data
    vorher = coordinator.data
    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": entity_id(hass, "select", "r1", "standard_favorit"),
            "option": "hr3",
        },
        blocking=True,
    )
    assert coordinator.data is not vorher


@pytest.mark.parametrize(
    ("fehler", "erwartet"),
    [
        (
            "light.turn_on",
            [
                "light.turn_on",
                "media_player.volume_set",
                "media_player.select_source",
                "media_player.media_play",
            ],
        ),
        ("media_player.volume_set", ["light.turn_on", "media_player.volume_set"]),
    ],
)
async def test_ein_geraet_scheitert_das_andere_schaltet(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    fehler: str,
    erwartet: list[str],
) -> None:
    """E52 (Teil): Scheitert ein Gerät, schaltet das andere trotzdem; Warnung im Log.

    Scheitert der Lautsprecher schon bei der Lautstärke, kommt keine Quelle
    und kein Play hinterher.
    """
    aufrufe = mitschreiben(hass, {fehler})
    await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert namen(aufrufe) == erwartet
    assert "nicht erreichbar" in caplog.text


# ---------------------------------------------------------------- Ausschalten


async def test_nach_der_dauer_wird_ausgeschaltet(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """45 min nach dem Schalten: Licht aus, Lautsprecher stopp."""
    aufrufe = mitschreiben(hass)
    await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    aufrufe.clear()
    await vorspulen(hass, freezer, tag(WINTER, "06:59:59"))
    assert aufrufe == []
    await vorspulen(hass, freezer, tag(WINTER, "07:00:00"))
    assert aufrufe == [
        ("light", "turn_off", {"entity_id": LICHT}),
        ("media_player", "media_stop", {"entity_id": LAUTSPRECHER}),
    ]


async def test_vom_menschen_geaendertes_bleibt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """E50: Licht schon aus, andere Quelle gewählt → nichts ausschalten."""
    aufrufe = mitschreiben(hass)
    await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    hass.states.async_set(LICHT, "off")
    hass.states.async_set(
        LAUTSPRECHER, "playing", {"source_list": FAVORITEN, "source": "hr3"}
    )
    aufrufe.clear()
    await vorspulen(hass, freezer, tag(WINTER, "07:00:00"))
    assert aufrufe == []


async def test_aus_timer_uebersteht_neuladen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """E12: Nach Neuladen während der Dauer wird trotzdem ausgeschaltet."""
    aufrufe = mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    aufrufe.clear()
    await vorspulen(hass, freezer, tag(WINTER, "07:00:00"))
    assert namen(aufrufe) == ["light.turn_off", "media_player.media_stop"]


async def test_abgelaufener_timer_wird_beim_start_nachgeholt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """E54 (2): War HA beim Aus-Zeitpunkt aus, wird beim Start ausgeschaltet."""
    aufrufe = mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert await hass.config_entries.async_unload(entry.entry_id)
    aufrufe.clear()
    freezer.move_to(tag(WINTER, "07:30:00"))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert namen(aufrufe) == ["light.turn_off", "media_player.media_stop"]
    # Danach ist der Auftrag erledigt: kein zweites Ausschalten.
    aufrufe.clear()
    await vorspulen(hass, freezer, tag(WINTER, "08:00:00"))
    assert aufrufe == []


async def test_nach_dem_entladen_wird_nicht_mehr_ausgeschaltet(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Entladen meldet den Aus-Timer ab."""
    aufrufe = mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert await hass.config_entries.async_unload(entry.entry_id)
    aufrufe.clear()
    await vorspulen(hass, freezer, tag(WINTER, "07:00:00"))
    assert aufrufe == []


async def test_aus_auftrag_steht_sofort_im_speicher(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    """Der Aus-Auftrag wird mit dem Wecken sofort gespeichert (E12, E32)."""
    mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    # Geräte kommen nach dem Schalten dazu, gespeichert mit 1 s Verzögerung
    await vorspulen(hass, freezer, tag(WINTER, "06:15:02"))
    daten = hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]
    aus = daten["raeume"]["r1"]["aus"]
    assert aus == {
        "um": "2026-11-24T07:00:00+01:00",
        "lichter": [LICHT],
        "lautsprecher": LAUTSPRECHER,
        "quelle": "SWR3",
    }


# ---------------------------------------------------------------- Nachholen (E28)


@pytest.mark.parametrize(
    ("start", "geschaltet"), [("06:30:00", True), ("06:30:01", False)]
)
async def test_nachholen_nach_neustart_hoechstens_15_minuten(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    start: str,
    geschaltet: bool,
) -> None:
    """E28: HA war um 06:15 aus; bis 06:30 wird nachgeholt, danach nicht."""
    aufrufe = mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    assert await hass.config_entries.async_unload(entry.entry_id)
    freezer.move_to(tag(WINTER, start))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert bool(aufrufe) is geschaltet


async def test_unklarer_zustand_wird_ausgeschaltet_sobald_das_geraet_da_ist(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """E54 (3) mit A2: Licht fehlt, Lautsprecher nicht verfügbar → später aus.

    Eine Aktion an ein nicht verfügbares Gerät verpufft in HA. Darum wird
    gewartet, bis es wieder da ist, und dann nach E50 entschieden.
    """
    aufrufe = mitschreiben(hass)
    await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    hass.states.async_remove(LICHT)
    hass.states.async_set(LAUTSPRECHER, "unavailable")
    aufrufe.clear()
    await vorspulen(hass, freezer, tag(WINTER, "07:00:00"))
    assert aufrufe == []
    # Licht kommt eingeschaltet zurück → aus
    hass.states.async_set(LICHT, "on")
    await hass.async_block_till_done()
    assert namen(aufrufe) == ["light.turn_off"]
    # Lautsprecher kommt still zurück → nichts zu stoppen (E50)
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": FAVORITEN})
    await hass.async_block_till_done()
    assert namen(aufrufe) == ["light.turn_off"]


async def test_fremder_fehler_haelt_das_andere_geraet_nicht_auf(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Auch ein Nicht-HA-Fehler (z. B. RuntimeError) stoppt nur sein Gerät."""
    aufrufe = mitschreiben(hass)

    async def kaputt(call: ServiceCall) -> None:
        msg = "Bibliothek abgestürzt"
        raise RuntimeError(msg)

    hass.services.async_register("light", "turn_on", kaputt)
    await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert namen(aufrufe) == [
        "media_player.volume_set",
        "media_player.select_source",
        "media_player.media_play",
    ]
    assert "Bibliothek abgestürzt" in caplog.text


async def test_fehler_beim_planen_stoert_den_lauf_nicht(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ein Fehler beim Schaltplan wird geloggt; der Raum ist trotzdem geweckt."""
    aufrufe = mitschreiben(hass)
    await aufbau(hass, freezer)
    with patch(
        "custom_components.homewake.coordinator.schaltplan",
        side_effect=ValueError("kaputt"),
    ):
        await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert aufrufe == []
    assert "Schalten in Schlafzimmer fehlgeschlagen" in caplog.text
    assert hass.states.get(entity_id(hass, "binary_sensor", "r1", "wach")).state == "on"  # type: ignore[union-attr]


async def test_nachholen_beim_booten_erst_nach_dem_start(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Beim Booten wird erst geschaltet, wenn HA fertig gestartet ist."""
    aufrufe = mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    assert await hass.config_entries.async_unload(entry.entry_id)
    freezer.move_to(tag(WINTER, "06:20:00"))
    hass.set_state(CoreState.starting)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert aufrufe == []
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert namen(aufrufe)[0] == "light.turn_on"
    assert len(aufrufe) == 4


async def test_entladen_beim_booten_verwirft_das_wartende_schalten(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Wird vor dem Start entladen, schaltet das Nachholen nicht mehr."""
    aufrufe = mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    assert await hass.config_entries.async_unload(entry.entry_id)
    freezer.move_to(tag(WINTER, "06:20:00"))
    hass.set_state(CoreState.starting)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert aufrufe == []


async def test_diagnose_schwaerzt_die_geraete_im_aus_auftrag(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """E49: Geräte im Aus-Auftrag geschwärzt, der Sender nicht."""
    mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    diag = await async_get_config_entry_diagnostics(hass, entry)
    aus = diag["speicher"]["raeume"]["r1"]["aus"]
    assert aus["lichter"] == "**REDACTED**"
    assert aus["lautsprecher"] == "**REDACTED**"
    assert aus["quelle"] == "SWR3"


# ---------------------------------------------------------------- Wiederholen (A2, E52)


def warnungen(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Warnungen des Schalt-Bausteins."""
    return [
        r.getMessage()
        for r in caplog.records
        if r.name.endswith(".schalten") and r.levelno == logging.WARNING
    ]


async def test_nicht_verfuegbares_licht_wird_nachgeholt(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Licht beim Wecken nicht verfügbar → kein Aufruf; wieder da → einschalten.

    Danach steht es im Aus-Auftrag und wird nach der Dauer ausgeschaltet.
    """
    caplog.set_level(logging.INFO)
    aufrufe = mitschreiben(hass)
    await aufbau(hass, freezer)
    hass.states.async_set(LICHT, "unavailable")
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert "light.turn_on" not in namen(aufrufe)
    assert len(warnungen(caplog)) == 1
    assert "nicht verfügbar" in warnungen(caplog)[0]
    freezer.move_to(tag(WINTER, "06:16:10"))
    hass.states.async_set(LICHT, "off")
    await hass.async_block_till_done()
    assert namen(aufrufe).count("light.turn_on") == 1
    assert "jetzt geschaltet" in caplog.text
    aufrufe.clear()
    await vorspulen(hass, freezer, tag(WINTER, "07:00:00"))
    assert namen(aufrufe) == ["light.turn_off", "media_player.media_stop"]


async def test_wiederholung_alle_30_sekunden_mit_einer_warnung(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """E55 (1): Scheitert die Aktion, alle 30 s neu; nur die erste warnt."""
    aufrufe = mitschreiben(hass, {"light.turn_on"})
    await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    await vorspulen(hass, freezer, tag(WINTER, "06:15:29"))
    assert namen(aufrufe).count("light.turn_on") == 1
    await vorspulen(hass, freezer, tag(WINTER, "06:15:30"))
    assert namen(aufrufe).count("light.turn_on") == 2
    await vorspulen(hass, freezer, tag(WINTER, "06:16:00"))
    assert namen(aufrufe).count("light.turn_on") == 3
    assert len(warnungen(caplog)) == 1


async def test_nach_15_minuten_wird_aufgegeben(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """E52: Letzter Versuch 15 min nach dem Wecken, dann Warnung und Schluss."""
    aufrufe = mitschreiben(hass, {"light.turn_on"})
    await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    await vorspulen(hass, freezer, tag(WINTER, "06:29:59"))
    assert len(warnungen(caplog)) == 1
    await vorspulen(hass, freezer, tag(WINTER, "06:30:00"))
    assert namen(aufrufe).count("light.turn_on") == 3
    assert len(warnungen(caplog)) == 2
    assert "aufgegeben" in warnungen(caplog)[1]
    await vorspulen(hass, freezer, tag(WINTER, "06:31:00"))
    assert namen(aufrufe).count("light.turn_on") == 3
    # Nie eingeschaltet → nach der Dauer nichts auszuschalten
    aufrufe.clear()
    await vorspulen(hass, freezer, tag(WINTER, "07:00:00"))
    assert namen(aufrufe) == ["media_player.media_stop"]


async def test_lautsprecher_kommt_zurueck_und_waehlt_die_quelle_dann(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Lautsprecher beim Wecken ohne Liste nicht verfügbar; zurück → Favorit spielt."""
    aufrufe = mitschreiben(hass)
    await aufbau(hass, freezer)
    hass.states.async_set(LAUTSPRECHER, "unavailable")
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert namen(aufrufe) == ["light.turn_on"]
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": FAVORITEN})
    await hass.async_block_till_done()
    assert aufrufe[1:] == [
        (
            "media_player",
            "volume_set",
            {"entity_id": LAUTSPRECHER, "volume_level": 0.3},
        ),
        (
            "media_player",
            "select_source",
            {"entity_id": LAUTSPRECHER, "source": "SWR3"},
        ),
        ("media_player", "media_play", {"entity_id": LAUTSPRECHER}),
    ]
    aufrufe.clear()
    await vorspulen(hass, freezer, tag(WINTER, "07:00:00"))
    assert namen(aufrufe) == ["light.turn_off", "media_player.media_stop"]


async def test_haengendes_geraet_laeuft_ins_zeitlimit(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Hängt eine Aktion, gilt sie nach dem Zeitlimit als gescheitert."""
    aufrufe = mitschreiben(hass)
    nie = asyncio.Event()

    async def haengt(call: ServiceCall) -> None:
        aufrufe.append((call.domain, call.service, dict(call.data)))
        await nie.wait()

    hass.services.async_register("light", "turn_on", haengt)
    await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert "media_player.media_play" in namen(aufrufe)
    assert warnungen(caplog) == []
    await vorspulen(hass, freezer, tag(WINTER, "06:15:10"))
    assert any("Zeitlimit" in w for w in warnungen(caplog))


async def test_ausschalten_gibt_nach_15_minuten_auf(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    hass_storage: dict[str, Any],
) -> None:
    """Bleibt das Licht beim Ausschalten weg, Schluss 15 min nach dem Aus-Zeitpunkt."""
    aufrufe = mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    hass.states.async_set(LICHT, "unavailable")
    aufrufe.clear()
    await vorspulen(hass, freezer, tag(WINTER, "07:00:00"))
    assert namen(aufrufe) == ["media_player.media_stop"]
    await vorspulen(hass, freezer, tag(WINTER, "07:14:59"))
    await vorspulen(hass, freezer, tag(WINTER, "07:15:00"))
    assert any("aufgegeben" in w for w in warnungen(caplog))
    await hass.async_block_till_done(wait_background_tasks=True)
    await vorspulen(hass, freezer, tag(WINTER, "07:15:02"))
    daten = hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]
    assert daten["raeume"]["r1"]["aus"] is None


async def test_kurze_dauer_beendet_die_versuche(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Dauer 2 min: Versuche enden zum Aus-Zeitpunkt, danach wird nichts mehr an."""
    aufrufe = mitschreiben(hass)
    await aufbau(hass, freezer, dauer=2)
    hass.states.async_set(LICHT, "unavailable")
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    await vorspulen(hass, freezer, tag(WINTER, "06:17:00"))
    aufrufe.clear()
    hass.states.async_set(LICHT, "off")
    await hass.async_block_till_done()
    await vorspulen(hass, freezer, tag(WINTER, "06:18:00"))
    assert "light.turn_on" not in namen(aufrufe)


async def test_diagnose_zeigt_offene_versuche(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Die Diagnose zählt die Geräte, die gerade wiederholt werden."""
    mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    hass.states.async_set(LICHT, "unavailable")
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["schalten"]["wiederholungen"] == {"r1": 1}
    assert diag["schalten"]["aus_auftraege"] == ["r1"]


# ---------------------------------------------------------------- Gerät fehlt (A2)


async def test_fehlendes_geraet_zeigt_hinweis_bis_es_da_ist(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ein eingetragenes Gerät, das HA nicht kennt → Hinweis pro Raum."""
    entry = await aufbau(hass, freezer, lichter=[LICHT, "light.weg"])
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "geraet_fehlt_r1")
    assert issue is not None
    assert issue.translation_key == "geraet_fehlt"
    assert issue.translation_placeholders == {
        "raum": "Schlafzimmer",
        "geraete": "light.weg",
    }
    assert issue.config_entry_id == entry.entry_id
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["hinweise"]["geraet_fehlt"] == ["r1"]
    # Nur nicht verfügbar zählt nicht als fehlend
    hass.states.async_set("light.weg", "unavailable")
    await entry.runtime_data.async_refresh()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "geraet_fehlt_r1") is None


async def test_hinweis_erst_wenn_ha_gestartet_ist(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Beim Booten fehlen Geräte oft nur kurz: geprüft wird nach dem Start."""
    entry = await aufbau(hass, freezer, favorit=None, lautsprecher="media_player.weg")
    assert await hass.config_entries.async_unload(entry.entry_id)
    ir.async_delete_issue(hass, DOMAIN, "geraet_fehlt_r1")
    hass.set_state(CoreState.starting)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "geraet_fehlt_r1") is None
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "geraet_fehlt_r1") is not None


async def test_hinweis_eines_geloeschten_raums_verschwindet(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Raum gelöscht → sein Hinweis „Gerät fehlt“ geht mit."""
    entry = await aufbau(hass, freezer, lichter=["light.weg"])
    assert ir.async_get(hass).async_get_issue(DOMAIN, "geraet_fehlt_r1") is not None
    assert hass.config_entries.async_remove_subentry(entry, "r1")
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "geraet_fehlt_r1") is None


# ---------------------------------------------------------------- Raum gelöscht (A2)


async def test_geloeschter_raum_schaltet_trotzdem_aus(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    """Raum während der Dauer gelöscht: Der Aus-Auftrag läuft trotzdem."""
    aufrufe = mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert hass.config_entries.async_remove_subentry(entry, "r1")
    await hass.async_block_till_done()
    aufrufe.clear()
    await vorspulen(hass, freezer, tag(WINTER, "07:00:00"))
    assert namen(aufrufe) == ["light.turn_off", "media_player.media_stop"]
    await hass.async_block_till_done(wait_background_tasks=True)
    await vorspulen(hass, freezer, tag(WINTER, "07:00:02"))
    daten = hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]
    assert "r1" not in daten["raeume"]


# ---------------------------------------------------------------- Wettläufe (Review A2)


async def test_attribut_aenderung_loest_keinen_sofortigen_versuch_aus(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Nur das Wiederkommen löst sofort einen Versuch aus, nicht jede Änderung."""
    aufrufe = mitschreiben(hass, {"light.turn_on"})
    await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    hass.states.async_set(LICHT, "off", {"friendly_name": "neu"})
    await hass.async_block_till_done()
    assert namen(aufrufe).count("light.turn_on") == 1


async def test_neues_wecken_bricht_laufendes_ausschalten_ab(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ein altes Ausschalten darf ein neues Wecken nicht wieder stoppen."""
    aufrufe = mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    hass.states.async_set(LAUTSPRECHER, "unavailable")
    await vorspulen(hass, freezer, tag(WINTER, "07:00:00"))
    # Ausschalten des Lautsprechers wartet; jetzt wird der Raum neu geweckt
    jetzt = dt_util.now()
    entry.runtime_data._schalter.wecken(
        "r1",
        Schaltplan(
            licht=None,
            radio=RadioBefehl(LAUTSPRECHER, 0.3, "SWR3", None),
            aus_um=jetzt + timedelta(minutes=45),
            versuche_bis=jetzt + timedelta(minutes=15),
        ),
    )
    aufrufe.clear()
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": FAVORITEN})
    await hass.async_block_till_done()
    await vorspulen(hass, freezer, tag(WINTER, "07:00:30"))
    assert namen(aufrufe) == [
        "media_player.volume_set",
        "media_player.select_source",
        "media_player.media_play",
    ]


async def test_abbruch_mitten_im_einschalten_laesst_kein_licht_an(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Aus-Zeitpunkt während eines hängenden Einschaltens: Licht trotzdem aus."""
    aufrufe = mitschreiben(hass)
    nie = asyncio.Event()

    async def an_und_haengen(call: ServiceCall) -> None:
        aufrufe.append((call.domain, call.service, dict(call.data)))
        hass.states.async_set(LICHT, "on")
        await nie.wait()

    hass.services.async_register("light", "turn_on", an_und_haengen)
    await aufbau(hass, freezer, dauer=2)
    hass.states.async_set(LICHT, "unavailable")
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    freezer.move_to(tag(WINTER, "06:16:55"))
    hass.states.async_set(LICHT, "off")
    await hass.async_block_till_done()
    assert namen(aufrufe).count("light.turn_on") == 1
    await vorspulen(hass, freezer, tag(WINTER, "06:17:00"))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert "light.turn_off" in namen(aufrufe)


async def test_entladen_beendet_laufende_versuche(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Nach dem Entladen schaltet kein alter Versuch mehr."""
    aufrufe = mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    hass.states.async_set(LICHT, "unavailable")
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert await hass.config_entries.async_unload(entry.entry_id)
    aufrufe.clear()
    hass.states.async_set(LICHT, "off")
    await vorspulen(hass, freezer, tag(WINTER, "06:16:00"))
    assert aufrufe == []


async def test_deaktiviertes_geraet_zeigt_hinweis(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ein deaktiviertes Licht kann HomeWake nicht schalten → Hinweis."""
    er.async_get(hass).async_get_or_create(
        "light",
        "test",
        "aus_1",
        suggested_object_id="deaktiviert",
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    await aufbau(hass, freezer, lichter=[LICHT, "light.deaktiviert"])
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "geraet_fehlt_r1")
    assert issue is not None
    assert issue.translation_placeholders == {
        "raum": "Schlafzimmer",
        "geraete": "light.deaktiviert",
    }


# ------------------------------------------------- Leere Favoritenliste (E55 (7))


async def test_leere_favoritenliste_wird_abgewartet(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Lautsprecher da, Liste noch leer (Sonos nach Neustart) → warten, dann spielen."""
    aufrufe = mitschreiben(hass)
    await aufbau(hass, freezer)
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": []})
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert namen(aufrufe) == ["light.turn_on"]
    assert any("Favoritenliste" in w for w in warnungen(caplog))
    # Liste kommt (nur ein Attribut ändert sich) → sofort weiter
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": FAVORITEN})
    await hass.async_block_till_done()
    assert namen(aufrufe)[1:] == [
        "media_player.volume_set",
        "media_player.select_source",
        "media_player.media_play",
    ]


async def test_ohne_favoriten_und_ohne_liste_wird_gewartet(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """E56: Auch ohne Favoriten wird auf die Liste gewartet, dann der Erste."""
    aufrufe = mitschreiben(hass)
    await aufbau(hass, freezer, favorit=None)
    hass.states.async_set(LAUTSPRECHER, "idle")
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert namen(aufrufe) == ["light.turn_on"]
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": FAVORITEN})
    await hass.async_block_till_done()
    assert (
        "media_player",
        "select_source",
        {"entity_id": LAUTSPRECHER, "source": "hr3"},
    ) in aufrufe


# ------------------------------------------------- Favorit fehlt in der Liste (E56)


def favorit_hinweis(hass: HomeAssistant, sid: str) -> ir.IssueEntry | None:
    """Hinweis „Favorit fehlt“ einer Person bzw. eines Raums."""
    return ir.async_get(hass).async_get_issue(DOMAIN, f"favorit_fehlt_{sid}")


async def standard_favorit(hass: HomeAssistant, option: str) -> None:
    """Standard-Favorit des Raums r1 wählen."""
    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": entity_id(hass, "select", "r1", "standard_favorit"),
            "option": option,
        },
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_fehlender_favorit_der_person_zeigt_hinweis_und_spielt_den_ersten(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """E56: Favorit der Person fehlt in der Liste → Hinweis, Wecken mit dem Ersten."""
    aufrufe = mitschreiben(hass)
    await aufbau(hass, freezer)
    assert favorit_hinweis(hass, "p1") is None
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": ["YOU FM", "hr3"]})
    await hass.async_block_till_done()
    issue = favorit_hinweis(hass, "p1")
    assert issue is not None
    assert issue.translation_key == "favorit_fehlt_person"
    assert issue.translation_placeholders == {
        "person": "Vater",
        "favorit": "SWR3",
        "raum": "Schlafzimmer",
    }
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert (
        "media_player",
        "select_source",
        {"entity_id": LAUTSPRECHER, "source": "YOU FM"},
    ) in aufrufe
    # Favorit wieder in der Liste → Hinweis weg
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": FAVORITEN})
    await hass.async_block_till_done()
    assert favorit_hinweis(hass, "p1") is None


async def test_fehlender_favorit_der_person_nimmt_den_standard_favoriten(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """E56: Fehlt der Favorit der Person, gilt zuerst der Standard-Favorit."""
    aufrufe = mitschreiben(hass)
    await aufbau(hass, freezer)
    await standard_favorit(hass, "hr3")
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": ["YOU FM", "hr3"]})
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert (
        "media_player",
        "select_source",
        {"entity_id": LAUTSPRECHER, "source": "hr3"},
    ) in aufrufe
    assert favorit_hinweis(hass, "p1") is not None
    assert favorit_hinweis(hass, "r1") is None


async def test_fehlender_standard_favorit_zeigt_hinweis_am_raum(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """E56: Auch der Standard-Favorit des Raums wird geprüft."""
    mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    await standard_favorit(hass, "YOU FM")
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": ["hr3", "SWR3"]})
    await hass.async_block_till_done()
    issue = favorit_hinweis(hass, "r1")
    assert issue is not None
    assert issue.translation_key == "favorit_fehlt_raum"
    assert issue.translation_placeholders == {
        "raum": "Schlafzimmer",
        "favorit": "YOU FM",
    }
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["hinweise"]["favorit_fehlt"] == ["r1"]
    # Anderen Standard-Favoriten wählen → Hinweis weg
    await standard_favorit(hass, "hr3")
    assert favorit_hinweis(hass, "r1") is None


async def test_leere_liste_zeigt_keinen_favoriten_hinweis(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ohne Liste (z. B. Lautsprecher startet neu) ist nichts zu prüfen."""
    mitschreiben(hass)
    await aufbau(hass, freezer)
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": []})
    await hass.async_block_till_done()
    assert favorit_hinweis(hass, "p1") is None


async def test_favoriten_hinweis_verschwindet_ohne_raum(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Wählt die Person „kein Raum“, gibt es keinen Lautsprecher zu prüfen."""
    mitschreiben(hass)
    await aufbau(hass, freezer)
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": ["hr3"]})
    await hass.async_block_till_done()
    assert favorit_hinweis(hass, "p1") is not None
    await waehle_raum(hass, "p1", "kein_raum")
    assert favorit_hinweis(hass, "p1") is None


async def test_kurz_weg_laesst_den_favoriten_hinweis_stehen(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Liste kurz weg (Neustart des Lautsprechers): Hinweis bleibt, keine Warnung."""
    mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": ["hr3"]})
    await hass.async_block_till_done()
    assert favorit_hinweis(hass, "p1") is not None
    caplog.clear()
    hass.states.async_set(LAUTSPRECHER, "unavailable")
    await hass.async_block_till_done()
    assert favorit_hinweis(hass, "p1") is not None
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": []})
    await entry.runtime_data.async_refresh()
    assert favorit_hinweis(hass, "p1") is not None
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": ["hr3"]})
    await hass.async_block_till_done()
    await entry.runtime_data.async_refresh()
    assert favorit_hinweis(hass, "p1") is not None
    assert "Favorit SWR3" not in caplog.text
    assert "erledigt" not in caplog.text


async def test_alter_favoriten_hinweis_wird_aufgeraeumt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ein Hinweis aus der Zeit vor dem Neustart, der nicht mehr gilt, verschwindet."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        "favorit_fehlt_weg",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="favorit_fehlt_raum",
    )
    mitschreiben(hass)
    await aufbau(hass, freezer)
    assert favorit_hinweis(hass, "weg") is None


async def test_favoriten_hinweis_erst_nach_dem_start(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Beim Booten wird nicht geprüft, direkt nach dem Start dann schon."""
    mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    assert await hass.config_entries.async_unload(entry.entry_id)
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": ["hr3"]})
    hass.set_state(CoreState.starting)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert favorit_hinweis(hass, "p1") is None
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert favorit_hinweis(hass, "p1") is not None


# ------------------------------------------- Lautsprecher ohne Favoritenliste (E58)


def ohne_liste_hinweis(hass: HomeAssistant, sid: str = "r1") -> ir.IssueEntry | None:
    """Hinweis „Lautsprecher ohne Favoritenliste“ eines Raums."""
    return ir.async_get(hass).async_get_issue(DOMAIN, f"lautsprecher_ohne_liste_{sid}")


async def test_ohne_liste_bis_zum_aufgeben_zeigt_hinweis(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """E58/E61: 15 min ohne Liste, Radio aufgegeben → Hinweis für den Raum."""
    mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    hass.states.async_set(LAUTSPRECHER, "idle")
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    await vorspulen(hass, freezer, tag(WINTER, "06:29:59"))
    assert ohne_liste_hinweis(hass) is None
    await vorspulen(hass, freezer, tag(WINTER, "06:30:00"))
    issue = ohne_liste_hinweis(hass)
    assert issue is not None
    assert issue.translation_key == "lautsprecher_ohne_liste"
    assert issue.translation_placeholders == {
        "raum": "Schlafzimmer",
        "lautsprecher": LAUTSPRECHER,
    }
    assert issue.config_entry_id == entry.entry_id
    # Entsteht nur beim Wecken, muss also einen HA-Neustart überstehen
    assert issue.is_persistent
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["hinweise"]["lautsprecher_ohne_liste"] == ["r1"]
    # Liste taucht auf → Hinweis weg
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": FAVORITEN})
    await hass.async_block_till_done()
    assert ohne_liste_hinweis(hass) is None


async def test_ohne_liste_bei_kurzer_dauer_hinweis_zum_aus_zeitpunkt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Dauer 2 min: Die Versuche enden zum Aus-Zeitpunkt, der Hinweis kommt dann."""
    mitschreiben(hass)
    await aufbau(hass, freezer, dauer=2)
    hass.states.async_set(LAUTSPRECHER, "idle")
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert ohne_liste_hinweis(hass) is None
    await vorspulen(hass, freezer, tag(WINTER, "06:17:00"))
    assert ohne_liste_hinweis(hass) is not None


async def test_nicht_verfuegbarer_lautsprecher_zeigt_keinen_ohne_liste_hinweis(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Nicht verfügbar ist ein anderer Grund: kein Hinweis E58."""
    mitschreiben(hass)
    await aufbau(hass, freezer)
    hass.states.async_set(LAUTSPRECHER, "unavailable")
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    await vorspulen(hass, freezer, tag(WINTER, "06:30:00"))
    assert ohne_liste_hinweis(hass) is None


async def test_druck_auf_die_taste_zeigt_keinen_ohne_liste_hinweis(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Wecken von Hand beendet, während auf die Liste gewartet wird: kein Hinweis."""
    mitschreiben(hass)
    await aufbau(hass, freezer)
    hass.states.async_set(LAUTSPRECHER, "idle")
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    freezer.move_to(tag(WINTER, "06:16:00"))
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_id(hass, "button", "r1", "wecken_beenden")},
        blocking=True,
    )
    await hass.async_block_till_done()
    await vorspulen(hass, freezer, tag(WINTER, "06:30:00"))
    await vorspulen(hass, freezer, tag(WINTER, "07:00:00"))
    assert ohne_liste_hinweis(hass) is None


async def test_ohne_liste_hinweis_bleibt_wenn_der_lautsprecher_kurz_weg_ist(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Lautsprecher nicht verfügbar: nichts entschieden, der Hinweis bleibt."""
    mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    hass.states.async_set(LAUTSPRECHER, "idle")
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    await vorspulen(hass, freezer, tag(WINTER, "06:30:00"))
    hass.states.async_set(LAUTSPRECHER, "unavailable")
    await hass.async_block_till_done()
    await entry.runtime_data.async_refresh()
    assert ohne_liste_hinweis(hass) is not None


async def test_ohne_liste_hinweis_verschwindet_ohne_lautsprecher(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Lautsprecher aus dem Raum entfernt → Hinweis weg."""
    mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    hass.states.async_set(LAUTSPRECHER, "idle")
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    await vorspulen(hass, freezer, tag(WINTER, "06:30:00"))
    assert ohne_liste_hinweis(hass) is not None
    sub = entry.subentries["r1"]
    hass.config_entries.async_update_subentry(
        entry, sub, data=dict(sub.data) | {"lautsprecher": None}
    )
    await hass.async_block_till_done()
    assert ohne_liste_hinweis(hass) is None


async def test_ohne_liste_hinweis_verschwindet_mit_dem_raum(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Raum gelöscht → Hinweis weg."""
    mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    hass.states.async_set(LAUTSPRECHER, "idle")
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    await vorspulen(hass, freezer, tag(WINTER, "06:30:00"))
    assert hass.config_entries.async_remove_subentry(entry, "r1")
    await hass.async_block_till_done()
    assert ohne_liste_hinweis(hass) is None


def alter_ohne_liste_hinweis(hass: HomeAssistant, sid: str, lautsprecher: str) -> None:
    """Hinweis E58 wie aus der Zeit vor einem Neustart."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"lautsprecher_ohne_liste_{sid}",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="lautsprecher_ohne_liste",
        translation_placeholders={"raum": "Alt", "lautsprecher": lautsprecher},
    )


async def test_alter_ohne_liste_hinweis_bleibt_solange_die_liste_fehlt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Nach dem Neustart: weiter keine Liste → Hinweis bleibt; Liste da → weg."""
    mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    assert await hass.config_entries.async_unload(entry.entry_id)
    alter_ohne_liste_hinweis(hass, "r1", LAUTSPRECHER)
    hass.states.async_set(LAUTSPRECHER, "idle")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert ohne_liste_hinweis(hass) is not None
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": FAVORITEN})
    await hass.async_block_till_done()
    assert ohne_liste_hinweis(hass) is None


async def test_alter_ohne_liste_hinweis_wird_aufgeraeumt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Gelöschter Raum oder anderer Lautsprecher: alter Hinweis verschwindet."""
    alter_ohne_liste_hinweis(hass, "weg", LAUTSPRECHER)
    alter_ohne_liste_hinweis(hass, "r1", "media_player.alt")
    hass.states.async_set(LAUTSPRECHER, "idle")
    mitschreiben(hass)
    await aufbau(hass, freezer)
    assert ohne_liste_hinweis(hass, "weg") is None
    assert ohne_liste_hinweis(hass) is None


async def test_ohne_liste_hinweis_ohne_text_bleibt_solange_die_liste_fehlt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ein Hinweis ohne Platzhalter (Rest von früher) zählt nur nach dem Raum."""
    mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    assert await hass.config_entries.async_unload(entry.entry_id)
    ir.async_create_issue(
        hass,
        DOMAIN,
        "lautsprecher_ohne_liste_r1",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="lautsprecher_ohne_liste",
    )
    hass.states.async_set(LAUTSPRECHER, "idle")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert ohne_liste_hinweis(hass) is not None


async def test_entladen_beim_warten_auf_die_liste_zeigt_keinen_hinweis(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Neuladen/Entladen beendet das Warten ohne Hinweis (E55 (5), E61)."""
    mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    hass.states.async_set(LAUTSPRECHER, "idle")
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert await hass.config_entries.async_unload(entry.entry_id)
    await vorspulen(hass, freezer, tag(WINTER, "06:30:00"))
    assert ohne_liste_hinweis(hass) is None


async def test_zuletzt_nicht_verfuegbar_zeigt_keinen_ohne_liste_hinweis(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Erst keine Liste, am Ende nicht verfügbar: der letzte Grund zählt."""
    mitschreiben(hass)
    await aufbau(hass, freezer)
    hass.states.async_set(LAUTSPRECHER, "idle")
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    hass.states.async_set(LAUTSPRECHER, "unavailable")
    await vorspulen(hass, freezer, tag(WINTER, "06:20:00"))
    await vorspulen(hass, freezer, tag(WINTER, "06:30:00"))
    assert ohne_liste_hinweis(hass) is None


async def test_liste_kommt_noch_rechtzeitig_kein_ohne_liste_hinweis(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Die Liste kommt kurz vor Schluss, das Radio spielt: kein Hinweis."""
    aufrufe = mitschreiben(hass)
    await aufbau(hass, freezer)
    hass.states.async_set(LAUTSPRECHER, "idle")
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    freezer.move_to(tag(WINTER, "06:29:50"))
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": FAVORITEN})
    await hass.async_block_till_done()
    await vorspulen(hass, freezer, tag(WINTER, "06:30:00"))
    assert "media_player.media_play" in namen(aufrufe)
    assert ohne_liste_hinweis(hass) is None
