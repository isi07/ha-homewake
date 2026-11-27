import { describe, expect, it } from "vitest";
import {
  findeObjekte,
  laufendeWecker,
  personAnsicht,
  raumAnsicht,
  zeitpunkt,
} from "../src/daten";
import { fakeHass, JETZT } from "./fake";

describe("findeObjekte", () => {
  it("findet Personen zuerst, dann Räume nach Namen, nur HomeWake-Geräte", () => {
    const objekte = findeObjekte(fakeHass());
    expect(objekte.map((o) => [o.typ, o.name, o.id])).toEqual([
      ["person", "Vater", "p1"],
      ["raum", "Bad", "r2"],
      ["raum", "Schlafzimmer", "r1"],
    ]);
    expect(objekte[0]?.entities.wach).toBe("binary_sensor.p1_wach");
  });

  it("bevorzugt den vom Nutzer vergebenen Gerätenamen", () => {
    const hass = fakeHass();
    const geraet = hass.devices.d_p1;
    if (geraet) geraet.name_by_user = "Papa";
    expect(findeObjekte(hass)[0]?.name).toBe("Papa");
  });

  it("überspringt Geräte ohne passendes Modell oder ohne Kennung", () => {
    const hass = fakeHass();
    const raum = hass.devices.d_r2;
    if (raum) raum.model = "Etwas";
    const person = hass.devices.d_p1;
    if (person) person.identifiers = [];
    expect(findeObjekte(hass).map((o) => o.id)).toEqual(["r1"]);
  });
});

describe("zeitpunkt", () => {
  it("liest ISO-Texte, sonst null", () => {
    expect(zeitpunkt("2026-07-14T04:15:00+00:00")?.toISOString()).toBe(
      "2026-07-14T04:15:00.000Z",
    );
    expect(zeitpunkt("unknown")).toBeNull();
    expect(zeitpunkt("kein Datum")).toBeNull();
    expect(zeitpunkt(42)).toBeNull();
  });
});

describe("personAnsicht", () => {
  const hass = fakeHass();
  const objekte = findeObjekte(hass);
  const person = objekte[0];
  if (!person) throw new Error("Person fehlt");
  const a = personAnsicht(hass, person, objekte, JETZT);

  it("zeigt Status und Grund je Tag übersetzt", () => {
    expect(a.tage.map((t) => [t.status, t.grund])).toEqual([
      ["«werktag»", "«dienstag»"],
      ["«feiertag»", "«Testtag»"],
    ]);
  });

  it("markiert vergangene Ereignisse und den nächsten Wecker", () => {
    const [heute, morgen] = a.tage;
    expect(heute.ereignisse.map((e) => [e.art, e.vergangen, e.naechster])).toEqual([
      ["wecker", true, false],
      ["ende", false, false],
    ]);
    expect(morgen.ereignisse[0]).toMatchObject({ art: "wecker", naechster: true });
    expect(heute.datum?.toISOString()).toBe("2026-07-14T04:15:00.000Z");
  });

  it("zeigt Raum mit Sprungziel, Ausnahme, Licht/Radio und Favorit", () => {
    expect(a.raum).toEqual({ name: "«Schlafzimmer»", id: "r1" });
    expect(a.wach).toBe(true);
    expect(a.verfuegbar).toBe(true);
    expect(a.ausnahme).toEqual({
      schalter: { entity: "switch.p1_ausnahme", an: false, bedienbar: true },
      zeit: { entity: "time.p1_ausnahme_zeit", wert: "08:00", bedienbar: true },
    });
    const an = (e: string, wert: boolean | null, bedienbar = true) => ({
      entity: `switch.p1_${e}`,
      an: wert,
      bedienbar,
    });
    expect(a.profile).toEqual([
      {
        profil: "zeitplan",
        licht: an("licht_zeitplan", true),
        radio: an("radio_zeitplan", false),
      },
      {
        profil: "standard",
        licht: an("licht_standard", false),
        radio: an("radio_standard", true),
      },
      {
        profil: "ausnahme",
        licht: an("licht_ausnahme", null, false),
        radio: an("radio_ausnahme", false),
      },
    ]);
    expect(a.favorit.text).toBe("«SWR3»");
  });

  it("ohne Raum: Raum ohne Sprungziel", () => {
    const h = fakeHass((s) => {
      s["select.p1_raum"] = {
        entity_id: "select.p1_raum",
        state: "kein_raum",
        attributes: { raum_id: null },
      };
    });
    const o = findeObjekte(h);
    expect(personAnsicht(h, o[0] as never, o, JETZT).raum).toEqual({
      name: "«kein_raum»",
      id: null,
    });
  });

  it("nicht verfügbar: keine Zeiten, keine Werte, nicht verfügbar", () => {
    const h = fakeHass((s) => {
      for (const eid of Object.keys(s)) {
        if (eid.includes("p1_")) {
          s[eid] = { entity_id: eid, state: "unavailable", attributes: {} };
        }
      }
    });
    const o = findeObjekte(h);
    const n = personAnsicht(h, o[0] as never, o, JETZT);
    expect(n.verfuegbar).toBe(false);
    expect(n.raum).toBeNull();
    expect(n.tage[0]).toEqual({
      datum: null,
      status: null,
      grund: null,
      ereignisse: [],
    });
    expect(n.ausnahme.schalter).toEqual({
      entity: "switch.p1_ausnahme",
      an: null,
      bedienbar: false,
    });
    expect(n.ausnahme.zeit.wert).toBeNull();
    expect(n.favorit.text).toBeNull();
    expect(n.favorit.bedienbar).toBe(false);
    expect(n.raumAuswahl.bedienbar).toBe(false);
  });

  it("ohne Formatierungsfunktionen von HA: rohe Werte", () => {
    const h = fakeHass();
    delete h.formatEntityState;
    delete h.formatEntityAttributeValue;
    const o = findeObjekte(h);
    const n = personAnsicht(h, o[0] as never, o, JETZT);
    expect(n.tage[0].status).toBe("werktag");
    expect(n.raum?.name).toBe("Schlafzimmer");
  });
});

