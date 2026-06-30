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
| 1 | **Startup state seeding** | `async_query_status()` connects, subscribes to notify, and reads real on/off + brightness + colour (`33 00`/`aa 04`/`aa 05`), seeding actual state after a restart | `async_query_status()` returns `False` — **optimistic only**; state is unknown until the first command | **Main functional gap.** After an HA restart a generic light shows no real on/off/brightness/colour until you control it; H6163 recovers it (link permitting). The light is still *available* in both cases. |
| 2 | **Hidden effects** | `async_set_effect` also accepts `"Music - Rolling (Red)"` / `"(Blue)"` (settable via service call though not in the UI list) | Those two frames are not in `COMMON_EFFECTS`, so they're ignored | A `light.turn_on` service call with those exact effect names is a no-op on generic lights. The UI effect list (13) is identical. |
| 3 | **Pairing / config flow** | `requires_pairing=True` → config flow shows the vestigial "press button" link step (a no-op pairer that returns a dummy token) | `requires_pairing=False` → entry is created directly, no link step | Cleaner setup for generic lights. H6163 kept as-is to preserve behavior. |
| 4 | **Capabilities** | Fixed: RGB+COLOR_TEMP, 2000–9000 K, 13 effects (class attributes) | Derived from `LightCaps` per definition; today all generic lights use the same defaults, so the resulting HA attributes match H6163 (minus #2). A future per-model cap (e.g. white-only, or RGBIC segments) would diverge here. | None today; the mechanism exists for per-model variation. |
| 5 | **Logging / MODEL** | Logs as `H6163`; `MODEL` is the class constant | Logs via package logger; `MODEL` is the actual discovered SKU | Cosmetic. |

### Why H6163 stays bespoke
Its byte layouts are the proven reference the generic codec was validated against, and it has a
real status-read path (#1) the generic engine doesn't replicate. Keeping it bespoke is
behavior-preserving; it could be re-expressed through `GenericLightApi` later, at which point it
would inherit differences #1–#3 (notably losing real status seeding) — which is exactly why it
wasn't.

## Sensors
`GenericSensorApi` has **no bespoke counterpart** (the only prior sensors were the H5086's
power-monitoring entities, which belong to that bespoke *plug*). So there's nothing to diff: it
is broadcast-only, parsing the packed-24 `0xEC88` temp/hum/battery advert, and never connects.

## Testing the generic driver on your own hardware

The H6163 has a **"Use generic driver (test)"** toggle in its device options
(Settings → Devices → the H6163 → Configure). With it on, the entry is reloaded through
`GenericLightApi` instead of the bespoke class, so you can A/B the generic path on a light you
actually own — in your real environment (ESPHome-proxy reachable), not a standalone script.
Default off = bespoke. The toggle only appears for lights that have a bespoke driver (today,
the H6163). Expect identical control; the visible difference is #1 (no real state seeding after
a restart while it's on).

## Verification status (important)
- The generic engines are **unit-tested and byte-validated** against the extracted spec and the
  H6163 reference, but **not hardware-validated** — the only physically-owned devices (plugs,
  H6163) remain on their unchanged bespoke paths. Every generic light/sensor definition is flagged
  `experimental=True`. Real-hardware confirmation per family is the follow-up.
