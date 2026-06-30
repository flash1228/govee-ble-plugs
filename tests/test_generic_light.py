"""Behaviour tests for the generic, codec-driven light API.

Verifies it emits the same frames as CommonLightCodec and tracks optimistic state. The BLE
transport is monkeypatched out (we assert on the bytes handed to ``_send_message``).
"""
import asyncio
import importlib
import os
import sys
import types

PKG = "govee_ble_plugs"
_PKGDIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "govee_ble_plugs")
)

# Defensive stubs: no-ops if the real packages are installed (full HA env).
sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
_exc = types.ModuleType("homeassistant.exceptions")
_exc.ConfigEntryError = type("ConfigEntryError", (Exception,), {})
sys.modules.setdefault("homeassistant.exceptions", _exc)
# aiousbwatcher is an HA-bluetooth transitive dep not always present in a bare venv.
if "aiousbwatcher" not in sys.modules:
    _usb = types.ModuleType("aiousbwatcher")
    _usb.InotifyNotAvailableError = type("InotifyNotAvailableError", (Exception,), {})
    _usb.AIOUSBWatcher = type("AIOUSBWatcher", (), {"__init__": lambda self, *a, **k: None})
    sys.modules["aiousbwatcher"] = _usb

if PKG not in sys.modules:
    _pkg = types.ModuleType(PKG)
    _pkg.__path__ = [_PKGDIR]
    sys.modules[PKG] = _pkg

try:
    generic_light = importlib.import_module(f"{PKG}.devices.generic_light")
    capabilities = importlib.import_module(f"{PKG}.devices.capabilities")
    common_light = importlib.import_module(f"{PKG}.devices.codecs.common_light")
    _IMPORT_OK = True
except Exception as _e:  # pragma: no cover - environment lacks HA bluetooth stack
    _IMPORT_OK = False
    _IMPORT_ERR = _e

import pytest

pytestmark = pytest.mark.skipif(not _IMPORT_OK, reason="HA bluetooth stack unavailable")


class _FakeDevice:
    name = "Fake"
    address = "AA:BB:CC:DD:EE:FF"


class _FakeDefn:
    def __init__(self, caps):
        self.caps = caps


def _make_api():
    GenericLightApi = generic_light.GenericLightApi
    LightCaps = capabilities.LightCaps
    api = GenericLightApi(_FakeDevice(), None, _FakeDefn(LightCaps()), "H6159")
    sent = []

    async def fake_send(msg):
        sent.append(msg)
        return True

    api._send_message = fake_send
    return api, sent


def test_metadata():
    api, _ = _make_api()
    assert api.MODEL == "H6159"
    assert api.port_names() == []
    assert api.has_light() is True
    assert api.supports_power_monitoring() is False


def test_commands_emit_codec_frames():
    api, sent = _make_api()
    C = common_light.CommonLightCodec
    asyncio.run(api.async_turn_on(0))
    asyncio.run(api.async_set_light_brightness(200))
    asyncio.run(api.async_set_light_rgb((10, 20, 30)))
    asyncio.run(api.async_turn_off(0))
    assert sent == [C.power(True), C.brightness(200), C.rgb(10, 20, 30), C.power(False)]
    assert api._is_on is False
    assert api._rgb == (10, 20, 30)
    assert api._brightness == 200


def test_color_temp_and_effects():
    api, sent = _make_api()
    asyncio.run(api.async_set_light_color_temp(4000))
    assert api.get_color_mode() == "color_temp"
    assert api.get_color_temp_kelvin() == 4000

    asyncio.run(api.async_set_effect("Movie"))
    assert api._effect == "Movie"
    assert sent[-1] == common_light.CommonLightCodec.effect("Movie")

    # Unknown effect is ignored (no send, no state change).
    before = list(sent)
    asyncio.run(api.async_set_effect("Nonexistent"))
    assert sent == before


def test_light_caps_fills_effects_from_codec():
    api, _ = _make_api()
    caps = api.light_caps()
    assert "Movie" in caps.effects and "Normal" in caps.effects
    # Only codec-emittable effects are exposed (no "Rolling" no-ops).
    assert "Music - Rolling (Red)" not in caps.effects


def test_prefer_generic_routes_bespoke_light_to_generic():
    devices = importlib.import_module(f"{PKG}.devices")
    gen = devices.get_api_by_model("H6163", _FakeDevice(), "", prefer_generic=True)
    assert type(gen).__name__ == "GenericLightApi"
    besp = devices.get_api_by_model("H6163", _FakeDevice(), "", prefer_generic=False)
    assert type(besp).__name__ == "GoveePlugH6163"
    # Plugs ignore prefer_generic (category != light).
    plug = devices.get_api_by_model("H5080", _FakeDevice(), "tok", prefer_generic=True)
    assert type(plug).__name__ == "GoveePlugH5080"
