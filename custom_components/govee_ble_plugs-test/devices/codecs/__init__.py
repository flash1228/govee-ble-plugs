"""Protocol codecs: build/parse the Govee BLE byte frames. Codecs are pure functions of
bytes — no I/O — so they are unit-testable against known byte vectors without hardware.
"""
from __future__ import annotations

from .base import READ, WRITE, NOTIFY, single_frame, xor_checksum
from .common_light import CommonLightCodec

__all__ = ["READ", "WRITE", "NOTIFY", "single_frame", "xor_checksum", "CommonLightCodec"]
