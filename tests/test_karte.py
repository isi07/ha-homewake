"""Tests für die Anmeldung der Dashboard-Karte (ARCHITEKTUR.md 5.6, E68, E69).

HomeWake liefert die gebaute Karte mit und meldet sie selbst an: als statische
Datei und als Zusatz-Modul des Frontends, mit einer Prüfsumme gegen alte
Fassungen im Browser-Zwischenspeicher.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.homewake.const import DOMAIN

DATEI = (
    Path(__file__).parent.parent
    / "custom_components"
    / "homewake"
    / "frontend"
    / "homewake-card.js"
)


async def einrichten(hass: HomeAssistant) -> None:
    """Richtet HomeWake ohne Personen und Räume ein."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def module(hass: HomeAssistant) -> list[str]:
    """Angemeldete Zusatz-Module des Frontends."""
    return list(hass.data[DATA_EXTRA_MODULE_URL].urls)


async def test_gebaute_karte_liegt_bei() -> None:
    """Die gebaute Karte ist Teil der Integration (eingecheckt, E68)."""
    assert DATEI.is_file()
    assert "homewake-card" in DATEI.read_text(encoding="utf-8")


async def test_karte_wird_angemeldet(
    hass: HomeAssistant, frontend_nachbilden: MagicMock
) -> None:
    """Statischer Pfad und Zusatz-Modul mit Prüfsumme der Datei."""
    await einrichten(hass)
    frontend_nachbilden.async_register_static_paths.assert_awaited_once()
    (pfad,) = frontend_nachbilden.async_register_static_paths.await_args.args[0]
    assert pfad.url_path == "/homewake/homewake-card.js"
    assert Path(pfad.path) == DATEI
    assert pfad.cache_headers
    pruefsumme = hashlib.sha256(DATEI.read_bytes()).hexdigest()[:12]
    assert module(hass) == [f"/homewake/homewake-card.js?v={pruefsumme}"]


async def test_neu_laden_meldet_nicht_doppelt_an(
    hass: HomeAssistant, frontend_nachbilden: MagicMock
) -> None:
    """Die Karte wird einmal pro HA-Start angemeldet, nicht pro Laden des Eintrags."""
    await einrichten(hass)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    frontend_nachbilden.async_register_static_paths.assert_awaited_once()
    assert len(module(hass)) == 1


async def test_fehlende_karte_haelt_homewake_nicht_auf(
    hass: HomeAssistant,
    frontend_nachbilden: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Fehlt die gebaute Datei, läuft HomeWake ohne Karte weiter (Warnung)."""
    with patch("custom_components.homewake.KARTE_DATEI", DATEI.with_name("fehlt.js")):
        await einrichten(hass)
    frontend_nachbilden.async_register_static_paths.assert_not_awaited()
    assert module(hass) == []
    assert "Dashboard-Karte" in caplog.text
    assert hass.config_entries.async_entries(DOMAIN)[0].runtime_data is not None
