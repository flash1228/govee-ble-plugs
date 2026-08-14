"""Appliance definitions — Kitchen Electronic + Air Treatment on/off switches.

Registered as a single power switch per device (opcode 0x01). Mode/gear/ice-size control is a
future enhancement. Experimental: protocol-derived, not hardware-verified per SKU.
"""
from __future__ import annotations

from ..capabilities import SwitchCaps
from ..registry import DeviceDefinition, find_definition_by_model, register
from ._appliance_skus import APPLIANCE_SKUS


def _appliance_api(device, token, defn, model):
    from ..generic_appliance import GenericApplianceApi
    return GenericApplianceApi(device, token, defn, model)


_models = tuple(s for s in APPLIANCE_SKUS if find_definition_by_model(s) is None)

register(DeviceDefinition(
    models=_models,
    name_prefixes=(),  # discovered via broad manifest matchers + extract_sku
    category="appliance",
    caps=SwitchCaps(),
    api_factory=_appliance_api,
    pair_factory=None,
    requires_pairing=False,
    default_polling=False,
    experimental=True,
))
