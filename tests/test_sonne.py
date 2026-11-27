"""Tests für den Sonnenstand: Dialog und Klemmung der Räume (3.5, 4.6, E30)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.homewake.const import DOMAIN
from custom_components.homewake.logic.sonnenstand import SONNENSTAENDE
from custom_components.homewake.sonne import sonnenhoehe
from tests.test_person_sensoren import entity_id
from tests.test_raum_sensoren import raum

# Frankfurt am Main, Römer (Hessen)
BREITE, LAENGE = 50.1106, 8.6821


async def haus(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    jetzt: str,
    daten: dict[str, Any],
    breite: float = BREITE,
) -> MockConfigEntry:
    """HomeWake mit Raum „Flur“ (Standardplan Mo-Fr 06:00-22:15) und Sonnendaten."""
    hass.config.latitude, hass.config.longitude, hass.config.elevation = (
        breite,
        LAENGE,
        100,
    )
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to(jetzt)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="HomeWake",
        data={"land": "DE", "bundesland": "HE"} | daten,
        subentries_data=[raum("r1", "Flur")],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def zeit(hass: HomeAssistant, schluessel: str) -> datetime:
    """Zeitpunkt eines Raum-Sensors."""
    state = hass.states.get(entity_id(hass, "sensor", "r1", schluessel))
    assert state is not None
    return datetime.fromisoformat(state.state)


def ortszeit(text: str) -> datetime:
    """Berliner Ortszeit als Zeitpunkt."""
    return datetime.fromisoformat(text)


# ---------------------------------------------------------------- Dialog


async def test_einrichten_mit_sonnenstand(hass: HomeAssistant) -> None:
    """Nach Land/Region folgt der Sonnenstand; ohne Eingabe gilt -6° (bürgerlich)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"land": "DE"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"bundesland": "HE"}
    )
    assert result["step_id"] == "sonne"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "land": "DE",
        "bundesland": "HE",
        "sonne_morgen": "buergerlich",
        "grad_morgen": None,
        "sonne_abend": "buergerlich",
        "grad_abend": None,
    }


async def test_frei_gewaehlte_gradzahl_wird_gespeichert(hass: HomeAssistant) -> None:
    """Bei „frei wählen“ wird die Gradzahl gespeichert, sonst nicht."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"land": "IS"}
    )
    assert result["step_id"] == "sonne"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "sonne_morgen": "frei",
            "grad_morgen": -9.5,
            "sonne_abend": "nautisch",
            "grad_abend": 3,
        },
    )
    assert result["data"]["sonne_morgen"] == "frei"
    assert result["data"]["grad_morgen"] == -9.5
    assert result["data"]["sonne_abend"] == "nautisch"
    assert result["data"]["grad_abend"] is None


async def test_aendern_mit_sonnenstand(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Im Ändern-Dialog ist der Sonnenstand vorbelegt und änderbar."""
    entry = await haus(hass, freezer, "2026-07-14 04:00:00+02:00", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"land": "DE"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"bundesland": "HE"}
    )
    assert result["step_id"] == "sonne"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"sonne_morgen": "horizont", "sonne_abend": "buergerlich"}
    )
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["sonne_morgen"] == "horizont"


# ---------------------------------------------------------------- Klemmung


async def test_winter_tagesbeginn_an_fensterende_gedeckelt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Dezember: Dämmerung nach 07:00 → Tagesbeginn 07:00 (Weckzeit 06:00 + 60 min)."""
    await haus(hass, freezer, "2026-12-15 04:00:00+01:00", {})
    assert zeit(hass, "weckzeit") == ortszeit("2026-12-15T06:00:00+01:00")
    assert zeit(hass, "tagesbeginn") == ortszeit("2026-12-15T07:00:00+01:00")
    # Abenddämmerung ~17:00 → Tagesende auf Fensterstart 21:15 vorgezogen
    assert zeit(hass, "tagesende") == ortszeit("2026-12-15T21:15:00+01:00")


async def test_sommer_tagesbeginn_bleibt_weckzeit(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ende Juli: Dämmerung vor 06:00 → Tagesbeginn = Weckzeit; Ende an Dämmerung.

    Frankfurt am 28.07.2026 (Dienstag): bürgerliche Dämmerung ~05:05 und ~21:57.
    """
    await haus(hass, freezer, "2026-07-28 04:00:00+02:00", {})
    assert zeit(hass, "tagesbeginn") == ortszeit("2026-07-28T06:00:00+02:00")
    ende = zeit(hass, "tagesende")
    assert (
        ortszeit("2026-07-28T21:50:00+02:00")
        < ende
        < ortszeit("2026-07-28T22:05:00+02:00")
    )


