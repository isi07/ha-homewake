# HomeWake – Architektur

> **Lebendes Dokument.** Beschreibt den **aktuellen** Aufbau von HomeWake und seine Fachregeln.
> Bedienung und Einrichtung für Nutzer stehen in der [README](../README.md), Änderungen pro Version
> im [CHANGELOG](../CHANGELOG.md).
>
> Nummern wie „E12“ in diesem Dokument und im Code verweisen auf das interne
> Entscheidungsprotokoll der Entwicklung. Es ist nicht öffentlich; die hier beschriebenen Regeln
> gelten auch ohne es.

## 1. Zweck und Überblick

HomeWake ist ein Wecker für ein Haus mit mehreren Personen und Räumen in Home Assistant. Es
berechnet für jede Person die nächste Weckzeit (abhängig von Zeitplan, Ausnahme, Urlaub,
Schulferien, Feiertagen und Wochenende), fasst das pro Raum zusammen, schaltet zur Weckzeit Licht
und Radio und liefert pro Raum einen Tag/Nacht-Status, z. B. für eine Rollladen-Steuerung wie
Adaptive Cover Pro.

### 1.1 Drei Schichten

| Schicht | Aufgabe | Wo |
|---|---|---|
| 1 Personen | nächster Wecker, nächstes Tagesende, Status und Grund, Licht/Radio-Wunsch fürs nächste Wecken, wach | `logic/` (Person) |
| 2 Räume | fasst die Personen eines Raums zusammen (früheste Zeit gewinnt) oder nutzt den Standardplan; klemmt Tagesbeginn und Tagesende an die Dämmerung; wach und Tag | `logic/` (Raum) |
| 3 Aktorik | schaltet zur Weckzeit Licht und Radio, nach der Dauer wieder aus | `logic/aktorik.py` (Schaltplan), `schalten.py` (HA) |

Alle Schichten rechnen in **einem Lauf** mit demselben „jetzt“ (5.1). Die reine Fachlogik in
`logic/` kennt Home Assistant nicht; die HA-Schicht holt die Eingaben und schaltet die Geräte.

## 2. Begriffe

| Begriff | Bedeutung |
|---|---|
| **Haus** | der eine Haupteintrag von HomeWake; Land/Bundesland für Feiertage und der Sonnenstand gelten für alle (3.5) |
| **Person** | wird geweckt; hat einen Zeitplan, optional Schule und Urlaubskalender, und ist einem Raum zugeordnet (3.6) |
| **Raum** | fasst die Personen darin zusammen oder folgt seinem Standardplan; kann Licht und Radio schalten (3.7) |
| **Zeitplan, Zeile** | pro Wochentag höchstens ein Paar Tagesbeginn/Tagesende, dazu die Pflicht-Zeile **Standard** (3.4) |
| **Standardplan** | der Zeitplan eines Raums, gilt, wenn keine aktive Person den Raum bestimmt |
| **Weckzeit, Wecker** | Zeitpunkt, zu dem eine Person bzw. ein Raum geweckt wird |
| **Tagesbeginn, Tagesende** | Beginn und Ende des Tags einer Person bzw. eines Raums; beim Raum an die Dämmerung geklemmt |
| **Dawn, Dusk** | Zeitpunkt, an dem die Sonne morgens bzw. abends den gewählten Sonnenstand erreicht (3.5) |
| **Klemmung** | Tagesbeginn und Tagesende eines Raums werden innerhalb eines Fensters an Dawn/Dusk verschoben (4.6) |
| **Ausnahme** | einmalige Weckzeit einer Person mit höchster Priorität; wird nach dem Wecken gelöscht |
| **Inaktiv** | Person ohne Raum: Zeiten werden angezeigt, wirken aber auf keinen Raum (4.4) |
| **Status, Grund** | warum eine Zeit gilt (Ausnahme, Urlaub, Schulferien, Feiertag, Wochenende, Werktag, Inaktiv) und Einzelheit dazu (4.1) |
| **Wach, Tag** | Binärsensoren: Person/Raum ist zwischen Wecken und Tagesende; Raum ist zwischen geklemmtem Tagesbeginn und Tagesende |
| **Lauf** | eine Berechnung aller Personen und Räume mit demselben „jetzt“ (5.1) |
| **Sicherheitslauf** | Lauf alle 10 Minuten, unabhängig vom Timer (5.2) |
| **Aus-Auftrag** | gespeicherter Zeitpunkt, zu dem Licht und Radio eines Raums wieder ausgeschaltet werden (4.7) |
| **Hinweis** | Meldung unter *Einstellungen → Reparaturen* (5.5) |

## 3. Datenmodell

### 3.1 Haupteintrag und Untereinträge

HomeWake hat genau **einen Haupteintrag** (Config Entry, `single_config_entry`) für das Haus.
Personen und Räume werden darunter als **Untereinträge** (Config Subentries) angelegt, jeweils mit
eigenem Einrichtungsdialog. Jeder Untereintrag wird in HA ein **Gerät**, an dem seine Entities hängen.

