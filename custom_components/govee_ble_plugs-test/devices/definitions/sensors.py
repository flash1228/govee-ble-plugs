"""Sensor definitions — broadcast monitor-only thermo-hygrometers.

These parse temperature/humidity/battery from BLE advertisements (no connection, no pairing).
Note: HA core's ``govee-ble`` integration also covers many of these; this brings them under
one roof alongside the integration's plug/light control.
"""
from __future__ import annotations

from ..capabilities import SensorCaps
from ..registry import DeviceDefinition, find_definition_by_model, register
from ._sensor_skus import TH_SENSOR_SKUS


def _generic_sensor_api(device, token, defn, model):
    from ..generic_sensor import GenericSensorApi
    return GenericSensorApi(device, token, defn, model)


_models = tuple(s for s in TH_SENSOR_SKUS if find_definition_by_model(s) is None)

register(DeviceDefinition(
    models=_models,
    name_prefixes=(),  # discovered via broad manifest matchers + extract_sku
    category="sensor",
    caps=SensorCaps(metrics=("temperature", "humidity", "battery")),
    api_factory=_generic_sensor_api,
    pair_factory=None,
    requires_pairing=False,
    default_polling=False,
    experimental=True,
))