describe("raumAnsicht", () => {
  const hass = fakeHass();
  const objekte = findeObjekte(hass);
  const schlafzimmer = objekte.find((o) => o.id === "r1");
  const bad = objekte.find((o) => o.id === "r2");
  if (!schlafzimmer || !bad) throw new Error("Raum fehlt");

  it("zeigt Wecker, Tagesbeginn und Tagesende je Tag", () => {
    const a = raumAnsicht(hass, schlafzimmer, objekte, JETZT);
    expect(a.tage[0].ereignisse.map((e) => [e.art, e.vergangen])).toEqual([
      ["wecker", true],
      ["beginn", true],
      ["ende", false],
    ]);
    // Heute ist vorbei: der nächste Wecker ist morgen
    expect(a.tage[1].ereignisse[0]).toMatchObject({ art: "wecker", naechster: true });
    expect(a.tage[0].status).toBeNull();
  });

  it("zeigt Zustände, Quelle, Personen mit Sprungziel und Standard-Favorit", () => {
    const a = raumAnsicht(hass, schlafzimmer, objekte, JETZT);
    expect([a.wach, a.tag, a.verfuegbar]).toEqual([true, true, true]);
    expect(a.quelle).toBe("«personen»");
    expect(a.personen).toEqual([{ name: "Vater", id: "p1" }]);
    expect(a.favorit?.text).toBe("«kein_favorit»");
  });

  it("Raum ohne Personen und ohne Lautsprecher; heutiger Wecker steht noch an", () => {
    const a = raumAnsicht(hass, bad, objekte, JETZT);
    expect(a.personen).toEqual([]);
    expect(a.favorit).toBeNull();
    expect(a.tage[0].ereignisse.map((e) => e.art)).toEqual(["wecker", "ende"]);
    expect(a.tage[0].ereignisse[0]?.naechster).toBe(true);
    expect(a.tage[1].ereignisse[0]?.naechster).toBe(false);
  });

  it("ohne Weckzeiten: Datum aus dem Tagesbeginn, kein nächster Wecker", () => {
    const h = fakeHass((s) => {
      for (const eid of ["sensor.r1_weckzeit", "sensor.r1_weckzeit_morgen"]) {
        s[eid] = { entity_id: eid, state: "unavailable", attributes: {} };
      }
    });
    const o = findeObjekte(h);
    const a = raumAnsicht(h, o.find((x) => x.id === "r1") as never, o, JETZT);
    expect(a.verfuegbar).toBe(false);
    expect(a.tage[1].datum?.toISOString()).toBe("2026-07-15T06:00:00.000Z");
    expect(a.tage[1].ereignisse.some((e) => e.naechster)).toBe(false);
  });
});

describe("laufendeWecker", () => {
  it("nennt Räume mit wecken_bis", () => {
    const hass = fakeHass();
    expect(laufendeWecker(hass, findeObjekte(hass))).toEqual([
      {
        raum: { name: "Schlafzimmer", id: "r1" },
        bis: new Date("2026-07-14T05:00:00Z"),
        taste: { entity: "button.r1_wecken_beenden", bedienbar: true },
      },
    ]);
  });

  it("sortiert nach Endzeit", () => {
    const hass = fakeHass((s) => {
      s["binary_sensor.r2_wach"] = {
        entity_id: "binary_sensor.r2_wach",
        state: "on",
        attributes: { wecken_bis: "2026-07-14T04:50:00+00:00" },
      };
    });
    expect(laufendeWecker(hass, findeObjekte(hass)).map((w) => w.raum.id)).toEqual([
      "r2",
      "r1",
    ]);
  });
});

