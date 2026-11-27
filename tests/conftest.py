"""Gemeinsame Test-Fixtures.

Das Test-Paket ``pytest-homeassistant`` (ab HA 2026.11) erlaubt das Laden von
Integrationen aus ``custom_components`` bereits standardmäßig; eine eigene
Fixture dafür ist nicht mehr nötig.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL, UrlManager
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import mock_component


@pytest.fixture(autouse=True)
def frontend_nachbilden(request: pytest.FixtureRequest) -> MagicMock | None:
    """``http`` und ``frontend`` als geladen melden (Abhängigkeiten, E69).

    Das echte Frontend braucht das Paket ``hass_frontend``, das in den Tests
    fehlt. HomeWake meldet darüber nur seine Karte an; das wird nachgebildet:
    ``hass.http`` nimmt statische Pfade an, die Liste der Zusatz-Module ist leer.

    Wirkt nur in Tests, die ``hass`` ohnehin nutzen; die Logik-Tests bleiben
    ohne HA. Achtung: ``hass.http`` ist hier ein Mock. Ein Test, der echte
    HTTP-Aufrufe braucht (``hass_client``), muss das Fixture überschreiben.
    """
    if "hass" not in request.fixturenames:
        return None
    hass: HomeAssistant = request.getfixturevalue("hass")
    mock_component(hass, "http")
    mock_component(hass, "frontend")
    http = MagicMock()
    http.async_register_static_paths = AsyncMock()
    hass.http = http
    hass.data[DATA_EXTRA_MODULE_URL] = UrlManager(lambda *_: None, [])
    return http
