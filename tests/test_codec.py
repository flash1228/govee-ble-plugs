"""Byte-vector tests for the device codec layer.

These pin the generic ``CommonLightCodec`` to the exact frames the hardware-validated
H6163 light emits (see ``light.py``), proving the data-driven path reproduces the proven
protocol. Pure-bytes — no HA/bleak needed; we mount the component dir as a stub package so
the heavy ``__init__`` never runs.
"""
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
CommonLightCodec = importlib.import_module(f"{PKG}.devices.codecs.common_light").CommonLightCodec


def _hex(b: bytes) -> str:
    return b.hex()


# ---- frame primitives -----------------------------------------------------------------
def test_single_frame_is_20_bytes_with_xor():
    frame = base.single_frame(0x33, 0x01, bytes([0x01]))
    assert len(frame) == 20
    # XOR of 0x33 ^ 0x01 ^ 0x01 == 0x33; rest are zero
    assert frame[-1] == 0x33
    assert base.is_valid_frame(frame)


def test_single_frame_rejects_overlong_payload():
    try:
        base.single_frame(0x33, 0x01, bytes(18))
    except ValueError:
        return
    raise AssertionError("expected ValueError for >17-byte payload")


def test_le16_be16():
    assert base.le16(0x1234) == bytes([0x34, 0x12])
    assert base.be16(0x1234) == bytes([0x12, 0x34])


# ---- common light vectors (must match light.py's H6163 bytes) -------------------------
def test_power_on_off():
    assert _hex(CommonLightCodec.power(True)) == "3301010000000000000000000000000000000033"
    assert _hex(CommonLightCodec.power(False)) == "3301000000000000000000000000000000000032"


def test_brightness():
    # light.py: [0x33, 0x04, BRIGHTNESS] + zeros + xor
    assert _hex(CommonLightCodec.brightness(0xFF)) == "3304ff00000000000000000000000000000000c8"


def test_rgb_matches_h6163_layout():
    # light.py: [0x33,0x05,0x02, R,G,B, 0x00,0xFF,0xAE,0x54] + zeros + xor
    assert _hex(CommonLightCodec.rgb(0x12, 0x34, 0x56)) == "33050212345600ffae5400000000000000000041"


def test_color_temp_matches_h6163_layout():
    # light.py: [0x33,0x05,0x02, 0xFF,0xFF,0xFF,0x01, R,G,B] + zeros + xor
    assert _hex(CommonLightCodec.color_temp_rgb(0xAA, 0xBB, 0xCC)) == "330502ffffff01aabbcc00000000000000000017"


def test_scene_matches_h6163_effect_vector():
    # H6163 "Movie" effect is 33 05 04 04 .. -> scene code 0x04
    assert _hex(CommonLightCodec.scene(0x04)) == "3305040400000000000000000000000000000036"


def test_parse_power_reply():
    on = base.single_frame(0x33, 0x01, bytes([0x01]))
    off = base.single_frame(0x33, 0x01, bytes([0x00]))
    assert CommonLightCodec.parse_power_reply(on) is True
    assert CommonLightCodec.parse_power_reply(off) is False
    assert CommonLightCodec.parse_power_reply(bytes([0x33, 0x99])) is None


def test_status_queries_and_replies():
    # query frames
    assert _hex(CommonLightCodec.query_power()) == "aa010000000000000000000000000000000000ab"
    assert _hex(CommonLightCodec.query_brightness()) == "aa040000000000000000000000000000000000ae"
    assert _hex(CommonLightCodec.query_color()) == "aa050100000000000000000000000000000000ae"
    # reply parsers
    assert CommonLightCodec.parse_brightness_reply(base.single_frame(0xAA, 0x04, bytes([200]))) == 200
    assert CommonLightCodec.parse_color_reply(base.single_frame(0xAA, 0x05, bytes([0x01, 10, 20, 30]))) == (10, 20, 30)
    # cross-type frames don't mis-parse
    assert CommonLightCodec.parse_brightness_reply(base.single_frame(0xAA, 0x05, bytes([0x01, 1, 2, 3]))) is None
    assert CommonLightCodec.parse_color_reply(base.single_frame(0xAA, 0x04, bytes([200]))) is None
