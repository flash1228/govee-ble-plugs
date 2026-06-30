"""Generic appliance API — on/off control for Govee BLE kitchen/air appliances.

Humidifiers, ice makers, kettles, heaters, purifiers, fans, etc. (the ``base_h71xx`` family)
share the main-switch opcode ``0x01`` (``33 01 <on>``; GOVEE_BLE_DEVICES.md fam-kitchen-air
§3.1). This exposes that as a single power switch. Mode/gear/ice-size (opcode 0x05) and the
various feature switches are per-SKU and left as future work.

State is optimistic (these devices' broadcast layouts vary); the switch is available on
discovery via ``optimistic_switch``. Experimental — BLE control is protocol-derived, not
hardware-verified per SKU.
"""
from __future__ import annotations

import logging
import typing as T

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..light import GoveePlugH6xxx
from .codecs.common_light import CommonLightCodec

_LOGGER = logging.getLogger(__package__)

_SEND_UUID = "00010203-0405-0607-0809-0a0b0c0d2b11"
_RECV_UUID = "00010203-0405-0607-0809-0a0b0c0d2b10"


class GenericApplianceApi(GoveePlugH6xxx):
    # The switch entity treats this device as available on discovery (state is optimistic).
    optimistic_switch = True

    def __init__(self, device: BLEDevice, token: T.Optional[str], definition, model: str) -> None:
        super().__init__(device, token or "", _RECV_UUID, _SEND_UUID)
        self.MODEL = model
        self._defn = definition
        self._is_on: T.Optional[bool] = None

    def port_names(self) -> T.List[T.Tuple[T.Optional[int], T.Optional[str]]]:
        return [(None, None)]  # single power switch

    def is_on(self, port: int) -> T.Optional[bool]:
        return self._is_on

    def has_light(self) -> bool:
        return False

    def supports_power_monitoring(self) -> bool:
        return False

    def handle_bluetooth_event(self, device: BLEDevice, adv: AdvertisementData) -> None:
        self._device = device

    async def async_turn_on(self, port: int) -> None:
        if await self._send_message(CommonLightCodec.power(True)):
            self._is_on = True

    async def async_turn_off(self, port: int) -> None:
        if await self._send_message(CommonLightCodec.power(False)):
            self._is_on = False

    async def async_query_status(self) -> bool:
        return False
