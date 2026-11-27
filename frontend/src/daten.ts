// Datenaufbereitung der Karte (E62, E70): aus `hass` die Ansicht einer Person
// bzw. eines Raums bauen. Kein Lit, kein DOM; wie `logic/` in Python ohne
// Anzeige testbar. Die Karte rechnet hier keine Fachregeln nach: Sie liest nur
// Werte von HomeWake und vergleicht Zeitpunkte mit „jetzt“ (blass/fett).

import type { Hass, HassEntityState } from "./hass";

export const PLATTFORM = "homewake";

export type Typ = "person" | "raum";

/** Eine Person oder ein Raum: ein HomeWake-Gerät mit seinen Entities. */
export interface Objekt {
  /** ID des Untereintrags (wie `raum_id` an der Raum-Auswahl). */
  id: string;
  geraetId: string;
  typ: Typ;
  name: string;
  /** Übersetzungsschlüssel → Entity-ID, z. B. `wach` → `binary_sensor.x_wach`. */
  entities: Record<string, string>;
}

export interface Ereignis {
  art: "wecker" | "beginn" | "ende";
  zeit: Date;
  vergangen: boolean;
  naechster: boolean;
}

export interface Tag {
  /** Ein Zeitpunkt an diesem Tag (für Wochentag und Datum im Kopf). */
  datum: Date | null;
  /** Nur bei Personen: übersetzter Status und Grund des Tags. */
  status: string | null;
  grund: string | null;
  ereignisse: Ereignis[];
}

/** Name mit Ziel für einen Sprung (id = Untereintrag, null = kein Ziel). */
export interface Verweis {
  name: string;
  id: string | null;
}

export type Profil = "zeitplan" | "standard" | "ausnahme";

// Bedienelemente (B3, E74): jeweils die Entity, die die Karte über eine
// HA-Standardaktion ändert, ihr aktueller Wert und ob sie bedienbar ist
// (vorhanden und nicht „nicht verfügbar“). `entity` null = fehlt.

/** Ein `switch`: an/aus (null = unbekannt). */
export interface Schalter {
  entity: string | null;
  an: boolean | null;
  bedienbar: boolean;
}

/** Eine `time`-Entity: Uhrzeit „HH:MM“. */
export interface Uhrzeit {
  entity: string | null;
  wert: string | null;
  bedienbar: boolean;
}

export interface Option {
  wert: string;
  text: string;
}

/** Ein `select`: gewählte Option (roh und übersetzt) und alle Optionen. */
export interface Auswahl {
  entity: string | null;
  wert: string | null;
  text: string | null;
  optionen: Option[];
  bedienbar: boolean;
}

export interface LichtRadio {
  profil: Profil;
  licht: Schalter;
  radio: Schalter;
}

export interface PersonAnsicht {
  typ: "person";
  name: string;
  verfuegbar: boolean;
  wach: boolean | null;
  /** Gewählter Raum mit Sprungziel (zum Anzeigen und Springen). */
  raum: Verweis | null;
  /** Raum-Auswahl zum Ändern, inkl. „kein Raum“. */
  raumAuswahl: Auswahl;
  tage: [Tag, Tag];
  ausnahme: { schalter: Schalter; zeit: Uhrzeit };
  profile: LichtRadio[];
  favorit: Auswahl;
}

export interface RaumAnsicht {
  typ: "raum";
  name: string;
  verfuegbar: boolean;
  wach: boolean | null;
  tag: boolean | null;
  quelle: string | null;
  personen: Verweis[];
  /** Standard-Favorit; null, wenn der Raum keinen Lautsprecher hat. */
  favorit: Auswahl | null;
  tage: [Tag, Tag];
}

export interface LaufenderWecker {
  raum: Verweis;
  bis: Date;
  /** Taste „Wecken beenden“ des Raums (E60); null, wenn sie fehlt. */
  taste: { entity: string; bedienbar: boolean } | null;
}

const UNGUELTIG = new Set(["unknown", "unavailable"]);
const MODELL: Record<string, Typ> = { Person: "person", Raum: "raum" };

/** Alle HomeWake-Personen und -Räume, Personen zuerst, jeweils nach Namen. */
export function findeObjekte(hass: Hass): Objekt[] {
  const proGeraet = new Map<string, Record<string, string>>();
  for (const eintrag of Object.values(hass.entities)) {
    if (!eintrag || eintrag.platform !== PLATTFORM || !eintrag.device_id) continue;
    if (!eintrag.translation_key) continue;
    const liste = proGeraet.get(eintrag.device_id) ?? {};
    liste[eintrag.translation_key] = eintrag.entity_id;
    proGeraet.set(eintrag.device_id, liste);
  }
  const objekte: Objekt[] = [];
  for (const [geraetId, entities] of proGeraet) {
    const geraet = hass.devices[geraetId];
    const typ = MODELL[geraet?.model ?? ""];
    const id = geraet?.identifiers?.find(([domain]) => domain === PLATTFORM)?.[1];
    if (!geraet || !typ || !id) continue;
    const name = geraet.name_by_user || geraet.name || id;
    objekte.push({ id, geraetId, typ, name, entities });
  }
  return objekte.sort(
    (a, b) =>
      (a.typ === b.typ ? 0 : a.typ === "person" ? -1 : 1) ||
      a.name.localeCompare(b.name, hass.locale.language),
  );
}

