"""Capability descriptors for a Govee device family.

A definition's ``caps`` is one of these (or a tuple of them, for a device that is both —
e.g. a plug that also exposes a night-light). The capability-probing platforms
(``switch``/``light``/``sensor``) read these to decide which entities to create and how to
configure them, instead of hard-coding per-model behaviour.
"""
from __future__ import annotations

import dataclasses
from typing import Optional


@dataclasses.dataclass(frozen=True)
class SwitchCaps:
    """One or more on/off outlets.

    ``ports`` mirrors the existing ``api.port_names()`` shape: a list of
    ``(port_index, port_name)``. ``(None, None)`` means a single unnamed switch (the
    original H5080 entity), preserved for unique-id backwards compatibility.
    """

    ports: tuple[tuple[Optional[int], Optional[str]], ...] = ((None, None),)
    power_monitoring: bool = False  # H5086-style voltage/current/power/energy sensors


@dataclasses.dataclass(frozen=True)
class LightCaps:
    """A controllable light.

    ``color_temp_k`` is the (min, max) kelvin range, or ``None`` if the light has no
    tunable white. ``segments`` > 0 marks an RGBIC light with per-segment colour.
    ``effects`` is a curated, static effect-name list (the human-readable scene catalogue
    is cloud-side, so this is best-effort); applying an effect by code still works even if
    a device's real catalogue differs.
    """

    brightness: bool = True
    rgb: bool = True
    color_temp_k: Optional[tuple[int, int]] = (2000, 9000)
    segments: int = 0
    effects: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class SensorCaps:
    """Read-only metrics parsed from BLE advertisements (and/or connected reads).

    ``metrics`` are stable keys the sensor platform maps to HA SensorEntityDescriptions,
    e.g. ``"temperature"``, ``"humidity"``, ``"battery"``, ``"pm25"``, ``"co2"``.
    """

    metrics: tuple[str, ...] = ()
