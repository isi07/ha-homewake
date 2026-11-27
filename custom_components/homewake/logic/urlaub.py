"""Urlaub aus einem Kalender bestimmen (ARCHITEKTUR.md 3.6, E38).

Urlaub gilt ganztägig: Ein Tag ist Urlaub, wenn irgendein Kalendereintrag ihn
berührt. Die Termine kommen als einfache Daten aus der HA-Aktion
``calendar.get_events``: ganztägige mit reinem Datum (``"2026-11-26"``, Ende
exklusiv), alle anderen mit Uhrzeit (``"2026-11-26T09:00:00+01:00"``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo


@dataclass(frozen=True, slots=True)
class Termin:
    """Ein Kalendereintrag: beide Grenzen ganztägig (``date``) oder mit Uhrzeit."""

    beginn: date | datetime
    ende: date | datetime


def beruehrt(termin: Termin, tag: date) -> bool:
    """Ob der Termin den Tag berührt.

    Ganztägig: ``beginn <= tag < ende`` (Ende exklusiv; Ende gleich Beginn gilt
    als der eine Tag). Ein reines Datum hat keine Zeitzone und wird nie
    umgerechnet.

    Mit Uhrzeit: Es zählen die Tage **so, wie der Termin eingetragen ist**, also
    in seiner eigenen Zeitzone (E38), nicht umgerechnet in die HA-Zeitzone. Ein
    Urlaub in Tokio am 27. zählt am 27., auch wenn er in Berlin noch am 26.
    beginnt. Endet der Termin genau um 00:00, zählt der Folgetag nicht; ein
    Termin ohne Dauer zählt am Tag seines Zeitpunkts.
    """
    if isinstance(termin.beginn, datetime) and isinstance(termin.ende, datetime):
        erster = termin.beginn.date()  # Datum in der Zeitzone des Termins
        letzter = termin.ende.date()
        if termin.ende > termin.beginn and termin.ende.time() == time():
            letzter -= timedelta(days=1)
        return erster <= tag <= letzter
    ende = max(termin.ende, termin.beginn + timedelta(days=1))
    return termin.beginn <= tag < ende


def urlaub_an(termine: Iterable[Termin], tag: date) -> bool:
    """Ob irgendein Termin den Tag berührt."""
    return any(beruehrt(t, tag) for t in termine)


def _zeitpunkt(wert: object, zeitzone: tzinfo) -> date | datetime | None:
    """Datum oder Zeitpunkt aus dem Text; ohne Offset gilt die HA-Zeitzone."""
    if not isinstance(wert, str):
        return None
    try:
        if "T" not in wert and " " not in wert.strip():
            return date.fromisoformat(wert)
        zeit = datetime.fromisoformat(wert)
    except ValueError:
        return None
    return zeit if zeit.tzinfo is not None else zeit.replace(tzinfo=zeitzone)


def termine_aus_antwort(
    eintraege: Iterable[object], *, zeitzone: tzinfo
) -> list[Termin]:
    """Termine aus der Liste ``events`` von ``calendar.get_events``.

    Unlesbare Einträge (fehlende oder kaputte Grenzen, Ende vor Beginn,
    ganztägig und mit Uhrzeit gemischt) werden übersprungen.
    """
    termine: list[Termin] = []
    for eintrag in eintraege:
        if not isinstance(eintrag, Mapping):
            continue
        beginn = _zeitpunkt(eintrag.get("start"), zeitzone)
        ende = _zeitpunkt(eintrag.get("end"), zeitzone)
        if beginn is None or ende is None:
            continue
        if isinstance(beginn, datetime) != isinstance(ende, datetime):
            continue
        if ende < beginn:
            continue
        termine.append(Termin(beginn, ende))
    return termine
