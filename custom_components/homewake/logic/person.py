"""Personen-Logik (ARCHITEKTUR.md 4.1, 4.3, 4.4).

Baut auf dem Zeitplan-Baustein auf. Bestimmt pro Tag Status, Grund und Profil
und daraus den nächsten Wecker einer Person.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, tzinfo
from enum import StrEnum

from .zeitplan import Quelle, Zeitplan, kandidat, naechste_aenderung

# Status-Grund als Schlüssel; die Anzeige kommt aus den Übersetzungen (E48).
# Freie Namen (Feiertag, Schulferien) bleiben Text.
WOCHENTAGE = (
    "montag",
    "dienstag",
    "mittwoch",
    "donnerstag",
    "freitag",
    "samstag",
    "sonntag",
)
GRUND_KEIN_RAUM = "kein_raum"
ERSTER_WOCHENENDTAG = 5  # date.weekday(): 5 = Samstag


class PersonStatus(StrEnum):
    """Status einer Person für den nächsten Wecker (4.1, 4.4)."""

    AUSNAHME = "ausnahme"
    URLAUB = "urlaub"
    SCHULFERIEN = "schulferien"
    FEIERTAG = "feiertag"
    WOCHENENDE = "wochenende"
    WERKTAG = "werktag"
    INAKTIV = "inaktiv"


class Profil(StrEnum):
    """Welche Licht/Radio-Schalter fürs Wecken gelten (E7)."""

    ZEITPLAN = "zeitplan"
    STANDARD = "standard"
    AUSNAHME = "ausnahme"


@dataclass(frozen=True, slots=True)
class TagInfo:
    """Was an einem Tag für eine Person gilt.

    ``feiertag`` und ``schulferien`` tragen den Namen, wenn der Tag einer ist,
    sonst ``None``. Ob die Person Schulferien oder Urlaub hat, hat der
    Aufrufer schon berücksichtigt.
    """

    feiertag: str | None = None
    schulferien: str | None = None
    urlaub: bool = False

    @property
    def frei(self) -> bool:
        """Ob die Standard-Zeile gilt (Urlaub, Schulferien, Feiertag)."""
        return self.urlaub or self.schulferien is not None or self.feiertag is not None


@dataclass(frozen=True, slots=True)
class Tagesplan:
    """Plan einer Person für einen Tag, ohne Ausnahme."""

    datum: date
    beginn: datetime
    ende: datetime
    status: PersonStatus
    grund: str | None
    profil: Profil


def tagesstatus(tag: date, info: TagInfo) -> tuple[PersonStatus, str | None]:
    """Status und Grund eines Tags nach der Prioritätskette (4.1).

    Urlaub > Schulferien > Feiertag > Wochenende > Werktag. Urlaub hat keinen
    Grund (9 #2), Ferien und Feiertag ihren Namen, sonst der Wochentag als
    Schlüssel (E48).
    """
    if info.urlaub:
        return PersonStatus.URLAUB, None
    if info.schulferien is not None:
        return PersonStatus.SCHULFERIEN, info.schulferien
    if info.feiertag is not None:
        return PersonStatus.FEIERTAG, info.feiertag
    wochentag = WOCHENTAGE[tag.weekday()]
    if tag.weekday() >= ERSTER_WOCHENENDTAG:
        return PersonStatus.WOCHENENDE, wochentag
    return PersonStatus.WERKTAG, wochentag


def tagesplan(
    zeitplan: Zeitplan, tag: date, info: TagInfo, *, zeitzone: tzinfo
) -> Tagesplan:
    """Plan für ``tag``: Zeitfenster aus dem Zeitplan, Status, Grund, Profil."""
    k = kandidat(zeitplan, tag, frei=info.frei, zeitzone=zeitzone)
    status, grund = tagesstatus(tag, info)
    profil = Profil.ZEITPLAN if k.quelle is Quelle.WOCHENTAG else Profil.STANDARD
    return Tagesplan(
        datum=tag,
        beginn=k.beginn,
        ende=k.ende,
        status=status,
        grund=grund,
        profil=profil,
    )


class KandidatTag(StrEnum):
    """Ob der nächste Wecker heute oder morgen liegt."""

    HEUTE = "heute"
    MORGEN = "morgen"


@dataclass(frozen=True, slots=True)
class LichtRadio:
    """Ob beim Wecken Licht und Radio eingeschaltet werden."""

    licht: bool = False
    radio: bool = False


@dataclass(frozen=True, slots=True)
class PersonEingaben:
    """Alles, was HomeWake für eine Person aus der Konfiguration und HA liest.

    ``heute`` und ``morgen`` beziehen sich auf das Ortsdatum von „jetzt“.
    Fehlt ein Profil in ``licht_radio``, sind Licht und Radio aus.
    """

    zeitplan: Zeitplan
    heute: TagInfo
    morgen: TagInfo
    ausnahme_aktiv: bool = False
    # None = keine eigene Uhrzeit: es gilt der Beginn der Standard-Zeile (E63)
    ausnahme_zeit: time | None = None
    licht_radio: Mapping[Profil, LichtRadio] = field(default_factory=dict)
    raum_zugeordnet: bool = True


@dataclass(frozen=True, slots=True)
class PersonZustand:
    """Was HomeWake sich von Lauf zu Lauf merkt (4.3, E14).

    ``naechster_wecker`` ist der zuletzt *angekündigte* Wecker. Geweckt wird,
    sobald er erreicht ist, auch wenn sich die Eingaben inzwischen geändert haben.
    """

    wach: bool = False
    geweckt_um: datetime | None = None
    naechster_wecker: datetime | None = None
    naechster_ist_ausnahme: bool = False


@dataclass(frozen=True, slots=True)
class PersonErgebnis:
    """Ergebnis eines Laufs für eine Person, inklusive neuem Zustand."""

    naechster_wecker: datetime
    naechstes_tagesende: datetime
    kandidat_tag: KandidatTag
    status: PersonStatus
    grund: str | None
    profil: Profil
    licht_radio: LichtRadio
    wach: bool
    geweckt_um: datetime | None
    jetzt_geweckt: bool
    ausnahme_loeschen: bool
    tagesbeginn_heute: datetime
    tagesende_heute: datetime
    tagesbeginn_morgen: datetime
    tagesende_morgen: datetime
    naechste_aenderung: datetime
    zustand: PersonZustand
    # Status und Grund je Tag für die Anzeige (Karte, E70); „Ausnahme“, wenn
    # an diesem Tag eine Ausnahme ansteht
    status_heute: PersonStatus
    grund_heute: str | None
    status_morgen: PersonStatus
    grund_morgen: str | None
    # Aktive Ausnahme, die wegen E18 (ab Tagesende) nicht zählt.
    ausnahme_ignoriert: bool = False


def _vor(a: datetime, b: datetime) -> bool:
    """Ob ``a`` als echter Zeitpunkt vor ``b`` liegt."""
    return a.timestamp() < b.timestamp()


def _erreicht(zeitpunkt: datetime, jetzt: datetime) -> bool:
    """Ob ``zeitpunkt`` erreicht ist, verglichen als echter Zeitpunkt (UTC).

    Zwei ``datetime`` mit derselben Zeitzone vergleicht Python nach Wanduhrzeit;
    über UTC ist der Vergleich auch an der Zeitumstellung eindeutig.
    """
    return zeitpunkt.timestamp() <= jetzt.timestamp()


@dataclass(frozen=True, slots=True)
class _Uebergang:
    """Zwischenergebnis von Wecken und Tagesende (Regeln 1 und 2)."""

    wach: bool
    geweckt_um: datetime | None
    jetzt_geweckt: bool
    ausnahme_verbraucht: bool


@dataclass(frozen=True, slots=True)
class _Wahl:
    """Der gewählte nächste Wecker und der Tagesplan seines Tags."""

    wecker: datetime
    tag: KandidatTag
    ist_ausnahme: bool
    plan: Tagesplan


def _uebergaenge(
    zustand: PersonZustand,
    plan_heute: Tagesplan,
    *,
    jetzt: datetime,
    zeitzone: tzinfo,
) -> _Uebergang:
    """Regel 1 (Wecken) und Regel 2 (Tagesende), beide im selben Lauf möglich."""
    wach = zustand.wach
    geweckt_um = zustand.geweckt_um
    jetzt_geweckt = False
    ausnahme_verbraucht = False
    if (
        not wach
        and zustand.naechster_wecker is not None
        and _erreicht(zustand.naechster_wecker, jetzt)
    ):
        wach = True
        geweckt_um = zustand.naechster_wecker
        jetzt_geweckt = True
        ausnahme_verbraucht = zustand.naechster_ist_ausnahme

    # Ein Weck-Tag vor heute ist längst vorbei; sonst zählt das heutige Tagesende.
    if wach and (
        geweckt_um is None
        or geweckt_um.astimezone(zeitzone).date() != plan_heute.datum
        or _erreicht(plan_heute.ende, jetzt)
    ):
        wach = False
    return _Uebergang(wach, geweckt_um, jetzt_geweckt, ausnahme_verbraucht)


def _ausnahme_zeitpunkte(
    eingaben: PersonEingaben,
    plaene: tuple[Tagesplan, Tagesplan],
    *,
    ausnahme_verbraucht: bool,
    heute_verbraucht: bool,
    jetzt: datetime,
) -> tuple[datetime | None, datetime | None]:
    """Regel 5: Zeitpunkt der Ausnahme heute oder morgen (höchstens einer).

    Zählt nur mit Raum (E8) und wenn sie in diesem Lauf nicht gerade
    verbraucht wurde. Ist sie heute vorbei oder heute schon geweckt, gilt
    sie morgen (E17). Liegt sie nicht vor dem Tagesende ihres Tags, zählt sie
    nicht (E18). Ohne eigene Uhrzeit gilt der Beginn der Standard-Zeile (E63).
    """
    zeit = eingaben.ausnahme_zeit
    if zeit is None:
        zeit = eingaben.zeitplan.standard.beginn
    if (
        not eingaben.ausnahme_aktiv
        or not eingaben.raum_zugeordnet
        or ausnahme_verbraucht
    ):
        return None, None
    plan_heute, plan_morgen = plaene
    zeitzone = plan_heute.beginn.tzinfo
    an_heute = datetime.combine(plan_heute.datum, zeit, tzinfo=zeitzone)
    if not heute_verbraucht and not _erreicht(an_heute, jetzt):
        return (an_heute, None) if _vor(an_heute, plan_heute.ende) else (None, None)
    an_morgen = datetime.combine(plan_morgen.datum, zeit, tzinfo=zeitzone)
    return (None, an_morgen) if _vor(an_morgen, plan_morgen.ende) else (None, None)


def _waehle_wecker(
    plan_heute: Tagesplan,
    plan_morgen: Tagesplan,
    ausnahme: tuple[datetime | None, datetime | None],
    *,
    heute_verbraucht: bool,
    jetzt: datetime,
) -> _Wahl:
    """Regel 4: Ausnahme heute, sonst Plan heute (offen), sonst Ausnahme/Plan morgen."""
    ausnahme_heute, ausnahme_morgen = ausnahme
    if ausnahme_heute is not None:
        return _Wahl(ausnahme_heute, KandidatTag.HEUTE, True, plan_heute)
    if not heute_verbraucht and not _erreicht(plan_heute.beginn, jetzt):
        return _Wahl(plan_heute.beginn, KandidatTag.HEUTE, False, plan_heute)
    if ausnahme_morgen is not None:
        return _Wahl(ausnahme_morgen, KandidatTag.MORGEN, True, plan_morgen)
    return _Wahl(plan_morgen.beginn, KandidatTag.MORGEN, False, plan_morgen)


def _veraltet(zustand: PersonZustand, heute: date, zeitzone: tzinfo) -> bool:
    """Ob der Zustand leer ist oder der angekündigte Wecker vor heute lag (E15)."""
    wecker = zustand.naechster_wecker
    return wecker is None or wecker.astimezone(zeitzone).date() < heute


def _sollzustand(plan_heute: Tagesplan, jetzt: datetime) -> PersonZustand:
    """Regel 6: Zustand direkt aus dem heutigen Plan und der Uhrzeit (E15).

    Ist der heutige Tagesbeginn erreicht, gilt heute als geweckt; wach ist die
    Person bis zum Tagesende. Es wird kein Wecken gemeldet, denn es gab keinen
    angekündigten Wecker.
    """
    if not _erreicht(plan_heute.beginn, jetzt):
        return PersonZustand()
    return PersonZustand(
        wach=not _erreicht(plan_heute.ende, jetzt),
        geweckt_um=plan_heute.beginn,
    )


def _tag_anzeige(
    plan: Tagesplan, ausnahme: datetime | None, inaktiv: bool
) -> tuple[PersonStatus, str | None]:
    """Status und Grund eines Tags für die Anzeige (E70).

    Steht an dem Tag eine Ausnahme an, heißt er „Ausnahme“; ohne Raum ist er
    inaktiv (E8); sonst gilt die Prioritätskette (4.1).
    """
    if ausnahme is not None:
        return PersonStatus.AUSNAHME, None
    if inaktiv:
        return PersonStatus.INAKTIV, GRUND_KEIN_RAUM
    return plan.status, plan.grund


def berechne_person(
    eingaben: PersonEingaben,
    zustand: PersonZustand,
    *,
    jetzt: datetime,
    zeitzone: tzinfo,
) -> PersonErgebnis:
    """Berechnet Wecker, Tagesende, Status und neuen Zustand einer Person (4.3)."""
    if jetzt.tzinfo is None or jetzt.utcoffset() is None:
        msg = "jetzt muss zeitzonenbehaftet sein"
        raise ValueError(msg)

    heute = jetzt.astimezone(zeitzone).date()
    morgen = heute + timedelta(days=1)
    plan_heute = tagesplan(eingaben.zeitplan, heute, eingaben.heute, zeitzone=zeitzone)
    plan_morgen = tagesplan(
        eingaben.zeitplan, morgen, eingaben.morgen, zeitzone=zeitzone
    )

    if _veraltet(zustand, heute, zeitzone):
        zustand = _sollzustand(plan_heute, jetzt)
    u = _uebergaenge(zustand, plan_heute, jetzt=jetzt, zeitzone=zeitzone)
    # Regel 3: heute schon geweckt → heute kein zweiter Wecker.
    heute_verbraucht = (
        u.geweckt_um is not None and u.geweckt_um.astimezone(zeitzone).date() == heute
    )
    ausnahme_heute, ausnahme_morgen = _ausnahme_zeitpunkte(
        eingaben,
        (plan_heute, plan_morgen),
        ausnahme_verbraucht=u.ausnahme_verbraucht,
        heute_verbraucht=heute_verbraucht,
        jetzt=jetzt,
    )
    wahl = _waehle_wecker(
        plan_heute,
        plan_morgen,
        (ausnahme_heute, ausnahme_morgen),
        heute_verbraucht=heute_verbraucht,
        jetzt=jetzt,
    )

    inaktiv = not eingaben.raum_zugeordnet
    if wahl.ist_ausnahme:
        status, grund, profil = PersonStatus.AUSNAHME, None, Profil.AUSNAHME
    elif inaktiv:
        # E8: Zeiten normal, Status Inaktiv mit Grund „kein Raum“ (4.4).
        status, grund, profil = PersonStatus.INAKTIV, GRUND_KEIN_RAUM, wahl.plan.profil
    else:
        status, grund, profil = wahl.plan.status, wahl.plan.grund, wahl.plan.profil

    status_heute, grund_heute = _tag_anzeige(plan_heute, ausnahme_heute, inaktiv)
    status_morgen, grund_morgen = _tag_anzeige(plan_morgen, ausnahme_morgen, inaktiv)

    if heute_verbraucht and u.geweckt_um is not None:
        tagesbeginn_heute = u.geweckt_um
    else:
        tagesbeginn_heute = ausnahme_heute or plan_heute.beginn

    return PersonErgebnis(
        naechster_wecker=wahl.wecker,
        # wach → Ende des Weck-Tags (heute), sonst Ende am Tag des Weckers (E16).
        naechstes_tagesende=plan_heute.ende if u.wach else wahl.plan.ende,
        kandidat_tag=wahl.tag,
        status=status,
        grund=grund,
        profil=profil,
        licht_radio=eingaben.licht_radio.get(profil, LichtRadio()),
        wach=u.wach,
        geweckt_um=u.geweckt_um,
        jetzt_geweckt=u.jetzt_geweckt,
        # E8: bei Inaktiv wird eine aktive Ausnahme gelöscht.
        ausnahme_loeschen=u.ausnahme_verbraucht
        or (inaktiv and eingaben.ausnahme_aktiv),
        status_heute=status_heute,
        grund_heute=grund_heute,
        status_morgen=status_morgen,
        grund_morgen=grund_morgen,
        ausnahme_ignoriert=(
            eingaben.ausnahme_aktiv
            and not inaktiv
            and not u.ausnahme_verbraucht
            and ausnahme_heute is None
            and ausnahme_morgen is None
        ),
        tagesbeginn_heute=tagesbeginn_heute,
        tagesende_heute=plan_heute.ende,
        tagesbeginn_morgen=ausnahme_morgen or plan_morgen.beginn,
        tagesende_morgen=plan_morgen.ende,
        naechste_aenderung=naechste_aenderung(
            jetzt,
            zeitzone,
            (wahl.wecker, plan_heute.ende if u.wach else wahl.plan.ende),
        ),
        zustand=PersonZustand(
            wach=u.wach,
            geweckt_um=u.geweckt_um,
            naechster_wecker=wahl.wecker,
            naechster_ist_ausnahme=wahl.ist_ausnahme,
        ),
    )