```
HomeWake (Haupteintrag „Haus“)
├── Person: Person 1   → Gerät „Person 1“
├── Person: Person 2 …
├── Raum: Schlafzimmer → Gerät „Schlafzimmer“
└── Raum: Küche …
```

### 3.2 Ein Raumtyp: Räume mit und ohne Personen

HomeWake kennt **einen** Raumtyp (E4). Was ein Raum tut, ergibt sich aus seiner Konfiguration:

| Einstellung im Raum | Wirkung |
|---|---|
| **Personen zuordenbar** = ja | Der Raum erscheint in der Raum-Auswahl der Personen. Sind ihm aktive Personen zugeordnet, bestimmt die früheste Person die Raum-Zeiten. |
| **Personen zuordenbar** = nein, oder keine aktive Person zugeordnet | Der Raum läuft über seinen eigenen **Standardplan**. |
| **Aktorik** (Lichter, Lautsprecher) eingetragen | Der Raum schaltet zur Weckzeit Licht/Radio, aber nur, wenn die Weckzeit von einer Person kommt. Läuft der Raum über seinen Standardplan, schaltet er keine Aktorik. |
| keine Aktorik | Der Raum liefert nur Zeiten und „ist Tag“, z. B. für die Rollläden. |

### 3.3 Zwei Sorten Einstellungen

| Sorte | Wie oft geändert | Wo gepflegt | Wo gespeichert |
|---|---|---|---|
| **Konfiguration** | selten | Einrichtungs- bzw. „Konfigurieren“-Dialog des (Unter-)Eintrags | in den Daten des (Unter-)Eintrags (`data`), dadurch im HA-Backup |
| **Bedienung** | im Alltag | Entities, die **HomeWake selbst anlegt** (Schalter, Uhrzeit, Auswahl, Taste) | zentral im Coordinator, gesichert in einem HomeWake-eigenen Speicher (`helpers.storage.Store`); die Entities zeigen den Wert nur an und geben Änderungen weiter |

Leitziel: **HomeWake legt so viel wie möglich selbst an.** Es gibt keine `input_*`- oder
`schedule`-Helfer, die von Hand angelegt und verknüpft werden müssen.

Die Bedienwerte liegen zentral statt in jeder Entity einzeln, weil HomeWake beim Start erst
rechnen soll, wenn alle Werte da sind, und weil HomeWake selbst Werte ändern muss (Ausnahme
löschen, Raum auf „kein Raum“ setzen).

### 3.4 Der Zeitplan (Personen und Räume)

| Zeile | Tagesbeginn | Tagesende |
|---|---|---|
| Montag … Sonntag | optional | optional |
| **Standard** | Pflicht | Pflicht |

Prüfung beim Speichern: Pro Zeile sind entweder beide Zeiten gesetzt oder keine, und das Ende liegt
nach dem Beginn. Mehrere Bereiche pro Tag sind damit nicht eingebbar (E5).

Welche Zeile gilt (Personen, E6):

1. **Feiertag, Schulferien** (falls für die Person eine Schule eingetragen ist) **oder Urlaub** →
   immer **Standard**, auch wenn der Wochentag eine eigene Zeit hat.
2. Sonst: Hat der **Wochentag** eine Zeit, gilt sie, **auch am Samstag/Sonntag**.
3. Sonst: **Standard**.

Räume haben denselben Aufbau als **Standardplan** und dieselbe Regel (E13): **Feiertag** →
Standard, sonst Wochentag mit Zeit → diese, sonst Standard. Schulferien und Urlaub hängen an
Personen und spielen für den Standardplan eines Raums keine Rolle.

**Pflege:** im „Konfigurieren“-Dialog der Person bzw. des Raums. Ändert sich nur der Zeitplan,
wird nur neu gerechnet, nicht der ganze Eintrag neu geladen.

### 3.5 Haus (Haupteintrag)

| Konfiguration | Zweck |
|---|---|
| Land, Bundesland (ggf. weitere Region) | **Feiertage**, gelten für alle Personen. Berechnet offline mit der Python-Bibliothek `holidays` (dieselbe, die HAs `workday`/`holiday` nutzen), inkl. Name des Feiertags (E9). |
| Sonnenstand morgens / abends | Für die Klemmung (4.6). HomeWake berechnet Dawn/Dusk selbst aus dem HA-Standort (E30), getrennt wählbar für morgens und abends: Astronomische Dämmerung −18°, Nautische −12°, **Bürgerliche −6° (Standard)**, Blaue Stunde Ende/Goldene Stunde Beginn −4°, Sonnenaufgang/-untergang (oberer Sonnenrand am Horizont, scheinbar −0,27°), Horizont 0°, Goldene Stunde Ende +6°, oder frei wählbare Gradzahl (−18° bis +10°; Feld erscheint nur bei dieser Wahl). |

Wochenende (Samstag, Sonntag) gilt für alle gleich.

### 3.6 Person

**Konfiguration**

