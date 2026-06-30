# Govee BLE for Home Assistant

![Govee Logo](assets/govee-logo.png)

Local control and monitoring of Govee Bluetooth Low Energy (BLE) devices — smart plugs, lights, thermo-hygrometer sensors, and kitchen/air appliances — directly from Home Assistant, with no cloud account and no bridge.

> [!IMPORTANT]
> **This is an independent project, not a drop-in replacement for the original.**
>
> It began as a fork of [virtuald/govee-ble-plugs](https://github.com/virtuald/govee-ble-plugs) but has since diverged substantially (a data-driven device registry covering the whole Govee BLE lineup, a light platform with RGBIC support, sensor and appliance platforms, polling, and reliability work).
>
> The domain stays `govee_ble_plugs` (so existing config entries keep working), but it now presents in Home Assistant as **"Govee BLE"**. If you are coming from the *original* `govee-ble-plugs` integration, you must remove it and re-add your devices — entities and history will not carry over.

## Supported devices

The integration is **data-driven**: a declarative device registry maps every catalogued Govee BLE SKU to its capabilities and a protocol codec, so coverage spans the broad Govee BLE lineup rather than a hand-picked few. Support comes in two tiers.

### Hardware-verified

| Model | Type | Capabilities |
|-------|------|--------------|
| **H5080** | Smart plug (single outlet) | on/off |
| **H5082** | Dual smart plug | on/off per outlet (2) |
| **H5083** | Smart plug (single outlet) | on/off — *community-contributed* |
| **H5086** | Smart plug w/ energy monitoring | on/off, plus voltage / current / power / energy / power-factor sensors |
| **H6163** | RGB LED light | on/off, brightness, RGB color, color temperature, scene & music effects |

### Protocol-derived (experimental)

Everything below is supported from a model of the Govee BLE protocol, but is **not yet validated on physical hardware**. These devices are flagged *experimental* — they should work, but may need per-model fixes. (See [Testing experimental devices](#testing-experimental-devices).)

- **Lights (~450 SKUs)** — on/off, brightness, RGB color, color temperature, and a shared catalogue of built-in scene/music effects. **RGBIC** strips (addressable) additionally get whole-strip color via the native command plus per-segment color through a custom service.
- **Thermo-hygrometers (~20 SKUs)** — temperature, humidity, and battery, parsed passively from BLE advertisements (no connection needed).
- **Kitchen & air appliances (~75 SKUs)** — on/off for humidifiers, ice makers, kettles, heaters, purifiers, and fans. (Mode/gear/ice-size are not yet implemented.)

Discovery matches any Govee BLE advertisement name (`GVH*`, `ihoment_*`, `Govee_*`, `GBK_*`, `Minger_*`); the registry then resolves the SKU. Supported models offer to configure; unrecognised ones are politely declined.

## Features

- **Local BLE control** — talks to devices directly over Bluetooth; works with an adapter on the Home Assistant host or via ESPHome / Shelly BLE proxies.
- **Data-driven device registry** — adding a device is a declarative entry (`custom_components/govee_ble_plugs/devices/`), with a per-SKU override hook for quirks; most lights share one common codec.
- **Switch entities** for plugs (incl. per-outlet control for the dual H5082) and for appliances (on/off).
- **Light entities** — brightness, RGB, color temperature, and built-in effects; **RGBIC** strips expose the `light.set_segment_color` service (`{segments: [0,1,2], rgb_color: [255,0,0]}`) for per-segment color.
- **Sensor entities** — temperature / humidity / battery for thermo-hygrometers.
- **Energy monitoring** for the H5086: voltage, current, power, accumulated energy, and power-factor sensors, polled over BLE.
- **State tracking** from passive BLE advertisements, plus active status polling with exponential backoff.
- **Optimistic updates with a command cooldown**, so a stale advertisement can't briefly revert a command you just issued.
- **Resilient connection handling** — per-device connection serialization, connection timeouts, and capped retries to coexist with the limited connection slots on BLE proxies.
- **UI configuration** via a config flow, with Home Assistant brand assets (icon/logo).

## Installation

Install through [HACS](https://hacs.xyz/) as a custom repository (this integration is not in the default HACS store):

1. In HACS, open the three-dot menu → **Custom repositories**.
2. Add `https://github.com/eseverson/govee-ble-plugs` with category **Integration**. ([How custom repositories work.](https://www.hacs.xyz/docs/faq/custom_repositories/))
3. Install **Govee BLE**, then restart Home Assistant.

Make sure Home Assistant can access Bluetooth on your host (or that you have a working BLE proxy) before adding devices.

## Usage

Add the integration from **Settings → Devices & Services → Add Integration**, select your discovered device, and follow the prompts. Plugs and appliances appear as switch entities, lights as light entities, and thermo-hygrometers as sensor entities.

### Pairing (plugs only — press the button)

Plugs hand out their auth token only after a **short press of the physical button**. When the config flow shows the "Pair Govee Smart Plug" screen, short-press the button on the plug once, then click **Submit**. The token is stored and reused on every connection, so you only do this once per plug. Lights, sensors, and appliances do not need pairing — they configure directly.

### Newer (post-OTA) H5080 firmware

Govee pushed an OTA (around firmware `1.00.28`) that moved the H5080's local BLE control behind an **encrypted, per-connection session** (AES-128 + RC4) plus a token-based auth step. Plugs on that firmware stopped responding to the old plaintext commands (symptom: `authentication timeout` in the logs and switches that don't actuate).

This integration speaks both protocols and **auto-detects** which one a plug uses on each connection, so updated and not-yet-updated units both work. The encrypted protocol was recovered by reverse-engineering the firmware. No cloud account or per-device secret is required — the session key and token are exchanged locally over BLE.

## Testing experimental devices

Because the bulk of device support is protocol-derived rather than hardware-tested, two aids help you validate against gear you actually own:

- **Generic-driver toggle (H6163).** The H6163's device options (**Configure**) include a **"Use generic driver (test)"** switch. Turn it on to route the light through the same data-driven driver the experimental lights use, so you can confirm the generic path works on real hardware in your environment. Default off uses the built-in, validated driver. See [`docs/generic-vs-bespoke.md`](docs/generic-vs-bespoke.md) for exactly how the two differ.
- **`light.set_segment_color` service.** Exercise RGBIC per-segment color from Developer Tools → Services.

If you confirm a model works (or fix one), please open an issue/PR so it can be promoted from experimental.

## Troubleshooting

- **Range / connectivity** — make sure the device is within Bluetooth range of the host or a BLE proxy.
- **An experimental device doesn't respond** — its protocol is not hardware-verified, and some models use different opcodes. Enable debug logging (below) to see the exact bytes sent, and file an issue with the model.
- **`authentication timeout` / switch won't actuate on an H5080** — the plug is likely on the newer encrypted firmware and needs to be **re-paired**: remove the device and add it again, short-pressing the button when prompted (see Pairing above). This refreshes the stored token to the one the updated firmware expects.
- **Logs** — check **Settings → System → Logs** for messages from `govee_ble_plugs`. Enabling debug logging for the integration surfaces the raw advertisement and command bytes, which is the fastest way to diagnose state or protocol issues.

## Support & contributions

- **Issues:** <https://github.com/eseverson/govee-ble-plugs/issues>
- New **local-only** device support and fixes are welcome. Cloud-based integrations are out of scope.

## Credits

This project builds on the work of others:

- **Original integration:** [virtuald/govee-ble-plugs](https://github.com/virtuald/govee-ble-plugs) — the base this project forked from.
- **H5083 support:** adapted from [zaza7/govee-ble-plugs](https://github.com/zaza7/govee-ble-plugs).
- **H5086 advertisement state-byte fix & command cooldown:** adapted from [cmorgannorris/govee-ble-plugs](https://github.com/cmorgannorris/govee-ble-plugs).
- **H5086 power/energy monitoring:** ported from [nsheaps/govee-ble-plugs](https://github.com/nsheaps/govee-ble-plugs).
- **H6163 color-temperature protocol:** referenced from [wez/govee-py](https://github.com/wez/govee-py) and [chvolkmann/govee_btled](https://github.com/chvolkmann/govee_btled).
- **Protocol reverse-engineering:** [egold555/Govee-Reverse-Engineering](https://github.com/egold555/Govee-Reverse-Engineering) — a great starting point for adding new devices.
- **Inspiration & structure:** [Beshelmek/govee_ble_lights](https://github.com/Beshelmek/govee_ble_lights) and Home Assistant's [keymitt_ble integration](https://github.com/home-assistant/core/tree/dev/homeassistant/components/keymitt_ble).

Available under the Apache 2.0 license.
