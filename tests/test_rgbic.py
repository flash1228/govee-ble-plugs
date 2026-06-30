"""Byte-vector tests for the RGBIC per-segment codec."""
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
rgbic = importlib.import_module(f"{PKG}.devices.codecs.rgbic")
common = importlib.import_module(f"{PKG}.devices.codecs.common_light")
RgbicLightCodec = rgbic.RgbicLightCodec


def test_segment_color_mask_and_layout():
    # segments 0,1,2 -> mask bits 0b111 = 0x07 0x00 ; payload 15 01 R G B M0 M1
    got = RgbicLightCodec.segment_color(0x12, 0x34, 0x56, [0, 1, 2])
    want = base.single_frame(0x33, 0x05, bytes([0x15, 0x01, 0x12, 0x34, 0x56, 0x07, 0x00]))
    assert got == want


def test_segment_mask_high_byte():
    # segment 8 -> bit 8 -> mask 0x00 0x01
    got = RgbicLightCodec.segment_color(1, 2, 3, [8])
    want = base.single_frame(0x33, 0x05, bytes([0x15, 0x01, 1, 2, 3, 0x00, 0x01]))
    assert got == want


def test_whole_strip_rgb_selects_all_segments():
    # rgb() -> all 16 segments -> mask 0xFFFF
    got = RgbicLightCodec.rgb(0x12, 0x34, 0x56)
    want = base.single_frame(0x33, 0x05, bytes([0x15, 0x01, 0x12, 0x34, 0x56, 0xFF, 0xFF]))
    assert got == want


def test_color_temp_uses_0x0d():
    got = RgbicLightCodec.color_temp_rgb(0xAA, 0xBB, 0xCC)
    want = base.single_frame(0x33, 0x05, bytes([0x0D, 0xAA, 0xBB, 0xCC]))
    assert got == want


def test_inherits_common_power_brightness_effects():
    # Non-colour commands are unchanged from the common codec.
    assert RgbicLightCodec.power(True) == common.CommonLightCodec.power(True)
    assert RgbicLightCodec.brightness(200) == common.CommonLightCodec.brightness(200)
    assert RgbicLightCodec.effect("Movie") == common.CommonLightCodec.effect("Movie")
