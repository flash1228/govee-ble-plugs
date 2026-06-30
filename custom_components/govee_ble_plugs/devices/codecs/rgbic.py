"""RGBIC (addressable per-segment) light codec (GOVEE_BLE_DEVICES.md fam-rgbic §3).

Adds per-segment colour on top of the common set. The principal RGBIC colour command is
``33 05 15 01 R G B <2-byte segment mask>`` (builder ``h``); the mask is little-endian with
bit k = segment k. Whole-strip colour just selects every segment. Power/brightness/effects are
inherited from CommonLightCodec.
"""
from __future__ import annotations

from typing import Iterable

from .base import WRITE, single_frame
from .common_light import CommonLightCodec

# 16-segment mask covers the common RGBIC strips (segments 0..15); >16-seg strips use a paged
# format we don't drive here.
MAX_SEGMENTS = 16
ALL_SEGMENTS = tuple(range(MAX_SEGMENTS))


def _segment_mask(segments: Iterable[int]) -> bytes:
    """2-byte little-endian mask: bit k => segment k selected."""
    mask = 0
    for s in segments:
        if 0 <= s < MAX_SEGMENTS:
            mask |= 1 << s
    return bytes([mask & 0xFF, (mask >> 8) & 0xFF])


class RgbicLightCodec(CommonLightCodec):
    @staticmethod
    def segment_color(r: int, g: int, b: int, segments: Iterable[int]) -> bytes:
        """Colour the selected segments (``33 05 15 01 R G B <mask>``)."""
        payload = bytes([0x15, 0x01, r & 0xFF, g & 0xFF, b & 0xFF]) + _segment_mask(segments)
        return single_frame(WRITE, 0x05, payload)

    @classmethod
    def rgb(cls, r: int, g: int, b: int) -> bytes:
        # Whole-strip = every segment, via the RGBIC-native command.
        return cls.segment_color(r, g, b, ALL_SEGMENTS)

    @staticmethod
    def color_temp_rgb(r: int, g: int, b: int) -> bytes:
        # Whole-strip colour-temperature-as-RGB (sub-mode 0x0D).
        return single_frame(WRITE, 0x05, bytes([0x0D, r & 0xFF, g & 0xFF, b & 0xFF]))
