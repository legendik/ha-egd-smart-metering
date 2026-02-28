from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.egd_smart_meter.api import (
    EGDAuthError,
    EGDClient,
    MeasurementData,
)


class TestEGDClient:
    @pytest.fixture
    def client(self):
        return EGDClient("test_client_id", "test_client_secret")

    def test_client_initialization(self, client):
        assert client._client_id == "test_client_id"
        assert client._client_secret == "test_client_secret"
        assert client._access_token is None

    @pytest.mark.asyncio
    async def test_token_caching(self, client):
        """Test that token is cached and reused until expiration."""
        client._access_token = "cached_token"
        client._token_expires = datetime.now() + timedelta(hours=1)

        token = await client._get_access_token()
        assert token == "cached_token"

    @pytest.mark.asyncio
    async def test_get_consumption_data_success(self, client):
        mock_response = [
            {
                "ean/eic": "859182400100366666",
                "profile": "ICC1",
                "units": "KW",
                "total": 2,
                "data": [
                    {
                        "timestamp": "2023-03-01T00:45:00.000Z",
                        "value": 0.5,
                        "status": "IU012",
                    },
                    {
                        "timestamp": "2023-03-01T01:00:00.000Z",
                        "value": 0.75,
                        "status": "IU012",
                    },
                ],
            }
        ]

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            results = await client.get_consumption_data(
                ean="859182400100366666",
                start_date=date(2023, 3, 1),
                end_date=date(2023, 3, 1),
            )

        assert len(results) == 2
        assert results[0].value == 0.5
        assert results[0].status == "IU012"

    @pytest.mark.asyncio
    async def test_get_consumption_data_with_null_values(self, client):
        mock_response = [
            {
                "ean/eic": "859182400100366666",
                "profile": "ICC1",
                "units": "KW",
                "total": 2,
                "data": [
                    {
                        "timestamp": "2023-03-01T00:45:00.000Z",
                        "value": None,
                        "status": "IU011",
                    },
                    {
                        "timestamp": "2023-03-01T01:00:00.000Z",
                        "value": 0.75,
                        "status": "IU012",
                    },
                ],
            }
        ]

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            results = await client.get_consumption_data(
                ean="859182400100366666",
                start_date=date(2023, 3, 1),
                end_date=date(2023, 3, 1),
            )

        assert len(results) == 2
        assert results[0].value is None
        assert results[1].value == 0.75

    @pytest.mark.asyncio
    async def test_auth_error_raises_egdauth_error(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = EGDAuthError("Invalid credentials")

            with pytest.raises(EGDAuthError):
                await client.get_consumption_data(
                    ean="test_ean",
                    start_date=date(2023, 3, 1),
                    end_date=date(2023, 3, 1),
                )

    @pytest.mark.asyncio
    async def test_batch_loading_multiple_months(self, client):
        """Test that batch loading splits requests by month."""
        from custom_components.egd_smart_meter.api import MeasurementData

        mock_data_jan = [
            MeasurementData(
                timestamp=datetime(2023, 1, 15, 12, 0, 0),
                value=1.0,
                status="IU012",
            )
        ]
        mock_data_feb = [
            MeasurementData(
                timestamp=datetime(2023, 2, 15, 12, 0, 0),
                value=2.0,
                status="IU012",
            )
        ]

        call_count = 0

        async def mock_response(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_data_jan
            else:
                return mock_data_feb

        with patch.object(client, "get_consumption_data", side_effect=mock_response):
            results = await client.get_consumption_data_batch(
                ean="859182400100366666",
                start_date=date(2023, 1, 1),
                end_date=date(2023, 2, 28),
            )

        assert call_count == 2
        assert len(results) == 2
        assert results[0].value == 1.0
        assert results[1].value == 2.0


class TestDataClasses:
    def test_measurement_data_creation(self):
        md = MeasurementData(
            timestamp=datetime(2023, 3, 1, 12, 0, 0),
            value=10.5,
            status="W",
        )
        assert md.timestamp == datetime(2023, 3, 1, 12, 0, 0)
        assert md.value == 10.5
        assert md.status == "W"

    def test_measurement_data_with_none_value(self):
        md = MeasurementData(
            timestamp=datetime(2023, 3, 1, 12, 0, 0),
            value=None,
            status="F",
        )
        assert md.value is None
