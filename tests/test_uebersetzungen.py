"""Prüft, dass jede Übersetzungsdatei alle Grund-Schlüssel und Hinweise kennt (E48).

Ein Tippfehler fiele sonst erst im Frontend auf (roher Schlüssel statt Text).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from custom_components.homewake.const import SUBENTRY_PERSON, SUBENTRY_RAUM
from custom_components.homewake.coordinator import (
    ISSUE_FEIERTAGE,
    ISSUE_KALENDER,
    ISSUE_RAUM_VERLOREN,
    ISSUE_SCHULFERIEN,
    ISSUE_ZEITPLAN,
)
from custom_components.homewake.logic.person import GRUND_KEIN_RAUM, WOCHENTAGE

ORDNER = Path(__file__).parent.parent / "custom_components" / "homewake"
DATEIEN = ("strings.json", "translations/en.json", "translations/de.json")
HINWEISE = (
    ISSUE_FEIERTAGE,
    ISSUE_KALENDER,
    ISSUE_SCHULFERIEN,
    ISSUE_RAUM_VERLOREN,
    f"{ISSUE_ZEITPLAN}_{SUBENTRY_PERSON}",
    f"{ISSUE_ZEITPLAN}_{SUBENTRY_RAUM}",
)


def lade(datei: str) -> Any:
    """Übersetzungsdatei als Dict."""
    return json.loads((ORDNER / datei).read_text(encoding="utf-8"))


@pytest.mark.parametrize("datei", DATEIEN)
def test_alle_grund_schluessel_sind_uebersetzt(datei: str) -> None:
    """Wochentage und „kein Raum“ haben eine Anzeige im Status-Attribut „Grund“."""
    status = lade(datei)["entity"]["sensor"]["status"]
    texte = status["state_attributes"]["grund"]["state"]
    assert set(texte) == {*WOCHENTAGE, GRUND_KEIN_RAUM}
    assert all(texte.values())


@pytest.mark.parametrize("datei", DATEIEN)
def test_alle_hinweise_sind_uebersetzt(datei: str) -> None:
    """Jeder Reparatur-Hinweis hat Titel und Beschreibung."""
    issues = lade(datei)["issues"]
    for schluessel in HINWEISE:
        assert issues[schluessel]["title"]
        assert issues[schluessel]["description"]
