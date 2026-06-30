# re_apk — Govee Home APK reverse engineering

Reverse-engineering of the **Govee Home Android app v7.5.20-1091** to recover the BLE
protocol used by Govee devices (focus: the H508x smart-plug family).

## Deliverable

- **[`GOVEE_BLE_PROTOCOL.md`](GOVEE_BLE_PROTOCOL.md)** — the consolidated, implementation-ready
  BLE protocol reference. GATT UUIDs, the 20-byte frame + XOR checksum, multi-packet framing,
  the V1/V2 encrypted session handshake, advertisement/broadcast parsing, and a ~190-opcode
  command reference across plugs, lights, and sensors. **Start here.**
- **[`spec_sections/`](spec_sections/)** — the ten per-dimension extractions the master doc was
  synthesized from (more byte-level detail + `file:line` citations per section).

## How it was produced

1. `base.apk` (14 dex / ~37k classes) + `split_pact_*` modules decompiled with **jadx 1.5.5**.
2. Ten parallel reader agents each extracted one protocol dimension from the decompiled Java,
   writing a spec section.
3. The five critical sections (transport, crypto, broadcast, H5080, H5086) were
   adversarially re-verified against source (opcode/byte accuracy); corrections applied inline.
4. A synthesis pass merged everything into `GOVEE_BLE_PROTOCOL.md`.

Orchestration script: [`extract_ble_spec.workflow.js`](extract_ble_spec.workflow.js).

## Reproducing the decompile (artifacts are git-ignored)

The APK bundle, the decompiled tree (`decompiled/`), jadx (`tools/`), and extracted assets are
intentionally **not** committed (size). To regenerate:

```sh
# from re_apk/
APK="com.govee.home_7.5.20-1091_*/base.apk"
JAVA_OPTS="-Xmx16g" tools/jadx/bin/jadx -j 24 --no-res --no-imports -d decompiled/base $APK
```

All `file:line` citations in the spec are relative to `decompiled/base/sources/`.