// ---------------------------------------------------------------- Helfer

function zustand(hass: Hass, o: Objekt, schluessel: string): HassEntityState | null {
  const eid = o.entities[schluessel];
  return (eid && hass.states[eid]) || null;
}

function istAn(hass: Hass, o: Objekt, schluessel: string): boolean | null {
  const s = zustand(hass, o, schluessel);
  if (!s || UNGUELTIG.has(s.state)) return null;
  return s.state === "on";
}

/** Zeitpunkt aus einem Text (ISO) oder null. */
export function zeitpunkt(wert: unknown): Date | null {
  if (typeof wert !== "string" || UNGUELTIG.has(wert)) return null;
  const d = new Date(wert);
  return Number.isNaN(d.getTime()) ? null : d;
}

function zeitVon(hass: Hass, o: Objekt, schluessel: string): Date | null {
  return zeitpunkt(zustand(hass, o, schluessel)?.state);
}

/** Übersetzter Zustand einer Entity (Fallback: roher Zustand). */
function zeige(hass: Hass, s: HassEntityState | null): string | null {
  if (!s || UNGUELTIG.has(s.state)) return null;
  return hass.formatEntityState?.(s) ?? s.state;
}

/** Übersetzter Attributwert (Fallback: roher Wert); null, wenn er fehlt. */
function zeigeAttribut(
  hass: Hass,
  s: HassEntityState | null,
  attribut: string,
): string | null {
  const wert = s?.attributes[attribut];
  if (!s || wert === undefined || wert === null) return null;
  return hass.formatEntityAttributeValue?.(s, attribut) ?? String(wert);
}

function ereignis(
  art: Ereignis["art"],
  zeit: Date | null,
  jetzt: Date,
  naechster: Date | null = null,
): Ereignis[] {
  if (!zeit) return [];
  return [
    {
      art,
      zeit,
      vergangen: zeit.getTime() <= jetzt.getTime(),
      naechster: naechster !== null && zeit.getTime() === naechster.getTime(),
    },
  ];
}

function verfuegbar(hass: Hass, o: Objekt, schluessel: string): boolean {
  const s = zustand(hass, o, schluessel);
  return s !== null && s.state !== "unavailable";
}

// ---------------------------------------------------------------- Bedienelemente

function schalter(hass: Hass, o: Objekt, schluessel: string): Schalter {
  return {
    entity: o.entities[schluessel] ?? null,
    an: istAn(hass, o, schluessel),
    bedienbar: verfuegbar(hass, o, schluessel),
  };
}

function uhrzeitVon(hass: Hass, o: Objekt, schluessel: string): Uhrzeit {
  const s = zustand(hass, o, schluessel);
  return {
    entity: o.entities[schluessel] ?? null,
    // HA meldet „HH:MM:SS“; das Uhrzeitfeld braucht „HH:MM“
    wert: s && !UNGUELTIG.has(s.state) ? s.state.slice(0, 5) : null,
    bedienbar: verfuegbar(hass, o, schluessel),
  };
}

function auswahl(hass: Hass, o: Objekt, schluessel: string): Auswahl {
  const s = zustand(hass, o, schluessel);
  const wert = s && !UNGUELTIG.has(s.state) ? s.state : null;
  const roh = s?.attributes.options;
  const werte = Array.isArray(roh) ? roh.filter((x) => typeof x === "string") : [];
  // Der aktuelle Wert gehört immer in die Liste, sonst zeigte sie ihn nicht an
  if (wert !== null && !werte.includes(wert)) werte.push(wert);
  const text = (w: string) => (s && hass.formatEntityState?.(s, w)) ?? w;
  return {
    entity: o.entities[schluessel] ?? null,
    wert,
    text: zeige(hass, s),
    optionen: werte.map((w) => ({ wert: w, text: text(w) })),
    bedienbar: verfuegbar(hass, o, schluessel),
  };
}

// ---------------------------------------------------------------- Person

