"""Data-driven Govee BLE device registry.

This package replaces the old per-model ``if/elif`` dispatch in ``plugs.py`` with a
declarative registry. Each device *family* is described once by a
:class:`~.registry.DeviceDefinition` (which SKUs / advertised-name prefixes it owns, its
capabilities, how to build its runtime API, whether it needs button-pairing, etc.).

The four dispatch entry points the rest of the integration uses
(``get_api_by_model``, ``get_pair_by_model``, ``parse_advertisement_data``,
``default_enable_polling``) are thin lookups over that registry, re-exported here so call
sites import from ``.devices`` instead of ``.plugs``.

Adding a new device later = add a ``DeviceDefinition`` (and a codec only if its protocol
deviates from the common set). Nothing else changes.
"""
from __future__ import annotations

# Importing .definitions populates the registry as a side effect.
from . import definitions as _definitions  # noqa: F401
from .registry import (
    DeviceDefinition,
    all_name_prefixes,
    default_enable_polling,
    find_definition_by_model,
    get_api_by_model,
    get_pair_by_model,
    iter_definitions,
    parse_advertisement_data,
    extract_sku,
)

__all__ = [
    "DeviceDefinition",
    "all_name_prefixes",
    "default_enable_polling",
    "extract_sku",
    "find_definition_by_model",
    "get_api_by_model",
    "get_pair_by_model",
    "iter_definitions",
    "parse_advertisement_data",
]
