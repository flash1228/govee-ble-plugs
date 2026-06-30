"""Old "DreamColor" RGBIC light codec (H6163 / H6117 / H6116 / H6125 / H6126 / …).

These addressable strips predate the newer ``0x15`` segment protocol. Whole-strip colour stays
on the legacy ``0x05 0x02`` command (validated on the H6163); per-segment colour uses
``0x05 0x0B R G B <mask0-7> <mask8-14>`` (15 segments, bit k = segment k).
"""
from __future__ import annotations

from typing import Iterable

from .base import WRITE, single_frame
from .common_light import CommonLightCodec

MAX_SEGMENTS = 15


def _segment_mask(segments: Iterable[int]) -> bytes:
    """2 bytes: byte0 = segments 0-7 (bit k = seg k), byte1 = segments 8-14 (bit0 = seg8)."""
    mask = 0
    for s in segments:
        if 0 <= s < MAX_SEGMENTS:
            mask |= 1 << s
    return bytes([mask & 0xFF, (mask >> 8) & 0xFF])


class OldDreamColorCodec(CommonLightCodec):
    # Inherits power/brightness/colour-temp/effects/queries from the common codec, so
    # whole-strip colour (rgb) uses the legacy 0x05 0x02 form proven on the H6163.

    @staticmethod
    def segment_color(r: int, g: int, b: int, segments: Iterable[int]) -> bytes:
        """Colour the selected segments (``33 05 0B R G B <mask>``)."""
        payload = bytes([0x0B, r & 0xFF, g & 0xFF, b & 0xFF]) + _segment_mask(segments)
        return single_frame(WRITE, 0x05, payload)