/** Ansicht einer Person: Tage heute/morgen, Raum, Ausnahme, Licht/Radio (E62). */
export function personAnsicht(
  hass: Hass,
  o: Objekt,
  objekte: Objekt[],
  jetzt: Date,
): PersonAnsicht {
  const status = zustand(hass, o, "status");
  const attr = (name: string) => zeitpunkt(status?.attributes[name]);
  const naechster = zeitVon(hass, o, "naechster_wecker");
  const tag = (wann: "heute" | "morgen"): Tag => {
    const beginn = attr(`tagesbeginn_${wann}`);
    return {
      datum: beginn,
      status: zeigeAttribut(hass, status, `status_${wann}`),
      grund: zeigeAttribut(hass, status, `grund_${wann}`),
      ereignisse: [
        ...ereignis("wecker", beginn, jetzt, naechster),
        ...ereignis("ende", attr(`tagesende_${wann}`), jetzt),
      ],
    };
  };

  const raumAuswahl = zustand(hass, o, "raum");
  const raumName = zeige(hass, raumAuswahl);
  const raumId = raumAuswahl?.attributes.raum_id;
  const ziel = objekte.find((r) => r.typ === "raum" && r.id === raumId);

  return {
    typ: "person",
    name: o.name,
    verfuegbar: verfuegbar(hass, o, "status"),
    wach: istAn(hass, o, "wach"),
    raum: raumName === null ? null : { name: raumName, id: ziel ? ziel.id : null },
    raumAuswahl: auswahl(hass, o, "raum"),
    tage: [tag("heute"), tag("morgen")],
    ausnahme: {
      schalter: schalter(hass, o, "ausnahme"),
      zeit: uhrzeitVon(hass, o, "ausnahme_zeit"),
    },
    profile: (["zeitplan", "standard", "ausnahme"] as const).map((profil) => ({
      profil,
      licht: schalter(hass, o, `licht_${profil}`),
      radio: schalter(hass, o, `radio_${profil}`),
    })),
    favorit: auswahl(hass, o, "favorit"),
  };
}

// ---------------------------------------------------------------- Raum

/** Ansicht eines Raums: Tage heute/morgen, Quelle, Personen, Favorit (E62). */
export function raumAnsicht(
  hass: Hass,
  o: Objekt,
  objekte: Objekt[],
  jetzt: Date,
): RaumAnsicht {
  const wecker = [zeitVon(hass, o, "weckzeit"), zeitVon(hass, o, "weckzeit_morgen")];
  // Der nächste Wecker des Raums ist der erste, der noch nicht erreicht ist.
  const naechster =
    wecker.find((w) => w !== null && w.getTime() > jetzt.getTime()) ?? null;
  const tag = (zusatz: "" | "_morgen", w: Date | null): Tag => {
    const beginn = zeitVon(hass, o, `tagesbeginn${zusatz}`);
    return {
      datum: w ?? beginn,
      status: null,
      grund: null,
      ereignisse: [
        ...ereignis("wecker", w, jetzt, naechster),
        ...ereignis("beginn", beginn, jetzt),
        ...ereignis("ende", zeitVon(hass, o, `tagesende${zusatz}`), jetzt),
      ],
    };
  };
  const weckzeit = zustand(hass, o, "weckzeit");
  const personen = objekte
    .filter(
      (p) =>
        p.typ === "person" && zustand(hass, p, "raum")?.attributes.raum_id === o.id,
    )
    .map((p) => ({ name: p.name, id: p.id }));
  return {
    typ: "raum",
    name: o.name,
    verfuegbar: verfuegbar(hass, o, "weckzeit"),
    wach: istAn(hass, o, "wach"),
    tag: istAn(hass, o, "tag"),
    quelle: zeigeAttribut(hass, weckzeit, "quelle"),
    personen,
    favorit: o.entities.standard_favorit ? auswahl(hass, o, "standard_favorit") : null,
    tage: [tag("", wecker[0] ?? null), tag("_morgen", wecker[1] ?? null)],
  };
}

// ---------------------------------------------------------------- Laufende Wecker

/** Räume, in denen gerade geweckt wird (`wecken_bis`, E64), nach Endzeit. */
export function laufendeWecker(hass: Hass, objekte: Objekt[]): LaufenderWecker[] {
  const laufend: LaufenderWecker[] = [];
  for (const o of objekte) {
    if (o.typ !== "raum") continue;
    const bis = zeitpunkt(zustand(hass, o, "wach")?.attributes.wecken_bis);
    if (bis) {
      const eid = o.entities.wecken_beenden;
      const taste = eid
        ? { entity: eid, bedienbar: verfuegbar(hass, o, "wecken_beenden") }
        : null;
      laufend.push({ raum: { name: o.name, id: o.id }, bis, taste });
    }
  }
  return laufend.sort((a, b) => a.bis.getTime() - b.bis.getTime());
}