| Feld | Pflicht | Bemerkung |
|---|---|---|
| Name | ja | wird Gerätename |
| Zeitplan | ja (Standard-Zeile) | siehe 3.4 |
| Schule (Schulferien) | nein | leer = Schulferien gelten nicht. HomeWake ruft die Ferien dieser Schule selbst ab (E10). Auswahl über einen Anbieter (vorerst nur mehr-schulferien.de) und dessen Schritte, dort Bundesland → Landkreis → Ort → Schule (E40, E44); Abruf täglich, ein Jahr Vorrat im Speicher (E41) |
| Urlaubskalender | nein | ein Kalender in HA (z. B. ein lokaler Kalender); HomeWake liest nur die Termine. Ein Tag ist Urlaub, wenn ein Eintrag ihn berührt (E38). Neue oder geänderte Termine wirken spätestens nach dem nächsten Sicherheitslauf (10 min), meist sofort, weil HomeWake neu liest, sobald der Kalender seinen Zustand ändert (E45) |

**Bedienung** (Entities, von HomeWake angelegt)

| Entity | Typ | Inhalt |
|---|---|---|
| Raum | `select` | nur Räume mit „Personen zuordenbar = ja“, plus „kein Raum“. Intern wird die ID des Raums gespeichert, nicht der Name; Attribut `raum_id` (E11, E70). |
| Ausnahme aktiv | `switch` | gilt einmal, wird nach dem Wecken gelöscht |
| Ausnahme-Weckzeit | `time` | ohne eigene Uhrzeit der Beginn der Standard-Zeile; nach der Ausnahme zurück darauf (E63, E71) |
| Zeitplan-Licht, Zeitplan-Radio | `switch` | gilt, wenn die eigene Zeit des Wochentags gilt |
| Standard-Licht, Standard-Radio | `switch` | gilt, wenn die Standard-Zeile gilt |
| Ausnahme-Licht, Ausnahme-Radio | `switch` | gilt, wenn eine Ausnahme aktiv ist |
| Radio-Favorit | `select` | „kein Favorit“ oder eine Quelle/ein Favorit des Lautsprechers im Raum der Person; die Auswahl passt sich Raum und Favoritenliste an (E33) |

**Ausgabe** (Sensoren)

| Entity | Typ | Inhalt |
|---|---|---|
| Nächster Wecker | `sensor` (timestamp) | |
| Nächstes Tagesende | `sensor` (timestamp) | |
| Status | `sensor` (enum) | Ausnahme, Urlaub, Schulferien, Feiertag, Wochenende, Werktag, Inaktiv. Attribute: Grund (Wochentag bzw. `kein_raum` als übersetzter Schlüssel, Feiertags- und Ferienname als Text, E48), Licht/Radio fürs nächste Wecken, Kandidat heute/morgen, Tagesbeginn und Tagesende heute und morgen (E16; Tagesbeginn inkl. Ausnahme, heute nach dem Wecken der tatsächliche Weckzeitpunkt). Status und Grund je Tag: `status_heute`, `grund_heute`, `status_morgen`, `grund_morgen` (E70). Mit Schule zusätzlich `schule` (vollständiger Auswahlweg mit Schule, E44), `schulferien` (geladene heutige und künftige Ferien mit Name, Beginn, Ende) und `schulferien_stand` (letzter erfolgreicher Abruf); diese drei werden nicht im Verlauf aufgezeichnet |
| Wach | `binary_sensor` | |

### 3.7 Raum

**Konfiguration**

| Feld | Pflicht | Default |
|---|---|---|
| HA-Bereich | nein | Vorschlag für Name, Lichter und Lautsprecher (E35); jeder Bereich nur ein Raum |
| Name | ja | bleibt er leer, wird der Bereichsname übernommen; „kein_raum“ ist reserviert |
| Standardplan | ja (Standard-Zeile) | siehe 3.4 |
| Personen zuordenbar | ja | |
| Klemm-Fenster Tagesbeginn / Tagesende (Minuten) | ja | 60 / 60 |
| Lichter | nein | |
| Licht-Helligkeit (%) | – | 100 |
| Licht-Elevations-Schwelle (°) | – | -3 |
| Licht/Radio-Dauer (Minuten) | – | 45 |
| Lautsprecher | nein | |
| Lautstärke (%) | – | 30 |

Licht- und Lautsprecher-Felder erscheinen im Dialog nur, wenn Lichter bzw. ein Lautsprecher gewählt
sind (bedingte Felder, HA 2026.11).

**Bedienung**

| Entity | Typ | Inhalt |
|---|---|---|
| Standard-Favorit | `select` | „kein Favorit“ oder eine Quelle/ein Favorit des Lautsprechers; nur bei Raum mit Lautsprecher (E33) |
| Wecken beenden | `button` | nur bei Raum mit Lichtern oder Lautsprecher; schaltet sofort aus, was nach der Dauer ausgeschaltet würde, und beendet laufende Versuche (E53, E60) |

**Ausgabe**

