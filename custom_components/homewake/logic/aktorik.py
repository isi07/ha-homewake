"""Aktorik: was zur Weckzeit geschaltet wird (ARCHITEKTUR.md 4.7).

Reine Logik ohne Home Assistant. Aus dem Wecken eines Raums, „jetzt“ und der
Sonnenhöhe entsteht ein **Schaltplan**: Licht mit Helligkeit, Radio mit
Lautstärke und Favoriten, der Aus-Zeitpunkt nach der Dauer und die Frist für
erneute Versuche (E52). Die Quelle wird erst beim Versuch aus der dann
aktuellen ``source_list`` gewählt. Der Aus-Auftrag füllt sich mit dem, was
wirklich geschaltet wurde; nach Ablauf entscheidet ``was_ausschalten``, was
noch so ist, wie HomeWake es gesetzt hat (E50, E54).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

# Höchstens so lange nach dem Wecken wird noch geschaltet (E28)
NACHHOLEN_BIS = timedelta(minutes=15)
STANDARD_DAUER = timedelta(minutes=45)

# Zustand eines Geräts, das HA zwar kennt, aber nicht erreicht (A2)
_NICHT_VERFUEGBAR = "unavailable"

# Zustände, bei denen HomeWake nicht weiß, wie das Gerät gerade steht (E54)
_UNKLAR = frozenset({"unavailable", "unknown"})


@dataclass(frozen=True, slots=True)
class AktorikKonfig:
    """Geräte und Werte eines Raums für die Aktorik (3.7)."""

    lichter: tuple[str, ...] = ()
    helligkeit: int = 100  # Prozent
    elevation: float = -3.0  # Licht nur bis zu dieser Sonnenhöhe (Grad)
    dauer: timedelta = STANDARD_DAUER
    lautsprecher: str | None = None
    lautstaerke: int = 30  # Prozent


@dataclass(frozen=True, slots=True)
class AktorikEingaben:
    """Alles, was der Schaltplan braucht.

    ``licht``/``radio``/``favorit`` kommen aus dem eingefrorenen Wecken des
    Raums, ``sonnenhoehe`` ist die Sonnenhöhe im Schaltzeitpunkt (E51, E54).
    """

    konfig: AktorikKonfig
    licht: bool
    radio: bool
    favorit: str | None
    standard_favorit: str | None
    geweckt_um: datetime
    sonnenhoehe: float


@dataclass(frozen=True, slots=True)
class LichtBefehl:
    """Lichter einschalten mit Helligkeit in Prozent."""

    lichter: tuple[str, ...]
    helligkeit: int


@dataclass(frozen=True, slots=True)
class RadioBefehl:
    """Lautstärke (0 bis 1) setzen, dann Quelle wählen und abspielen.

    Die Quelle wird bei jedem Versuch mit ``quelle`` aus der dann aktuellen
    Liste gewählt (E56).
    """

    lautsprecher: str
    lautstaerke: float
    favorit: str | None
    standard_favorit: str | None

    def quelle(self, quellen: Sequence[str]) -> str | None:
        """Quelle für diesen Versuch: Favorit, sonst Standard-Favorit (4.7)."""
        return waehle_quelle(self.favorit, self.standard_favorit, quellen)


@dataclass(frozen=True, slots=True)
class AusAuftrag:
    """Was nach Ablauf der Dauer ausgeschaltet wird, und wann.

    Enthält nur, was wirklich eingeschaltet wurde (A2). ``lautsprecher`` und
    ``quelle`` sind nur gesetzt, wenn eine Quelle gespielt wurde; sonst gibt
    es am Lautsprecher nichts auszuschalten.
    """

    um: datetime
    lichter: tuple[str, ...] = ()
    lautsprecher: str | None = None
    quelle: str | None = None


@dataclass(frozen=True, slots=True)
class Schaltplan:
    """Was zur Weckzeit geschaltet wird, wann aus, und bis wann versucht wird."""

    licht: LichtBefehl | None
    radio: RadioBefehl | None
    aus_um: datetime
    versuche_bis: datetime


@dataclass(frozen=True, slots=True)
class GeraetZustand:
    """Zustand eines Geräts beim Ausschalten; ``quelle`` nur bei Lautsprechern."""

    zustand: str | None
    quelle: str | None = None


def waehle_quelle(
    favorit: str | None, standard_favorit: str | None, quellen: Sequence[str]
) -> str | None:
    """Favorit der Person, sonst Standard-Favorit, sonst der Erste der Liste.

    Gültig ist nur, was exakt so in der Liste des Lautsprechers steht
    (Backlog 9). Fehlen beide (oder ist keiner eingestellt), spielt der erste
    Eintrag der Liste (E56). Nur ohne Liste gibt es keine Quelle.
    """
    for kandidat in (favorit, standard_favorit):
        if kandidat is not None and kandidat in quellen:
            return kandidat
    return quellen[0] if quellen else None


def schaltplan(eingaben: AktorikEingaben, *, jetzt: datetime) -> Schaltplan | None:
    """Schaltplan für ein gerade gemeldetes Wecken; None, wenn nichts zu tun ist.

    Liegt das Wecken mehr als 15 Minuten zurück, wird nicht mehr geschaltet
    (E28). Der Aus-Zeitpunkt zählt ab ``jetzt`` (E54). Erneut versucht wird
    bis 15 Minuten nach dem Wecken, aber nie über den Aus-Zeitpunkt hinaus
    (E52). Ob Licht gewünscht ist, steht mit dem Plan fest (E55).
    """
    if jetzt.tzinfo is None or jetzt.utcoffset() is None:
        msg = "jetzt muss zeitzonenbehaftet sein"
        raise ValueError(msg)
    if jetzt.timestamp() - eingaben.geweckt_um.timestamp() > (
        NACHHOLEN_BIS.total_seconds()
    ):
        return None
    konfig = eingaben.konfig

    licht: LichtBefehl | None = None
    if eingaben.licht and konfig.lichter and eingaben.sonnenhoehe <= konfig.elevation:
        licht = LichtBefehl(lichter=konfig.lichter, helligkeit=konfig.helligkeit)

    radio: RadioBefehl | None = None
    if eingaben.radio and konfig.lautsprecher:
        radio = RadioBefehl(
            lautsprecher=konfig.lautsprecher,
            lautstaerke=konfig.lautstaerke / 100,
            favorit=eingaben.favorit,
            standard_favorit=eingaben.standard_favorit,
        )

    if licht is None and radio is None:
        return None
    aus_um = jetzt + konfig.dauer
    return Schaltplan(
        licht=licht,
        radio=radio,
        aus_um=aus_um,
        versuche_bis=min(eingaben.geweckt_um + NACHHOLEN_BIS, aus_um),
    )


def aus_auftrag_beginnen(plan: Schaltplan, alt: AusAuftrag | None) -> AusAuftrag:
    """Aus-Auftrag eines neuen Weckens: zunächst leer, Zeitpunkt aus dem Plan.

    Ist noch ein Auftrag offen, bleiben dessen Geräte darin; sie werden dann
    mit dem neuen Zeitpunkt ausgeschaltet.
    """
    if alt is None:
        return AusAuftrag(um=plan.aus_um)
    return AusAuftrag(
        um=plan.aus_um,
        lichter=alt.lichter,
        lautsprecher=alt.lautsprecher,
        quelle=alt.quelle,
    )


def erreichbar(zustand: str | None) -> bool:
    """Ob ein Schaltversuch Sinn hat: Das Gerät ist in HA da und verfügbar.

    Eine Aktion an ein nicht verfügbares Gerät überspringt HA stillschweigend;
    das gilt darum als gescheitert und wird später wiederholt (A2). Ein
    unbekannter Zustand (``unknown``) wird geschaltet.
    """
    return zustand is not None and zustand != _NICHT_VERFUEGBAR


def _unklar(zustand: GeraetZustand | None) -> bool:
    """Ob HomeWake nicht weiß, wie das Gerät steht (fehlt, nicht verfügbar …)."""
    return zustand is None or zustand.zustand is None or zustand.zustand in _UNKLAR


def was_ausschalten(
    auftrag: AusAuftrag, zustaende: Mapping[str, GeraetZustand]
) -> tuple[tuple[str, ...], bool]:
    """Welche Lichter aus und ob der Lautsprecher stoppen soll (E50, E54).

    Aus geht, was noch so ist, wie HomeWake es gesetzt hat: ein Licht, das an
    ist, ein Lautsprecher, der die Weck-Quelle spielt. Ist der Zustand unklar
    (fehlt, nicht verfügbar, unbekannt, spielt ohne gemeldete Quelle), wird
    trotzdem ausgeschaltet. Unberührt bleibt nur, was sicher anders ist.
    """
    lichter = tuple(
        eid
        for eid in auftrag.lichter
        if _unklar(z := zustaende.get(eid)) or (z is not None and z.zustand == "on")
    )
    stoppen = False
    if auftrag.lautsprecher is not None:
        z = zustaende.get(auftrag.lautsprecher)
        if _unklar(z):
            stoppen = True
        elif z is not None and z.zustand == "playing":
            stoppen = z.quelle is None or z.quelle == auftrag.quelle
    return lichter, stoppen
