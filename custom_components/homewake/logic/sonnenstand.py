"""Auswahl des Sonnenstands für Dawn/Dusk (ARCHITEKTUR.md 3.5, E30).

Gemeint ist immer die *scheinbare* Höhe der Sonnenmitte über dem Horizont in
Grad, wie bei Sun2 und der Bibliothek astral (die Lichtbrechung rechnet astral
selbst ein). Sonnenaufgang/-untergang heißt: oberer Sonnenrand am Horizont,
also Sonnenmitte einen Sonnenradius (0,267°) darunter.
"""

from __future__ import annotations

FREI = "frei"
STANDARD_SONNENSTAND = "buergerlich"

# Benannte Ereignisse → Grad (negativ = unter dem Horizont)
SONNENSTAENDE: dict[str, float] = {
    "astronomisch": -18.0,
    "nautisch": -12.0,
    "buergerlich": -6.0,
    "blaue_stunde": -4.0,
    "sonnenaufgang": -0.267,
    "horizont": 0.0,
    "goldene_stunde": 6.0,
}

FREI_MIN = -18.0
FREI_MAX = 10.0


def grad(wahl: str, frei: float | None) -> float:
    """Gradzahl zur Auswahl; „frei“ nimmt die eigene Zahl.

    Unbekannte Auswahl oder „frei“ ohne Zahl fallen auf den Standard (-6°).
    """
    if wahl == FREI and frei is not None:
        return float(frei)
    return SONNENSTAENDE.get(wahl, SONNENSTAENDE[STANDARD_SONNENSTAND])