| Entity | Typ | Inhalt |
|---|---|---|
| Weckzeit | `sensor` (timestamp) | heute, roh, Basis für die Dawn-Klemmung. Attribute: Personen (live), Weckende, Licht, Radio, Favorit, Quelle (Personen/Standardplan); alle außer Personen frieren mit der Weckzeit ein (E47) |
| Tagesbeginn | `sensor` (timestamp) | heute, an Dawn geklemmt |
| Tagesende | `sensor` (timestamp) | heute, an Dusk geklemmt |
| Weckzeit morgen | `sensor` (timestamp) | morgen, roh (E22) |
| Tagesbeginn morgen | `sensor` (timestamp) | morgen, an Dawn von morgen geklemmt (E22) |
| Tagesende morgen | `sensor` (timestamp) | morgen, an Dusk von morgen geklemmt (E22) |
| Wach | `binary_sensor` | Attribut `wecken_bis`: Aus-Zeitpunkt, solange ein Wecken läuft (E64) |
| Tag | `binary_sensor` | z. B. für Adaptive Cover Pro |

Die Sensoren für heute zeigen immer den heutigen Tag und frieren nach Erreichen bis Mitternacht
ein (4.5, E21). Zusammengefasst wird pro Tag (E22): früheste Person gewinnt, frühestes Tagesende
gilt; ohne Personen der Standardplan. Der Aus-Zeitpunkt für Licht/Radio läuft intern statt als
`timer`-Entity und wird gespeichert, damit er einen HA-Neustart übersteht (E12).

### 3.8 Namen und IDs

- **Anzeigename = Gerätename + Entity-Name.** Jede Person und jeder Raum ist ein Gerät (Name =
  Titel des Untereintrags). Die Entities setzen `_attr_has_entity_name = True` und einen
  `translation_key`, aber keinen eigenen Namen. Der Entity-Name kommt aus den Übersetzungen
  (deutsch mit Umlauten, englisch). Ergebnis z. B. „Person 1 Nächster Wecker“.
- **Entity-ID** wird von HA beim ersten Anlegen erzeugt, aus den Teilen Bereich + übergeordnetes
  Gerät + Gerät + Entity-Name (Standard, in den HA-Einstellungen änderbar). Bei deutscher
  HA-Sprache aus den deutschen Namen, Umlaute als einzelner Buchstabe, z. B.
  `sensor.person_1_nachster_wecker`, `binary_sensor.schlafzimmer_tag`. HomeWake gibt keine eigene
  `object_id` vor und ordnet Raum-Geräte keinem HA-Bereich zu (E36).
- Bestehende Entity-IDs ändern sich nicht von selbst. Umbenennen in der UI (Gerät oder Entity) ist
  jederzeit möglich; HA erledigt das ohne Entfernen und Neuanlegen.
- **`unique_id` = `<Untereintrags-ID>_<Schlüssel>`**, z. B. `01J…_naechster_wecker`. Sie ändert
  sich nie, auch nicht beim Umbenennen.
- Geräte werden über `DeviceInfo` angelegt, Typ „Dienst“.

## 4. Regeln

### 4.1 Die Prioritätskette bei Personen

```
1. Ausnahme (manuell gesetzt)         → höchste Priorität
2. Urlaub (Kalender)
3. Schulferien
4. Feiertag
5. Wochenende (Sa/So)
6. Werktag                            → Standardfall
```

Nur die **erste zutreffende** Bedingung gewinnt. Dazu kommt der Sonderfall `Inaktiv` (4.4).
**Status-Grund:** Wochentag bzw. „kein Raum“ als übersetzter Schlüssel (`samstag`, `kein_raum`),
Feiertags- und Ferienname als Text (E48); bei Ausnahme und Urlaub kein Grund.

Welche Zeit und welches Licht/Radio daraus folgt (E6, E7):

| Status | Weckzeit | Tagesende | Licht/Radio |
|---|---|---|---|
| Ausnahme | Ausnahme-Weckzeit | aus der Zeile, die ohne Ausnahme gälte | Ausnahme-Licht/Radio |
| Urlaub, Schulferien, Feiertag | Standard | Standard | Standard-Licht/Radio |
| Wochenende, Werktag | Wochentag, falls gepflegt, sonst Standard | ebenso | Zeitplan-Licht/Radio, falls die Wochentags-Zeit gilt, sonst Standard-Licht/Radio |

Feiertage gelten für alle Personen (Haus), Schulferien nur für Personen mit eingetragener Schule,
Urlaub nur für Personen mit Urlaubskalender.

### 4.2 Datum und Uhrzeit immer gemeinsam

Für „heute“ und „morgen“ wird **je ein vollständiger Kandidat** (Datum und Uhrzeit zusammen, aus
der jeweils geltenden Zeile) gebildet, und erst dann geprüft, welcher gilt. Datum und Uhrzeit aus
verschiedenen Tagen zu kombinieren ist eine typische Fehlerklasse von Weckern (in Tests
„Datums-Bug“ genannt); sie ist damit strukturell ausgeschlossen.

