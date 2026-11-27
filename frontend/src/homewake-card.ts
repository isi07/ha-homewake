// Dashboard-Karte von HomeWake (E59, E62): zeigt eine Person oder einen Raum,
// heute und morgen, laufende Wecker oben. Seit Phase B3 bedienbar, nur über
// HA-Standardaktionen der Entities (E59, E65, E74).
//
// Lit-Begriffe: Eine Karte ist ein eigenes HTML-Element („Web Component“).
// `render()` beschreibt mit `html\`…\`` das Aussehen; Lit zeichnet neu, wenn
// sich eine der `properties` ändert (z. B. `hass` bei jeder Zustandsänderung).

import { css, html, LitElement, nothing, type TemplateResult } from "lit";
import { live } from "lit/directives/live.js";
import {
  type Auswahl,
  findeObjekte,
  type LaufenderWecker,
  laufendeWecker,
  type Objekt,
  type PersonAnsicht,
  PLATTFORM,
  personAnsicht,
  type RaumAnsicht,
  raumAnsicht,
  type Schalter,
  type Tag,
  type Uhrzeit,
} from "./daten";
import type { Hass } from "./hass";
import { datum, type TextSchluessel, texte, uhrzeit } from "./texte";

export interface KartenConfig {
  type: string;
  /**
   * Person oder Raum, der zuerst gezeigt wird: ID des Untereintrags, Name
   * oder Geräte-ID (die liefert der Editor, E79).
   */
  objekt?: string;
}

type Texte = Record<TextSchluessel, string>;

/**
 * Ziel des Zahnrads (E65): die HomeWake-Seite. Dort hat jede Person und jeder
 * Raum ein eigenes Zahnrad für den „Konfigurieren“-Dialog; die Geräteseite
 * bietet ihn nicht an (geprüft auf HA 2026.11).
 */
const KONFIG_SEITE = "/config/integrations/integration/homewake";

/** Alle wie viele Millisekunden die Karte ohne Änderung in HA neu zeichnet (E80). */
const TAKT_MS = 60_000;

/** Zu einer Seite in HA wechseln, wie es HAs eigene Links tun. */
function navigiere(pfad: string): void {
  history.pushState(null, "", pfad);
  window.dispatchEvent(
    new CustomEvent("location-changed", { detail: { replace: false } }),
  );
}

/** Lesbare Meldung aus einem Fehler von HA (`{ code, message }`) oder sonstwas. */
function meldung(fehler: unknown): string {
  if (typeof fehler === "string") return fehler;
  const text = (fehler as { message?: unknown } | null)?.message;
  return typeof text === "string" ? text : "";
}

export class HomeWakeCard extends LitElement {
  static override properties = {
    hass: { attribute: false },
    _config: { state: true },
    _auswahl: { state: true },
    _fehler: { state: true },
    _laeuft: { state: true },
  };

  declare hass?: Hass;
  declare _config?: KartenConfig;
  /** Vom Nutzer gewählte Person bzw. gewählter Raum (ID); null = Vorgabe. */
  declare _auswahl: string | null;
  /** Meldung der zuletzt gescheiterten Aktion (E76); null = kein Fehler. */
  declare _fehler: string | null;
  /** Entities, für die gerade eine Aktion läuft (gesperrt, E75). */
  declare _laeuft: ReadonlySet<string>;
  /** Zuletzt gezeigte Person bzw. gezeigter Raum (für die Auswahlliste). */
  private _gezeigt: string | null = null;
  private _takt: ReturnType<typeof setInterval> | undefined;

  constructor() {
    super();
    this._auswahl = null;
    this._fehler = null;
    this._laeuft = new Set();
  }

  static getStubConfig(): Record<string, never> {
    return {};
  }

  /**
   * Einstellungs-Editor (E79): HA zeichnet das Formular selbst aus diesem
   * Schema. Die Geräteauswahl bietet nur HomeWake-Personen und -Räume an.
   */
  static getConfigForm(): {
    schema: unknown[];
    computeLabel: (s: { name: string }) => string;
    computeHelper: (s: { name: string }) => string;
  } {
    // Die Sprache von HA steht am <html>-Element (statisch gibt es kein `hass`)
    const t = () => texte(document.documentElement.lang || "en");
    return {
      schema: [
        {
          name: "objekt",
          selector: {
            device: {
              filter: [
                { integration: PLATTFORM, model: "Person" },
                { integration: PLATTFORM, model: "Raum" },
              ],
            },
          },
        },
      ],
      computeLabel: (s) => (s.name === "objekt" ? t().editor_objekt : s.name),
      computeHelper: (s) => (s.name === "objekt" ? t().editor_objekt_hilfe : ""),
    };
  }

