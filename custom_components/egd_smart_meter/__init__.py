"""EGD Smart Meter integration."""

from datetime import date, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import EGDApiError, EGDClient
from .const import (
    ATTR_CONSUMPTION,
    ATTR_PRODUCTION,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_EAN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
)


class EGDCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Data update coordinator for EGD Smart Meter."""

    def __init__(
        self,
        hass: HomeAssistant,
        client_id: str,
        client_secret: str,
        ean: str,
        start_date: date,
    ) -> None:
        self.api = EGDClient(client_id, client_secret)
        self.ean = ean
        self.start_date = start_date
        self._total_consumption = 0.0
        self._total_production = 0.0
        self._last_date: date | None = None

        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

        # Initialize data immediately so sensors can read it
        self.data = {
            ATTR_CONSUMPTION: self._total_consumption,
            ATTR_PRODUCTION: self._total_production,
        }

    async def _async_update_data(self) -> dict[str, Any]:
        # API requires data to be at least 1 day old, use day before yesterday
        safe_date = date.today() - timedelta(days=2)

        if self._last_date is None or safe_date > self._last_date:
            try:
                data = await self.api.get_consumption_data(
                    ean=self.ean,
                    start_date=safe_date,
                    end_date=safe_date,
                )

                daily_total = sum(
                    item.value for item in data if item.value is not None and item.status == "IU012"
                )

                if self._last_date is None:
                    self._total_consumption = daily_total
                else:
                    self._total_consumption += daily_total

                self._last_date = safe_date
                LOGGER.info(
                    "Updated consumption: %.2f kWh (total: %.2f)",
                    daily_total,
                    self._total_consumption,
                )

            except EGDApiError as err:
                LOGGER.error("Failed to fetch data: %s", err)

        return {
            ATTR_CONSUMPTION: self._total_consumption,
            ATTR_PRODUCTION: self._total_production,
        }

    async def fetch_initial_data(self) -> None:
        # API requires data to be at least 1 day old
        safe_date = date.today() - timedelta(days=2)

        if self.start_date > safe_date:
            LOGGER.warning(
                "Start date %s is too recent. Using %s instead.",
                self.start_date.isoformat(),
                safe_date.isoformat(),
            )
            self.start_date = safe_date

        try:
            data = await self.api.get_consumption_data_batch(
                ean=self.ean,
                start_date=self.start_date,
                end_date=safe_date,
            )

            LOGGER.info("Received %d total records from API", len(data))

            # Debug: count by status
            status_counts = {}
            for item in data:
                status = item.status
                status_counts[status] = status_counts.get(status, 0) + 1

            if status_counts:
                LOGGER.info("Status distribution: %s", status_counts)

            valid_count = 0
            for item in data:
                if item.value is not None and item.status == "IU012":
                    self._total_consumption += item.value
                    valid_count += 1

            if data:
                self._last_date = safe_date

            LOGGER.info(
                "Fetched %d records, %d valid (IU012), total consumption: %.2f kWh",
                len(data),
                valid_count,
                self._total_consumption,
            )

            # Update data so sensors can read the new values
            self.data = {
                ATTR_CONSUMPTION: self._total_consumption,
                ATTR_PRODUCTION: self._total_production,
            }

            LOGGER.info("Updated coordinator data: consumption=%.2f kWh", self._total_consumption)

        except EGDApiError as err:
            LOGGER.error("Failed to fetch initial data: %s", err)

    async def close(self) -> None:
        await self.api.close()


async def async_setup_entry(hass: HomeAssistant, entry: Any) -> bool:
    """Set up EGD Smart Meter from a config entry."""
    # Ensure start_date is a date object (it may be stored as string in JSON)
    start_date = entry.data["start_date"]
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)

    coordinator = EGDCoordinator(
        hass,
        entry.data[CONF_CLIENT_ID],
        entry.data[CONF_CLIENT_SECRET],
        entry.data[CONF_EAN],
        start_date,
    )

    await coordinator.fetch_initial_data()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    return True


async def async_unload_entry(hass: HomeAssistant, entry: Any) -> bool:
    """Unload a config entry."""
    coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
    if coordinator:
        await coordinator.close()
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])
