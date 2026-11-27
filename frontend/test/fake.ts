// Nachgebautes `hass` für die Tests: eine Person „Vater“ im Raum
// „Schlafzimmer“, ein zweiter Raum „Bad“ ohne Personen, ein fremdes Gerät.
// Zeiten in UTC; „jetzt“ ist Dienstag 2026-07-14 05:00 UTC (07:00 in Berlin).

import type { Hass, HassEntityState } from "../src/hass";

export const JETZT = new Date("2026-07-14T05:00:00Z");

type Werte = Record<string, [string, Record<string, unknown>?]>;

const PERSON: Werte = {
  status: [
    "werktag",
    {
      status_heute: "werktag",
      grund_heute: "dienstag",
      status_morgen: "feiertag",
      grund_morgen: "Testtag",
      tagesbeginn_heute: "2026-07-14T04:15:00+00:00",
      tagesende_heute: "2026-07-14T20:00:00+00:00",
      tagesbeginn_morgen: "2026-07-15T06:00:00+00:00",
      tagesende_morgen: "2026-07-15T19:00:00+00:00",
    },
  ],
  naechster_wecker: ["2026-07-15T06:00:00+00:00"],
  naechstes_tagesende: ["2026-07-14T20:00:00+00:00"],
  wach: ["on"],
  raum: ["Schlafzimmer", { raum_id: "r1", options: ["kein_raum", "Schlafzimmer"] }],
  ausnahme: ["off"],
  ausnahme_zeit: ["08:00:00"],
  licht_zeitplan: ["on"],
  radio_zeitplan: ["off"],
  licht_standard: ["off"],
  radio_standard: ["on"],
  licht_ausnahme: ["unavailable"],
  radio_ausnahme: ["off"],
  favorit: ["SWR3", { options: ["kein_favorit", "SWR3", "hr3"] }],
};

const RAUM: Werte = {
  weckzeit: ["2026-07-14T04:15:00+00:00", { quelle: "personen", personen: ["x"] }],
  tagesbeginn: ["2026-07-14T04:30:00+00:00"],
  tagesende: ["2026-07-14T19:30:00+00:00"],
  weckzeit_morgen: ["2026-07-15T06:00:00+00:00"],
  tagesbeginn_morgen: ["2026-07-15T06:00:00+00:00"],
  tagesende_morgen: ["2026-07-15T19:00:00+00:00"],
  wach: ["on", { wecken_bis: "2026-07-14T05:00:00+00:00" }],
  tag: ["on"],
  standard_favorit: ["kein_favorit", { options: ["kein_favorit", "SWR3"] }],
  wecken_beenden: ["unknown"],
};

const BAD: Werte = {
  weckzeit: ["2026-07-14T06:00:00+00:00", { quelle: "standardplan" }],
  tagesbeginn: ["unknown"],
  tagesende: ["2026-07-14T19:30:00+00:00"],
  weckzeit_morgen: ["2026-07-15T06:00:00+00:00"],
  tagesbeginn_morgen: ["2026-07-15T06:00:00+00:00"],
  tagesende_morgen: ["2026-07-15T19:00:00+00:00"],
  wach: ["off"],
  tag: ["off"],
};

const DOMAINS: Record<string, string> = {
  status: "sensor",
  naechster_wecker: "sensor",
  naechstes_tagesende: "sensor",
  weckzeit: "sensor",
  tagesbeginn: "sensor",
  tagesende: "sensor",
  weckzeit_morgen: "sensor",
  tagesbeginn_morgen: "sensor",
  tagesende_morgen: "sensor",
  wach: "binary_sensor",
  tag: "binary_sensor",
  raum: "select",
  favorit: "select",
  standard_favorit: "select",
  ausnahme_zeit: "time",
  wecken_beenden: "button",
};

/** Baut ein `hass` aus Geräten; `aendern` passt Zustände vorher an. */
export function fakeHass(
  aendern: (states: Record<string, HassEntityState>) => void = () => {},
): Hass {
  const hass: Hass = {
    states: {},
    entities: {},
    devices: {},
    locale: { language: "de" },
    config: { time_zone: "Europe/Berlin" },
    formatEntityState: (s, wert) => `«${wert ?? s.state}»`,
    formatEntityAttributeValue: (s, a) => `«${String(s.attributes[a])}»`,
  };
  const geraet = (id: string, name: string, model: string, werte: Werte) => {
    hass.devices[`d_${id}`] = {
      id: `d_${id}`,
      name,
      model,
      identifiers: [["homewake", id]],
    };
    for (const [schluessel, [state, attributes]] of Object.entries(werte)) {
      const domain = DOMAINS[schluessel] ?? "switch";
      const eid = `${domain}.${id}_${schluessel}`;
      hass.entities[eid] = {
        entity_id: eid,
        device_id: `d_${id}`,
        platform: "homewake",
        translation_key: schluessel,
      };
      hass.states[eid] = { entity_id: eid, state, attributes: attributes ?? {} };
    }
  };
  geraet("p1", "Vater", "Person", PERSON);
  geraet("r1", "Schlafzimmer", "Raum", RAUM);
  geraet("r2", "Bad", "Raum", BAD);
  // Fremdes Gerät und eine Entity ohne Gerät: werden ignoriert
  hass.devices.fremd = { id: "fremd", name: "Lampe", model: "X" };
  hass.entities["light.lampe"] = {
    entity_id: "light.lampe",
    device_id: "fremd",
    platform: "hue",
  };
  hass.entities["sensor.ohne"] = { entity_id: "sensor.ohne", platform: "homewake" };
  aendern(hass.states as Record<string, HassEntityState>);
  return hass;
}
