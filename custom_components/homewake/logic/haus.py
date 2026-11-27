"""Ein Lauf über das ganze Haus (ARCHITEKTUR.md 5.1, E31).

Rechnet erst alle Personen, dann alle Räume, mit demselben „jetzt“, wendet die
Bedien-Regeln an (ungültiger Raum → kein Raum, Ausnahme löschen) und liefert
die kleinste „nächste Änderung“.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, time, tzinfo

from .person import (
    LichtRadio,
    PersonEingaben,
    PersonErgebnis,
    PersonZustand,
    Profil,
    TagInfo,
    berechne_person,
)
from .raum import (
    PersonImRaum,
    RaumEingaben,
    RaumErgebnis,
    RaumKonfig,
    RaumZustand,
    Sonne,
    berechne_raum,
)
from .zeitplan import Zeitplan, naechste_aenderung


@dataclass(frozen=True, slots=True)
class PersonKonfig:
    """Konfiguration einer Person aus dem Untereintrag."""

    zeitplan: Zeitplan
    name: str = ""


@dataclass(frozen=True, slots=True)
class PersonBedienung:
    """Bedienwerte einer Person (Entities von HomeWake, gespeichert im Store)."""

    raum_id: str | None = None
    ausnahme_aktiv: bool = False
    ausnahme_zeit: time | None = None
    licht_radio: Mapping[Profil, LichtRadio] = field(default_factory=dict)
    favorit: str | None = None


@dataclass(frozen=True, slots=True)
class HausEingaben:
    """Alles, was ein Lauf braucht; Schlüssel sind die Untereintrags-IDs.

    ``tage`` enthält pro Person (heute, morgen); fehlt sie, gilt ein normaler Tag.
    Feiertag und Sonne gelten für das ganze Haus (Räume). ``raeume_ungueltig``
    sind zuordenbare Räume, deren Standardplan nicht lesbar ist (beschädigte
    Daten): Sie werden nicht gerechnet, nehmen ihren Personen den Raum aber
    nicht weg (E46).
    """

    personen: Mapping[str, PersonKonfig] = field(default_factory=dict)
    bedienung: Mapping[str, PersonBedienung] = field(default_factory=dict)
    zustaende: Mapping[str, PersonZustand] = field(default_factory=dict)
    tage: Mapping[str, tuple[TagInfo, TagInfo]] = field(default_factory=dict)
    raeume: Mapping[str, RaumKonfig] = field(default_factory=dict)
    raum_zustaende: Mapping[str, RaumZustand] = field(default_factory=dict)
    feiertag_heute: bool = False
    feiertag_morgen: bool = False
    sonne_heute: Sonne = field(default_factory=Sonne)
    sonne_morgen: Sonne = field(default_factory=Sonne)
    raeume_ungueltig: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class HausErgebnis:
    """Ergebnis eines Laufs: Personen, Räume, neue Bedienwerte, nächste Änderung.

    ``raum_verloren`` sind die Personen, deren Raum dieser Lauf auf „kein
    Raum“ zurückgesetzt hat (Reparatur-Hinweis, E11).
    """

    personen: dict[str, PersonErgebnis]
    bedienung: dict[str, PersonBedienung]
    naechste_aenderung: datetime
    raeume: dict[str, RaumErgebnis] = field(default_factory=dict)
    raum_verloren: frozenset[str] = frozenset()


def berechne_haus(
    eingaben: HausEingaben, *, jetzt: datetime, zeitzone: tzinfo
) -> HausErgebnis:
    """Rechnet erst alle Personen, dann alle Räume mit demselben „jetzt“ (E31)."""
    zuordenbar = {
        rid for rid, konfig in eingaben.raeume.items() if konfig.personen_zuordenbar
    } | eingaben.raeume_ungueltig
    personen: dict[str, PersonErgebnis] = {}
    bedienung: dict[str, PersonBedienung] = {}
    verloren: set[str] = set()
    for pid, konfig in eingaben.personen.items():
        b = eingaben.bedienung.get(pid, PersonBedienung())
        # E11: ein nicht (mehr) zuordenbarer Raum gilt als „kein Raum“.
        if b.raum_id is not None and b.raum_id not in zuordenbar:
            b = replace(b, raum_id=None)
            verloren.add(pid)
        heute, morgen = eingaben.tage.get(pid, (TagInfo(), TagInfo()))
        ergebnis = berechne_person(
            PersonEingaben(
                zeitplan=konfig.zeitplan,
                heute=heute,
                morgen=morgen,
                ausnahme_aktiv=b.ausnahme_aktiv,
                ausnahme_zeit=b.ausnahme_zeit,
                licht_radio=b.licht_radio,
                raum_zugeordnet=b.raum_id is not None,
            ),
            eingaben.zustaende.get(pid, PersonZustand()),
            jetzt=jetzt,
            zeitzone=zeitzone,
        )
        if ergebnis.ausnahme_loeschen:
            # E63: danach wieder die Standard-Zeit statt der eigenen Uhrzeit
            b = replace(b, ausnahme_aktiv=False, ausnahme_zeit=None)
        personen[pid] = ergebnis
        bedienung[pid] = b

    raeume: dict[str, RaumErgebnis] = {}
    for rid, raum_konfig in eingaben.raeume.items():
        im_raum = tuple(
            PersonImRaum.aus_ergebnis(
                eingaben.personen[pid].name, personen[pid], bedienung[pid].favorit
            )
            for pid in personen
            if bedienung[pid].raum_id == rid
        )
        raeume[rid] = berechne_raum(
            RaumEingaben(
                konfig=raum_konfig,
                personen=im_raum,
                feiertag_heute=eingaben.feiertag_heute,
                feiertag_morgen=eingaben.feiertag_morgen,
                sonne_heute=eingaben.sonne_heute,
                sonne_morgen=eingaben.sonne_morgen,
            ),
            eingaben.raum_zustaende.get(rid, RaumZustand()),
            jetzt=jetzt,
            zeitzone=zeitzone,
        )

    kandidaten = [p.naechste_aenderung for p in personen.values()]
    kandidaten += [r.naechste_aenderung for r in raeume.values()]
    return HausErgebnis(
        personen=personen,
        bedienung=bedienung,
        naechste_aenderung=naechste_aenderung(jetzt, zeitzone, kandidaten),
        raeume=raeume,
        raum_verloren=frozenset(verloren),
    )
