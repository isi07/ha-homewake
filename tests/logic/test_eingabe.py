"""Tests für das Lesen und Prüfen des Zeitplans aus dem Dialog (3.4, 5.4)."""

from __future__ import annotations

from datetime import time

import pytest

from custom_components.homewake.logic.eingabe import (
    FEHLER_BEIDE_ODER_KEINER,
    FEHLER_ENDE_VOR_BEGINN,
    FEHLER_PFLICHT,
    STANDARD,
    WOCHENTAGE,
    pruefe_zeitplan,
    zeitplan_aus_daten,
)
from custom_components.homewake.logic.zeitplan import Zeitfenster


def paar(beginn: str | None, ende: str | None) -> dict[str, str]:
    """Abschnitt des Dialogs mit optionalem Beginn/Ende."""
    daten: dict[str, str] = {}
    if beginn is not None:
        daten["beginn"] = beginn
    if ende is not None:
        daten["ende"] = ende
    return daten


GUELTIG = {
    STANDARD: paar("08:00:00", "21:00:00"),
    "montag": paar("06:15:00", "22:00:00"),
    "dienstag": paar(None, None),
}


def test_wochentage_in_reihenfolge_montag_bis_sonntag() -> None:
    """Die Abschnitte heißen montag … sonntag, Index wie date.weekday()."""
    assert WOCHENTAGE == (
        "montag",
        "dienstag",
        "mittwoch",
        "donnerstag",
        "freitag",
        "samstag",
        "sonntag",
    )


def test_gueltiger_zeitplan_hat_keine_fehler() -> None:
    """Standard gesetzt, Montag vollständig, Rest leer: keine Fehler."""
    assert pruefe_zeitplan(GUELTIG) == {}


@pytest.mark.parametrize(
    ("standard", "fehler"),
    [
        (paar(None, None), FEHLER_PFLICHT),
        (paar("08:00:00", None), FEHLER_PFLICHT),
        (paar("21:00:00", "08:00:00"), FEHLER_ENDE_VOR_BEGINN),
        (paar("08:00:00", "08:00:00"), FEHLER_ENDE_VOR_BEGINN),
    ],
    ids=["leer", "nur_beginn", "ende_vor_beginn", "ende_gleich_beginn"],
)
def test_standard_fehler(standard: dict[str, str], fehler: str) -> None:
    """Die Standard-Zeile ist Pflicht und muss gültig sein."""
    assert pruefe_zeitplan({STANDARD: standard}) == {STANDARD: fehler}


@pytest.mark.parametrize(
    ("tag", "fehler"),
    [
        (paar("06:00:00", None), FEHLER_BEIDE_ODER_KEINER),
        (paar(None, "22:00:00"), FEHLER_BEIDE_ODER_KEINER),
        (paar("22:00:00", "06:00:00"), FEHLER_ENDE_VOR_BEGINN),
    ],
    ids=["nur_beginn", "nur_ende", "ende_vor_beginn"],
)
def test_wochentag_fehler(tag: dict[str, str], fehler: str) -> None:
    """Ein Wochentag hat beide Zeiten oder keine, Ende nach Beginn."""
    daten = {STANDARD: paar("08:00:00", "21:00:00"), "mittwoch": tag}
    assert pruefe_zeitplan(daten) == {"mittwoch": fehler}


def test_leere_strings_gelten_als_nicht_gesetzt() -> None:
    """Leere Felder zählen wie fehlende Felder."""
    daten = {STANDARD: paar("08:00:00", "21:00:00"), "freitag": paar("", "")}
    assert pruefe_zeitplan(daten) == {}


def test_zeitplan_aus_daten() -> None:
    """Aus den Dialogdaten entsteht der Zeitplan mit Standard und Wochentagen."""
    zp = zeitplan_aus_daten(GUELTIG)
    assert zp.standard == Zeitfenster(time(8, 0), time(21, 0))
    assert zp.wochentage[0] == Zeitfenster(time(6, 15), time(22, 0))
    assert zp.wochentage[1:] == (None,) * 6


def test_zeitplan_aus_daten_akzeptiert_hh_mm() -> None:
    """Auch Uhrzeiten ohne Sekunden (HH:MM) werden gelesen."""
    zp = zeitplan_aus_daten({STANDARD: paar("08:00", "21:30")})
    assert zp.standard == Zeitfenster(time(8, 0), time(21, 30))


def test_zeitplan_aus_ungueltigen_daten_ist_ein_fehler() -> None:
    """Ungültige Daten lösen einen ValueError aus (statt still falsch zu rechnen)."""
    with pytest.raises(ValueError):
        zeitplan_aus_daten({STANDARD: paar(None, None)})
