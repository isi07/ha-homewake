"""Anbieter mehr-schulferien.de (ARCHITEKTUR.md 3.6, E40, E41, E44).

Öffentliche API ohne Anmeldung, Version 2.1. Schulen hängen in einer Kette:
Bundesland → Landkreis → Ort → Schule; jede Stufe hat eine eigene Liste und
wird über ihre Kennung („Slug“) angesprochen. Genutzt wird die gemeinsame
Web-Verbindung von HA (``async_get_clientsession``, inject-websession).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import date
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..logic.mehr_schulferien import ferien_aus_antwort
from ..logic.schulferien import Ferien
from . import Anbieter, AnbieterFehler

BASIS = "https://www.mehr-schulferien.de/api/v2.1"
TIMEOUT = 30  # Sekunden pro Abfrage im Hintergrund
TIMEOUT_DIALOG = 10  # Sekunden für die Listen im Dialog (Nutzer wartet)
# mehr-schulferien.de kennt nur Deutschland (``/countries``, 26.11.2026)
LAND = "Deutschland"


async def _hole(
    hass: HomeAssistant,
    pfad: str,
    params: Mapping[str, str] | None = None,
    *,
    sekunden: float = TIMEOUT_DIALOG,
) -> Any:
    """JSON einer Adresse der API; jeder Fehler wird zu ``AnbieterFehler``."""
    session = async_get_clientsession(hass)
    try:
        async with (
            asyncio.timeout(sekunden),
            session.get(f"{BASIS}/{pfad}", params=params) as antwort,
        ):
            antwort.raise_for_status()
            return await antwort.json()
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise AnbieterFehler(str(err) or type(err).__name__) from err


def _liste(antwort: Any, *, mit_strasse: bool = False) -> dict[str, str]:
    """Kennung → Anzeigename aus einer Liste, nach Name sortiert.

    Bei Schulen kommt die Straße dazu, damit gleichnamige unterscheidbar sind.
    """
    eintraege = antwort.get("data") if isinstance(antwort, Mapping) else None
    if not isinstance(eintraege, list):
        msg = "Antwort ohne Liste 'data'"
        raise AnbieterFehler(msg)
    namen: dict[str, str] = {}
    for eintrag in eintraege:
        if not isinstance(eintrag, Mapping):
            continue
        slug, name = eintrag.get("slug"), eintrag.get("name")
        if not isinstance(slug, str) or not slug or not isinstance(name, str):
            continue
        adresse = eintrag.get("address")
        strasse = adresse.get("street") if isinstance(adresse, Mapping) else None
        if mit_strasse and isinstance(strasse, str) and strasse:
            name = f"{name} ({strasse})"
        namen[slug] = name
    return dict(sorted(namen.items(), key=lambda e: (e[1].casefold(), e[0])))


async def liste(hass: HomeAssistant, stufe: str, auswahl: str | None) -> dict[str, str]:
    """Kennung → Name einer Auswahlstufe, gefiltert nach der vorigen Wahl.

    Orte gibt es nur über den Landkreis (``cities?federal_state=…`` ist leer).
    """
    if stufe == "bundesland":
        return await bundeslaender(hass)
    if auswahl is None:
        msg = f"Stufe {stufe} ohne vorige Wahl"
        raise AnbieterFehler(msg)
    return await STUFEN[stufe](hass, auswahl)


async def bundeslaender(hass: HomeAssistant) -> dict[str, str]:
    """Alle Bundesländer."""
    return _liste(await _hole(hass, "federal-states"))


async def kreise(hass: HomeAssistant, bundesland: str) -> dict[str, str]:
    """Landkreise und kreisfreie Städte eines Bundeslands."""
    return _liste(await _hole(hass, "counties", {"federal_state": bundesland}))


async def orte(hass: HomeAssistant, kreis: str) -> dict[str, str]:
    """Orte eines Landkreises."""
    return _liste(await _hole(hass, "cities", {"county": kreis}))


async def schulen(hass: HomeAssistant, ort: str) -> dict[str, str]:
    """Schulen eines Orts, Anzeigename mit Straße."""
    return _liste(await _hole(hass, "schools", {"city": ort}), mit_strasse=True)


async def ferien(
    hass: HomeAssistant, schule: str, von: date, bis: date
) -> list[Ferien]:
    """Schulferien einer Schule im Zeitraum (beide Tage eingeschlossen).

    Die API liefert jeden Zeitraum, der den Zeitraum berührt, also auch
    laufende Ferien, die vor ``von`` begonnen haben (am 26.11.2026 geprüft).
    """
    antwort = await _hole(
        hass,
        f"schools/{schule}/periods",
        {"start_date": von.isoformat(), "end_date": bis.isoformat()},
        sekunden=TIMEOUT,
    )
    try:
        return ferien_aus_antwort(antwort)
    except ValueError as err:
        raise AnbieterFehler(str(err)) from err


STUFEN = {"kreis": kreise, "ort": orte, "schule": schulen}

ANBIETER = Anbieter(
    titel="mehr-schulferien.de",
    stufen=("bundesland", "kreis", "ort", "schule"),
    pfad_anfang=(LAND,),
    liste=liste,
    ferien=ferien,
)
