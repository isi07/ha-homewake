"""Tests für Bedienelemente: Ausnahme, Licht/Radio, Favoriten (3.6, 3.7)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.homewake.const import DOMAIN
from tests.test_person_sensoren import einrichten, entity_id, person, vorspulen, zustand
from tests.test_raum_sensoren import raum, waehle_raum

LAUTSPRECHER = "media_player.test_sonos"
FAVORITEN = ["hr3", "SWR3", "YOU FM"]
SCHALTER = (
    "licht_zeitplan",
    "radio_zeitplan",
    "licht_standard",
    "radio_standard",
    "licht_ausnahme",
    "radio_ausnahme",
)


async def dienst(
    hass: HomeAssistant, domain: str, service: str, eid: str, **daten: Any
) -> None:
    """Ruft einen Dienst blockierend auf."""
    await hass.services.async_call(
        domain, service, {"entity_id": eid, **daten}, blocking=True
    )
    await hass.async_block_till_done()


async def schalte(hass: HomeAssistant, sid: str, schluessel: str, an: bool) -> None:
    """Schaltet einen HomeWake-Schalter."""
    await dienst(
        hass,
        "switch",
        "turn_on" if an else "turn_off",
        entity_id(hass, "switch", sid, schluessel),
    )


async def ausnahme_zeit(hass: HomeAssistant, sid: str, zeit: str) -> None:
    """Setzt die Ausnahme-Uhrzeit."""
    await dienst(
        hass,
        "time",
        "set_value",
        entity_id(hass, "time", sid, "ausnahme_zeit"),
        time=zeit,
    )


async def mit_raum(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Person Vater im Schlafzimmer (mit Lautsprecher), Dienstag 04:00."""
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": FAVORITEN})
    await einrichten(
        hass,
        freezer,
        person("p1", "Vater"),
        raum("r1", "Schlafzimmer", lautsprecher=LAUTSPRECHER),
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")


def attribut(
    hass: HomeAssistant, domain: str, sid: str, schluessel: str, name: str
) -> Any:
    """Attribut einer HomeWake-Entity."""
    state = hass.states.get(entity_id(hass, domain, sid, schluessel))
    assert state is not None
    return state.attributes.get(name)


# ---------------------------------------------------------------- Entities


async def test_person_bekommt_alle_bedienelemente(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ausnahme (Schalter + Uhrzeit), sechs Licht/Radio-Schalter, Favorit."""
    await einrichten(hass, freezer, person("p1", "Vater"))
    assert zustand(hass, "switch", "p1", "ausnahme") == STATE_OFF
    # E63: vorbelegt mit dem Beginn der Standard-Zeile
    assert zustand(hass, "time", "p1", "ausnahme_zeit") == "08:00:00"
    for schluessel in SCHALTER:
        assert zustand(hass, "switch", "p1", schluessel) == STATE_OFF
    assert zustand(hass, "select", "p1", "favorit") == "kein_favorit"


# ---------------------------------------------------------------- Licht/Radio


async def test_licht_schalter_wirkt_auf_naechstes_wecken(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Zeitplan-Licht an: Licht fürs nächste Wecken (Werktag mit eigener Zeit)."""
    await mit_raum(hass, freezer)
    await schalte(hass, "p1", "licht_zeitplan", True)
    assert zustand(hass, "switch", "p1", "licht_zeitplan") == STATE_ON
    assert attribut(hass, "sensor", "p1", "status", "licht") is True
    assert attribut(hass, "sensor", "r1", "weckzeit", "licht") is True


# ---------------------------------------------------------------- Ausnahme


async def test_ausnahme_setzen_und_wecken(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ausnahme 05:00: nächster Wecker 05:00, nach dem Wecken ist sie aus."""
    await mit_raum(hass, freezer)
    await ausnahme_zeit(hass, "p1", "05:00:00")
    await schalte(hass, "p1", "ausnahme", True)
    assert zustand(hass, "sensor", "p1", "status") == "ausnahme"
    assert (
        zustand(hass, "sensor", "p1", "naechster_wecker") == "2026-07-14T03:00:00+00:00"
    )
    await vorspulen(hass, freezer, "2026-07-14T05:00:00+02:00")
    assert zustand(hass, "switch", "p1", "ausnahme") == STATE_OFF
    # E63: nach der abgelaufenen Ausnahme wieder die Standard-Zeit
    assert zustand(hass, "time", "p1", "ausnahme_zeit") == "08:00:00"


async def test_ausnahme_bei_inaktiver_person_abgelehnt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ohne Raum lässt sich die Ausnahme nicht einschalten (E8)."""
    await einrichten(hass, freezer, person("p1", "Vater"))
    await ausnahme_zeit(hass, "p1", "05:00:00")
    with pytest.raises(ServiceValidationError) as fehler:
        await schalte(hass, "p1", "ausnahme", True)
    assert fehler.value.translation_key == "ausnahme_inaktiv"
    assert zustand(hass, "switch", "p1", "ausnahme") == STATE_OFF


async def test_ausnahme_ohne_eigene_uhrzeit_nimmt_standard(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ohne eigene Uhrzeit weckt die Ausnahme zum Standard-Beginn 08:00 (E63)."""
    await mit_raum(hass, freezer)
    await schalte(hass, "p1", "ausnahme", True)
    assert zustand(hass, "sensor", "p1", "status") == "ausnahme"
    assert (
        zustand(hass, "sensor", "p1", "naechster_wecker") == "2026-07-14T06:00:00+00:00"
    )


async def test_ausnahme_ausschalten_setzt_die_uhrzeit_zurueck(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Schaltet der Nutzer die Ausnahme aus, gilt wieder die Standard-Zeit (E63)."""
    await mit_raum(hass, freezer)
    await ausnahme_zeit(hass, "p1", "05:00:00")
    await schalte(hass, "p1", "ausnahme", True)
    await schalte(hass, "p1", "ausnahme", False)
    assert zustand(hass, "time", "p1", "ausnahme_zeit") == "08:00:00"


async def test_uhrzeit_bei_ausgeschalteter_ausnahme_bleibt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Eine Uhrzeit, die vor dem Einschalten gesetzt wird, bleibt stehen."""
    await mit_raum(hass, freezer)
    await ausnahme_zeit(hass, "p1", "05:00:00")
    await schalte(hass, "p1", "licht_standard", True)
    assert zustand(hass, "time", "p1", "ausnahme_zeit") == "05:00:00"


async def test_ausnahme_ab_tagesende_abgelehnt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Eine Ausnahme ab dem Tagesende wird beim Setzen abgelehnt (E18)."""
    await mit_raum(hass, freezer)
    await ausnahme_zeit(hass, "p1", "23:00:00")
    with pytest.raises(ServiceValidationError) as fehler:
        await schalte(hass, "p1", "ausnahme", True)
    assert fehler.value.translation_key == "ausnahme_nach_tagesende"


async def test_uhrzeit_aendern_bei_aktiver_ausnahme_wird_geprueft(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ist die Ausnahme an, wird eine neue Uhrzeit ab Tagesende abgelehnt (E18)."""
    await mit_raum(hass, freezer)
    await ausnahme_zeit(hass, "p1", "05:00:00")
    await schalte(hass, "p1", "ausnahme", True)
    with pytest.raises(ServiceValidationError):
        await ausnahme_zeit(hass, "p1", "22:30:00")
    assert zustand(hass, "time", "p1", "ausnahme_zeit") == "05:00:00"


async def test_bedienwerte_ueberstehen_neuladen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Schalter, Uhrzeit und Favorit bleiben nach dem Neuladen erhalten."""
    await mit_raum(hass, freezer)
    await schalte(hass, "p1", "radio_standard", True)
    await ausnahme_zeit(hass, "p1", "05:30:00")
    await dienst(
        hass,
        "select",
        "select_option",
        entity_id(hass, "select", "p1", "favorit"),
        option="SWR3",
    )
    entry = hass.config_entries.async_entries("homewake")[0]
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert zustand(hass, "switch", "p1", "radio_standard") == STATE_ON
    assert zustand(hass, "time", "p1", "ausnahme_zeit") == "05:30:00"
    assert zustand(hass, "select", "p1", "favorit") == "SWR3"


# ---------------------------------------------------------------- Favoriten (E33)


async def test_favoriten_kommen_vom_lautsprecher_im_raum(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Die Auswahl bietet „kein Favorit“ und die Quellen des Raum-Lautsprechers."""
    await mit_raum(hass, freezer)
    assert attribut(hass, "select", "p1", "favorit", "options") == [
        "kein_favorit",
        *FAVORITEN,
    ]


async def test_favoritenliste_folgt_dem_lautsprecher(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ändert sich die Quellenliste des Lautsprechers, passt sich die Auswahl an."""
    await mit_raum(hass, freezer)
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": ["N-JOY"]})
    await hass.async_block_till_done()
    assert attribut(hass, "select", "p1", "favorit", "options") == [
        "kein_favorit",
        "N-JOY",
    ]


async def test_gewaehlter_favorit_bleibt_auch_ohne_lautsprecher_sichtbar(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ist der Lautsprecher weg, bleibt der gewählte Favorit als Option erhalten."""
    await mit_raum(hass, freezer)
    await dienst(
        hass,
        "select",
        "select_option",
        entity_id(hass, "select", "p1", "favorit"),
        option="hr3",
    )
    hass.states.async_remove(LAUTSPRECHER)
    await hass.async_block_till_done()
    assert zustand(hass, "select", "p1", "favorit") == "hr3"
    assert attribut(hass, "select", "p1", "favorit", "options") == [
        "kein_favorit",
        "hr3",
    ]


async def test_person_ohne_raum_hat_nur_kein_favorit(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ohne Raum (und damit ohne Lautsprecher) gibt es nur „kein Favorit“."""
    await einrichten(hass, freezer, person("p1", "Vater"))
    assert attribut(hass, "select", "p1", "favorit", "options") == ["kein_favorit"]


async def test_favorit_geht_an_den_raum(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Mit Radio und Favorit übernimmt der Raum den Favoriten fürs Wecken."""
    await mit_raum(hass, freezer)
    await schalte(hass, "p1", "radio_zeitplan", True)
    await dienst(
        hass,
        "select",
        "select_option",
        entity_id(hass, "select", "p1", "favorit"),
        option="YOU FM",
    )
    assert attribut(hass, "sensor", "r1", "weckzeit", "favorit") == "YOU FM"


async def test_raum_standard_favorit(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ein Raum mit Lautsprecher hat eine eigene Standard-Favorit-Auswahl (E33)."""
    await mit_raum(hass, freezer)
    eid = entity_id(hass, "select", "r1", "standard_favorit")
    await dienst(hass, "select", "select_option", eid, option="hr3")
    assert zustand(hass, "select", "r1", "standard_favorit") == "hr3"


async def test_raum_ohne_lautsprecher_hat_keine_favoriten_auswahl(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ohne Lautsprecher legt HomeWake keine Standard-Favorit-Auswahl an."""
    await einrichten(hass, freezer, raum("r1", "Flur"))
    from homeassistant.helpers import entity_registry as er  # noqa: PLC0415

    assert (
        er.async_get(hass).async_get_entity_id(
            "select", "homewake", "r1_standard_favorit"
        )
        is None
    )


# ---------------------------------------------------------------- Review-Ergänzungen


async def test_ausnahme_ausschalten_und_zeit_ohne_pruefung(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ausschalten geht immer; bei ausgeschalteter Ausnahme keine Zeit-Prüfung."""
    await mit_raum(hass, freezer)
    await ausnahme_zeit(hass, "p1", "05:00:00")
    await schalte(hass, "p1", "ausnahme", True)
    await schalte(hass, "p1", "ausnahme", False)
    assert zustand(hass, "switch", "p1", "ausnahme") == STATE_OFF
    await ausnahme_zeit(hass, "p1", "23:30:00")
    assert zustand(hass, "time", "p1", "ausnahme_zeit") == "23:30:00"


async def test_standard_radio_am_samstag(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Samstag ohne eigene Zeit: Standard-Radio gilt (E7)."""
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": FAVORITEN})
    await einrichten(
        hass,
        freezer,
        person("p1", "Vater"),
        raum("r1", "Schlafzimmer", lautsprecher=LAUTSPRECHER),
        jetzt="2026-07-18 04:00:00+02:00",
    )
    await waehle_raum(hass, "p1", "Schlafzimmer")
    await schalte(hass, "p1", "radio_standard", True)
    assert attribut(hass, "sensor", "p1", "status", "radio") is True


async def test_ausnahme_licht_bei_ausnahme(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Mit aktiver Ausnahme gilt das Ausnahme-Licht (E7)."""
    await mit_raum(hass, freezer)
    await ausnahme_zeit(hass, "p1", "05:00:00")
    await schalte(hass, "p1", "ausnahme", True)
    await schalte(hass, "p1", "licht_ausnahme", True)
    assert attribut(hass, "sensor", "p1", "status", "licht") is True


async def test_paralleles_schalten_verliert_nichts(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Zwei Licht/Radio-Schalter gleichzeitig: beide Werte bleiben erhalten."""
    await mit_raum(hass, freezer)
    await asyncio.gather(
        schalte(hass, "p1", "licht_zeitplan", True),
        schalte(hass, "p1", "radio_zeitplan", True),
    )
    assert zustand(hass, "switch", "p1", "licht_zeitplan") == STATE_ON
    assert zustand(hass, "switch", "p1", "radio_zeitplan") == STATE_ON


async def test_standard_favorit_uebersteht_neuladen_und_folgt_liste(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Standard-Favorit wird gespeichert; seine Optionen folgen dem Lautsprecher."""
    await mit_raum(hass, freezer)
    eid = entity_id(hass, "select", "r1", "standard_favorit")
    await dienst(hass, "select", "select_option", eid, option="SWR3")
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert zustand(hass, "select", "r1", "standard_favorit") == "SWR3"
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": ["N-JOY"]})
    await hass.async_block_till_done()
    assert attribut(hass, "select", "r1", "standard_favorit", "options") == [
        "kein_favorit",
        "N-JOY",
        "SWR3",
    ]


@pytest.mark.parametrize(
    "raum_daten",
    [{"zustand": {}}, {"zustand": {}, "bedienung": {"standard_favorit": 42}}],
    ids=["alter_speicher", "kaputter_wert"],
)
async def test_alter_oder_kaputter_speicher_fuer_standard_favorit(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
    raum_daten: dict[str, Any],
) -> None:
    """Fehlt der Standard-Favorit im Speicher oder ist er kaputt: kein Favorit."""
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": FAVORITEN})
    entry_id = "eintrag1"
    hass_storage[f"{DOMAIN}.{entry_id}"] = {
        "version": 1,
        "minor_version": 1,
        "key": f"{DOMAIN}.{entry_id}",
        "data": {"personen": {}, "raeume": {"r1": raum_daten}},
    }
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to("2026-07-14 04:00:00+02:00")
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        subentries_data=[raum("r1", "Schlafzimmer", lautsprecher=LAUTSPRECHER)],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert zustand(hass, "select", "r1", "standard_favorit") == "kein_favorit"


async def test_lautsprecher_nach_entladen_ohne_wirkung(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Nach dem Entladen löst eine Lautsprecher-Änderung nichts mehr aus."""
    await mit_raum(hass, freezer)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    coordinator = entry.runtime_data
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    with patch.object(coordinator, "async_update_listeners") as update:
        hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": ["X"]})
        await hass.async_block_till_done()
    update.assert_not_called()


async def test_lautsprecher_attribute_ohne_listenwechsel_ignoriert(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ändert der Lautsprecher nur den Titel, schreibt HomeWake nichts neu."""
    await mit_raum(hass, freezer)
    coordinator = hass.config_entries.async_entries(DOMAIN)[0].runtime_data
    with patch.object(coordinator, "async_update_listeners") as update:
        hass.states.async_set(
            LAUTSPRECHER, "playing", {"source_list": FAVORITEN, "media_title": "Lied"}
        )
        await hass.async_block_till_done()
    update.assert_not_called()


async def test_person_mit_kaputtem_zeitplan_hat_funktionierende_auswahl(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ungültiger Zeitplan: Favorit-Auswahl nicht verfügbar, aber ohne Fehler."""
    await einrichten(hass, freezer, person("p1", "Kaputt", zeitplan={}))
    assert zustand(hass, "select", "p1", "favorit") == "unavailable"
    assert attribut(hass, "select", "p1", "favorit", "options") == ["kein_favorit"]


async def test_lautsprecher_nachtraeglich_hinzufuegen_und_entfernen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Lautsprecher per Ändern: Standard-Favorit erscheint bzw. verschwindet."""
    hass.states.async_set(LAUTSPRECHER, "idle", {"source_list": FAVORITEN})
    entry = await einrichten(hass, freezer, raum("r1", "Flur"))
    sub = entry.subentries["r1"]
    hass.config_entries.async_update_subentry(
        entry, sub, data=dict(sub.data) | {"lautsprecher": LAUTSPRECHER}
    )
    await hass.async_block_till_done()
    assert attribut(hass, "select", "r1", "standard_favorit", "options") == [
        "kein_favorit",
        *FAVORITEN,
    ]
    sub = entry.subentries["r1"]
    hass.config_entries.async_update_subentry(
        entry, sub, data=dict(sub.data) | {"lautsprecher": None}
    )
    await hass.async_block_till_done()
    ent_reg = er.async_get(hass)
    assert ent_reg.async_get_entity_id("select", DOMAIN, "r1_standard_favorit") is None