describe("Review B2b", () => {
  it("nur formatEntityState vorhanden: Attribute roh", () => {
    const h = fakeHass();
    delete h.formatEntityAttributeValue;
    const o = findeObjekte(h);
    const a = personAnsicht(h, o[0] as never, o, JETZT);
    expect(a.tage[0].status).toBe("werktag");
    expect(a.favorit.text).toBe("«SWR3»");
  });

  it("Entity in der Registry ohne Zustand gilt als fehlend", () => {
    const h = fakeHass((s) => {
      delete s["select.p1_favorit"];
      delete s["binary_sensor.p1_wach"];
    });
    const o = findeObjekte(h);
    const a = personAnsicht(h, o[0] as never, o, JETZT);
    expect(a.favorit).toEqual({
      entity: "select.p1_favorit",
      wert: null,
      text: null,
      optionen: [],
      bedienbar: false,
    });
    expect(a.wach).toBeNull();
  });
});

describe("Bedienung B3 (E74)", () => {
  it("Auswahllisten: Optionen aus `options`, übersetzt, mit gewähltem Wert", () => {
    const h = fakeHass();
    const o = findeObjekte(h);
    const a = personAnsicht(h, o[0] as never, o, JETZT);
    expect(a.raumAuswahl).toEqual({
      entity: "select.p1_raum",
      wert: "Schlafzimmer",
      text: "«Schlafzimmer»",
      optionen: [
        { wert: "kein_raum", text: "«kein_raum»" },
        { wert: "Schlafzimmer", text: "«Schlafzimmer»" },
      ],
      bedienbar: true,
    });
    expect(a.favorit.optionen.map((x) => x.wert)).toEqual([
      "kein_favorit",
      "SWR3",
      "hr3",
    ]);
    const r = raumAnsicht(h, o.find((x) => x.id === "r1") as never, o, JETZT);
    expect(r.favorit?.entity).toBe("select.r1_standard_favorit");
    expect(r.favorit?.optionen).toHaveLength(2);
  });

  it("ohne Formatierung: Optionen roh; kaputte `options`: nur der aktuelle Wert", () => {
    const h = fakeHass((s) => {
      const f = s["select.p1_favorit"];
      if (f) f.attributes = { options: "kaputt" };
    });
    delete h.formatEntityState;
    const o = findeObjekte(h);
    const a = personAnsicht(h, o[0] as never, o, JETZT);
    expect(a.raumAuswahl.optionen[0]).toEqual({ wert: "kein_raum", text: "kein_raum" });
    // Der aktuelle Wert steht immer in der Liste, sonst zeigte sie ihn nicht an
    expect(a.favorit.optionen).toEqual([{ wert: "SWR3", text: "SWR3" }]);
  });

  it("unbekannter Zustand bleibt bedienbar, nicht verfügbar nicht", () => {
    const h = fakeHass((s) => {
      s["switch.p1_ausnahme"] = {
        entity_id: "switch.p1_ausnahme",
        state: "unknown",
        attributes: {},
      };
      s["time.p1_ausnahme_zeit"] = {
        entity_id: "time.p1_ausnahme_zeit",
        state: "unavailable",
        attributes: {},
      };
    });
    const o = findeObjekte(h);
    const a = personAnsicht(h, o[0] as never, o, JETZT);
    expect(a.ausnahme.schalter).toMatchObject({ an: null, bedienbar: true });
    expect(a.ausnahme.zeit).toMatchObject({ wert: null, bedienbar: false });
  });

  it("fehlende Entity: kein Ziel, nicht bedienbar", () => {
    const h = fakeHass();
    delete h.entities["switch.p1_licht_standard"];
    const o = findeObjekte(h);
    const a = personAnsicht(h, o[0] as never, o, JETZT);
    expect(a.profile[1]?.licht).toEqual({ entity: null, an: null, bedienbar: false });
  });

  it("laufender Wecker ohne Taste: taste null", () => {
    const h = fakeHass((s) => {
      s["binary_sensor.r2_wach"] = {
        entity_id: "binary_sensor.r2_wach",
        state: "on",
        attributes: { wecken_bis: "2026-07-14T04:50:00+00:00" },
      };
    });
    const w = laufendeWecker(h, findeObjekte(h));
    expect(w.find((x) => x.raum.id === "r2")?.taste).toBeNull();
  });
});
