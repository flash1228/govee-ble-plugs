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
# Frame layout (per APK DeviceElectricController.d()/e()):
#   ee 19 [runtime:3 BE][energy:3 BE][voltage:2 BE][current:2 BE][power:3 BE] [padding:4]
# The XOR checksum at byte[19] is recomputed by build_frame for unit-test inputs.

def _power_frame(runtime: int, energy_raw: int, voltage_raw: int,
                 current_raw: int, power_raw: int) -> bytearray:
    payload = bytes([
        # proType, cmdType
        0xEE, 0x19,
        # runtime:3 BE
        (runtime >> 16) & 0xFF, (runtime >> 8) & 0xFF, runtime & 0xFF,
        # energy:3 BE
        (energy_raw >> 16) & 0xFF, (energy_raw >> 8) & 0xFF, energy_raw & 0xFF,
        # voltage:2 BE
        (voltage_raw >> 8) & 0xFF, voltage_raw & 0xFF,
        # current:2 BE
        (current_raw >> 8) & 0xFF, current_raw & 0xFF,
        # power:3 BE
        (power_raw >> 16) & 0xFF, (power_raw >> 8) & 0xFF, power_raw & 0xFF,
        # padding bytes (zeros) — build_frame fills to 20 bytes with checksum at [19]
    ])
    return bytearray(crypto.build_frame(payload))


class _FakeDevice:
    address = "00:00:00:00:00:00"


def _parse_h5086_power(frame: bytearray):
    api = plugs.GoveePlugH5086.__new__(plugs.GoveePlugH5086)
    api._power_data = plugs.GoveePowerData()
    api._device = _FakeDevice()
    api._parse_power_response(frame)
    return api._power_data


def test_h5086_power_parse_known_values():
    # 230.50 V, 0.12 A, 27.66 W, 100 Wh energy, 3600 s runtime.
    # energy divisor is /10000 (kWh) then *1000 (Wh) — for 100 Wh:
    #   energy_raw / 10000 * 1000 == 100  ->  energy_raw = 1000
    frame = _power_frame(runtime=3600, energy_raw=1000, voltage_raw=23050,
                         current_raw=12, power_raw=2766)
    pd = _parse_h5086_power(frame)
    assert pd is not None
    assert pd.time_on == 3600
    assert pd.voltage == 230.50
    assert pd.current == 0.12
    assert pd.power == 27.66
    assert abs(pd.energy - 100.0) < 1e-6
    # power factor is no longer parsed (APK shows only 13 payload bytes)
    assert pd.power_factor is None


def test_h5086_power_parse_short_frame_ignored():
    # A frame shorter than 15 bytes should be ignored (no exception, no update).
    frame = bytearray(b"\xee\x19\x01\x02\x03")
    api = plugs.GoveePlugH5086.__new__(plugs.GoveePlugH5086)
    api._power_data = plugs.GoveePowerData(time_on=999)
    api._device = _FakeDevice()
    api._parse_power_response(frame)
    assert api._power_data.time_on == 999  # unchanged


def test_h5086_power_parse_wrong_header_ignored():
    # Frame starting with anything other than ee 19 must not parse.
    frame = _power_frame(runtime=10, energy_raw=0, voltage_raw=0,
                         current_raw=0, power_raw=0)
    frame[0] = 0x33  # corrupt the header
    api = plugs.GoveePlugH5086.__new__(plugs.GoveePlugH5086)
    api._power_data = plugs.GoveePowerData(time_on=999)
    api._device = _FakeDevice()
    api._parse_power_response(frame)
    assert api._power_data.time_on == 999  # unchanged