async def test_morgen_wird_mit_sonne_von_morgen_geklemmt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Auch die Sensoren für morgen werden an die Dämmerung von morgen geklemmt."""
    await haus(hass, freezer, "2026-12-15 04:00:00+01:00", {})
    assert zeit(hass, "tagesbeginn_morgen") == ortszeit("2026-12-16T07:00:00+01:00")


async def test_goldene_stunde_morgens_ist_spaeter_als_buergerlich(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Juli, Weckzeit 06:00: +6° liegt im Fenster, nach der bürgerlichen Dämmerung."""
    await haus(
        hass, freezer, "2026-07-14 04:00:00+02:00", {"sonne_morgen": "goldene_stunde"}
    )
    beginn = zeit(hass, "tagesbeginn")
    assert (
        ortszeit("2026-07-14T06:00:00+02:00")
        < beginn
        <= ortszeit("2026-07-14T07:00:00+02:00")
    )


async def test_ohne_daemmerung_wird_nicht_geklemmt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Polarnacht (78° Nord): keine Dämmerung → ungeklemmt (E25), kein Fehler."""
    await haus(hass, freezer, "2026-12-15 04:00:00+01:00", {}, breite=78.0)
    assert zeit(hass, "tagesbeginn") == ortszeit("2026-12-15T06:00:00+01:00")
    assert zeit(hass, "tagesende") == ortszeit("2026-12-15T22:15:00+01:00")


# ---------------------------------------------------------------- Review-Ergänzungen


async def test_frei_ohne_gradzahl_ist_ein_fehler(hass: HomeAssistant) -> None:
    """Bei „frei wählen“ ist die Gradzahl Pflicht (sichtbares Pflichtfeld)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"land": "IS"}
    )
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {"sonne_morgen": "frei"}
        )


async def test_aendern_belegt_freie_gradzahl_vor_und_verwirft_sie(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ändern: „frei -9,5“ ist vorbelegt; Wechsel auf „nautisch“ verwirft die Zahl."""
    entry = await haus(
        hass,
        freezer,
        "2026-07-14 04:00:00+02:00",
        {"sonne_morgen": "frei", "grad_morgen": -9.5},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"land": "DE"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"bundesland": "HE"}
    )
    schema = result["data_schema"]
    assert schema is not None
    vorschlag = {
        str(k): (k.description or {}).get("suggested_value") for k in schema.schema
    }
    assert vorschlag["sonne_morgen"] == "frei"
    assert vorschlag["grad_morgen"] == -9.5
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {"sonne_morgen": "nautisch"}
    )
    assert entry.data["sonne_morgen"] == "nautisch"
    assert entry.data["grad_morgen"] is None


async def test_freie_gradzahl_abends_wie_benannter_stand(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Frei -12° am Abend ergibt dasselbe Tagesende wie „nautisch“."""
    await haus(
        hass,
        freezer,
        "2026-07-14 04:00:00+02:00",
        {"sonne_abend": "frei", "grad_abend": -12.0},
    )
    frei = zeit(hass, "tagesende")
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    hass.config_entries.async_update_entry(
        entry, data=dict(entry.data) | {"sonne_abend": "nautisch", "grad_abend": None}
    )
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert zeit(hass, "tagesende") == frei


async def test_daemmerung_am_tag_der_zeitumstellung(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Erster Werktag nach der Zeitumstellung: Dämmerung in Sommerzeit (~06:31)."""
    await haus(hass, freezer, "2026-03-30 04:00:00+02:00", {})
    beginn = zeit(hass, "tagesbeginn")
    assert (
        ortszeit("2026-03-30T06:20:00+02:00")
        < beginn
        < ortszeit("2026-03-30T07:00:00+02:00")
    )


def test_sonnenaufgang_entspricht_astral() -> None:
    """„Sonnenaufgang“ liegt höchstens 1 min neben astral.sunrise."""
    from astral import Observer  # noqa: PLC0415
    from astral.sun import SunDirection, sunrise, time_at_elevation  # noqa: PLC0415

    beobachter = Observer(BREITE, LAENGE, 0)
    tag = date(2026, 7, 14)
    berechnet = time_at_elevation(
        beobachter, SONNENSTAENDE["sonnenaufgang"], tag, SunDirection.RISING
    )
    assert abs((berechnet - sunrise(beobachter, tag)).total_seconds()) <= 60


async def test_sonnenhoehe_mittags_positiv_nachts_negativ(hass: HomeAssistant) -> None:
    """Sonnenhöhe (E51): im Juni mittags weit oben, um Mitternacht darunter."""
    hass.config.latitude, hass.config.longitude = 50.1106, 8.6821  # Frankfurt am Main
    berlin = ZoneInfo("Europe/Berlin")
    assert sonnenhoehe(hass, datetime(2026, 6, 21, 13, 30, tzinfo=berlin)) > 60
    assert sonnenhoehe(hass, datetime(2026, 6, 21, 1, 30, tzinfo=berlin)) < -10
