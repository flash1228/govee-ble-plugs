"""Config-entry migrations.

minor 1 -> 2 disables the H5086 power-factor entity on installs that predate it becoming
a disabled-by-default diagnostic. The registry is faked: the real one needs a running hass,
and everything under test here is the selection logic plus the once-only version bump.
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
if PKG not in sys.modules:
    _pkg = types.ModuleType(PKG)
    _pkg.__path__ = [_PKGDIR]
    sys.modules[PKG] = _pkg

init = importlib.import_module(f"{PKG}.__init__")
const = importlib.import_module(f"{PKG}.const")

DISABLER = init.er.RegistryEntryDisabler


class _RegEntry:
    def __init__(self, entity_id, unique_id, disabled_by=None):
        self.entity_id = entity_id
        self.unique_id = unique_id
        self.disabled_by = disabled_by


class _Registry:
    def __init__(self, entries):
        self.entries = entries

    def async_update_entity(self, entity_id, **changes):
        for e in self.entries:
            if e.entity_id == entity_id:
                for k, v in changes.items():
                    setattr(e, k, v)


class _ConfigEntries:
    def async_update_entry(self, entry, **changes):
        for k, v in changes.items():
            setattr(entry, k, v)


class _Hass:
    def __init__(self):
        self.config_entries = _ConfigEntries()


class _Entry:
    entry_id = "abc123"

    def __init__(self, version=1, minor_version=1):
        self.version = version
        self.minor_version = minor_version


def _migrate(monkeypatch, entries, entry):
    reg = _Registry(entries)
    monkeypatch.setattr(init.er, "async_get", lambda hass: reg)
    monkeypatch.setattr(
        init.er, "async_entries_for_config_entry", lambda registry, entry_id: registry.entries
    )
    ok = asyncio.run(init.async_migrate_entry(_Hass(), entry))
    return ok, entries


def test_flow_stamps_new_entries_past_the_migration():
    """New entries are stamped with these, so the sweep below never runs on a fresh
    install. Drop MINOR back to 1 and every new H5086 would get migrated on first load."""
    assert const.CONFIG_ENTRY_VERSION == 1
    assert const.CONFIG_ENTRY_MINOR_VERSION == 2


def test_migration_disables_power_factor(monkeypatch):
    pf = _RegEntry("sensor.plug_power_factor", "AA:BB:CC:00:00:01-power_factor")
    power = _RegEntry("sensor.plug_power", "AA:BB:CC:00:00:01-power")
    entry = _Entry(minor_version=1)

    ok, _ = _migrate(monkeypatch, [pf, power], entry)

    assert ok is True
    assert pf.disabled_by is DISABLER.INTEGRATION
    assert power.disabled_by is None       # only the power-factor entity is touched
    assert entry.minor_version == 2        # ...and the entry is stamped so it won't re-run


def test_migration_leaves_user_disabled_entity_alone(monkeypatch):
    """Already disabled by the user: don't rewrite the reason."""
    pf = _RegEntry(
        "sensor.plug_power_factor", "AA:BB:CC:00:00:01-power_factor", disabled_by=DISABLER.USER
    )
    ok, _ = _migrate(monkeypatch, [pf], _Entry(minor_version=1))
    assert ok is True
    assert pf.disabled_by is DISABLER.USER


def test_migration_is_a_noop_once_stamped(monkeypatch):
    """A user who re-enables the sensor after migrating keeps it: the sweep runs once."""
    pf = _RegEntry("sensor.plug_power_factor", "AA:BB:CC:00:00:01-power_factor")
    ok, _ = _migrate(monkeypatch, [pf], _Entry(minor_version=2))
    assert ok is True
    assert pf.disabled_by is None


def test_migration_refuses_future_major_version(monkeypatch):
    pf = _RegEntry("sensor.plug_power_factor", "AA:BB:CC:00:00:01-power_factor")
    ok, _ = _migrate(monkeypatch, [pf], _Entry(version=2, minor_version=1))
    assert ok is False
    assert pf.disabled_by is None


def test_migration_tolerates_missing_unique_id(monkeypatch):
    """Registry entries can carry unique_id=None; the sweep must not raise on them."""
    orphan = _RegEntry("sensor.plug_orphan", None)
    pf = _RegEntry("sensor.plug_power_factor", "AA:BB:CC:00:00:01-power_factor")
    ok, _ = _migrate(monkeypatch, [orphan, pf], _Entry(minor_version=1))
    assert ok is True
    assert pf.disabled_by is DISABLER.INTEGRATION
