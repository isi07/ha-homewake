"""Tests für die Daten, die die eigene Karte braucht (E62, E64, E70).

Die Karte sieht nur Entities, Attribute und die Registries des Frontends.
Was ihr fehlt, ergänzt HomeWake als Attribut.
"""

from __future__ import annotations

from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from tests.test_bedienung import attribut, ausnahme_zeit, mit_raum, schalte
from tests.test_button import druecken
from tests.test_hinweise import daten_aendern
from tests.test_person_sensoren import (
    einrichten,
    entity_id,
    person,
    vorspulen,
    zustand,
)
from tests.test_raum_sensoren import waehle_raum
from tests.test_schalten import LICHT, WINTER, aufbau, mitschreiben, tag

# ---------------------------------------------------------------- Status heute/morgen


async def test_status_sensor_zeigt_status_fuer_heute_und_morgen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Dienstag mit Raum: heute und morgen Werktag mit Wochentag als Grund."""
    await mit_raum(hass, freezer)
    assert attribut(hass, "sensor", "p1", "status", "status_heute") == "werktag"
    assert attribut(hass, "sensor", "p1", "status", "grund_heute") == "dienstag"
    assert attribut(hass, "sensor", "p1", "status", "status_morgen") == "werktag"
    assert attribut(hass, "sensor", "p1", "status", "grund_morgen") == "mittwoch"


async def test_status_ohne_raum_inaktiv(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ohne Raum sind beide Tage inaktiv."""
    await einrichten(hass, freezer, person("p1", "Vater"))
    assert attribut(hass, "sensor", "p1", "status", "status_heute") == "inaktiv"
    assert attribut(hass, "sensor", "p1", "status", "grund_morgen") == "kein_raum"


# ---------------------------------------------------------------- Raum-ID


async def test_raum_auswahl_nennt_die_raum_id(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Die Raum-Auswahl nennt die ID des Raums (Sprung in der Karte)."""
    await mit_raum(hass, freezer)
    assert attribut(hass, "select", "p1", "raum", "raum_id") == "r1"
    await waehle_raum(hass, "p1", "kein_raum")
    assert attribut(hass, "select", "p1", "raum", "raum_id") is None


async def test_raum_id_fehlt_bei_nicht_zuordenbarem_raum(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Wie die Auswahl („kein Raum“): keine ID eines nicht zuordenbaren Raums."""
    entry = await mit_raum_entry(hass, freezer)
    daten_aendern(hass, entry, "r1", zuordenbar=False)
    await hass.async_block_till_done()
    assert attribut(hass, "select", "p1", "raum", "raum_id") is None


async def mit_raum_entry(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> Any:
    """Wie ``mit_raum``, gibt den Eintrag zurück."""
    await mit_raum(hass, freezer)
    return hass.config_entries.async_entries("homewake")[0]


# ---------------------------------------------------------------- wecken_bis (E64)


async def test_wach_wechselt_beim_wecken_ohne_zwischenstand(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Beim Wecken genau ein neuer Zustand: an, mit ``wecken_bis`` (Review B2a)."""
    mitschreiben(hass)
    await aufbau(hass, freezer)
    aenderungen: list[tuple[str, object]] = []

    @callback
    def _merken(event: Event[EventStateChangedData]) -> None:
        neu = event.data["new_state"]
        assert neu is not None
        aenderungen.append((neu.state, neu.attributes.get("wecken_bis")))

    abmelden = async_track_state_change_event(
        hass, [entity_id(hass, "binary_sensor", "r1", "wach")], _merken
    )
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    abmelden()
    assert len(aenderungen) == 1
    assert aenderungen[0][0] == "on"
    assert aenderungen[0][1] is not None


async def test_wecken_bis_fehlt_waehrend_erneut_ausgeschaltet_wird(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ab dem Aus-Zeitpunkt fehlt das Attribut, auch wenn noch versucht wird."""
    mitschreiben(hass)
    await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    hass.states.async_set(LICHT, "unavailable")
    await vorspulen(hass, freezer, tag(WINTER, "07:00:00"))
    assert attribut(hass, "binary_sensor", "r1", "wach", "wecken_bis") is None
    entry = hass.config_entries.async_entries("homewake")[0]
    assert entry.runtime_data._schalter.auftraege  # Auftrag läuft noch


async def test_wecken_bis_waehrend_des_weckens(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ab dem Wecken steht der Aus-Zeitpunkt am Raum, nach der Dauer nicht mehr."""
    mitschreiben(hass)
    await aufbau(hass, freezer)
    assert attribut(hass, "binary_sensor", "r1", "wach", "wecken_bis") is None
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    bis = attribut(hass, "binary_sensor", "r1", "wach", "wecken_bis")
    assert bis is not None
    assert bis.isoformat() == "2026-11-24T07:00:00+01:00"
    await vorspulen(hass, freezer, tag(WINTER, "07:00:00"))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert attribut(hass, "binary_sensor", "r1", "wach", "wecken_bis") is None


async def test_wecken_bis_verschwindet_nach_der_taste(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Nach „Wecken beenden“ fehlt das Attribut ohne neuen Lauf (E60, E64)."""
    mitschreiben(hass)
    await aufbau(hass, freezer)
    await vorspulen(hass, freezer, tag(WINTER, "06:15:00"))
    freezer.move_to(tag(WINTER, "06:20:00"))
    await druecken(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert attribut(hass, "binary_sensor", "r1", "wach", "wecken_bis") is None


# ---------------------------------------------------------------- E63


async def test_ausnahme_zeit_nach_kein_raum_wieder_standard(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ausnahme an, dann „kein Raum“: Ausnahme gelöscht, Uhrzeit wieder 08:00 (E8)."""
    await mit_raum(hass, freezer)
    await ausnahme_zeit(hass, "p1", "05:00:00")
    await schalte(hass, "p1", "ausnahme", True)
    await waehle_raum(hass, "p1", "kein_raum")
    assert zustand(hass, "switch", "p1", "ausnahme") == "off"
    assert zustand(hass, "time", "p1", "ausnahme_zeit") == "08:00:00"


async def test_ausnahme_zeit_ohne_lesbaren_zeitplan(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Ohne lesbaren Zeitplan gibt es keine Standard-Zeit (Person nicht verfügbar)."""
    entry = await einrichten(hass, freezer, person("p1", "Vater", zeitplan={}))
    assert entry.runtime_data.ausnahme_zeit("p1") is None