### 4.3 Personen-Zustand und Wecken (E14–E20)

HomeWake rechnet bei jedem Lauf aus **Eingaben** (Zeitplan, Ausnahme, Feiertag/Ferien/Urlaub,
Raum), **„jetzt“** und dem **gespeicherten Zustand** das Ergebnis und einen neuen Zustand. Der
Zustand ist klein: wach ja/nein, zuletzt angekündigter Wecker, war das die Ausnahme, geweckt um.

1. **Wecken:** Ist die Person nicht wach und der *angekündigte* Wecker erreicht (≤ jetzt), wird sie
   wach. Maßgeblich ist der zuvor ausgegebene Wecker, nicht ein inzwischen neu berechneter. War es
   die Ausnahme, wird sie gelöscht.
2. **Tagesende:** Ist die Person wach und das Tagesende ihres Weck-Tags erreicht, ist sie nicht mehr
   wach. Das Tagesende kommt aus der Zeile, die ohne Ausnahme gälte (4.1); Änderungen am Zeitplan
   wirken, bis es erreicht ist.
3. **Heute verbraucht:** Wurde heute schon geweckt, gibt es heute keinen zweiten Wecker.
4. **Nächster Wecker:** heute, wenn noch nicht verbraucht und noch in der Zukunft (> jetzt), sonst
   morgen. Keine Toleranz: Wecken nutzt ≤, die Auswahl nutzt >; ob heute schon geweckt wurde, steht
   im Zustand und wird nicht aus der Uhrzeit geraten.
5. **Ausnahme:** zählt nur mit Uhrzeit und vor dem Tagesende ihres Tags (E18). Ist die Uhrzeit heute
   schon vorbei, bleibt der heutige Plan-Wecker, und die Ausnahme gilt morgen (E17).
6. **Sollzustand (E15):** Beim ersten Start oder nach längerem Ausfall wird der Zustand direkt aus
   Zeitplan und Uhrzeit bestimmt. Wecken und Tagesende können im selben Lauf beide greifen.
7. **Verpasstes Wecken (E20):** Das Ergebnis meldet „gerade geweckt“ und den eigentlichen
   Weckzeitpunkt. Licht/Radio schalten höchstens 15 Minuten danach noch (E28).

### 4.4 Inaktiv

Weil die Standard-Zeile Pflicht ist, hat jede Person immer eine Zeit. „Inaktiv“ bedeutet: **Die
Person ist keinem Raum zugeordnet** (E8). Einen eigenen Schalter gibt es nicht.

- Die Zeiten werden trotzdem berechnet und angezeigt (z. B. um einen Gast vorab zu prüfen).
  Status `Inaktiv`, Grund „kein Raum“. Auf Räume wirkt die Person nicht.
- Wird die Person inaktiv, wird eine bestehende Ausnahme **gelöscht**. Solange sie inaktiv ist,
  lässt sich keine Ausnahme einschalten (Ablehnung mit Hinweis).
- `Wach` schaltet auch bei inaktiven Personen normal (E19).

### 4.5 Eingefroren bis Mitternacht (Räume)

Weckzeit, Tagesbeginn, Tagesende und Licht/Radio/Favorit, Quelle und weckende Personen (E47)
frieren nach Erreichen bis Mitternacht ein, damit man den ganzen Tag sieht, wann der Tag begann
und endete (E21, E22). Umgesetzt mit einem kleinen Raum-Zustand: die eingefrorenen Werte von heute
und die Ankündigung des nächsten Weckens. Ein neues Datum verwirft die eingefrorenen Werte;
HomeWake rechnet um Mitternacht neu. Geweckt wird mit den *angekündigten* Werten (wie bei
Personen, E14). „Wach“ gilt von der Weckzeit bis vor das geklemmte Tagesende, „Tag“ vom
geklemmten Tagesbeginn bis vor das geklemmte Tagesende (E26).

### 4.6 Dawn/Dusk-Klemmung

Tagesbeginn (morgens, Dawn) und Tagesende (abends, Dusk) werden an den gewählten Sonnenstand
geklemmt (3.5, Standard −6°), mit **pro Raum einstellbarem** Fenster in Minuten (3.7). Gerechnet
wird in echten Zeitpunkten, damit die Zeitumstellung stimmt; Dawn/Dusk immer für ein bestimmtes
Datum (heute bzw. morgen). HomeWake berechnet Dawn/Dusk selbst aus dem HA-Standort (Bibliothek
astral, E30). Gradzahlen sind die scheinbare Höhe der Sonnenmitte. Fehlt Dawn oder Dusk (z. B.
Polarnacht), wird nicht geklemmt (E25).

**Morgen** (Fenster nach der Weckzeit):
```
Dawn <= Weckzeit                      → Tagesbeginn = Weckzeit (schon hell)
Weckzeit < Dawn <= Weckzeit+Fenster   → Tagesbeginn = Dawn
Dawn > Weckzeit+Fenster               → Tagesbeginn = Weckzeit+Fenster (gedeckelt)
```