  setConfig(config: KartenConfig): void {
    this._config = config;
    this._auswahl = null;
  }

  getCardSize(): number {
    return 6;
  }

  override connectedCallback(): void {
    super.connectedCallback();
    // Ohne Takt würde ein Wecker erst beim nächsten Update in HA blass (E80)
    this._takt = setInterval(() => this.requestUpdate(), TAKT_MS);
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    clearInterval(this._takt);
    this._takt = undefined;
  }

  private _aktiv(objekte: Objekt[]): Objekt | undefined {
    const wunsch = this._auswahl ?? this._config?.objekt;
    return (
      objekte.find(
        (o) => o.id === wunsch || o.geraetId === wunsch || o.name === wunsch,
      ) ?? objekte[0]
    );
  }

  private _waehle(id: string | null): void {
    if (id !== null) this._auswahl = id;
  }

  // ---------------------------------------------------------------- Aktionen

  /**
   * Eine HA-Standardaktion für eine Entity ausführen (E74). Die Karte zeigt
   * danach weiter, was HA meldet (E75); scheitert die Aktion, erscheint die
   * Meldung von HA in der Karte (E76).
   */
  private async _aktion(
    domain: string,
    service: string,
    entity: string,
    daten: Record<string, unknown> = {},
  ): Promise<void> {
    // Doppelklick: solange die Aktion läuft, nichts Neues schicken (E75)
    if (this._laeuft.has(entity)) return;
    this._laeuft = new Set([...this._laeuft, entity]);
    try {
      if (!this.hass?.callService) throw "";
      await this.hass.callService(domain, service, daten, { entity_id: entity }, false);
      this._fehler = null;
    } catch (fehler) {
      this._fehler = meldung(fehler);
    } finally {
      const rest = new Set(this._laeuft);
      rest.delete(entity);
      this._laeuft = rest;
    }
  }

  /** Nicht bedienbar (fehlt oder nicht verfügbar): `disabled`. */
  private _gesperrt(e: { entity: string | null; bedienbar: boolean }): boolean {
    return !e.bedienbar || e.entity === null;
  }

  /**
   * Aktion läuft: nur `aria-busy`, nicht `disabled`, damit das Element den
   * Tastaturfokus behält; ein zweiter Klick wird in `_aktion` ignoriert.
   */
  private _beschaeftigt(entity: string | null): "true" | "false" {
    return entity !== null && this._laeuft.has(entity) ? "true" : "false";
  }

  private _umschalten(s: Schalter): void {
    if (s.entity) void this._aktion("switch", s.an ? "turn_off" : "turn_on", s.entity);
  }

  // ---------------------------------------------------------------- Anzeige

  override render(): TemplateResult | typeof nothing {
    const hass = this.hass;
    if (!hass) return nothing;
    const t = texte(hass.locale.language);
    const objekte = findeObjekte(hass);
    const aktiv = this._aktiv(objekte);
    this._gezeigt = aktiv?.id ?? null;
    if (!aktiv) {
      return html`<ha-card><div class="leer">${t.leer}</div></ha-card>`;
    }
    const jetzt = new Date();
    const ansicht =
      aktiv.typ === "person"
        ? personAnsicht(hass, aktiv, objekte, jetzt)
        : raumAnsicht(hass, aktiv, objekte, jetzt);
    return html`<ha-card>
      ${this._laufend(laufendeWecker(hass, objekte), hass, t)} ${this._fehlerZeile(t)}
      <div class="kopf">
        <select
          class="name"
          aria-label=${t.auswahl}
          @change=${(e: Event) => this._waehle((e.target as HTMLSelectElement).value)}
        >
          ${objekte.map((o) => html`<option value=${o.id}>${o.name}</option>`)}
        </select>
        <span class="pille ${ansicht.wach ? "an" : ""}"
          >${ansicht.wach === null ? "–" : ansicht.wach ? t.wach : t.schlaeft}</span
        >
        <button
          class="zahnrad"
          title=${t.einstellungen}
          aria-label=${t.einstellungen}
          @click=${() => navigiere(KONFIG_SEITE)}
        >
          <ha-icon icon="mdi:cog"></ha-icon>
        </button>
      </div>
      ${ansicht.verfuegbar ? nothing : html`<div class="hinweis">${t.nicht_verfuegbar}</div>`}
      <div class="tage">
        ${this._tag(ansicht.tage[0], t.heute, hass)} ${this._tag(ansicht.tage[1], t.morgen, hass)}
      </div>
      ${ansicht.typ === "person" ? this._person(ansicht, t) : this._raum(ansicht, t)}
    </ha-card>`;
  }

