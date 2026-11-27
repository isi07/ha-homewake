"""Config Flow für HomeWake (Einrichtung über die HA-Oberfläche).

Der Haupteintrag steht für das Haus. Personen werden als Untereinträge
(Subentries) angelegt und geändert (ARCHITEKTUR.md 3.1, 3.6, 5.4).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, override

import probatio
from homeassistant import data_entry_flow
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentry,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.field_visibility import (
    ConditionOperator,
    FieldCondition,
)
from homeassistant.helpers.selector import (
    AreaSelector,
    BooleanSelector,
    CountrySelector,
    CountrySelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TimeSelector,
)
from homeassistant.helpers.translation import async_get_translations

from . import feiertage
from .anbieter import ANBIETER, Anbieter, AnbieterFehler
from .const import (
    CONF_BEREICH,
    CONF_BUNDESLAND,
    CONF_DAUER,
    CONF_ELEVATION,
    CONF_GRAD_ABEND,
    CONF_GRAD_MORGEN,
    CONF_HELLIGKEIT,
    CONF_KLEMM_BEGINN,
    CONF_KLEMM_ENDE,
    CONF_LAND,
    CONF_LAUTSPRECHER,
    CONF_LAUTSTAERKE,
    CONF_LICHTER,
    CONF_NAME,
    CONF_SCHULE,
    CONF_SONNE_ABEND,
    CONF_SONNE_MORGEN,
    CONF_URLAUBSKALENDER,
    CONF_ZEITPLAN,
    CONF_ZUORDENBAR,
    DOMAIN,
    NAME,
    SUBENTRY_PERSON,
    SUBENTRY_RAUM,
)
from .logic.eingabe import BEGINN, ENDE, STANDARD, WOCHENTAGE, pruefe_zeitplan
from .logic.schulferien import schul_pfad
from .logic.sonnenstand import (
    FREI,
    FREI_MAX,
    FREI_MIN,
    SONNENSTAENDE,
    STANDARD_SONNENSTAND,
)

FEHLER_NAME_VERGEBEN = "name_vergeben"
KEIN_RAUM = "kein_raum"  # reservierter Wert der Raum-Auswahl


class HomeWakeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einrichtungsdialog für HomeWake.

    Es gibt nur einen Eintrag pro HA-Instanz (``single_config_entry`` im
    Manifest). Personen kommen als Untereinträge dazu.
    """

    VERSION = 1

    def __init__(self) -> None:
        """Merkt sich Land und Region zwischen den Schritten."""
        self._land = ""
        self._region: str | None = None

    async def _land_schema(self, vorschlag: str | None) -> probatio.Schema:
        """Formular: Land (für Feiertage), vorbelegt."""
        laender = await self.hass.async_add_executor_job(feiertage.laender)
        schema = probatio.Schema(
            {
                probatio.Required(CONF_LAND): CountrySelector(
                    CountrySelectorConfig(countries=laender)
                )
            }
        )
        return self.add_suggested_values_to_schema(schema, {CONF_LAND: vorschlag})

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Schritt 1 beim Einrichten: Land für die Feiertage (3.5, E9)."""
        if user_input is not None:
            self._land = user_input[CONF_LAND]
            return await self.async_step_region()
        return self.async_show_form(
            step_id="user",
            data_schema=await self._land_schema(self.hass.config.country),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Land und Bundesland ändern."""
        if user_input is not None:
            self._land = user_input[CONF_LAND]
            return await self.async_step_region()
        land = self._get_reconfigure_entry().data.get(CONF_LAND)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=await self._land_schema(land or self.hass.config.country),
        )

    async def async_step_region(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Schritt 2: Region (z. B. Bundesland), falls das Land welche hat."""
        regionen = await self.hass.async_add_import_executor_job(
            feiertage.regionen, self._land
        )
        if user_input is None and regionen:
            vorschlag: dict[str, Any] = {}
            if self.source == SOURCE_RECONFIGURE:
                alt = self._get_reconfigure_entry().data
                # Alte Region nur vorschlagen, wenn das Land gleich blieb.
                if (
                    alt.get(CONF_LAND) == self._land
                    and alt.get(CONF_BUNDESLAND) in regionen
                ):
                    vorschlag[CONF_BUNDESLAND] = alt.get(CONF_BUNDESLAND)
            schema = probatio.Schema(
                {
                    probatio.Optional(CONF_BUNDESLAND): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=code, label=name)
                                for code, name in regionen.items()
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            )
            return self.async_show_form(
                step_id="region",
                data_schema=self.add_suggested_values_to_schema(schema, vorschlag),
            )
        self._region = (user_input or {}).get(CONF_BUNDESLAND) or None
        return await self.async_step_sonne()

    async def async_step_sonne(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Schritt 3: Sonnenstand für Dawn (morgens) und Dusk (abends), E30."""
        if user_input is not None:
            daten: dict[str, Any] = {
                CONF_LAND: self._land,
                CONF_BUNDESLAND: self._region,
            }
            for wahl_feld, grad_feld in (
                (CONF_SONNE_MORGEN, CONF_GRAD_MORGEN),
                (CONF_SONNE_ABEND, CONF_GRAD_ABEND),
            ):
                wahl = user_input.get(wahl_feld) or STANDARD_SONNENSTAND
                frei = user_input.get(grad_feld)
                daten[wahl_feld] = wahl
                daten[grad_feld] = (
                    float(frei) if wahl == FREI and frei is not None else None
                )
            if self.source == SOURCE_RECONFIGURE:
                return self.async_update_and_abort(
                    self._get_reconfigure_entry(), data=daten
                )
            return self.async_create_entry(title=NAME, data=daten)
        vorschlag: dict[str, Any] = {}
        if self.source == SOURCE_RECONFIGURE:
            vorschlag = dict(self._get_reconfigure_entry().data)
        return self.async_show_form(
            step_id="sonne",
            data_schema=self.add_suggested_values_to_schema(_sonne_schema(), vorschlag),
        )

    @classmethod
    @callback
    @override
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Untereinträge, die HomeWake anbietet."""
        return {SUBENTRY_PERSON: PersonSubentryFlow, SUBENTRY_RAUM: RaumSubentryFlow}


def _sonne_schema() -> probatio.Schema:
    """Formular: Sonnenstand morgens/abends; Gradfeld nur bei „frei wählen“."""
    auswahl = SelectSelector(
        SelectSelectorConfig(
            options=[*SONNENSTAENDE, FREI],
            mode=SelectSelectorMode.DROPDOWN,
            translation_key="sonnenstand",
        )
    )
    zahl = NumberSelector(
        NumberSelectorConfig(
            min=FREI_MIN,
            max=FREI_MAX,
            step=0.5,
            unit_of_measurement="°",
            mode=NumberSelectorMode.BOX,
        )
    )
    schema: dict[Any, Any] = {}
    for wahl_feld, grad_feld in (
        (CONF_SONNE_MORGEN, CONF_GRAD_MORGEN),
        (CONF_SONNE_ABEND, CONF_GRAD_ABEND),
    ):
        schema[probatio.Optional(wahl_feld, default=STANDARD_SONNENSTAND)] = auswahl
        schema[
            data_entry_flow.Required(
                grad_feld, visible={"field": wahl_feld, "value": FREI}
            )
        ] = zahl
    return probatio.Schema(schema)


def _zeitplan_schema() -> dict[Any, Any]:
    """Abschnitte des Zeitplans: Standard (Pflicht) und sieben Wochentage."""
    schema: dict[Any, Any] = {
        probatio.Required(STANDARD): data_entry_flow.section(
            probatio.Schema(
                {
                    # Optional, damit die eigene, verständliche Meldung
                    # „standard_pflicht“ erscheint statt eines allgemeinen Fehlers.
                    probatio.Optional(BEGINN): TimeSelector(),
                    probatio.Optional(ENDE): TimeSelector(),
                }
            ),
            {"collapsed": False},
        )
    }
    for tag in WOCHENTAGE:
        schema[probatio.Optional(tag)] = data_entry_flow.section(
            probatio.Schema(
                {
                    probatio.Optional(BEGINN): TimeSelector(),
                    probatio.Optional(ENDE): TimeSelector(),
                }
            ),
            {"collapsed": True},
        )
    return schema


# Feld „Schulferien“ im Personen-Dialog (E40)
CONF_SCHULFERIEN = "schulferien"
SCHULE_KEINE = "keine"
SCHULE_WAEHLEN = "waehlen"
SCHULE_BEHALTEN = "behalten"
OHNE_SCHULE = "ohne_schule"  # Schulwahl abbrechen, wenn die Seite nicht antwortet
FEHLER_KEINE_VERBINDUNG = "keine_verbindung"
FEHLER_LEER = "leer"
CONF_ANBIETER = "anbieter"


def _person_schema(wahl: list[SelectOptionDict]) -> probatio.Schema:
    """Formular: Name, Urlaubskalender, Schulferien (3.6, E40), Zeitplan.

    ``wahl`` sind die Optionen für „Schulferien“ (``_schul_optionen``); die
    erste ist vorgewählt.
    """
    return probatio.Schema(
        {
            probatio.Required(CONF_NAME): TextSelector(),
            probatio.Optional(CONF_URLAUBSKALENDER): EntitySelector(
                EntitySelectorConfig(domain="calendar")
            ),
            probatio.Required(
                CONF_SCHULFERIEN, default=wahl[0]["value"]
            ): SelectSelector(
                SelectSelectorConfig(options=wahl, mode=SelectSelectorMode.LIST)
            ),
        }
        | _zeitplan_schema()
    )


def _person_daten(
    user_input: Mapping[str, Any], zeitplan: dict[str, dict[str, str]]
) -> dict[str, Any]:
    """Gespeicherte Personen-Daten; der Kalender nur, wenn einer gewählt ist.

    Die Schule kommt erst beim Speichern dazu (``_speichern``).
    """
    daten: dict[str, Any] = {CONF_ZEITPLAN: zeitplan}
    if kalender := user_input.get(CONF_URLAUBSKALENDER):
        daten[CONF_URLAUBSKALENDER] = kalender
    return daten


def _zeitplan_daten(user_input: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Zeitplan aus den Formulardaten: alle acht Abschnitte, leere Felder entfernt."""
    daten: dict[str, dict[str, str]] = {}
    for abschnitt in (STANDARD, *WOCHENTAGE):
        werte = user_input.get(abschnitt) or {}
        daten[abschnitt] = {k: v for k, v in werte.items() if k in (BEGINN, ENDE) and v}
    return daten


class PersonSubentryFlow(ConfigSubentryFlow):
    """Dialog „Person hinzufügen“ und „Person ändern“.

    Wird „Schule wählen“ angekreuzt, folgen der Schritt „Anbieter“ und dessen
    Auswahlstufen, bei mehr-schulferien.de Bundesland → Landkreis → Ort →
    Schule (E40, E44); gespeichert wird erst nach dem letzten Schritt.
    """

    def __init__(self) -> None:
        """Merkt sich die Eingaben des ersten Schritts für die Schulwahl."""
        super().__init__()
        self._titel = ""
        self._daten: dict[str, Any] = {}
        self._schule_alt: dict[str, Any] | None = None
        self._namen: dict[str, str] = {}  # Liste der angezeigten Stufe
        self._auswahl: str | None = None  # ihr Filter (Wahl der vorigen Stufe)
        self._gewaehlt: dict[str, str] = {}  # Stufe → gewählter Name
        self._anbieter: Anbieter | None = None
        self._anbieter_id = ""

    def _speichern(self, schule: Mapping[str, Any] | None) -> SubentryFlowResult:
        """Person anlegen bzw. ändern, mit oder ohne Schule."""
        daten = dict(self._daten)
        if schule:
            daten[CONF_SCHULE] = dict(schule)
        if self.source == SOURCE_RECONFIGURE:
            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                title=self._titel,
                data=daten,
            )
        return self.async_create_entry(title=self._titel, data=daten)

    async def _weiter(
        self, user_input: Mapping[str, Any], zeitplan: dict[str, dict[str, str]]
    ) -> SubentryFlowResult:
        """Nach dem ersten Schritt: speichern oder zur Schulwahl."""
        self._titel = user_input[CONF_NAME].strip()
        self._daten = _person_daten(user_input, zeitplan)
        wahl = user_input.get(CONF_SCHULFERIEN, SCHULE_KEINE)
        if wahl == SCHULE_WAEHLEN:
            return await self.async_step_anbieter()
        return self._speichern(self._schule_alt if wahl == SCHULE_BEHALTEN else None)

    async def async_step_anbieter(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Schulwahl: Anbieter der Schulferien (E44), dann dessen Stufen."""
        if user_input is not None:
            self._anbieter_id = user_input[CONF_ANBIETER]
            self._anbieter = ANBIETER[self._anbieter_id]
            self._gewaehlt = {}
            return await self._stufe(self._anbieter.stufen[0], None, None)
        return self.async_show_form(
            step_id="anbieter",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_ANBIETER): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=schluessel, label=a.titel)
                                for schluessel, a in ANBIETER.items()
                            ],
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def _stufe(
        self, stufe: str, user_input: dict[str, Any] | None, auswahl: str | None
    ) -> SubentryFlowResult:
        """Eine Auswahlstufe des Anbieters: Liste laden und anzeigen, Wahl übernehmen.

        ``auswahl`` ist die Wahl der vorigen Stufe (Filter der Liste). Antwortet
        der Anbieter nicht, kann der Nutzer es erneut versuchen oder die
        Schulwahl abbrechen (beim Ändern bleibt dann die bisherige Schule).
        """
        anbieter = self._anbieter
        assert anbieter is not None  # nur nach dem Schritt „anbieter“ erreichbar
        stufen = anbieter.stufen
        self._auswahl = auswahl
        if user_input is not None and user_input.get(OHNE_SCHULE):
            return self._speichern(self._schule_alt)
        if user_input is not None and stufe in user_input:
            wahl = user_input[stufe]
            # Namen merken: der ganze Auswahlweg wird mit der Schule angezeigt
            self._gewaehlt[stufe] = self._namen.get(wahl, wahl)
            if stufe == stufen[-1]:
                return self._speichern(
                    {
                        "anbieter": self._anbieter_id,
                        "kennung": wahl,
                        "name": self._gewaehlt[stufe],
                        "pfad": [
                            *anbieter.pfad_anfang,
                            *(self._gewaehlt[s] for s in stufen[:-1]),
                        ],
                    }
                )
            return await self._stufe(stufen[stufen.index(stufe) + 1], None, wahl)
        try:
            self._namen = await anbieter.liste(self.hass, stufe, auswahl)
        except AnbieterFehler:
            fehler = FEHLER_KEINE_VERBINDUNG
        else:
            fehler = "" if self._namen else FEHLER_LEER
        if fehler:
            # Formular ohne Liste: „erneut versuchen“ (absenden) oder abbrechen
            return self.async_show_form(
                step_id=stufe,
                data_schema=probatio.Schema(
                    {probatio.Optional(OHNE_SCHULE, default=False): BooleanSelector()}
                ),
                errors={"base": fehler},
                description_placeholders={"anbieter": anbieter.titel},
            )
        return self.async_show_form(
            step_id=stufe,
            data_schema=probatio.Schema(
                {
                    probatio.Required(stufe): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=kennung, label=name)
                                for kennung, name in self._namen.items()
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    # Auswahlstufen der Anbieter. HA ruft Schritte über ihren Namen auf; jede
    # Stufe eines Anbieters braucht darum hier eine Methode (und Übersetzungen).

    async def async_step_bundesland(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """mehr-schulferien.de 1: Bundesland."""
        return await self._stufe("bundesland", user_input, self._auswahl)

    async def async_step_kreis(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """mehr-schulferien.de 2: Landkreis bzw. kreisfreie Stadt."""
        return await self._stufe("kreis", user_input, self._auswahl)

    async def async_step_ort(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """mehr-schulferien.de 3: Ort."""
        return await self._stufe("ort", user_input, self._auswahl)

    async def async_step_schule(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """mehr-schulferien.de 4: Schule."""
        return await self._stufe("schule", user_input, self._auswahl)

    def _name_vergeben(self, name: str, *, ausser: str | None = None) -> bool:
        """Ob schon eine andere Person diesen Namen trägt (Groß/Klein egal)."""
        vergleich = name.strip().casefold()
        return any(
            sub.subentry_type == SUBENTRY_PERSON
            and sub.subentry_id != ausser
            and sub.title.strip().casefold() == vergleich
            for sub in self._get_entry().subentries.values()
        )

    def _pruefe(
        self, user_input: Mapping[str, Any], *, ausser: str | None = None
    ) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
        """Fehler und aufbereitete Zeitplan-Daten zu den Formulareingaben."""
        zeitplan = _zeitplan_daten(user_input)
        fehler = pruefe_zeitplan(zeitplan)
        if self._name_vergeben(user_input[CONF_NAME], ausser=ausser):
            fehler[CONF_NAME] = FEHLER_NAME_VERGEBEN
        return fehler, zeitplan

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Neue Person: Name, Urlaubskalender und Zeitplan."""
        fehler: dict[str, str] = {}
        if user_input is not None:
            fehler, zeitplan = self._pruefe(user_input)
            if not fehler:
                return await self._weiter(user_input, zeitplan)
        schema = self.add_suggested_values_to_schema(
            _person_schema(await self._schul_optionen()), user_input or {}
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=fehler)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Bestehende Person ändern: alle Felder vorbelegt."""
        subentry = self._get_reconfigure_subentry()
        schule = subentry.data.get(CONF_SCHULE)
        self._schule_alt = dict(schule) if isinstance(schule, Mapping) else None
        fehler: dict[str, str] = {}
        if user_input is not None:
            fehler, zeitplan = self._pruefe(user_input, ausser=subentry.subentry_id)
            if not fehler:
                return await self._weiter(user_input, zeitplan)
        vorbelegt = user_input or {
            CONF_NAME: subentry.title,
            CONF_URLAUBSKALENDER: subentry.data.get(CONF_URLAUBSKALENDER),
            **subentry.data.get(CONF_ZEITPLAN, {}),
        }
        schema = self.add_suggested_values_to_schema(
            _person_schema(await self._schul_optionen()), vorbelegt
        )
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=fehler
        )

    async def _schul_optionen(self) -> list[SelectOptionDict]:
        """Optionen für „Schulferien“, beschriftet in der HA-Sprache (E40, E44).

        Eine Option kann keine eigene Beschreibung tragen; darum steht die
        Erklärung in der Beschriftung. Bei „Bisherige Schule behalten“ stehen
        Anbieter und vollständiger Pfad der aktuellen Schule dabei. Die Texte
        kommen aus den Übersetzungen (``selector.schulferien``).
        """
        texte = await async_get_translations(
            self.hass, self.hass.config.language, "selector", {DOMAIN}
        )

        def text(wert: str) -> str:
            schluessel = f"component.{DOMAIN}.selector.schulferien.options.{wert}"
            return texte.get(schluessel, wert)

        wahl = [
            SelectOptionDict(value=SCHULE_KEINE, label=text(SCHULE_KEINE)),
            SelectOptionDict(value=SCHULE_WAEHLEN, label=text(SCHULE_WAEHLEN)),
        ]
        if self._schule_alt is not None:
            schluessel = self._schule_alt.get("anbieter")
            anbieter = ANBIETER.get(schluessel) if isinstance(schluessel, str) else None
            behalten = (
                text(SCHULE_BEHALTEN)
                .replace("{anbieter}", anbieter.titel if anbieter else str(schluessel))
                .replace("{schule}", schul_pfad(self._schule_alt))
            )
            wahl.insert(0, SelectOptionDict(value=SCHULE_BEHALTEN, label=behalten))
        return wahl


# ---------------------------------------------------------------- Räume

FEHLER_NAME_ODER_BEREICH = "name_oder_bereich"
FEHLER_BEREICH_VERGEBEN = "bereich_vergeben"

# Standardwerte der Raum-Konfiguration (ARCHITEKTUR.md 3.7)
RAUM_STANDARDS: dict[str, Any] = {
    CONF_ZUORDENBAR: True,
    CONF_KLEMM_BEGINN: 60,
    CONF_KLEMM_ENDE: 60,
    CONF_LICHTER: [],
    CONF_HELLIGKEIT: 100,
    CONF_ELEVATION: -3.0,
    CONF_DAUER: 45,
    CONF_LAUTSPRECHER: None,
    CONF_LAUTSTAERKE: 30,
}
_MIT_LICHTERN: FieldCondition = {
    "field": CONF_LICHTER,
    "operator": ConditionOperator.EXISTS,
}
_MIT_LAUTSPRECHER: FieldCondition = {
    "field": CONF_LAUTSPRECHER,
    "operator": ConditionOperator.EXISTS,
}


def _zahl(
    minimum: float, maximum: float, einheit: str, schritt: float = 1
) -> NumberSelector:
    """Zahlenfeld als Eingabefeld mit Einheit."""
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=schritt,
            unit_of_measurement=einheit,
            mode=NumberSelectorMode.BOX,
        )
    )


def _raum_einstellungen_schema() -> dict[Any, Any]:
    """Einstellungen eines Raums; Licht-/Lautsprecher-Felder nur bei Geräten."""
    std = RAUM_STANDARDS
    return _zeitplan_schema() | {
        probatio.Optional(CONF_ZUORDENBAR, default=std[CONF_ZUORDENBAR]): (
            BooleanSelector()
        ),
        probatio.Optional(CONF_KLEMM_BEGINN, default=std[CONF_KLEMM_BEGINN]): _zahl(
            0, 240, "min"
        ),
        probatio.Optional(CONF_KLEMM_ENDE, default=std[CONF_KLEMM_ENDE]): _zahl(
            0, 240, "min"
        ),
        probatio.Optional(CONF_LICHTER): EntitySelector(
            EntitySelectorConfig(domain="light", multiple=True)
        ),
        data_entry_flow.Optional(
            CONF_HELLIGKEIT, default=std[CONF_HELLIGKEIT], visible=_MIT_LICHTERN
        ): _zahl(1, 100, "%"),
        data_entry_flow.Optional(
            CONF_ELEVATION, default=std[CONF_ELEVATION], visible=_MIT_LICHTERN
        ): _zahl(-18, 10, "°", 0.5),
        probatio.Optional(CONF_LAUTSPRECHER): EntitySelector(
            EntitySelectorConfig(domain="media_player")
        ),
        data_entry_flow.Optional(
            CONF_LAUTSTAERKE, default=std[CONF_LAUTSTAERKE], visible=_MIT_LAUTSPRECHER
        ): _zahl(0, 100, "%"),
        probatio.Optional(CONF_DAUER, default=std[CONF_DAUER]): _zahl(1, 240, "min"),
    }


def _raum_daten(user_input: Mapping[str, Any], bereich: str | None) -> dict[str, Any]:
    """Gespeicherte Raum-Daten aus dem Formular; Fehlendes mit Standardwerten."""
    daten: dict[str, Any] = {
        CONF_BEREICH: bereich,
        CONF_ZEITPLAN: _zeitplan_daten(user_input),
    }
    for feld, standard in RAUM_STANDARDS.items():
        wert = user_input.get(feld)
        if wert in (None, ""):
            wert = standard
        elif isinstance(standard, bool):
            wert = bool(wert)
        elif isinstance(standard, int):
            wert = int(wert)
        elif isinstance(standard, float):
            wert = float(wert)
        daten[feld] = wert
    daten[CONF_LICHTER] = list(daten[CONF_LICHTER] or [])
    return daten


def _entities_im_bereich(hass: HomeAssistant, bereich: str, domain: str) -> list[str]:
    """Entity-IDs einer Domain im Bereich (direkt oder über ihr Gerät)."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    gefunden = {
        e.entity_id
        for e in er.async_entries_for_area(ent_reg, bereich)
        if e.domain == domain and not e.disabled
    }
    for geraet in dr.async_entries_for_area(dev_reg, bereich):
        for e in er.async_entries_for_device(ent_reg, geraet.id):
            if e.domain == domain and not e.disabled and e.area_id in (None, bereich):
                gefunden.add(e.entity_id)
    return sorted(gefunden)


