"""Tests für das Zusammenfassen eines Raums pro Tag (ARCHITEKTUR.md 3.7, E22, E24)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from custom_components.homewake.logic.person import (
    KandidatTag,
    LichtRadio,
    PersonEingaben,
    PersonZustand,
    TagInfo,
    berechne_person,
)
from custom_components.homewake.logic.raum import (
    PersonImRaum,
    RaumEingaben,
    RaumKonfig,
    RaumQuelle,
    RaumTag,
    aggregiere_tag,
)
from custom_components.homewake.logic.zeitplan import Zeitfenster, Zeitplan

BERLIN = ZoneInfo("Europe/Berlin")
DIENSTAG = date(2026, 7, 14)
MITTWOCH = date(2026, 7, 15)


def lokal(tag: date, uhrzeit: str) -> datetime:
    """Berliner Ortszeitpunkt."""
    return datetime.combine(tag, time.fromisoformat(uhrzeit), tzinfo=BERLIN)


def fenster(b: str, e: str) -> Zeitfenster:
    """Zeitfenster aus zwei Uhrzeiten HH:MM."""
    return Zeitfenster(time.fromisoformat(b), time.fromisoformat(e))


# Raum-Standardplan: Mo-Fr 06:00-22:15, Standard 07:00-22:30
STANDARDPLAN = Zeitplan(
    standard=fenster("07:00", "22:30"),
    wochentage=(fenster("06:00", "22:15"),) * 5 + (None, None),
)


def person(
    name: str,
    heute: tuple[str, str],
    morgen: tuple[str, str] = ("06:15", "22:00"),
    *,
    licht: bool = False,
    radio: bool = False,
    favorit: str | None = None,
    naechster: datetime | None = None,
) -> PersonImRaum:
    """Person im Raum am DIENSTAG; nächster Wecker standardmäßig heute."""
    beginn_heute = lokal(DIENSTAG, heute[0])
    return PersonImRaum(
        name=name,
        tagesbeginn_heute=beginn_heute,
        tagesende_heute=lokal(DIENSTAG, heute[1]),
        tagesbeginn_morgen=lokal(MITTWOCH, morgen[0]),
        tagesende_morgen=lokal(MITTWOCH, morgen[1]),
        naechster_wecker=naechster or beginn_heute,
        licht_radio=LichtRadio(licht=licht, radio=radio),
        favorit=favorit,
    )


def eingaben(*personen: PersonImRaum, **aenderungen: object) -> RaumEingaben:
    """Raum-Eingaben ohne Feiertag und ohne Sonnenzeiten."""
    basis = RaumEingaben(
        konfig=RaumKonfig(standardplan=STANDARDPLAN), personen=personen
    )
    return replace(basis, **aenderungen)  # type: ignore[arg-type]


def heute(e: RaumEingaben) -> RaumTag:
    """Zusammenfassung für heute."""
    return aggregiere_tag(e, KandidatTag.HEUTE, heute=DIENSTAG, zeitzone=BERLIN)


VATER = person("Vater", ("06:30", "22:00"))
MUTTER = person("Mutter", ("08:00", "21:30"), licht=True)


# ---------------------------------------------------------------- Personen


def test_eine_person_bestimmt_die_zeiten() -> None:
    """Mit einer Person gelten ihre Zeiten, Quelle Personen."""
    t = heute(eingaben(VATER))
    assert (t.datum, t.weckzeit, t.tagesende_roh) == (
        DIENSTAG,
        lokal(DIENSTAG, "06:30"),
        lokal(DIENSTAG, "22:00"),
    )
    assert t.quelle is RaumQuelle.PERSONEN
    assert t.weckende == ("Vater",)


def test_frueheste_person_und_fruehestes_tagesende_gelten() -> None:
    """Zwei Personen: früheste Weckzeit (06:30), frühestes Tagesende (21:30)."""
    t = heute(eingaben(MUTTER, VATER))
    assert t.weckzeit == lokal(DIENSTAG, "06:30")
    assert t.tagesende_roh == lokal(DIENSTAG, "21:30")
    assert t.weckende == ("Vater",)


def test_licht_radio_nur_von_der_weckenden_person() -> None:
    """Mutter (08:00) will Licht, Vater (06:30) nicht: kein Licht um 06:30 (E24)."""
    t = heute(eingaben(VATER, MUTTER))
    assert (t.licht, t.radio, t.favorit) == (False, False, None)


def test_gleichstand_licht_radio_als_oder_favorit_alphabetisch() -> None:
    """Gleiche Weckzeit: Licht/Radio ODER, Favorit alphabetisch zuerst."""
    a = person("A", ("06:30", "22:00"), radio=True, favorit="WDR 2")
    b = person("B", ("06:30", "22:00"), licht=True, radio=True, favorit="Antenne")
    t = heute(eingaben(a, b))
    assert (t.licht, t.radio, t.favorit) == (True, True, "Antenne")
    assert t.weckende == ("A", "B")


def test_favorit_nur_von_personen_mit_radio() -> None:
    """Ein Favorit zählt nur, wenn die Person Radio möchte."""
    a = person("A", ("06:30", "22:00"), radio=False, favorit="WDR 2")
    b = person("B", ("06:30", "22:00"), radio=True, favorit=None)
    t = heute(eingaben(a, b))
    assert (t.radio, t.favorit) == (True, None)


def test_licht_radio_nur_wenn_der_naechste_wecker_dieser_tag_ist() -> None:
    """Liegt der nächste Wecker der Person nicht auf der Raum-Weckzeit: aus."""
    p = person("C", ("06:30", "22:00"), licht=True, naechster=lokal(MITTWOCH, "06:15"))
    t = heute(eingaben(p))
    assert t.weckzeit == lokal(DIENSTAG, "06:30")
    assert not t.licht


def test_morgen_nimmt_die_morgen_werte_der_personen() -> None:
    """Für morgen gelten Tagesbeginn/-ende von morgen."""
    p = person("C", ("06:30", "22:00"), morgen=("05:45", "21:00"))
    t = aggregiere_tag(eingaben(p), KandidatTag.MORGEN, heute=DIENSTAG, zeitzone=BERLIN)
    assert (t.datum, t.weckzeit, t.tagesende_roh) == (
        MITTWOCH,
        lokal(MITTWOCH, "05:45"),
        lokal(MITTWOCH, "21:00"),
    )


# ---------------------------------------------------------------- Standardplan


def test_leerer_raum_nutzt_standardplan_ohne_licht_radio() -> None:
    """Ohne Personen gilt der Standardplan, ohne Licht/Radio (Abschnitt 3.2)."""
    t = heute(eingaben())
    assert (t.weckzeit, t.tagesende_roh) == (
        lokal(DIENSTAG, "06:00"),
        lokal(DIENSTAG, "22:15"),
    )
    assert t.quelle is RaumQuelle.STANDARDPLAN
    assert (t.licht, t.radio, t.favorit, t.weckende) == (False, False, None, ())


def test_feiertag_heute_nimmt_standardzeile_morgen_wochentag() -> None:
    """Feiertag heute → Standard-Zeile; morgen ohne Feiertag → Wochentag (E13)."""
    e = eingaben(feiertag_heute=True)
    t_heute = heute(e)
    t_morgen = aggregiere_tag(e, KandidatTag.MORGEN, heute=DIENSTAG, zeitzone=BERLIN)
    assert t_heute.weckzeit == lokal(DIENSTAG, "07:00")
    assert t_morgen.weckzeit == lokal(MITTWOCH, "06:00")


def test_nicht_zuordenbarer_raum_ignoriert_personen() -> None:
    """Ist der Raum nicht zuordenbar, gilt der Standardplan trotz Personen."""
    konfig = RaumKonfig(standardplan=STANDARDPLAN, personen_zuordenbar=False)
    t = heute(eingaben(VATER, konfig=konfig))
    assert t.quelle is RaumQuelle.STANDARDPLAN
    assert t.weckzeit == lokal(DIENSTAG, "06:00")


# ---------------------------------------------------------------- Brücke zur Person


def test_person_im_raum_aus_personen_ergebnis() -> None:
    """PersonImRaum übernimmt die Werte aus einem PersonErgebnis."""
    zp = Zeitplan(
        standard=fenster("08:00", "21:00"), wochentage=(fenster("06:15", "22:00"),) * 7
    )
    e = PersonEingaben(
        zeitplan=zp,
        heute=TagInfo(),
        morgen=TagInfo(),
        licht_radio={},
    )
    r = berechne_person(
        e, PersonZustand(), jetzt=lokal(DIENSTAG, "04:00"), zeitzone=BERLIN
    )
    p = PersonImRaum.aus_ergebnis("Vater", r, favorit="WDR 2")
    assert p.name == "Vater"
    assert p.tagesbeginn_heute == lokal(DIENSTAG, "06:15")
    assert p.tagesende_morgen == lokal(MITTWOCH, "22:00")
    assert p.naechster_wecker == r.naechster_wecker
    assert p.licht_radio == r.licht_radio
    assert p.favorit == "WDR 2"
