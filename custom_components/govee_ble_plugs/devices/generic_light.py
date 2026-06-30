"""Generic, codec-driven light API.

Reuses the proven BLE message-queue transport from ``light.GoveePlugH6xxx`` and implements
the light half of the ``GoveePlugApi`` interface via a :class:`CommonLightCodec` (or a
per-family subclass) plus a :class:`LightCaps` descriptor. One class drives every common-set
light SKU; the byte layouts are identical to the hardware-validated H6163 bespoke class.

Imported lazily (by a definition's factory), so importing ``..light`` here is cycle-free.
"""
from __future__ import annotations

import asyncio
import logging
import typing as T

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak_retry_connector import establish_connection
from homeassistant.util.color import color_temperature_to_rgb

from ..light import GoveePlugH6xxx
from .capabilities import LightCaps
from .codecs.common_light import CommonLightCodec

_STATUS_QUERY_TIMEOUT = 5.0

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
        """Effective caps. Effects are restricted to those the codec can actually emit, so
        the HA effect list never advertises a no-op (relevant when a bespoke definition's
        caps list more effects than the common codec supports — e.g. H6163 via generic)."""
        names = self._caps.effects or self._codec.effect_names()
        effects = tuple(n for n in names if self._codec.effect(n) is not None)
        return LightCaps(
            brightness=self._caps.brightness,
            rgb=self._caps.rgb,
            color_temp_k=self._caps.color_temp_k,
            segments=self._caps.segments,
            effects=effects,
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
        """Seed real state by connecting, subscribing to notifications, and querying
        brightness (``aa 04``), colour (``aa 05 01``) and on/off (``aa 01``) — the same
        sequence the bespoke H6163 uses. Returns True if any state was read. Best-effort:
        a device that doesn't answer leaves state optimistic (the entity stays available).
        """
        client = None
        name = f"{self._device.name} ({self._device.address})"
        got_state = False
        try:
            async with self._connection_lock:
                try:
                    client = await establish_connection(
                        BleakClient, self._device, name,
                        max_attempts=1, connection_timeout=_STATUS_QUERY_TIMEOUT,
                    )
                except Exception as e:
                    _LOGGER.debug("status connect failed for %s: %s", name, e)
                    return False

            ready = asyncio.Event()

            def _on_notify(_char, data) -> None:
                frame = bytes(data)
                bri = self._codec.parse_brightness_reply(frame)
                if bri is not None:
                    self._brightness = bri
                    if bri > 0:
                        self._last_brightness = bri
                    ready.set()
                    return
                rgb = self._codec.parse_color_reply(frame)
                if rgb is not None:
                    self._rgb = rgb
                    ready.set()
                    return
                onoff = self._codec.parse_power_reply(frame)
                if onoff is not None:
                    self._is_on = onoff
                    ready.set()

            await client.start_notify(self._RECV_CHARACTERISTIC_UUID, _on_notify)

            for query in (self._codec.query_brightness(), self._codec.query_color(),
                          self._codec.query_power()):
                ready.clear()
                try:
                    await client.write_gatt_char(self._SEND_CHARACTERISTIC_UUID, query, response=False)
                    await asyncio.wait_for(ready.wait(), timeout=_STATUS_QUERY_TIMEOUT)
                    got_state = True
                except (asyncio.TimeoutError, Exception) as e:
                    _LOGGER.debug("status query no reply for %s: %s", name, e)
            return got_state
        except Exception as e:
            _LOGGER.debug("status query error for %s: %s", name, e)
            return got_state
        finally:
            if client is not None:
                try:
                    if client.is_connected:
                        await client.disconnect()
                    await asyncio.sleep(0.1)
                except Exception:
                    pass

    # ---- RGBIC per-segment (only when the codec supports it) --------------------------
    def supports_segments(self) -> bool:
        return self._caps.segments > 0 and hasattr(self._codec, "segment_color")

    async def async_set_segment_color(self, segments, rgb: tuple[int, int, int]) -> None:
        """Set the colour of specific RGBIC segments. No-op on non-RGBIC codecs."""
        if not hasattr(self._codec, "segment_color"):
            return
        r, g, b = rgb
        if await self._send_message(self._codec.segment_color(r, g, b, segments)):
            self._rgb = rgb
            self._color_mode = "rgb"
            self._color_temp_kelvin = None
