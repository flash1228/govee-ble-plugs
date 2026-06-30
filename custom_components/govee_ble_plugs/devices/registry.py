"""The device registry: definitions, lookups, and the public dispatch functions."""
from __future__ import annotations

import dataclasses
import logging
import re
from typing import TYPE_CHECKING, Any, Callable, Iterable, Optional

from homeassistant.exceptions import ConfigEntryError

if TYPE_CHECKING:  # avoid importing the HA-heavy / bleak modules at import time
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData

_LOGGER = logging.getLogger(__name__)

# api_factory(device, token, definition) -> a GoveePlugApi-conforming object
ApiFactory = Callable[["BLEDevice", Optional[str], "DeviceDefinition"], Any]
# pair_factory(device, definition) -> a GoveePairApi-conforming object
PairFactory = Callable[["BLEDevice", "DeviceDefinition"], Any]


@dataclasses.dataclass(frozen=True)
class DeviceDefinition:
    """Declarative description of one Govee BLE device family."""

    models: tuple[str, ...]
    name_prefixes: tuple[str, ...]
    category: str  # "plug" | "light" | "sensor"
    caps: Any  # SwitchCaps | LightCaps | SensorCaps | tuple[...]
    api_factory: ApiFactory
    pair_factory: Optional[PairFactory] = None
    requires_pairing: bool = False
    default_polling: bool = False
    experimental: bool = True
    display_model: Optional[str] = None

    def matches_model(self, model: str) -> bool:
        return model.upper() in {m.upper() for m in self.models}

    def matches_name(self, local_name: str) -> bool:
        return any(local_name.startswith(p) for p in self.name_prefixes)


_REGISTRY: list[DeviceDefinition] = []


def register(defn: DeviceDefinition) -> DeviceDefinition:
    """Add a definition to the registry. Called by the modules in ``definitions/``."""
    _REGISTRY.append(defn)
    return defn


def iter_definitions() -> Iterable[DeviceDefinition]:
    return tuple(_REGISTRY)


def find_definition_by_model(model: str) -> Optional[DeviceDefinition]:
    for defn in _REGISTRY:
        if defn.matches_model(model):
            return defn
    return None


def find_definition_by_name(local_name: str) -> Optional[DeviceDefinition]:
    for defn in _REGISTRY:
        if defn.matches_name(local_name):
            return defn
    return None


def all_name_prefixes() -> tuple[str, ...]:
    """Every advertised-name prefix across the registry (used to derive manifest matchers)."""
    prefixes: list[str] = []
    for defn in _REGISTRY:
        prefixes.extend(defn.name_prefixes)
    return tuple(sorted(set(prefixes)))


# --- SKU extraction from an advertised local name --------------------------------------
#
# Govee/Ihoment advertise under several naming schemes (see GOVEE_BLE_PROTOCOL.md §5.2):
#   ihoment_H5080_AB12 / Govee_H6163_XXXX / Minger_HXXXX_  -> underscore-split[1]
#   GBK_HXXXX_...                                          -> underscore-split[1]
#   GVH5086 / GVHxxxx                                      -> strip "GV" -> "H5086"
#   GV5080... (V3)                                         -> "H" + 4 digits after "GV"
_UNDERSCORE_PREFIXES = ("ihoment_", "Govee_", "Minger_", "GBK_")
_SKU_RE = re.compile(r"^[HhRr]\d{3,4}[A-Za-z0-9]*$")


def extract_sku(local_name: Optional[str]) -> Optional[str]:
    """Best-effort SKU (e.g. ``"H5080"``) from a BLE advertised name."""
    if not local_name:
        return None
    name = local_name

    for pref in _UNDERSCORE_PREFIXES:
        if name.startswith(pref):
            rest = name[len(pref):]
            token = rest.split("_", 1)[0]
            return token.upper() if token else None

    if name.startswith("GV"):
        rest = name[2:]
        token = rest.split("_", 1)[0]
        if token[:1] in ("H", "h", "R", "r") and _SKU_RE.match(token):
            return token.upper()
        # GV<4 digits>...  ->  H<4 digits>
        digits = re.match(r"(\d{4})", token)
        if digits:
            return "H" + digits.group(1)

    # Fall back: a bare SKU-looking token anywhere.
    for token in re.split(r"[_\- ]", name):
        if _SKU_RE.match(token):
            return token.upper()
    return None


# --- Public dispatch (re-exported from devices/__init__.py) -----------------------------


def get_api_by_model(model: str, device: "BLEDevice", token: Optional[str]) -> Any:
    defn = find_definition_by_model(model)
    if defn is None:
        raise ConfigEntryError(f"Unsupported model {model}")
    return defn.api_factory(device, token, defn)


def get_pair_by_model(model: str, device: "BLEDevice") -> Any:
    defn = find_definition_by_model(model)
    if defn is None:
        raise ConfigEntryError(f"Unsupported model {model}")
    if defn.pair_factory is None:
        raise ConfigEntryError(f"Model {model} does not support pairing")
    return defn.pair_factory(device, defn)


def default_enable_polling(model: str) -> bool:
    defn = find_definition_by_model(model)
    return bool(defn.default_polling) if defn else False


def parse_advertisement_data(device: "BLEDevice", adv: "AdvertisementData") -> Any:
    """Map a discovered advertisement to a GoveeAdvertisementData, or ``None``.

    Resolution order: exact SKU from the advertised name, then name-prefix family match
    (so a long-tail SKU still resolves to its family even if not individually enumerated).
    """
    from ..plugs import GoveeAdvertisementData  # local import: avoid import cycle

    local_name = adv.local_name
    if not local_name:
        return None

    sku = extract_sku(local_name)
    defn = find_definition_by_model(sku) if sku else None
    if defn is None:
        defn = find_definition_by_name(local_name)
    if defn is None:
        return None

    model = sku if (sku and defn.matches_model(sku)) else defn.models[0]
    return GoveeAdvertisementData(local_name, device.address, device, model)
