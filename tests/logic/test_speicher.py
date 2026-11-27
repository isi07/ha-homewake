"""Tests für das Umwandeln des Personen-Zustands für den Speicher (5.3)."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from custom_components.homewake.logic.aktorik import AusAuftrag
from custom_components.homewake.logic.haus import PersonBedienung
from custom_components.homewake.logic.person import LichtRadio, PersonZustand, Profil
from custom_components.homewake.logic.raum import RaumQuelle, RaumWecken, RaumZustand
from custom_components.homewake.logic.speicher import (
    aus_auftrag_aus_json,
    aus_auftrag_zu_json,
    person_bedienung_aus_json,
    person_bedienung_zu_json,
    person_zustand_aus_json,
    person_zustand_zu_json,
    raum_zustand_aus_json,
    raum_zustand_zu_json,
    urlaub_aus_json,
    urlaub_zu_json,
)

BERLIN = ZoneInfo("Europe/Berlin")
GEWECKT = PersonZustand(
    wach=True,
    geweckt_um=datetime(2026, 7, 14, 6, 15, tzinfo=BERLIN),
    naechster_wecker=datetime(2026, 7, 15, 5, 30, tzinfo=BERLIN),
    naechster_ist_ausnahme=True,
)


def test_zustand_als_json() -> None:
    """Zeitpunkte werden ISO-Text mit Offset, der Rest bleibt einfach."""
    assert person_zustand_zu_json(GEWECKT) == {
        "wach": True,
        "geweckt_um": "2026-07-14T06:15:00+02:00",
        "naechster_wecker": "2026-07-15T05:30:00+02:00",
        "naechster_ist_ausnahme": True,
    }


def test_hin_und_zurueck_ergibt_denselben_zeitpunkt() -> None:
    """Speichern und Laden ergibt dieselben Zeitpunkte und Werte."""
    geladen = person_zustand_aus_json(person_zustand_zu_json(GEWECKT))
    assert geladen == GEWECKT


def test_leerer_zustand_hin_und_zurueck() -> None:
    """Auch der Leerzustand übersteht Speichern und Laden."""
    leer = PersonZustand()
    assert person_zustand_aus_json(person_zustand_zu_json(leer)) == leer


@pytest.mark.parametrize(
    "daten",
    [
        None,
        "kaputt",
        {},
        {"wach": "ja"},
        {"geweckt_um": "kein Datum"},
        {"naechster_wecker": "2026-07-15T05:30:00"},
    ],
    ids=["none", "text", "leer", "wach_kein_bool", "kein_datum", "ohne_zeitzone"],
)
def test_unlesbares_wird_zum_leerzustand(daten: Any) -> None:
    """Unlesbare Daten ergeben den Leerzustand; der Sollzustand heilt das (E15)."""
    assert person_zustand_aus_json(daten) == PersonZustand()


# ---------------------------------------------------------------- Bedienwerte


BEDIENUNG = PersonBedienung(
    raum_id="raum1",
    ausnahme_aktiv=True,
    ausnahme_zeit=time(5, 30),
    licht_radio={
        Profil.ZEITPLAN: LichtRadio(licht=True, radio=False),
        Profil.AUSNAHME: LichtRadio(licht=True, radio=True),
    },
    favorit="SWR3",
)


def test_bedienung_als_json() -> None:
    """Bedienwerte werden einfache JSON-Werte, Uhrzeit als HH:MM:SS."""
    assert person_bedienung_zu_json(BEDIENUNG) == {
        "raum_id": "raum1",
        "ausnahme_aktiv": True,
        "ausnahme_zeit": "05:30:00",
        "licht_radio": {
            "zeitplan": {"licht": True, "radio": False},
            "ausnahme": {"licht": True, "radio": True},
        },
        "favorit": "SWR3",
    }


def test_bedienung_hin_und_zurueck() -> None:
    """Speichern und Laden ergibt dieselben Bedienwerte."""
    assert person_bedienung_aus_json(person_bedienung_zu_json(BEDIENUNG)) == BEDIENUNG


@pytest.mark.parametrize(
    "daten",
    [None, "kaputt", {"ausnahme_zeit": "25:00"}, {"licht_radio": {"unbekannt": {}}}],
    ids=["none", "text", "falsche_uhrzeit", "unbekanntes_profil"],
)
def test_unlesbare_bedienung_wird_zum_standard(daten: Any) -> None:
    """Unlesbare Bedienwerte ergeben die Standardwerte."""
    assert person_bedienung_aus_json(daten) == PersonBedienung()


# ---------------------------------------------------------------- Raum-Zustand


RAUM_ZUSTAND = RaumZustand(
    datum=date(2026, 7, 14),
    geweckt=RaumWecken(
        zeit=datetime(2026, 7, 14, 6, 30, tzinfo=BERLIN),
        licht=True,
        radio=False,
        favorit="SWR3",
        quelle=RaumQuelle.PERSONEN,
        weckende=("Vater", "Mutter"),
    ),
    tagesbeginn=datetime(2026, 7, 14, 6, 58, tzinfo=BERLIN),
    tagesende=None,
    angekuendigt=RaumWecken(zeit=datetime(2026, 7, 15, 6, 30, tzinfo=BERLIN)),
)


def test_raum_zustand_hin_und_zurueck() -> None:
    """Raum-Zustand übersteht Speichern und Laden."""
    assert raum_zustand_aus_json(raum_zustand_zu_json(RAUM_ZUSTAND)) == RAUM_ZUSTAND


def test_raum_zustand_als_json() -> None:
    """Datum als ISO-Datum, Zeitpunkte als ISO-Text mit Offset."""
    daten = raum_zustand_zu_json(RAUM_ZUSTAND)
    assert daten["datum"] == "2026-07-14"
    assert daten["geweckt"]["zeit"] == "2026-07-14T06:30:00+02:00"
    assert daten["tagesende"] is None


@pytest.mark.parametrize(
    "daten",
    [None, [], {"datum": "kein Datum"}, {"geweckt": {"zeit": "2026-07-14T06:30"}}],
    ids=["none", "liste", "kein_datum", "ohne_zeitzone"],
)
def test_unlesbarer_raum_zustand_wird_leer(daten: Any) -> None:
    """Unlesbares ergibt den Leerzustand; der Sollzustand (E23) heilt das."""
    assert raum_zustand_aus_json(daten) == RaumZustand()


# ---------------------------------------------------------------- Urlaub (E38)


def test_urlaub_hin_und_zurueck() -> None:
    """Der zuletzt gelesene Urlaub pro Tag übersteht das Speichern."""
    tage = {date(2026, 11, 27): False, date(2026, 11, 26): True}
    daten = urlaub_zu_json(tage)
    assert daten == {"2026-11-26": True, "2026-11-27": False}
    assert urlaub_aus_json(daten) == tage


@pytest.mark.parametrize(
    "daten",
    [None, [], "kaputt", {"kein-datum": True}, {"2026-11-26": "ja"}, {5: True}],
)
def test_unlesbarer_urlaub_ist_leer(daten: object) -> None:
    """Unlesbare gespeicherte Daten ergeben „nichts bekannt“."""
    assert urlaub_aus_json(daten) == {}


def test_raum_wecken_mit_quelle_und_weckenden_als_json() -> None:
    """Quelle und weckende Personen werden mitgespeichert (E47)."""
    daten = raum_zustand_zu_json(RAUM_ZUSTAND)
    assert daten["geweckt"]["quelle"] == "personen"
    assert daten["geweckt"]["weckende"] == ["Vater", "Mutter"]


@pytest.mark.parametrize(
    "zusatz",
    [{}, {"quelle": "unbekannt", "weckende": "Vater"}, {"weckende": [1, None]}],
    ids=["altes_format", "unlesbar", "keine_texte"],
)
def test_raum_wecken_ohne_quelle_nimmt_standardwerte(zusatz: dict[str, Any]) -> None:
    """Gespeicherte Daten von vor E47 (oder kaputte Felder) bleiben lesbar."""
    wecken = {"zeit": "2026-07-14T06:30:00+02:00", "licht": True} | zusatz
    zustand = raum_zustand_aus_json({"datum": "2026-07-14", "geweckt": wecken})
    assert zustand.geweckt == RaumWecken(
        zeit=datetime(2026, 7, 14, 6, 30, tzinfo=BERLIN), licht=True
    )


# ---------------------------------------------------------------- Aus-Auftrag (A1)


def test_aus_auftrag_hin_und_zurueck() -> None:
    """Der Aus-Auftrag der Aktorik übersteht Speichern und Laden (E12)."""
    auftrag = AusAuftrag(
        um=datetime.fromisoformat("2026-11-24T07:00:00+01:00"),
        lichter=("light.a", "light.b"),
        lautsprecher="media_player.sonos",
        quelle="SWR3",
    )
    assert aus_auftrag_aus_json(aus_auftrag_zu_json(auftrag)) == auftrag
    assert aus_auftrag_zu_json(None) is None


@pytest.mark.parametrize(
    "daten",
    [
        None,
        "kaputt",
        {},
        {"um": "kein Datum"},
        {"um": "2026-11-24T07:00:00"},  # ohne Zeitzone
        {"um": "2026-11-24T07:00:00+01:00", "lichter": "light.a"},
        {"um": "2026-11-24T07:00:00+01:00", "lichter": [1]},
        {"um": "2026-11-24T07:00:00+01:00", "quelle": 3},
    ],
)
def test_aus_auftrag_unlesbar_ist_keiner(daten: object) -> None:
    """Fehlende oder kaputte Daten ergeben keinen Aus-Auftrag."""
    assert aus_auftrag_aus_json(daten) is None