**Abend** (Fenster vor dem Tagesende, spiegelbildlich):
```
Dusk <= Tagesende−Fenster             → Tagesende = Tagesende−Fenster (früh dunkel)
Tagesende−Fenster < Dusk <= Tagesende → Tagesende = Dusk
Dusk > Tagesende                      → Tagesende bleibt (noch hell, nie später)
```

Bei Fenster 0 ergibt die Formel immer den unveränderten Zeitplan-Wert. Weil der Raum pro Tag
zusammenfasst und die heutigen Werte einfriert (4.5), ändert sich der heutige Tagesbeginn nicht,
wenn eine Person auf morgen rollt.

**Allgemeine Lehre (Fehlerklasse):** Jede Größe, die aus einer *Zusammenfassung über mehrere
Quellen* abgeleitet wird, kann sich ändern, ohne dass sich ihr Datum ändert, sobald eine Quelle
„verbraucht“ ist und rollt. Abgeleitete, noch wartende Werte deshalb an den **eingefrorenen
Ausgabewert** koppeln, nicht an das frisch neu berechnete Ergebnis.

### 4.7 Licht und Radio beim Wecken

Die Entscheidung steckt als reine Logik in `logic/aktorik.py` (Schaltplan aus Raum-Wecken, „jetzt“
und Sonnenhöhe, E51), geschaltet wird in `schalten.py`, jedes Gerät für sich mit erneutem Versuch
(E52, E55).

- **Licht:** alle Lichter des Raums mit der eingestellten Helligkeit, solange die Sonne nicht
  höher steht als die Licht-Schwelle.
- **Radio:** strikte Reihenfolge **Lautstärke → Quelle → Play**. Quelle ist der Favorit der Person,
  sonst der Standard-Favorit des Raums, sonst der erste Eintrag der Favoritenliste (E56); ein
  fehlender gewählter Favorit erzeugt einen Hinweis. Die Quelle wird beim Versuch aus der dann
  aktuellen `source_list` gewählt; ohne Liste wird gewartet (E55).
- **Nicht erreichbar:** Versuche alle 30 s und sofort beim Wiederkommen, bis 15 min nach der
  Weckzeit (höchstens bis zum Ausschalten); Zeitlimit 10 s pro Befehl (E55).
- **Ausschalten** nach der Licht/Radio-Dauer: nur, was noch so ist, wie HomeWake es gesetzt hat
  (E50, E54); der Aus-Auftrag steht im Speicher beim Raum und übersteht einen Neustart (E12).
- **Wecken beenden** (Taste pro Raum) schaltet sofort nach denselben Regeln aus (E60).

## 5. HA-Schicht

Wie die reine Fachlogik (`logic/`) mit Home Assistant verbunden wird (E29–E34).

### 5.1 Ablauf eines Laufs

1. Der **Coordinator** (`DataUpdateCoordinator` ohne eigenes Intervall) holt die Eingaben aus HA:
   Konfiguration der (Unter-)Einträge, Bedienwerte und Zustände aus dem Speicher, Feiertage,
   Urlaub, Schulferien, Dawn/Dusk, „jetzt“ (`dt_util.now()`) und die HA-Zeitzone.
   Feiertage, Urlaub und Schulferien liegen dabei schon vor: Hintergrund-Aufgaben laden sie und
   stoßen danach einen Lauf an. Ein Lauf enthält **kein `await`** und wartet nie auf Kalender,
   Bibliothek oder Netz (E45).
2. Er ruft die reine Funktion `berechne_haus` auf (E31): erst alle Personen, dann alle Räume, mit
   demselben „jetzt“. Ergebnis: alle Personen- und Raum-Ergebnisse, neue Zustände, ggf. zu löschende
   Ausnahmen und die kleinste „nächste Änderung“.
3. Er speichert die neuen Zustände (nach Wecken oder Ausnahme-Löschen sofort als eigene Aufgabe,
   sonst verzögert um 1 s; beides ohne Warten im Lauf) und stellt den Timer neu.
4. Meldet ein Raum „gerade geweckt“, rechnet er den Schaltplan und ruft `schalten.py` auf (4.7).

### 5.2 Wann gerechnet wird

- beim Start und nach jedem Neuladen,
- zur **„nächsten Änderung“** über einen genauen Timer (`async_track_point_in_utc_time`; HAs
  eingebautes Intervall rundet und taugt nicht als Wecker),
- bei Änderungen von außen (Bedienelemente, Konfiguration, HA-Zeitzone/Standort),
- im **Sicherheitslauf** alle 10 Minuten zur Minute :09, :19, … :59 (E29),
- nach jedem fertigen Hintergrund-Abruf (Urlaub, nachgeladene Feiertage, Schulferien; E41, E45).

