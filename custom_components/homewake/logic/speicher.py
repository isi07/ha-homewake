"""Zustände in speicherbare JSON-Daten umwandeln und zurück (ARCHITEKTUR.md 5.3).

Zeitpunkte werden als ISO-Text mit Zeitzonen-Offset gespeichert. Unlesbare
Daten werden zum Leerzustand; der Sollzustand (E15, E23) heilt das beim
nächsten Lauf.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from .aktorik import AusAuftrag
from .haus import PersonBedienung
from .person import LichtRadio, PersonZustand, Profil
from .raum import RaumQuelle, RaumWecken, RaumZustand
from .schulferien import Ferien, SchulDaten


def _zeit_zu_text(wert: datetime | None) -> str | None:
    """Zeitpunkt als ISO-Text oder None."""
    return wert.isoformat() if wert is not None else None


def _zeit_aus_text(wert: Any) -> datetime | None:
    """Zeitpunkt aus ISO-Text; ValueError bei Unlesbarem oder fehlender Zeitzone."""
    if wert is None:
        return None
    if not isinstance(wert, str):
        msg = f"kein Zeitpunkt: {wert!r}"
        raise ValueError(msg)
    zeitpunkt = datetime.fromisoformat(wert)
    if zeitpunkt.tzinfo is None:
        msg = f"Zeitpunkt ohne Zeitzone: {wert!r}"
        raise ValueError(msg)
    return zeitpunkt


def _bool(wert: Any) -> bool:
    """Wahrheitswert; ValueError bei allem anderen."""
    if not isinstance(wert, bool):
        msg = f"kein Wahrheitswert: {wert!r}"
        raise ValueError(msg)
    return wert


def person_zustand_zu_json(zustand: PersonZustand) -> dict[str, Any]:
    """PersonZustand als JSON-fähiges Dict."""
    return {
        "wach": zustand.wach,
        "geweckt_um": _zeit_zu_text(zustand.geweckt_um),
        "naechster_wecker": _zeit_zu_text(zustand.naechster_wecker),
        "naechster_ist_ausnahme": zustand.naechster_ist_ausnahme,
    }


def person_zustand_aus_json(daten: Any) -> PersonZustand:
    """PersonZustand aus gespeicherten Daten; Unlesbares ergibt den Leerzustand."""
    if not isinstance(daten, dict) or not daten:
        return PersonZustand()
    try:
        return PersonZustand(
            wach=_bool(daten.get("wach", False)),
            geweckt_um=_zeit_aus_text(daten.get("geweckt_um")),
            naechster_wecker=_zeit_aus_text(daten.get("naechster_wecker")),
            naechster_ist_ausnahme=_bool(daten.get("naechster_ist_ausnahme", False)),
        )
    except ValueError:
        return PersonZustand()


def person_bedienung_zu_json(bedienung: PersonBedienung) -> dict[str, Any]:
    """PersonBedienung als JSON-fähiges Dict (Uhrzeit als HH:MM:SS)."""
    zeit = bedienung.ausnahme_zeit
    return {
        "raum_id": bedienung.raum_id,
        "ausnahme_aktiv": bedienung.ausnahme_aktiv,
        "ausnahme_zeit": zeit.isoformat(timespec="seconds") if zeit else None,
        "licht_radio": {
            profil.value: {"licht": lr.licht, "radio": lr.radio}
            for profil, lr in bedienung.licht_radio.items()
        },
        "favorit": bedienung.favorit,
    }


def _text_oder_none(wert: Any) -> str | None:
    """Text oder None; ValueError bei allem anderen."""
    if wert is None or isinstance(wert, str):
        return wert
    msg = f"kein Text: {wert!r}"
    raise ValueError(msg)


def person_bedienung_aus_json(daten: Any) -> PersonBedienung:
    """PersonBedienung aus gespeicherten Daten; Unlesbares ergibt die Standardwerte."""
    if not isinstance(daten, dict) or not daten:
        return PersonBedienung()
    try:
        zeit_text = _text_oder_none(daten.get("ausnahme_zeit"))
        licht_radio_roh = daten.get("licht_radio") or {}
        if not isinstance(licht_radio_roh, dict):
            msg = "licht_radio ist kein Dict"
            raise ValueError(msg)
        return PersonBedienung(
            raum_id=_text_oder_none(daten.get("raum_id")),
            ausnahme_aktiv=_bool(daten.get("ausnahme_aktiv", False)),
            ausnahme_zeit=time.fromisoformat(zeit_text) if zeit_text else None,
            licht_radio={
                Profil(profil): LichtRadio(
                    licht=_bool(werte.get("licht", False)),
                    radio=_bool(werte.get("radio", False)),
                )
                for profil, werte in licht_radio_roh.items()
            },
            favorit=_text_oder_none(daten.get("favorit")),
        )
    except ValueError, AttributeError:
        return PersonBedienung()


def _wecken_zu_json(wecken: RaumWecken | None) -> dict[str, Any] | None:
    """RaumWecken als JSON-Dict oder None."""
    if wecken is None:
        return None
    return {
        "zeit": wecken.zeit.isoformat(),
        "licht": wecken.licht,
        "radio": wecken.radio,
        "favorit": wecken.favorit,
        "quelle": wecken.quelle.value,
        "weckende": list(wecken.weckende),
    }


def _quelle(wert: Any) -> RaumQuelle:
    """Quelle eines Weckens; fehlend oder unbekannt (vor E47) = Standardplan."""
    try:
        return RaumQuelle(wert)
    except ValueError:
        return RaumQuelle.STANDARDPLAN


def _namen(wert: Any) -> tuple[str, ...]:
    """Weckende Personen; fehlend oder unlesbar (vor E47) = keine."""
    if not isinstance(wert, list) or not all(isinstance(n, str) for n in wert):
        return ()
    return tuple(wert)


def _wecken_aus_json(daten: Any) -> RaumWecken | None:
    """RaumWecken aus JSON; ValueError bei Unlesbarem."""
    if daten is None:
        return None
    if not isinstance(daten, dict):
        msg = f"kein Wecken: {daten!r}"
        raise ValueError(msg)
    zeit = _zeit_aus_text(daten.get("zeit"))
    if zeit is None:
        msg = "Wecken ohne Zeit"
        raise ValueError(msg)
    return RaumWecken(
        zeit=zeit,
        licht=_bool(daten.get("licht", False)),
        radio=_bool(daten.get("radio", False)),
        favorit=_text_oder_none(daten.get("favorit")),
        quelle=_quelle(daten.get("quelle")),
        weckende=_namen(daten.get("weckende")),
    )


def raum_zustand_zu_json(zustand: RaumZustand) -> dict[str, Any]:
    """RaumZustand als JSON-fähiges Dict."""
    return {
        "datum": zustand.datum.isoformat() if zustand.datum else None,
        "geweckt": _wecken_zu_json(zustand.geweckt),
        "tagesbeginn": _zeit_zu_text(zustand.tagesbeginn),
        "tagesende": _zeit_zu_text(zustand.tagesende),
        "angekuendigt": _wecken_zu_json(zustand.angekuendigt),
    }


def raum_zustand_aus_json(daten: Any) -> RaumZustand:
    """RaumZustand aus gespeicherten Daten; Unlesbares ergibt den Leerzustand."""
    if not isinstance(daten, dict) or not daten:
        return RaumZustand()
    try:
        datum_text = _text_oder_none(daten.get("datum"))
        return RaumZustand(
            datum=date.fromisoformat(datum_text) if datum_text else None,
            geweckt=_wecken_aus_json(daten.get("geweckt")),
            tagesbeginn=_zeit_aus_text(daten.get("tagesbeginn")),
            tagesende=_zeit_aus_text(daten.get("tagesende")),
            angekuendigt=_wecken_aus_json(daten.get("angekuendigt")),
        )
    except ValueError:
        return RaumZustand()


def aus_auftrag_zu_json(auftrag: AusAuftrag | None) -> dict[str, Any] | None:
    """Aus-Auftrag der Aktorik als JSON-Dict oder None (E12)."""
    if auftrag is None:
        return None
    return {
        "um": auftrag.um.isoformat(),
        "lichter": list(auftrag.lichter),
        "lautsprecher": auftrag.lautsprecher,
        "quelle": auftrag.quelle,
    }


def aus_auftrag_aus_json(daten: Any) -> AusAuftrag | None:
    """Aus-Auftrag aus gespeicherten Daten; fehlend oder unlesbar = keiner."""
    if not isinstance(daten, dict):
        return None
    try:
        um = _zeit_aus_text(daten.get("um"))
        lichter = daten.get("lichter") or []
        if um is None or not isinstance(lichter, list):
            return None
        if not all(isinstance(eid, str) for eid in lichter):
            return None
        return AusAuftrag(
            um=um,
            lichter=tuple(lichter),
            lautsprecher=_text_oder_none(daten.get("lautsprecher")),
            quelle=_text_oder_none(daten.get("quelle")),
        )
    except ValueError:
        return None


def urlaub_zu_json(tage: dict[date, bool]) -> dict[str, bool]:
    """Zuletzt gelesener Urlaub pro Tag als JSON (E38): ``{"2026-11-26": true}``."""
    return {tag.isoformat(): urlaub for tag, urlaub in sorted(tage.items())}


def urlaub_aus_json(daten: Any) -> dict[date, bool]:
    """Zuletzt gelesener Urlaub pro Tag; Unlesbares ergibt „nichts bekannt“."""
    if not isinstance(daten, dict):
        return {}
    try:
        return {date.fromisoformat(tag): _bool(wert) for tag, wert in daten.items()}
    except TypeError, ValueError:
        return {}


def schulferien_zu_json(daten: SchulDaten) -> dict[str, Any]:
    """Geladene Schulferien einer Schule als JSON (E41).

    ``{"abgerufen": "…+01:00",
    "ferien": [["2026-12-23", "2027-01-12", "Weihnachten"]]}``
    """
    return {
        "abgerufen": _zeit_zu_text(daten.abgerufen),
        "ferien": [
            [f.beginn.isoformat(), f.ende.isoformat(), f.name] for f in daten.ferien
        ],
    }


def schulferien_aus_json(daten: Any) -> SchulDaten:
    """Geladene Schulferien; Unlesbares ergibt „keine Daten“ (dann neu abrufen)."""
    if not isinstance(daten, dict):
        return SchulDaten()
    try:
        roh = daten.get("ferien") or []
        if not isinstance(roh, list):
            msg = "ferien ist keine Liste"
            raise ValueError(msg)
        ferien: list[Ferien] = []
        for beginn, ende, name in roh:
            if not isinstance(name, str):
                msg = f"kein Name: {name!r}"
                raise ValueError(msg)
            ferien.append(
                Ferien(date.fromisoformat(beginn), date.fromisoformat(ende), name)
            )
        return SchulDaten(
            abgerufen=_zeit_aus_text(daten.get("abgerufen")), ferien=tuple(ferien)
        )
    except TypeError, ValueError:
        return SchulDaten()
