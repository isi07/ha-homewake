"""Tests für Feiertage: Dialog Land/Bundesland und Wirkung (3.5, E9, E13)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.homewake import feiertage
from custom_components.homewake.const import DOMAIN
from tests.test_person_sensoren import entity_id, person, zustand
from tests.test_raum_sensoren import raum, waehle_raum


async def feiertags_haus(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    jetzt: str,
    *untereintraege: Any,
    land: str | None = "DE",
    bundesland: str | None = "HE",
) -> MockConfigEntry:
    """HomeWake mit Land/Bundesland, deutsche HA-Sprache, Berliner Zeit."""
    hass.config.language = "de"
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to(jetzt)
    daten = {} if land is None else {"land": land, "bundesland": bundesland}
    entry = MockConfigEntry(
        domain=DOMAIN, title="HomeWake", data=daten, subentries_data=untereintraege
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


# ---------------------------------------------------------------- Dialog


async def test_einrichten_fragt_land_und_bundesland(hass: HomeAssistant) -> None:
    """Einrichten: Land (vorbelegt aus HA), dann Bundesland; beides wird gespeichert."""
    hass.config.country = "DE"
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"land": "DE"}
    )
    assert result["step_id"] == "region"
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


async def test_land_ohne_regionen_braucht_keinen_zweiten_schritt(
    hass: HomeAssistant,
) -> None:
    """Hat ein Land keine Regionen, wird direkt gespeichert."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"land": "IS"}
    )
    assert result["step_id"] == "sonne"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["bundesland"] is None


async def test_bundesland_ist_optional(hass: HomeAssistant) -> None:
    """Ohne Bundesland gelten nur die landesweiten Feiertage."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"land": "DE"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["data"]["bundesland"] is None


async def test_land_und_bundesland_aendern(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Im Ändern-Dialog lassen sich Land und Bundesland anpassen."""
    entry = await feiertags_haus(hass, freezer, "2026-07-14 04:00:00+02:00")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"land": "DE"}
    )
    assert result["step_id"] == "region"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"bundesland": "BY"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["land"] == "DE"
    assert entry.data["bundesland"] == "BY"


# ---------------------------------------------------------------- Wirkung


async def test_feiertag_im_bundesland_gilt_fuer_personen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Fronleichnam (Hessen): Status Feiertag mit Namen, Standard-Zeile 08:00."""
    await feiertags_haus(
        hass,
        freezer,
        "2026-06-04 04:00:00+02:00",
        person("p1", "Vater"),
        raum("r1", "Schlafzimmer"),
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    assert zustand(hass, "sensor", "p1", "status") == "feiertag"
    state = hass.states.get(entity_id(hass, "sensor", "p1", "status"))
    assert state is not None
    assert state.attributes["grund"] == "Fronleichnam"
    assert (
        zustand(hass, "sensor", "p1", "naechster_wecker") == "2026-06-04T06:00:00+00:00"
    )


async def test_feiertag_gilt_fuer_raum_standardplan(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Raum ohne Personen: am Feiertag die Standard-Zeile (07:00, E13)."""
    await feiertags_haus(hass, freezer, "2026-06-04 04:00:00+02:00", raum("r1", "Flur"))
    assert zustand(hass, "sensor", "r1", "weckzeit") == "2026-06-04T05:00:00+00:00"


