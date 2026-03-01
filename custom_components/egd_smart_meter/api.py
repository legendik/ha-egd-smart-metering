"""EGD Smart Meter API client with OAuth2 authentication."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import aiohttp

from .const import (
    BASE_URL_DATA,
    BASE_URL_TOKEN,
    LOGGER,
    OAUTH_TOKEN_ENDPOINT,
    PROFILE_CONSUMPTION,
)


@dataclass
class MeasurementData:
    timestamp: datetime
    value: float | None
    status: str


class EGDApiError(Exception):
    pass


class EGDAuthError(EGDApiError):
    pass


class EGDClient:
    """EGD API client with OAuth2 authentication."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token: str | None = None
        self._token_expires: datetime | None = None
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get_access_token(self) -> str:
        """Get or refresh OAuth2 access token."""
        now = datetime.now()

        if self._access_token and self._token_expires and now < self._token_expires:
            return self._access_token

        session = await self._get_session()
        url = f"{BASE_URL_TOKEN}{OAUTH_TOKEN_ENDPOINT}"

        payload = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": "namerena_data_openapi",
        }

        async with session.post(url, json=payload) as response:
            if response.status == 401:
                raise EGDAuthError("Invalid client credentials")
            if response.status != 200:
                text = await response.text()
                raise EGDApiError(f"Token error {response.status}: {text}")

            data = await response.json()
            self._access_token = data.get("access_token")
            expires_in = data.get("expires", 41017000)
            self._token_expires = now + timedelta(seconds=expires_in)

            if not self._access_token:
                raise EGDApiError("No access token in response")

            return self._access_token

    async def _request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        retry_on_401: bool = True,
    ) -> Any:
        """Make authenticated API request with auto-retry on token expiry."""
        token = await self._get_access_token()
        session = await self._get_session()

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        async with session.request(method, url, headers=headers, params=params) as response:
            if response.status == 401:
                self._access_token = None
                self._token_expires = None
                if retry_on_401:
                    # Retry once with fresh token
                    LOGGER.debug("Token expired, retrying with fresh token")
                    return await self._request(method, url, params, retry_on_401=False)
                raise EGDAuthError("Access token expired or invalid")
            if response.status != 200:
                text = await response.text()
                raise EGDApiError(f"API error {response.status}: {text}")

            return await response.json()

    async def get_consumption_data(
        self,
        ean: str,
        start_date: date,
        end_date: date,
        page_start: int = 0,
    ) -> list[MeasurementData]:
        """Get quarter-hour consumption data.

        API returns values in kW for 15-minute intervals.
        Convert to kWh by dividing by 4 (since 15 min = 0.25 hour).
        """
        url = f"{BASE_URL_DATA}/spotreby"

        params = {
            "ean": ean,
            "profile": PROFILE_CONSUMPTION,
            "from": f"{start_date.isoformat()}T00:00:00.000Z",
            "to": f"{end_date.isoformat()}T23:59:59.999Z",
            "PageStart": page_start,
            "PageSize": 3000,
        }

        data = await self._request("GET", url, params=params)
        results = []

        # API returns a list with one object containing the data
        if not isinstance(data, list):
            LOGGER.warning("Unexpected data format from API: %s", type(data))
            return results

        total_records_in_response = 0
        for item in data:
            if not isinstance(item, dict):
                continue

            # Get total count if available (for pagination)
            total_records = item.get("total", 0)
            if total_records:
                total_records_in_response = total_records

            # Extract actual data points from nested "data" field
            data_points = item.get("data", [])
            for record in data_points:
                if not isinstance(record, dict):
                    continue
                ts_str = record.get("timestamp")
                if not ts_str:
                    continue

                try:
                    timestamp = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S.%fZ")
                except ValueError:
                    LOGGER.warning("Invalid timestamp format: %s, skipping", ts_str)
                    continue

                # Convert kW (15-min power) to kWh (energy)
                # 15 minutes = 0.25 hours, so kW * 0.25 = kWh, or kW / 4
                raw_value = record.get("value")
                kwh_value = raw_value / 4.0 if raw_value is not None else None

                results.append(
                    MeasurementData(
                        timestamp=timestamp,
                        value=kwh_value,
                        status=record.get("status", "IU012"),
                    )
                )

        # Check if there are more pages to fetch
        if total_records_in_response > 0 and page_start + len(results) < total_records_in_response:
            LOGGER.debug(
                "Pagination needed: fetched %d of %d records, fetching next page",
                page_start + len(results),
                total_records_in_response,
            )
            next_page_results = await self.get_consumption_data(
                ean=ean,
                start_date=start_date,
                end_date=end_date,
                page_start=page_start + len(results),
            )
            results.extend(next_page_results)

        return results

    async def get_consumption_data_batch(
        self,
        ean: str,
        start_date: date,
        end_date: date,
    ) -> list[MeasurementData]:
        """Get consumption data in batches to avoid rate limits.

        API limit: max 3000 records (~1 month of quarter-hour data).
        Split large date ranges into monthly chunks.
        """
        all_results: list[MeasurementData] = []
        current_start = start_date
        batch_count = 0

        # Ensure end_date is not in the future and not today/yesterday
        # API requires data to be at least 1 day old
        max_allowed_date = date.today() - timedelta(days=2)
        effective_end_date = min(end_date, max_allowed_date)

        if effective_end_date < start_date:
            LOGGER.warning(
                "Requested end_date %s is too recent. Using %s instead.",
                end_date.isoformat(),
                effective_end_date.isoformat(),
            )
            return all_results

        while current_start <= effective_end_date:
            # Calculate end of current month or effective_end_date
            if current_start.month == 12:
                next_month = current_start.replace(year=current_start.year + 1, month=1, day=1)
            else:
                next_month = current_start.replace(month=current_start.month + 1, day=1)

            current_end = min(next_month - timedelta(days=1), effective_end_date)

            LOGGER.info(
                "Fetching batch %d: %s to %s",
                batch_count + 1,
                current_start.isoformat(),
                current_end.isoformat(),
            )

            try:
                batch_data = await self.get_consumption_data(
                    ean=ean,
                    start_date=current_start,
                    end_date=current_end,
                )
                all_results.extend(batch_data)
                LOGGER.info("Batch %d: fetched %d records", batch_count + 1, len(batch_data))
            except EGDApiError as err:
                LOGGER.error("Failed to fetch batch %d: %s", batch_count + 1, err)
                # Continue with next batch, don't fail completely

            batch_count += 1
            current_start = next_month

        LOGGER.info(
            "Batch loading complete: %d batches, %d total records",
            batch_count,
            len(all_results),
        )
        return all_results