  override updated(): void {
    // Die Auswahlliste nach jedem Zeichnen auf das Gezeigte stellen; ein
    // `selected` an den Optionen geht beim Einfügen neuer Optionen verloren.
    const auswahl = this.renderRoot.querySelector(
      "select.name",
    ) as HTMLSelectElement | null;
    if (auswahl && this._gezeigt !== null) auswahl.value = this._gezeigt;
  }

  private _laufend(
    laufend: LaufenderWecker[],
    hass: Hass,
    t: Texte,
  ): TemplateResult | typeof nothing {
    if (laufend.length === 0) return nothing;
    const zeit = (d: Date) => uhrzeit(d, hass.locale.language, hass.config.time_zone);
    return html`<div class="laufend">
      ${laufend.map(
        (w) => html`<div class="zeile">
          <ha-icon icon="mdi:alarm"></ha-icon>
          <button class="raumname" @click=${() => this._waehle(w.raum.id)}>
            ${w.raum.name}
          </button>
          <span class="bis">${t.weckt_bis} ${zeit(w.bis)}</span>
          ${this._beenden(w.taste, t)}
        </div>`,
      )}
    </div>`;
  }

  /** Knopf „Wecken beenden“: drückt die Taste des Raums, ohne Rückfrage (E60, E78). */
  private _beenden(
    taste: LaufenderWecker["taste"],
    t: Texte,
  ): TemplateResult | typeof nothing {
    if (taste === null) return nothing;
    return html`<button
      class="beenden"
      ?disabled=${!taste.bedienbar}
      aria-busy=${this._beschaeftigt(taste.entity)}
      @click=${() => this._aktion("button", "press", taste.entity)}
    >
      <ha-icon icon="mdi:alarm-off"></ha-icon>${t.wecken_beenden}
    </button>`;
  }

  private _fehlerZeile(t: Texte): TemplateResult | typeof nothing {
    if (this._fehler === null) return nothing;
    return html`<div class="fehler" role="alert">
      <ha-icon icon="mdi:alert-circle"></ha-icon>
      <span>${t.fehler}${this._fehler ? `: ${this._fehler}` : ""}</span>
      <button
        title=${t.schliessen}
        aria-label=${t.schliessen}
        @click=${() => {
          this._fehler = null;
        }}
      >
        ✕
      </button>
    </div>`;
  }

  private _tag(tag: Tag, wann: string, hass: Hass): TemplateResult {
    const t = texte(hass.locale.language);
    const sprache = hass.locale.language;
    const zone = hass.config.time_zone;
    return html`<div class="tag">
      <div class="tagkopf">
        <span class="wann">${wann}</span>
        <span class="datum">${tag.datum ? datum(tag.datum, sprache, zone) : ""}</span>
        ${
          tag.status
            ? html`<span class="status">${tag.status}${tag.grund ? ` · ${tag.grund}` : ""}</span>`
            : nothing
        }
      </div>
      ${tag.ereignisse.map(
        (e) => html`<div
          class="ereignis ${e.vergangen ? "vergangen" : ""} ${e.naechster ? "naechster" : ""}"
        >
          <span>${t[e.art]}</span><span>${uhrzeit(e.zeit, sprache, zone)}</span>
        </div>`,
      )}
    </div>`;
  }

  private _verweis(name: string, id: string | null): TemplateResult {
    return id === null
      ? html`<span>${name}</span>`
      : html`<button class="verweis" @click=${() => this._waehle(id)}>${name}</button>`;
  }