Gelesen werden die Urlaubskalender beim Start, im Sicherheitslauf, um 00:00, bei geändertem
Kalender einer Person und bei jeder Zustandsänderung einer Kalender-Entity (E45). Timer,
Sicherheitslauf, Mitternachts-Anlass und Kalender-Beobachtung werden beim Entladen abgemeldet,
laufende Abrufe abgebrochen.

### 5.3 Speicher

Ein `Store` pro HomeWake-Eintrag (`homewake.<entry_id>`, Version 1) mit pro Person Bedienwerten,
zuletzt gelesenem Urlaub pro Tag (E38) und Zustand, pro Raum Zustand und Aus-Auftrag, pro Schule
die geladenen Schulferien mit Zeitpunkt des letzten erfolgreichen Abrufs (E41). Zeitpunkte als
ISO-Text mit Zeitzonen-Offset. Ein unlesbarer oder fehlender Eintrag wird zum Leerzustand; der
Sollzustand (E15, E23) heilt das. Spätere Formatänderungen laufen über eine Migration. Wird
HomeWake gelöscht, wird auch die Datei entfernt (`async_remove_entry`).

### 5.4 Untereinträge, Geräte und Aufräumen

- Personen und Räume sind Untereinträge; jeder wird ein Gerät (Typ „Dienst“), Entities werden mit
  `config_subentry_id` angelegt.
- Der Zeitplan steht im `data` des Untereintrags in Dialogform
  (`{"standard": {"beginn": "06:30:00", "ende": "22:00:00"}, "montag": {...}, "dienstag": {}}`).
- **Entfernen einer Person/eines Raums:** HA entfernt Gerät und Entities dieses Untereintrags
  selbst. HomeWake lädt neu, entfernt verwaiste Einträge aus seinem Speicher und setzt Personen
  eines entfernten Raums auf „kein Raum“ (Hinweis, 5.5). Ein laufender Aus-Auftrag eines
  gelöschten Raums läuft weiter.
- **Wegfallende Entities innerhalb eines Untereintrags** (z. B. Lautsprecher entfernt → keine
  Favoriten-Auswahl mehr): HomeWake vergleicht beim Einrichten die Registry mit den tatsächlich
  angelegten Entities und entfernt übrige Einträge selbst.
- Neue oder umbenannte Untereinträge laden die Integration neu (Entities kurz „nicht
  verfügbar“, Zustand bleibt). Reine Wertänderungen rechnen nur neu.

### 5.5 Hinweise unter „Reparaturen“

| Anlass | Folge |
|---|---|
| Raum einer Person wird gelöscht oder auf „nicht zuordenbar“ gestellt (E11) | Person fällt auf „kein Raum“ zurück (inaktiv, Ausnahme gelöscht). Hinweis pro Person; verschwindet, sobald sie wieder einen Raum hat, in der Raum-Auswahl bewusst „kein Raum“ gewählt wird oder die Person gelöscht wird (bleibt über Neustarts, ein „Ignorieren“ ebenso). |
| Schulferien-Daten einer Schule zu alt (E42): 3 Tage kein erfolgreicher Abruf, oder keine Daten und Abruf scheitert seit 30 Minuten | Hinweis pro Schule; bis dahin und danach gelten die zuletzt geladenen Daten (ohne Daten keine Schulferien). Verschwindet nach dem nächsten erfolgreichen Abruf oder wenn keine Person die Schule mehr hat |
| Zeitplan einer Person oder eines Raums nicht lesbar (beschädigte Daten, E46) | Hinweis pro Untereintrag; die Person bzw. der Raum ist nicht verfügbar, Personen eines solchen Raums behalten ihn. Eine Person mit kaputtem Zeitplan wird gar nicht gerechnet, ihr Raum wird also auch erst nach der Reparatur geprüft. Verschwindet, sobald der Zeitplan wieder gilt oder der Untereintrag gelöscht wird; über Neustarts bleibt derselbe Hinweis (ein „Ignorieren“ hält). |
| Urlaubskalender einer Person länger als 30 Minuten nicht lesbar (E39) | Hinweis pro Person mit Kalendername; bis dahin und danach gilt der zuletzt gelesene Urlaub (höchstens heute und morgen, E38). Verschwindet, sobald der Kalender wieder lesbar ist, aus der Person entfernt oder die Person gelöscht wird. |
| Gerät eines Raums (Licht, Lautsprecher) fehlt in HA oder ist deaktiviert (E55) | Hinweis pro Raum; wird in jedem Lauf geprüft und verschwindet also bis zu 10 min nach dem Wiederkommen des Geräts |
| Gewählter Radio-Favorit steht nicht mehr in der Liste des Lautsprechers (E56) | Hinweis; gespielt wird der nächste passende Favorit (4.7) |
| Lautsprecher eines Raums meldet beim Wecken bis zum Ende der Versuche keine Favoritenliste, das Radio bleibt stumm (E58, E61) | Hinweis pro Raum mit dem Lautsprecher; verschwindet, sobald der Lautsprecher eine Liste meldet, der Raum einen anderen oder keinen Lautsprecher hat oder gelöscht wird. Ist der Lautsprecher gerade nicht verfügbar, bleibt der Hinweis. |

