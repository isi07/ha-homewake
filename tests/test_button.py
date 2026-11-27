"""Tests für die Taste „Wecken beenden“ pro Raum (ARCHITEKTUR.md 3.7, E53, E60).

Ein Druck zieht den Aus-Zeitpunkt auf jetzt vor: laufende Einschalt-Versuche
enden, ausgeschaltet wird nach E50/E54 (nur, was noch so ist), der Aus-Auftrag
ist danach weg. Ohne laufendes Wecken passiert nichts.
"""

from __future__ import annotations

import asyncio

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.homewake.const import DOMAIN
from custom_components.homewake.diagnostics import (
    async_get_config_entry_diagnostics,
)
from tests.test_hinweise import daten_aendern
from tests.test_person_sensoren import einrichten, entity_id, vorspulen
from tests.test_raum_sensoren import raum
from tests.test_schalten import (
    FAVORITEN,
    LAUTSPRECHER,
    LICHT,
    WINTER,
    aufbau,
    mitschreiben,
    namen,
    tag,
)


async def druecken(hass: HomeAssistant, sid: str = "r1") -> None:
    """Taste „Wecken beenden“ eines Raums drücken, wie es eine Automation tut."""
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_id(hass, "button", sid, "wecken_beenden")},
        blocking=True,
    )
    await hass.async_block_till_done()


def taste(hass: HomeAssistant, sid: str) -> str | None:
    """Entity-ID der Taste eines Raums oder None."""
    return er.async_get(hass).async_get_entity_id(
        "button", DOMAIN, f"{sid}_wecken_beenden"
    )


async def aus_auftraege(hass: HomeAssistant, entry: MockConfigEntry) -> list[str]:
    """Räume mit offenem Aus-Auftrag laut Diagnose."""
    diag = await async_get_config_entry_diagnostics(hass, entry)
    return list(diag["schalten"]["aus_auftraege"])


# ---------------------------------------------------------------- Anlegen


