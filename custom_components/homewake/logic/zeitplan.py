"""Zeitplan einer Person oder eines Raums (ARCHITEKTUR.md 3.4, E5, E6, E13).

Ein Zeitplan hat pro Wochentag höchstens ein Zeitfenster (Tagesbeginn bis
Tagesende) und eine Pflicht-Zeile „Standard“. Dieser Baustein beantwortet nur:
Welche Zeile gilt an einem Tag, und welche Zeitpunkte ergeben sich daraus?

Ob ein Tag „frei“ ist (Feiertag, Schulferien, Urlaub), entscheidet der Aufrufer.
Ausnahmen gehören nicht hierher, sondern in den Personen-Baustein.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from enum import StrEnum

ANZAHL_WOCHENTAGE = 7


class Quelle(StrEnum):
    """Welche Zeile des Zeitplans für einen Tag gilt."""

    WOCHENTAG = "wochentag"
    STANDARD = "standard"


@dataclass(frozen=True, slots=True)
class Zeitfenster:
    """Ein Paar aus Tagesbeginn und Tagesende als lokale Uhrzeiten.

    Die Uhrzeiten tragen keine Zeitzone. Erst ``kandidat`` verbindet sie mit
    einem Datum und einer Zeitzone zu echten Zeitpunkten.
    """

    beginn: time
    ende: time

    def __post_init__(self) -> None:
        """Prüft, dass beide Uhrzeiten lokal sind und das Ende nach dem Beginn liegt."""
        if self.beginn.tzinfo is not None or self.ende.tzinfo is not None:
            msg = "Zeitfenster nimmt nur lokale Uhrzeiten ohne Zeitzone an"
            raise ValueError(msg)
        if self.ende <= self.beginn:
            msg = f"Tagesende {self.ende} liegt nicht nach Tagesbeginn {self.beginn}"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Zeitplan:
    """Wochenplan: pro Wochentag ein Fenster oder leer, dazu die Standard-Zeile.

    ``wochentage`` hat genau sieben Einträge, Index wie ``date.weekday()``
    (0 = Montag … 6 = Sonntag).
    """

    standard: Zeitfenster
    wochentage: tuple[Zeitfenster | None, ...] = (None,) * ANZAHL_WOCHENTAGE

    def __post_init__(self) -> None:
        """Prüft, dass genau sieben Wochentage angegeben sind."""
        if len(self.wochentage) != ANZAHL_WOCHENTAGE:
            msg = (
                f"Zeitplan braucht {ANZAHL_WOCHENTAGE} Wochentage, "
                f"nicht {len(self.wochentage)}"
            )
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Tageskandidat:
    """Vollständiger Kandidat für einen Tag: Datum und Zeitpunkte gemeinsam.

    Datum und Uhrzeit werden nie getrennt kombiniert (Architektur-Regel,
    Datums-Bug aus ARCHITEKTUR.md 4.2).
    """

    datum: date
    beginn: datetime
    ende: datetime
    quelle: Quelle


def geltendes_fenster(
    zeitplan: Zeitplan, tag: date, *, frei: bool
) -> tuple[Zeitfenster, Quelle]:
    """Wählt die Zeile, die an ``tag`` gilt.

    Freier Tag → Standard. Sonst das Fenster des Wochentags, falls gepflegt
    (auch Samstag/Sonntag), sonst Standard.
    """
    if not frei:
        eigenes = zeitplan.wochentage[tag.weekday()]
        if eigenes is not None:
            return eigenes, Quelle.WOCHENTAG
    return zeitplan.standard, Quelle.STANDARD


def kandidat(
    zeitplan: Zeitplan, tag: date, *, frei: bool, zeitzone: tzinfo
) -> Tageskandidat:
    """Bildet den vollständigen Kandidaten für ``tag`` in ``zeitzone``."""
    fenster, quelle = geltendes_fenster(zeitplan, tag, frei=frei)
    return Tageskandidat(
        datum=tag,
        beginn=datetime.combine(tag, fenster.beginn, tzinfo=zeitzone),
        ende=datetime.combine(tag, fenster.ende, tzinfo=zeitzone),
        quelle=quelle,
    )


def kandidaten_heute_morgen(
    zeitplan: Zeitplan,
    heute: date,
    *,
    frei_heute: bool,
    frei_morgen: bool,
    zeitzone: tzinfo,
) -> tuple[Tageskandidat, Tageskandidat]:
    """Bildet die Kandidaten für heute und morgen, jeden für sich vollständig.

    Welcher davon der „nächste“ ist, entscheidet der Aufrufer anhand von „jetzt“.
    """
    morgen = heute + timedelta(days=1)
    return (
        kandidat(zeitplan, heute, frei=frei_heute, zeitzone=zeitzone),
        kandidat(zeitplan, morgen, frei=frei_morgen, zeitzone=zeitzone),
    )


def naechste_mitternacht(jetzt: datetime, zeitzone: tzinfo) -> datetime:
    """Beginn (00:00) des nächsten lokalen Tages nach ``jetzt``."""
    morgen = jetzt.astimezone(zeitzone).date() + timedelta(days=1)
    return datetime.combine(morgen, time(0), tzinfo=zeitzone)


def naechste_aenderung(
    jetzt: datetime, zeitzone: tzinfo, kandidaten: Iterable[datetime | None]
) -> datetime:
    """Frühester Kandidat nach ``jetzt``, höchstens die nächste Mitternacht.

    Für den Zeitplaner: Zu diesem Zeitpunkt muss HomeWake neu rechnen.
    """
    grenze = naechste_mitternacht(jetzt, zeitzone)
    spaeter = [
        k
        for k in kandidaten
        if k is not None and jetzt.timestamp() < k.timestamp() < grenze.timestamp()
    ]
    return min(spaeter, key=datetime.timestamp, default=grenze)
