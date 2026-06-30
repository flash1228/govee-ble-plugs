"""Smart-plug definitions (H5080/H5082/H5083/H5086).

These wrap the existing, hardware-validated bespoke plug classes in ``plugs.py`` — the
registry refactor is behaviour-preserving for them. ``plugs.py`` is a leaf module (it does
not import ``devices``/``coordinator``), so importing the classes here at module load is
cycle-free.
"""
from __future__ import annotations

from ...plugs import (
    GoveePlugH5080,
    GoveePlugH5082,
    GoveePlugH5083,
    GoveePlugH5086,
    GoveePlugPairer,
)
from ..capabilities import SwitchCaps
from ..registry import DeviceDefinition, register


def _api(cls):
    def factory(device, token, defn):
        return cls(device, token)
    return factory


def _pairer(cls):
    def factory(device, defn):
        return GoveePlugPairer(
            device,
            cls.RECV_CHARACTERISTIC_UUID,
            cls.SEND_CHARACTERISTIC_UUID,
            cls.MSG_GET_AUTH_KEY,
        )
    return factory


# Single-outlet relay plugs (post-OTA H5080 uses the encrypted session path internally).
for _cls, _prefix in (
    (GoveePlugH5080, "ihoment_H5080_"),
    (GoveePlugH5082, "ihoment_H5082_"),
    (GoveePlugH5083, "ihoment_H5083_"),
):
    register(DeviceDefinition(
        models=(_cls.MODEL,),
        name_prefixes=(_prefix,),
        category="plug",
        caps=SwitchCaps(),
        api_factory=_api(_cls),
        pair_factory=_pairer(_cls),
        requires_pairing=True,
        default_polling=False,
        experimental=False,
    ))

# H5086 Smart Plug Pro — energy monitoring; benefits from active polling.
register(DeviceDefinition(
    models=(GoveePlugH5086.MODEL,),
    name_prefixes=("GVH5086",),
    category="plug",
    caps=SwitchCaps(power_monitoring=True),
    api_factory=_api(GoveePlugH5086),
    pair_factory=_pairer(GoveePlugH5086),
    requires_pairing=True,
    default_polling=True,
    experimental=False,
))
