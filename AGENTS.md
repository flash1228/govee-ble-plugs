# Govee BLE Plugs — Agent Instructions

## Repo
Home Assistant custom integration for local BLE control of Govee devices (plugs, lights, sensors, appliances). HACS category: Integration. Domain: `govee_ble_plugs`.

## Developer commands
```
pip install -r tests/requirements.txt    # one-time setup
pytest -q tests                          # run all tests
pytest -q tests/test_foo.py              # single test file
```
CI uses Python 3.13. Lint is `black` only (`.github/workflows/lint.yml`). Validation is `hassfest` + `hacs` (GitHub-only).

## Architecture overview
- **Data-driven device registry** — `custom_components/govee_ble_plugs/devices/`
  - `definitions/` — declarative SKU lists + `DeviceDefinition` registrations (side-effect of importing `.definitions`)
  - `codecs/` — pure-bytes protocol encoders/decoders (testable without hardware; `tests/test_codec.py` mounts the package dir as a stub)
  - `registry.py` — lookup/dispatch (`get_api_by_model`, `parse_advertisement_data`, `extract_sku`)
- **Entry points** — `__init__.py` (platform setup), `coordinator.py` (BLE passive listening + polling), `config_flow.py` (discovery/pairing/options)
- **Platforms** — `switch.py`, `light.py`, `sensor.py` (forwarded from `__init__.py` via `async_forward_entry_setups`)
- **BLE transport** — `plugs.py` (Bleak client, connection pooling via `bleak-retry-connector`), `session.py` (encrypted session for newer H5080 firmware)
- **Devices** — `generic_light.py`, `generic_appliance.py`, `generic_sensor.py` (data-driven paths); bespoke classes in `plugs.py` (H5080/82/83/86 plugs, H6163 light)

## Adding a new device
1. Add SKU(s) to the appropriate `_*_skus.py` in `devices/definitions/` (or create a new one).
2. Register a `DeviceDefinition` in the matching `devices/definitions/<category>.py` module — this populates the registry as a side effect.
3. If the device uses a new protocol, add a codec in `devices/codecs/`. Most lights share `CommonLightCodec`.

## Testing quirks
- Tests use a `conftest.py` stub for `aiousbwatcher` (not installed in bare venvs) and optionally import `homeassistant` if present.
- Codec tests (`test_codec.py`, `test_generic_light.py`) mount the package as a stub module to avoid HA import overhead — they are pure byte-vector tests.
- No hardware needed for codec tests; real BLE required for integration-level verification.

## Known gotchas
- **H5080 encrypted firmware** (OTA ~1.00.28): plugs on this firmware need re-pairing after removing. The integration auto-detects old vs new protocol.
- **Pairing (plugs only)**: physical button short-press required during config flow to obtain auth token. Lights/sensors/appliances configure directly.
- **H6163 generic-driver toggle**: device options → "Use generic driver (test)" routes the H6163 through `GenericLightApi` instead of its bespoke driver. Default off. See `docs/generic-vs-bespoke.md`.
- **BLE proxies** (ESPHome/Shelly): work but have limited connection slots — the coordinator uses connection serialization and capped retries.

## Style
- Python 3.10+ (uses `|` union syntax, `X | None`).
- `black` formatting (no other linter configured).
- `from __future__ import annotations` at top of every file.
- No `pyproject.toml` / `setup.cfg` — this is a HA custom component, not a distributable package.
