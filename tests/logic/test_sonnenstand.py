"""Tests für die Auswahl des Sonnenstands (ARCHITEKTUR.md 3.5, E30)."""

from __future__ import annotations

import pytest

from custom_components.homewake.logic.sonnenstand import (
    FREI,
    SONNENSTAENDE,
    STANDARD_SONNENSTAND,
    grad,
)


def test_liste_der_sonnenstaende() -> None:
    """Die benannten Ereignisse mit ihrer Gradzahl (Mitte der Sonnenscheibe)."""
    assert SONNENSTAENDE == {
        "astronomisch": -18.0,
        "nautisch": -12.0,
        "buergerlich": -6.0,
        "blaue_stunde": -4.0,
        "sonnenaufgang": -0.267,
        "horizont": 0.0,
        "goldene_stunde": 6.0,
    }


def test_standard_ist_buergerliche_daemmerung() -> None:
    """Standard ist -6° wie bisher (Sun2)."""
    assert STANDARD_SONNENSTAND == "buergerlich"
    assert grad(STANDARD_SONNENSTAND, None) == -6.0


@pytest.mark.parametrize(("wahl", "erwartet"), list(SONNENSTAENDE.items()))
def test_benannte_auswahl(wahl: str, erwartet: float) -> None:
    """Eine benannte Auswahl ergibt ihre Gradzahl, eine freie Zahl wird ignoriert."""
    assert grad(wahl, 3.0) == erwartet


def test_frei_gewaehlte_gradzahl() -> None:
    """„Frei“ nimmt die eingegebene Gradzahl."""
    assert grad(FREI, -9.5) == -9.5


@pytest.mark.parametrize("wahl", [FREI, "unbekannt", ""])
def test_ungueltiges_faellt_auf_standard(wahl: str) -> None:
    """Frei ohne Zahl oder unbekannte Auswahl: Standard -6° (robust bei alten Daten)."""
    assert grad(wahl, None) == -6.0
