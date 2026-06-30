"""Light definitions.

The existing H6163 keeps its bespoke class (validated on hardware). Its factories import
``light.py`` lazily because ``light.py`` -> ``entity`` -> ``coordinator`` -> ``devices``
would otherwise form an import cycle at registry-population time.

Future light families (sub-project 2) register here too, most of them pointing at the
generic light API + ``CommonLightCodec`` rather than a bespoke class.
"""
from __future__ import annotations

from ..capabilities import LightCaps
from ..registry import DeviceDefinition, register

# Effect catalogue the bespoke H6163 already supports (see light.py async_set_effect).
_H6163_EFFECTS = (
    "Normal", "Music - Energetic", "Music - Spectrum (Red)", "Music - Spectrum (Blue)",
    "Music - Rolling (Red)", "Music - Rolling (Blue)", "Music - Rhythm", "Sunrise",
    "Sunset", "Movie", "Dating", "Romantic", "Blinking", "Candlelight", "Snowflake",
)


def _h6163_api(device, token, defn):
    from ...light import GoveePlugH6163
    return GoveePlugH6163(device, token)


def _h6163_pair(device, defn):
    from ...light import GoveePlugH6163
    from ...plugs import NoOpPlugPairer
    return NoOpPlugPairer(
        device,
        GoveePlugH6163.RECV_CHARACTERISTIC_UUID,
        GoveePlugH6163.SEND_CHARACTERISTIC_UUID,
        GoveePlugH6163.MSG_GET_AUTH_KEY,
    )


register(DeviceDefinition(
    models=("H6163",),
    name_prefixes=("ihoment_H6163_",),
    category="light",
    caps=LightCaps(brightness=True, rgb=True, color_temp_k=(2000, 9000), effects=_H6163_EFFECTS),
    api_factory=_h6163_api,
    pair_factory=_h6163_pair,
    requires_pairing=True,   # unchanged: keeps the existing (no-op) link step
    default_polling=False,
    experimental=False,
))
