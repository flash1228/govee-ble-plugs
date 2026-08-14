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


# ---- H5086 power frame parsing ----
# Layout: <aa|ee> 19 [time:3][energy:3][voltage:2][current:2][power:3][factor:1]
# Both vectors below are real 20-byte captures with valid XOR checksums, one under
# each header: `ee 19` is the device's unsolicited push, `aa 19` the reply to a read.

# reydanro@, egold555/Govee-Reverse-Engineering Products/H5086.md
_POWER_FRAME_EE = "ee1900198b0000262f3d00910044656400000085"
# flash1228@, PR #1 (docs/h5086-protocol.md worked example)
_POWER_FRAME_AA = "aa1900338a0003c027d9001b000a426100000005"


class _FakeDevice:
    address = "00:00:00:00:00:00"


def _parse_h5086_power(frame_hex: str, seed=None):
    api = plugs.GoveePlugH5086.__new__(plugs.GoveePlugH5086)  # skip __init__
    api._power_data = seed if seed is not None else plugs.GoveePowerData()
    api._device = _FakeDevice()
    api._parse_power_response(bytearray(bytes.fromhex(frame_hex)))
    return api._power_data


def test_h5086_power_parse_ee_header():
    """The device's unsolicited `ee 19` push must still parse."""
    pd = _parse_h5086_power(_POWER_FRAME_EE)
    assert pd.time_on == 6539
    assert pd.voltage == 120.93
    assert pd.current == 1.45
    assert pd.power == 175.09
    assert pd.energy == 3.8
    assert pd.power_factor == 100


def test_h5086_power_parse_aa_header():
    """The `aa 19` reply to our own read carries the identical payload."""
    pd = _parse_h5086_power(_POWER_FRAME_AA)
    assert pd.time_on == 13194
    assert pd.voltage == 102.01
    assert pd.current == 0.27
    assert pd.power == 26.26
    assert pd.energy == 96.0
    assert pd.power_factor == 97


def test_h5086_power_factor_matches_computed():
    """byte[15] is power factor, not padding: on both captures it agrees with the
    PF computed from that same frame's V/A/W, within current quantisation (0.01 A)."""
    for frame in (_POWER_FRAME_EE, _POWER_FRAME_AA):
        pd = _parse_h5086_power(frame)
        computed = pd.power / (pd.voltage * pd.current) * 100
        assert abs(computed - pd.power_factor) < 2.5


def test_h5086_power_parse_short_frame_ignored():
    seed = plugs.GoveePowerData(time_on=999)
    assert _parse_h5086_power("aa190102", seed=seed).time_on == 999


def test_h5086_power_parse_wrong_header_ignored():
    seed = plugs.GoveePowerData(time_on=999)
    bad = "33" + _POWER_FRAME_AA[2:]
    assert _parse_h5086_power(bad, seed=seed).time_on == 999
