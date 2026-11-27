"""Schalt-Baustein: führt den Schaltplan in HA aus (ARCHITEKTUR.md 4.7).

Der Coordinator rechnet im Lauf den Schaltplan (reine Logik in
``logic/aktorik.py``) und übergibt ihn hier. Geschaltet wird in eigenen
Hintergrund-Aufgaben, eine pro Gerät, damit kein Lauf und kein anderes Gerät
auf ein Gerät wartet (E45, E52). Scheitert ein Gerät, wird es alle 30 Sekunden
und sofort beim Wiederkommen erneut versucht, bis zur Frist des Plans (E52).
Den Aus-Auftrag hält dieser Baustein; der Coordinator speichert ihn mit, so
übersteht er einen Neustart (E12). Ausgeschaltet wird nach E50 und E54, bei
nicht erreichbaren Geräten ebenfalls mit Wiederholung. Die Taste „Wecken
beenden“ zieht den Aus-Zeitpunkt auf jetzt vor (E60). Bleibt das Radio stumm,
weil der Lautsprecher keine Favoritenliste meldet, erfährt es der Coordinator
für den Hinweis E58 (E61).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    CALLBACK_TYPE,
    CoreState,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util

from .logic.aktorik import (
    NACHHOLEN_BIS,
    AusAuftrag,
    GeraetZustand,
    RadioBefehl,
    Schaltplan,
    aus_auftrag_beginnen,
    erreichbar,
    was_ausschalten,
)

_LOGGER = logging.getLogger(__name__)

ZEITLIMIT = 10  # Sekunden, die eine einzelne Aktion höchstens dauern darf
WIEDERHOLEN_NACH = timedelta(seconds=30)
# So lange nach dem Aus-Zeitpunkt wird das Ausschalten noch versucht
AUS_VERSUCHE = NACHHOLEN_BIS


class _NichtErreichbar(Exception):
    """Das Gerät fehlt in HA oder ist nicht verfügbar."""


class _KeineListe(_NichtErreichbar):
    """Der Lautsprecher meldet (noch) keine Favoritenliste (E55 (7))."""


class Schalter:
    """Schaltet Licht und Radio eines Raums und später wieder aus."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        speichern: Callable[[], None],
        ohne_liste: Callable[[str, str], None],
    ) -> None:
        """Legt den Baustein an.

        ``speichern`` lässt den Coordinator speichern; ``ohne_liste(raum_id,
        lautsprecher)`` meldet ein Radio, das ohne Favoritenliste stumm blieb.
        """
        self.hass = hass
        self._entry = entry
        self._speichern = speichern
        self._ohne_liste_melden = ohne_liste
        # Offene Aus-Aufträge pro Raum (wird mit dem Raum gespeichert)
        self.auftraege: dict[str, AusAuftrag] = {}
        self._timer: dict[str, CALLBACK_TYPE] = {}
        self._start_abmelden: list[CALLBACK_TYPE] = []
        # Laufende Einschalt-Aufgaben pro Raum und Geräte, die gerade auf
        # einen neuen Versuch warten (für die Diagnose)
        self._einschalten: dict[str, set[asyncio.Task[None]]] = {}
        self._ausschalten: dict[str, asyncio.Task[None]] = {}
        self._wiederholt: dict[str, set[str]] = {}
        # Räume, deren Radio gerade auf die Favoritenliste wartet (E61)
        self._ohne_liste: dict[str, str] = {}
        # Abgebrochene Einschalt-Aufgaben, die noch auslaufen, und Geräte,
        # deren Schaltbefehl beim Abbruch gerade unterwegs war
        self._auslaufend: dict[str, set[asyncio.Task[None]]] = {}
        self._unterwegs: dict[str, set[str]] = {}
        self._beendet = False

    # ------------------------------------------------------------ Lebenszyklus

    @callback
    def laden(self, auftraege: Mapping[str, AusAuftrag]) -> None:
        """Gespeicherte Aus-Aufträge übernehmen.

        Die Timer starten erst, wenn HA fertig gestartet ist: Dann kennen die
        Geräte ihren Zustand, und ein schon abgelaufener Auftrag schaltet
        sofort aus (E54).
        """
        self.auftraege = dict(auftraege)
        if self.auftraege:
            self.nach_start(self._timer_fuer_alle)

    @callback
    def nach_start(self, aktion: Callable[[], None]) -> None:
        """``aktion`` ausführen, sobald HA fertig gestartet ist (sonst sofort).

        Beim Entladen wird eine noch wartende Aktion verworfen.
        """
        if self.hass.state is CoreState.running:
            aktion()
            return

        @callback
        def _gestartet(_hass: HomeAssistant) -> None:
            if not self._beendet:
                aktion()

        self._start_abmelden.append(async_at_started(self.hass, _gestartet))

    @callback
    def _timer_fuer_alle(self) -> None:
        """HA ist gestartet: Timer für die gespeicherten Aufträge stellen."""
        for raum_id in list(self.auftraege):
            if raum_id not in self._timer:
                self._timer_stellen(raum_id)

    @callback
    def abmelden(self) -> None:
        """Beim Entladen: Timer und Versuche beenden; die Aufträge bleiben gespeichert.

        Laufende Versuche enden auch beim Neuladen (E55); danach speichert
        dieser Baustein nichts mehr, damit er den neuen Stand nicht überschreibt.
        """
        self._beendet = True
        while self._start_abmelden:
            self._start_abmelden.pop()()
        for raum_id in list(self._timer):
            self._timer_weg(raum_id)
        for raum_id in list(self._einschalten):
            self._einschalten_abbrechen(raum_id)
        self._auslaufend.clear()
        self._unterwegs.clear()
        for raum_id in list(self._ausschalten):
            self._ausschalten_abbrechen(raum_id)

    @callback
    def _merken(self) -> None:
        """Aufträge speichern lassen, aber nicht mehr nach dem Entladen."""
        if not self._beendet:
            self._speichern()

    def _aufgabe(
        self, coro: Coroutine[Any, Any, None], name: str
    ) -> asyncio.Task[None]:
        """Hintergrund-Aufgabe des Eintrags (beim Entladen abgebrochen)."""
        return self._entry.async_create_background_task(self.hass, coro, name)

    def wecken_bis(self, raum_id: str) -> datetime | None:
        """Aus-Zeitpunkt, solange das Wecken läuft (E64).

        Ab dem Ausschalten None, auch wenn ein nicht erreichbares Gerät noch
        erneut ausgeschaltet wird: Das Wecken selbst ist dann vorbei.
        """
        auftrag = self.auftraege.get(raum_id)
        if auftrag is None or raum_id in self._ausschalten:
            return None
        return auftrag.um

    def diagnose(self) -> dict[str, Any]:
        """Offene Aus-Aufträge und Geräte im Wiederholen, gezählt pro Raum."""
        return {
            "aus_auftraege": sorted(self.auftraege),
            "wiederholungen": {
                raum_id: len(geraete)
                for raum_id, geraete in sorted(self._wiederholt.items())
                if geraete
            },
        }

    # ------------------------------------------------------------ Einschalten

    @callback
    def wecken(self, raum_id: str, plan: Schaltplan) -> None:
        """Schaltplan eines gerade geweckten Raums ausführen.

        Der Aus-Auftrag steht danach sofort in ``auftraege`` (zunächst ohne
        Geräte) und füllt sich mit dem, was eingeschaltet wird. Versuche eines
        früheren Weckens im selben Raum enden hier, auch ein noch laufendes
        Ausschalten (dessen Geräte bleiben im neuen Auftrag).
        """
        self._einschalten_abbrechen(raum_id)
        self._ausschalten_abbrechen(raum_id)
        self.auftraege[raum_id] = aus_auftrag_beginnen(
            plan, self.auftraege.get(raum_id)
        )
        self._timer_stellen(raum_id)
        self._merken()
        aufgaben = self._einschalten.setdefault(raum_id, set())
        if (licht := plan.licht) is not None:
            for eid in licht.lichter:
                coro = self._licht_an(raum_id, eid, licht.helligkeit, plan.versuche_bis)
                aufgaben.add(self._aufgabe(coro, f"homewake_an_{raum_id}_{eid}"))
        if (radio := plan.radio) is not None:
            coro = self._radio_an(raum_id, radio, plan.versuche_bis)
            name = f"homewake_an_{raum_id}_{radio.lautsprecher}"
            aufgaben.add(self._aufgabe(coro, name))
        for aufgabe in aufgaben:
            aufgabe.add_done_callback(aufgaben.discard)

    @callback
    def beenden(self, raum_id: str) -> bool:
        """Taste „Wecken beenden“: den Aus-Zeitpunkt auf jetzt vorziehen (E60).

        Laufende Einschalt-Versuche enden sofort; ausgeschaltet wird wie nach
        der Dauer, also nur, was noch so ist, wie HomeWake es gesetzt hat
        (E50, E54), ein nicht erreichbares Gerät bis 15 Minuten lang erneut
        (E55 (4)). Danach ist der Aus-Auftrag weg. Gibt zurück, ob ein Wecken
        lief; ohne Aus-Auftrag passiert nichts, ebenso, wenn schon
        ausgeschaltet wird (die Versuche dafür laufen dann schon).
        """
        if raum_id in self._ausschalten:
            return False
        self._einschalten_abbrechen(raum_id)
        if (auftrag := self.auftraege.get(raum_id)) is None:
            return False
        self.auftraege[raum_id] = replace(auftrag, um=dt_util.now())
        self._merken()
        self._timer_stellen(raum_id)
        return True

    @callback
    def _einschalten_abbrechen(self, raum_id: str) -> None:
        """Noch laufende Einschalt-Versuche eines Raums abbrechen (ohne Hinweis)."""
        self._ohne_liste.pop(raum_id, None)
        for aufgabe in self._einschalten.pop(raum_id, set()):
            if aufgabe.cancel():
                self._auslaufend.setdefault(raum_id, set()).add(aufgabe)

    async def _schalten_unterwegs(
        self, raum_id: str, eid: str, aktion: Awaitable[None]
    ) -> None:
        """Schaltbefehl ausführen; bei Abbruch das Gerät als unklar merken.

        Ein abgebrochener Befehl kann das Gerät trotzdem noch erreichen (ein
        Sonos spielt oft schon beim Wählen der Quelle). Ein solches Gerät wird
        beim folgenden Ausschalten ohne Blick auf seinen Zustand ausgeschaltet
        (wie ein unklarer Zustand nach E54 (3)).
        """
        try:
            await aktion
        except asyncio.CancelledError:
            self._unterwegs.setdefault(raum_id, set()).add(eid)
            raise

    @callback
    def _stumm_melden(self, raum_id: str) -> None:
        """Radio wartete bis zum Ende auf die Favoritenliste: melden (E58, E61)."""
        if (eid := self._ohne_liste.pop(raum_id, None)) is not None:
            self._ohne_liste_melden(raum_id, eid)

    @callback
    def _ausschalten_abbrechen(self, raum_id: str) -> None:
        """Ein noch laufendes Ausschalten eines Raums abbrechen."""
        if (aufgabe := self._ausschalten.pop(raum_id, None)) is not None:
            aufgabe.cancel()

    @callback
    def _in_auftrag(
        self,
        raum_id: str,
        *,
        licht: str | None = None,
        lautsprecher: str | None = None,
        quelle: str | None = None,
    ) -> None:
        """Gerät vor der Aktion in den Aus-Auftrag nehmen.

        Schon vorher, damit ein Abbruch mitten in der Aktion (Aus-Zeitpunkt,
        neues Wecken) kein eingeschaltetes Gerät ohne Auftrag zurücklässt.
        Ausgeschaltet wird später ohnehin nur, was noch an ist bzw. die
        Weck-Quelle spielt (E50).
        """
        if (alt := self.auftraege.get(raum_id)) is None:
            return
        neu = alt
        if licht is not None and licht not in alt.lichter:
            neu = replace(alt, lichter=(*alt.lichter, licht))
        if lautsprecher is not None:
            neu = replace(alt, lautsprecher=lautsprecher, quelle=quelle)
        if neu != alt:
            self.auftraege[raum_id] = neu
            self._merken()

    async def _licht_an(
        self, raum_id: str, eid: str, helligkeit: int, bis: datetime
    ) -> None:
        """Ein Licht einschalten; ab dem ersten Schaltbefehl im Aus-Auftrag."""

        async def versuch() -> None:
            self._pruefe_erreichbar(eid)
            self._in_auftrag(raum_id, licht=eid)
            await self._schalten_unterwegs(
                raum_id,
                eid,
                self._aktion(
                    "light",
                    "turn_on",
                    {"entity_id": eid, "brightness_pct": helligkeit},
                ),
            )

        await self._wiederholen(raum_id, eid, versuch, bis)

    async def _radio_an(self, raum_id: str, radio: RadioBefehl, bis: datetime) -> None:
        """Lautstärke → Quelle → Play (4.7); die Quelle passend zur Liste jetzt.

        Meldet der Lautsprecher noch keine Favoritenliste (z. B. kurz nach
        seinem Neustart), gilt er als nicht erreichbar und wird erneut
        versucht (E55, E56).
        """
        eid = radio.lautsprecher

        async def versuch() -> None:
            self._ohne_liste.pop(raum_id, None)
            self._pruefe_erreichbar(eid)
            if (quelle := radio.quelle(self._quellen(eid))) is None:
                self._ohne_liste[raum_id] = eid
                msg = "noch keine Favoritenliste"
                raise _KeineListe(msg)
            if quelle not in (radio.favorit, radio.standard_favorit):
                _LOGGER.info("Kein Favorit in der Liste von %s: spiele %s", eid, quelle)
            await self._aktion(
                "media_player",
                "volume_set",
                {"entity_id": eid, "volume_level": radio.lautstaerke},
            )
            self._in_auftrag(raum_id, lautsprecher=eid, quelle=quelle)
            await self._schalten_unterwegs(
                raum_id, eid, self._quelle_und_play(eid, quelle)
            )

        geklappt, _ = await self._wiederholen(raum_id, eid, versuch, bis)
        if not geklappt:
            self._stumm_melden(raum_id)

    async def _quelle_und_play(self, eid: str, quelle: str) -> None:
        """Quelle wählen, dann Play (4.7)."""
        await self._aktion(
            "media_player", "select_source", {"entity_id": eid, "source": quelle}
        )
        await self._aktion("media_player", "media_play", {"entity_id": eid})

    # ------------------------------------------------------------ Wiederholen

    async def _wiederholen[T](
        self,
        raum_id: str,
        geraet: str,
        versuch: Callable[[], Awaitable[T]],
        bis: datetime,
    ) -> tuple[bool, T | None]:
        """``versuch`` ausführen, bei Fehler erneut, bis ``bis`` (E52).

        Ein Versuch scheitert an jedem Fehler (auch einer fremden Integration),
        am Zeitlimit oder daran, dass das Gerät fehlt bzw. nicht verfügbar
        ist. Neu versucht wird nach 30 Sekunden oder sofort, wenn das Gerät
        wieder verfügbar wird. Ins Log kommt nur der Wechsel: Warnung beim
        ersten Fehlschlag, Info beim späteren Erfolg, Warnung beim Aufgeben
        (E55). Gibt zurück, ob es geklappt hat, und das Ergebnis des Versuchs.
        """
        gescheitert = False
        try:
            while True:
                try:
                    async with asyncio.timeout(ZEITLIMIT):
                        ergebnis = await versuch()
                except Exception as err:
                    grund = (
                        "Zeitlimit überschritten"
                        if isinstance(err, TimeoutError)
                        else str(err) or type(err).__name__
                    )
                    if dt_util.utcnow() >= bis:
                        _LOGGER.warning(
                            "%s: aufgegeben, konnte nicht geschaltet werden (%s)",
                            geraet,
                            grund,
                        )
                        return False, None
                    if gescheitert:
                        _LOGGER.debug("%s weiter nicht schaltbar: %s", geraet, grund)
                    else:
                        _LOGGER.warning(
                            "%s konnte nicht geschaltet werden (%s); "
                            "neuer Versuch bis %s",
                            geraet,
                            grund,
                            dt_util.as_local(bis).strftime("%H:%M:%S"),
                        )
                        gescheitert = True
                        self._wiederholt.setdefault(raum_id, set()).add(geraet)
                    await self._warten(geraet, bis)
                    continue
                if gescheitert:
                    _LOGGER.info("%s ist jetzt geschaltet", geraet)
                return True, ergebnis
        finally:
            if (geraete := self._wiederholt.get(raum_id)) is not None:
                geraete.discard(geraet)
                if not geraete:
                    del self._wiederholt[raum_id]

    async def _warten(self, eid: str, bis: datetime) -> None:
        """Bis zum nächsten Versuch: 30 Sekunden, höchstens bis ``bis``.

        Wird das Gerät vorher wieder verfügbar (Wechsel von „fehlt“ bzw.
        „nicht verfügbar“ zu erreichbar) oder taucht seine Favoritenliste auf,
        geht es sofort weiter; andere Zustandsänderungen lösen keinen Versuch
        aus.
        """
        weiter = asyncio.Event()

        @callback
        def _zeit(_jetzt: datetime) -> None:
            weiter.set()

        @callback
        def _zustand(event: Event[EventStateChangedData]) -> None:
            alt, neu = event.data["old_state"], event.data["new_state"]
            if neu is None or not erreichbar(neu.state):
                return
            if (
                alt is None
                or not erreichbar(alt.state)
                or (
                    (not alt.attributes.get("source_list"))
                    and bool(neu.attributes.get("source_list"))
                )
            ):
                weiter.set()

        naechster = min(dt_util.utcnow() + WIEDERHOLEN_NACH, bis.astimezone(UTC))
        abmelden = [
            async_track_point_in_utc_time(self.hass, _zeit, naechster),
            async_track_state_change_event(self.hass, [eid], _zustand),
        ]
        try:
            await weiter.wait()
        finally:
            for ab in abmelden:
                ab()

    def _pruefe_erreichbar(self, eid: str) -> GeraetZustand:
        """Zustand des Geräts; ``_NichtErreichbar``, wenn es fehlt/nicht verfügbar ist.

        Eine Aktion an ein solches Gerät würde HA stillschweigend überspringen.
        """
        if (state := self.hass.states.get(eid)) is None:
            msg = "fehlt in Home Assistant"
            raise _NichtErreichbar(msg)
        if not erreichbar(state.state):
            msg = "nicht verfügbar"
            raise _NichtErreichbar(msg)
        quelle = state.attributes.get("source")
        return GeraetZustand(
            zustand=state.state, quelle=quelle if isinstance(quelle, str) else None
        )

    async def _aktion(self, domain: str, service: str, daten: dict[str, Any]) -> None:
        """Eine HA-Aktion ausführen und auf ihr Ende warten."""
        await self.hass.services.async_call(domain, service, daten, blocking=True)

    def _quellen(self, eid: str) -> list[str]:
        """Aktuelle ``source_list`` eines Lautsprechers."""
        state = self.hass.states.get(eid)
        liste = state.attributes.get("source_list") if state else None
        return [str(q) for q in liste] if isinstance(liste, list) else []

    # ------------------------------------------------------------ Ausschalten

    @callback
    def _timer_stellen(self, raum_id: str) -> None:
        """Timer auf den Aus-Zeitpunkt; ist er schon vorbei, sofort ausschalten."""
        self._timer_weg(raum_id)
        if self._beendet:
            return
        um = self.auftraege[raum_id].um.astimezone(UTC)
        if um <= dt_util.utcnow():
            self._aus_starten(raum_id)
            return
        self._timer[raum_id] = async_track_point_in_utc_time(
            self.hass, partial(self._timer_abgelaufen, raum_id), um
        )

    @callback
    def _timer_abgelaufen(self, raum_id: str, _jetzt: datetime) -> None:
        """Timer erreicht: Ausschalten als Aufgabe des Eintrags starten."""
        self._timer.pop(raum_id, None)
        self._aus_starten(raum_id)

    @callback
    def _aus_starten(self, raum_id: str) -> None:
        """Ausschalten als Aufgabe des Eintrags starten und merken."""
        self._ausschalten_abbrechen(raum_id)
        aufgabe = self._aufgabe(self._faellig(raum_id), f"homewake_aus_{raum_id}")
        if aufgabe.done():
            return
        self._ausschalten[raum_id] = aufgabe
        # ``wecken_bis`` fällt ab jetzt weg (E64)
        self._merken()

        @callback
        def _fertig(_aufgabe: asyncio.Task[None]) -> None:
            if self._ausschalten.get(raum_id) is aufgabe:
                del self._ausschalten[raum_id]

        aufgabe.add_done_callback(_fertig)

    @callback
    def _timer_weg(self, raum_id: str) -> None:
        """Timer eines Raums abmelden."""
        if (abmelden := self._timer.pop(raum_id, None)) is not None:
            abmelden()

    async def _faellig(self, raum_id: str) -> None:
        """Aus-Zeitpunkt erreicht: ausschalten, Auftrag erledigt, speichern.

        Noch laufende Einschalt-Versuche enden zuerst, damit nach dem
        Ausschalten nichts mehr angeht; wartete das Radio bis hierher auf die
        Favoritenliste, wird das gemeldet (E61). Jedes Gerät wird für sich
        ausgeschaltet, ein nicht erreichbares bis 15 Minuten nach dem
        Aus-Zeitpunkt erneut.
        """
        self._stumm_melden(raum_id)
        self._einschalten_abbrechen(raum_id)
        # Abgebrochene Einschalt-Aufgaben erst auslaufen lassen, dann den
        # Zustand der Geräte beurteilen
        if auslaufend := self._auslaufend.pop(raum_id, set()):
            await asyncio.wait(auslaufend, timeout=ZEITLIMIT)
        unklar = self._unterwegs.pop(raum_id, set())
        if (auftrag := self.auftraege.get(raum_id)) is None:
            return
        bis = auftrag.um + AUS_VERSUCHE
        aufgaben = [
            self._licht_aus(raum_id, auftrag, eid, bis, unklar=eid in unklar)
            for eid in auftrag.lichter
        ]
        if (lautsprecher := auftrag.lautsprecher) is not None:
            aufgaben.append(
                self._radio_aus(
                    raum_id, auftrag, lautsprecher, bis, unklar=lautsprecher in unklar
                )
            )
        await asyncio.gather(*aufgaben)
        if not self._beendet and self.auftraege.get(raum_id) is auftrag:
            del self.auftraege[raum_id]
            self._merken()

    async def _licht_aus(
        self,
        raum_id: str,
        auftrag: AusAuftrag,
        eid: str,
        bis: datetime,
        *,
        unklar: bool,
    ) -> None:
        """Ein Licht aus, wenn es noch an ist (E50); Zustand beim Versuch.

        ``unklar``: Beim Abbruch war ein Schaltbefehl unterwegs, also immer aus.
        """

        async def versuch() -> None:
            zustand = self._pruefe_erreichbar(eid)
            nur_dieses = AusAuftrag(um=auftrag.um, lichter=(eid,))
            lichter, _ = was_ausschalten(nur_dieses, {eid: zustand})
            if lichter or unklar:
                await self._aktion("light", "turn_off", {"entity_id": eid})

        await self._wiederholen(raum_id, eid, versuch, bis)

    async def _radio_aus(
        self,
        raum_id: str,
        auftrag: AusAuftrag,
        eid: str,
        bis: datetime,
        *,
        unklar: bool,
    ) -> None:
        """Lautsprecher stoppen, wenn er noch die Weck-Quelle spielt (E50, E54).

        ``unklar``: Beim Abbruch war ein Schaltbefehl unterwegs, also immer stopp.
        """

        async def versuch() -> None:
            zustand = self._pruefe_erreichbar(eid)
            nur_dieser = AusAuftrag(
                um=auftrag.um, lautsprecher=eid, quelle=auftrag.quelle
            )
            _, stoppen = was_ausschalten(nur_dieser, {eid: zustand})
            if stoppen or unklar:
                await self._aktion("media_player", "media_stop", {"entity_id": eid})

        await self._wiederholen(raum_id, eid, versuch, bis)