async def test_ohne_bundesland_kein_regionaler_feiertag(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ohne Bundesland ist Fronleichnam kein Feiertag."""
    await feiertags_haus(
        hass,
        freezer,
        "2026-06-04 04:00:00+02:00",
        person("p1", "Vater"),
        raum("r1", "Schlafzimmer"),
        bundesland=None,
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    assert zustand(hass, "sensor", "p1", "status") == "werktag"


async def test_feiertag_morgen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Am Vorabend des 1. Mai: nächster Wecker morgen zur Standard-Zeile."""
    await feiertags_haus(
        hass,
        freezer,
        "2026-04-30 23:00:00+02:00",
        person("p1", "Vater"),
        raum("r1", "Schlafzimmer"),
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    assert zustand(hass, "sensor", "p1", "status") == "feiertag"
    assert (
        zustand(hass, "sensor", "p1", "naechster_wecker") == "2026-05-01T06:00:00+00:00"
    )
    assert (
        zustand(hass, "sensor", "r1", "weckzeit_morgen") == "2026-05-01T06:00:00+00:00"
    )


async def test_alter_eintrag_ohne_land_nutzt_ha_land(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ein Eintrag ohne Land (aus Phase 1) nimmt das Land der HA-Einstellungen."""
    hass.config.country = "DE"
    await feiertags_haus(
        hass,
        freezer,
        "2026-05-01 04:00:00+02:00",
        person("p1", "Vater"),
        raum("r1", "Schlafzimmer"),
        land=None,
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    assert zustand(hass, "sensor", "p1", "status") == "feiertag"


# ---------------------------------------------------------------- Review-Ergänzungen


async def test_unbekannte_region_weckt_weiter_mit_hinweis(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Unbekannte Region: kein Absturz, keine Feiertage, Reparatur-Hinweis (E37)."""
    entry = await feiertags_haus(
        hass,
        freezer,
        "2026-05-01 04:00:00+02:00",
        person("p1", "Vater"),
        raum("r1", "Schlafzimmer"),
        bundesland="XX",
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    assert zustand(hass, "sensor", "p1", "status") == "werktag"
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "feiertage_nicht_verfuegbar")
    assert issue is not None
    assert issue.config_entry_id == entry.entry_id


async def test_hinweis_verschwindet_nach_korrektur(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Wird die Region korrigiert, verschwindet der Hinweis und Feiertage gelten."""
    entry = await feiertags_haus(
        hass,
        freezer,
        "2026-06-04 04:00:00+02:00",
        person("p1", "Vater"),
        raum("r1", "Schlafzimmer"),
        bundesland="XX",
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    hass.config_entries.async_update_entry(
        entry, data={"land": "DE", "bundesland": "HE"}
    )
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, "feiertage_nicht_verfuegbar") is None
    )
    assert zustand(hass, "sensor", "p1", "status") == "feiertag"


async def test_aendern_wirkt_sofort(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """31.10.: von Hessen auf Niedersachsen → Reformationstag wird Feiertag."""
    entry = await feiertags_haus(
        hass,
        freezer,
        "2026-10-31 04:00:00+01:00",
        person("p1", "Vater"),
        raum("r1", "Schlafzimmer"),
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    assert zustand(hass, "sensor", "p1", "status") == "wochenende"
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"land": "DE"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"bundesland": "NI"}
    )
    await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert zustand(hass, "sensor", "p1", "status") == "feiertag"


async def test_landwechsel_schlaegt_alte_region_nicht_vor(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Wechsel von DE/HE nach AT: die alte Region wird nicht vorbelegt."""
    entry = await feiertags_haus(hass, freezer, "2026-07-14 04:00:00+02:00")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"land": "AT"}
    )
    assert result["step_id"] == "region"
    schema = result["data_schema"]
    assert schema is not None
    feld = next(k for k in schema.schema if str(k) == "bundesland")
    assert not (feld.description or {}).get("suggested_value")


async def test_landwechsel_ohne_regionen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Wechsel auf ein Land ohne Regionen: direkt gespeichert, Region leer."""
    entry = await feiertags_haus(hass, freezer, "2026-07-14 04:00:00+02:00")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"land": "IS"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["land"] == "IS"
    assert entry.data["bundesland"] is None


async def test_jahreswechsel_neujahr_ist_morgen_feiertag(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """31.12. abends: Neujahr (anderes Jahr) gilt morgen als Feiertag."""
    await feiertags_haus(
        hass,
        freezer,
        "2026-12-31 23:00:00+01:00",
        person("p1", "Vater"),
        raum("r1", "Schlafzimmer"),
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    assert zustand(hass, "sensor", "p1", "status") == "feiertag"
    assert (
        zustand(hass, "sensor", "p1", "naechster_wecker") == "2027-01-01T07:00:00+00:00"
    )


async def test_lauf_laedt_keine_feiertage_nach(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Das nächste Jahr wird vorab geladen; ein Lauf wartet nie darauf (E45).

    Am 30.12. ist das neue Jahr noch nicht „morgen“. Trotzdem kennt HomeWake
    Neujahr, ohne die Bibliothek im Lauf noch einmal zu fragen.
    """
    await feiertags_haus(
        hass,
        freezer,
        "2026-12-30 04:00:00+01:00",
        person("p1", "Vater"),
        raum("r1", "Schlafzimmer"),
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    with patch.object(feiertage, "feiertage", side_effect=AssertionError("im Lauf")):
        for zeitpunkt in ("2026-12-31 04:09:00+01:00", "2027-01-01 04:09:00+01:00"):
            freezer.move_to(zeitpunkt)
            async_fire_time_changed(hass)
            await hass.async_block_till_done(wait_background_tasks=True)
    assert zustand(hass, "sensor", "p1", "status") == "feiertag"


async def test_unbekannte_region_wird_nur_einmal_versucht(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Kennt die Bibliothek die Region nicht, fragt nicht jeder Lauf erneut."""
    with patch.object(feiertage, "feiertage", wraps=feiertage.feiertage) as abfrage:
        await feiertags_haus(
            hass,
            freezer,
            "2026-05-01 04:00:00+02:00",
            person("p1", "Vater"),
            raum("r1", "Schlafzimmer"),
            bundesland="XX",
        )
        anzahl = abfrage.call_count
        for zeitpunkt in ("2026-05-01 04:09:00+02:00", "2026-05-01 04:19:00+02:00"):
            freezer.move_to(zeitpunkt)
            async_fire_time_changed(hass)
            await hass.async_block_till_done(wait_background_tasks=True)
    assert anzahl >= 1
    assert abfrage.call_count == anzahl


async def test_unerwarteter_fehler_beim_nachladen(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Wirft die Bibliothek beim Nachladen Unerwartetes: Traceback, weiter rechnen."""
    entry = await feiertags_haus(
        hass,
        freezer,
        "2026-10-31 04:00:00+01:00",
        person("p1", "Vater"),
        raum("r1", "Schlafzimmer"),
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    with patch.object(feiertage, "feiertage", side_effect=RuntimeError("kaputt")):
        hass.config_entries.async_update_entry(
            entry, data={"land": "DE", "bundesland": "NI"}
        )
        await hass.async_block_till_done(wait_background_tasks=True)
    assert any(
        "Unerwarteter Fehler" in r.getMessage() and r.exc_info for r in caplog.records
    )
    assert zustand(hass, "sensor", "p1", "status") == "wochenende"


async def test_ohne_land_und_ohne_ha_land_keine_feiertage(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Weder Land im Eintrag noch in HA: keine Feiertage, kein Fehler."""
    hass.config.country = None
    await feiertags_haus(
        hass,
        freezer,
        "2026-05-01 04:00:00+02:00",
        person("p1", "Vater"),
        raum("r1", "Schlafzimmer"),
        land=None,
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    assert zustand(hass, "sensor", "p1", "status") == "werktag"


async def test_einrichten_ohne_ha_land_ohne_vorbelegung(hass: HomeAssistant) -> None:
    """Ohne Land in den HA-Einstellungen ist das Land nicht vorbelegt."""
    hass.config.country = None
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    schema = result["data_schema"]
    assert schema is not None
    feld = next(k for k in schema.schema if str(k) == "land")
    assert not (feld.description or {}).get("suggested_value")


@pytest.mark.parametrize(
    ("sprache", "erwartet"),
    [
        ("de", "Fronleichnam"),
        ("en", "Corpus Christi"),
        ("en-GB", "Corpus Christi"),
        ("ja", "Fronleichnam"),
    ],
)
def test_sprache_der_feiertagsnamen(sprache: str, erwartet: str) -> None:
    """Namen in der HA-Sprache; Varianten und Unbekanntes fallen sinnvoll zurück."""
    namen = feiertage.feiertage("DE", "HE", 2026, sprache)
    assert namen[date(2026, 6, 4)] == erwartet
