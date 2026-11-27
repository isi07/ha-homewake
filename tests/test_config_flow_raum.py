"""Tests für den Dialog „Raum hinzufügen/ändern“ (Untereintrag, 3.7, E35)."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigSubentryDataWithId, SubentryFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.homewake.const import DOMAIN, SUBENTRY_RAUM

STANDARD = {"beginn": "07:00:00", "ende": "22:30:00"}
PLAN = {
    "standard": STANDARD,
    "montag": {},
    "dienstag": {},
    "mittwoch": {},
    "donnerstag": {},
    "freitag": {},
    "samstag": {},
    "sonntag": {},
}


def haus(hass: HomeAssistant, *raeume: ConfigSubentryDataWithId) -> MockConfigEntry:
    """HomeWake-Haupteintrag mit optionalen Räumen."""
    entry = MockConfigEntry(domain=DOMAIN, title="HomeWake", subentries_data=raeume)
    entry.add_to_hass(hass)
    return entry


def raum(titel: str, sid: str, **daten: Any) -> ConfigSubentryDataWithId:
    """Daten eines Raum-Untereintrags."""
    return ConfigSubentryDataWithId(
        data={"bereich": None, "zeitplan": PLAN} | daten,
        subentry_type=SUBENTRY_RAUM,
        title=titel,
        unique_id=None,
        subentry_id=sid,
    )


def bereich_mit_geraeten(hass: HomeAssistant, name: str = "OG Schlafzimmer") -> str:
    """Legt einen Bereich mit zwei Lichtern und einem Lautsprecher an."""
    area = ar.async_get(hass).async_create(name)
    ent_reg = er.async_get(hass)
    for domain, uid in (
        ("light", "decke"),
        ("light", "nachttisch"),
        ("media_player", "sonos"),
        ("switch", "steckdose"),
    ):
        eintrag = ent_reg.async_get_or_create(domain, "test", uid)
        ent_reg.async_update_entity(eintrag.entity_id, area_id=area.id)
    return area.id


def vorschlag(result: SubentryFlowResult, feld: str) -> Any:
    """Vorbelegter Wert (suggested_value) eines Formularfelds."""
    for key in result["data_schema"].schema:  # type: ignore[union-attr]
        if str(key) == feld:
            return (key.description or {}).get("suggested_value")
    msg = f"Feld {feld} fehlt"
    raise AssertionError(msg)


async def starte(hass: HomeAssistant, entry: MockConfigEntry) -> SubentryFlowResult:
    """Startet den Dialog „Raum hinzufügen“."""
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_RAUM), context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def test_raum_aus_bereich_schlaegt_geraete_vor(hass: HomeAssistant) -> None:
    """Bereich wählen: Name, Lichter und Lautsprecher werden vorgeschlagen (E35)."""
    area_id = bereich_mit_geraeten(hass)
    result = await starte(hass, haus(hass))
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"bereich": area_id}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "einstellungen"
    assert sorted(vorschlag(result, "lichter")) == [
        "light.test_decke",
        "light.test_nachttisch",
    ]
    assert vorschlag(result, "lautsprecher") == "media_player.test_sonos"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "standard": STANDARD,
            "lichter": ["light.test_decke"],
            "lautsprecher": "media_player.test_sonos",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "OG Schlafzimmer"
    daten = result["data"]
    assert daten["bereich"] == area_id
    assert daten["zeitplan"] == PLAN
    assert daten["lichter"] == ["light.test_decke"]
    assert daten["lautsprecher"] == "media_player.test_sonos"
    assert daten["zuordenbar"] is True
    assert (daten["klemm_beginn"], daten["klemm_ende"]) == (60, 60)
    assert (daten["helligkeit"], daten["lautstaerke"], daten["dauer"]) == (100, 30, 45)


async def test_raum_ohne_bereich_mit_eigenem_namen(hass: HomeAssistant) -> None:
    """Ohne Bereich genügt ein Name; ohne Geräte gibt es keine Vorschläge."""
    result = await starte(hass, haus(hass))
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Gästezimmer"}
    )
    assert result["step_id"] == "einstellungen"
    assert not vorschlag(result, "lichter")
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"standard": STANDARD, "zuordenbar": False}
    )
    assert result["title"] == "Gästezimmer"
    assert result["data"]["bereich"] is None
    assert result["data"]["zuordenbar"] is False
    assert result["data"]["lichter"] == []
    assert result["data"]["lautsprecher"] is None


async def test_weder_bereich_noch_name_ist_ein_fehler(hass: HomeAssistant) -> None:
    """Ohne Bereich und ohne Namen geht es nicht weiter."""
    result = await starte(hass, haus(hass))
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "name_oder_bereich"}


async def test_bereich_nur_einmal(hass: HomeAssistant) -> None:
    """Ein Bereich, der schon ein HomeWake-Raum ist, wird abgelehnt (E35)."""
    area_id = bereich_mit_geraeten(hass)
    entry = haus(hass, raum("OG Schlafzimmer", "r1", bereich=area_id))
    result = await starte(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"bereich": area_id, "name": "Anders"}
    )
    assert result["errors"] == {"bereich": "bereich_vergeben"}


async def test_raumname_nur_einmal(hass: HomeAssistant) -> None:
    """Zwei Räume dürfen nicht gleich heißen."""
    entry = haus(hass, raum("Küche", "r1"))
    result = await starte(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "küche"}
    )
    assert result["errors"] == {"name": "name_vergeben"}


async def test_fehler_im_standardplan(hass: HomeAssistant) -> None:
    """Der Standardplan des Raums wird wie bei Personen geprüft."""
    result = await starte(hass, haus(hass))
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Bad"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"standard": {"beginn": "22:00:00", "ende": "07:00:00"}}
    )
    assert result["step_id"] == "einstellungen"
    assert result["errors"] == {"standard": "ende_vor_beginn"}


async def test_raum_aendern(hass: HomeAssistant) -> None:
    """Im Ändern-Dialog lassen sich Name und Einstellungen anpassen."""
    entry = haus(
        hass,
        raum(
            "Bad",
            "r1",
            zuordenbar=True,
            klemm_beginn=60,
            klemm_ende=60,
            lichter=[],
            helligkeit=100,
            elevation=-3,
            dauer=45,
            lautsprecher=None,
            lautstaerke=30,
        ),
    )
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_RAUM),
        context={"source": "reconfigure", "subentry_id": "r1"},
    )
    assert result["step_id"] == "reconfigure"
    assert vorschlag(result, "name") == "Bad"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"name": "EG Bad", "standard": STANDARD, "klemm_beginn": 30},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    sub = entry.subentries["r1"]
    assert sub.title == "EG Bad"
    assert sub.data["klemm_beginn"] == 30
    assert sub.data["zeitplan"] == PLAN


# ---------------------------------------------------------------- Review-Ergänzungen


def raum_voll(titel: str, sid: str, **daten: Any) -> ConfigSubentryDataWithId:
    """Raum mit allen gespeicherten Feldern."""
    return raum(
        titel,
        sid,
        **{
            "zuordenbar": True,
            "klemm_beginn": 60,
            "klemm_ende": 60,
            "lichter": [],
            "helligkeit": 100,
            "elevation": -3.0,
            "dauer": 45,
            "lautsprecher": None,
            "lautstaerke": 30,
        }
        | daten,
    )


async def aendern(
    hass: HomeAssistant, entry: MockConfigEntry, sid: str, eingabe: dict[str, Any]
) -> SubentryFlowResult:
    """Startet „Raum ändern“ und schickt die Eingabe ab."""
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_RAUM),
        context={"source": "reconfigure", "subentry_id": sid},
    )
    return await hass.config_entries.subentries.async_configure(
        result["flow_id"], eingabe
    )


async def test_aendern_mit_leerem_namen_nimmt_bereichsnamen(
    hass: HomeAssistant,
) -> None:
    """Leerer Name im Ändern-Dialog: der Name des Bereichs wird übernommen."""
    area_id = bereich_mit_geraeten(hass)
    entry = haus(hass, raum_voll("Alt", "r1", bereich=area_id))
    result = await aendern(
        hass, entry, "r1", {"name": " ", "bereich": area_id, "standard": STANDARD}
    )
    assert result["reason"] == "reconfigure_successful"
    assert entry.subentries["r1"].title == "OG Schlafzimmer"


async def test_aendern_ohne_namen_und_bereich_ist_ein_fehler(
    hass: HomeAssistant,
) -> None:
    """Ohne Namen und ohne Bereich wird nicht gespeichert."""
    entry = haus(hass, raum_voll("Bad", "r1"))
    result = await aendern(hass, entry, "r1", {"name": "", "standard": STANDARD})
    assert result["errors"] == {"base": "name_oder_bereich"}
    assert entry.subentries["r1"].title == "Bad"


async def test_aendern_mit_vergebenem_namen_und_bereich(hass: HomeAssistant) -> None:
    """Name und Bereich eines anderen Raums werden im Ändern-Dialog abgelehnt."""
    area_id = bereich_mit_geraeten(hass)
    entry = haus(
        hass,
        raum_voll("Bad", "r1"),
        raum_voll("Schlafzimmer", "r2", bereich=area_id),
    )
    result = await aendern(
        hass,
        entry,
        "r1",
        {"name": "schlafzimmer", "bereich": area_id, "standard": STANDARD},
    )
    assert result["errors"] == {"name": "name_vergeben", "bereich": "bereich_vergeben"}


async def test_aendern_mit_fehler_im_plan(hass: HomeAssistant) -> None:
    """Ein Fehler im Standardplan erscheint auch im Ändern-Dialog."""
    entry = haus(hass, raum_voll("Bad", "r1"))
    result = await aendern(
        hass,
        entry,
        "r1",
        {"name": "Bad", "standard": STANDARD, "freitag": {"beginn": "06:00:00"}},
    )
    assert result["errors"] == {"freitag": "beide_oder_keiner"}


async def test_name_kein_raum_ist_reserviert(hass: HomeAssistant) -> None:
    """„Kein Raum“ ist der reservierte Wert der Raum-Auswahl."""
    result = await starte(hass, haus(hass))
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Kein Raum"}
    )
    assert result["errors"] == {"name": "name_vergeben"}


async def test_vorschlag_ueber_geraet_ohne_deaktivierte(hass: HomeAssistant) -> None:
    """Lichter über ihr Gerät im Bereich zählen; deaktivierte oder umgezogene nicht."""
    from homeassistant.helpers import device_registry as dr  # noqa: PLC0415

    area = ar.async_get(hass).async_create("Büro")
    andere = ar.async_get(hass).async_create("Flur")
    entry = haus(hass)
    geraet = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("test", "lampe")}
    )
    dr.async_get(hass).async_update_device(geraet.id, area_id=area.id)
    ent_reg = er.async_get(hass)
    for uid in ("ueber_geraet", "deaktiviert", "umgezogen"):
        e = ent_reg.async_get_or_create(
            "light",
            "test",
            uid,
            device_id=geraet.id,
            config_entry=entry,
            has_entity_name=True,
            original_name=uid,
        )
        if uid == "deaktiviert":
            ent_reg.async_update_entity(
                e.entity_id, disabled_by=er.RegistryEntryDisabler.USER
            )
        if uid == "umgezogen":
            ent_reg.async_update_entity(e.entity_id, area_id=andere.id)
    for uid in ("sonos_a", "sonos_b"):
        e = ent_reg.async_get_or_create("media_player", "test", uid)
        ent_reg.async_update_entity(e.entity_id, area_id=area.id)

    result = await starte(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"bereich": area.id}
    )
    erwartet = ent_reg.async_get_entity_id("light", "test", "ueber_geraet")
    assert vorschlag(result, "lichter") == [erwartet]
    assert (
        vorschlag(result, "lautsprecher") is None
    )  # zwei Lautsprecher: kein Vorschlag


async def test_zahlen_werden_als_ganzzahl_bzw_kommazahl_gespeichert(
    hass: HomeAssistant,
) -> None:
    """NumberSelector liefert Kommazahlen; Minuten/Prozent werden ganzzahlig."""
    result = await starte(hass, haus(hass))
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Bad"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "standard": STANDARD,
            "klemm_beginn": 30.0,
            "lichter": ["light.x"],
            "elevation": -2.5,
        },
    )
    daten = result["data"]
    assert daten["klemm_beginn"] == 30
    assert isinstance(daten["klemm_beginn"], int)
    assert daten["elevation"] == -2.5
