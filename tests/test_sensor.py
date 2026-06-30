"""Tests for the broadcast sensor codec and the generic sensor API."""
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

sensor_codec = importlib.import_module(f"{PKG}.devices.codecs.sensor")
generic_sensor = importlib.import_module(f"{PKG}.devices.generic_sensor")
capabilities = importlib.import_module(f"{PKG}.devices.capabilities")

EC88 = sensor_codec.GOVEE_COMPANY_ID  # 0xEC88


# ---- codec: packed-24 temp/hum/battery (canonical H5075) -------------------------------
def test_parse_th_positive():
    # data[1:4] = 03 41 8b -> raw 213387 -> 21.3C / 38.7% ; data[4]=0x64 battery 100
    out = sensor_codec.parse_th_broadcast({EC88: bytes.fromhex("0003418b6400")})
    assert out == {"temperature": 21.3, "humidity": 38.7, "battery": 100}


def test_parse_th_negative_temp():
    # raw 50500 with sign bit -> -5.0C / 50.0% ; battery 0x5a = 90
    out = sensor_codec.parse_th_broadcast({EC88: bytes.fromhex("0080c5445a")})
    assert out == {"temperature": -5.0, "humidity": 50.0, "battery": 90}


def test_parse_th_invalid_returns_none():
    assert sensor_codec.parse_th_broadcast({EC88: bytes.fromhex("00ffffff64")}) is None
    assert sensor_codec.parse_th_broadcast({}) is None
    assert sensor_codec.parse_th_broadcast({0x1234: bytes.fromhex("0003418b6400")}) is None


# ---- generic sensor api ---------------------------------------------------------------
class _Dev:
    name = "TH"
    address = "AA:BB:CC:00:00:01"


class _Adv:
    def __init__(self, mfr):
        self.manufacturer_data = mfr


class _Defn:
    caps = capabilities.SensorCaps(metrics=("temperature", "humidity", "battery"))


def test_generic_sensor_parses_and_exposes_metrics():
    api = generic_sensor.GenericSensorApi(_Dev(), None, _Defn(), "H5075")
    assert api.MODEL == "H5075"
    assert api.has_light() is False
    assert api.port_names() == []
    assert api.is_on(0) is None
    assert api.get_sensor_values() == {}

    api.handle_bluetooth_event(_Dev(), _Adv({EC88: bytes.fromhex("0003418b6400")}))
    vals = api.get_sensor_values()
    assert vals == {"temperature": 21.3, "humidity": 38.7, "battery": 100}
    assert set(api.sensor_metrics()) == {"temperature", "humidity", "battery"}


def test_generic_sensor_ignores_unparseable_advert():
    api = generic_sensor.GenericSensorApi(_Dev(), None, _Defn(), "H5075")
    api.handle_bluetooth_event(_Dev(), _Adv({0x9999: b"\x01\x02\x03"}))
    assert api.get_sensor_values() == {}
