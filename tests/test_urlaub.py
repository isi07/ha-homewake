"""Tests für den Urlaubskalender pro Person (ARCHITEKTUR.md 3.6, 5.2, E38).

Der Kalender wird über die Aktion ``calendar.get_events`` gelesen. Hier wird
diese Aktion nachgebaut, damit die Tests ohne echten Kalender laufen.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time
from typing import Any
from unittest.mock import patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigSubentryDataWithId
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.homewake.const import DOMAIN, SUBENTRY_PERSON
from tests.test_person_sensoren import PLAN, einrichten, zustand
from tests.test_raum_sensoren import raum, waehle_raum

KALENDER = "calendar.urlaub_vater"
# Donnerstag, Werktag 06:15, Standard 08:00 (= 07:00 UTC)
JETZT = "2026-11-26 04:00:00+01:00"
WERKTAG_WECKER = "2026-11-26T05:15:00+00:00"
STANDARD_WECKER = "2026-11-26T07:00:00+00:00"


class Kalender:
    """Nachgebaute Aktion ``calendar.get_events`` mit festen Terminen."""

    def __init__(self) -> None:
        """Leerer Kalender; ``fehler`` lässt die Aktion scheitern."""
        self.termine: dict[str, list[dict[str, Any]]] = {}
        self.fehler: Exception | None = None
        self.aufrufe: list[dict[str, Any]] = []
        # Gesetzt: der nächste Aufruf antwortet erst, wenn der Test das Signal
        # setzt (langsamer Kalender), und zwar mit den Terminen von vorher.
        self.halt: asyncio.Event | None = None

    async def get_events(self, call: ServiceCall) -> ServiceResponse:
        """Antwortet wie HA: pro Kalender eine Liste ``events``."""
        self.aufrufe.append(dict(call.data))
        if self.fehler is not None:
            raise self.fehler
        ids = call.data["entity_id"]
        ids = [ids] if isinstance(ids, str) else ids
        antwort: dict[str, Any] = {
            eid: {"events": list(self.termine.get(eid, []))} for eid in ids
        }
        if (halt := self.halt) is not None:
            self.halt = None
            await halt.wait()
        return antwort


@pytest.fixture
def kalender(hass: HomeAssistant) -> Kalender:
    """Registriert die nachgebaute Aktion ``calendar.get_events``."""
    kal = Kalender()
    hass.states.async_set(KALENDER, "off")
    hass.services.async_register(
        "calendar",
        "get_events",
        kal.get_events,
        supports_response=SupportsResponse.ONLY,
    )
    return kal


def person_mit_kalender(
    sid: str, titel: str, kalender: str | None = KALENDER
) -> ConfigSubentryDataWithId:
    """Personen-Untereintrag mit Werktagsplan und Urlaubskalender."""
    daten: dict[str, Any] = {"zeitplan": PLAN}
    if kalender is not None:
        daten["urlaubskalender"] = kalender
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
    """HomeWake mit Personen im Schlafzimmer."""
    entry = await einrichten(
        hass, freezer, *personen, raum("r1", "Schlafzimmer"), jetzt=jetzt
    )
    for person in personen:
        await waehle_raum(hass, person["subentry_id"], "Schlafzimmer")
    # Der Kalender wird im Hintergrund gelesen (E45); darauf warten.
    await hass.async_block_till_done(wait_background_tasks=True)
    return entry


async def vorspulen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, zeitpunkt: str
) -> None:
    """Zeit vorspulen und warten, bis auch Hintergrund-Läufe fertig sind.

    Sicherheitslauf und Timer laufen in HA als Hintergrund-Aufgaben; mit
    Kalender wartet der Lauf auf die Abfrage.
    """
    freezer.move_to(zeitpunkt)
    async_fire_time_changed(hass, datetime.fromisoformat(zeitpunkt))
    await hass.async_block_till_done(wait_background_tasks=True)


GANZTAEGIG_HEUTE = {"start": "2026-11-26", "end": "2026-11-27", "summary": "Urlaub"}


# ---------------------------------------------------------------- Wirkung


async def test_urlaub_heute(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Ganztägiger Urlaub heute: Status „urlaub“, Wecker zur Standard-Zeile."""
    kalender.termine[KALENDER] = [GANZTAEGIG_HEUTE]
    await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    assert zustand(hass, "sensor", "p1", "status") == "urlaub"
    assert zustand(hass, "sensor", "p1", "naechster_wecker") == STANDARD_WECKER


