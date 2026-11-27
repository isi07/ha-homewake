"""Tests für den Config Flow."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.homewake.const import DOMAIN, NAME


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """Der Nutzer kann HomeWake über die Oberfläche hinzufügen."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"land": "IS"}
    )
    assert result["step_id"] == "sonne"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == {
        "land": "IS",
        "bundesland": None,
        "sonne_morgen": "buergerlich",
        "grad_morgen": None,
        "sonne_abend": "buergerlich",
        "grad_abend": None,
    }


async def test_only_single_entry_allowed(hass: HomeAssistant) -> None:
    """Ein zweiter Eintrag wird abgelehnt."""
    MockConfigEntry(domain=DOMAIN).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
