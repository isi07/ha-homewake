"""Tests für Raum-Werte heute/morgen, wach und Tag (ARCHITEKTUR.md 3.7, 4.6, E26)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest

from custom_components.homewake.logic.raum import (
    RaumEingaben,
    RaumErgebnis,
    RaumQuelle,
    RaumZustand,
    Sonne,
    berechne_raum,
)
from tests.logic.test_raum_tag import (
    BERLIN,
    DIENSTAG,
    MITTWOCH,
    MUTTER,
    VATER,
    eingaben,
    lokal,
    person,
)

SONNE_HEUTE = Sonne(dawn=lokal(DIENSTAG, "06:58"), dusk=lokal(DIENSTAG, "20:30"))
SONNE_MORGEN = Sonne(dawn=lokal(MITTWOCH, "07:00"), dusk=lokal(MITTWOCH, "20:28"))


def mit_sonne(e: RaumEingaben) -> RaumEingaben:
    """Ergänzt Dawn/Dusk für heute und morgen."""
    return replace(e, sonne_heute=SONNE_HEUTE, sonne_morgen=SONNE_MORGEN)


def rechne(e: RaumEingaben, uhrzeit: str) -> RaumErgebnis:
    """berechne_raum am DIENSTAG ohne gespeicherten Zustand."""
    return berechne_raum(
        e, RaumZustand(), jetzt=lokal(DIENSTAG, uhrzeit), zeitzone=BERLIN
    )


SCHLAFZIMMER = mit_sonne(eingaben(VATER, MUTTER))


# ---------------------------------------------------------------- Werte heute


def test_werte_heute_mit_klemmung() -> None:
    """Weckzeit 06:30, Tagesbeginn an Dawn 06:58, Tagesende an Fensterstart 21:00."""
    r = rechne(SCHLAFZIMMER, "04:00")
    assert r.weckzeit == lokal(DIENSTAG, "06:30")
    assert r.tagesbeginn == lokal(DIENSTAG, "06:58")
    assert r.tagesende_roh == lokal(DIENSTAG, "21:30")
    # Dusk 20:30 liegt im Fenster 20:30-21:30 → Dusk
    assert r.tagesende == lokal(DIENSTAG, "20:30")


def test_werte_morgen_mit_sonne_von_morgen() -> None:
    """Die Morgen-Sensoren nutzen die Personenwerte und Dawn/Dusk von morgen (E22)."""
    r = rechne(SCHLAFZIMMER, "04:00")
    assert r.weckzeit_morgen == lokal(MITTWOCH, "06:15")
    assert r.tagesbeginn_morgen == lokal(MITTWOCH, "07:00")
    assert r.tagesende_morgen == lokal(MITTWOCH, "21:00")


def test_ohne_sonne_wird_nicht_geklemmt() -> None:
    """Ohne Dawn/Dusk sind Tagesbeginn und -ende ungeklemmt (E25)."""
    r = rechne(eingaben(VATER), "04:00")
    assert r.tagesbeginn == lokal(DIENSTAG, "06:30")
    assert r.tagesende == lokal(DIENSTAG, "22:00")


def test_personen_und_quelle() -> None:
    """Alle Personen des Raums als Liste, weckende Person, Quelle Personen."""
    r = rechne(SCHLAFZIMMER, "04:00")
    assert r.personen == ("Mutter", "Vater")  # alphabetisch
    assert r.weckende == ("Vater",)
    assert r.quelle is RaumQuelle.PERSONEN


def test_standardplan_raum_klemmt_an_dawn() -> None:
    """Standardplan 06:00, Dawn 06:05:13: Tagesbeginn 06:05:13 (alter Anker-Test)."""
    e = replace(eingaben(), sonne_heute=Sonne(dawn=lokal(DIENSTAG, "06:05:13")))
    r = rechne(e, "04:00")
    assert r.quelle is RaumQuelle.STANDARDPLAN
    assert r.personen == ()
    assert r.tagesbeginn == lokal(DIENSTAG, "06:05:13")


# ---------------------------------------------------------------- wach und Tag


@pytest.mark.parametrize(
    ("uhrzeit", "wach", "tag"),
    [
        ("04:00", False, False),
        ("06:30", True, False),
        ("06:45", True, False),
        ("06:58", True, True),
        ("20:29", True, True),
        ("20:30", False, False),
        ("23:00", False, False),
    ],
    ids=[
        "nacht",
        "genau_weckzeit",
        "wach_vor_dawn",
        "genau_tagesbeginn",
        "kurz_vor_tagesende",
        "genau_tagesende",
        "spaet_abends",
    ],
)
def test_wach_und_tag_im_tagesverlauf(uhrzeit: str, wach: bool, tag: bool) -> None:
    """Wach ab Weckzeit, Tag ab geklemmtem Beginn, beide bis vor das Ende."""
    r = rechne(SCHLAFZIMMER, uhrzeit)
    assert (r.wach, r.tag) == (wach, tag)


def test_kein_tag_wenn_beginn_nicht_vor_ende() -> None:
    """Liegt der geklemmte Beginn nicht vor dem Ende, ist nie Tag (E26)."""
    kurz = person("Kurz", ("06:30", "07:00"))
    e = replace(eingaben(kurz), sonne_heute=Sonne(dawn=lokal(DIENSTAG, "08:00")))
    r_frueh = rechne(e, "06:45")
    assert r_frueh.tagesbeginn == lokal(DIENSTAG, "07:30")
    assert r_frueh.wach
    assert not r_frueh.tag
    assert not rechne(e, "07:45").tag


def test_jetzt_ohne_zeitzone_ist_ein_fehler() -> None:
    """„jetzt“ muss zeitzonenbehaftet sein."""
    naiv = datetime(2026, 7, 14, 4, 0)  # noqa: DTZ001
    with pytest.raises(ValueError):
        berechne_raum(SCHLAFZIMMER, RaumZustand(), jetzt=naiv, zeitzone=BERLIN)
