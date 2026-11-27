import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "../src/homewake-card";
import type { Hass } from "../src/hass";
import type { HomeWakeCard } from "../src/homewake-card";
import { fakeHass, JETZT } from "./fake";

async function karte(
  hass: Hass = fakeHass(),
  config: Record<string, unknown> = {},
): Promise<HomeWakeCard> {
  const el = document.createElement("homewake-card") as HomeWakeCard;
  el.setConfig({ type: "custom:homewake-card", ...config });
  el.hass = hass;
  document.body.appendChild(el);
  await el.updateComplete;
  return el;
}

function root(el: HomeWakeCard): ShadowRoot {
  if (!el.shadowRoot) throw new Error("kein shadowRoot");
  return el.shadowRoot;
}

/** Name der gezeigten Person bzw. des Raums (gewählte Option oben). */
function angezeigt(el: HomeWakeCard): string {
  const auswahl = root(el).querySelector("select") as HTMLSelectElement | null;
  const option = [...(auswahl?.options ?? [])].find((o) => o.value === auswahl?.value);
  return option?.textContent ?? "";
}

function text(el: HomeWakeCard, selektor: string): string {
  return (
    root(el).querySelector(selektor)?.textContent?.replace(/\s+/g, " ").trim() ?? ""
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(JETZT);
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("Anmeldung", () => {
  it("meldet sich in der Kartenauswahl an", () => {
    const karten = (window as unknown as { customCards: { type: string }[] })
      .customCards;
    expect(karten.some((k) => k.type === "homewake-card")).toBe(true);
  });

  it("liefert eine leere Vorgabe und eine Größe", async () => {
    const el = await karte();
    const klasse = customElements.get("homewake-card") as unknown as {
      getStubConfig: () => object;
    };
    expect(klasse.getStubConfig()).toEqual({});
    expect(el.getCardSize()).toBeGreaterThan(0);
  });
});

describe("Auswahl", () => {
  it("zeigt alle Personen und Räume, zuerst die erste Person", async () => {
    const el = await karte();
    const optionen = [...root(el).querySelectorAll("select.name option")].map(
      (o) => o.textContent,
    );
    expect(optionen).toEqual(["Vater", "Bad", "Schlafzimmer"]);
    expect(angezeigt(el)).toBe("Vater");
  });

  it("startet mit dem eingestellten Objekt (ID oder Name)", async () => {
    expect(angezeigt(await karte(fakeHass(), { objekt: "r2" }))).toBe("Bad");
    document.body.innerHTML = "";
    expect(angezeigt(await karte(fakeHass(), { objekt: "Schlafzimmer" }))).toBe(
      "Schlafzimmer",
    );
  });

  it("wechselt über die Auswahl", async () => {
    const el = await karte();
    const auswahl = root(el).querySelector("select") as HTMLSelectElement;
    auswahl.value = "r1";
    auswahl.dispatchEvent(new Event("change"));
    await el.updateComplete;
    expect(angezeigt(el)).toBe("Schlafzimmer");
  });

  it("springt von der Person zum Raum und vom Raum zur Person", async () => {
    const el = await karte();
    (root(el).querySelector("button.verweis") as HTMLButtonElement).click();
    await el.updateComplete;
    expect(angezeigt(el)).toBe("Schlafzimmer");
    (root(el).querySelector(".personen button.verweis") as HTMLButtonElement).click();
    await el.updateComplete;
    expect(angezeigt(el)).toBe("Vater");
  });

  it("ohne HomeWake-Geräte ein Hinweis", async () => {
    const hass = fakeHass();
    hass.entities = {};
    const el = await karte(hass);
    expect(text(el, ".leer")).toContain("HomeWake");
  });

  it("verschwundenes Objekt: zurück zum ersten", async () => {
    const el = await karte(fakeHass(), { objekt: "r2" });
    const hass = fakeHass();
    delete hass.devices.d_r2;
    el.hass = hass;
    await el.updateComplete;
    expect(angezeigt(el)).toBe("Vater");
  });
});

describe("Person", () => {
  it("zeigt wach, Tage mit Status, vergangene Ereignisse blass, nächsten Wecker fett", async () => {
    const el = await karte();
    expect(text(el, ".pille")).toBe("wach");
    const tage = root(el).querySelectorAll(".tag");
    expect(tage).toHaveLength(2);
    expect(tage[0]?.querySelector(".status")?.textContent).toContain("«werktag»");
    expect(tage[0]?.querySelector(".status")?.textContent).toContain("«dienstag»");
    expect(tage[0]?.querySelector(".ereignis")?.classList.contains("vergangen")).toBe(
      true,
    );
    expect(tage[1]?.querySelector(".ereignis.naechster")?.textContent).toContain(
      "08:00",
    );
    // Kopf mit Wochentag und Datum in HA-Zeitzone
    expect(tage[0]?.querySelector(".datum")?.textContent).toContain("14.07.");
  });

  it("zeigt Raum, Ausnahme, Licht/Radio je Profil und Favorit", async () => {
    const el = await karte();
    const raum = root(el).querySelector(".raum select") as HTMLSelectElement;
    expect(raum.value).toBe("Schlafzimmer");
    expect(
      root(el).querySelector("button.verweis")?.getAttribute("aria-label"),
    ).toContain("Schlafzimmer");
    const uhr = root(el).querySelector(".ausnahme input") as HTMLInputElement;
    expect(uhr.value).toBe("08:00");
    const schalter = root(el).querySelector(".ausnahme [role=switch]");
    expect(schalter?.getAttribute("aria-checked")).toBe("false");
    const profile = [...root(el).querySelectorAll(".profil")].map((p) =>
      p.textContent?.replace(/\s+/g, " ").trim(),
    );
    expect(profile).toHaveLength(3);
    expect(profile[1]).toContain("Frei");
    expect(root(el).querySelectorAll(".profil .an")).toHaveLength(2);
    expect(text(el, ".favorit")).toContain("«SWR3»");
  });

  it("Raum ohne Sprungziel ist kein Knopf", async () => {
    const el = await karte(
      fakeHass((s) => {
        s["select.p1_raum"] = {
          entity_id: "select.p1_raum",
          state: "kein_raum",
          attributes: { raum_id: null },
        };
      }),
    );
    expect(root(el).querySelector("button.verweis")).toBeNull();
    expect(text(el, ".raum")).toContain("«kein_raum»");
  });

  it("nicht verfügbar wird angezeigt", async () => {
    const el = await karte(
      fakeHass((s) => {
        s["sensor.p1_status"] = {
          entity_id: "sensor.p1_status",
          state: "unavailable",
          attributes: {},
        };
        s["binary_sensor.p1_wach"] = {
          entity_id: "binary_sensor.p1_wach",
          state: "unavailable",
          attributes: {},
        };
      }),
    );
    expect(text(el, ".hinweis")).toBe("nicht verfügbar");
    expect(text(el, ".pille")).toBe("–");
  });
});

describe("Raum", () => {
  it("zeigt wach/Tag, Quelle, Personen und Standard-Favorit", async () => {
    const el = await karte(fakeHass(), { objekt: "r1" });
    expect(text(el, ".pille")).toBe("wach");
    expect(text(el, ".werte")).toContain("Tag");
    expect(text(el, ".werte")).toContain("«personen»");
    expect(text(el, ".personen")).toContain("Vater");
    expect(text(el, ".favorit")).toContain("«kein_favorit»");
    expect(root(el).querySelectorAll(".tag .ereignis")).toHaveLength(6);
  });

  it("Raum ohne Personen, schläft, Nacht", async () => {
    const el = await karte(fakeHass(), { objekt: "r2" });
    expect(text(el, ".pille")).toBe("schläft");
    expect(text(el, ".werte")).toContain("Nacht");
    expect(text(el, ".personen")).toContain("niemand");
    expect(root(el).querySelector(".favorit")).toBeNull();
  });
});

describe("Laufende Wecker", () => {
  it("stehen oben, unabhängig von der Auswahl, und springen zum Raum", async () => {
    const el = await karte();
    expect(text(el, ".laufend")).toContain("Schlafzimmer");
    expect(text(el, ".laufend")).toContain("07:00");
    (root(el).querySelector(".laufend button") as HTMLButtonElement).click();
    await el.updateComplete;
    expect(angezeigt(el)).toBe("Schlafzimmer");
  });

  it("ohne laufendes Wecken kein Bereich", async () => {
    const el = await karte(
      fakeHass((s) => {
        s["binary_sensor.r1_wach"] = {
          entity_id: "binary_sensor.r1_wach",
          state: "on",
          attributes: {},
        };
      }),
    );
    expect(root(el).querySelector(".laufend")).toBeNull();
  });
});

describe("Zahnrad und Sprache", () => {
  it("springt zur HomeWake-Seite in HA (E65)", async () => {
    const el = await karte();
    const gemeldet: string[] = [];
    window.addEventListener("location-changed", () => gemeldet.push(location.pathname));
    (root(el).querySelector("button.zahnrad") as HTMLButtonElement).click();
    expect(location.pathname).toBe("/config/integrations/integration/homewake");
    expect(gemeldet).toContain("/config/integrations/integration/homewake");
  });

  it("englische Texte bei englischem HA", async () => {
    const hass = fakeHass();
    hass.locale = { language: "en" };
    const el = await karte(hass);
    expect(text(el, ".pille")).toBe("awake");
    expect(text(el, ".profil")).toContain("Schedule");
  });

  it("unbekannte Sprache fällt auf Englisch zurück", async () => {
    const hass = fakeHass();
    hass.locale = { language: "fr" };
    expect(text(await karte(hass), ".pille")).toBe("awake");
  });
});

describe("Review B2b", () => {
  it("Licht/Radio nennen ihren Zustand auch für Screenreader", async () => {
    const el = await karte();
    const titel = [...root(el).querySelectorAll(".profil button[title]")].map((s) =>
      s.getAttribute("title"),
    );
    expect(titel).toContain("Licht: an");
    expect(titel).toContain("Radio: aus");
    expect(titel).toContain("Licht: –");
    expect(root(el).querySelectorAll(".profil .unbekannt")).toHaveLength(1);
  });

  it("meldet sich nur einmal in der Kartenauswahl an", async () => {
    const karten = (window as unknown as { customCards: { type: string }[] })
      .customCards;
    vi.resetModules();
    await import("../src/homewake-card");
    expect(karten.filter((k) => k.type === "homewake-card")).toHaveLength(1);
  });

  it("Auswahlliste folgt einem Wechsel über die Konfiguration", async () => {
    const el = await karte();
    el.setConfig({ type: "custom:homewake-card", objekt: "r2" });
    await el.updateComplete;
    expect(angezeigt(el)).toBe("Bad");
  });
});

// ---------------------------------------------------------------- Phase B3

type Aufruf = [string, string, Record<string, unknown> | undefined, unknown, unknown];

/** `hass` mit aufgezeichnetem `callService`; `fehler` lässt den Aufruf scheitern. */
function bedienHass(fehler?: unknown): { hass: Hass; aufrufe: Aufruf[] } {
  const aufrufe: Aufruf[] = [];
  const hass = fakeHass();
  hass.callService = (domain, service, daten, ziel, melden) => {
    aufrufe.push([domain, service, daten, ziel, melden]);
    return fehler === undefined ? Promise.resolve(undefined) : Promise.reject(fehler);
  };
  return { hass, aufrufe };
}

async function warte(el: HomeWakeCard): Promise<void> {
  await new Promise((r) => setTimeout(r, 0));
  await el.updateComplete;
}

function waehle(el: HomeWakeCard, selektor: string, wert: string): void {
  const s = root(el).querySelector(selektor) as HTMLSelectElement;
  s.value = wert;
  s.dispatchEvent(new Event("change"));
}

function ausnahmeSchalter(el: HomeWakeCard): HTMLButtonElement {
  return root(el).querySelector(".ausnahme [role=switch]") as HTMLButtonElement;
}

describe("Bedienung Person (B3)", () => {
  it("Ausnahme an über switch.turn_on, ohne eigene HA-Meldung (E76)", async () => {
    const { hass, aufrufe } = bedienHass();
    const el = await karte(hass);
    ausnahmeSchalter(el).click();
    await warte(el);
    expect(aufrufe).toEqual([
      ["switch", "turn_on", {}, { entity_id: "switch.p1_ausnahme" }, false],
    ]);
  });

  it("eingeschaltete Ausnahme wird ausgeschaltet", async () => {
    const { hass, aufrufe } = bedienHass();
    const s = hass.states["switch.p1_ausnahme"];
    if (s) s.state = "on";
    const el = await karte(hass);
    expect(ausnahmeSchalter(el).getAttribute("aria-checked")).toBe("true");
    ausnahmeSchalter(el).click();
    await warte(el);
    expect(aufrufe[0]?.slice(0, 2)).toEqual(["switch", "turn_off"]);
  });

  it("Uhrzeit über time.set_value; leer oder unverändert: nichts (E77)", async () => {
    const { hass, aufrufe } = bedienHass();
    const el = await karte(hass);
    const uhr = root(el).querySelector(".ausnahme input") as HTMLInputElement;
    for (const wert of ["", "08:00", "06:45"]) {
      uhr.value = wert;
      uhr.dispatchEvent(new Event("blur"));
    }
    await warte(el);
    expect(aufrufe).toEqual([
      [
        "time",
        "set_value",
        { time: "06:45:00" },
        { entity_id: "time.p1_ausnahme_zeit" },
        false,
      ],
    ]);
  });

  it("ein geleertes Uhrzeitfeld zeigt wieder den Wert von HA", async () => {
    const { hass } = bedienHass();
    const el = await karte(hass);
    const uhr = root(el).querySelector(".ausnahme input") as HTMLInputElement;
    uhr.value = "";
    uhr.dispatchEvent(new Event("blur"));
    await el.updateComplete;
    expect(uhr.value).toBe("08:00");
  });

  it("Licht/Radio je Profil schalten den passenden Schalter", async () => {
    const { hass, aufrufe } = bedienHass();
    const el = await karte(hass);
    const knoepfe = root(el).querySelectorAll(
      ".profil button",
    ) as NodeListOf<HTMLButtonElement>;
    knoepfe[0]?.click(); // Licht Zeitplan: an → aus
    knoepfe[3]?.click(); // Radio Frei: an → aus
    knoepfe[5]?.click(); // Radio Ausnahme: aus → an
    await warte(el);
    expect(aufrufe.map((a) => [a[1], a[3]])).toEqual([
      ["turn_off", { entity_id: "switch.p1_licht_zeitplan" }],
      ["turn_off", { entity_id: "switch.p1_radio_standard" }],
      ["turn_on", { entity_id: "switch.p1_radio_ausnahme" }],
    ]);
    // Licht Ausnahme ist nicht verfügbar: gesperrt
    expect(knoepfe[4]?.disabled).toBe(true);
    expect(knoepfe[4]?.getAttribute("aria-pressed")).toBe("mixed");
    expect(knoepfe[0]?.getAttribute("aria-pressed")).toBe("true");
  });

  it("Raum und Favorit über select.select_option, auch „kein Raum“", async () => {
    const { hass, aufrufe } = bedienHass();
    const el = await karte(hass);
    const raum = root(el).querySelector(".raum select") as HTMLSelectElement;
    expect([...raum.options].map((o) => o.textContent)).toEqual([
      "«kein_raum»",
      "«Schlafzimmer»",
    ]);
    waehle(el, ".raum select", "kein_raum");
    waehle(el, ".favorit select", "hr3");
    await warte(el);
    expect(aufrufe).toEqual([
      [
        "select",
        "select_option",
        { option: "kein_raum" },
        { entity_id: "select.p1_raum" },
        false,
      ],
      [
        "select",
        "select_option",
        { option: "hr3" },
        { entity_id: "select.p1_favorit" },
        false,
      ],
    ]);
  });

  it("dieselbe Option noch einmal gewählt: nichts", async () => {
    const { hass, aufrufe } = bedienHass();
    const el = await karte(hass);
    waehle(el, ".favorit select", "SWR3");
    await warte(el);
    expect(aufrufe).toEqual([]);
  });

  it("während der Aktion beschäftigt, behält den Fokus, Doppelklick ignoriert", async () => {
    let fertig: (wert?: unknown) => void = () => {};
    let anzahl = 0;
    const hass = fakeHass();
    hass.callService = () =>
      new Promise((r) => {
        anzahl += 1;
        fertig = r;
      });
    const el = await karte(hass);
    ausnahmeSchalter(el).click();
    ausnahmeSchalter(el).click();
    await el.updateComplete;
    expect(anzahl).toBe(1);
    expect(ausnahmeSchalter(el).getAttribute("aria-busy")).toBe("true");
    // nicht `disabled`: das Element verliert den Tastaturfokus nicht
    expect(ausnahmeSchalter(el).disabled).toBe(false);
    fertig();
    await warte(el);
    expect(ausnahmeSchalter(el).getAttribute("aria-busy")).toBe("false");
  });

  it("nicht verfügbare Person: alle Bedienelemente gesperrt", async () => {
    const hass = fakeHass((s) => {
      for (const eid of Object.keys(s)) {
        if (eid.includes("p1_")) {
          s[eid] = { entity_id: eid, state: "unavailable", attributes: {} };
        }
      }
    });
    const el = await karte(hass);
    const elemente = root(el).querySelectorAll(
      ".werte button:not(.verweis), .werte select, .werte input",
    ) as NodeListOf<HTMLButtonElement>;
    expect(elemente.length).toBe(10);
    for (const e of elemente) expect(e.disabled).toBe(true);
  });
});

describe("Bedienung Raum (B3)", () => {
  it("Standard-Favorit über select.select_option", async () => {
    const { hass, aufrufe } = bedienHass();
    const el = await karte(hass, { objekt: "r1" });
    waehle(el, ".favorit select", "SWR3");
    await warte(el);
    expect(aufrufe).toEqual([
      [
        "select",
        "select_option",
        { option: "SWR3" },
        { entity_id: "select.r1_standard_favorit" },
        false,
      ],
    ]);
  });
});

describe("Laufende Wecker bedienen (B3, E60, E78)", () => {
  it("Knopf „Wecken beenden“ drückt die Taste des Raums, ohne Rückfrage", async () => {
    const { hass, aufrufe } = bedienHass();
    const el = await karte(hass);
    const knopf = root(el).querySelector(
      ".laufend button.beenden",
    ) as HTMLButtonElement;
    expect(knopf.textContent).toContain("Wecken beenden");
    knopf.click();
    await warte(el);
    expect(aufrufe).toEqual([
      ["button", "press", {}, { entity_id: "button.r1_wecken_beenden" }, false],
    ]);
    // Die Auswahl bleibt, wo sie war
    expect(angezeigt(el)).toBe("Vater");
  });

  it("ohne Taste kein Knopf", async () => {
    const hass = fakeHass();
    delete hass.entities["button.r1_wecken_beenden"];
    const el = await karte(hass);
    expect(root(el).querySelector(".laufend button.beenden")).toBeNull();
    expect(text(el, ".laufend")).toContain("Schlafzimmer");
  });
});

describe("Fehleranzeige (E76)", () => {
  it("zeigt die Meldung von HA, Auswahl springt zurück, ✕ schließt", async () => {
    const { hass } = bedienHass({ code: "invalid", message: "Zu spät" });
    const el = await karte(hass);
    waehle(el, ".favorit select", "hr3");
    await warte(el);
    expect(text(el, ".fehler")).toContain("Zu spät");
    expect((root(el).querySelector(".favorit select") as HTMLSelectElement).value).toBe(
      "SWR3",
    );
    (root(el).querySelector(".fehler button") as HTMLButtonElement).click();
    await el.updateComplete;
    expect(root(el).querySelector(".fehler")).toBeNull();
  });

  it("Fehler ohne Meldung; die nächste gelungene Aktion räumt ihn weg", async () => {
    const { hass } = bedienHass("kaputt");
    const el = await karte(hass);
    ausnahmeSchalter(el).click();
    await warte(el);
    expect(text(el, ".fehler")).toContain("kaputt");
    hass.callService = () => Promise.resolve(undefined);
    ausnahmeSchalter(el).click();
    await warte(el);
    expect(root(el).querySelector(".fehler")).toBeNull();
  });

  it("ohne callService (altes HA) eine Fehlermeldung statt Absturz", async () => {
    const el = await karte();
    ausnahmeSchalter(el).click();
    await warte(el);
    expect(text(el, ".fehler")).toContain("Aktion fehlgeschlagen");
  });
});

describe("Einstellungs-Editor (E79)", () => {
  type Form = {
    schema: { name: string; selector: { device: { filter: unknown[] } } }[];
    computeLabel: (s: { name: string }) => string;
    computeHelper: (s: { name: string }) => string;
  };
  const form = () =>
    (
      customElements.get("homewake-card") as unknown as { getConfigForm: () => Form }
    ).getConfigForm();

  it("bietet ein Feld „objekt“ mit HomeWake-Personen und -Räumen", () => {
    const f = form();
    expect(f.schema[0]?.name).toBe("objekt");
    expect(f.schema[0]?.selector.device.filter).toEqual([
      { integration: "homewake", model: "Person" },
      { integration: "homewake", model: "Raum" },
    ]);
    document.documentElement.lang = "de";
    expect(f.computeLabel({ name: "objekt" })).toBe("Zuerst zeigen");
    expect(f.computeHelper({ name: "objekt" })).toContain("leer");
    document.documentElement.lang = "en";
    expect(f.computeLabel({ name: "objekt" })).toBe("Show first");
    expect(f.computeLabel({ name: "anders" })).toBe("anders");
    expect(f.computeHelper({ name: "anders" })).toBe("");
  });

  it("die Karte versteht die Geräte-ID aus dem Editor", async () => {
    expect(angezeigt(await karte(fakeHass(), { objekt: "d_r2" }))).toBe("Bad");
  });
});

describe("Minutentakt (E80)", () => {
  it("zeichnet jede Minute neu und hört beim Entfernen auf", async () => {
    vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] });
    vi.setSystemTime(JETZT);
    const el = await karte();
    const ende = () =>
      root(el).querySelectorAll(".tag")[0]?.querySelectorAll(".ereignis")[1];
    expect(ende()?.classList.contains("vergangen")).toBe(false);
    // Tagesende heute ist 20:00 UTC: danach ist es vergangen
    vi.setSystemTime(new Date("2026-07-14T20:00:30Z"));
    vi.advanceTimersByTime(60_000);
    await el.updateComplete;
    expect(ende()?.classList.contains("vergangen")).toBe(true);
    const anzahl = vi.getTimerCount();
    el.remove();
    expect(vi.getTimerCount()).toBe(anzahl - 1);
  });
});

