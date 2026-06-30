"""Generic, codec-driven light API.

Reuses the proven BLE message-queue transport from ``light.GoveePlugH6xxx`` and implements
the light half of the ``GoveePlugApi`` interface via a :class:`CommonLightCodec` (or a
per-family subclass) plus a :class:`LightCaps` descriptor. One class drives every common-set
light SKU; the byte layouts are identical to the hardware-validated H6163 bespoke class.

Imported lazily (by a definition's factory), so importing ``..light`` here is cycle-free.
"""
from __future__ import annotations

import logging
import typing as T

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from homeassistant.util.color import color_temperature_to_rgb

from ..light import GoveePlugH6xxx
from .capabilities import LightCaps
from .codecs.common_light import CommonLightCodec

_LOGGER = logging.getLogger(__package__)

# The common modern write+notify characteristic pair (same as the H6163).
_SEND_UUID = "00010203-0405-0607-0809-0a0b0c0d2b11"
_RECV_UUID = "00010203-0405-0607-0809-0a0b0c0d2b10"


class GenericLightApi(GoveePlugH6xxx):
    """Codec-driven light. State is tracked optimistically (most BLE lights don't carry
    usable state in advertisements); the entity reports `available` on discovery alone.
    """

    def __init__(self, device: BLEDevice, token: T.Optional[str], definition, model: str,
                 codec: T.Type[CommonLightCodec] = CommonLightCodec) -> None:
        super().__init__(device, token or "", _RECV_UUID, _SEND_UUID)
        self.MODEL = model
        self._defn = definition
        self._codec = codec
        # Pull the LightCaps out of the definition (caps may be a single cap or a tuple).
        caps = definition.caps
        if isinstance(caps, tuple):
            caps = next((c for c in caps if isinstance(c, LightCaps)), LightCaps())
        self._caps: LightCaps = caps

        # Optimistic state — same attribute names the entity reads directly.
        self._is_on: T.Optional[bool] = None
        self._rgb: T.Optional[tuple[int, int, int]] = None
        self._brightness: T.Optional[int] = None
        self._last_brightness: int = 255
        self._effect: T.Optional[str] = "Normal"
        self._color_temp_kelvin: T.Optional[int] = None
        self._color_mode: str = "rgb"

    # ---- capability advertisement (read by the light entity) --------------------------
    def light_caps(self) -> LightCaps:
        """Effective caps: fall back to the codec's built-in effect catalogue."""
        if self._caps.effects:
            return self._caps
        return LightCaps(
            brightness=self._caps.brightness,
            rgb=self._caps.rgb,
            color_temp_k=self._caps.color_temp_k,
            segments=self._caps.segments,
            effects=self._codec.effect_names(),
        )

    # ---- GoveePlugApi surface ---------------------------------------------------------
    def port_names(self) -> T.List[T.Tuple[T.Optional[int], T.Optional[str]]]:
        return []  # a light, not a switch

    def is_on(self, port: int) -> T.Optional[bool]:
        return self._is_on

    def has_light(self) -> bool:
        return True

    def supports_power_monitoring(self) -> bool:
        return False

    def handle_bluetooth_event(self, device: BLEDevice, adv: AdvertisementData) -> None:
        # No usable state in advertisements for most lights; keep the device ref fresh.
        self._device = device

    def get_light_state(self) -> T.Tuple[T.Optional[tuple[int, int, int]], T.Optional[int]]:
        return self._rgb, self._brightness

    def get_color_mode(self) -> str:
        if self._caps.color_temp_k and self._color_mode == "color_temp":
            return "color_temp"
        return "rgb"

    def get_color_temp_kelvin(self) -> T.Optional[int]:
        return self._color_temp_kelvin

    def get_effect(self) -> T.Optional[str]:
        return self._effect

    async def async_turn_on(self, port: int) -> None:
        if await self._send_message(self._codec.power(True)):
            self._is_on = True

    async def async_turn_off(self, port: int) -> None:
        if await self._send_message(self._codec.power(False)):
            self._is_on = False

    async def async_set_light_rgb(self, rgb: tuple[int, int, int]) -> None:
        r, g, b = rgb
        if await self._send_message(self._codec.rgb(r, g, b)):
            self._rgb = rgb
            self._color_mode = "rgb"
            self._color_temp_kelvin = None

    async def async_set_light_color_temp(self, kelvin: int) -> None:
        if not self._caps.color_temp_k:
            return
        r, g, b = (int(c) for c in color_temperature_to_rgb(kelvin))
        if await self._send_message(self._codec.color_temp_rgb(r, g, b)):
            self._color_temp_kelvin = kelvin
            self._rgb = (r, g, b)
            self._color_mode = "color_temp"

    async def async_set_light_brightness(self, brightness: int) -> None:
        if await self._send_message(self._codec.brightness(brightness)):
            self._brightness = brightness
            if brightness > 0:
                self._last_brightness = brightness

    async def async_set_effect(self, effect: str) -> None:
        frame = self._codec.effect(effect)
        if frame is None:
            return
        if await self._send_message(frame):
            self._effect = effect

    async def async_query_status(self) -> bool:
        # Best-effort: common-set lights don't reliably answer a status read over this
        # write-only transport, so state stays optimistic. The entity is available on
        # discovery regardless (see GoveePlugLight.available).
        return False
