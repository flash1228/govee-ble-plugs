"""The common Govee light command set (GOVEE_BLE_PROTOCOL.md §6.1 / §6.5).

This is the legacy/common protocol shared by the large `pactType 11` "data-driven" band of
Govee BLE lights and validated on real hardware by this integration's H6163 light (it also
matches the widely-used community protocols wez/govee-py and chvolkmann/govee_btled). RGBIC
segment colour and the newer 0x15 colour sub-mode are handled by per-family codec subclasses.

All builders return a ready-to-write 20-byte frame.
"""
from __future__ import annotations

from typing import Optional

from .base import READ, WRITE, single_frame

# Mode sub-selectors carried in byte[2] of an 0x05 (SINGLE_MODE) frame.
_SUB_COLOR = 0x02   # legacy manual/static colour
_SUB_MUSIC = 0x01
_SUB_SCENE = 0x04

# Fixed trailer on the legacy colour frame (white-point / segment marker), as emitted by
# the stock app and the community protocols. Kept byte-for-byte for compatibility.
_COLOR_TRAILER = bytes([0x00, 0xFF, 0xAE, 0x54])


class CommonLightCodec:
    """Stateless builder/parser for the common light protocol."""

    # ---- writes -----------------------------------------------------------------------
    @staticmethod
    def power(on: bool) -> bytes:
        return single_frame(WRITE, 0x01, bytes([1 if on else 0]))

    @staticmethod
    def brightness(level: int) -> bytes:
        """level is 0-255 (HA's brightness scale)."""
        return single_frame(WRITE, 0x04, bytes([max(0, min(255, int(level)))]))

    @staticmethod
    def rgb(r: int, g: int, b: int) -> bytes:
        return single_frame(WRITE, 0x05, bytes([_SUB_COLOR, r & 0xFF, g & 0xFF, b & 0xFF]) + _COLOR_TRAILER)

    @staticmethod
    def color_temp_rgb(r: int, g: int, b: int) -> bytes:
        """White at a colour temperature, sent as a manual colour whose RGB is the
        white-point (the H6163 has no dedicated white channel over BLE):
        ``33 05 02 FF FF FF 01 R G B``.
        """
        return single_frame(WRITE, 0x05, bytes([_SUB_COLOR, 0xFF, 0xFF, 0xFF, 0x01, r & 0xFF, g & 0xFF, b & 0xFF]))

    @staticmethod
    def scene(scene_id: int) -> bytes:
        """Apply a scene/effect by its 1-byte code (``33 05 04 <id>``)."""
        return single_frame(WRITE, 0x05, bytes([_SUB_SCENE, scene_id & 0xFF]))

    @staticmethod
    def music(mode_id: int, params: bytes = b"") -> bytes:
        """Music-reactive mode (``33 05 01 <mode> <params>``)."""
        return single_frame(WRITE, 0x05, bytes([_SUB_MUSIC, mode_id & 0xFF]) + bytes(params))

    # ---- reads ------------------------------------------------------------------------
    @staticmethod
    def query_power() -> bytes:
        return single_frame(READ, 0x01)

    @staticmethod
    def query_brightness() -> bytes:
        return single_frame(READ, 0x04)

    # ---- parse ------------------------------------------------------------------------
    @staticmethod
    def parse_power_reply(frame: bytes) -> Optional[bool]:
        """A ``33/AA 01 <state> ..`` reply -> on/off. byte[2] is the relay/light state."""
        if len(frame) >= 3 and frame[1] == 0x01:
            return frame[2] == 0x01
        return None
