// Die Teile des HA-Frontend-Objekts `hass`, die die Karte liest (E70).
// HA liefert dazu keine offiziellen Typen; die Felder stammen aus dem
// HA-Frontend (Entity- und Geräte-Registry, Zustände, Formatierung).

export interface HassEntityState {
  entity_id: string;
  state: string;
  attributes: Record<string, unknown>;
}

/** Eintrag der Entity-Registry, wie ihn das Frontend kennt. */
export interface HassEntityEintrag {
  entity_id: string;
  device_id?: string | null;
  platform?: string;
  translation_key?: string | null;
}

/** Eintrag der Geräte-Registry, wie ihn das Frontend kennt. */
export interface HassGeraet {
  id: string;
  name: string | null;
  name_by_user?: string | null;
  model?: string | null;
  identifiers?: [string, string][];
}

export interface Hass {
  states: Record<string, HassEntityState | undefined>;
  entities: Record<string, HassEntityEintrag | undefined>;
  devices: Record<string, HassGeraet | undefined>;
  locale: { language: string };
  config: { time_zone: string };
  /**
   * Übersetzter Zustand, z. B. „Werktag“ oder der Raumname. Mit `wert` wird
   * statt des aktuellen Zustands dieser Wert übersetzt (z. B. eine Option).
   */
  formatEntityState?: (state: HassEntityState, wert?: string) => string;
  /**
   * HA-Aktion ausführen (B3, E74). `melden = false` unterdrückt HAs eigene
   * Fehlermeldung, weil die Karte Fehler selbst anzeigt (E76). Scheitert die
   * Aktion, wird das Promise mit einem Objekt `{ code, message }` abgelehnt.
   */
  callService?: (
    domain: string,
    service: string,
    daten?: Record<string, unknown>,
    ziel?: { entity_id: string },
    melden?: boolean,
  ) => Promise<unknown>;
  /** Übersetzter Attributwert, z. B. Grund „Montag“. */
  formatEntityAttributeValue?: (state: HassEntityState, attribut: string) => string;
}