  // ---------------------------------------------------------------- Bedienelemente

  /** Licht bzw. Radio eines Profils als Umschalt-Knopf. */
  private _knopf(s: Schalter, text: string, profil: string, t: Texte): TemplateResult {
    const klasse = s.an === null ? "unbekannt" : s.an ? "an" : "aus";
    // Zustand auch als Text (Tooltip), nicht nur als Stil
    const zustand = s.an === null ? "–" : s.an ? t.an : t.aus;
    // Screenreader: „Licht Frei“, Zustand über aria-pressed („mixed“ = unbekannt)
    return html`<button
      class="knopf ${klasse}"
      title="${text}: ${zustand}"
      aria-label="${text} ${profil}"
      aria-pressed=${s.an === null ? "mixed" : s.an ? "true" : "false"}
      aria-busy=${this._beschaeftigt(s.entity)}
      ?disabled=${this._gesperrt(s)}
      @click=${() => this._umschalten(s)}
    >
      ${text}
    </button>`;
  }

  /** Schalter an/aus (Ausnahme). */
  private _schalter(s: Schalter, text: string, t: Texte): TemplateResult {
    const zustand = s.an === null ? "–" : s.an ? t.an : t.aus;
    return html`<button
      class="schalter ${s.an ? "an" : ""}"
      role="switch"
      aria-checked=${s.an ? "true" : "false"}
      aria-label=${text}
      title="${text}: ${zustand}"
      aria-busy=${this._beschaeftigt(s.entity)}
      ?disabled=${this._gesperrt(s)}
      @click=${() => this._umschalten(s)}
    >
      <span class="griff"></span>
    </button>`;
  }

  /**
   * Uhrzeitfeld (E77). Gesendet wird erst beim Verlassen des Felds oder mit
   * Enter, nicht bei jedem `change`: Browser melden beim Tippen schon nach der
   * ersten Ziffer eine gültige Uhrzeit. Ein geleertes Feld wird ignoriert.
   * Ohne `live`: ein Neuzeichnen während der Eingabe überschreibt sie nicht.
   */
  private _uhrzeit(u: Uhrzeit, text: string): TemplateResult {
    const zurueck = (feld: HTMLInputElement) => {
      feld.value = u.wert ?? "";
    };
    const senden = async (e: Event) => {
      const feld = e.target as HTMLInputElement;
      const wert = feld.value;
      if (!wert || wert === u.wert || u.entity === null) {
        zurueck(feld);
        return;
      }
      await this._aktion("time", "set_value", u.entity, { time: `${wert}:00` });
      // Gescheitert: wieder den Wert von HA zeigen (E76)
      if (this._fehler !== null) zurueck(feld);
    };
    return html`<input
      type="time"
      aria-label=${text}
      .value=${u.wert ?? ""}
      aria-busy=${this._beschaeftigt(u.entity)}
      ?disabled=${this._gesperrt(u)}
      @blur=${senden}
      @keydown=${(e: KeyboardEvent) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
      }}
    />`;
  }

  /** Auswahlliste (Raum, Favorit, Standard-Favorit). */
  private _liste(a: Auswahl, text: string): TemplateResult {
    const geaendert = (e: Event) => {
      const wert = (e.target as HTMLSelectElement).value;
      if (wert === a.wert || a.entity === null) return;
      void this._aktion("select", "select_option", a.entity, { option: wert });
    };
    // `live`: nach einem Fehler springt die Liste auf den Wert von HA zurück.
    // Unbekannter Wert: Platzhalter „–“, sonst zeigte die Liste die erste
    // Option an, und genau die ließe sich dann nicht wählen.
    return html`<select
      class="liste"
      aria-label=${text}
      aria-busy=${this._beschaeftigt(a.entity)}
      ?disabled=${this._gesperrt(a)}
      @change=${geaendert}
    >
      ${
        a.wert === null
          ? html`<option value="" disabled .selected=${live(true)}>–</option>`
          : nothing
      }
      ${a.optionen.map(
        (o) =>
          html`<option value=${o.wert} .selected=${live(o.wert === a.wert)}>${o.text}</option>`,
      )}
    </select>`;
  }

