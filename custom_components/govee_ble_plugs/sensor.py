from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import GoveePlugEntity

# Ported from nsheaps@'s H5086 power-monitoring work.


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up power-monitoring (H5086) and broadcast metric (thermo-hygrometer) sensors."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator = entry_data["coordinator"]
    api = coordinator.api
    entities: list = []

    # Power-monitoring sensors (H5086).
    if api is not None and hasattr(api, "supports_power_monitoring"):
        supports_power = api.supports_power_monitoring()
    else:
        # Device not discovered yet — fall back to the configured model so the
        # sensors still register (they report unavailable until data arrives).
        supports_power = entry_data.get("model") == "H5086"
    if supports_power:
        entities += [
            GoveePlugVoltageSensor(coordinator, entry),
            GoveePlugCurrentSensor(coordinator, entry),
            GoveePlugPowerSensor(coordinator, entry),
            GoveePlugEnergySensor(coordinator, entry),
            GoveePlugPowerFactorSensor(coordinator, entry),
        ]

    # Broadcast metric sensors (thermo-hygrometers): temperature/humidity/battery.
    metrics: tuple[str, ...] = ()
    if api is not None and hasattr(api, "sensor_metrics"):
        metrics = api.sensor_metrics()
    else:
        from .devices import find_definition_by_model
        from .devices.capabilities import SensorCaps

        defn = find_definition_by_model(entry_data.get("model") or "")
        if defn is not None and defn.category == "sensor" and isinstance(defn.caps, SensorCaps):
            metrics = defn.caps.metrics
    entities += [GoveeMetricSensor(coordinator, entry, m) for m in metrics if m in METRIC_SPECS]

    if entities:
        async_add_entities(entities)


# Broadcast metric specs: metric key -> HA sensor description bits.
METRIC_SPECS: dict[str, dict] = {
    "temperature": {
        "name": "Temperature",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "unit": UnitOfTemperature.CELSIUS,
    },
    "humidity": {
        "name": "Humidity",
        "device_class": SensorDeviceClass.HUMIDITY,
        "unit": PERCENTAGE,
    },
    "battery": {
        "name": "Battery",
        "device_class": SensorDeviceClass.BATTERY,
        "unit": PERCENTAGE,
    },
}


class GoveeMetricSensor(GoveePlugEntity, SensorEntity):
    """A single broadcast-derived metric (temperature/humidity/battery)."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, config_entry: ConfigEntry, metric: str):
        spec = METRIC_SPECS[metric]
        self._metric = metric
        self._attr_name = spec["name"]
        super().__init__(coordinator, config_entry, None, spec["name"])
        self._attr_unique_id = f"{self._address}-{metric}"
        self._attr_device_class = spec["device_class"]
        self._attr_native_unit_of_measurement = spec["unit"]

    @property
    def available(self) -> bool:
        api = self.coordinator.api
        return (
            api is not None
            and hasattr(api, "get_sensor_values")
            and self._metric in api.get_sensor_values()
        )

    @property
    def native_value(self):
        api = self.coordinator.api
        if api is None or not hasattr(api, "get_sensor_values"):
            return None
        return api.get_sensor_values().get(self._metric)


class GoveePlugSensorBase(GoveePlugEntity, SensorEntity):
    """Base class for Govee power-monitoring sensors."""

    _sensor_type: str = ""

    def __init__(self, coordinator, config_entry: ConfigEntry):
        # Device-level sensor: no port, name comes from the subclass _attr_name.
        super().__init__(coordinator, config_entry, None, self._attr_name)
        self._attr_unique_id = f"{self._address}-{self._sensor_type}"

    @property
    def available(self) -> bool:
        api = self.coordinator.api
        return (
            api is not None
            and getattr(api, "supports_power_monitoring", lambda: False)()
            and api.get_power_data() is not None
        )

    def _power(self):
        api = self.coordinator.api
        return api.get_power_data() if api else None


class GoveePlugVoltageSensor(GoveePlugSensorBase):
    _sensor_type = "voltage"
    _attr_name = "Voltage"
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT

    @property
    def native_value(self) -> float | None:
        data = self._power()
        return data.voltage if data else None


class GoveePlugCurrentSensor(GoveePlugSensorBase):
    _sensor_type = "current"
    _attr_name = "Current"
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    @property
    def native_value(self) -> float | None:
        data = self._power()
        return data.current if data else None


class GoveePlugPowerSensor(GoveePlugSensorBase):
    _sensor_type = "power"
    _attr_name = "Power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    @property
    def native_value(self) -> float | None:
        data = self._power()
        return data.power if data else None


class GoveePlugEnergySensor(GoveePlugSensorBase):
    _sensor_type = "energy"
    _attr_name = "Energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR

    @property
    def native_value(self) -> float | None:
        data = self._power()
        return data.energy if data else None


class GoveePlugPowerFactorSensor(GoveePlugSensorBase):
    """Diagnostic, disabled by default.

    Power factor is definitionally derivable from the other three sensors
    (``PF = W / (V * A)``), so for most users it is a redundant near-constant that
    would write a recorder row on every poll. It is not free of information — the
    plug reports current in 0.01 A steps but computes PF from its unrounded
    internals, so at the sub-amp loads a plug actually sees the device's own byte
    beats a derived one (see docs/h5086-protocol.md) — and it is a useful load
    fingerprint (~1.0 resistive, 0.5-0.7 switching supply) and a slow-drift signal
    for motor loads. Enable it if you want that; nobody else pays for it.
    """

    _sensor_type = "power_factor"
    _attr_name = "Power Factor"
    _attr_device_class = SensorDeviceClass.POWER_FACTOR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> int | None:
        data = self._power()
        return data.power_factor if data else None
