"""Sensor platform for EGD Smart Meter integration."""

from functools import cached_property
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DOMAIN, SENSOR_TYPES

if TYPE_CHECKING:
    from . import EGDCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EGDCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for sensor_type in SENSOR_TYPES:
        entities.append(EGDSensor(coordinator, sensor_type, entry.entry_id))

    async_add_entities(entities)


class EGDSensor(SensorEntity):
    """EGD Smart Meter sensor with cumulative values for energy dashboard."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(
        self,
        coordinator: "EGDCoordinator",
        sensor_type: str,
        entry_id: str,
    ) -> None:
        self.coordinator = coordinator
        self.sensor_type = sensor_type
        self.entry_id = entry_id

        ean = coordinator.ean
        self._attr_unique_id = f"{entry_id}_{ean}_{sensor_type}"
        self._attr_name = f"EGD {ean} {SENSOR_TYPES[sensor_type]}"
        self._attr_entity_id = f"sensor.egd_{ean.replace('-', '_')}_{sensor_type}"

    @cached_property
    def native_value(self) -> StateType:
        return self.coordinator.data.get(self.sensor_type, 0.0)

    @cached_property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return {
            "ean": self.coordinator.ean,
            "last_updated": self.coordinator.last_update_success,
        }

    async def async_update(self) -> None:
        await self.coordinator.async_request_refresh()