class RaumSubentryFlow(ConfigSubentryFlow):
    """Dialog „Raum hinzufügen“ (Bereich, dann Einstellungen) und „Raum ändern“."""

    def __init__(self) -> None:
        """Merkt sich Bereich und Name zwischen den Schritten."""
        super().__init__()
        self._bereich: str | None = None
        self._name = ""

    def _andere_raeume(self, ausser: str | None) -> list[ConfigSubentry]:
        """Alle anderen Räume dieses Eintrags."""
        return [
            sub
            for sub in self._get_entry().subentries.values()
            if sub.subentry_type == SUBENTRY_RAUM and sub.subentry_id != ausser
        ]

    def _name_mit_bereich(self, name: str, bereich: str | None) -> str:
        """Leerer Name → Name des Bereichs (falls es ihn gibt)."""
        if not name and bereich:
            area = ar.async_get(self.hass).async_get_area(bereich)
            return area.name if area else ""
        return name

    def _pruefe_name_bereich(
        self, name: str, bereich: str | None, *, ausser: str | None = None
    ) -> dict[str, str]:
        """Fehler zu Name und Bereich (beide eindeutig, ein Name ist nötig)."""
        if not name:
            return {"base": FEHLER_NAME_ODER_BEREICH}
        fehler: dict[str, str] = {}
        if name.strip().casefold().replace(" ", "_") == KEIN_RAUM:
            fehler[CONF_NAME] = FEHLER_NAME_VERGEBEN
        andere = self._andere_raeume(ausser)
        if bereich and any(sub.data.get(CONF_BEREICH) == bereich for sub in andere):
            fehler[CONF_BEREICH] = FEHLER_BEREICH_VERGEBEN
        vergleich = name.strip().casefold()
        if any(sub.title.strip().casefold() == vergleich for sub in andere):
            fehler[CONF_NAME] = FEHLER_NAME_VERGEBEN
        return fehler

    def _vorschlaege(self, bereich: str | None) -> dict[str, Any]:
        """Lichter und (genau ein) Lautsprecher aus dem Bereich (E35)."""
        if not bereich:
            return {}
        vorschlag: dict[str, Any] = {}
        if lichter := _entities_im_bereich(self.hass, bereich, "light"):
            vorschlag[CONF_LICHTER] = lichter
        lautsprecher = _entities_im_bereich(self.hass, bereich, "media_player")
        if len(lautsprecher) == 1:
            vorschlag[CONF_LAUTSPRECHER] = lautsprecher[0]
        return vorschlag

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Schritt 1: HA-Bereich (optional) und Name."""
        fehler: dict[str, str] = {}
        if user_input is not None:
            bereich = user_input.get(CONF_BEREICH) or None
            name = self._name_mit_bereich(
                (user_input.get(CONF_NAME) or "").strip(), bereich
            )
            fehler = self._pruefe_name_bereich(name, bereich)
            if not fehler:
                self._bereich, self._name = bereich, name
                return await self.async_step_einstellungen()
        schema = self.add_suggested_values_to_schema(
            probatio.Schema(
                {
                    probatio.Optional(CONF_BEREICH): AreaSelector(),
                    probatio.Optional(CONF_NAME): TextSelector(),
                }
            ),
            user_input or {},
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=fehler)

    async def async_step_einstellungen(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Schritt 2: Standardplan, Klemm-Fenster, Geräte und Werte."""
        fehler: dict[str, str] = {}
        if user_input is not None:
            daten = _raum_daten(user_input, self._bereich)
            fehler = pruefe_zeitplan(daten[CONF_ZEITPLAN])
            if not fehler:
                return self.async_create_entry(title=self._name, data=daten)
        vorbelegt = user_input or self._vorschlaege(self._bereich)
        schema = self.add_suggested_values_to_schema(
            probatio.Schema(_raum_einstellungen_schema()), vorbelegt
        )
        return self.async_show_form(
            step_id="einstellungen",
            data_schema=schema,
            errors=fehler,
            description_placeholders={"name": self._name},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Raum ändern: Name, Bereich und alle Einstellungen, vorbelegt."""
        subentry = self._get_reconfigure_subentry()
        fehler: dict[str, str] = {}
        if user_input is not None:
            bereich = user_input.get(CONF_BEREICH) or None
            name = self._name_mit_bereich(
                (user_input.get(CONF_NAME) or "").strip(), bereich
            )
            daten = _raum_daten(user_input, bereich)
            fehler = self._pruefe_name_bereich(
                name, bereich, ausser=subentry.subentry_id
            ) | pruefe_zeitplan(daten[CONF_ZEITPLAN])
            if not fehler:
                return self.async_update_and_abort(
                    self._get_entry(), subentry, title=name, data=daten
                )
        gespeichert = dict(subentry.data)
        vorbelegt = user_input or {
            CONF_NAME: subentry.title,
            **gespeichert,
            **gespeichert.get(CONF_ZEITPLAN, {}),
        }
        schema = self.add_suggested_values_to_schema(
            probatio.Schema(
                {
                    probatio.Required(CONF_NAME): TextSelector(),
                    probatio.Optional(CONF_BEREICH): AreaSelector(),
                }
                | _raum_einstellungen_schema()
            ),
            vorbelegt,
        )
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=fehler
        )
