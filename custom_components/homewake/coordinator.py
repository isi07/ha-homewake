"""Coordinator: holt Eingaben aus HA, rechnet, speichert und plant (ARCHITEKTUR.md 5).

Der Coordinator hält die Ergebnisse für alle Entities. Gerechnet wird beim Start,
zur „nächsten Änderung“ (genauer Timer), im Sicherheitslauf alle 10 Minuten
(E29) und bei Änderungen von außen. Die eigentliche Rechnung steckt in der reinen
Funktion ``berechne_haus`` (E31).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from functools import partial
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_CORE_CONFIG_UPDATE, STATE_UNAVAILABLE
from homeassistant.core import (
    CALLBACK_TYPE,
    CoreState,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import feiertage, sonne
from .anbieter import ANBIETER, AnbieterFehler
from .const import (
    CONF_BUNDESLAND,
    CONF_DAUER,
    CONF_ELEVATION,
    CONF_GRAD_ABEND,
    CONF_GRAD_MORGEN,
    CONF_HELLIGKEIT,
    CONF_KLEMM_BEGINN,
    CONF_KLEMM_ENDE,
    CONF_LAND,
    CONF_LAUTSPRECHER,
    CONF_LAUTSTAERKE,
    CONF_LICHTER,
    CONF_SCHULE,
    CONF_SONNE_ABEND,
    CONF_SONNE_MORGEN,
    CONF_URLAUBSKALENDER,
    CONF_ZEITPLAN,
    CONF_ZUORDENBAR,
    DOMAIN,
    SUBENTRY_PERSON,
    SUBENTRY_RAUM,
)
from .logic.aktorik import AktorikEingaben, AktorikKonfig, Schaltplan, schaltplan
from .logic.diagnose import als_json
from .logic.eingabe import zeitplan_aus_daten
from .logic.haus import (
    HausEingaben,
    HausErgebnis,
    PersonBedienung,
    PersonKonfig,
    berechne_haus,
)
from .logic.person import LichtRadio, PersonStatus, PersonZustand, Profil, TagInfo
from .logic.raum import RaumErgebnis, RaumKonfig, RaumZustand, Sonne
from .logic.schulferien import (
    VORRAT,
    SchulDaten,
    abruf_faellig,
    schul_pfad,
    schul_schluessel,
    schulferien_an,
    veraltet,
)
from .logic.sonnenstand import STANDARD_SONNENSTAND, grad
from .logic.speicher import (
    aus_auftrag_aus_json,
    aus_auftrag_zu_json,
    person_bedienung_aus_json,
    person_bedienung_zu_json,
    person_zustand_aus_json,
    person_zustand_zu_json,
    raum_zustand_aus_json,
    raum_zustand_zu_json,
    schulferien_aus_json,
    schulferien_zu_json,
    urlaub_aus_json,
    urlaub_zu_json,
)
from .logic.urlaub import termine_aus_antwort, urlaub_an
from .logic.zeitplan import Zeitplan
from .schalten import Schalter

_LOGGER = logging.getLogger(__name__)
ISSUE_FEIERTAGE = "feiertage_nicht_verfuegbar"
ISSUE_KALENDER = "urlaubskalender_nicht_verfuegbar"  # + "_<Person-ID>"
ISSUE_SCHULFERIEN = "schulferien_veraltet"  # + "_<Hash der Schule>" (E42, E49)
ISSUE_RAUM_VERLOREN = "raum_verloren"  # + "_<Person-ID>" (E11)
ISSUE_ZEITPLAN = "zeitplan_ungueltig"  # + "_<Untereintrags-ID>" (E46)
ISSUE_GERAET = "geraet_fehlt"  # + "_<Raum-ID>" (5.5)
ISSUE_FAVORIT = "favorit_fehlt"  # + "_<Personen- oder Raum-ID>" (E56)
ISSUE_OHNE_LISTE = "lautsprecher_ohne_liste"  # + "_<Raum-ID>" (E58, E61)
# Reparatur-Hinweis erst nach dieser Ausfallzeit (kein Aufblitzen beim Start, E39)
KALENDER_HINWEIS_NACH = timedelta(minutes=30)

STORE_VERSION = 1
SPEICHER_VERZOEGERUNG = 1.0  # Sekunden
KALENDER_TIMEOUT = 10  # Sekunden für eine Kalender-Abfrage
# Sicherheitslauf zur Minute :09, :19, … :59, Sekunde 0 (E29)
SICHERHEITSLAUF_MINUTEN = tuple(range(9, 60, 10))

type HomeWakeConfigEntry = ConfigEntry[HomeWakeCoordinator]


def schul_hinweis_id(schluessel: str) -> str:
    """ID des Hinweises „Schulferien-Daten veraltet“ einer Schule (E42).

    Aus einem kurzen Hash statt der Kennung: HA hängt die Hinweis-IDs
    ungeschwärzt an die Diagnose an, und die Kennung verrät die Schule (E49).
    """
    kurz = hashlib.sha256(schluessel.encode()).hexdigest()[:12]
    return f"{ISSUE_SCHULFERIEN}_{kurz}"


type Ort = tuple[str, str | None, str]  # Land, Region, Sprache der Feiertage


class HomeWakeCoordinator(DataUpdateCoordinator[HausErgebnis]):
    """Rechnet alle Personen und Räume in einem Lauf und hält die Ergebnisse."""

    config_entry: HomeWakeConfigEntry

    def __init__(self, hass: HomeAssistant, entry: HomeWakeConfigEntry) -> None:
        """Legt den Coordinator für einen HomeWake-Eintrag an."""
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=None
        )
        self._store: Store[dict[str, Any]] = Store(
            hass, STORE_VERSION, f"{DOMAIN}.{entry.entry_id}", atomic_writes=True
        )
        self._bedienung: dict[str, PersonBedienung] = {}
        self._zustaende: dict[str, PersonZustand] = {}
        self._raum_zustaende: dict[str, RaumZustand] = {}
        self._standard_favorit: dict[str, str | None] = {}
        # Schaltet Licht und Radio zur Weckzeit und hält die Aus-Aufträge (A1)
        self._schalter = Schalter(
            hass, entry, self._auftraege_geaendert, self._ohne_liste_melden
        )
        self._im_lauf = False
        # Feiertage pro (Land, Region, Sprache, Jahr), vorab geladen (E45);
        # Orte, für die das Laden gescheitert ist, und der laufende Nachlade-Abruf
        self._feiertage: dict[tuple[str, str | None, str, int], dict[date, str]] = {}
        self._feiertage_gescheitert: set[Ort] = set()
        self._feiertage_fehler = False
        self._feiertage_abruf: asyncio.Task[None] | None = None
        # Zuletzt gelesener Urlaub pro Person und Tag (E38); bleibt bei Ausfall
        self._urlaub: dict[str, dict[date, bool]] = {}
        # Urlaubskalender pro Person (Stand des letzten Laufs), deren Beobachtung,
        # der laufende Abruf und ob danach noch einmal gelesen werden soll (E45)
        self._urlaub_kalender: dict[str, str] = {}
        self._kalender_beobachtung: CALLBACK_TYPE | None = None
        self._urlaub_abruf: asyncio.Task[None] | None = None
        self._urlaub_nochmal = False
        # Personen mit nicht lesbarem Kalender: seit wann; und die mit Hinweis
        self._kalender_fehler: dict[str, datetime] = {}
        self._kalender_hinweis: set[str] = set()
        # Schulferien pro Schul-Kennung (E41): geladene Daten, letzter Versuch,
        # Ausfall seit, Schulen mit Hinweis (E42) und der laufende Abruf
        self._schulen: dict[str, SchulDaten] = {}
        self._schul_versucht: dict[str, datetime] = {}
        self._schul_fehler: dict[str, datetime] = {}
        self._schul_hinweis: set[str] = set()
        self._schul_abruf: asyncio.Task[None] | None = None
        self._schule_ungueltig: set[str] = set()  # Personen, schon gemeldet
        self._timer: CALLBACK_TYPE | None = None
        self._abmelden: list[CALLBACK_TYPE] = []
        self._geladen = False  # erst nach erfolgreichem Laden wird gespeichert
        self._beendet = False  # nach async_shutdown: nichts Neues mehr anstoßen
        self._ungueltig: set[str] = set()  # Personen/Räume mit ungültigem Zeitplan
        self._raum_hinweis: set[str] = set()  # Personen mit Hinweis „Raum verloren“
        # Räume mit Hinweis „Gerät fehlt“ und die zuletzt gemeldeten Geräte
        self._geraet_fehlt: dict[str, list[str]] = {}
        # Personen/Räume mit Hinweis „Favorit fehlt“ und dessen Platzhalter
        self._favorit_fehlt: dict[str, dict[str, str]] = {}
        # Zuordenbare Räume des letzten Laufs (ID → Name) für die Raum-Auswahl
        self.zuordenbare_raeume: dict[str, str] = {}

    # ------------------------------------------------------------ Lebenszyklus

    async def _async_setup(self) -> None:
        """Lädt den Speicher und meldet Sicherheitslauf und Zeitzonen-Änderung an."""
        gespeichert = await self._store.async_load() or {}
        personen = gespeichert.get("personen") or {}
        for sid in self._personen_ids():
            daten = personen.get(sid) or {}
            self._bedienung[sid] = person_bedienung_aus_json(daten.get("bedienung"))
            self._zustaende[sid] = person_zustand_aus_json(daten.get("zustand"))
            self._urlaub[sid] = urlaub_aus_json(daten.get("urlaub"))
        self._alte_kalender_hinweise_entfernen()
        gespeicherte_schulen = gespeichert.get("schulferien") or {}
        for schluessel in self.schulen():
            self._schulen[schluessel] = schulferien_aus_json(
                gespeicherte_schulen.get(schluessel)
            )
        self._alte_schul_hinweise_entfernen()
        self._alte_raum_hinweise_pruefen()
        self._alte_zeitplan_hinweise_pruefen()
        raeume = gespeichert.get("raeume") or {}
        # Aus-Aufträge auch gelöschter Räume: Ihr Licht geht trotzdem aus (A2).
        auftraege = {
            sid: auftrag
            for sid, daten in raeume.items()
            if isinstance(daten, dict)
            and (auftrag := aus_auftrag_aus_json(daten.get("aus"))) is not None
        }
        for sid in self._ids(SUBENTRY_RAUM):
            daten = raeume.get(sid) or {}
            self._raum_zustaende[sid] = raum_zustand_aus_json(daten.get("zustand"))
            bedienung = daten.get("bedienung") or {}
            favorit = bedienung.get("standard_favorit")
            self._standard_favorit[sid] = favorit if isinstance(favorit, str) else None
        # Feiertage für dieses und das nächste Jahr vorab laden: Hier darf
        # gewartet werden, es läuft noch kein Lauf (E45).
        if (ort := self._feiertag_ort()) is not None:
            jahr = dt_util.now().year
            await self._feiertage_laden(ort, [jahr, jahr + 1])
        # Favoritenlisten folgen den Lautsprechern der Räume (E33).
        if lautsprecher := sorted(
            {e for sid in self._ids(SUBENTRY_RAUM) if (e := self.lautsprecher(sid))}
        ):
            self._abmelden.append(
                async_track_state_change_event(
                    self.hass, lautsprecher, self._lautsprecher_geaendert
                )
            )
        self._abmelden.append(
            async_track_time_change(
                self.hass,
                self._sicherheitslauf,
                minute=SICHERHEITSLAUF_MINUTEN,
                second=0,
            )
        )
        # Kurz nach Mitternacht den Urlaub für den neuen „morgen“ lesen (E45).
        self._abmelden.append(
            async_track_time_change(
                self.hass, self._mitternacht, hour=0, minute=0, second=0
            )
        )
        self._abmelden.append(
            self.hass.bus.async_listen(EVENT_CORE_CONFIG_UPDATE, self._config_geaendert)
        )
        # Aus-Aufträge von vor dem Neustart (E12, E54)
        self._schalter.laden(auftraege)
        # Fehlende Geräte und Favoriten erst prüfen, wenn HA gestartet ist
        self._schalter.nach_start(self._geraete_pruefen)
        self._schalter.nach_start(self._favoriten_pruefen)
        self._geladen = True

    async def async_shutdown(self) -> None:
        """Beendet Läufe, meldet Timer ab und schreibt den Speicher beim Entladen.

        Zuerst ``super()``: das verhindert neue Läufe. Gespeichert wird nur, wenn
        der Speicher vorher gelesen wurde; sonst würde ein fehlgeschlagener
        Start die gute Datei mit Standardwerten überschreiben.
        """
        self._beendet = True  # keine neuen Timer und Abrufe mehr
        await super().async_shutdown()
        # Laufende Abrufe sollen danach nichts mehr speichern oder anstoßen.
        for abruf in (self._schul_abruf, self._urlaub_abruf, self._feiertage_abruf):
            if abruf is not None and not abruf.done():
                abruf.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await abruf
        self._kalender_beobachten([])
        self.timer_abmelden()
        self._schalter.abmelden()
        while self._abmelden:
            self._abmelden.pop()()
        if self._geladen:
            await self._store.async_save(self._speicherdaten())

    # ------------------------------------------------------------ Rechnen

    def _ids(self, typ: str) -> list[str]:
        """IDs aller Untereinträge eines Typs."""
        return [
            sid
            for sid, sub in self.config_entry.subentries.items()
            if sub.subentry_type == typ
        ]

    def _personen_ids(self) -> list[str]:
        """IDs aller Personen-Untereinträge."""
        return self._ids(SUBENTRY_PERSON)

    def _zeitplan(self, sid: str) -> Zeitplan | None:
        """Zeitplan eines Untereintrags; None bei ungültigen Daten.

        Ungültig wird er nur durch beschädigte Daten (der Dialog prüft beim
        Speichern). Gemeldet wird beim Wechsel: Warnung im Log und Hinweis
        unter „Reparaturen“ (E46), der verschwindet, sobald er wieder gilt.
        """
        sub = self.config_entry.subentries[sid]
        try:
            zeitplan = zeitplan_aus_daten(sub.data.get(CONF_ZEITPLAN) or {})
        except ValueError:
            # Nur beim Wechsel melden, nicht bei jedem Lauf (log-when-unavailable).
            if sid not in self._ungueltig:
                _LOGGER.warning("Ungültiger Zeitplan bei %s", sub.title)
                self._ungueltig.add(sid)
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    f"{ISSUE_ZEITPLAN}_{sid}",
                    config_entry_id=self.config_entry.entry_id,
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key=f"{ISSUE_ZEITPLAN}_{sub.subentry_type}",
                    translation_placeholders={"name": sub.title},
                )
            return None
        if sid in self._ungueltig:
            _LOGGER.info("Zeitplan bei %s ist wieder gültig", sub.title)
            self._ungueltig.discard(sid)
            ir.async_delete_issue(self.hass, DOMAIN, f"{ISSUE_ZEITPLAN}_{sid}")
        return zeitplan

    def _hinweise(self, art: str) -> list[str]:
        """IDs aller bestehenden HomeWake-Hinweise einer Art (auch von früher)."""
        return [
            issue_id
            for domain, issue_id in ir.async_get(self.hass).issues
            if domain == DOMAIN and issue_id.startswith(f"{art}_")
        ]

    @callback
    def _alte_zeitplan_hinweise_pruefen(self) -> None:
        """Beim Start: Zeitplan-Hinweise gelöschter Untereinträge entfernen.

        Die übrigen bleiben stehen (ein „Ignorieren“ des Nutzers bleibt so
        erhalten) und gelten als gemeldet; ist der Zeitplan inzwischen gültig,
        entfernt der erste Lauf den Hinweis.
        """
        for issue_id in self._hinweise(ISSUE_ZEITPLAN):
            sid = issue_id.removeprefix(f"{ISSUE_ZEITPLAN}_")
            if sid in self.config_entry.subentries:
                self._ungueltig.add(sid)
            else:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    @callback
    def _alte_raum_hinweise_pruefen(self) -> None:
        """Beim Start: „Raum verloren“ behalten, solange die Person keinen Raum hat.

        Hinweise gelöschter Personen und solcher, die inzwischen wieder einen
        zuordenbaren Raum haben, werden entfernt; die übrigen merkt sich
        HomeWake, damit sie verschwinden, sobald die Person einen Raum bekommt
        (ein „Ignorieren“ bleibt so erhalten).
        """
        raeume = {
            rid
            for rid in self._ids(SUBENTRY_RAUM)
            if self.config_entry.subentries[rid].data.get(CONF_ZUORDENBAR, True)
        }
        for issue_id in self._hinweise(ISSUE_RAUM_VERLOREN):
            pid = issue_id.removeprefix(f"{ISSUE_RAUM_VERLOREN}_")
            if pid in self._bedienung and self._bedienung[pid].raum_id not in raeume:
                self._raum_hinweis.add(pid)
            else:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    @callback
    def _raum_hinweis_weg(self, pid: str) -> None:
        """Hinweis „Raum verloren“ einer Person entfernen."""
        if pid in self._raum_hinweis:
            self._raum_hinweis.discard(pid)
            ir.async_delete_issue(self.hass, DOMAIN, f"{ISSUE_RAUM_VERLOREN}_{pid}")

    @callback
    def _raum_hinweise_pflegen(self, ergebnis: HausErgebnis) -> None:
        """Hinweis „Raum verloren“ zeigen bzw. entfernen (E11, 5.5)."""
        for pid in ergebnis.raum_verloren:
            sub = self.config_entry.subentries[pid]
            _LOGGER.warning(
                "Raum von %s gelöscht oder nicht mehr zuordenbar: kein Raum", sub.title
            )
            self._raum_hinweis.add(pid)
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"{ISSUE_RAUM_VERLOREN}_{pid}",
                config_entry_id=self.config_entry.entry_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_RAUM_VERLOREN,
                translation_placeholders={"person": sub.title},
            )
        for pid, bedienung in ergebnis.bedienung.items():
            if bedienung.raum_id is not None:
                self._raum_hinweis_weg(pid)

    @callback
    def _geraete_pruefen(self) -> None:
        """Hinweis „Gerät fehlt“ pro Raum zeigen bzw. entfernen (5.5).

        Fehlend ist ein eingetragenes Licht oder ein Lautsprecher, den HA
        weder in der Entity-Registry noch als Zustand kennt (gelöscht,
        umbenannt), oder der deaktiviert ist. Ein nur nicht verfügbares Gerät
        zählt nicht; dafür gibt es den erneuten Versuch beim Schalten.
        Geprüft wird erst, wenn HA gestartet ist, weil beim Booten viele
        Geräte noch fehlen. Gemeldet
        wird nur beim Wechsel; Hinweise gelöschter Räume verschwinden.
        """
        if self.hass.state is not CoreState.running or self._beendet:
            return
        raeume = self._ids(SUBENTRY_RAUM)
        for issue_id in self._hinweise(ISSUE_GERAET):
            if issue_id.removeprefix(f"{ISSUE_GERAET}_") not in raeume:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        registry = er.async_get(self.hass)
        for rid in raeume:
            sub = self.config_entry.subentries[rid]
            geraete = [str(e) for e in sub.data.get(CONF_LICHTER) or ()]
            if (lautsprecher := self.lautsprecher(rid)) is not None:
                geraete.append(lautsprecher)
            fehlend = [
                eid
                for eid in geraete
                if self.hass.states.get(eid) is None
                and (
                    (eintrag := registry.async_get(eid)) is None
                    or eintrag.disabled_by is not None
                )
            ]
            if not fehlend:
                if self._geraet_fehlt.pop(rid, None) is not None:
                    _LOGGER.info("Alle Geräte von %s sind wieder da", sub.title)
                # Auch einen Hinweis aus der Zeit vor einem Neustart entfernen
                ir.async_delete_issue(self.hass, DOMAIN, f"{ISSUE_GERAET}_{rid}")
                continue
            if self._geraet_fehlt.get(rid) == fehlend:
                continue
            self._geraet_fehlt[rid] = fehlend
            _LOGGER.warning(
                "Geräte von %s fehlen in Home Assistant: %s",
                sub.title,
                ", ".join(fehlend),
            )
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"{ISSUE_GERAET}_{rid}",
                config_entry_id=self.config_entry.entry_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_GERAET,
                translation_placeholders={
                    "raum": sub.title,
                    "geraete": ", ".join(fehlend),
                },
            )

    @callback
    def _favoriten_pruefen(self) -> None:
        """Hinweis „Favorit fehlt“ pro Person bzw. Raum zeigen oder entfernen (E56).

        Geprüft wird der Radio-Favorit jeder Person gegen die Favoritenliste
        des Lautsprechers in ihrem Raum und der Standard-Favorit jedes Raums
        gegen die eigene Liste. Ist die Liste gerade leer (Lautsprecher nicht
        verfügbar oder startet neu), bleibt der bisherige Stand samt Hinweis
        stehen, damit ein „Ignorieren“ des Nutzers erhalten bleibt. Beim
        Wecken spielt der Standard-Favorit bzw. der erste Eintrag der Liste.
        Gemeldet wird nur beim Wechsel; Hinweise gelöschter Personen und
        Räume, ohne Raum oder ohne Favorit verschwinden.
        """
        if self.hass.state is not CoreState.running or self._beendet:
            return
        subentries = self.config_entry.subentries
        fehlend, offen = self._favoriten_stand()
        # Hinweise, die nicht mehr gelten (auch von vor einem Neustart)
        for issue_id in self._hinweise(ISSUE_FAVORIT):
            sid = issue_id.removeprefix(f"{ISSUE_FAVORIT}_")
            if sid not in fehlend and sid not in offen:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        for sid in set(self._favorit_fehlt) - set(fehlend) - offen:
            del self._favorit_fehlt[sid]
            titel = subentries[sid].title if sid in subentries else sid
            _LOGGER.info("Hinweis „Favorit fehlt“ für %s erledigt", titel)
        for sid, (schluessel, platzhalter) in fehlend.items():
            if self._favorit_fehlt.get(sid) == platzhalter:
                continue
            self._favorit_fehlt[sid] = platzhalter
            _LOGGER.warning(
                "Favorit %s von %s fehlt in der Favoritenliste des Lautsprechers",
                platzhalter["favorit"],
                subentries[sid].title,
            )
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"{ISSUE_FAVORIT}_{sid}",
                config_entry_id=self.config_entry.entry_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=schluessel,
                translation_placeholders=platzhalter,
            )

    @callback
    def _ohne_liste_melden(self, raum_id: str, lautsprecher: str) -> None:
        """Radio blieb stumm, weil keine Favoritenliste kam: Hinweis (E58, E61).

        Der Schalter meldet das, wenn die Versuche nach 15 Minuten oder zum
        Aus-Zeitpunkt enden. Ist der Raum inzwischen weg, hat er einen anderen
        Lautsprecher oder ist die Liste schon da, gibt es keinen Hinweis.
        """
        if (
            self._beendet
            or raum_id not in self.config_entry.subentries
            or self.lautsprecher(raum_id) != lautsprecher
            or self.quellen(raum_id)
        ):
            return
        titel = self.config_entry.subentries[raum_id].title
        _LOGGER.warning(
            "%s in %s meldet keine Favoritenliste: kein Radio beim Wecken",
            lautsprecher,
            titel,
        )
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"{ISSUE_OHNE_LISTE}_{raum_id}",
            config_entry_id=self.config_entry.entry_id,
            # Entsteht nur beim Wecken: muss einen HA-Neustart samt Text überstehen
            is_persistent=True,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_OHNE_LISTE,
            translation_placeholders={"raum": titel, "lautsprecher": lautsprecher},
        )

    @callback
    def _ohne_liste_pruefen(self) -> None:
        """Hinweise „Lautsprecher ohne Favoritenliste“ entfernen, die nicht mehr gelten.

        Weg ist der Hinweis, sobald der Lautsprecher eine Liste meldet, der
        Raum einen anderen oder keinen Lautsprecher hat oder gelöscht ist
        (auch für Hinweise von vor einem Neustart). Meldet der Lautsprecher
        gerade gar nichts (nicht verfügbar), bleibt der Hinweis stehen.
        """
        registry = ir.async_get(self.hass)
        for issue_id in self._hinweise(ISSUE_OHNE_LISTE):
            rid = issue_id.removeprefix(f"{ISSUE_OHNE_LISTE}_")
            issue = registry.async_get_issue(DOMAIN, issue_id)
            gemeldet = (
                (issue.translation_placeholders or {}).get("lautsprecher")
                if issue is not None
                else None
            )
            # Ohne gemeldeten Lautsprecher (Rest ohne Text) zählt nur der Raum
            if (
                rid in self.config_entry.subentries
                and (lautsprecher := self.lautsprecher(rid)) is not None
                and gemeldet in (None, lautsprecher)
                and not self.quellen(rid)
            ):
                continue
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            sub = self.config_entry.subentries.get(rid)
            _LOGGER.info(
                "Hinweis „Lautsprecher ohne Favoritenliste“ für %s erledigt",
                sub.title if sub is not None else rid,
            )

    def hat_aktorik(self, raum_id: str) -> bool:
        """Ob ein Raum Lichter oder einen Lautsprecher schaltet."""
        daten = self.config_entry.subentries[raum_id].data
        return bool(daten.get(CONF_LICHTER)) or self.lautsprecher(raum_id) is not None

    @callback
    def wecken_beenden(self, raum_id: str) -> None:
        """Taste „Wecken beenden“: Licht und Radio jetzt aus (E53, E60)."""
        titel = self.config_entry.subentries[raum_id].title
        if self._schalter.beenden(raum_id):
            _LOGGER.info("Wecken in %s von Hand beendet", titel)
        else:
            _LOGGER.debug("Wecken beenden in %s: kein laufendes Wecken", titel)

    def _favoriten_stand(
        self,
    ) -> tuple[dict[str, tuple[str, dict[str, str]]], set[str]]:
        """Fehlende Favoriten (ID → Übersetzung, Platzhalter) und offene IDs.

        Offen sind Personen/Räume, deren Lautsprecher gerade keine Liste
        meldet: Für sie wird nichts entschieden.
        """
        subentries = self.config_entry.subentries
        fehlend: dict[str, tuple[str, dict[str, str]]] = {}
        offen: set[str] = set()
        for pid in self._personen_ids():
            favorit = self.bedienung(pid).favorit
            raum = self.raum_id(pid)
            if favorit is None or raum is None or raum not in subentries:
                continue
            quellen = self.quellen(raum)
            if not quellen and self.lautsprecher(raum) is not None:
                offen.add(pid)
            elif quellen and favorit not in quellen:
                fehlend[pid] = (
                    f"{ISSUE_FAVORIT}_person",
                    {
                        "person": subentries[pid].title,
                        "favorit": favorit,
                        "raum": subentries[raum].title,
                    },
                )
        for rid in self._ids(SUBENTRY_RAUM):
            favorit = self._standard_favorit.get(rid)
            if favorit is None or self.lautsprecher(rid) is None:
                continue
            quellen = self.quellen(rid)
            if not quellen:
                offen.add(rid)
            elif favorit not in quellen:
                fehlend[rid] = (
                    f"{ISSUE_FAVORIT}_raum",
                    {"raum": subentries[rid].title, "favorit": favorit},
                )
        return fehlend, offen

    def _raeume_ungueltig(self, raeume: Mapping[str, RaumKonfig]) -> frozenset[str]:
        """Zuordenbare Räume, deren Standardplan nicht lesbar ist (E46)."""
        return frozenset(
            rid
            for rid in self._ids(SUBENTRY_RAUM)
            if rid not in raeume
            and bool(self.config_entry.subentries[rid].data.get(CONF_ZUORDENBAR, True))
        )

    def raum_konfig(self) -> dict[str, RaumKonfig]:
        """Konfiguration aller Räume mit gültigem Standardplan."""
        konfig: dict[str, RaumKonfig] = {}
        for sid in self._ids(SUBENTRY_RAUM):
            if (zeitplan := self._zeitplan(sid)) is None:
                continue
            daten = self.config_entry.subentries[sid].data
            konfig[sid] = RaumKonfig(
                standardplan=zeitplan,
                klemm_beginn=timedelta(minutes=daten.get(CONF_KLEMM_BEGINN, 60)),
                klemm_ende=timedelta(minutes=daten.get(CONF_KLEMM_ENDE, 60)),
                personen_zuordenbar=bool(daten.get(CONF_ZUORDENBAR, True)),
            )
        return konfig

    def raum_id(self, person_id: str) -> str | None:
        """Aktuell zugeordneter Raum einer Person."""
        return self._bedienung.get(person_id, PersonBedienung()).raum_id

    async def async_setze_raum(self, person_id: str, raum_id: str | None) -> None:
        """Raum einer Person setzen (Bedienung), neu rechnen und speichern."""
        await self.async_setze_bedienung(person_id, raum_id=raum_id)

    def _personen_konfig(self) -> dict[str, PersonKonfig]:
        """Konfiguration aller Personen; ein ungültiger Zeitplan wird übersprungen."""
        konfig: dict[str, PersonKonfig] = {}
        for sid in self._personen_ids():
            if (zeitplan := self._zeitplan(sid)) is None:
                continue
            titel = self.config_entry.subentries[sid].title
            konfig[sid] = PersonKonfig(zeitplan=zeitplan, name=titel)
        return konfig

    async def _async_update_data(self) -> HausErgebnis:
        """Ein Lauf: Eingaben lesen, rechnen, Zustand übernehmen, Timer stellen.

        Der Lauf enthält **kein** ``await`` (E45): Er wartet nie auf Kalender,
        Feiertags-Bibliothek oder Netz, sondern rechnet mit dem, was vorliegt.
        Was fehlt, holen Hintergrund-Abrufe; ein fertiger Abruf stößt einen
        neuen Lauf an. So hält nichts den Wecker-Timer oder die Bedienung auf
        (HA lässt immer nur einen Lauf zur Zeit rechnen), und „jetzt“ ist beim
        Rechnen nie veraltet.

        Wirft die Rechnung unerwartet einen Fehler, wird kein neuer Timer gestellt;
        der Sicherheitslauf (E29) rechnet spätestens nach 10 Minuten erneut.
        """
        raeume = self.raum_konfig()
        # Ein Raum mit kaputtem Plan bleibt wählbar und behält seine Personen (E46).
        ungueltig = self._raeume_ungueltig(raeume)
        self.zuordenbare_raeume = {
            rid: self.config_entry.subentries[rid].title
            for rid in self._ids(SUBENTRY_RAUM)
            if rid in ungueltig or (rid in raeume and raeume[rid].personen_zuordenbar)
        }
        jetzt = dt_util.now()
        self._feiertage_pflegen(jetzt)
        self._urlaub_pflegen()
        self._schulferien_pflegen(jetzt)
        ergebnis = self._rechne(self._bedienung, raeume, jetzt=jetzt)
        self._bedienung.update(ergebnis.bedienung)
        self._raum_hinweise_pflegen(ergebnis)
        self._geraete_pruefen()
        self._favoriten_pruefen()
        self._ohne_liste_pruefen()
        for sid, person in ergebnis.personen.items():
            self._zustaende[sid] = person.zustand
        # Während des Laufs keine Zwischenstände zeigen (E64): Der Lauf
        # benachrichtigt die Entities am Ende ohnehin mit den neuen Werten.
        self._im_lauf = True
        try:
            for sid, raum in ergebnis.raeume.items():
                self._raum_zustaende[sid] = raum.zustand
                if raum.jetzt_geweckt:
                    self._wecken_schalten(sid, raum)
        finally:
            self._im_lauf = False
        # Nach Wecken oder Ausnahme-Löschen sofort speichern (kein doppeltes
        # Wecken nach einem Neustart): eigene Aufgabe mit dem Stand von jetzt,
        # damit der Lauf nicht wartet. Nicht ``async_delay_save(…, 0)``: Ein
        # folgender Lauf mit Verzögerung würde dieses Schreiben hinausschieben.
        if any(
            p.jetzt_geweckt or p.ausnahme_loeschen for p in ergebnis.personen.values()
        ) or any(r.jetzt_geweckt for r in ergebnis.raeume.values()):
            self.config_entry.async_create_task(
                self.hass,
                self._store.async_save(self._speicherdaten()),
                "homewake_speichern",
            )
        else:
            self._store.async_delay_save(self._speicherdaten, SPEICHER_VERZOEGERUNG)
        self._stelle_timer(ergebnis.naechste_aenderung)
        return ergebnis

    def _wecken_schalten(self, raum_id: str, raum: RaumErgebnis) -> None:
        """Raum gerade geweckt: Schaltplan rechnen und an den Schalter geben (A1).

        Beim Booten (Nachholen, E28) erst, wenn HA fertig gestartet ist: Vorher
        fehlen oft noch Lichter und die Favoriten des Lautsprechers.
        """
        if raum.geweckt_um is None or not (raum.licht or raum.radio):
            return
        self._schalter.nach_start(partial(self._wecken_jetzt, raum_id, raum))

    @callback
    def _wecken_jetzt(self, raum_id: str, raum: RaumErgebnis) -> None:
        """Schaltplan rechnen und schalten lassen; ohne Warten (E45).

        Sonnenhöhe und Quellen des Lautsprechers werden nur gelesen,
        geschaltet wird in einer eigenen Aufgabe. Ein Fehler hier (z. B.
        beschädigte Raumdaten) wird geloggt und stört den Lauf nicht.
        """
        jetzt = dt_util.now()
        try:
            plan = self._schaltplan(raum_id, raum, jetzt)
        except Exception:
            _LOGGER.exception(
                "Schalten in %s fehlgeschlagen",
                self.config_entry.subentries[raum_id].title,
            )
            return
        if plan is not None:
            self._schalter.wecken(raum_id, plan)

    def _schaltplan(
        self, raum_id: str, raum: RaumErgebnis, jetzt: datetime
    ) -> Schaltplan | None:
        """Schaltplan eines Raums aus Konfiguration und aktuellen Gerätedaten."""
        if raum.geweckt_um is None:
            return None
        daten = self.config_entry.subentries[raum_id].data
        return schaltplan(
            AktorikEingaben(
                konfig=AktorikKonfig(
                    lichter=tuple(daten.get(CONF_LICHTER) or ()),
                    helligkeit=int(daten.get(CONF_HELLIGKEIT, 100)),
                    elevation=float(daten.get(CONF_ELEVATION, -3.0)),
                    dauer=timedelta(minutes=daten.get(CONF_DAUER, 45)),
                    lautsprecher=self.lautsprecher(raum_id),
                    lautstaerke=int(daten.get(CONF_LAUTSTAERKE, 30)),
                ),
                licht=raum.licht,
                radio=raum.radio,
                favorit=raum.favorit,
                standard_favorit=self._standard_favorit.get(raum_id),
                geweckt_um=raum.geweckt_um,
                # Sonnenhöhe im Schaltzeitpunkt (E51, E54)
                sonnenhoehe=sonne.sonnenhoehe(self.hass, jetzt),
            ),
            jetzt=jetzt,
        )

    def _rechne(
        self,
        bedienung: Mapping[str, PersonBedienung],
        raeume: Mapping[str, RaumKonfig] | None = None,
        *,
        jetzt: datetime | None = None,
    ) -> HausErgebnis:
        """Reine Rechnung mit den aktuellen Eingaben (ohne etwas zu übernehmen).

        Alle Teile eines Laufs nutzen dasselbe „jetzt“ (5.1). Feiertage kommen
        aus den vorab geladenen Jahren; fehlt ein Jahr noch, gilt kein Feiertag.
        """
        jetzt = jetzt or dt_util.now()
        personen = self._personen_konfig()
        sonne_heute, sonne_morgen = self._sonne(jetzt.date())
        heute, morgen = self._feiertag_namen(jetzt.date())
        tage = {sid: self._tage(sid, jetzt.date(), heute, morgen) for sid in personen}
        if raeume is None:
            raeume = self.raum_konfig()
        return berechne_haus(
            HausEingaben(
                personen=personen,
                bedienung=bedienung,
                zustaende=self._zustaende,
                tage=tage,
                raeume=raeume,
                raeume_ungueltig=self._raeume_ungueltig(raeume),
                raum_zustaende=self._raum_zustaende,
                feiertag_heute=heute is not None,
                feiertag_morgen=morgen is not None,
                sonne_heute=sonne_heute,
                sonne_morgen=sonne_morgen,
            ),
            jetzt=jetzt,
            zeitzone=dt_util.get_default_time_zone(),
        )

    def _sonne(self, heute: date) -> tuple[Sonne, Sonne]:
        """Dawn/Dusk für heute und morgen mit dem gewählten Sonnenstand (E30)."""
        daten = self.config_entry.data
        grad_morgen = grad(
            daten.get(CONF_SONNE_MORGEN, STANDARD_SONNENSTAND),
            daten.get(CONF_GRAD_MORGEN),
        )
        grad_abend = grad(
            daten.get(CONF_SONNE_ABEND, STANDARD_SONNENSTAND),
            daten.get(CONF_GRAD_ABEND),
        )
        return (
            sonne.sonne(self.hass, heute, grad_morgen, grad_abend),
            sonne.sonne(self.hass, heute + timedelta(days=1), grad_morgen, grad_abend),
        )

    def _feiertag_ort(self) -> Ort | None:
        """Land, Region und Sprache der Feiertage (E9); None ohne Land.

        Ohne Land im Eintrag gilt das Land der HA-Einstellungen.
        """
        land = self.config_entry.data.get(CONF_LAND) or self.hass.config.country
        if not land:
            return None
        return (
            land,
            self.config_entry.data.get(CONF_BUNDESLAND),
            self.hass.config.language,
        )

    def _feiertag_namen(self, heute: date) -> tuple[str | None, str | None]:
        """Namen der Feiertage heute und morgen aus den geladenen Jahren."""
        if (ort := self._feiertag_ort()) is None:
            return None, None
        namen: list[str | None] = []
        for tag in (heute, heute + timedelta(days=1)):
            tabelle = self._feiertage.get((*ort, tag.year))
            namen.append(tabelle.get(tag) if tabelle is not None else None)
        return namen[0], namen[1]

    @callback
    def _feiertage_pflegen(self, jetzt: datetime) -> None:
        """Pro Lauf: dieses und nächstes Jahr bereithalten, sonst nachladen (E45).

        Fehlt ein Jahr (Land, Region oder Sprache geändert), lädt ein
        Hintergrund-Abruf nach und stößt danach einen Lauf an. Ist das Laden
        für diesen Ort schon gescheitert, wird es erst nach einer Änderung oder
        einem Neustart wieder versucht.
        """
        if (ort := self._feiertag_ort()) is None:
            return
        jahre = [jetzt.year, jetzt.year + 1]
        # Nur die gerade gebrauchten Jahre behalten.
        self._feiertage = {
            k: v for k, v in self._feiertage.items() if k[:3] == ort and k[3] in jahre
        }
        fehlend = [j for j in jahre if (*ort, j) not in self._feiertage]
        if (
            not fehlend
            or ort in self._feiertage_gescheitert
            or (self._feiertage_abruf is not None and not self._feiertage_abruf.done())
        ):
            return
        self._feiertage_abruf = self.config_entry.async_create_background_task(
            self.hass, self._feiertage_nachladen(ort, fehlend), "homewake_feiertage"
        )

    async def _feiertage_nachladen(self, ort: Ort, jahre: list[int]) -> None:
        """Fehlende Jahre im Hintergrund laden, danach neu rechnen.

        Ein unerwarteter Fehler wird mit Traceback geloggt; gerechnet wird
        trotzdem (ohne Feiertage dieses Orts).
        """
        try:
            await self._feiertage_laden(ort, jahre)
        except Exception:
            _LOGGER.exception("Unerwarteter Fehler beim Laden der Feiertage")
        finally:
            self._feiertage_abruf = None
        await self.async_refresh()

    async def _feiertage_laden(self, ort: Ort, jahre: list[int]) -> None:
        """Feiertage der Jahre über die Bibliothek ``holidays`` laden.

        Kennt die Bibliothek Land oder Region nicht, rechnet HomeWake ohne
        Feiertage weiter und meldet das unter „Reparaturen“ (E37).
        """
        land, region, sprache = ort
        geklappt = False
        try:
            for jahr in jahre:
                self._feiertage[
                    (*ort, jahr)
                ] = await self.hass.async_add_import_executor_job(
                    feiertage.feiertage, land, region, jahr, sprache
                )
            geklappt = True
        except (NotImplementedError, KeyError, ValueError) as err:
            if not self._feiertage_fehler:
                _LOGGER.warning(
                    "Feiertage für %s/%s nicht verfügbar: %s", land, region, err
                )
                self._feiertage_fehler = True
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    ISSUE_FEIERTAGE,
                    config_entry_id=self.config_entry.entry_id,
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key=ISSUE_FEIERTAGE,
                    translation_placeholders={"land": land, "region": region or "-"},
                )
        finally:
            # Auch bei unerwarteten Fehlern nicht in jedem Lauf erneut versuchen.
            if not geklappt:
                self._feiertage_gescheitert.add(ort)
        if geklappt and self._feiertage_fehler:
            self._feiertage_fehler = False
            ir.async_delete_issue(self.hass, DOMAIN, ISSUE_FEIERTAGE)

    # ------------------------------------------------------------ Urlaub

    def _kalender_der_personen(self) -> dict[str, str]:
        """Urlaubskalender jeder Person, die einen eingetragen hat."""
        kalender: dict[str, str] = {}
        for sid in self._personen_ids():
            wert = self.config_entry.subentries[sid].data.get(CONF_URLAUBSKALENDER)
            if isinstance(wert, str) and wert:
                kalender[sid] = wert
        return kalender

    @callback
    def _urlaub_pflegen(self) -> None:
        """Pro Lauf: Kalender-Änderungen erkennen, Beobachtung und Abruf (E45).

        Ohne Kalender verfällt der alte Urlaub einer Person (E38), ebenso beim
        Wechsel auf einen anderen Kalender. Ein neuer oder geänderter Kalender
        (auch beim Start) wird sofort im Hintergrund gelesen.
        """
        kalender = self._kalender_der_personen()
        for sid in self._personen_ids():
            if sid not in kalender:
                self._kalender_lesbar(sid)
                self._urlaub.pop(sid, None)  # ohne Kalender kein alter Urlaub
        if kalender == self._urlaub_kalender:
            return
        for sid, alt in self._urlaub_kalender.items():
            if sid in kalender and kalender[sid] != alt:
                self._urlaub.pop(sid, None)  # Urlaub des alten Kalenders
                self._kalender_lesbar(sid)
        self._urlaub_kalender = kalender
        self._kalender_beobachten(kalender.values())
        self._urlaub_anstossen()

    @callback
    def _kalender_beobachten(self, kalender: Iterable[str]) -> None:
        """Zustandsänderungen der Kalender-Entities beobachten (neu anmelden)."""
        if self._kalender_beobachtung is not None:
            self._kalender_beobachtung()
            self._kalender_beobachtung = None
        if entities := sorted(set(kalender)):
            self._kalender_beobachtung = async_track_state_change_event(
                self.hass, entities, self._kalender_geaendert
            )

    @callback
    def _kalender_geaendert(self, _event: Event[EventStateChangedData]) -> None:
        """Ein Kalender hat seinen Zustand geändert (neuer Termin, wieder da)."""
        self._urlaub_anstossen()

    @callback
    def _urlaub_anstossen(self) -> None:
        """Kalender im Hintergrund lesen; läuft schon ein Abruf, danach erneut."""
        if not self._urlaub_kalender or self._beendet:
            return
        if self._urlaub_abruf is not None and not self._urlaub_abruf.done():
            self._urlaub_nochmal = True
            return
        self._urlaub_abruf = self.config_entry.async_create_background_task(
            self.hass, self._urlaub_abrufen(), "homewake_urlaub"
        )

    async def _urlaub_abrufen(self) -> None:
        """Alle Kalender lesen (so oft wie angestoßen), danach neu rechnen.

        Ein unerwarteter Fehler wird mit Traceback geloggt; es gilt der zuletzt
        gelesene Urlaub, und gerechnet wird trotzdem.
        """
        try:
            while True:
                self._urlaub_nochmal = False
                await self._lade_urlaub(dt_util.now())
                if not self._urlaub_nochmal:
                    break
        except Exception:
            _LOGGER.exception("Unerwarteter Fehler beim Lesen der Urlaubskalender")
        finally:
            # Als fertig markieren: ein Anlass während des Laufs startet neu.
            self._urlaub_abruf = None
        await self.async_refresh()

    async def _lade_urlaub(self, jetzt: datetime) -> None:
        """Urlaub heute/morgen für jede Person mit Urlaubskalender (3.6, E38).

        Gefragt wird mit einem Tag Puffer auf beiden Seiten (gestern 00:00 bis
        in drei Tagen 00:00, HA-Zeit), weil Termine in ihrer eigenen Zeitzone
        zählen. Fehlt der Kalender oder scheitert die Abfrage, gilt der zuletzt
        gelesene Urlaub weiter (auch über einen Neustart, E38), sonst keiner;
        gemeldet wird nur der Wechsel (log-when-unavailable).
        """
        heute = jetzt.date()
        kalender = dict(self._urlaub_kalender)
        # Alle Kalender gleichzeitig fragen: ein langsamer verzögert nicht die übrigen.
        ergebnisse = await asyncio.gather(
            *(self._urlaub_einer_person(sid, k, jetzt) for sid, k in kalender.items())
        )
        for sid, werte in zip(kalender, ergebnisse, strict=True):
            if self._urlaub_kalender.get(sid) != kalender[sid]:
                continue  # Kalender inzwischen entfernt oder gewechselt
            if werte is not None:
                self._urlaub[sid] = werte
            else:  # Ausfall: letzten Stand behalten, nur Vergangenes vergessen
                alt = self._urlaub.get(sid, {})
                self._urlaub[sid] = {t: u for t, u in alt.items() if t >= heute}

    async def _urlaub_einer_person(
        self, sid: str, kalender: str, jetzt: datetime
    ) -> dict[date, bool] | None:
        """Urlaub einer Person für heute und morgen; None bei Fehler.

        Urlaub ist nur eine zusätzliche Eingabe. Darum wird hier **jeder** Fehler
        abgefangen: Auch eine fremde Kalender-Integration, die etwas Unerwartetes
        wirft, darf das Wecken der anderen Personen nicht verhindern.
        """
        sub = self.config_entry.subentries[sid]
        heute = jetzt.date()
        zeitzone = dt_util.get_default_time_zone()
        beginn = datetime.combine(heute - timedelta(days=1), time(), tzinfo=zeitzone)
        ende = datetime.combine(heute + timedelta(days=3), time(), tzinfo=zeitzone)
        try:
            eintraege = await self._kalender_eintraege(kalender, beginn, ende)
        except Exception as err:
            self._kalender_nicht_lesbar(sid, kalender, jetzt, err)
            return None
        if sid in self._kalender_fehler:
            _LOGGER.info(
                "Urlaubskalender %s von %s ist wieder lesbar", kalender, sub.title
            )
        self._kalender_lesbar(sid)
        termine = termine_aus_antwort(eintraege, zeitzone=zeitzone)
        morgen = heute + timedelta(days=1)
        return {heute: urlaub_an(termine, heute), morgen: urlaub_an(termine, morgen)}

    def _hinweis_id(self, sid: str) -> str:
        """ID des Reparatur-Hinweises „Urlaubskalender nicht verfügbar“ (E39)."""
        return f"{ISSUE_KALENDER}_{sid}"

    def _kalender_nicht_lesbar(
        self, sid: str, kalender: str, jetzt: datetime, err: Exception
    ) -> None:
        """Ausfall merken: Warnung beim Wechsel, Hinweis nach 30 Minuten (E39)."""
        sub = self.config_entry.subentries.get(sid)
        titel = sub.title if sub is not None else sid  # Person gerade entfernt
        neu = sid not in self._kalender_fehler
        seit = self._kalender_fehler.setdefault(sid, jetzt)
        if neu:
            _LOGGER.warning(
                "Urlaubskalender %s von %s nicht lesbar, nutze den zuletzt "
                "gelesenen Urlaub: %s",
                kalender,
                titel,
                err or type(err).__name__,
            )
        if sid in self._kalender_hinweis or jetzt - seit < KALENDER_HINWEIS_NACH:
            return
        self._kalender_hinweis.add(sid)
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._hinweis_id(sid),
            config_entry_id=self.config_entry.entry_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_KALENDER,
            translation_placeholders={"person": titel, "kalender": kalender},
        )

    @callback
    def _kalender_lesbar(self, sid: str) -> None:
        """Kalender wieder lesbar oder nicht mehr eingetragen: Ausfall vergessen.

        Der Hinweis wird immer entfernt, auch einer aus der Zeit vor einem
        Neustart (er steht in HAs Registry, nicht im Gedächtnis von HomeWake).
        """
        self._kalender_fehler.pop(sid, None)
        self._kalender_hinweis.discard(sid)
        ir.async_delete_issue(self.hass, DOMAIN, self._hinweis_id(sid))

    @callback
    def _alte_kalender_hinweise_entfernen(self) -> None:
        """Hinweise zu Personen entfernen, die es nicht mehr gibt."""
        personen = {self._hinweis_id(sid) for sid in self._personen_ids()}
        for domain, issue_id in list(ir.async_get(self.hass).issues):
            if (
                domain == DOMAIN
                and issue_id.startswith(f"{ISSUE_KALENDER}_")
                and issue_id not in personen
            ):
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    async def _kalender_eintraege(
        self, kalender: str, beginn: datetime, ende: datetime
    ) -> list[Any]:
        """Termine eines Kalenders über die Aktion ``calendar.get_events``.

        Fehlt die Kalender-Entity oder ist sie nicht verfügbar, wird gar nicht
        erst gefragt (sonst schreibt HA bei jedem Lauf selbst eine Warnung).
        Fehlt der Kalender in der Antwort, gilt er ebenfalls als nicht lesbar.
        """
        state = self.hass.states.get(kalender)
        if state is None or state.state == STATE_UNAVAILABLE:
            raise HomeAssistantError("Kalender fehlt oder ist nicht verfügbar")
        async with asyncio.timeout(KALENDER_TIMEOUT):
            antwort = await self.hass.services.async_call(
                "calendar",
                "get_events",
                {
                    "entity_id": kalender,
                    "start_date_time": beginn,
                    "end_date_time": ende,
                },
                blocking=True,
                return_response=True,
            )
        daten = (antwort or {}).get(kalender)
        if not isinstance(daten, Mapping):
            raise HomeAssistantError("keine Antwort für diesen Kalender")
        eintraege = daten.get("events")
        return eintraege if isinstance(eintraege, list) else []

    # ------------------------------------------------------------ Schulferien

    def _schule(self, sid: str) -> str | None:
        """``<anbieter>:<kennung>`` der Schule einer Person (E44).

        None ohne Schule, bei kaputten Daten oder unbekanntem Anbieter.
        """
        sub = self.config_entry.subentries[sid]
        wert = sub.data.get(CONF_SCHULE)
        if wert is None:
            return None
        schluessel = None
        if isinstance(wert, Mapping) and wert.get("anbieter") in ANBIETER:
            schluessel = schul_schluessel(wert)
        if schluessel is None and sid not in self._schule_ungueltig:
            # Einmal melden (z. B. Anbieter weggefallen), nicht bei jedem Lauf
            self._schule_ungueltig.add(sid)
            _LOGGER.warning(
                "Schule von %s ist ungültig oder ihr Anbieter wird nicht "
                "unterstützt; rechne ohne Schulferien. Bitte die Schule neu wählen",
                sub.title,
            )
        return schluessel

    def schulen(self) -> dict[str, str]:
        """Schulen aller Personen: ``<anbieter>:<kennung>`` → Name."""
        schulen: dict[str, str] = {}
        for sid in self._personen_ids():
            if (schluessel := self._schule(sid)) is None:
                continue
            name = self.config_entry.subentries[sid].data[CONF_SCHULE].get("name")
            schulen.setdefault(
                schluessel, name if isinstance(name, str) and name else schluessel
            )
        return schulen

    def schul_anzeige(self, sid: str) -> dict[str, Any] | None:
        """Schule, heutige und künftige Ferien und Stand für den Status-Sensor.

        None ohne Schule. Die Ferien kommen aus dem Speicher; vergangene
        werden ausgeblendet, auch wenn der letzte Abruf älter ist.
        """
        if (schluessel := self._schule(sid)) is None:
            return None
        heute = dt_util.now().date()
        daten = self._schulen.get(schluessel, SchulDaten())
        return {
            "schule": schul_pfad(self.config_entry.subentries[sid].data[CONF_SCHULE]),
            "schulferien": [
                {
                    "name": f.name,
                    "beginn": f.beginn.isoformat(),
                    "ende": f.ende.isoformat(),
                }
                for f in daten.ferien
                if f.ende >= heute
            ],
            "schulferien_stand": daten.abgerufen,
        }

    @callback
    def _schulferien_pflegen(self, jetzt: datetime) -> None:
        """Pro Lauf: Hinweise prüfen, Unbenutztes vergessen, Abruf anstoßen (E41).

        Der Abruf läuft als eigene Hintergrund-Aufgabe; der Lauf wartet nie aufs
        Netz und rechnet mit den gespeicherten Daten.
        """
        schulen = self.schulen()
        for schluessel in set(self._schulen) - set(schulen):
            self._schulen.pop(schluessel, None)
            self._schul_versucht.pop(schluessel, None)
            self._schul_fehler.pop(schluessel, None)
            self._schul_hinweis_weg(schluessel)
        for schluessel, name in schulen.items():
            daten = self._schulen.setdefault(schluessel, SchulDaten())
            if veraltet(
                abgerufen=daten.abgerufen,
                fehler_seit=self._schul_fehler.get(schluessel),
                jetzt=jetzt,
            ):
                self._schul_hinweis_zeigen(schluessel, name)
        if self._schul_abruf is not None and not self._schul_abruf.done():
            return
        faellig = [
            schluessel
            for schluessel in schulen
            if abruf_faellig(
                abgerufen=self._schulen[schluessel].abgerufen,
                versucht=self._schul_versucht.get(schluessel),
                jetzt=jetzt,
            )
        ]
        if faellig:
            self._schul_abruf = self.config_entry.async_create_background_task(
                self.hass, self._schulen_abrufen(faellig), "homewake_schulferien"
            )

    async def _schulen_abrufen(self, schluessel_liste: list[str]) -> None:
        """Schulferien der Schulen abrufen, speichern und neu rechnen (E41).

        Scheitert ein Abruf, bleiben die zuletzt geladenen Daten; gemeldet wird
        nur der Wechsel (log-when-unavailable).
        """
        jetzt = dt_util.now()
        heute = jetzt.date()
        ergebnisse = await asyncio.gather(
            *(
                ANBIETER[anbieter].ferien(self.hass, kennung, heute, heute + VORRAT)
                for anbieter, kennung in (s.split(":", 1) for s in schluessel_liste)
            ),
            return_exceptions=True,
        )
        schulen = self.schulen()
        for schluessel, ergebnis in zip(schluessel_liste, ergebnisse, strict=True):
            if schluessel not in schulen:
                continue  # inzwischen aus der Person entfernt
            name = schulen[schluessel]
            self._schul_versucht[schluessel] = jetzt
            if isinstance(ergebnis, asyncio.CancelledError):
                raise ergebnis
            if isinstance(ergebnis, BaseException):
                if schluessel not in self._schul_fehler:
                    # Unerwartetes (Programmierfehler) mit Traceback, sonst
                    # sähe es wie ein Netzausfall aus.
                    _LOGGER.warning(
                        "Schulferien der Schule %s nicht abrufbar, nutze die "
                        "zuletzt geladenen Daten: %s",
                        name,
                        ergebnis or type(ergebnis).__name__,
                        exc_info=None
                        if isinstance(ergebnis, AnbieterFehler)
                        else ergebnis,
                    )
                self._schul_fehler.setdefault(schluessel, jetzt)
                continue
            if self._schul_fehler.pop(schluessel, None) is not None:
                _LOGGER.info("Schulferien der Schule %s wieder abrufbar", name)
            self._schul_hinweis_weg(schluessel)
            self._schulen[schluessel] = SchulDaten(
                abgerufen=jetzt,
                ferien=tuple(f for f in ergebnis if f.ende >= heute),
            )
        # Sofort speichern: selten, und frische Daten überstehen so jeden Neustart.
        await self._store.async_save(self._speicherdaten())
        # Als fertig markieren, damit der folgende Lauf eine inzwischen neu
        # gewählte Schule gleich abruft (nicht erst im Sicherheitslauf).
        self._schul_abruf = None
        await self.async_refresh()

    def _schul_hinweis_id(self, schluessel: str) -> str:
        """ID des Reparatur-Hinweises „Schulferien-Daten veraltet“ (E42)."""
        return schul_hinweis_id(schluessel)

    @callback
    def _schul_hinweis_zeigen(self, schluessel: str, name: str) -> None:
        """Hinweis unter „Reparaturen“ zeigen (einmal pro Ausfall)."""
        if schluessel in self._schul_hinweis:
            return
        self._schul_hinweis.add(schluessel)
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._schul_hinweis_id(schluessel),
            config_entry_id=self.config_entry.entry_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_SCHULFERIEN,
            translation_placeholders={
                "schule": name,
                "anbieter": ANBIETER[schluessel.split(":", 1)[0]].titel,
            },
        )

    @callback
    def _schul_hinweis_weg(self, schluessel: str) -> None:
        """Hinweis entfernen (auch einen aus der Zeit vor einem Neustart)."""
        self._schul_hinweis.discard(schluessel)
        ir.async_delete_issue(self.hass, DOMAIN, self._schul_hinweis_id(schluessel))

    @callback
    def _alte_schul_hinweise_entfernen(self) -> None:
        """Hinweise zu Schulen entfernen, die keine Person mehr hat."""
        aktuell = {self._schul_hinweis_id(schluessel) for schluessel in self.schulen()}
        for domain, issue_id in list(ir.async_get(self.hass).issues):
            if (
                domain == DOMAIN
                and issue_id.startswith(f"{ISSUE_SCHULFERIEN}_")
                and issue_id not in aktuell
            ):
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    def _tage(
        self,
        sid: str,
        heute: date,
        feiertag_heute: str | None,
        feiertag_morgen: str | None,
    ) -> tuple[TagInfo, TagInfo]:
        """Feiertag und Urlaub einer Person für heute und morgen.

        Ein Tag ohne gelesenen Urlaub gilt als kein Urlaub.
        """
        tage = self._urlaub.get(sid, {})
        morgen = heute + timedelta(days=1)
        schluessel = self._schule(sid)
        ferien = (
            self._schulen.get(schluessel, SchulDaten()).ferien if schluessel else ()
        )
        return (
            TagInfo(
                feiertag=feiertag_heute,
                schulferien=schulferien_an(ferien, heute),
                urlaub=tage.get(heute, False),
            ),
            TagInfo(
                feiertag=feiertag_morgen,
                schulferien=schulferien_an(ferien, morgen),
                urlaub=tage.get(morgen, False),
            ),
        )

    # ------------------------------------------------------------ Bedienung

    async def async_setze_bedienung(self, person_id: str, **aenderungen: Any) -> None:
        """Bedienwerte einer Person ändern (geprüft), neu rechnen, speichern.

        Eine Ausnahme wird beim Einschalten bzw. beim Ändern ihrer Uhrzeit
        geprüft: nicht ohne Raum (E8), nicht ab Tagesende (E18). Abgelehnt wird
        mit einer übersetzten Meldung. Ausschalten setzt die Uhrzeit auf die
        Standard-Zeit zurück (E63).
        """
        alt = self._bedienung.get(person_id, PersonBedienung())
        neu = replace(alt, **aenderungen)
        if alt.ausnahme_aktiv and not neu.ausnahme_aktiv:
            # E63: ausgeschaltet → wieder die Standard-Zeit
            neu = replace(neu, ausnahme_zeit=None)
        if neu.ausnahme_aktiv and (
            not alt.ausnahme_aktiv or neu.ausnahme_zeit != alt.ausnahme_zeit
        ):
            self._pruefe_ausnahme(person_id, neu)
        self._bedienung[person_id] = neu
        if "raum_id" in aenderungen:
            # Bewusst gewählt, auch „kein Raum“: Hinweis erledigt (E11).
            self._raum_hinweis_weg(person_id)
        await self.async_refresh()
        await self._store.async_save(self._speicherdaten())

    @callback
    def _auftraege_geaendert(self) -> None:
        """Aus-Aufträge geändert: speichern und ``wecken_bis`` neu zeigen (E64).

        Aufträge enden auch ohne Lauf (Dauer abgelaufen, Taste), darum werden
        die Entities hier direkt benachrichtigt, außer mitten in einem Lauf.
        """
        self._store.async_delay_save(self._speicherdaten, SPEICHER_VERZOEGERUNG)
        if not self._im_lauf:
            self.async_update_listeners()

    def wecken_bis(self, raum_id: str) -> datetime | None:
        """Aus-Zeitpunkt des laufenden Weckens eines Raums, sonst None (E64)."""
        return self._schalter.wecken_bis(raum_id)

    def ausnahme_zeit(self, person_id: str) -> time | None:
        """Angezeigte Ausnahme-Uhrzeit: eigene Uhrzeit, sonst Standard-Beginn (E63).

        None nur, wenn der Zeitplan nicht lesbar ist (dann ist die Person
        ohnehin nicht verfügbar).
        """
        if (zeit := self.bedienung(person_id).ausnahme_zeit) is not None:
            return zeit
        daten = self.config_entry.subentries[person_id].data
        try:
            return zeitplan_aus_daten(daten.get(CONF_ZEITPLAN) or {}).standard.beginn
        except ValueError:
            return None

    def bedienung(self, person_id: str) -> PersonBedienung:
        """Aktuelle Bedienwerte einer Person (auch ohne gültigen Zeitplan)."""
        return self._bedienung.get(person_id, PersonBedienung())

    async def async_setze_licht_radio(
        self, person_id: str, profil: Profil, art: str, an: bool
    ) -> None:
        """Licht bzw. Radio eines Profils setzen (liest den aktuellen Stand)."""
        licht_radio = dict(self.bedienung(person_id).licht_radio)
        alt = licht_radio.get(profil, LichtRadio())
        licht_radio[profil] = replace(alt, **{art: an})
        await self.async_setze_bedienung(person_id, licht_radio=licht_radio)

    def _pruefe_ausnahme(self, person_id: str, neu: PersonBedienung) -> None:
        """Lehnt eine Ausnahme ab, die nicht zählen würde."""
        probe = self._rechne({**self._bedienung, person_id: neu}).personen.get(
            person_id
        )
        if probe is None or probe.status is PersonStatus.INAKTIV:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="ausnahme_inaktiv"
            )
        if probe.ausnahme_ignoriert:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="ausnahme_nach_tagesende"
            )

    def lautsprecher(self, raum_id: str | None) -> str | None:
        """Lautsprecher eines Raums laut Konfiguration."""
        if raum_id is None or raum_id not in self.config_entry.subentries:
            return None
        wert = self.config_entry.subentries[raum_id].data.get(CONF_LAUTSPRECHER)
        return wert if isinstance(wert, str) and wert else None

    def quellen(self, raum_id: str | None) -> list[str]:
        """Quellen/Favoriten des Raum-Lautsprechers (``source_list``)."""
        if (eid := self.lautsprecher(raum_id)) is None:
            return []
        state = self.hass.states.get(eid)
        liste = state.attributes.get("source_list") if state else None
        return [str(q) for q in liste] if isinstance(liste, list) else []

    def standard_favorit(self, raum_id: str) -> str | None:
        """Standard-Favorit eines Raums (Bedienung, E33)."""
        return self._standard_favorit.get(raum_id)

    async def async_setze_standard_favorit(
        self, raum_id: str, favorit: str | None
    ) -> None:
        """Standard-Favorit eines Raums setzen, neu rechnen und speichern (3.7)."""
        self._standard_favorit[raum_id] = favorit
        await self.async_refresh()
        await self._store.async_save(self._speicherdaten())

    @callback
    def _lautsprecher_geaendert(self, event: Event[EventStateChangedData]) -> None:
        """Geänderte Favoritenliste: Favoriten prüfen, Auswahl-Listen neu zeigen."""
        alt, neu = event.data["old_state"], event.data["new_state"]
        alt_liste = alt.attributes.get("source_list") if alt else None
        neu_liste = neu.attributes.get("source_list") if neu else None
        if alt_liste != neu_liste:
            self._favoriten_pruefen()
            self._ohne_liste_pruefen()
            self.async_update_listeners()

    def _speicherdaten(self) -> dict[str, Any]:
        """Bedienwerte und Zustände der vorhandenen Personen und Räume (JSON).

        Ein gelöschter Raum bleibt nur mit seinem offenen Aus-Auftrag
        gespeichert, bis der erledigt ist (4.7).
        """
        raeume = self._ids(SUBENTRY_RAUM)
        return {
            "personen": {
                sid: {
                    "bedienung": person_bedienung_zu_json(
                        self._bedienung.get(sid, PersonBedienung())
                    ),
                    "zustand": person_zustand_zu_json(
                        self._zustaende.get(sid, PersonZustand())
                    ),
                    "urlaub": urlaub_zu_json(self._urlaub.get(sid, {})),
                }
                for sid in self._personen_ids()
            },
            "raeume": {
                sid: {
                    "zustand": raum_zustand_zu_json(
                        self._raum_zustaende.get(sid, RaumZustand())
                    ),
                    "bedienung": {"standard_favorit": self._standard_favorit.get(sid)},
                    "aus": aus_auftrag_zu_json(self._schalter.auftraege.get(sid)),
                }
                for sid in raeume
            }
            | {
                sid: {"aus": aus_auftrag_zu_json(auftrag)}
                for sid, auftrag in self._schalter.auftraege.items()
                if sid not in raeume
            },
            "schulferien": {
                schluessel: schulferien_zu_json(
                    self._schulen.get(schluessel, SchulDaten())
                )
                for schluessel in self.schulen()
            },
        }

    # ------------------------------------------------------------ Diagnose

    def diagnose(self) -> dict[str, Any]:
        """Stand für die Diagnose-Datei (ungeschwärzt; das macht diagnostics.py).

        Vom Urlaub nur heute und morgen (was der Lauf nutzt). Schulen stehen
        nur unter einer laufenden Nummer, weil ihre Kennung den Ort verrät.
        Die Namen der Personen im Raum heißen hier ``im_raum``, damit sie
        geschwärzt werden können, ohne den Abschnitt „personen“ zu treffen.
        """
        heute = dt_util.now().date()
        tage = {heute.isoformat(), (heute + timedelta(days=1)).isoformat()}
        nummer = {
            schluessel: f"schule_{i}"
            for i, schluessel in enumerate(sorted(self.schulen()), start=1)
        }
        speicher = self._speicherdaten()
        for sid, person in speicher["personen"].items():
            # Welche Person welche (anonyme) Schule hat
            schule = self._schule(sid)
            person["schul_nummer"] = nummer.get(schule) if schule else None
            person["urlaub"] = {
                tag: wert for tag, wert in person["urlaub"].items() if tag in tage
            }
        speicher["schulferien"] = {
            nummer[schluessel]: daten
            for schluessel, daten in speicher["schulferien"].items()
        }
        ergebnis = als_json(self.data) if self.data is not None else None
        if ergebnis is not None:
            for raum in ergebnis["raeume"].values():
                raum["im_raum"] = raum.pop("personen")
        entry = self.config_entry
        return {
            "eintrag": {
                "version": entry.version,
                "minor_version": entry.minor_version,
                "data": dict(entry.data),
            },
            "untereintraege": {
                sid: {
                    "typ": sub.subentry_type,
                    "title": sub.title,
                    "data": dict(sub.data),
                }
                for sid, sub in entry.subentries.items()
            },
            "speicher": speicher,
            "ergebnis": ergebnis,
            "lauf": {
                "letzter_lauf_erfolgreich": self.last_update_success,
                "timer_gestellt": self._timer is not None,
            },
            "feiertage": {
                "geladen": sorted(
                    "/".join(str(teil or "-") for teil in schluessel)
                    for schluessel in self._feiertage
                ),
                "gescheitert": sorted(
                    "/".join(str(teil or "-") for teil in ort)
                    for ort in self._feiertage_gescheitert
                ),
            },
            "kalender": {
                "ausfall_seit": als_json(self._kalender_fehler),
                "hinweis": sorted(self._kalender_hinweis),
            },
            "schulen": {
                name: {
                    "versucht": als_json(self._schul_versucht.get(schluessel)),
                    "fehler_seit": als_json(self._schul_fehler.get(schluessel)),
                    "hinweis": schluessel in self._schul_hinweis,
                }
                for schluessel, name in nummer.items()
            },
            "hinweise": {
                "raum_verloren": sorted(self._raum_hinweis),
                "zeitplan_ungueltig": sorted(self._ungueltig),
                "geraet_fehlt": sorted(self._geraet_fehlt),
                "favorit_fehlt": sorted(self._favorit_fehlt),
                "lautsprecher_ohne_liste": sorted(
                    i.removeprefix(f"{ISSUE_OHNE_LISTE}_")
                    for i in self._hinweise(ISSUE_OHNE_LISTE)
                ),
            },
            "schalten": self._schalter.diagnose(),
        }

    # ------------------------------------------------------------ Zeitplaner

    def _stelle_timer(self, zeitpunkt: datetime) -> None:
        """Genauer Timer auf die nächste Änderung (ersetzt einen alten Timer)."""
        self.timer_abmelden()
        if self._beendet:
            return
        self._timer = async_track_point_in_utc_time(
            self.hass, self._faellig, zeitpunkt.astimezone(UTC)
        )

    @callback
    def timer_abmelden(self) -> None:
        """Meldet den genauen Timer ab (auch für Tests)."""
        if self._timer is not None:
            self._timer()
            self._timer = None

    async def _faellig(self, _jetzt: datetime) -> None:
        """Der genaue Timer ist abgelaufen: neu rechnen."""
        self._timer = None
        await self.async_refresh()

    async def _sicherheitslauf(self, _jetzt: datetime) -> None:
        """Sicherheitslauf alle 10 Minuten (E29); liest auch die Kalender (E45)."""
        self._urlaub_anstossen()
        await self.async_refresh()

    @callback
    def _mitternacht(self, _jetzt: datetime) -> None:
        """Neuer Tag: Urlaub für den neuen „morgen“ lesen (E45)."""
        self._urlaub_anstossen()

    async def _config_geaendert(self, _event: Event) -> None:
        """HA-Zeitzone oder Standort geändert: neu rechnen."""
        await self.async_request_refresh()
