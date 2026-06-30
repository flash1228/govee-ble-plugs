"""Byte-vector tests for the old-DreamColor (H6163-family) segment codec."""
import importlib
import os
import sys
import types

PKG = "govee_ble_plugs"
_PKGDIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "govee_ble_plugs")
)
if PKG not in sys.modules:
    _pkg = types.ModuleType(PKG)
    _pkg.__path__ = [_PKGDIR]
    sys.modules[PKG] = _pkg

base = importlib.import_module(f"{PKG}.devices.codecs.base")
dreamcolor = importlib.import_module(f"{PKG}.devices.codecs.dreamcolor")
common = importlib.import_module(f"{PKG}.devices.codecs.common_light")
OldDreamColorCodec = dreamcolor.OldDreamColorCodec


def test_segment_color_0x0b_layout():
    # segments 0,1,2 -> mask 0x07 0x00 ; payload 0B R G B M0 M1
    got = OldDreamColorCodec.segment_color(0x11, 0x22, 0x33, [0, 1, 2])
    want = base.single_frame(0x33, 0x05, bytes([0x0B, 0x11, 0x22, 0x33, 0x07, 0x00]))
    assert got == want


def test_segment_high_byte():
    # segment 8 -> mask byte1 bit0
    got = OldDreamColorCodec.segment_color(1, 2, 3, [8, 14])
    mask = (1 << 8) | (1 << 14)  # 0x4100
    want = base.single_frame(0x33, 0x05, bytes([0x0B, 1, 2, 3, mask & 0xFF, (mask >> 8) & 0xFF]))
    assert got == want


def test_whole_strip_stays_legacy_0x02():
    # Inherited whole-strip colour must be the legacy 0x05 0x02 form (proven on H6163),
    # NOT the 0x0B/0x15 segment form.
    assert OldDreamColorCodec.rgb(10, 20, 30) == common.CommonLightCodec.rgb(10, 20, 30)
    assert OldDreamColorCodec.power(True) == common.CommonLightCodec.power(True)
    assert OldDreamColorCodec.brightness(128) == common.CommonLightCodec.brightness(128)
