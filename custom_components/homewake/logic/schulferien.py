"""Schulferien einer Schule, unabhängig vom Anbieter (ARCHITEKTUR.md 3.6, E41-E44).

Ein Anbieter liefert Ferienzeiträume; abgerufen wird in der HA-Schicht. Hier
steht nur, ob ein Tag Ferien ist, wann neu abgerufen wird, wann die Daten als
veraltet gelten und wie eine gespeicherte Schule angezeigt wird. Wie die Antwort
eines bestimmten Anbieters gelesen wird, steht in einer eigenen Datei
(z. B. ``mehr_schulferien.py``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta

# Wie oft abgerufen wird (E41)
ABRUF_ALLE = timedelta(hours=24)
NEUER_VERSUCH_NACH = timedelta(hours=1)
# Ab wann ein Hinweis unter „Reparaturen“ erscheint (E42)
VERALTET_NACH = timedelta(days=3)
OHNE_DATEN_HINWEIS_NACH = timedelta(minutes=30)
# Wie weit im Voraus geladen wird (E41)
VORRAT = timedelta(days=365)
PFAD_TRENNER = " → "


@dataclass(frozen=True, slots=True)
class Ferien:
    """Ein Ferienzeitraum; Beginn und Ende zählen beide mit."""

    beginn: date
    ende: date
    name: str


@dataclass(frozen=True, slots=True)
class SchulDaten:
    """Zuletzt geladene Schulferien einer Schule und wann sie geladen wurden."""

    abgerufen: datetime | None = None
    ferien: tuple[Ferien, ...] = ()


def schulferien_an(ferien: Iterable[Ferien], tag: date) -> str | None:
    """Name der Ferien am Tag oder None.

    Überschneiden sich Zeiträume, gilt der früher beginnende (E41).
    """
    treffer = [f for f in ferien if f.beginn <= tag <= f.ende]
    if not treffer:
        return None
    return min(treffer, key=lambda f: (f.beginn, f.ende, f.name)).name


def abruf_faellig(
    *, abgerufen: datetime | None, versucht: datetime | None, jetzt: datetime
) -> bool:
    """Ob neu abgerufen werden soll (E41).

    Täglich; nach einem Fehlschlag frühestens eine Stunde später wieder. Liegt
    ein Zeitpunkt in der Zukunft (Uhr verstellt), gilt er als nicht vorhanden.
    """
    if abgerufen is not None and abgerufen > jetzt:
        abgerufen = None
    if versucht is not None and versucht > jetzt:
        versucht = None
    if abgerufen is not None and jetzt - abgerufen < ABRUF_ALLE:
        return False
    return versucht is None or jetzt - versucht >= NEUER_VERSUCH_NACH


def veraltet(
    *, abgerufen: datetime | None, fehler_seit: datetime | None, jetzt: datetime
) -> bool:
    """Ob ein Hinweis unter „Reparaturen“ erscheinen soll (E42).

    Nur, solange der Abruf scheitert: mit Daten nach drei Tagen seit dem
    letzten Erfolg, ganz ohne Daten nach 30 Minuten Ausfall. Ein Abruf in der
    Zukunft (Uhr verstellt) zählt wie keine Daten.
    """
    if fehler_seit is None:
        return False
    if abgerufen is not None and abgerufen > jetzt:
        abgerufen = None
    if abgerufen is None:
        return jetzt - fehler_seit >= OHNE_DATEN_HINWEIS_NACH
    return jetzt - abgerufen >= VERALTET_NACH


def schul_pfad(schule: Mapping[str, object]) -> str:
    """Auswahlweg und Schule, für Dialog und Status-Attribut (E40, E44).

    Gespeichert ist eine Schule als ``{"anbieter", "kennung", "name", "pfad"}``;
    ``pfad`` ist der Weg, über den sie gewählt wurde, z. B. Deutschland →
    Hessen → Frankfurt am Main → Frankfurt am Main. Kaputte Teile werden ausgelassen,
    ohne Namen steht die Kennung da.
    """
    pfad = schule.get("pfad")
    teile = (
        [t for t in pfad if isinstance(t, str) and t] if isinstance(pfad, list) else []
    )
    name = schule.get("name")
    teile.append(name if isinstance(name, str) and name else str(schule.get("kennung")))
    return PFAD_TRENNER.join(teile)


def schul_schluessel(schule: Mapping[str, object]) -> str | None:
    """``<anbieter>:<kennung>`` für Speicher und Hinweis (E44); None wenn unvollständig.

    Zwei Anbieter könnten dieselbe Kennung vergeben; darum zählt das Paar.
    """
    anbieter, kennung = schule.get("anbieter"), schule.get("kennung")
    if isinstance(anbieter, str) and anbieter and isinstance(kennung, str) and kennung:
        return f"{anbieter}:{kennung}"
    return None
