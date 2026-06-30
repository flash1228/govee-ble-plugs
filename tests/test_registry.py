"""Registry tests: SKU extraction, lookups, and manifest/registry consistency."""
import importlib
import json
import os
import sys
import types

PKG = "govee_ble_plugs"
_PKGDIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "govee_ble_plugs")
)

# Defensive HA stub (no-op if HA is actually installed).
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

registry = importlib.import_module(f"{PKG}.devices.registry")
devices = importlib.import_module(f"{PKG}.devices")


# ---- SKU extraction -------------------------------------------------------------------
def test_extract_sku_underscore_schemes():
    assert registry.extract_sku("ihoment_H5080_AB12") == "H5080"
    assert registry.extract_sku("Govee_H6163_1F2E") == "H6163"
    assert registry.extract_sku("Minger_H6199_0001") == "H6199"
    assert registry.extract_sku("GBK_H6104_7799") == "H6104"


def test_extract_sku_gv_schemes():
    assert registry.extract_sku("GVH5086") == "H5086"
    assert registry.extract_sku("GVH6159_AB12") == "H6159"
    assert registry.extract_sku("GV5080xyz") == "H5080"  # GV + 4 digits -> H####


def test_extract_sku_none():
    assert registry.extract_sku("") is None
    assert registry.extract_sku(None) is None
    assert registry.extract_sku("RandomDevice") is None


# ---- registry population & lookups ----------------------------------------------------
def test_all_five_models_registered():
    models = {m for d in devices.iter_definitions() for m in d.models}
    assert {"H5080", "H5082", "H5083", "H5086", "H6163"} <= models


def test_find_definition_by_model_and_name():
    assert devices.find_definition_by_model("H5086").category == "plug"
    assert devices.find_definition_by_model("H6163").category == "light"
    assert devices.find_definition_by_model("HZZZZ") is None
    defn = registry.find_definition_by_name("ihoment_H5080_AB12")
    assert defn is not None and "H5080" in defn.models


def test_polling_defaults():
    assert devices.default_enable_polling("H5086") is True
    assert devices.default_enable_polling("H5080") is False
    assert devices.default_enable_polling("Unknown") is False


def test_caps_shapes():
    light = devices.find_definition_by_model("H6163").caps
    assert light.rgb and light.brightness and light.color_temp_k == (2000, 9000)
    h5086 = devices.find_definition_by_model("H5086").caps
    assert h5086.power_monitoring is True


# ---- manifest <-> registry consistency ------------------------------------------------
def test_manifest_matchers_cover_registry_prefixes():
    """Every registered name prefix must be covered by some manifest bluetooth matcher,
    so registered families are actually discovered. Matchers may be broad (``GVH*``)."""
    with open(os.path.join(_PKGDIR, "manifest.json")) as f:
        manifest = json.load(f)
    globs = [m.get("local_name", "").rstrip("*") for m in manifest.get("bluetooth", [])]
    for prefix in devices.all_name_prefixes():
        assert any(prefix.startswith(g) for g in globs), \
            f"no manifest bluetooth matcher covers {prefix!r}"


def test_generic_light_sku_resolves_to_generic_api():
    """A catalogued light SKU not otherwise claimed resolves to the generic light family."""
    defn = devices.find_definition_by_model("H6159")
    assert defn is not None and defn.category == "light"
    assert defn.requires_pairing is False
    # H6163 stays bespoke (its own definition), not the generic family.
    assert "H6163" not in defn.models