### 5.6 Dashboard-Karte

Eigene Karte `custom:homewake-card` (E59, E62–E80): Quellcode in `frontend/` (TypeScript, Lit),
gebaut nach `custom_components/homewake/frontend/homewake-card.js` und von HomeWake beim Start
selbst angemeldet (E66–E69). Sie zeigt eine Person oder einen Raum mit heute/morgen und bedient
nur über Standard-Aktionen (`switch`, `time`, `select`, `button`); sie rechnet selbst nichts.
Einzelheiten zur Bedienung stehen in der README.

### 5.7 Diagnose

*HomeWake → ⋮ → Diagnose herunterladen* (`diagnostics.py`, E49): Eintrag und Untereinträge,
Speicher, letztes Ergebnis, ob der letzte Lauf geklappt hat und der Timer steht, geladene und
gescheiterte Feiertagsjahre, Kalender-Ausfälle, Schul-Abrufe, Schalt-Aufträge und gemeldete
Hinweise. Geschwärzt werden Namen von Personen und Räumen, Urlaubskalender, Schule, HA-Bereich,
Lichter und Lautsprecher; vom Urlaub stehen nur heute und morgen darin (E49).

## 6. Bekannte Grenzen und offene Punkte

**Maßstab für die Aktorik** (Schwere der Fehler, absteigend): **gar nicht geweckt** > zur falschen
Zeit geweckt (z. B. im Urlaub zur Werktagszeit) > Rollläden zur falschen Zeit > doppelt geschaltet.
Im Zweifel lieber doppelt schalten als gar nicht wecken.

Bekannte Grenzen (bewusst so, kein Fehler):

- **Aktorik:** Ein Gerät kommt schon mit dem ersten Schaltbefehl in den Aus-Auftrag; scheiterte der
  Befehl, schaltet HomeWake es nach der Dauer trotzdem aus, falls es dann an ist (E50, E54). Ein
  Licht, das immer `unknown` meldet, wird nach jedem Wecken ausgeschaltet (E54). Ein Gerät, dessen
  Einschaltversuch ins Zeitlimit lief, wird nach der Dauer bzw. beim Tastendruck ohne Blick auf den
  Zustand ausgeschaltet. Versuche werden nach einem Neustart nicht fortgesetzt (E57).
- **Lautsprecher ohne Favoritenliste** (kein `select_source`) warten bei jedem Wecken 15 min
  vergeblich und bekommen nicht einmal die Lautstärke (E55); danach erscheint der Hinweis
  „Lautsprecher ohne Favoritenliste“ (5.5).
- **Wecken beenden** überspringt kein künftiges Wecken. Das Ausschalten eines nicht erreichbaren
  Geräts kann nach dem Druck bis 15 min weiterlaufen; ein neues Wecken in dieser Zeit bricht es ab.
- **Speichern nach dem Wecken:** Fällt HA genau zwischen Wecken und Speichern aus, kann nach dem
  Neustart innerhalb der 15 Minuten (E28) noch einmal geschaltet werden (Folgen gering).
- **Status nach der Ausnahme:** Nach dem Wecken durch die Ausnahme zeigt `status_heute` wieder den
  Plan-Status (E70). Ändert sich die Standard-Zeile bei aktiver Ausnahme ohne eigene Uhrzeit,
  wandert die Ausnahme still mit; liegt der neue Beginn ab dem Tagesende ihres Tags, zählt sie
  nicht (E18), ohne Meldung.
- **Karte:** prüft nicht, ob Karte und HomeWake-Version zueinander passen (alte Karte im
  Browser-Zwischenspeicher nach einem Update ohne Neustart). Nicht verfügbare Personen/Räume zeigen
  nur „nicht verfügbar“. Gleich benannte Personen/Räume sind in der Auswahl nicht unterscheidbar.
  Das Zahnrad springt nur zur HomeWake-Seite. Die Karte lädt auf jeder HA-Seite (E69). Zurück zur
  Standardzeit der Ausnahme nur über „Ausnahme aus“ (E77). Fehlermeldungen kommen in der
  Server-Sprache von HA (E76), die Fehlerzeile gilt für die ganze Karte. In sehr schmalen Karten
  wird der Name stark gekürzt. Native Auswahllisten sehen je nach Browser anders aus (E74).

Offen:

- Lautsprecher ohne Favoritenliste schon im Einrichtungsdialog ausfiltern?
- Ein Feld „geweckt durch Ausnahme“ im Personen-Zustand, falls `status_heute` das zeigen soll.
- Bedienung der Karte mit einem echten Screenreader prüfen (bisher nur in den Karten-Tests).
- **Quality Scale Gold** (`quality_scale.yaml`): Doku-Regeln (Datenaktualisierung, Beispiele,
  Grenzen, Funktionen, Fehlersuche, Anwendungsfälle), `entity-category`,
  `entity-disabled-by-default` (z. B. Morgen-Sensoren der Räume), `icon-translations`.