describe("Review B3", () => {
  it("Uhrzeit: Tippen allein sendet nichts, erst Enter (Verlassen des Felds)", async () => {
    const { hass, aufrufe } = bedienHass();
    const el = await karte(hass);
    const uhr = root(el).querySelector(".ausnahme input") as HTMLInputElement;
    uhr.focus();
    uhr.value = "06:45";
    uhr.dispatchEvent(new Event("input"));
    uhr.dispatchEvent(new Event("change"));
    await warte(el);
    expect(aufrufe).toEqual([]);
    uhr.dispatchEvent(new KeyboardEvent("keydown", { key: "a" }));
    uhr.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));
    await warte(el);
    expect(aufrufe.map((a) => a[2])).toEqual([{ time: "06:45:00" }]);
  });

  it("Uhrzeit: nach einem Fehler wieder der Wert von HA", async () => {
    const { hass } = bedienHass({ message: "Nach dem Tagesende" });
    const el = await karte(hass);
    const uhr = root(el).querySelector(".ausnahme input") as HTMLInputElement;
    uhr.value = "23:30";
    uhr.dispatchEvent(new Event("blur"));
    await warte(el);
    expect(text(el, ".fehler")).toContain("Nach dem Tagesende");
    expect(uhr.value).toBe("08:00");
  });

  it("Auswahlliste mit unbekanntem Wert: Platzhalter, erste Option wählbar", async () => {
    const { hass, aufrufe } = bedienHass();
    const f = hass.states["select.p1_favorit"];
    if (f) f.state = "unknown";
    const el = await karte(hass);
    const liste = root(el).querySelector(".favorit select") as HTMLSelectElement;
    expect(liste.value).toBe("");
    expect(liste.options[0]?.textContent).toBe("–");
    waehle(el, ".favorit select", "kein_favorit");
    await warte(el);
    expect(aufrufe.map((a) => a[2])).toEqual([{ option: "kein_favorit" }]);
  });

  it("Licht/Radio: Name mit Profil für Screenreader, unbekannt = mixed", async () => {
    const el = await karte();
    const knoepfe = [...root(el).querySelectorAll(".profil button")];
    expect(knoepfe[2]?.getAttribute("aria-label")).toBe("Licht Frei");
    expect(knoepfe[4]?.getAttribute("aria-pressed")).toBe("mixed");
  });

  it("„Wecken beenden“: nicht verfügbare Taste gesperrt, Doppeldruck einmal", async () => {
    let anzahl = 0;
    const hass = fakeHass();
    hass.callService = () => {
      anzahl += 1;
      return new Promise(() => {});
    };
    const el = await karte(hass);
    const knopf = () => root(el).querySelector(".beenden") as HTMLButtonElement;
    knopf().click();
    knopf().click();
    await el.updateComplete;
    expect(anzahl).toBe(1);
    expect(knopf().getAttribute("aria-busy")).toBe("true");
    const s = hass.states["button.r1_wecken_beenden"];
    if (s) s.state = "unavailable";
    el.hass = { ...hass };
    await el.updateComplete;
    expect(knopf().disabled).toBe(true);
  });

  it("ein Fehler verschwindet auch nach einer gelungenen anderen Aktion (E76)", async () => {
    const { hass } = bedienHass("kaputt");
    const el = await karte(hass);
    ausnahmeSchalter(el).click();
    await warte(el);
    expect(root(el).querySelector(".fehler")).not.toBeNull();
    hass.callService = () => Promise.resolve(undefined);
    (root(el).querySelector(".profil button") as HTMLButtonElement).click();
    await warte(el);
    expect(root(el).querySelector(".fehler")).toBeNull();
  });
});
