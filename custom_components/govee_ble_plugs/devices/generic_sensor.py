"""Generic broadcast-monitoring sensor API.

Govee sensors expose state only via BLE advertisements, so this needs no connection: it parses
each advert into metric values the sensor platform reads. Implements the same ``GoveePlugApi``
surface the coordinator/entities expect (no switch ports, no light, no power monitoring).
"""
from __future__ import annotations

import logging
import typing as T

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from .capabilities import SensorCaps
from .codecs.sensor import parse_th_broadcast

_LOGGER = logging.getLogger(__package__)


class GenericSensorApi:
    def __init__(self, device: BLEDevice, token: T.Optional[str], definition, model: str) -> None:
        self._device = device
        self.MODEL = model
        self._defn = definition
        caps = definition.caps
        if isinstance(caps, tuple):
            caps = next((c for c in caps if isinstance(c, SensorCaps)), SensorCaps())
        self._caps: SensorCaps = caps
        self._values: dict[str, float] = {}

    # ---- capability surface -----------------------------------------------------------
    def sensor_metrics(self) -> tuple[str, ...]:
        return self._caps.metrics

    def get_sensor_values(self) -> dict[str, float]:
        return dict(self._values)

    # ---- GoveePlugApi surface ---------------------------------------------------------
    def port_names(self) -> T.List[T.Tuple[T.Optional[int], T.Optional[str]]]:
        return []

    def is_on(self, port: int) -> T.Optional[bool]:
        return None

    def has_light(self) -> bool:
        return False

    def supports_power_monitoring(self) -> bool:
        return False

    def handle_bluetooth_event(self, device: BLEDevice, adv: AdvertisementData) -> None:
        self._device = device
        parsed = parse_th_broadcast(adv.manufacturer_data or {})
        if parsed:
            # Keep only metrics this device declares.
            for key, value in parsed.items():
                if not self._caps.metrics or key in self._caps.metrics:
                    self._values[key] = value

    async def async_turn_on(self, port: int) -> None:  # not actuatable
        return None

    async def async_turn_off(self, port: int) -> None:
        return None

    async def async_query_status(self) -> bool:
        return False  # broadcast-only