  private _person(a: PersonAnsicht, t: Texte): TemplateResult {
    const ziel = a.raum?.id ? a.raum : null;
    return html`<div class="werte">
      <div class="raum">
        <span class="label">${t.raum}</span>
        ${this._liste(a.raumAuswahl, t.raum)}
        ${
          ziel
            ? html`<button
              class="verweis"
              title="${t.zum_raum} ${ziel.name}"
              aria-label="${t.zum_raum} ${ziel.name}"
              @click=${() => this._waehle(ziel.id)}
            >
              <ha-icon icon="mdi:arrow-right"></ha-icon>
            </button>`
            : nothing
        }
      </div>
      <div class="ausnahme">
        <span class="label">${t.ausnahme}</span>
        ${this._schalter(a.ausnahme.schalter, t.ausnahme, t)}
        ${this._uhrzeit(a.ausnahme.zeit, t.ausnahme_zeit)}
      </div>
      ${a.profile.map(
        (p) => html`<div class="profil">
          <span class="label">${t[p.profil]}</span>
          ${this._knopf(p.licht, t.licht, t[p.profil], t)}
          ${this._knopf(p.radio, t.radio, t[p.profil], t)}
        </div>`,
      )}
      <div class="favorit">
        <span class="label">${t.favorit}</span>${this._liste(a.favorit, t.favorit)}
      </div>
    </div>`;
  }

  private _raum(a: RaumAnsicht, t: Texte): TemplateResult {
    return html`<div class="werte">
      <div>
        <span class="label">${t.tag}/${t.nacht}</span>
        <span>${a.tag === null ? "–" : a.tag ? t.tag : t.nacht}</span>
      </div>
      <div><span class="label">${t.quelle}</span><span>${a.quelle ?? "–"}</span></div>
      <div class="personen">
        <span class="label">${t.personen}</span>
        ${
          a.personen.length === 0
            ? html`<span>${t.niemand}</span>`
            : a.personen.map((p) => this._verweis(p.name, p.id))
        }
      </div>
      ${
        a.favorit === null
          ? nothing
          : html`<div class="favorit">
            <span class="label">${t.standard_favorit}</span>
            ${this._liste(a.favorit, t.standard_favorit)}
          </div>`
      }
    </div>`;
  }

