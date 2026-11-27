// Eigene Texte der Karte, deutsch und englisch nach HA-Sprache (E72).
// Zustände und Status-Gründe kommen aus den HA-Übersetzungen von HomeWake.

const DE = {
  wach: "wach",
  schlaeft: "schläft",
  tag: "Tag",
  nacht: "Nacht",
  heute: "Heute",
  morgen: "Morgen",
  wecker: "Wecker",
  beginn: "Tagesbeginn",
  ende: "Tagesende",
  raum: "Raum",
  ausnahme: "Ausnahme",
  an: "an",
  aus: "aus",
  licht: "Licht",
  radio: "Radio",
  zeitplan: "Zeitplan",
  standard: "Frei",
  favorit: "Radio-Favorit",
  standard_favorit: "Standard-Favorit",
  quelle: "Quelle",
  personen: "Personen",
  niemand: "niemand",
  weckt_bis: "weckt bis",
  einstellungen: "Einstellungen in Home Assistant",
  auswahl: "Person oder Raum",
  leer: "Keine Personen oder Räume von HomeWake gefunden.",
  nicht_verfuegbar: "nicht verfügbar",
  wecken_beenden: "Wecken beenden",
  zum_raum: "Zum Raum",
  ausnahme_zeit: "Uhrzeit der Ausnahme",
  fehler: "Aktion fehlgeschlagen",
  schliessen: "Schließen",
  editor_objekt: "Zuerst zeigen",
  editor_objekt_hilfe:
    "Person oder Raum, den die Karte beim Laden zeigt; leer = die erste Person",
};

export type TextSchluessel = keyof typeof DE;

const EN: Record<TextSchluessel, string> = {
  wach: "awake",
  schlaeft: "asleep",
  tag: "Day",
  nacht: "Night",
  heute: "Today",
  morgen: "Tomorrow",
  wecker: "Alarm",
  beginn: "Start of day",
  ende: "End of day",
  raum: "Room",
  ausnahme: "Exception",
  an: "on",
  aus: "off",
  licht: "Light",
  radio: "Radio",
  zeitplan: "Schedule",
  standard: "Day off",
  favorit: "Radio favorite",
  standard_favorit: "Default favorite",
  quelle: "Source",
  personen: "Persons",
  niemand: "nobody",
  weckt_bis: "waking until",
  einstellungen: "Settings in Home Assistant",
  auswahl: "Person or room",
  leer: "No HomeWake persons or rooms found.",
  nicht_verfuegbar: "unavailable",
  wecken_beenden: "Stop alarm",
  zum_raum: "Go to room",
  ausnahme_zeit: "Exception time",
  fehler: "Action failed",
  schliessen: "Close",
  editor_objekt: "Show first",
  editor_objekt_hilfe:
    "Person or room shown when the card loads; empty = the first person",
};

const SPRACHEN: Record<string, Record<TextSchluessel, string>> = { de: DE, en: EN };

/** Texte für eine HA-Sprache wie „de“ oder „de-AT“; sonst Englisch. */
export function texte(sprache: string): Record<TextSchluessel, string> {
  return SPRACHEN[sprache.split("-")[0] ?? ""] ?? EN;
}

/** Uhrzeit „07:00“ in der HA-Zeitzone. */
export function uhrzeit(zeit: Date, sprache: string, zeitzone: string): string {
  return new Intl.DateTimeFormat(sprache, {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: zeitzone,
  }).format(zeit);
}

/** Wochentag und Datum, z. B. „Dienstag, 14.07.“, in der HA-Zeitzone. */
export function datum(zeit: Date, sprache: string, zeitzone: string): string {
  return new Intl.DateTimeFormat(sprache, {
    weekday: "long",
    day: "2-digit",
    month: "2-digit",
    timeZone: zeitzone,
  }).format(zeit);
}
