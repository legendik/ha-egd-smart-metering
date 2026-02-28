import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import ClientSession
from aiohttp.web import Response

sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "egd_smart_meter"))


@pytest.fixture
def mock_aiohttp_response():
    async def _make_response(json_data: dict, status: int = 200):
        response = AsyncMock(spec=Response)
        response.status = status
        response.json = AsyncMock(return_value=json_data)
        response.text = AsyncMock(return_value="")
        return response
    return _make_response


@pytest.fixture
def mock_client_session(mock_aiohttp_response):
    session = AsyncMock(spec=ClientSession)
    session.request = AsyncMock()
    session.closed = False
    return session


@pytest.fixture
def mock_hass():
    hass = MagicMock()
    hass.data = {}
    return hass


@pytest.fixture
def mock_config_entry():
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        "api_token": "test_token",
        "ean": "12345678901234",
        "start_date": "2024-01-01",
    }
    return entry
