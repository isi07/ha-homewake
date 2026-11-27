"""Tests für Tagesstatus heute/morgen und die vorbelegte Ausnahme-Zeit (E63, E70).

Die Karte zeigt für heute und morgen je einen Status mit Grund. Bisher gab es
nur den Status für den Tag des nächsten Weckers.
"""

from __future__ import annotations

from datetime import time

from custom_components.homewake.logic.person import (
    GRUND_KEIN_RAUM,
    KandidatTag,
    PersonStatus,
    PersonZustand,
    TagInfo,
)
from tests.logic.test_person_wecken import (
    DIENSTAG,
    GEWECKT,
    LEER,
    MITTWOCH,
    eingaben,
    lokal,
    rechne,
)


def test_normaler_tag_hat_wochentag_als_grund() -> None:
    """Dienstag und Mittwoch: Werktag mit dem Wochentag als Grund."""
    r = rechne(eingaben(), LEER, DIENSTAG, "04:00")
    assert (r.status_heute, r.grund_heute) == (PersonStatus.WERKTAG, "dienstag")
    assert (r.status_morgen, r.grund_morgen) == (PersonStatus.WERKTAG, "mittwoch")


def test_feiertag_morgen() -> None:
    """Morgen Feiertag: Status Feiertag mit Namen, heute unverändert."""
    r = rechne(eingaben(morgen=TagInfo(feiertag="Testtag")), LEER, DIENSTAG, "04:00")
    assert (r.status_heute, r.grund_heute) == (PersonStatus.WERKTAG, "dienstag")
    assert (r.status_morgen, r.grund_morgen) == (PersonStatus.FEIERTAG, "Testtag")


def test_urlaub_heute_schulferien_morgen() -> None:
    """Urlaub ohne Grund (9 #2), Schulferien mit Namen."""
    r = rechne(
        eingaben(heute=TagInfo(urlaub=True), morgen=TagInfo(schulferien="Sommer")),
        LEER,
        DIENSTAG,
        "04:00",
    )
    assert (r.status_heute, r.grund_heute) == (PersonStatus.URLAUB, None)
    assert (r.status_morgen, r.grund_morgen) == (PersonStatus.SCHULFERIEN, "Sommer")


def test_ausnahme_heute_zeigt_heute_ausnahme() -> None:
    """Ausnahme heute 05:00 steht an: heute Ausnahme, morgen Werktag."""
    r = rechne(
        eingaben(ausnahme_aktiv=True, ausnahme_zeit=time(5, 0)), LEER, DIENSTAG, "04:00"
    )
    assert (r.status_heute, r.grund_heute) == (PersonStatus.AUSNAHME, None)
    assert (r.status_morgen, r.grund_morgen) == (PersonStatus.WERKTAG, "mittwoch")


def test_ausnahme_morgen_zeigt_morgen_ausnahme() -> None:
    """Heute schon geweckt: die Ausnahme gilt morgen (E17)."""
    r = rechne(
        eingaben(ausnahme_aktiv=True, ausnahme_zeit=time(5, 0)),
        GEWECKT,
        DIENSTAG,
        "07:00",
    )
    assert (r.status_heute, r.grund_heute) == (PersonStatus.WERKTAG, "dienstag")
    assert (r.status_morgen, r.grund_morgen) == (PersonStatus.AUSNAHME, None)


def test_ohne_raum_beide_tage_inaktiv() -> None:
    """Ohne Raum: heute und morgen Inaktiv mit Grund „kein Raum“ (E8)."""
    r = rechne(eingaben(raum_zugeordnet=False), LEER, DIENSTAG, "04:00")
    assert (r.status_heute, r.grund_heute) == (PersonStatus.INAKTIV, GRUND_KEIN_RAUM)
    assert (r.status_morgen, r.grund_morgen) == (PersonStatus.INAKTIV, GRUND_KEIN_RAUM)


# ---------------------------------------------------------------- E63


def test_ausnahme_ohne_eigene_zeit_nimmt_den_standard_beginn() -> None:
    """Ohne eigene Uhrzeit gilt der Beginn der Standard-Zeile (08:00, E63)."""
    r = rechne(eingaben(ausnahme_aktiv=True), LEER, DIENSTAG, "04:00")
    assert r.status is PersonStatus.AUSNAHME
    assert r.naechster_wecker == lokal(DIENSTAG, "08:00")
    assert not r.ausnahme_ignoriert


def test_ausnahme_ohne_eigene_zeit_gilt_morgen_wenn_heute_vorbei() -> None:
    """Nach 08:00 gilt die Standard-Zeit für morgen (E17)."""
    r = rechne(eingaben(ausnahme_aktiv=True), GEWECKT, DIENSTAG, "09:00")
    assert r.kandidat_tag is KandidatTag.MORGEN
    assert r.naechster_wecker == lokal(MITTWOCH, "08:00")


def test_nach_dem_wecken_durch_die_ausnahme_zeigt_heute_den_plan() -> None:
    """Die Ausnahme hat geweckt: heute wieder Werktag (Zustand merkt nichts, E70)."""
    zustand = PersonZustand(
        naechster_wecker=lokal(DIENSTAG, "05:00"), naechster_ist_ausnahme=True
    )
    r = rechne(
        eingaben(ausnahme_aktiv=True, ausnahme_zeit=time(5, 0)),
        zustand,
        DIENSTAG,
        "05:00",
    )
    assert r.jetzt_geweckt
    assert r.ausnahme_loeschen
    assert (r.status_heute, r.grund_heute) == (PersonStatus.WERKTAG, "dienstag")
