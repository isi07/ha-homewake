"""Dawn/Dusk-Klemmung für Räume (ARCHITEKTUR.md 4.6, E25).

Morgens wird der Tagesbeginn an die Morgendämmerung (Dawn) geklemmt, mit einem
Fenster *nach* der Weckzeit. Abends wird das Tagesende an die Abenddämmerung
(Dusk) geklemmt, mit einem Fenster *vor* dem Tagesende.

Gerechnet wird in echten Zeitpunkten (UTC), damit „+60 Minuten“ auch an der
Zeitumstellung 60 echte Minuten sind. Das Ergebnis liegt in der Zeitzone der
Weck- bzw. Endzeit.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def _pruefe_fenster(fenster: timedelta) -> None:
    """Lehnt ein negatives Klemm-Fenster ab."""
    if fenster < timedelta(0):
        msg = f"Klemm-Fenster darf nicht negativ sein: {fenster}"
        raise ValueError(msg)


def klemme_tagesbeginn(
    weckzeit: datetime, dawn: datetime | None, fenster: timedelta
) -> datetime:
    """Tagesbeginn = Weckzeit, Dawn oder Weckzeit+Fenster.

    Dawn ≤ Weckzeit → Weckzeit (schon hell). Dawn im Fenster → Dawn.
    Dawn nach dem Fenster → Weckzeit+Fenster. Fehlt Dawn, bleibt die Weckzeit.
    """
    _pruefe_fenster(fenster)
    if dawn is None:
        return weckzeit
    w = weckzeit.astimezone(UTC)
    ergebnis = min(max(w, dawn.astimezone(UTC)), w + fenster)
    return ergebnis.astimezone(weckzeit.tzinfo)


def klemme_tagesende(
    tagesende: datetime, dusk: datetime | None, fenster: timedelta
) -> datetime:
    """Tagesende = Ende-Fenster, Dusk oder Ende (spiegelbildlich zum Beginn).

    Dusk ≤ Ende-Fenster → Ende-Fenster (früh dunkel). Dusk im Fenster → Dusk.
    Dusk nach dem Ende → Ende (nie später). Fehlt Dusk, bleibt das Ende.
    """
    _pruefe_fenster(fenster)
    if dusk is None:
        return tagesende
    e = tagesende.astimezone(UTC)
    ergebnis = max(min(e, dusk.astimezone(UTC)), e - fenster)
    return ergebnis.astimezone(tagesende.tzinfo)
