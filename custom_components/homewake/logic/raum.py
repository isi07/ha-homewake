"""Raum-Logik (ARCHITEKTUR.md 3.2, 3.7, 4.5, 4.6, E21 bis E27).

Ein Raum fasst die ihm zugeordneten aktiven Personen **pro Tag** zusammen
(früheste Person gewinnt, frühestes Tagesende gilt) oder nutzt seinen eigenen
Standardplan. Daraus entstehen Weckzeit, geklemmter Tagesbeginn und Tagesende,
„wach“ und „Tag“.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, tzinfo
from enum import StrEnum

from .klemmung import klemme_tagesbeginn, klemme_tagesende
from .person import KandidatTag, LichtRadio, PersonErgebnis
from .zeitplan import Zeitplan, kandidat, naechste_aenderung

STANDARD_KLEMM_FENSTER = timedelta(minutes=60)


class RaumQuelle(StrEnum):
    """Woher die Zeiten eines Raums an einem Tag kommen."""

    PERSONEN = "personen"
    STANDARDPLAN = "standardplan"


@dataclass(frozen=True, slots=True)
class PersonImRaum:
    """Was der Raum von einer zugeordneten, aktiven Person braucht."""

    name: str
    tagesbeginn_heute: datetime
    tagesende_heute: datetime
    tagesbeginn_morgen: datetime
    tagesende_morgen: datetime
    naechster_wecker: datetime
    licht_radio: LichtRadio
    favorit: str | None = None

    @classmethod
    def aus_ergebnis(
        cls, name: str, ergebnis: PersonErgebnis, favorit: str | None
    ) -> PersonImRaum:
        """Baut den Auszug aus dem Ergebnis der Personen-Logik."""
        return cls(
            name=name,
            tagesbeginn_heute=ergebnis.tagesbeginn_heute,
            tagesende_heute=ergebnis.tagesende_heute,
            tagesbeginn_morgen=ergebnis.tagesbeginn_morgen,
            tagesende_morgen=ergebnis.tagesende_morgen,
            naechster_wecker=ergebnis.naechster_wecker,
            licht_radio=ergebnis.licht_radio,
            favorit=favorit,
        )


@dataclass(frozen=True, slots=True)
class RaumKonfig:
    """Konfiguration eines Raums (3.7)."""

    standardplan: Zeitplan
    klemm_beginn: timedelta = STANDARD_KLEMM_FENSTER
    klemm_ende: timedelta = STANDARD_KLEMM_FENSTER
    personen_zuordenbar: bool = True


@dataclass(frozen=True, slots=True)
class Sonne:
    """Morgen- und Abenddämmerung für ein bestimmtes Datum (fehlend = None)."""

    dawn: datetime | None = None
    dusk: datetime | None = None


@dataclass(frozen=True, slots=True)
class RaumEingaben:
    """Alles, was der Raum für einen Lauf braucht.

    ``personen`` enthält nur die diesem Raum zugeordneten aktiven Personen;
    das filtert die HA-Schicht. ``heute``/``morgen`` beziehen sich auf das
    Ortsdatum von „jetzt“.
    """

    konfig: RaumKonfig
    personen: tuple[PersonImRaum, ...] = ()
    feiertag_heute: bool = False
    feiertag_morgen: bool = False
    sonne_heute: Sonne = field(default_factory=Sonne)
    sonne_morgen: Sonne = field(default_factory=Sonne)


@dataclass(frozen=True, slots=True)
class RaumTag:
    """Zusammenfassung eines Raums für einen Tag, noch ungeklemmt."""

    datum: date
    weckzeit: datetime
    tagesende_roh: datetime
    quelle: RaumQuelle
    weckende: tuple[str, ...]
    licht: bool
    radio: bool
    favorit: str | None


def _gleich(a: datetime, b: datetime) -> bool:
    """Ob zwei Zeitpunkte real derselbe Moment sind."""
    return a.timestamp() == b.timestamp()


def _aus_standardplan(
    eingaben: RaumEingaben, tag: date, *, frei: bool, zeitzone: tzinfo
) -> RaumTag:
    """Standardplan des Raums; am Feiertag die Standard-Zeile (E13)."""
    k = kandidat(eingaben.konfig.standardplan, tag, frei=frei, zeitzone=zeitzone)
    return RaumTag(
        datum=tag,
        weckzeit=k.beginn,
        tagesende_roh=k.ende,
        quelle=RaumQuelle.STANDARDPLAN,
        weckende=(),
        licht=False,
        radio=False,
        favorit=None,
    )


def aggregiere_tag(
    eingaben: RaumEingaben, welcher: KandidatTag, *, heute: date, zeitzone: tzinfo
) -> RaumTag:
    """Fasst den Raum für heute oder morgen zusammen (E22, E24).

    Früheste Person bestimmt die Weckzeit, das früheste Tagesende gilt.
    Licht/Radio kommen nur von den Personen, die die Weckzeit bestimmen und
    deren nächster Wecker genau diese Weckzeit ist (Gleichstand: ODER).
    Der Favorit kommt von einer dieser Personen mit Radio, alphabetisch zuerst.
    """
    ist_morgen = welcher is KandidatTag.MORGEN
    tag = heute + timedelta(days=1) if ist_morgen else heute
    personen = eingaben.personen if eingaben.konfig.personen_zuordenbar else ()
    if not personen:
        frei = eingaben.feiertag_morgen if ist_morgen else eingaben.feiertag_heute
        return _aus_standardplan(eingaben, tag, frei=frei, zeitzone=zeitzone)

    def beginn(p: PersonImRaum) -> datetime:
        return p.tagesbeginn_morgen if ist_morgen else p.tagesbeginn_heute

    def ende(p: PersonImRaum) -> datetime:
        return p.tagesende_morgen if ist_morgen else p.tagesende_heute

    weckzeit = min((beginn(p) for p in personen), key=datetime.timestamp)
    tagesende = min((ende(p) for p in personen), key=datetime.timestamp)
    weckende = [p for p in personen if _gleich(beginn(p), weckzeit)]
    mit_wunsch = [p for p in weckende if _gleich(p.naechster_wecker, weckzeit)]
    favoriten = sorted(
        p.favorit for p in mit_wunsch if p.licht_radio.radio and p.favorit
    )
    return RaumTag(
        datum=tag,
        weckzeit=weckzeit,
        tagesende_roh=tagesende,
        quelle=RaumQuelle.PERSONEN,
        weckende=tuple(sorted(p.name for p in weckende)),
        licht=any(p.licht_radio.licht for p in mit_wunsch),
        radio=any(p.licht_radio.radio for p in mit_wunsch),
        favorit=favoriten[0] if favoriten else None,
    )


@dataclass(frozen=True, slots=True)
class RaumWecken:
    """Ein (angekündigtes oder erfolgtes) Wecken des Raums.

    Neben Licht/Radio/Favorit merkt es sich, woher die Weckzeit kam und wer
    geweckt wird, damit auch diese Anzeige bis Mitternacht einfriert (E47).
    """

    zeit: datetime
    licht: bool = False
    radio: bool = False
    favorit: str | None = None
    quelle: RaumQuelle = RaumQuelle.STANDARDPLAN
    weckende: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RaumZustand:
    """Was HomeWake sich pro Raum von Lauf zu Lauf merkt (E21).

    ``datum`` ist der Tag, für den die eingefrorenen Werte gelten. Ein neues
    Datum verwirft sie.
    """

    datum: date | None = None
    geweckt: RaumWecken | None = None
    tagesbeginn: datetime | None = None
    tagesende: datetime | None = None
    angekuendigt: RaumWecken | None = None


@dataclass(frozen=True, slots=True)
class RaumErgebnis:
    """Ergebnis eines Laufs für einen Raum, inklusive neuem Zustand."""

    weckzeit: datetime
    tagesbeginn: datetime
    tagesende: datetime
    tagesende_roh: datetime
    weckzeit_morgen: datetime
    tagesbeginn_morgen: datetime
    tagesende_morgen: datetime
    quelle: RaumQuelle
    personen: tuple[str, ...]
    weckende: tuple[str, ...]
    licht: bool
    radio: bool
    favorit: str | None
    wach: bool
    tag: bool
    jetzt_geweckt: bool
    geweckt_um: datetime | None
    naechste_aenderung: datetime
    zustand: RaumZustand


def _im_zeitraum(beginn: datetime, ende: datetime, jetzt: datetime) -> bool:
    """Ob ``jetzt`` in [beginn, ende) liegt, als echte Zeitpunkte verglichen."""
    return beginn.timestamp() <= jetzt.timestamp() < ende.timestamp()


def _erreicht(zeitpunkt: datetime, jetzt: datetime) -> bool:
    """Ob ``zeitpunkt`` erreicht ist (≤ jetzt), als echte Zeitpunkte verglichen."""
    return zeitpunkt.timestamp() <= jetzt.timestamp()


def _wecken_aus(t: RaumTag) -> RaumWecken:
    """Wecken mit Zeit, Licht/Radio/Favorit, Quelle und Weckenden eines Tags."""
    return RaumWecken(
        zeit=t.weckzeit,
        licht=t.licht,
        radio=t.radio,
        favorit=t.favorit,
        quelle=t.quelle,
        weckende=t.weckende,
    )


def _heutiges_wecken(
    zustand: RaumZustand,
    t_heute: RaumTag,
    *,
    heute: date,
    jetzt: datetime,
    zeitzone: tzinfo,
) -> tuple[RaumWecken | None, bool]:
    """Wecken von heute: schon geweckt, jetzt geweckt oder still geweckt.

    Liefert das heutige Wecken (oder None) und ob es gerade erst passiert ist.
    Geweckt wird mit den *angekündigten* Werten (E21, wie E14 bei Personen).
    Ist die heutige Weckzeit ohne Ankündigung schon vorbei (Neustart, Person
    kam nach ihrem Wecken dazu), gilt der Raum still als geweckt (E23).
    """
    if zustand.datum == heute and zustand.geweckt is not None:
        return zustand.geweckt, False
    ank = zustand.angekuendigt
    if (
        ank is not None
        and ank.zeit.astimezone(zeitzone).date() == heute
        and _erreicht(ank.zeit, jetzt)
    ):
        return ank, True
    if _erreicht(t_heute.weckzeit, jetzt):
        return _wecken_aus(t_heute), False
    return None, False


def _gefroren(
    gespeichert: datetime | None, live: datetime, jetzt: datetime
) -> tuple[datetime, datetime | None]:
    """Wert und neuer gespeicherter Wert: einmal erreicht, bleibt er bis Mitternacht."""
    if gespeichert is not None:
        return gespeichert, gespeichert
    return live, (live if _erreicht(live, jetzt) else None)


def berechne_raum(
    eingaben: RaumEingaben,
    zustand: RaumZustand,
    *,
    jetzt: datetime,
    zeitzone: tzinfo,
) -> RaumErgebnis:
    """Berechnet die Werte eines Raums für heute und morgen (3.7, 4.5, 4.6)."""
    if jetzt.tzinfo is None or jetzt.utcoffset() is None:
        msg = "jetzt muss zeitzonenbehaftet sein"
        raise ValueError(msg)

    heute = jetzt.astimezone(zeitzone).date()
    konfig = eingaben.konfig
    t_heute = aggregiere_tag(
        eingaben, KandidatTag.HEUTE, heute=heute, zeitzone=zeitzone
    )
    t_morgen = aggregiere_tag(
        eingaben, KandidatTag.MORGEN, heute=heute, zeitzone=zeitzone
    )

    # Tageswechsel (E21): eingefrorene Werte gelten nur für ihren Tag.
    if zustand.datum != heute:
        zustand = RaumZustand(datum=heute, angekuendigt=zustand.angekuendigt)

    geweckt, jetzt_geweckt = _heutiges_wecken(
        zustand, t_heute, heute=heute, jetzt=jetzt, zeitzone=zeitzone
    )
    wecken = geweckt or _wecken_aus(t_heute)

    # Einfrieren (4.5): Tagesbeginn wird aus der erreichten Weckzeit geklemmt.
    tagesbeginn, beginn_gespeichert = _gefroren(
        zustand.tagesbeginn,
        klemme_tagesbeginn(wecken.zeit, eingaben.sonne_heute.dawn, konfig.klemm_beginn),
        jetzt,
    )
    tagesende, ende_gespeichert = _gefroren(
        zustand.tagesende,
        klemme_tagesende(
            t_heute.tagesende_roh, eingaben.sonne_heute.dusk, konfig.klemm_ende
        ),
        jetzt,
    )

    # Ankündigung: heute, solange noch nicht geweckt, sonst morgen.
    ankuendigung = _wecken_aus(t_heute) if geweckt is None else _wecken_aus(t_morgen)

    personen = eingaben.personen if konfig.personen_zuordenbar else ()
    return RaumErgebnis(
        weckzeit=wecken.zeit,
        tagesbeginn=tagesbeginn,
        tagesende=tagesende,
        tagesende_roh=t_heute.tagesende_roh,
        weckzeit_morgen=t_morgen.weckzeit,
        tagesbeginn_morgen=klemme_tagesbeginn(
            t_morgen.weckzeit, eingaben.sonne_morgen.dawn, konfig.klemm_beginn
        ),
        tagesende_morgen=klemme_tagesende(
            t_morgen.tagesende_roh, eingaben.sonne_morgen.dusk, konfig.klemm_ende
        ),
        # Quelle und Weckende frieren mit der Weckzeit ein (E47).
        quelle=wecken.quelle,
        personen=tuple(sorted(p.name for p in personen)),
        weckende=wecken.weckende,
        licht=wecken.licht,
        radio=wecken.radio,
        favorit=wecken.favorit,
        # wach ab Weckzeit, Tag ab geklemmtem Beginn, beide bis vor das Ende (E26)
        wach=_im_zeitraum(wecken.zeit, tagesende, jetzt),
        tag=_im_zeitraum(tagesbeginn, tagesende, jetzt),
        jetzt_geweckt=jetzt_geweckt,
        geweckt_um=geweckt.zeit if geweckt is not None else None,
        naechste_aenderung=naechste_aenderung(
            jetzt,
            zeitzone,
            (wecken.zeit, tagesbeginn, tagesende, ankuendigung.zeit),
        ),
        zustand=RaumZustand(
            datum=heute,
            geweckt=geweckt,
            tagesbeginn=beginn_gespeichert,
            tagesende=ende_gespeichert,
            angekuendigt=ankuendigung,
        ),
    )
