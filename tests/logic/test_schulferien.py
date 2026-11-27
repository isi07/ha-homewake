"""Tests für die Schulferien-Logik (ARCHITEKTUR.md 3.6, E41, E42).

Die Beispieldaten stammen aus einer echten Antwort von mehr-schulferien.de
(Ludwig-Börne-Schule Frankfurt am Main, abgerufen am 26.11.2026), gekürzt.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from custom_components.homewake.logic.mehr_schulferien import ferien_aus_antwort
from custom_components.homewake.logic.schulferien import (
    Ferien,
    SchulDaten,
    abruf_faellig,
    schul_pfad,
    schul_schluessel,
    schulferien_an,
    veraltet,
)
from custom_components.homewake.logic.speicher import (
    schulferien_aus_json,
    schulferien_zu_json,
)

BERLIN = ZoneInfo("Europe/Berlin")
JETZT = datetime(2026, 11, 26, 4, 0, tzinfo=BERLIN)

ANTWORT: dict[str, Any] = {
    "data": [
        {
            "id": 5465,
            "name": "Neujahrstag",
            "type": "public_holiday",
            "starts_on": "2027-01-01",
            "ends_on": "2027-01-01",
            "is_public_holiday": True,
            "is_school_vacation": False,
        },
        {
            "id": 5268,
            "name": "Herbst",
            "type": "school_vacation",
            "starts_on": "2027-10-04",
            "ends_on": "2027-10-16",
            "is_public_holiday": False,
            "is_school_vacation": True,
        },
        {
            "id": 6266,
            "name": "Beweglicher Ferientag",
            "type": "school_vacation",
            "starts_on": "2027-02-08",
            "ends_on": "2027-02-08",
            "is_public_holiday": False,
            "is_school_vacation": True,
        },
        {
            "id": 5145,
            "name": "Weihnachten",
            "type": "school_vacation",
            "starts_on": "2026-12-23",
            "ends_on": "2027-01-12",
            "is_public_holiday": False,
            "is_school_vacation": True,
        },
    ],
    "meta": {"api_version": "2.1"},
}


# ---------------------------------------------------------------- Antwort lesen


def test_nur_schulferien_sortiert() -> None:
    """Nur Einträge mit ``is_school_vacation``, nach Beginn sortiert."""
    assert ferien_aus_antwort(ANTWORT) == [
        Ferien(date(2026, 12, 23), date(2027, 1, 12), "Weihnachten"),
        Ferien(date(2027, 2, 8), date(2027, 2, 8), "Beweglicher Ferientag"),
        Ferien(date(2027, 10, 4), date(2027, 10, 16), "Herbst"),
    ]


@pytest.mark.parametrize(
    "eintrag",
    [
        "kein dict",
        {"name": "X", "is_school_vacation": True, "starts_on": "2027-01-01"},
        {
            "name": "X",
            "is_school_vacation": True,
            "starts_on": "kaputt",
            "ends_on": "2027-01-01",
        },
        {
            "name": "X",
            "is_school_vacation": True,
            "starts_on": "2027-01-05",
            "ends_on": "2027-01-01",
        },
        {
            "name": "X",
            "is_school_vacation": "ja",
            "starts_on": "2027-01-01",
            "ends_on": "2027-01-01",
        },
        {
            "name": 5,
            "is_school_vacation": True,
            "starts_on": "2027-01-01",
            "ends_on": "2027-01-01",
        },
        {
            "name": "X",
            "is_school_vacation": True,
            "starts_on": 20270101,
            "ends_on": "2027-01-01",
        },
    ],
    ids=[
        "kein_dict",
        "ende_fehlt",
        "beginn_kaputt",
        "ende_vor_beginn",
        "flag_kein_bool",
        "name_kein_text",
        "datum_keine_zeichenkette",
    ],
)
def test_unlesbare_eintraege_uebersprungen(eintrag: object) -> None:
    """Unlesbare Einträge werden übersprungen, gültige bleiben."""
    gueltig = ANTWORT["data"][1]
    assert ferien_aus_antwort({"data": [eintrag, gueltig]}) == [
        Ferien(date(2027, 10, 4), date(2027, 10, 16), "Herbst")
    ]


@pytest.mark.parametrize("antwort", [None, [], {"data": "x"}, {"errors": []}], ids=str)
def test_antwort_ohne_liste_ist_fehler(antwort: object) -> None:
    """Ohne Liste ``data`` ist die Antwort kaputt (ValueError, kein leeres Ergebnis).

    Sonst würde eine kaputte Antwort die gespeicherten Ferien überschreiben.
    """
    with pytest.raises(ValueError, match="data"):
        ferien_aus_antwort(antwort)


def test_leere_liste_ist_gueltig() -> None:
    """Eine Schule ohne Ferien im Zeitraum ist eine gültige Antwort."""
    assert ferien_aus_antwort({"data": []}) == []


def test_name_leer_wird_ersetzt() -> None:
    """Ohne Namen heißen die Ferien „Schulferien“ (Status-Grund bleibt lesbar)."""
    eintrag = {
        "name": " ",
        "is_school_vacation": True,
        "starts_on": "2027-01-01",
        "ends_on": "2027-01-01",
    }
    assert ferien_aus_antwort({"data": [eintrag]})[0].name == "Schulferien"


# ---------------------------------------------------------------- Tag prüfen

WEIHNACHTEN = Ferien(date(2026, 12, 23), date(2027, 1, 12), "Weihnachten")
BEWEGLICH = Ferien(date(2027, 1, 12), date(2027, 1, 13), "Beweglicher Ferientag")


@pytest.mark.parametrize(
    ("tag", "erwartet"),
    [
        (date(2026, 12, 22), None),
        (date(2026, 12, 23), "Weihnachten"),  # erster Tag zählt
        (date(2027, 1, 1), "Weihnachten"),  # über den Jahreswechsel
        (date(2027, 1, 12), "Weihnachten"),  # letzter Tag zählt, früherer Beginn
        (date(2027, 1, 13), "Beweglicher Ferientag"),
        (date(2027, 1, 14), None),
    ],
)
def test_schulferien_an(tag: date, erwartet: str | None) -> None:
    """Beginn und Ende zählen mit; bei Überschneidung der früher beginnende."""
    assert schulferien_an([BEWEGLICH, WEIHNACHTEN], tag) == erwartet


def test_ohne_ferien() -> None:
    """Ohne Daten keine Schulferien."""
    assert schulferien_an([], date(2026, 12, 24)) is None


# ---------------------------------------------------------------- Abruf fällig


@pytest.mark.parametrize(
    ("abgerufen", "versucht", "faellig"),
    [
        (None, None, True),  # nie abgerufen
        (None, JETZT - timedelta(minutes=59), False),  # Fehlschlag vor < 1 h
        (None, JETZT - timedelta(hours=1), True),  # Fehlschlag vor 1 h
        (JETZT - timedelta(hours=23, minutes=59), None, False),
        (JETZT - timedelta(hours=24), None, True),  # täglich
        (
            JETZT - timedelta(days=2),
            JETZT - timedelta(minutes=10),
            False,
        ),  # alter Stand, letzter Versuch eben gescheitert
        (
            JETZT - timedelta(days=2),
            JETZT - timedelta(hours=1),
            True,
        ),
        (
            JETZT - timedelta(minutes=5),
            JETZT - timedelta(minutes=5),
            False,
        ),  # eben erfolgreich (Versuch = Erfolg)
    ],
)
def test_abruf_faellig(
    abgerufen: datetime | None, versucht: datetime | None, faellig: bool
) -> None:
    """Täglich abrufen, nach einem Fehlschlag höchstens stündlich (E41)."""
    assert abruf_faellig(abgerufen=abgerufen, versucht=versucht, jetzt=JETZT) is faellig


def test_abruf_uhr_zurueckgestellt() -> None:
    """Liegt der letzte Abruf in der Zukunft (Uhr verstellt), wird neu abgerufen."""
    assert abruf_faellig(
        abgerufen=JETZT + timedelta(days=1), versucht=None, jetzt=JETZT
    )


# ---------------------------------------------------------------- veraltet


@pytest.mark.parametrize(
    ("abgerufen", "fehler_seit", "erwartet"),
    [
        (None, None, False),  # noch kein Versuch gescheitert
        (None, JETZT - timedelta(minutes=29), False),
        (None, JETZT - timedelta(minutes=30), True),  # gar keine Daten
        (JETZT - timedelta(days=2, hours=23), JETZT - timedelta(days=1), False),
        (JETZT - timedelta(days=3), JETZT - timedelta(days=2), True),  # 3 Tage
        (JETZT - timedelta(days=5), None, False),  # alt, aber kein Fehler bekannt
    ],
)
def test_veraltet(
    abgerufen: datetime | None, fehler_seit: datetime | None, erwartet: bool
) -> None:
    """Hinweis nach 3 Tagen ohne Abruf oder 30 min ohne jede Daten (E42)."""
    assert veraltet(abgerufen=abgerufen, fehler_seit=fehler_seit, jetzt=JETZT) is (
        erwartet
    )


def test_veraltet_uhr_zurueckgestellt() -> None:
    """Liegt der letzte Abruf in der Zukunft, zählt das wie „keine Daten“."""
    assert veraltet(
        abgerufen=JETZT + timedelta(days=1),
        fehler_seit=JETZT - timedelta(minutes=30),
        jetzt=JETZT,
    )


# ---------------------------------------------------------------- Speicher


def test_speicher_hin_und_zurueck() -> None:
    """Abrufzeit und Ferien überstehen das Speichern."""
    daten = SchulDaten(abgerufen=JETZT, ferien=(WEIHNACHTEN, BEWEGLICH))
    json = schulferien_zu_json(daten)
    assert json == {
        "abgerufen": "2026-11-26T04:00:00+01:00",
        "ferien": [
            ["2026-12-23", "2027-01-12", "Weihnachten"],
            ["2027-01-12", "2027-01-13", "Beweglicher Ferientag"],
        ],
    }
    assert schulferien_aus_json(json) == daten


@pytest.mark.parametrize(
    "daten",
    [
        None,
        "x",
        {"abgerufen": "kaputt", "ferien": []},
        {"abgerufen": "2026-11-26T04:00:00", "ferien": []},  # ohne Zeitzone
        {"abgerufen": None, "ferien": "x"},
        {"abgerufen": None, "ferien": [["2026-12-23"]]},
        {"abgerufen": None, "ferien": [["x", "2027-01-12", "W"]]},
        {"abgerufen": None, "ferien": [["2026-12-23", "2027-01-12", 5]]},
    ],
    ids=[
        "none",
        "text",
        "zeit_kaputt",
        "ohne_zeitzone",
        "ferien_kein_liste",
        "zu_kurz",
        "datum_kaputt",
        "name_kein_text",
    ],
)
def test_speicher_unlesbar(daten: object) -> None:
    """Unlesbares ergibt „keine Daten“ (dann wird neu abgerufen)."""
    assert schulferien_aus_json(daten) == SchulDaten()


# ---------------------------------------------------------------- Anzeige


def test_schul_pfad_vollstaendig() -> None:
    """Vollständiger Auswahlweg und Schule für Dialog und Attribut (E44)."""
    schule = {
        "anbieter": "mehr_schulferien",
        "kennung": "60311-ludwig-boerne-schule",
        "name": "Ludwig-Börne-Schule (Lange Straße 30-36)",
        "pfad": ["Deutschland", "Hessen", "Frankfurt am Main", "Frankfurt am Main"],
    }
    assert schul_pfad(schule) == (
        "Deutschland → Hessen → Frankfurt am Main → Frankfurt am Main → "
        "Ludwig-Börne-Schule (Lange Straße 30-36)"
    )


def test_schul_pfad_ohne_weg() -> None:
    """Ohne gespeicherten Weg nur der Name."""
    assert (
        schul_pfad({"kennung": "x", "name": "Goethe-Gymnasium"}) == "Goethe-Gymnasium"
    )


def test_schul_pfad_kaputt() -> None:
    """Ohne Namen die Kennung; kaputte Teile des Wegs werden ausgelassen."""
    assert schul_pfad({"kennung": "x", "pfad": ["Hessen", 5, ""]}) == "Hessen → x"
    assert schul_pfad({"kennung": "x", "pfad": "Hessen"}) == "x"


def test_schul_schluessel() -> None:
    """Speicher und Hinweis zählen pro Anbieter und Kennung (E44)."""
    assert (
        schul_schluessel({"anbieter": "mehr_schulferien", "kennung": "abc"})
        == "mehr_schulferien:abc"
    )
    assert schul_schluessel({"anbieter": "mehr_schulferien"}) is None
    assert schul_schluessel({"kennung": "abc"}) is None
    assert schul_schluessel({"anbieter": "", "kennung": "abc"}) is None