  static override styles = css`
    :host {
      display: block;
    }
    ha-card {
      /* Maßgeblich ist die Breite der Karte, nicht des Bildschirms (E62) */
      container-type: inline-size;
      padding: 10px 12px 12px;
    }
    button {
      font: inherit;
      color: inherit;
      background: none;
      border: none;
      padding: 0;
      cursor: pointer;
    }
    button:disabled {
      cursor: default;
    }
    .leer,
    .hinweis {
      color: var(--secondary-text-color);
    }
    /* Laufende Wecker: Balken mit Knopf „Wecken beenden“ (B3) */
    .laufend {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin-bottom: 8px;
    }
    .laufend .zeile {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 4px 8px;
      padding: 6px 6px 6px 10px;
      border-radius: 8px;
      background: var(--warning-color, #ffa600);
      color: var(--text-primary-color, #fff);
    }
    .laufend .raumname {
      font-weight: 600;
      text-decoration: underline;
    }
    .laufend .bis {
      flex: 1;
      white-space: nowrap;
    }
    .laufend .beenden {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      min-height: 36px;
      padding: 0 12px;
      border-radius: 18px;
      background: var(--card-background-color, #fff);
      color: var(--warning-color, #ffa600);
      font-weight: 700;
      margin-left: auto;
    }
    .laufend .beenden:disabled {
      opacity: 0.6;
    }
    .fehler {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      margin-bottom: 8px;
      border-radius: 8px;
      background: var(--error-color, #db4437);
      color: var(--text-primary-color, #fff);
    }
    .fehler span {
      flex: 1;
      min-width: 0;
      overflow-wrap: anywhere;
    }
    .fehler button {
      min-width: 32px;
      min-height: 32px;
    }
    .kopf {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .kopf .name {
      flex: 1;
      min-width: 0;
      font: inherit;
      font-size: 1.2em;
      font-weight: 500;
      color: var(--primary-text-color);
      background: none;
      border: none;
      padding: 4px 0;
    }
    .pille {
      padding: 2px 10px;
      border-radius: 999px;
      font-size: 0.85em;
      background: var(--secondary-background-color, #e0e0e0);
      color: var(--secondary-text-color);
    }
    .pille.an {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .zahnrad {
      color: var(--secondary-text-color);
      min-width: 32px;
      min-height: 32px;
    }
    .tage {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin: 8px 0 10px;
    }
    @container (max-width: 280px) {
      .tage {
        grid-template-columns: 1fr;
      }
      /* Beschriftung über dem Element, damit Liste und Pfeil in eine Zeile passen */
      .werte .label {
        flex-basis: 100%;
      }
      .werte .liste {
        flex: 1 1 0;
      }
    }
    .tag {
      border: 1px solid var(--divider-color);
      border-radius: 8px;
      padding: 6px 8px;
      font-size: 0.9em;
      min-width: 0;
    }
    .tagkopf {
      display: flex;
      flex-wrap: wrap;
      gap: 0 6px;
      margin-bottom: 4px;
    }
    .wann {
      font-weight: 600;
    }
    .datum,
    .status {
      color: var(--secondary-text-color);
    }
    .status {
      flex-basis: 100%;
    }
    .ereignis {
      display: flex;
      justify-content: space-between;
      gap: 4px;
    }
    .ereignis span:first-child {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .ereignis.vergangen {
      opacity: 0.45;
    }
    .ereignis.naechster {
      font-weight: 700;
    }
    .werte > div {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 4px 8px;
      padding: 2px 0;
      min-height: 36px;
    }
    .label {
      min-width: 8em;
      color: var(--secondary-text-color);
    }
    /* Bedienelemente in HA-Farben (E74) */
    .liste,
    input[type="time"] {
      font: inherit;
      color: var(--primary-text-color);
      background: var(--secondary-background-color, #f0f0f0);
      border: 1px solid var(--divider-color);
      border-radius: 6px;
      min-height: 32px;
      padding: 0 6px;
      box-sizing: border-box;
    }
    .liste {
      flex: 1 1 8em;
      min-width: 0;
      max-width: 100%;
    }
    .liste:disabled,
    input[type="time"]:disabled,
    .knopf:disabled,
    .schalter:disabled {
      opacity: 0.4;
    }
    .knopf {
      min-height: 32px;
      min-width: 4.5em;
      padding: 0 10px;
      border-radius: 16px;
      border: 1px solid var(--divider-color);
    }
    .knopf.an {
      background: var(--primary-color);
      border-color: var(--primary-color);
      color: var(--text-primary-color, #fff);
      font-weight: 500;
    }
    .knopf.aus {
      color: var(--secondary-text-color);
      text-decoration: line-through;
    }
    .knopf.unbekannt {
      color: var(--secondary-text-color);
      font-style: italic;
    }
    .schalter {
      position: relative;
      width: 44px;
      height: 24px;
      border-radius: 12px;
      background: var(--switch-unchecked-track-color, #9e9e9e);
      flex: none;
    }
    .schalter .griff {
      position: absolute;
      top: 3px;
      left: 3px;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: #fff;
      transition: left 0.15s;
    }
    .schalter.an {
      background: var(--primary-color);
    }
    .schalter.an .griff {
      left: 23px;
    }
    .verweis {
      color: var(--primary-color);
      text-decoration: underline;
    }
    .raum .verweis {
      min-width: 32px;
      min-height: 32px;
      text-decoration: none;
    }
  `;
}

if (!customElements.get("homewake-card")) {
  customElements.define("homewake-card", HomeWakeCard);
}

// Eintrag in der Kartenauswahl von HA („Karte hinzufügen“)
// (nur einmal, auch wenn die Datei zusätzlich als Ressource eingetragen ist)
const fenster = window as unknown as {
  customCards?: { type: string; [schluessel: string]: unknown }[];
};
fenster.customCards = fenster.customCards ?? [];
if (!fenster.customCards.some((k) => k.type === "homewake-card")) {
  fenster.customCards.push({
    type: "homewake-card",
    name: "HomeWake",
    description:
      "Weckzeiten einer Person oder eines Raums, heute und morgen, mit Bedienung",
    preview: false,
  });
}
