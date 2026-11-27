"""Tests für den Zeitplan-Baustein (ARCHITEKTUR.md 3.4, E5, E6, E13)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.homewake.logic.zeitplan import (
    Quelle,
    Tageskandidat,
    Zeitfenster,
    Zeitplan,
    kandidat,
    kandidaten_heute_morgen,
)

BERLIN = ZoneInfo("Europe/Berlin")

# Referenztage im Juli 2026 (date.weekday(): 0 = Montag … 6 = Sonntag)
SONNTAG = date(2026, 7, 12)
MONTAG = date(2026, 7, 13)
DIENSTAG = date(2026, 7, 14)
MITTWOCH = date(2026, 7, 15)
SAMSTAG = date(2026, 7, 18)

_TAGNAMEN = ("mo", "di", "mi", "do", "fr", "sa", "so")


def fenster(b: str, e: str) -> Zeitfenster:
    """Baut ein Zeitfenster aus zwei Uhrzeiten im Format HH:MM."""
    return Zeitfenster(time.fromisoformat(b), time.fromisoformat(e))


def plan(standard: Zeitfenster, **tage: Zeitfenster) -> Zeitplan:
    """Baut einen Zeitplan; Wochentage als Schlüsselwort mo, di, … so."""
    unbekannt = set(tage) - set(_TAGNAMEN)
    assert not unbekannt, f"unbekannte Wochentage: {unbekannt}"
    return Zeitplan(
        standard=standard,
        wochentage=tuple(tage.get(name) for name in _TAGNAMEN),
    )


def lokal(tag: date, uhrzeit: str) -> datetime:
    """Bildet aus Datum und Uhrzeit einen Berliner Ortszeitpunkt."""
    return datetime.combine(tag, time.fromisoformat(uhrzeit), tzinfo=BERLIN)


STANDARD = fenster("08:00", "21:00")
MO_FENSTER = fenster("05:45", "21:30")
DI_FENSTER = fenster("06:15", "22:00")
MI_FENSTER = fenster("06:30", "22:15")
SA_FENSTER = fenster("07:30", "23:00")


# ---------------------------------------------------------------- Zeitfenster


@pytest.mark.parametrize(
    ("beginn", "ende"),
    [("07:00", "06:00"), ("07:00", "07:00")],
    ids=["ende_vor_beginn", "ende_gleich_beginn"],
)
def test_zeitfenster_lehnt_ende_nicht_nach_beginn_ab(beginn: str, ende: str) -> None:
    """Ein Zeitfenster, dessen Ende nicht nach dem Beginn liegt, ist ungültig."""
    with pytest.raises(ValueError):
        fenster(beginn, ende)


@pytest.mark.parametrize(
    ("beginn", "ende"),
    [
        (time(6, 0, tzinfo=BERLIN), time(21, 0)),
        (time(6, 0), time(21, 0, tzinfo=BERLIN)),
    ],
    ids=["beginn_mit_tzinfo", "ende_mit_tzinfo"],
)
def test_zeitfenster_lehnt_uhrzeit_mit_zeitzone_ab(beginn: time, ende: time) -> None:
    """Zeitfenster nehmen nur lokale Uhrzeiten ohne tzinfo an."""
    with pytest.raises(ValueError):
        Zeitfenster(beginn, ende)


# ---------------------------------------------------------------- Zeitplan


@pytest.mark.parametrize("anzahl", [6, 8], ids=["sechs_tage", "acht_tage"])
def test_zeitplan_verlangt_genau_sieben_wochentage(anzahl: int) -> None:
    """Ein Zeitplan mit mehr oder weniger als sieben Wochentagen ist ungültig."""
    with pytest.raises(ValueError):
        Zeitplan(standard=STANDARD, wochentage=(None,) * anzahl)


def test_zeitplan_ohne_wochentage_hat_sieben_leere_eintraege() -> None:
    """Ohne Angabe hat ein Zeitplan sieben leere Wochentage."""
    assert Zeitplan(standard=STANDARD).wochentage == (None,) * 7


# ---------------------------------------------------------------- Zeilenwahl


def test_wochentag_mit_eigener_zeit_nimmt_fenster_des_wochentags() -> None:
    """Ein Dienstag mit eigener Zeit liefert das Dienstag-Fenster."""
    k = kandidat(plan(STANDARD, di=DI_FENSTER), DIENSTAG, frei=False, zeitzone=BERLIN)
    assert k.quelle is Quelle.WOCHENTAG
    assert k.beginn == lokal(DIENSTAG, "06:15")
    assert k.ende == lokal(DIENSTAG, "22:00")


def test_wochentag_ohne_eintrag_nimmt_standard() -> None:
    """Ein Dienstag ohne eigene Zeit fällt auf die Standard-Zeile zurück."""
    k = kandidat(plan(STANDARD, mo=MO_FENSTER), DIENSTAG, frei=False, zeitzone=BERLIN)
    assert k.quelle is Quelle.STANDARD
    assert k.beginn == lokal(DIENSTAG, "08:00")
    assert k.ende == lokal(DIENSTAG, "21:00")


def test_samstag_mit_eigener_zeit_nimmt_wochentag() -> None:
    """Samstag mit eigener Zeit gilt diese, nicht Standard (löst Backlog 1 / E6)."""
    k = kandidat(plan(STANDARD, sa=SA_FENSTER), SAMSTAG, frei=False, zeitzone=BERLIN)
    assert k.quelle is Quelle.WOCHENTAG
    assert k.beginn == lokal(SAMSTAG, "07:30")
    assert k.ende == lokal(SAMSTAG, "23:00")


def test_sonntag_ohne_eintrag_nimmt_standard() -> None:
    """Ein Sonntag ohne eigene Zeit liefert die Standard-Zeile."""
    k = kandidat(plan(STANDARD, sa=SA_FENSTER), SONNTAG, frei=False, zeitzone=BERLIN)
    assert k.quelle is Quelle.STANDARD
    assert k.beginn == lokal(SONNTAG, "08:00")


def test_freier_tag_nimmt_standard_trotz_eigener_wochentagszeit() -> None:
    """Ein freier Tag (Feiertag/Ferien/Urlaub) nimmt immer Standard (E6, E13)."""
    k = kandidat(plan(STANDARD, di=DI_FENSTER), DIENSTAG, frei=True, zeitzone=BERLIN)
    assert k.quelle is Quelle.STANDARD
    assert k.beginn == lokal(DIENSTAG, "08:00")
    assert k.ende == lokal(DIENSTAG, "21:00")


# ---------------------------------------------------------------- Datum + Uhrzeit


def test_kandidat_traegt_datum_zeitzone_und_lokale_uhrzeit() -> None:
    """Beginn und Ende liegen am übergebenen Datum, zeitzonenbehaftet, lokal."""
    k = kandidat(plan(STANDARD, di=DI_FENSTER), DIENSTAG, frei=False, zeitzone=BERLIN)
    assert k.datum == DIENSTAG
    for zeitpunkt, uhrzeit in ((k.beginn, time(6, 15)), (k.ende, time(22, 0))):
        assert zeitpunkt.tzinfo is not None
        assert zeitpunkt.utcoffset() is not None
        assert zeitpunkt.date() == DIENSTAG
        assert zeitpunkt.time() == uhrzeit


@pytest.mark.parametrize(
    ("tag", "offset", "utc"),
    [
        (
            date(2026, 3, 29),
            timedelta(hours=2),
            datetime(2026, 3, 29, 4, 30, tzinfo=UTC),
        ),
        (
            date(2026, 10, 25),
            timedelta(hours=1),
            datetime(2026, 10, 25, 5, 30, tzinfo=UTC),
        ),
    ],
    ids=["sommerzeit_beginn", "sommerzeit_ende"],
)
def test_zeitumstellungstag_hat_offset_des_ortszeitpunkts(
    tag: date, offset: timedelta, utc: datetime
) -> None:
    """06:30 am Tag der Zeitumstellung trägt den dann gültigen Offset."""
    k = kandidat(plan(fenster("06:30", "21:00")), tag, frei=False, zeitzone=BERLIN)
    assert k.beginn.utcoffset() == offset
    assert k.beginn.astimezone(UTC) == utc


def test_fehlende_uhrzeit_bei_sommerzeitbeginn_liegt_eine_stunde_spaeter() -> None:
    """02:30 am 29.03.2026 gibt es nicht; der Zeitpunkt entspricht real 03:30 MESZ.

    Python rechnet eine Uhrzeit in der Lücke mit dem Offset vor der Umstellung
    (fold=0, +01:00). Festgelegt, damit eine spätere Änderung auffällt.
    """
    tag = date(2026, 3, 29)
    k = kandidat(plan(fenster("02:30", "21:00")), tag, frei=False, zeitzone=BERLIN)
    assert k.beginn.astimezone(UTC) == datetime(2026, 3, 29, 1, 30, tzinfo=UTC)
    assert k.beginn.astimezone(UTC) == lokal(tag, "03:30").astimezone(UTC)


def test_doppelte_uhrzeit_bei_sommerzeitende_nimmt_das_erste_vorkommen() -> None:
    """02:30 am 25.10.2026 gibt es zweimal; es gilt das erste (noch MESZ, +02:00)."""
    tag = date(2026, 10, 25)
    k = kandidat(plan(fenster("02:30", "21:00")), tag, frei=False, zeitzone=BERLIN)
    assert k.beginn.utcoffset() == timedelta(hours=2)
    assert k.beginn.astimezone(UTC) == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)


def test_tageskandidat_ist_unveraenderlich() -> None:
    """Ein Tageskandidat ist frozen und kann nicht nachträglich geändert werden."""
    k = kandidat(plan(STANDARD), DIENSTAG, frei=False, zeitzone=BERLIN)
    assert isinstance(k, Tageskandidat)
    with pytest.raises(AttributeError):
        k.datum = MITTWOCH  # type: ignore[misc]


# ---------------------------------------------------------------- heute/morgen


def test_morgen_kandidat_traegt_datum_heute_plus_eins() -> None:
    """Der Morgen-Kandidat liegt am Folgetag, der Heute-Kandidat am Tag selbst."""
    heute, morgen = kandidaten_heute_morgen(
        plan(STANDARD), DIENSTAG, frei_heute=False, frei_morgen=False, zeitzone=BERLIN
    )
    assert heute.datum == DIENSTAG
    assert morgen.datum == MITTWOCH
    assert morgen.beginn == lokal(MITTWOCH, "08:00")


def test_heute_frei_morgen_nicht_nimmt_heute_standard_morgen_wochentag() -> None:
    """Frei heute und Werktag morgen werden je Tag getrennt entschieden."""
    zp = plan(STANDARD, di=DI_FENSTER, mi=MI_FENSTER)
    heute, morgen = kandidaten_heute_morgen(
        zp, DIENSTAG, frei_heute=True, frei_morgen=False, zeitzone=BERLIN
    )
    assert heute.quelle is Quelle.STANDARD
    assert heute.beginn == lokal(DIENSTAG, "08:00")
    assert morgen.quelle is Quelle.WOCHENTAG
    assert morgen.beginn == lokal(MITTWOCH, "06:30")


def test_sonntag_auf_montag_nimmt_montagsfenster_fuer_morgen() -> None:
    """Am Sonntag wird für morgen das Montag-Fenster genommen (Wochenwechsel)."""
    zp = plan(STANDARD, mo=MO_FENSTER, so=fenster("09:00", "20:00"))
    heute, morgen = kandidaten_heute_morgen(
        zp, SONNTAG, frei_heute=False, frei_morgen=False, zeitzone=BERLIN
    )
    assert heute.beginn == lokal(SONNTAG, "09:00")
    assert morgen.datum == MONTAG
    assert morgen.quelle is Quelle.WOCHENTAG
    assert morgen.beginn == lokal(MONTAG, "05:45")
    assert morgen.ende == lokal(MONTAG, "21:30")


def test_jahreswechsel_morgen_liegt_im_neuen_jahr() -> None:
    """Vom 31.12.2026 (Do) auf den 01.01.2027 (Fr) stimmen Datum und Wochentag."""
    zp = plan(STANDARD, do=fenster("06:00", "22:00"), fr=fenster("06:45", "22:30"))
    heute, morgen = kandidaten_heute_morgen(
        zp,
        date(2026, 12, 31),
        frei_heute=False,
        frei_morgen=False,
        zeitzone=BERLIN,
    )
    assert heute.beginn == lokal(date(2026, 12, 31), "06:00")
    assert morgen.datum == date(2027, 1, 1)
    assert morgen.beginn == lokal(date(2027, 1, 1), "06:45")


def test_tag_vor_und_tag_der_zeitumstellung_haben_eigene_offsets() -> None:
    """Heute 28.03.2026 hat +1h, morgen 29.03.2026 (Umstellung) hat +2h."""
    heute, morgen = kandidaten_heute_morgen(
        plan(fenster("06:30", "21:00")),
        date(2026, 3, 28),
        frei_heute=False,
        frei_morgen=False,
        zeitzone=BERLIN,
    )
    assert heute.beginn.utcoffset() == timedelta(hours=1)
    assert morgen.beginn.utcoffset() == timedelta(hours=2)
    assert morgen.ende.utcoffset() == timedelta(hours=2)


def test_datums_bug_datum_und_uhrzeit_stammen_immer_vom_selben_tag() -> None:
    """Regression Datums-Bug: jeder Kandidat nimmt Datum und Zeile seines Tags.

    Altes Szenario (Test zur Prioritätskette im alten Projekt): Montag frei, Dienstag
    Werktag mit anderer Zeit. Datum des einen Tags darf nie mit der Uhrzeit
    des anderen Tags gemischt werden (Datum und Uhrzeit immer gemeinsam).
    """
    zp = plan(STANDARD, mo=MO_FENSTER, di=DI_FENSTER)
    heute, morgen = kandidaten_heute_morgen(
        zp, MONTAG, frei_heute=True, frei_morgen=False, zeitzone=BERLIN
    )
    assert (heute.datum, heute.beginn, heute.quelle) == (
        MONTAG,
        lokal(MONTAG, "08:00"),
        Quelle.STANDARD,
    )
    assert (morgen.datum, morgen.beginn, morgen.quelle) == (
        DIENSTAG,
        lokal(DIENSTAG, "06:15"),
        Quelle.WOCHENTAG,
    )


def test_kandidaten_heute_morgen_entspricht_einzelaufrufen() -> None:
    """Das Paar ist identisch mit zwei Einzelaufrufen von kandidat()."""
    zp = plan(STANDARD, mo=MO_FENSTER, di=DI_FENSTER)
    paar = kandidaten_heute_morgen(
        zp, MONTAG, frei_heute=False, frei_morgen=True, zeitzone=BERLIN
    )
    assert paar == (
        kandidat(zp, MONTAG, frei=False, zeitzone=BERLIN),
        kandidat(zp, DIENSTAG, frei=True, zeitzone=BERLIN),
    )
