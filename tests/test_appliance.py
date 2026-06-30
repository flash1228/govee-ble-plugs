"""Behaviour tests for the generic appliance (on/off) API."""
import asyncio
import importlib
import os
import sys
import types

PKG = "govee_ble_plugs"
_PKGDIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "govee_ble_plugs")
)

sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
_exc = types.ModuleType("homeassistant.exceptions")
_exc.ConfigEntryError = type("ConfigEntryError", (Exception,), {})
sys.modules.setdefault("homeassistant.exceptions", _exc)
if "aiousbwatcher" not in sys.modules:
    _usb = types.ModuleType("aiousbwatcher")
    _usb.InotifyNotAvailableError = type("InotifyNotAvailableError", (Exception,), {})
    _usb.AIOUSBWatcher = type("AIOUSBWatcher", (), {"__init__": lambda self, *a, **k: None})
    sys.modules["aiousbwatcher"] = _usb

if PKG not in sys.modules:
    _pkg = types.ModuleType(PKG)
    _pkg.__path__ = [_PKGDIR]
    sys.modules[PKG] = _pkg

import pytest

try:
    devices = importlib.import_module(f"{PKG}.devices")
    common_light = importlib.import_module(f"{PKG}.devices.codecs.common_light")
    _OK = True
except Exception as _e:  # pragma: no cover
    _OK = False

pytestmark = pytest.mark.skipif(not _OK, reason="HA bluetooth stack unavailable")


class _Dev:
    name = "Appliance"
    address = "AA:BB:CC:00:00:07"


def test_appliance_sku_resolves_and_controls():
    defn = devices.find_definition_by_model("H7160")  # humidifier
    assert defn is not None and defn.category == "appliance"

    api = devices.get_api_by_model("H7160", _Dev(), "")
    assert type(api).__name__ == "GenericApplianceApi"
    assert api.MODEL == "H7160"
    assert api.port_names() == [(None, None)]
    assert api.has_light() is False
    assert api.supports_power_monitoring() is False
    assert getattr(api, "optimistic_switch", False) is True

    sent = []

    async def fake_send(msg):
        sent.append(msg)
        return True

    api._send_message = fake_send
    asyncio.run(api.async_turn_on(0))
    asyncio.run(api.async_turn_off(0))
    assert sent == [common_light.CommonLightCodec.power(True), common_light.CommonLightCodec.power(False)]
    assert api.is_on(0) is False


def test_ice_maker_and_kettle_are_appliances():
    for sku in ("H7172", "H7130", "H8120"):
        defn = devices.find_definition_by_model(sku)
        assert defn is not None and defn.category == "appliance", sku
