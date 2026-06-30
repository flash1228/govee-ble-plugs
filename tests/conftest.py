"""Test session setup.

Runs before any test module is collected, so it can normalise sys.modules:

1. Import the real Home Assistant package first, so the per-test ``setdefault`` stubs
   (used to run pure-logic tests without HA) become harmless no-ops instead of shadowing
   real submodules like ``homeassistant.components.light``.
2. Stub ``aiousbwatcher`` — an optional HA-bluetooth transitive dependency not installed in
   a bare test venv — so modules that import the HA bluetooth stack can load.
"""
import sys
import types

if "aiousbwatcher" not in sys.modules:
    _usb = types.ModuleType("aiousbwatcher")
    _usb.InotifyNotAvailableError = type("InotifyNotAvailableError", (Exception,), {})
    _usb.AIOUSBWatcher = type("AIOUSBWatcher", (), {"__init__": lambda self, *a, **k: None})
    sys.modules["aiousbwatcher"] = _usb

try:  # real HA is present in CI / dev; bare-logic tests still work if it isn't
    import homeassistant  # noqa: F401
    import homeassistant.exceptions  # noqa: F401
except Exception:
    pass
