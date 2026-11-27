"""Zeitplan aus den Dialogdaten lesen und prüfen (ARCHITEKTUR.md 3.4, 5.4).

Der Dialog speichert den Zeitplan als einfache Daten: ein Abschnitt pro Zeile
(``standard``, ``montag`` … ``sonntag``) mit optionalen Feldern ``beginn`` und
``ende`` als Uhrzeit-Text (``HH:MM:SS`` oder ``HH:MM``).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import time

from .zeitplan import Zeitfenster, Zeitplan

STANDARD = "standard"
WOCHENTAGE = (
    "montag",
    "dienstag",
    "mittwoch",
    "donnerstag",
    "freitag",
    "samstag",
    "sonntag",
)
BEGINN = "beginn"
ENDE = "ende"

FEHLER_PFLICHT = "standard_pflicht"
FEHLER_BEIDE_ODER_KEINER = "beide_oder_keiner"
FEHLER_ENDE_VOR_BEGINN = "ende_vor_beginn"

ZeitplanDaten = Mapping[str, Mapping[str, str]]


def _uhrzeit(abschnitt: Mapping[str, str] | None, feld: str) -> time | None:
    """Uhrzeit eines Feldes oder None, wenn leer oder nicht vorhanden."""
    if not abschnitt:
        return None
    text = abschnitt.get(feld)
    return time.fromisoformat(text) if text else None


def _pruefe_zeile(abschnitt: Mapping[str, str] | None, *, pflicht: bool) -> str | None:
    """Fehlerschlüssel einer Zeile oder None, wenn sie gültig ist."""
    beginn, ende = _uhrzeit(abschnitt, BEGINN), _uhrzeit(abschnitt, ENDE)
    if beginn is None and ende is None:
        return FEHLER_PFLICHT if pflicht else None
    if beginn is None or ende is None:
        return FEHLER_PFLICHT if pflicht else FEHLER_BEIDE_ODER_KEINER
    if ende <= beginn:
        return FEHLER_ENDE_VOR_BEGINN
    return None


def pruefe_zeitplan(daten: ZeitplanDaten) -> dict[str, str]:
    """Prüft die Dialogdaten; liefert Fehlerschlüssel pro Abschnitt (leer = gültig).

    Standard ist Pflicht. Jeder Wochentag hat beide Zeiten oder keine.
    Das Ende muss nach dem Beginn liegen.
    """
    fehler: dict[str, str] = {}
    if (f := _pruefe_zeile(daten.get(STANDARD), pflicht=True)) is not None:
        fehler[STANDARD] = f
    for tag in WOCHENTAGE:
        if (f := _pruefe_zeile(daten.get(tag), pflicht=False)) is not None:
            fehler[tag] = f
    return fehler


def _fenster(abschnitt: Mapping[str, str] | None) -> Zeitfenster | None:
    """Zeitfenster einer gültigen Zeile oder None, wenn sie leer ist."""
    beginn, ende = _uhrzeit(abschnitt, BEGINN), _uhrzeit(abschnitt, ENDE)
    if beginn is None or ende is None:
        return None
    return Zeitfenster(beginn, ende)


def zeitplan_aus_daten(daten: ZeitplanDaten) -> Zeitplan:
    """Baut den Zeitplan aus geprüften Dialogdaten.

    Ungültige Daten lösen einen ``ValueError`` aus.
    """
    if fehler := pruefe_zeitplan(daten):
        msg = f"Ungültiger Zeitplan: {fehler}"
        raise ValueError(msg)
    standard = _fenster(daten.get(STANDARD))
    if standard is None:  # durch die Prüfung ausgeschlossen
        msg = "Standard-Zeile fehlt"
        raise ValueError(msg)
    return Zeitplan(
        standard=standard,
        wochentage=tuple(_fenster(daten.get(tag)) for tag in WOCHENTAGE),
    )
