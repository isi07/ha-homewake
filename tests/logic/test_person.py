"""Tests für den Personen-Baustein (ARCHITEKTUR.md 4.1, 4.3, 4.4)."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from custom_components.homewake.logic.person import (
    PersonStatus,
    Profil,
    TagInfo,
    tagesplan,
    tagesstatus,
)
from custom_components.homewake.logic.zeitplan import Zeitfenster, Zeitplan

BERLIN = ZoneInfo("Europe/Berlin")

DIENSTAG = date(2026, 7, 14)
SAMSTAG = date(2026, 7, 18)


def fenster(b: str, e: str) -> Zeitfenster:
    """Baut ein Zeitfenster aus zwei Uhrzeiten im Format HH:MM."""
    return Zeitfenster(time.fromisoformat(b), time.fromisoformat(e))


def lokal(tag: date, uhrzeit: str) -> datetime:
    """Bildet aus Datum und Uhrzeit einen Berliner Ortszeitpunkt."""
    return datetime.combine(tag, time.fromisoformat(uhrzeit), tzinfo=BERLIN)


STANDARD = fenster("08:00", "21:00")
DI_FENSTER = fenster("06:15", "22:00")
SA_FENSTER = fenster("07:30", "23:00")

# Index wie date.weekday(): Dienstag = 1, Samstag = 5
ZEITPLAN = Zeitplan(
    standard=STANDARD,
    wochentage=(None, DI_FENSTER, None, None, None, SA_FENSTER, None),
)


# ---------------------------------------------------------------- TagInfo


@pytest.mark.parametrize(
    ("info", "frei"),
    [
        (TagInfo(), False),
        (TagInfo(urlaub=True), True),
        (TagInfo(schulferien="Sommerferien"), True),
        (TagInfo(feiertag="Tag der Deutschen Einheit"), True),
    ],
    ids=["normal", "urlaub", "schulferien", "feiertag"],
)
def test_taginfo_frei_bei_urlaub_ferien_oder_feiertag(
    info: TagInfo, frei: bool
) -> None:
    """Ein Tag ist frei bei Urlaub, Schulferien oder Feiertag (nicht am Wochenende)."""
    assert info.frei is frei


# ---------------------------------------------------------------- Statuskette


@pytest.mark.parametrize(
    ("tag", "info", "status", "grund"),
    [
        (DIENSTAG, TagInfo(), PersonStatus.WERKTAG, "dienstag"),
        (SAMSTAG, TagInfo(), PersonStatus.WOCHENENDE, "samstag"),
        (
            DIENSTAG,
            TagInfo(feiertag="Fronleichnam"),
            PersonStatus.FEIERTAG,
            "Fronleichnam",
        ),
        (
            DIENSTAG,
            TagInfo(schulferien="Sommerferien"),
            PersonStatus.SCHULFERIEN,
            "Sommerferien",
        ),
        (DIENSTAG, TagInfo(urlaub=True), PersonStatus.URLAUB, None),
    ],
    ids=["werktag", "wochenende", "feiertag", "schulferien", "urlaub"],
)
def test_tagesstatus_liefert_status_und_grund(
    tag: date, info: TagInfo, status: PersonStatus, grund: str | None
) -> None:
    """Jeder Tagestyp liefert seinen Status und Grund (Urlaub ohne Grund, 9 #2)."""
    assert tagesstatus(tag, info) == (status, grund)


@pytest.mark.parametrize(
    ("tag", "info", "status"),
    [
        (
            DIENSTAG,
            TagInfo(urlaub=True, schulferien="Sommerferien", feiertag="X"),
            PersonStatus.URLAUB,
        ),
        (
            DIENSTAG,
            TagInfo(schulferien="Sommerferien", feiertag="X"),
            PersonStatus.SCHULFERIEN,
        ),
        (SAMSTAG, TagInfo(feiertag="X"), PersonStatus.FEIERTAG),
        (SAMSTAG, TagInfo(schulferien="Herbstferien"), PersonStatus.SCHULFERIEN),
    ],
    ids=[
        "urlaub_vor_ferien_und_feiertag",
        "ferien_vor_feiertag",
        "feiertag_vor_wochenende",
        "ferien_vor_wochenende",
    ],
)
def test_tagesstatus_prioritaetskette(
    tag: date, info: TagInfo, status: PersonStatus
) -> None:
    """Urlaub > Schulferien > Feiertag > Wochenende > Werktag (4.1)."""
    assert tagesstatus(tag, info)[0] is status


# ---------------------------------------------------------------- Tagesplan


def test_tagesplan_werktag_mit_eigener_zeit_nimmt_profil_zeitplan() -> None:
    """Werktag mit eigener Zeit: Wochentags-Fenster, Profil Zeitplan (E7)."""
    p = tagesplan(ZEITPLAN, DIENSTAG, TagInfo(), zeitzone=BERLIN)
    assert p.datum == DIENSTAG
    assert (p.beginn, p.ende) == (lokal(DIENSTAG, "06:15"), lokal(DIENSTAG, "22:00"))
    assert (p.status, p.grund, p.profil) == (
        PersonStatus.WERKTAG,
        "dienstag",
        Profil.ZEITPLAN,
    )


def test_tagesplan_werktag_ohne_eigene_zeit_nimmt_profil_standard() -> None:
    """Werktag ohne eigene Zeit: Standard-Zeile, Status Werktag, Profil Standard."""
    mittwoch = date(2026, 7, 15)
    p = tagesplan(ZEITPLAN, mittwoch, TagInfo(), zeitzone=BERLIN)
    assert p.beginn == lokal(mittwoch, "08:00")
    assert (p.status, p.profil) == (PersonStatus.WERKTAG, Profil.STANDARD)


def test_tagesplan_samstag_mit_eigener_zeit_bleibt_status_wochenende() -> None:
    """Samstag mit eigener Zeit: Status Wochenende, aber Profil Zeitplan (E6, E7)."""
    p = tagesplan(ZEITPLAN, SAMSTAG, TagInfo(), zeitzone=BERLIN)
    assert p.beginn == lokal(SAMSTAG, "07:30")
    assert (p.status, p.grund, p.profil) == (
        PersonStatus.WOCHENENDE,
        "samstag",
        Profil.ZEITPLAN,
    )


def test_tagesplan_feiertag_mit_eigener_zeit_nimmt_standard() -> None:
    """Feiertag an einem Tag mit eigener Zeit: Standard-Zeile, Profil Standard."""
    p = tagesplan(ZEITPLAN, DIENSTAG, TagInfo(feiertag="Fronleichnam"), zeitzone=BERLIN)
    assert (p.beginn, p.ende) == (lokal(DIENSTAG, "08:00"), lokal(DIENSTAG, "21:00"))
    assert (p.status, p.grund, p.profil) == (
        PersonStatus.FEIERTAG,
        "Fronleichnam",
        Profil.STANDARD,
    )


def test_tagesplan_urlaub_nimmt_standard_ohne_grund() -> None:
    """Urlaub: Standard-Zeile, Status Urlaub, kein Grund."""
    p = tagesplan(ZEITPLAN, DIENSTAG, TagInfo(urlaub=True), zeitzone=BERLIN)
    assert p.beginn == lokal(DIENSTAG, "08:00")
    assert (p.status, p.grund, p.profil) == (
        PersonStatus.URLAUB,
        None,
        Profil.STANDARD,
    )
