"""Tests für den Lauf über das ganze Haus (ARCHITEKTUR.md 5.1, E8, E11, E31)."""

from __future__ import annotations

from datetime import time

from custom_components.homewake.logic.haus import (
    HausEingaben,
    HausErgebnis,
    PersonBedienung,
    PersonKonfig,
    berechne_haus,
)
from custom_components.homewake.logic.person import (
    PersonStatus,
    PersonZustand,
    TagInfo,
)
from custom_components.homewake.logic.raum import RaumKonfig, RaumQuelle, RaumZustand
from tests.logic.test_person_wecken import (
    DIENSTAG,
    MITTWOCH,
    VOR_DEM_WECKEN,
    ZEITPLAN,
    fenster,
    lokal,
    woche,
)
from tests.logic.test_raum_tag import BERLIN, STANDARDPLAN

RAUM = "raum_schlafzimmer"
KONFIG = PersonKonfig(zeitplan=ZEITPLAN, name="Vater")
RAUM_KONFIG = RaumKonfig(standardplan=STANDARDPLAN)


def rechne(e: HausEingaben, uhrzeit: str) -> HausErgebnis:
    """berechne_haus am DIENSTAG."""
    return berechne_haus(e, jetzt=lokal(DIENSTAG, uhrzeit), zeitzone=BERLIN)


def test_leeres_haus_rechnet_bis_mitternacht() -> None:
    """Ohne Personen gibt es nichts zu tun; nächste Änderung ist Mitternacht."""
    r = rechne(HausEingaben(), "04:00")
    assert r.personen == {}
    assert r.naechste_aenderung == lokal(MITTWOCH, "00:00")


def test_person_ohne_raum_ist_inaktiv() -> None:
    """Ohne Raum: Status Inaktiv, Zeiten trotzdem berechnet (E8)."""
    r = rechne(HausEingaben(personen={"p1": KONFIG}), "04:00")
    assert r.personen["p1"].status is PersonStatus.INAKTIV
    assert r.personen["p1"].naechster_wecker == lokal(DIENSTAG, "06:15")


def test_person_mit_gueltigem_raum_ist_aktiv() -> None:
    """Mit einem gültigen Raum ist die Person aktiv."""
    e = HausEingaben(
        personen={"p1": KONFIG},
        bedienung={"p1": PersonBedienung(raum_id=RAUM)},
        raeume={RAUM: RAUM_KONFIG},
    )
    assert rechne(e, "04:00").personen["p1"].status is PersonStatus.WERKTAG


def test_ungueltiger_raum_wird_zu_kein_raum() -> None:
    """Zeigt die Raum-Auswahl auf einen fehlenden Raum, gilt „kein Raum“ (E11)."""
    e = HausEingaben(
        personen={"p1": KONFIG},
        bedienung={"p1": PersonBedienung(raum_id="geloescht")},
    )
    r = rechne(e, "04:00")
    assert r.personen["p1"].status is PersonStatus.INAKTIV
    assert r.bedienung["p1"].raum_id is None


def test_ausnahme_nach_dem_wecken_wird_in_der_bedienung_geloescht() -> None:
    """Weckt die Ausnahme, ist sie danach in der Bedienung aus (4.3)."""
    e = HausEingaben(
        personen={"p1": KONFIG},
        bedienung={
            "p1": PersonBedienung(
                raum_id=RAUM, ausnahme_aktiv=True, ausnahme_zeit=time(5, 0)
            )
        },
        zustaende={
            "p1": PersonZustand(
                naechster_wecker=lokal(DIENSTAG, "05:00"), naechster_ist_ausnahme=True
            )
        },
        raeume={RAUM: RAUM_KONFIG},
    )
    r = rechne(e, "05:00")
    assert r.personen["p1"].wach
    assert not r.bedienung["p1"].ausnahme_aktiv
    # E63: zurück auf die Standard-Zeit (keine eigene Uhrzeit mehr)
    assert r.bedienung["p1"].ausnahme_zeit is None


def test_ausnahme_einer_inaktiven_person_wird_geloescht() -> None:
    """Ohne Raum wird eine aktive Ausnahme gelöscht (E8)."""
    e = HausEingaben(
        personen={"p1": KONFIG},
        bedienung={
            "p1": PersonBedienung(ausnahme_aktiv=True, ausnahme_zeit=time(5, 0))
        },
    )
    b = rechne(e, "04:00").bedienung["p1"]
    assert not b.ausnahme_aktiv
    assert b.ausnahme_zeit is None  # E63


def test_zustand_und_tage_werden_pro_person_genutzt() -> None:
    """Gespeicherter Zustand und Feiertag-Info gelten je Person."""
    e = HausEingaben(
        personen={"p1": KONFIG, "p2": KONFIG},
        zustaende={"p1": VOR_DEM_WECKEN},
        tage={"p2": (TagInfo(feiertag="Fronleichnam"), TagInfo())},
    )
    r = rechne(e, "06:15")
    assert r.personen["p1"].jetzt_geweckt
    assert r.personen["p2"].naechster_wecker == lokal(DIENSTAG, "08:00")


def test_naechste_aenderung_ist_die_frueheste_aller_personen() -> None:
    """Die nächste Änderung des Hauses ist die früheste aller Personen."""
    frueh = PersonKonfig(zeitplan=woche(fenster("05:30", "21:00")))
    e = HausEingaben(personen={"p1": KONFIG, "p2": frueh})
    assert rechne(e, "04:00").naechste_aenderung == lokal(DIENSTAG, "05:30")


