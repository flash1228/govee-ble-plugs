# Generic vs. bespoke device behavior

After the all-device refactor, the integration has two kinds of device API:

- **Bespoke** classes — hand-written, hardware-validated: the plugs (`GoveePlugH5080/82/83/86`)
  and the `GoveePlugH6163` light.
- **Generic** classes — data-driven from the extracted protocol: `GenericLightApi` (every other
  light SKU) and `GenericSensorApi` (thermo-hygrometers).

This documents where the generic path behaves differently from the bespoke one. **Plugs are
entirely bespoke and unchanged** (the registry just wraps them), so there is no plug diff. The
only device class with both kinds is **lights** (`GenericLightApi` vs. `GoveePlugH6163`).

## Lights: `GenericLightApi` vs. bespoke `GoveePlugH6163`

### Identical (verified)
- **Wire bytes.** on/off, brightness, RGB (`33 05 02 …00 FF AE 54`), colour-temp
  (`33 05 02 FF FF FF 01 …`) and the shared effect frames are byte-for-byte identical
  (asserted in `tests/test_codec.py` / `tests/test_generic_light.py`).
- **BLE transport.** `GenericLightApi` *subclasses* the same `GoveePlugH6xxx` message-queue
  transport, so connect/retry/idle-disconnect timing (`IDLE_DISCONNECT_SECONDS=1`,
  `CONNECT_TIMEOUT_SECONDS=12`, `MAX_COMMAND_ATTEMPTS=3`) is the same.
- **Optimistic state model**, colour-temp→RGB conversion, 0–255 brightness scale, and the
  visible effect list (13 effects) all match.

### Differences

| # | Aspect | Bespoke H6163 | Generic light | Impact |
|---|--------|---------------|---------------|--------|
| 1 | **Startup state seeding** | `async_query_status()` connects, subscribes to notify, and reads real on/off + brightness + colour (`aa 04`/`aa 05 01`/`aa 01`), seeding actual state after a restart | **Now equivalent** — `GenericLightApi.async_query_status()` does the same connect → notify → query sequence, codec-driven | Closed (was the main gap). Both recover state after a restart, link permitting. A device that doesn't answer the query just stays optimistic. |
| 2 | **Hidden effects** | `async_set_effect` also accepts `"Music - Rolling (Red)"` / `"(Blue)"` (settable via service call though not in the UI list) | Those two frames are not in `COMMON_EFFECTS`, so they're ignored | A `light.turn_on` service call with those exact effect names is a no-op on generic lights. The UI effect list (13) is identical. |
| 3 | **Pairing / config flow** | `requires_pairing=True` → config flow shows the vestigial "press button" link step (a no-op pairer that returns a dummy token) | `requires_pairing=False` → entry is created directly, no link step | Cleaner setup for generic lights. H6163 kept as-is to preserve behavior. |
| 4 | **Capabilities** | Fixed: RGB+COLOR_TEMP, 2000–9000 K, 13 effects (class attributes) | Derived from `LightCaps` per definition; today all generic lights use the same defaults, so the resulting HA attributes match H6163 (minus #2). A future per-model cap (e.g. white-only, or RGBIC segments) would diverge here. | None today; the mechanism exists for per-model variation. |
| 5 | **Logging / MODEL** | Logs as `H6163`; `MODEL` is the class constant | Logs via package logger; `MODEL` is the actual discovered SKU | Cosmetic. |

### Why H6163 stays bespoke
Its byte layouts are the proven reference the generic codec was validated against. Keeping it
bespoke is behavior-preserving — but now that the generic engine also seeds state (#1), the two
are functionally close enough that the generic-driver toggle is a faithful test of the generic
path (only differences #2–#3 remain, both minor).

## Sensors, RGBIC & appliances (generic-only — no bespoke counterpart)
- **Sensors** (`GenericSensorApi`): the only prior sensors were the H5086's power-monitoring
  entities (part of that bespoke *plug*). Broadcast-only, parsing the packed-24 `0xEC88`
  temp/hum/battery advert; never connects.
- **RGBIC** (`GenericLightApi` + `RgbicLightCodec`): per-segment colour via `0x05 15 01`; whole-
  strip = all segments. Exposed in HA as a normal light plus the `govee_ble_plugs.set_segment_color`
  service. No bespoke RGBIC ever existed.
- **Appliances** (`GenericApplianceApi`): on/off only (opcode `0x01`), optimistic, available on
  discovery. Mode/gear/ice-size (`0x05`) and feature switches are not yet implemented.

All three are new device classes, so there's nothing to diff against — they're entirely
generic and flagged `experimental`.

## Testing the generic driver on your own hardware

The H6163 has a **"Use generic driver (test)"** toggle in its device options
(Settings → Devices → the H6163 → Configure). With it on, the entry is reloaded through
`GenericLightApi` instead of the bespoke class, so you can A/B the generic path on a light you
actually own — in your real environment (ESPHome-proxy reachable), not a standalone script.
Default off = bespoke. The toggle only appears for lights that have a bespoke driver (today,
the H6163). Expect identical control; the visible difference is #1 (no real state seeding after
a restart while it's on).

## Verification status (important)
- **Hardware-confirmed (2026-06-30):** the generic light path was driven against a real **H6163**
  via the "Use generic driver" toggle and **controlled correctly** — validating `GenericLightApi`
  + `CommonLightCodec` (on/off, brightness, RGB, colour-temp) end-to-end on physical hardware.
  This is the common-set codec that the bulk of the experimental lights share, so it materially
  de-risks them — but it is one device, not per-SKU proof.
- **Hardware-confirmed (2026-06-30):** H6163 **per-segment colour** via the old-DreamColor
  `0x05 0B` command (`OldDreamColorCodec`, 15 segments) through the `govee_ble_plugs.set_segment_color`
  service.
- Still unconfirmed on hardware: the **newer** RGBIC path (`RgbicLightCodec`, `0x05 15`, used by
  the H61xx-era strips), the **appliance** on/off opcode per family, and **sensor** broadcast
  offsets for models whose layout differs. These stay `experimental=True` pending a device of each kind.
- The generic engines are also **unit-tested and byte-validated** against known byte vectors and
  the H6163 reference.
