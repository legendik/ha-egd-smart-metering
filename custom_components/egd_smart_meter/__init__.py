"""EGD Smart Meter integration."""

from datetime import date, datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
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
    ) -> None:
        self.api = EGDClient(client_id, client_secret)
        self.ean = ean
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
        # Reset to 0 for new day (today's consumption is not yet available)
        today = date.today()
        if self._last_date is not None and self._last_date < today:
            self._total_consumption = 0.0
            LOGGER.debug("Reset consumption for new day: %s", today.isoformat())

        # API requires data to be at least 1 day old, fetch yesterday's data
        safe_date = today - timedelta(days=1)

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

                # Store yesterday's data but don't update current state
                # Current state shows today's consumption (which is 0 until tomorrow)
                self._last_date = safe_date
                LOGGER.info(
                    "Stored yesterday's consumption (%.2f kWh) for %s",
                    daily_total,
                    safe_date.isoformat(),
                )

            except EGDApiError as err:
                LOGGER.error("Failed to fetch data: %s", err)

        return {
            ATTR_CONSUMPTION: self._total_consumption,
            ATTR_PRODUCTION: self._total_production,
        }

    async def fetch_initial_data(self, entry: ConfigEntry) -> None:
        # API requires data to be at least 1 day old, use yesterday
        safe_date = date.today() - timedelta(days=1)

        try:
            # Fetch only the last day for the sensor (historical data for statistics disabled)
            data = await self.api.get_consumption_data(
                ean=self.ean,
                start_date=safe_date,
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
            yesterday_total = 0.0
            for item in data:
                if item.value is not None and item.status == "IU012":
                    yesterday_total += item.value
                    valid_count += 1

            # Keep _total_consumption at 0 (today's consumption is not yet available)
            # yesterday_total is just for logging
            if data:
                self._last_date = safe_date

            LOGGER.info(
                "Fetched %d records (%d valid), yesterday's consumption: %.2f kWh. "
                "Sensor shows 0 for today (data available tomorrow).",
                len(data),
                valid_count,
                yesterday_total,
            )

            # Update data - sensor shows 0 for today
            self.data = {
                ATTR_CONSUMPTION: self._total_consumption,  # 0.0
                ATTR_PRODUCTION: self._total_production,
            }

            LOGGER.info(
                "Sensor ready: showing 0 kWh for today (data for yesterday: %.2f kWh)",
                yesterday_total,
            )

            # Import yesterday's data as hourly statistics for Energy Dashboard
            await self._import_hourly_statistics(data, safe_date)

        except EGDApiError as err:
            LOGGER.error("Failed to fetch initial data: %s", err)

    async def _import_hourly_statistics(self, data: list, date_obj: date) -> None:
        """Import yesterday's data as hourly statistics for Energy Dashboard."""
        if not data:
            return

        # Filter valid data and group by hour
        hourly_data: dict[int, float] = {}
        for item in data:
            if item.value is not None and item.status == "IU012":
                hour = item.timestamp.hour
                hourly_data[hour] = hourly_data.get(hour, 0.0) + item.value

        if not hourly_data:
            LOGGER.warning("No valid hourly data to import")
            return

        # Prepare statistics with cumulative sum
        statistics = []
        running_sum = 0.0

        for hour in sorted(hourly_data.keys()):
            running_sum += hourly_data[hour]
            # Create timestamp for start of hour
            hour_dt = datetime.combine(date_obj, datetime.min.time().replace(hour=hour))
            hour_dt = hour_dt.replace(tzinfo=timezone.utc)  # noqa: UP017

            statistics.append(
                {
                    "start": hour_dt,
                    "sum": running_sum,
                    "state": running_sum,
                }
            )

        # Metadata
        metadata = {
            "has_mean": False,
            "has_sum": True,
            "name": f"EGD {self.ean} Consumption",
            "source": "egd_smart_meter",
            "statistic_id": f"egd_smart_meter:{self.ean}_consumption",
            "unit_of_measurement": "kWh",
            "unit_class": "energy",
        }

        # Import statistics (ignore if already exists)
        try:
            from homeassistant.components.recorder.statistics import async_add_external_statistics

            async_add_external_statistics(self.hass, metadata, statistics)
            LOGGER.info(
                "Imported %d hours of statistics for %s into Energy Dashboard",
                len(statistics),
                date_obj.isoformat(),
            )
        except Exception as err:
            if "UNIQUE constraint" in str(err):
                LOGGER.debug("Statistics for %s already exist", date_obj.isoformat())
            else:
                LOGGER.error("Failed to import statistics: %s", err)

    async def close(self) -> None:
        await self.api.close()


async def async_setup_entry(hass: HomeAssistant, entry: Any) -> bool:
    """Set up EGD Smart Meter from a config entry."""
    coordinator = EGDCoordinator(
        hass,
        entry.data[CONF_CLIENT_ID],
        entry.data[CONF_CLIENT_SECRET],
        entry.data[CONF_EAN],
    )

    await coordinator.fetch_initial_data(entry)

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