def test_neue_zustaende_stehen_im_ergebnis() -> None:
    """Die neuen Zustände zum Speichern liegen in den Personen-Ergebnissen."""
    e = HausEingaben(personen={"p1": KONFIG}, zustaende={"p1": VOR_DEM_WECKEN})
    r = rechne(e, "06:15")
    assert r.personen["p1"].zustand.wach
    assert r.personen["p1"].zustand.naechster_wecker == lokal(MITTWOCH, "06:15")


# ---------------------------------------------------------------- Räume (Phase 2)


def test_nicht_zuordenbarer_raum_gilt_als_kein_raum() -> None:
    """Zeigt die Person auf einen nicht zuordenbaren Raum, ist sie inaktiv (E11)."""
    nicht = RaumKonfig(standardplan=STANDARDPLAN, personen_zuordenbar=False)
    e = HausEingaben(
        personen={"p1": KONFIG},
        bedienung={"p1": PersonBedienung(raum_id=RAUM)},
        raeume={RAUM: nicht},
    )
    r = rechne(e, "04:00")
    assert r.personen["p1"].status is PersonStatus.INAKTIV
    assert r.bedienung["p1"].raum_id is None


def test_raum_mit_person_nimmt_ihre_zeiten() -> None:
    """Ein Raum mit einer aktiven Person nimmt deren Weckzeit und Favorit."""
    e = HausEingaben(
        personen={"p1": KONFIG},
        bedienung={"p1": PersonBedienung(raum_id=RAUM, favorit="SWR3")},
        raeume={RAUM: RAUM_KONFIG},
    )
    raum = rechne(e, "04:00").raeume[RAUM]
    assert raum.quelle is RaumQuelle.PERSONEN
    assert raum.personen == ("Vater",)
    assert raum.weckzeit == lokal(DIENSTAG, "06:15")
    assert raum.zustand.angekuendigt is not None


def test_raum_ohne_person_nimmt_standardplan() -> None:
    """Ein Raum ohne Personen läuft über seinen Standardplan (06:00)."""
    e = HausEingaben(personen={"p1": KONFIG}, raeume={RAUM: RAUM_KONFIG})
    raum = rechne(e, "04:00").raeume[RAUM]
    assert raum.quelle is RaumQuelle.STANDARDPLAN
    assert raum.weckzeit == lokal(DIENSTAG, "06:00")


def test_raum_feiertag_gilt_fuer_den_standardplan() -> None:
    """Der Feiertag des Hauses gilt auch für den Raum-Standardplan (E13)."""
    e = HausEingaben(raeume={RAUM: RAUM_KONFIG}, feiertag_heute=True)
    assert rechne(e, "04:00").raeume[RAUM].weckzeit == lokal(DIENSTAG, "07:00")


def test_raum_zustand_wird_genutzt() -> None:
    """Der gespeicherte Raum-Zustand fließt in die Rechnung ein (Wecken)."""
    vorher = rechne(HausEingaben(raeume={RAUM: RAUM_KONFIG}), "04:00")
    e = HausEingaben(
        raeume={RAUM: RAUM_KONFIG},
        raum_zustaende={RAUM: vorher.raeume[RAUM].zustand},
    )
    raum = rechne(e, "06:00").raeume[RAUM]
    assert raum.jetzt_geweckt
    assert raum.zustand.geweckt is not None


def test_naechste_aenderung_beruecksichtigt_raeume() -> None:
    """Auch Räume bestimmen die nächste Änderung (hier Standardplan 06:00)."""
    e = HausEingaben(personen={"p1": KONFIG}, raeume={RAUM: RAUM_KONFIG})
    assert rechne(e, "04:00").naechste_aenderung == lokal(DIENSTAG, "06:00")


def test_leerer_raum_zustand_ist_leer() -> None:
    """Ohne gespeicherten Zustand startet der Raum mit dem Leerzustand."""
    e = HausEingaben(raeume={RAUM: RAUM_KONFIG})
    assert rechne(e, "04:00").raeume[RAUM].zustand.geweckt is None
    assert RaumZustand().geweckt is None


# ------------------------------------------------- Raum verloren / ungültig (Phase 8)


def test_zurueckgesetzter_raum_wird_gemeldet() -> None:
    """Setzt der Lauf den Raum einer Person zurück, meldet er sie (Hinweis, E11)."""
    e = HausEingaben(
        personen={"p1": KONFIG, "p2": KONFIG},
        bedienung={
            "p1": PersonBedienung(raum_id="geloescht"),
            "p2": PersonBedienung(raum_id=RAUM),
        },
        raeume={RAUM: RAUM_KONFIG},
    )
    assert rechne(e, "04:00").raum_verloren == frozenset({"p1"})


def test_ohne_raum_wird_nichts_gemeldet() -> None:
    """Eine Person, die schon keinen Raum hat, wird nicht gemeldet."""
    r = rechne(HausEingaben(personen={"p1": KONFIG}), "04:00")
    assert r.raum_verloren == frozenset()


def test_raum_mit_ungueltigem_plan_behaelt_seine_personen() -> None:
    """Ein Raum mit unlesbarem Standardplan nimmt den Personen den Raum nicht (E46).

    Die Person bleibt aktiv; der Raum selbst wird nicht gerechnet.
    """
    e = HausEingaben(
        personen={"p1": KONFIG},
        bedienung={"p1": PersonBedienung(raum_id=RAUM)},
        raeume_ungueltig=frozenset({RAUM}),
    )
    r = rechne(e, "04:00")
    assert r.bedienung["p1"].raum_id == RAUM
    assert r.personen["p1"].status is PersonStatus.WERKTAG
    assert RAUM not in r.raeume
    assert r.raum_verloren == frozenset()
