"""Dawn/Dusk und Sonnenhöhe aus dem HA-Standort (ARCHITEKTUR.md 3.5, 4.6, E30, E51).

Nutzt dieselbe Bibliothek wie HA selbst (astral). Die Rechnung ist rein
rechnerisch und schnell, blockiert also nicht.
"""

from __future__ import annotations

from datetime import date, datetime

from astral import Observer
from astral.sun import SunDirection, elevation, time_at_elevation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.sun import get_astral_observer
from homeassistant.util import dt as dt_util

from .logic.raum import Sonne


def _zeitpunkt(
    beobachter: Observer, tag: date, grad: float, richtung: SunDirection
) -> datetime | None:
    """Zeitpunkt des Sonnenstands an diesem Tag, None wenn er nicht erreicht wird."""
    try:
        zeitpunkt: datetime = time_at_elevation(
            beobachter,
            grad,
            tag,
            direction=richtung,
            tzinfo=dt_util.get_default_time_zone(),
        )
    except ValueError:
        # z. B. Polarnacht oder Mitternachtssonne: kein Klemmen (E25)
        return None
    # astral rechnet mit dem UTC-Datum; fern vom Zeitzonen-Meridian könnte das
    # Ergebnis auf einem anderen Ortsdatum liegen. Dann lieber nicht klemmen (E25).
    if zeitpunkt.date() != tag:
        return None
    return zeitpunkt


def sonne(
    hass: HomeAssistant, tag: date, grad_morgen: float, grad_abend: float
) -> Sonne:
    """Morgen- und Abenddämmerung eines Tags am Standort der HA."""
    beobachter = get_astral_observer(hass)
    return Sonne(
        dawn=_zeitpunkt(beobachter, tag, grad_morgen, SunDirection.RISING),
        dusk=_zeitpunkt(beobachter, tag, grad_abend, SunDirection.SETTING),
    )


def sonnenhoehe(hass: HomeAssistant, zeitpunkt: datetime) -> float:
    """Scheinbare Sonnenhöhe in Grad zu einem Zeitpunkt (E51).

    Wie ``sun.sun`` mit Lichtbrechung; negativ heißt unter dem Horizont.
    """
    return float(elevation(get_astral_observer(hass), zeitpunkt))