async def test_taste_nur_bei_raum_mit_aktorik(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Nur Räume mit Lichtern oder Lautsprecher bekommen die Taste, am Raum-Gerät."""
    hass.states.async_set(LICHT, "off")
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": FAVORITEN})
    entry = await einrichten(
        hass,
        freezer,
        raum("r1", "Schlafzimmer", lichter=[LICHT]),
        raum("r2", "Bad", lautsprecher=LAUTSPRECHER),
        raum("r3", "Flur"),
    )
    assert taste(hass, "r3") is None
    ent_reg = er.async_get(hass)
    for sid in ("r1", "r2"):
        eid = taste(hass, sid)
        assert eid is not None
        eintrag = ent_reg.async_get(eid)
        assert eintrag is not None
        assert eintrag.translation_key == "wecken_beenden"
        assert eintrag.config_subentry_id == sid
        geraet = dr.async_get(hass).async_get_device_by_identifier(
            (DOMAIN, sid), entry.entry_id
        )
        assert geraet is not None
        assert eintrag.device_id == geraet.id
        assert geraet.model == "Raum"


async def test_taste_kommt_und_geht_mit_der_aktorik(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Erstes Licht eingetragen → Taste da; alles entfernt → Taste weg (5.4)."""
    hass.states.async_set(LICHT, "off")
    entry = await einrichten(hass, freezer, raum("r1", "Flur"))
    assert taste(hass, "r1") is None
    daten_aendern(hass, entry, "r1", lichter=[LICHT])
    await hass.async_block_till_done()
    assert taste(hass, "r1") is not None
    daten_aendern(hass, entry, "r1", lichter=[])
    await hass.async_block_till_done()
    assert taste(hass, "r1") is None


async def test_taste_auch_bei_kaputtem_zeitplan_verfuegbar(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ausschalten soll immer gehen, auch wenn der Raum nicht berechnet wird."""
    mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    daten_aendern(hass, entry, "r1", zeitplan={})
    await hass.async_block_till_done()
    state = hass.states.get(entity_id(hass, "button", "r1", "wecken_beenden"))
    assert state is not None
    assert state.state != "unavailable"


# ---------------------------------------------------------------- Drücken


async def test_druck_schaltet_sofort_aus_und_loescht_den_auftrag(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Licht aus, Radio stopp; nach der Dauer passiert nichts mehr."""
    aufrufe = mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert await aus_auftraege(hass, entry) == ["r1"]
    aufrufe.clear()
    freezer.move_to(tag(WINTER, "06:20:00"))
    await druecken(hass)
    assert aufrufe == [
        ("light", "turn_off", {"entity_id": LICHT}),
        ("media_player", "media_stop", {"entity_id": LAUTSPRECHER}),
    ]
    await hass.async_block_till_done(wait_background_tasks=True)
    assert await aus_auftraege(hass, entry) == []
    aufrufe.clear()
    await vorspulen(hass, freezer, tag(WINTER, "07:00:00"))
    assert aufrufe == []


async def test_druck_laesst_vom_menschen_geaendertes_stehen(
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
    await druecken(hass)
    assert aufrufe == []


async def test_druck_beendet_laufende_versuche(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Licht wartet auf einen neuen Versuch: nach dem Druck geht es nicht mehr an."""
    aufrufe = mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    hass.states.async_set(LICHT, "unavailable")
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    freezer.move_to(tag(WINTER, "06:16:00"))
    await druecken(hass)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["schalten"]["wiederholungen"] == {}
    aufrufe.clear()
    hass.states.async_set(LICHT, "off")
    await hass.async_block_till_done()
    await vorspulen(hass, freezer, tag(WINTER, "06:17:00"))
    assert "light.turn_on" not in namen(aufrufe)


async def test_druck_ohne_wecken_tut_nichts(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Kein laufendes Wecken: kein Aufruf, kein Fehler; das Wecken kommt trotzdem."""
    aufrufe = mitschreiben(hass)
    await aufbau(hass, freezer)
    await druecken(hass)
    assert aufrufe == []
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert "light.turn_on" in namen(aufrufe)


async def test_druck_nach_dem_ausschalten_tut_nichts(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Zweiter Druck: der Auftrag ist schon weg, also passiert nichts."""
    aufrufe = mitschreiben(hass)
    await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    await druecken(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    aufrufe.clear()
    hass.states.async_set(LICHT, "on")
    await druecken(hass)
    assert aufrufe == []


async def test_nicht_erreichbares_geraet_wird_beim_druck_weiter_versucht(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """E55 (4): Licht beim Druck weg → ausschalten, sobald es wieder da ist."""
    aufrufe = mitschreiben(hass)
    await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    hass.states.async_set(LICHT, "unavailable")
    aufrufe.clear()
    freezer.move_to(tag(WINTER, "06:20:00"))
    await druecken(hass)
    assert namen(aufrufe) == ["media_player.media_stop"]
    freezer.move_to(tag(WINTER, "06:21:00"))
    hass.states.async_set(LICHT, "on")
    await hass.async_block_till_done()
    assert namen(aufrufe) == ["media_player.media_stop", "light.turn_off"]


async def test_druck_uebersteht_neuladen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Nach dem Druck ist der Auftrag auch im Speicher weg: Neuladen schaltet nicht."""
    aufrufe = mitschreiben(hass)
    entry = await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    await druecken(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    hass.states.async_set(LICHT, "on")
    aufrufe.clear()
    await vorspulen(hass, freezer, tag(WINTER, "07:00:00"))
    assert aufrufe == []


async def test_druck_waehrend_des_ausschaltens_aendert_nichts(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Wird schon ausgeschaltet (Gerät weg), verlängert ein Druck die Versuche nicht."""
    aufrufe = mitschreiben(hass)
    await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    hass.states.async_set(LICHT, "unavailable")
    await vorspulen(hass, freezer, tag(WINTER, "07:00:00"))
    freezer.move_to(tag(WINTER, "07:10:00"))
    await druecken(hass)
    await vorspulen(hass, freezer, tag(WINTER, "07:15:00"))
    await hass.async_block_till_done(wait_background_tasks=True)
    aufrufe.clear()
    hass.states.async_set(LICHT, "on")
    await hass.async_block_till_done()
    await vorspulen(hass, freezer, tag(WINTER, "07:16:00"))
    assert aufrufe == []


async def test_druck_waehrend_ein_schaltbefehl_unterwegs_ist(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Druck, während die Quelle gewählt wird: Lautsprecher trotzdem stoppen.

    Der abgebrochene Befehl kann das Gerät noch erreichen, auch wenn sein
    Zustand in HA noch nicht „spielt“ zeigt (Review B1).
    """
    aufrufe = mitschreiben(hass)
    nie = asyncio.Event()

    async def haengt(call: ServiceCall) -> None:
        aufrufe.append((call.domain, call.service, dict(call.data)))
        await nie.wait()

    hass.services.async_register("media_player", "select_source", haengt)
    await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    assert namen(aufrufe)[-1] == "media_player.select_source"
    aufrufe.clear()
    await druecken(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert namen(aufrufe) == ["light.turn_off", "media_player.media_stop"]