async def test_urlaub_morgen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Nach Tagesende zählt morgen: Urlaub ab morgen → Standard-Zeile morgen."""
    kalender.termine[KALENDER] = [
        {"start": "2026-11-27", "end": "2026-12-01", "summary": "Urlaub"}
    ]
    await haus(
        hass,
        freezer,
        person_mit_kalender("p1", "Vater"),
        jetzt="2026-11-26 23:00:00+01:00",
    )
    assert zustand(hass, "sensor", "p1", "status") == "urlaub"
    assert (
        zustand(hass, "sensor", "p1", "naechster_wecker") == "2026-11-27T07:00:00+00:00"
    )


async def test_termin_mit_uhrzeit_beruehrt_den_tag(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Ein Urlaub, der heute 18:00 endet, macht heute zum Urlaubstag (E38)."""
    kalender.termine[KALENDER] = [
        {
            "start": "2026-11-20T08:00:00+01:00",
            "end": "2026-11-26T18:00:00+01:00",
            "summary": "Reise",
        }
    ]
    await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    assert zustand(hass, "sensor", "p1", "status") == "urlaub"


async def test_urlaub_gilt_nur_fuer_die_eigene_person(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Person ohne Kalender bleibt beim Werktag; gefragt wird nur der eigene."""
    kalender.termine[KALENDER] = [GANZTAEGIG_HEUTE]
    await haus(
        hass,
        freezer,
        person_mit_kalender("p1", "Vater"),
        person_mit_kalender("p2", "Mutter", kalender=None),
    )
    assert zustand(hass, "sensor", "p1", "status") == "urlaub"
    assert zustand(hass, "sensor", "p2", "status") == "werktag"
    assert zustand(hass, "sensor", "p2", "naechster_wecker") == WERKTAG_WECKER
    assert {a["entity_id"] for a in kalender.aufrufe} == {KALENDER}


async def test_abfrage_mit_einem_tag_puffer(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Gefragt wird von gestern 00:00 bis in drei Tagen 00:00 (Puffer, HA-Zeit)."""
    await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    aufruf = kalender.aufrufe[-1]
    assert datetime.fromisoformat(str(aufruf["start_date_time"])) == (
        datetime.fromisoformat("2026-11-25T00:00:00+01:00")
    )
    assert datetime.fromisoformat(str(aufruf["end_date_time"])) == (
        datetime.fromisoformat("2026-11-29T00:00:00+01:00")
    )


async def test_sicherheitslauf_holt_neue_termine(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Ein später eingetragener Urlaub wirkt spätestens beim Sicherheitslauf (E29)."""
    await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    assert zustand(hass, "sensor", "p1", "status") == "werktag"
    kalender.termine[KALENDER] = [GANZTAEGIG_HEUTE]
    await vorspulen(hass, freezer, "2026-11-26 04:09:00+01:00")
    assert zustand(hass, "sensor", "p1", "status") == "urlaub"


# ---------------------------------------------------- Abruf im Hintergrund (E45)


async def test_kalender_aenderung_wirkt_sofort(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Ändert sich der Zustand der Kalender-Entity, wird gleich neu gelesen.

    Ein lokaler Kalender ändert seinen Zustand z. B., wenn ein neuer Termin
    läuft oder er nach einem Neustart verfügbar wird.
    """
    await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    assert zustand(hass, "sensor", "p1", "status") == "werktag"
    kalender.termine[KALENDER] = [GANZTAEGIG_HEUTE]
    hass.states.async_set(KALENDER, "on")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert zustand(hass, "sensor", "p1", "status") == "urlaub"


async def test_kalender_der_person_gewechselt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Neuer Kalender in der Person: sofort gelesen und fortan beobachtet."""
    neu = "calendar.urlaub_neu"
    hass.states.async_set(neu, "off")
    entry = await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    kalender.termine[neu] = [GANZTAEGIG_HEUTE]
    hass.config_entries.async_update_subentry(
        entry, entry.subentries["p1"], data={"zeitplan": PLAN, "urlaubskalender": neu}
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert zustand(hass, "sensor", "p1", "status") == "urlaub"
    assert kalender.aufrufe[-1]["entity_id"] == neu

    # Der alte Kalender löst nichts mehr aus, der neue schon.
    anzahl = len(kalender.aufrufe)
    hass.states.async_set(KALENDER, "on")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(kalender.aufrufe) == anzahl
    kalender.termine[neu] = []
    hass.states.async_set(neu, "on")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(kalender.aufrufe) == anzahl + 1
    assert zustand(hass, "sensor", "p1", "status") == "werktag"


async def test_kurz_nach_mitternacht_wird_neu_gelesen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Um Mitternacht wird gelesen, damit „morgen“ gleich bekannt ist."""
    kalender.termine[KALENDER] = [
        {"start": "2026-11-28", "end": "2026-11-29", "summary": "Urlaub"}
    ]
    entry = await haus(
        hass,
        freezer,
        person_mit_kalender("p1", "Vater"),
        jetzt="2026-11-26 23:50:00+01:00",
    )
    await vorspulen(hass, freezer, "2026-11-27 00:00:00+01:00")
    aufruf = kalender.aufrufe[-1]
    assert datetime.fromisoformat(str(aufruf["start_date_time"])) == (
        datetime.fromisoformat("2026-11-26T00:00:00+01:00")
    )
    morgen = datetime.fromisoformat("2026-11-28T00:00:00+01:00").date()
    assert entry.runtime_data._urlaub["p1"][morgen] is True


async def test_ohne_kalender_wird_nichts_gelesen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Personen ohne Kalender: weder beim Start noch im Sicherheitslauf gefragt."""
    await haus(hass, freezer, person_mit_kalender("p1", "Mutter", kalender=None))
    await vorspulen(hass, freezer, "2026-11-26 04:09:00+01:00")
    await vorspulen(hass, freezer, "2026-11-27 00:00:00+01:00")
    assert kalender.aufrufe == []


async def bis(bedingung: Any) -> None:
    """Der Ereignisschleife Zeit lassen, bis ``bedingung()`` stimmt.

    Ohne Zeitlimit über die Uhr, weil freezegun die Uhr einfriert.
    """
    for _ in range(200):
        if bedingung():
            return
        await asyncio.sleep(0)
    raise AssertionError("Bedingung nicht erreicht")


async def vorspulen_ohne_warten(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, zeitpunkt: str
) -> None:
    """Zeit vorspulen, ohne auf hängende Hintergrund-Aufgaben zu warten."""
    freezer.move_to(zeitpunkt)
    async_fire_time_changed(hass, datetime.fromisoformat(zeitpunkt))
    await hass.async_block_till_done()


async def test_haengender_kalender_haelt_keinen_lauf_auf(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Regression: ein hängender Kalender verzögert weder Wecken noch Bedienung.

    HA lässt immer nur einen Lauf zur Zeit rechnen. Früher wartete ein Lauf
    kurz vor dem Wecken auf den Kalender (bis 10 s); der Wecker-Timer um 06:15
    und jede Bedienung mussten dahinter warten. Die Zeitsprünge bleiben unter
    den 10 s, sonst beendete die Zeitüberschreitung das Hängen.
    """
    entry = await haus(
        hass,
        freezer,
        person_mit_kalender("p1", "Vater"),
        jetzt="2026-11-26 06:14:55+01:00",
    )
    coordinator = entry.runtime_data
    halt = asyncio.Event()
    kalender.halt = halt
    try:
        # Kalender ändert sich, gleichzeitig kommt ein Lauf (z. B. Bedienung).
        hass.states.async_set(KALENDER, "on")
        lauf = hass.async_create_task(coordinator.async_refresh())
        await bis(lambda: kalender.halt is None)  # die Abfrage hängt jetzt
        await bis(lauf.done)

        await vorspulen_ohne_warten(hass, freezer, "2026-11-26 06:15:00+01:00")
        await bis(lambda: zustand(hass, "binary_sensor", "p1", "wach") == "on")

        bedienung = hass.async_create_task(
            coordinator.async_setze_bedienung("p1", licht_radio={})
        )
        await bis(bedienung.done)
    finally:
        halt.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert zustand(hass, "binary_sensor", "p1", "wach") == "on"


async def test_aenderung_waehrend_der_abfrage_wird_nachgeholt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Ändert sich der Kalender, während eine Abfrage hängt, wird danach neu gelesen.

    Die hängende Abfrage antwortet mit dem alten Stand (ohne Urlaub). Würde der
    gelten, kündigte HomeWake den Werktags-Wecker an und weckte am Urlaubstag.
    """
    await haus(
        hass,
        freezer,
        person_mit_kalender("p1", "Vater"),
        jetzt="2026-11-26 06:08:00+01:00",
    )
    halt = asyncio.Event()
    kalender.halt = halt
    try:
        await vorspulen_ohne_warten(hass, freezer, "2026-11-26 06:09:00+01:00")
        await bis(lambda: kalender.halt is None)
        kalender.termine[KALENDER] = [GANZTAEGIG_HEUTE]
        hass.states.async_set(KALENDER, "on")
    finally:
        halt.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert zustand(hass, "sensor", "p1", "status") == "urlaub"
    assert zustand(hass, "sensor", "p1", "naechster_wecker") == STANDARD_WECKER

    await vorspulen(hass, freezer, "2026-11-26 06:15:00+01:00")
    assert zustand(hass, "binary_sensor", "p1", "wach") == "off"


async def test_kalender_entfernt_waehrend_der_abfrage(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Antwort eines inzwischen aus der Person entfernten Kalenders zählt nicht."""
    entry = await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    kalender.termine[KALENDER] = [GANZTAEGIG_HEUTE]
    halt = asyncio.Event()
    kalender.halt = halt
    try:
        hass.states.async_set(KALENDER, "on")
        await bis(lambda: kalender.halt is None)
        hass.config_entries.async_update_subentry(
            entry, entry.subentries["p1"], data={"zeitplan": PLAN}
        )
        await hass.async_block_till_done()
    finally:
        halt.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert zustand(hass, "sensor", "p1", "status") == "werktag"


async def test_unerwarteter_fehler_beim_abruf_wird_geloggt(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    kalender: Kalender,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ein Programmierfehler im Abruf: mit Traceback geloggt, nächster Abruf geht."""
    entry = await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    with patch.object(
        type(entry.runtime_data), "_lade_urlaub", side_effect=RuntimeError("kaputt")
    ):
        hass.states.async_set(KALENDER, "on")
        await hass.async_block_till_done(wait_background_tasks=True)
    assert any(
        "Unerwarteter Fehler" in r.getMessage() and r.exc_info for r in caplog.records
    )
    kalender.termine[KALENDER] = [GANZTAEGIG_HEUTE]
    hass.states.async_set(KALENDER, "off")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert zustand(hass, "sensor", "p1", "status") == "urlaub"


async def test_entladen_waehrend_des_kalender_abrufs(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Wird HomeWake entladen, während der Kalender hängt: sauber beendet."""
    entry = await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    halt = asyncio.Event()
    kalender.halt = halt
    hass.states.async_set(KALENDER, "on")
    await bis(lambda: kalender.halt is None)
    assert await hass.config_entries.async_unload(entry.entry_id)
    halt.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state.name == "NOT_LOADED"

    # Beobachtung, Sicherheitslauf und Mitternacht sind abgemeldet.
    anzahl = len(kalender.aufrufe)
    hass.states.async_set(KALENDER, "off")
    await vorspulen(hass, freezer, "2026-11-26 04:09:00+01:00")
    await vorspulen(hass, freezer, "2026-11-27 00:00:00+01:00")
    assert len(kalender.aufrufe) == anzahl


# ---------------------------------------------------------------- Fehlerfälle


async def test_fehlender_kalender_rechnet_ohne_urlaub(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ohne Kalender-Aktion (z. B. Kalender fehlt): Werktag, einmal gewarnt."""
    await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    assert zustand(hass, "sensor", "p1", "status") == "werktag"
    assert zustand(hass, "sensor", "p1", "naechster_wecker") == WERKTAG_WECKER
    await vorspulen(hass, freezer, "2026-11-26 04:09:00+01:00")
    await vorspulen(hass, freezer, "2026-11-26 04:19:00+01:00")
    warnungen = [
        r
        for r in caplog.records
        if KALENDER in r.getMessage() and r.levelname == "WARNING"
    ]
    assert len(warnungen) == 1


async def test_kalender_fehler_und_wieder_verfuegbar(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    kalender: Kalender,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Abfrage scheitert: ohne Urlaub weiter; danach wieder mit, je einmal gemeldet."""
    kalender.termine[KALENDER] = [GANZTAEGIG_HEUTE]
    kalender.fehler = HomeAssistantError("Kalender nicht erreichbar")
    await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    assert zustand(hass, "sensor", "p1", "status") == "werktag"
    await vorspulen(hass, freezer, "2026-11-26 04:09:00+01:00")
    kalender.fehler = None
    await vorspulen(hass, freezer, "2026-11-26 04:19:00+01:00")
    assert zustand(hass, "sensor", "p1", "status") == "urlaub"
    meldungen = [r for r in caplog.records if KALENDER in r.getMessage()]
    assert [r.levelname for r in meldungen] == ["WARNING", "INFO"]


async def test_unerwartete_antwort_rechnet_ohne_urlaub(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Eine Antwort ohne den Kalender oder ohne ``events`` stürzt nicht ab."""

    async def antwort(_call: ServiceCall) -> ServiceResponse:
        return {"calendar.anderer": {"events": []}, KALENDER: {"events": "kaputt"}}

    hass.states.async_set(KALENDER, "off")
    hass.services.async_register(
        "calendar", "get_events", antwort, supports_response=SupportsResponse.ONLY
    )
    await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    assert zustand(hass, "sensor", "p1", "status") == "werktag"


async def test_ausnahme_probe_kennt_den_urlaub(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Die Probe beim Einschalten der Ausnahme nutzt den geholten Urlaub.

    Am Urlaubstag endet der Tag zur Standard-Zeile (21:00). Eine Ausnahme um
    21:30 liegt danach und wird abgelehnt; am Werktag (Ende 22:00) ginge sie.
    """
    kalender.termine[KALENDER] = [GANZTAEGIG_HEUTE]
    await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    coordinator = hass.config_entries.async_entries("homewake")[0].runtime_data

    with pytest.raises(ServiceValidationError):
        await coordinator.async_setze_bedienung(
            "p1", ausnahme_aktiv=True, ausnahme_zeit=time(21, 30)
        )


@pytest.mark.parametrize(
    "antwort",
    [
        {"calendar.anderer": {"events": []}},  # Kalender fehlt in der Antwort
        None,
    ],
)
async def test_antwort_ohne_kalender_gilt_als_nicht_lesbar(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    antwort: ServiceResponse,
) -> None:
    """Fehlt der Kalender in der Antwort: ohne Urlaub weiter, mit Warnung."""

    async def get_events(_call: ServiceCall) -> ServiceResponse:
        return antwort

    hass.states.async_set(KALENDER, "off")
    hass.services.async_register(
        "calendar", "get_events", get_events, supports_response=SupportsResponse.ONLY
    )
    await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    assert zustand(hass, "sensor", "p1", "status") == "werktag"
    assert any(
        KALENDER in r.getMessage() and r.levelname == "WARNING" for r in caplog.records
    )


async def test_zeitueberschreitung_rechnet_ohne_urlaub(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Antwortet der Kalender nicht rechtzeitig: ohne Urlaub weiter."""
    kalender.termine[KALENDER] = [GANZTAEGIG_HEUTE]
    kalender.fehler = TimeoutError()
    await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    assert zustand(hass, "sensor", "p1", "status") == "werktag"


async def test_fremder_fehler_legt_homewake_nicht_lahm(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Auch ein unerwarteter Fehler der Kalender-Integration: Wecker rechnen weiter."""
    kalender.termine[KALENDER] = [GANZTAEGIG_HEUTE]
    kalender.fehler = RuntimeError("Verbindung weg")
    await haus(
        hass,
        freezer,
        person_mit_kalender("p1", "Vater"),
        person_mit_kalender("p2", "Mutter", kalender=None),
    )
    assert zustand(hass, "sensor", "p1", "status") == "werktag"
    assert zustand(hass, "sensor", "p2", "naechster_wecker") == WERKTAG_WECKER


async def test_nicht_verfuegbarer_kalender_wird_nicht_gefragt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Ist die Kalender-Entity nicht verfügbar, wird gar nicht erst gefragt."""
    hass.states.async_set(KALENDER, "unavailable")
    await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    assert zustand(hass, "sensor", "p1", "status") == "werktag"
    assert kalender.aufrufe == []


async def test_zwei_kalender_einer_scheitert(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Fehlt der Kalender der einen Person, bekommt die andere trotzdem Urlaub."""
    kalender.termine[KALENDER] = [GANZTAEGIG_HEUTE]
    await haus(
        hass,
        freezer,
        person_mit_kalender("p1", "Vater"),
        person_mit_kalender("p2", "Mutter", kalender="calendar.gibt_es_nicht"),
    )
    assert zustand(hass, "sensor", "p1", "status") == "urlaub"
    assert zustand(hass, "sensor", "p2", "status") == "werktag"


# ---------------------------------------------------------------- letzter Stand (E38)


async def test_bei_ausfall_gilt_der_zuletzt_gelesene_urlaub(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Fällt der Kalender aus, gilt der zuletzt gelesene Urlaub für heute weiter."""
    kalender.termine[KALENDER] = [GANZTAEGIG_HEUTE]
    await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    assert zustand(hass, "sensor", "p1", "status") == "urlaub"
    kalender.fehler = HomeAssistantError("Kalender weg")
    await vorspulen(hass, freezer, "2026-11-26 04:09:00+01:00")
    assert zustand(hass, "sensor", "p1", "status") == "urlaub"
    assert zustand(hass, "sensor", "p1", "naechster_wecker") == STANDARD_WECKER


async def test_bei_ausfall_gilt_morgen_von_gestern_als_heute(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Gestern gelesen „morgen Urlaub“; heute ist der Kalender weg → heute Urlaub."""
    kalender.termine[KALENDER] = [GANZTAEGIG_HEUTE]
    await haus(
        hass,
        freezer,
        person_mit_kalender("p1", "Vater"),
        jetzt="2026-11-25 23:00:00+01:00",
    )
    hass.states.async_set(KALENDER, "unavailable")
    await vorspulen(hass, freezer, "2026-11-26 04:09:00+01:00")
    assert zustand(hass, "sensor", "p1", "status") == "urlaub"
    assert zustand(hass, "sensor", "p1", "naechster_wecker") == STANDARD_WECKER


async def test_letzter_urlaub_uebersteht_neustart(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Nach Neustart fehlt der Kalender oft noch: gespeicherter Urlaub gilt."""
    kalender.termine[KALENDER] = [GANZTAEGIG_HEUTE]
    entry = await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    hass.states.async_set(KALENDER, "unavailable")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert zustand(hass, "sensor", "p1", "status") == "urlaub"


async def test_alter_urlaub_gilt_nicht_mehr(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Ein gespeicherter Urlaub von vorgestern zählt nicht für heute oder morgen."""
    kalender.termine[KALENDER] = [GANZTAEGIG_HEUTE]
    await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    hass.states.async_set(KALENDER, "unavailable")
    await vorspulen(hass, freezer, "2026-11-27 04:09:00+01:00")  # Freitag
    assert zustand(hass, "sensor", "p1", "status") == "werktag"


async def test_ohne_kalender_wird_kein_alter_urlaub_genutzt(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Kalender aus der Person entfernt: auch der alte Urlaub gilt nicht mehr."""
    kalender.termine[KALENDER] = [GANZTAEGIG_HEUTE]
    entry = await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    hass.config_entries.async_update_subentry(
        entry, entry.subentries["p1"], data={"zeitplan": PLAN}
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert zustand(hass, "sensor", "p1", "status") == "werktag"


# ---------------------------------------------------------------- Reparatur (E39)


def hinweis(hass: HomeAssistant, sid: str = "p1") -> ir.IssueEntry | None:
    """Reparatur-Hinweis „Urlaubskalender nicht verfügbar“ einer Person."""
    return ir.async_get(hass).async_get_issue(
        DOMAIN, f"urlaubskalender_nicht_verfuegbar_{sid}"
    )


async def test_hinweis_erst_nach_30_minuten_ausfall(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Der Hinweis erscheint erst nach über 30 Minuten Ausfall, dann mit Namen."""
    hass.states.async_set(KALENDER, "unavailable")
    entry = await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    await vorspulen(hass, freezer, "2026-11-26 04:29:00+01:00")
    assert hinweis(hass) is None
    await vorspulen(hass, freezer, "2026-11-26 04:39:00+01:00")
    eintrag = hinweis(hass)
    assert eintrag is not None
    assert eintrag.config_entry_id == entry.entry_id
    assert eintrag.severity is ir.IssueSeverity.WARNING
    assert eintrag.translation_key == "urlaubskalender_nicht_verfuegbar"
    assert eintrag.translation_placeholders == {
        "person": "Vater",
        "kalender": KALENDER,
    }


async def test_kurzer_ausfall_ohne_hinweis(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Kalender kurz weg (z. B. beim Start), dann wieder da: kein Hinweis.

    Eine Zustandsänderung des Kalenders wird sofort gelesen (E45); der neue
    Ausfall zählt also ab dem Moment, in dem er beginnt.
    """
    hass.states.async_set(KALENDER, "unavailable")
    await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    await vorspulen(hass, freezer, "2026-11-26 04:09:00+01:00")
    hass.states.async_set(KALENDER, "off")  # nach 9 Minuten wieder da
    await hass.async_block_till_done(wait_background_tasks=True)
    await vorspulen(hass, freezer, "2026-11-26 04:19:00+01:00")
    hass.states.async_set(KALENDER, "unavailable")
    await hass.async_block_till_done(wait_background_tasks=True)
    await vorspulen(hass, freezer, "2026-11-26 04:29:00+01:00")
    await vorspulen(hass, freezer, "2026-11-26 04:39:00+01:00")
    assert hinweis(hass) is None  # neuer Ausfall erst seit 04:19


async def test_hinweis_verschwindet_wenn_kalender_wieder_da(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Ist der Kalender wieder lesbar, verschwindet der Hinweis."""
    hass.states.async_set(KALENDER, "unavailable")
    await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    await vorspulen(hass, freezer, "2026-11-26 04:39:00+01:00")
    assert hinweis(hass) is not None
    hass.states.async_set(KALENDER, "off")
    await vorspulen(hass, freezer, "2026-11-26 04:49:00+01:00")
    assert hinweis(hass) is None


async def test_hinweis_verschwindet_ohne_kalender_in_der_person(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Wird der Kalender aus der Person entfernt, verschwindet der Hinweis."""
    hass.states.async_set(KALENDER, "unavailable")
    entry = await haus(hass, freezer, person_mit_kalender("p1", "Vater"))
    await vorspulen(hass, freezer, "2026-11-26 04:39:00+01:00")
    assert hinweis(hass) is not None
    hass.config_entries.async_update_subentry(
        entry, entry.subentries["p1"], data={"zeitplan": PLAN}
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hinweis(hass) is None


async def test_hinweis_verschwindet_mit_der_person(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, kalender: Kalender
) -> None:
    """Wird die Person entfernt, verschwindet auch ihr Hinweis."""
    hass.states.async_set(KALENDER, "unavailable")
    entry = await haus(
        hass,
        freezer,
        person_mit_kalender("p1", "Vater"),
        person_mit_kalender("p2", "Mutter", kalender=None),
    )
    await vorspulen(hass, freezer, "2026-11-26 04:39:00+01:00")
    assert hinweis(hass) is not None
    hass.config_entries.async_remove_subentry(entry, "p1")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hinweis(hass) is None
