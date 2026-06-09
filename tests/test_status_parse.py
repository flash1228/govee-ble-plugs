"""Status-reply parsing for the H508x plugs.

A GATT status query (``33 00 ..``) is answered with a 20-byte frame
``33 01 <state> 00.. <xor-cksum>``. The relay state lives at byte[2]; byte[-1] is the
frame's XOR checksum. Regression test for the poll path that read ``data[-1]`` (the
checksum) and therefore reported the wrong on/off state on every poll — which, with
polling enabled, clobbered the correct advertisement-derived state.

plugs.py only needs ``homeassistant.exceptions.ConfigEntryError``; we stub that and mount
the component dir as a package so the real parser imports without a full Home Assistant
install and without running the (HA-heavy) package ``__init__``.
"""
import importlib
import os
import sys
import types

PKG = "govee_ble_plugs"
_PKGDIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "govee_ble_plugs")
)

_ha = types.ModuleType("homeassistant")
_ha_exc = types.ModuleType("homeassistant.exceptions")
_ha_exc.ConfigEntryError = type("ConfigEntryError", (Exception,), {})
_ha.exceptions = _ha_exc
sys.modules.setdefault("homeassistant", _ha)
sys.modules.setdefault("homeassistant.exceptions", _ha_exc)

if PKG not in sys.modules:
    _pkg = types.ModuleType(PKG)
    _pkg.__path__ = [_PKGDIR]
    sys.modules[PKG] = _pkg

crypto = importlib.import_module(f"{PKG}.crypto")
plugs = importlib.import_module(f"{PKG}.plugs")


def _status_reply(state_byte: int) -> bytearray:
    """The 20-byte frame the firmware returns to a ``33 00`` status query."""
    return bytearray(crypto.build_frame(bytes([0x33, 0x01, state_byte])))


def _parse_single(cls, state_byte: int):
    api = cls.__new__(cls)  # skip __init__ (no BLEDevice / asyncio needed here)
    api._is_on = None
    api._parse_status_response(_status_reply(state_byte))
    return api._is_on


def test_h5080_status_on():
    assert _parse_single(plugs.GoveePlugH5080, 0xFF) is True


def test_h5080_status_off():
    assert _parse_single(plugs.GoveePlugH5080, 0x00) is False


def test_h5083_status_on():
    assert _parse_single(plugs.GoveePlugH5083, 0xFF) is True


def test_h5083_status_off():
    assert _parse_single(plugs.GoveePlugH5083, 0x00) is False


def test_h5086_status_on():
    assert _parse_single(plugs.GoveePlugH5086, 0xFF) is True


def test_h5086_status_off():
    assert _parse_single(plugs.GoveePlugH5086, 0x00) is False


def _parse_h5082(state_byte: int):
    api = plugs.GoveePlugH5082.__new__(plugs.GoveePlugH5082)
    api._is_on = [None, None]
    api._parse_status_response(_status_reply(state_byte))
    return api._is_on


def test_h5082_left_on_right_off():
    # bitfield at byte[2]: bit1 = left, bit0 = right
    assert _parse_h5082(0x02) == [True, False]


def test_h5082_right_on_left_off():
    assert _parse_h5082(0x01) == [False, True]


def test_h5082_both_on():
    assert _parse_h5082(0x03) == [True, True]


def test_h5082_both_off():
    assert _parse_h5082(0x00) == [False, False]
