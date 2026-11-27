# Changelog

Alle für Nutzer sichtbaren Änderungen an HomeWake, neueste Version oben.

<!--
Regeln für die Pflege (E87):

- Jede für Nutzer sichtbare Änderung bekommt im selben Commit einen Eintrag unter
  „[Unveröffentlicht]“. Reines Aufräumen (refactor), Tests, CI und interne Werkzeuge nicht.
- Abschnitte in dieser Reihenfolge, leere weglassen:
    ### Breaking Changes  – Nutzer müssen etwas tun; immer mit „was zu tun ist“
    ### Neu               – neue Funktionen (feat)
    ### Geändert          – geändertes Verhalten oder geänderte Bedienung
    ### Behoben           – Fehlerbehebungen (fix)
    ### Entfernt          – weggefallene Funktionen oder Entities
- Ein Eintrag = ein Satz aus Sicht der Nutzer („Die Karte zeigt …“), kein Code-Detail, keine
  Personen-, Orts- oder Umgebungsdaten. Bei Bedarf Verweis auf die Entscheidung (E12).
- Beim Release: „[Unveröffentlicht]“ in „[X.Y.Z] – JJJJ-MM-TT“ umbenennen, darüber ein neues,
  leeres „[Unveröffentlicht]“ anlegen, Version in manifest.json, pyproject.toml und uv.lock
  setzen, Tag vX.Y.Z (Ablauf: README, „Release“).
- Versionsnummer: Breaking Change → erste Stelle (vor 1.0.0: zweite), sonst Neu → zweite
  Stelle, nur Behoben → dritte Stelle.
-->

## [Unveröffentlicht]

## [0.2.0] – 2026-11-27

Erste öffentliche Version.

### Neu

- Personen mit Wochenplan (Tagesbeginn und Tagesende je Wochentag, Pflicht-Zeile „Standard“),
  Ausnahme für einen Tag, Raum-Auswahl und Licht/Radio-Schaltern pro Profil.
- Räume fassen ihre Personen zusammen (früheste Person weckt) oder folgen ihrem Standardplan;
  Tagesbeginn und Tagesende werden an die gewählte Dämmerung angepasst. Sensoren für heute und
  morgen sowie „Wach“ und „Tag“ (z. B. für Adaptive Cover Pro).
- Feiertage offline über die Bibliothek `holidays`, Schulferien pro Person von
  mehr-schulferien.de, Urlaub aus einem Kalender in Home Assistant.
- Licht und Radio zur Weckzeit: Helligkeit, Lautstärke und Radio-Favorit, Ausschalten nach der
  eingestellten Dauer, erneute Versuche bei nicht erreichbaren Geräten, Nachholen bis 15 Minuten
  nach einem Neustart.
- Taste „Wecken beenden“ pro Raum.
- Eigene Dashboard-Karte `custom:homewake-card`, wird automatisch angemeldet; zeigt und bedient
  eine Person oder einen Raum.
- Hinweise unter *Reparaturen* (z. B. Kalender nicht lesbar, Schulferien veraltet, Raum gelöscht,
  Gerät fehlt, Radio-Favorit fehlt) und Diagnose-Datei mit geschwärzten Namen.
- Einrichtung vollständig über die Oberfläche; Installation über HACS bzw. den Marketplace als
  benutzerdefiniertes Repository oder als ZIP aus dem Release.
