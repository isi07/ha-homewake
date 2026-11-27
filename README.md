# HomeWake

[![CI](https://github.com/isi07/ha-homewake/actions/workflows/ci.yml/badge.svg)](https://github.com/isi07/ha-homewake/actions/workflows/ci.yml)
[![Validate](https://github.com/isi07/ha-homewake/actions/workflows/validate.yml/badge.svg)](https://github.com/isi07/ha-homewake/actions/workflows/validate.yml)

Wecker fürs Zuhause in Home Assistant: HomeWake berechnet Weckzeiten für Personen
und Räume (aus Zeitplänen, Kalendern, Ferien und Sonnenzeiten), schaltet zum Weckzeitpunkt
Licht und Radio und liefert einen Tag/Nacht-Status, z. B. für Rollläden.

> **Status:** frühe Version (0.2.0). HomeWake berechnet Weckzeiten, Tagesbeginn und
> Tagesende für Personen und Räume, schaltet zur Weckzeit Licht und Radio und bringt eine
> eigene Dashboard-Karte mit. Rollläden steuert HomeWake nicht selbst; dafür lassen sich die
> Sensoren (z. B. *Tag*) in eigenen Automationen oder in Adaptive Cover Pro nutzen.

## Was HomeWake macht

- **Personen** haben einen Wochenplan mit Weckzeit (Tagesbeginn) und Tagesende pro Wochentag
  und einer Pflicht-Zeile **Standard**. An Feiertagen, in den Schulferien (wenn eine Schule
  eingetragen ist) und im Urlaub (aus einem Kalender) gilt die Standard-Zeile. Für einen
  einzelnen Tag lässt sich eine **Ausnahme** setzen.
- **Räume** fassen die Personen zusammen, die ihnen zugeordnet sind: Die früheste Person
  bestimmt die Weckzeit, das früheste Tagesende gilt. Ohne Personen folgt ein Raum seinem
  eigenen Standardplan. Tagesbeginn und Tagesende werden an die Dämmerung angepasst
  („Klemmung“), damit z. B. Rollläden nicht im Dunkeln öffnen.
- Feiertage rechnet HomeWake offline (Bibliothek `holidays`), Schulferien lädt es von
  [mehr-schulferien.de](https://www.mehr-schulferien.de) und speichert ein Jahr Vorrat.
  Fällt eine Quelle aus, weckt HomeWake mit dem zuletzt bekannten Stand weiter und meldet
  das unter *Einstellungen → Reparaturen*.

**Entities pro Person:** Nächster Wecker, Nächstes Tagesende, Status (Werktag, Wochenende,
Feiertag, Schulferien, Urlaub, Ausnahme, Inaktiv), Wach, Raum-Auswahl, Ausnahme (Schalter
und Uhrzeit), Licht/Radio-Schalter pro Profil, Radio-Favorit.

**Entities pro Raum:** Weckzeit, Tagesbeginn und Tagesende für heute und morgen, Wach, Tag
(z. B. für Adaptive Cover Pro), Standard-Favorit (mit Lautsprecher).

Eine Person ohne Raum ist **inaktiv**: Ihre Zeiten werden angezeigt, aber kein Raum weckt sie.

## Installation

HomeWake braucht Home Assistant **2026.11** oder neuer.

### Über den Marketplace (empfohlen)

> Erst möglich, sobald das Repository öffentlich ist. Der Marketplace liest nur öffentliche
> GitHub-Repositories.

1. *Einstellungen → Marketplace* öffnen.
2. Dieses Repository als benutzerdefiniertes Repository hinzufügen
   (`https://github.com/isi07/ha-homewake`, Typ *Integration*) und HomeWake installieren.
3. Home Assistant neu starten.
4. *Einstellungen → Geräte & Dienste → Integration hinzufügen → „HomeWake“*.

### Manuell

1. Unter [Releases](https://github.com/isi07/ha-homewake/releases) die Datei `homewake.zip`
   der gewünschten Version laden und in einen neuen Ordner `config/custom_components/homewake/`
   deiner Home-Assistant-Instanz entpacken (alternativ den Ordner `custom_components/homewake`
   aus dem Repository dorthin kopieren).
2. Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → „HomeWake“*.

## Einrichten

HomeWake wird nur über die Oberfläche eingerichtet (kein YAML). Es gibt genau einen
Eintrag „HomeWake“ für das Haus; Personen und Räume legst du darunter an
(*HomeWake → Person hinzufügen* bzw. *Raum hinzufügen*). Jede Person und jeder Raum wird ein
Gerät mit eigenen Entities.

### Haus (beim Hinzufügen, später über „Neu konfigurieren“)

| Feld | Bedeutung |
|---|---|
| Land | Land für die Feiertage (Pflichtfeld, vorbelegt mit dem Land aus den HA-Einstellungen). |
| Bundesland / Region | Optional. Ohne Region gelten nur landesweite Feiertage. |
| Sonnenstand morgens / abends | Welche Dämmerung für Tagesbeginn bzw. Tagesende gilt: astronomisch (−18°), nautisch (−12°), **bürgerlich (−6°, Standard)**, Ende der blauen Stunde (−4°), Sonnenauf-/-untergang, Horizont (0°), Ende der goldenen Stunde (+6°) oder eine eigene Gradzahl. Der Standort kommt aus den HA-Einstellungen. |

### Person

| Feld | Bedeutung |
|---|---|
| Name | Wird Gerätename und Teil der Entity-Namen. |
| Zeitplan | Pro Wochentag optional Tagesbeginn (Weckzeit) und Tagesende, dazu die Pflicht-Zeile **Standard**. Ein Wochentag ohne Zeiten nutzt die Standard-Zeile. Pro Zeile beide Zeiten oder keine; das Ende liegt nach dem Beginn. |
| Urlaubskalender | Optional. Ein Kalender in HA; jeder Tag, den ein Eintrag berührt, ist Urlaub (Standard-Zeile). |
| Schulferien | Optional. Eine Schule, ausgewählt über Bundesland → Landkreis → Ort → Schule bei mehr-schulferien.de. Ihre Ferien gelten als freie Tage. |

Im Alltag werden Personen über ihre Entities bedient: Raum wählen, Ausnahme setzen,
Licht/Radio pro Profil (Zeitplan, Standard, Ausnahme) und Radio-Favorit.

### Raum

| Feld | Bedeutung |
|---|---|
| Bereich | Optional ein HA-Bereich. Name, Lichter und Lautsprecher werden daraus vorgeschlagen. |
| Name | Bleibt er leer, wird der Name des Bereichs übernommen. |
| Personen zuordenbar | Ob der Raum in der Raum-Auswahl der Personen erscheint. Aus: Der Raum läuft nur über seinen Standardplan (z. B. Rollläden im Wohnzimmer). |
| Standardplan | Wie der Zeitplan einer Person; gilt, wenn keine Person im Raum ist. An Feiertagen gilt die Standard-Zeile. |
| Klemm-Fenster Tagesbeginn / Tagesende | Minuten, um die Tagesbeginn bzw. Tagesende höchstens an die Dämmerung angepasst werden (Standard 60, 0 = nie). |
| Lichter, Helligkeit, Licht nur bis Sonnenstand | Für das Wecken mit Licht (siehe unten). |
| Lautsprecher, Lautstärke | Für das Wecken mit Radio (siehe unten). |
| Licht/Radio-Dauer | Nach dieser Zeit schalten Licht und Radio wieder aus. |

Personen und Räume lassen sich jederzeit über *Ändern* anpassen. Reine Wertänderungen
(z. B. am Zeitplan) werden sofort neu gerechnet; ein neuer Name lädt HomeWake kurz neu.

## Licht und Radio beim Wecken

Wird ein Raum geweckt und hat die weckende Person für das gerade geltende Profil Licht bzw.
Radio eingeschaltet, schaltet HomeWake die Geräte des Raums:

- **Licht:** alle eingetragenen Lichter mit der eingestellten Helligkeit, aber nur, solange
  die Sonne nicht höher steht als „Licht nur bis Sonnenstand“.
- **Radio:** zuerst die Lautstärke, dann der Radio-Favorit der Person (sonst der
  Standard-Favorit des Raums, sonst der erste Favorit in der Liste des Lautsprechers), dann
  Abspielen. Steht ein gewählter Favorit nicht mehr in der Liste, meldet HomeWake das unter
  *Reparaturen*. Meldet der Lautsprecher noch gar keine Favoritenliste (z. B. kurz nach seinem
  Neustart), wartet HomeWake darauf wie auf ein nicht erreichbares Gerät. Kommt bis zum Ende
  der Versuche keine Liste, bleibt das Radio stumm, und unter *Reparaturen* erscheint der
  Hinweis „Lautsprecher ohne Favoritenliste“. Er verschwindet, sobald der Lautsprecher eine
  Liste meldet oder der Raum einen anderen Lautsprecher bekommt.
- **Ausschalten:** Nach der Licht/Radio-Dauer schaltet HomeWake aus, was noch so ist, wie es
  gesetzt wurde: ein Licht, das noch an ist, und ein Lautsprecher, der noch den Weck-Sender
  spielt. Was jemand inzwischen selbst geändert hat, bleibt. Das übersteht auch einen Neustart.
- **Home Assistant war zur Weckzeit aus:** Bis 15 Minuten nach der Weckzeit wird nachgeholt,
  danach nicht mehr.
- **Gerät nicht erreichbar:** Jedes Gerät wird für sich geschaltet, ein Fehler hält die anderen
  nicht auf. Ist ein Gerät nicht verfügbar oder antwortet es nicht (Zeitlimit 10 Sekunden),
  versucht HomeWake es alle 30 Sekunden und sofort, wenn es wieder da ist, bis 15 Minuten nach
  der Weckzeit (höchstens bis zum Ausschalten). Das Ausschalten wird ebenso bis 15 Minuten nach
  dem Aus-Zeitpunkt wiederholt. Im Log steht eine Warnung beim ersten Fehlschlag und eine,
  wenn HomeWake aufgibt.
- **Gerät fehlt:** Ist ein eingetragenes Licht oder ein Lautsprecher in Home Assistant gar nicht
  mehr vorhanden (gelöscht, umbenannt oder deaktiviert), meldet HomeWake das unter *Reparaturen*.
- **Wecken beenden:** Jeder Raum mit Lichtern oder Lautsprecher hat die Taste *Wecken beenden*.
  Ein Druck schaltet sofort aus, was beim Ausschalten nach der Dauer ausgeschaltet würde (nur,
  was noch so ist, wie HomeWake es gesetzt hat), und beendet laufende Versuche. Ohne laufendes
  Wecken passiert nichts; das nächste Wecken wird nicht übersprungen. In Automationen:
  Aktion `button.press` mit der Taste als Ziel.

## Dashboard-Karte

HomeWake bringt eine eigene, platzsparende Karte mit. Sie wird beim Start von HomeWake
automatisch angemeldet; ein Eintrag unter *Dashboard-Ressourcen* oder eine zweite Installation
ist nicht nötig.

**Hinzufügen:** Dashboard bearbeiten → *Karte hinzufügen* → **HomeWake**. Im Editor der Karte
lässt sich unter *Zuerst zeigen* die Person oder der Raum wählen, den die Karte beim Laden zeigt
(leer = die erste Person). In YAML:

```yaml
type: custom:homewake-card
objekt: Schlafzimmer   # optional: Name, Geräte-ID oder ID des Untereintrags
```

**Was sie zeigt:** oben eine Auswahl über alle Personen und Räume, daneben wach/schläft und ein
Zahnrad zur HomeWake-Seite (dort öffnet *Konfigurieren* den Zeitplan). Darunter **heute und
morgen** mit Wochentag, Datum, bei Personen dem Status (z. B. Werktag, Schulferien, Ausnahme),
Wecker bzw. Tagesbeginn und Tagesende; Vergangenes ist blass, der nächste Wecker fett. Ist die
Karte schmal (Handy, halbe Spalte), stehen die Tage untereinander. Ein Klick auf den Raum einer
Person bzw. eine Person im Raum springt dorthin.

**Was sie bedient:**

| Wo | Element | Aktion dahinter |
|---|---|---|
| ganz oben, solange ein Raum weckt | Balken „Raum · weckt bis …“ mit Knopf **Wecken beenden** | `button.press` auf die Taste des Raums |
| Person | Ausnahme an/aus und ihre Uhrzeit | `switch.turn_on`/`turn_off`, `time.set_value` |
| Person | Licht und Radio je Profil Zeitplan, Frei, Ausnahme | `switch.turn_on`/`turn_off` |
| Person | Raum (inkl. „kein Raum“) und Radio-Favorit | `select.select_option` |
| Raum | Standard-Favorit | `select.select_option` |

Die Karte nutzt nur diese Standard-Aktionen, dieselben, die auch Automationen nutzen. Sie rechnet
selbst nichts: Nach einer Änderung zeigt sie die von HomeWake neu berechneten Werte, also mit
kurzer Verzögerung. Die Uhrzeit wird erst gesendet, wenn das Feld verlassen oder Enter gedrückt
wird; ein geleertes Feld wird ignoriert (zurück zur Standardzeit: Ausnahme ausschalten). Scheitert
eine Aktion (z. B. eine Ausnahme nach dem Tagesende), zeigt die Karte die Meldung von Home
Assistant in einer roten Zeile; der Wert springt zurück. Zeitplan und Raum-Einstellungen werden
nicht in der Karte geändert, sondern über das Zahnrad.

**Grenzen:** Gleich benannte Personen oder Räume sind in der Auswahl nicht unterscheidbar. Nach
einem Update von HomeWake ohne Neustart von Home Assistant kann der Browser noch die alte Karte
zeigen (Seite neu laden). Die Karte wird auf jeder Seite von Home Assistant mitgeladen (ca. 36 KB).

## Entfernen

1. Optional: Automationen und Dashboards, die HomeWake-Entities nutzen, anpassen.
2. *Einstellungen → Geräte & Dienste → HomeWake → ⋮ → Löschen*. Home Assistant entfernt dabei
   alle Personen, Räume, Geräte und Entities sowie den gespeicherten Zustand von HomeWake.
3. Wer über den Marketplace bzw. HACS installiert hat, entfernt dort anschließend den
   Download; bei manueller Installation den Ordner `config/custom_components/homewake`
   löschen.
4. Home Assistant neu starten.

Eine einzelne Person oder einen Raum entfernst du unter *HomeWake → (Person/Raum) → ⋮ →
Löschen*. Personen in einem gelöschten Raum fallen auf „kein Raum“ zurück; HomeWake meldet
das unter *Reparaturen*.

## Fehlersuche

- Hinweise erscheinen unter *Einstellungen → Reparaturen* (z. B. Kalender nicht lesbar,
  Schulferien veraltet, Raum gelöscht, Gerät eines Raums nicht gefunden, Radio-Favorit nicht
  mehr in der Liste).
- Schaltet Licht oder Radio nicht, steht im Log, welches Gerät nicht erreichbar war.
- *HomeWake → ⋮ → Diagnose herunterladen* liefert den aktuellen Stand als Datei. Namen,
  Kalender, Schule, Bereich und Geräte sind darin unkenntlich gemacht, vom Urlaub stehen nur
  heute und morgen darin.

## Änderungen

Was sich pro Version geändert hat, steht in [CHANGELOG.md](CHANGELOG.md).

## Lizenz

HomeWake steht unter der [MIT-Lizenz](LICENSE). Schulferien kommen von
[mehr-schulferien.de](https://www.mehr-schulferien.de); deren Nutzungsbedingungen gelten
für die abgerufenen Daten.

<!-- ha-marketplace:exclude-start -->

## Projektaufbau

| Pfad | Inhalt |
|---|---|
| `custom_components/homewake/` | die Integration selbst, mit der gebauten Dashboard-Karte unter `frontend/` |
| `frontend/` | Quellcode der Dashboard-Karte (TypeScript, Lit) und ihre Tests (Vitest) |
| `tests/` | automatische Tests (pytest) |
| `docs/ARCHITEKTUR.md` | Architektur und Fachregeln (lebendes Dokument) |
| `CHANGELOG.md` | Änderungen pro Version |
| `scripts/dev.sh`, `scripts/dev.ps1` | Entwicklungsbefehle (Tests, Lint, Typprüfung) |
| `pyproject.toml`, `uv.lock` | Werkzeug-Konfiguration und exakt festgelegte Paketversionen |
| `.github/workflows/` | CI (Prüfungen), Validate (hassfest, HACS) und Release (ZIP bei Tag `vX.Y.Z`) |

## Entwicklung

Home Assistant läuft nur unter Linux, deshalb laufen Tests und Prüfungen in **WSL2**.
Der Code kann unter Windows liegen, die Python-Umgebung liegt im
Linux-Dateisystem (`~/.venvs/ha-homewake`), weil sie dort wesentlich schneller ist.

### Einmalig einrichten

1. In WSL `uv` nach `~/.local/bin` installieren (siehe <https://docs.astral.sh/uv/>).
2. Umgebung anlegen (installiert Home Assistant, pytest, ruff und mypy, dazu Node.js
   und die Pakete der Dashboard-Karte):

   ```powershell
   .\scripts\dev.ps1 setup
   ```

### Befehle

| Befehl | Was passiert |
|---|---|
| `.\scripts\dev.ps1 check` | alles prüfen: Karte bauen und prüfen, ruff, mypy, pytest (muss vor jedem Commit grün sein) |
| `.\scripts\dev.ps1 karte` | nur die Dashboard-Karte bauen und prüfen (Biome, tsc, Vitest) |
| `.\scripts\dev.ps1 test` | nur die Tests (weitere pytest-Argumente möglich, z. B. `-v`) |
| `.\scripts\dev.ps1 lint` | Stil und typische Fehler prüfen (ruff) |
| `.\scripts\dev.ps1 format` | Code automatisch formatieren und korrigieren (Python und Karte) |
| `.\scripts\dev.ps1 types` | Typprüfung (mypy, strict) |

Aus WSL heraus geht dasselbe mit `scripts/dev.sh <befehl>`.

### Home-Assistant-Version aktualisieren

Die HA-Version kommt über das Test-Paket `pytest-homeassistant` von Home Assistant
(ab HA 2026.11), das genau eine HA-Version festlegt. In `pyproject.toml` ist es auf eine
Version gepinnt (`pytest-homeassistant==2026.11.3`). Aktualisieren: dort die Version
erhöhen, dann

```bash
UV_PROJECT_ENVIRONMENT=~/.venvs/ha-homewake uv lock
scripts/dev.sh setup && scripts/dev.sh check
```

### Release

HomeWake wird in einem eigenen Entwicklungs-Repo gepflegt. Dieses Repository bekommt pro
Version genau einen Commit mit dem geprüften Stand (E88, E92):

1. Im Entwicklungs-Repo in `CHANGELOG.md` „[Unveröffentlicht]“ zur neuen Version mit Datum
   machen, Version in `custom_components/homewake/manifest.json` und `pyproject.toml` gleich
   setzen (z. B. `0.2.0`), `uv lock` ausführen, als `build: Version 0.2.0` committen, Tag
   `v0.2.0` setzen und beides pushen.
2. Das Export-Skript des Entwicklungs-Repos überträgt den Stand zum Tag hierher: ohne Verlauf
   und ohne interne Dateien, nach einer Prüfung auf private Daten und einem vollständigen
   `check`. Zuerst als Trockenlauf, dann mit einem Commit `build: Version 0.2.0` und dem Tag.
3. Der Workflow *Release* prüft hier, dass Tag und beide Versionen übereinstimmen, und legt
   einen GitHub-Release mit `homewake.zip` an (Inhalt von `custom_components/homewake`). HACS
   bzw. der Marketplace installiert dieses ZIP (`hacs.json`: `zip_release`).

<!-- ha-marketplace:exclude-end -->
