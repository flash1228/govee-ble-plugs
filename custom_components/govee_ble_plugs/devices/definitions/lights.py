"""Light definitions.

H6163 keeps its hardware-validated bespoke class. Every other catalogued Govee light SKU is
registered as a generic, codec-driven common-set light (on/off, brightness, RGB, colour-temp,
and the shared built-in effect catalogue). RGBIC per-segment colour is a future per-family
codec; core control works on the common set today.

Lazy imports break the ``light -> entity -> coordinator -> devices`` cycle at registry-build
time.
"""
from __future__ import annotations

from ..capabilities import LightCaps
from ..codecs.dreamcolor import OldDreamColorCodec
from ..registry import DeviceDefinition, find_definition_by_model, register
from ._light_skus import LIGHT_SKUS, RGBIC_SKUS

# --- H6163: keep the bespoke, hardware-validated implementation ------------------------
_H6163_EFFECTS = (
    "Normal", "Music - Energetic", "Music - Spectrum (Red)", "Music - Spectrum (Blue)",
    "Music - Rolling (Red)", "Music - Rolling (Blue)", "Music - Rhythm", "Sunrise",
    "Sunset", "Movie", "Dating", "Romantic", "Blinking", "Candlelight", "Snowflake",
)


def _h6163_api(device, token, defn, model):
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
    caps=LightCaps(brightness=True, rgb=True, color_temp_k=(2000, 9000), segments=15, effects=_H6163_EFFECTS),
    api_factory=_h6163_api,
    pair_factory=_h6163_pair,
    requires_pairing=True,   # unchanged: keeps the existing (no-op) link step
    default_polling=False,
    experimental=False,
    # When forced onto the generic driver, use the old-DreamColor codec (15-seg, 0x0B).
    light_codec=OldDreamColorCodec,
))


# --- Generic common-set lights (everything else in the catalogue) ----------------------
def _generic_light_api(device, token, defn, model):
    from ..generic_light import GenericLightApi
    return GenericLightApi(device, token, defn, model)


def _rgbic_light_api(device, token, defn, model):
    from ..generic_light import GenericLightApi
    from ..codecs.rgbic import RgbicLightCodec
    return GenericLightApi(device, token, defn, model, codec=RgbicLightCodec)


# RGBIC (addressable, catalogue ic>0): per-segment colour via the RGBIC-native command.
_rgbic_models = tuple(
    s for s in LIGHT_SKUS if s in RGBIC_SKUS and find_definition_by_model(s) is None
)
register(DeviceDefinition(
    models=_rgbic_models,
    name_prefixes=(),
    category="light",
    caps=LightCaps(brightness=True, rgb=True, color_temp_k=(2000, 9000), segments=16),
    api_factory=_rgbic_light_api,
    pair_factory=None,
    requires_pairing=False,
    default_polling=False,
    experimental=True,
))

# Plain (non-segmented) lights: whole-strip colour via the legacy common command.
_plain_models = tuple(
    s for s in LIGHT_SKUS if s not in RGBIC_SKUS and find_definition_by_model(s) is None
)
register(DeviceDefinition(
    models=_plain_models,
    name_prefixes=(),  # discovered via broad manifest matchers + extract_sku
    category="light",
    caps=LightCaps(brightness=True, rgb=True, color_temp_k=(2000, 9000)),
    api_factory=_generic_light_api,
    pair_factory=None,        # BLE lights have no button-pairing token
    requires_pairing=False,
    default_polling=False,
    experimental=True,        # protocol-derived; not all hardware-verified
))
