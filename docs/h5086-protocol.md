# H5086 Smart Plug Pro — BLE Protocol Reference

The H5086 speaks the same per-connection BLE protocol as the H5080, plus an energy-metering
opcode. This document reconciles three independent sources, and says which one each claim
rests on:

| Source | What it settles | Limits |
|---|---|---|
| **Govee Android app** (`com.govee.home` 7.5.20, jadx-decompiled to `re_apk/decompiled`) | what the app sends and parses | says nothing about fields the app ignores |
| **H5080 firmware dump** (`flash.bin`, Ghidra exports in `re/`) | the token/auth path | **H5080 only** — the dump has no H5086 code, and the H5086 is a different silicon family (it carries a Telink chart channel) |
| **Live captures** — reydanro@ via [egold555/Govee-Reverse-Engineering](https://github.com/egold555/Govee-Reverse-Engineering/blob/master/Products/H5086.md), flash1228@ via PR #1 | what the device actually emits | two frames, both checksum-valid |

Where they disagree, the disagreement is noted rather than resolved by preference.

## BLE transport

| UUID | Role | Source |
|------|------|--------|
| `00010203-0405-0607-0809-0a0b0c0d1910` | Service | `h5086/ble/BleComm.java`, `BleNotifyComm.getServiceUuid()` |
| `00010203-0405-0607-0809-0a0b0c0d2b11` | Write characteristic | `h5086/ble/BleComm.java` (`getCharacteristicUuid()`) |
| `00010203-0405-0607-0809-0a0b0c0d2b10` | Notify characteristic | `encryp/ble/Constants.java:17` |

`1910` is the **service**, not a characteristic — subscribing to it raises
`BleakCharacteristicNotFoundError`. The H5086 package only names the write characteristic;
the notify characteristic is declared in the shared encryption module, which is why it looks
absent if you grep only `com/govee/h5086`.

## Frame format

All frames are exactly 20 bytes:

```
[proType] [cmdType] [payload (17 bytes)] [xor-checksum]
```

- `proType` — `0xAA` for reads, `0x33` for writes (`AbsControllerNoEvent4Single.getProType()`;
  there is also a `0x3A` write variant this integration does not use).
- `cmdType` — the command byte.
- `xor-checksum` — XOR of bytes[0..18], stored at byte[19], computed **before** encryption.

Integers are **big-endian unsigned**. The app's accessor is named `getSignedInt`, but it masks
every byte with `& 255` (`base2light/ble/BleUtil.java`) — the name is a misnomer.

### Command bytes

| Operation | proType | cmdType | Payload | Response |
|------------|---------|---------|---------|----------|
| Read auth token | `0xAA` | `0xB1` | (none) | `aa b1 01 <8-byte token> <padding>` |
| Write auth token | `0x33` | `0xB2` | 8-byte token | `33 b2 <status>` (`0x00` = ok) |
| Switch ON / OFF | `0x33` | `0x01` | `0x01` / `0x00` | `33 01 <state>` (`!= 0` = ON) |
| Read power | `0xAA` | `0x19` | (none) | `aa 19` or `ee 19` + 13-byte payload |

## Response headers: `aa 19` **and** `ee 19` both occur

This trips everyone up, so it is worth stating precisely. The app has **two** paths into the
*same* power parser:

**Synchronous reply — `aa 19`.** `AbsControllerNoEvent4Single.isSameController` matches
`getProType() == bytes[0] && getCommandType() == bytes[1]`, and `getProType()` returns `0xAA`
for a read controller. So the direct answer to our own read echoes `aa 19`.

**Unsolicited push — `ee 19`.** `AbsNotify.parse` gates on a leading `0xEE`
(`b()` returns `(byte) -18`), strips that byte, then dispatches on the *next* byte —
`DeviceStateNotifyParse.c()` returns `25` = `0x19` — into
`DeviceElectricController.d()`, byte-for-byte the same parser as above.

reydanro@'s capture is an `ee 19` frame; flash1228@'s is `aa 19`. **Both are real. Parse both.**
Matching only one is how this integration has twice ended up with power sensors stuck at
"unknown" — first by accepting only `ee 19` (so the poll reply was dropped), and nearly a
second time by swapping that for only `aa 19` (which would have dropped the push).

## Power query and parse

Send `aa 19` zero-padded to 20 bytes, checksum `0xb3` (`0xaa ^ 0x19`). The app sends cmdType
`0x19`; reydanro@'s older capture used `aa 00` and still got a `0x19` response.

The 13-byte payload (`DeviceElectricController.Companion.d()`):

| Bytes after header | Field | App's scaling | This integration |
|---|---|---|---|
| `[0:3]` | runtime | `/ 60` → **int minutes** | kept as raw **seconds** |
| `[3:6]` | energy | `/ 10000.0` → kWh | `/ 10.0` → Wh (same scale) |
| `[6:8]` | voltage | `/ 100.0` | V |
| `[8:10]` | current | `/ 100.0` | A |
| `[10:13]` | active power | `/ 100.0` | W |
| `[13]` | **power factor, %** | **not read by the app** | parsed — see below |

### The power-factor byte

The app parses 13 payload bytes and stops. `ElectricData` has exactly five fields, and the
string `factor` does not appear anywhere in the decompiled tree. It is therefore true that
**the app never reads payload byte `[13]`** (frame byte `[15]`).

It does not follow that the byte is padding. Both captures carry a non-zero value there that
matches the power factor computed from that same frame's own V/A/W:

| Capture | V | A | W | VA | computed PF | byte[15] |
|---|---|---|---|---|---|---|
| reydanro@ | 120.93 | 1.45 | 175.09 | 175.35 | 99.9 % | `0x64` = 100 |
| flash1228@ | 102.01 | 0.27 | 26.26 | 27.54 | 95.3 % | `0x61` = 97 |

Two devices, two loads, agreement within the 0.01 A current quantisation — and the true zero
padding starts at byte `[16]`. reydanro@ labelled it "Power Factor (in %)" from packet
captures in 2021, years before this APK was decompiled. The vendor app simply doesn't surface
it. `tests/test_status_parse.py::test_h5086_power_factor_matches_computed` pins this.

The residual on the second row is itself informative: to make the computed PF equal the
reported 97 %, current would have to be 0.2653 A. The plug reports current in 0.01 A steps
but derives PF from its unrounded internals, so below ~0.5 A the device's byte is the more
accurate figure — you cannot reproduce it from the three published sensors.

That accuracy edge is narrow, though, and PF is otherwise redundant with `W / (V × A)`. The
sensor is therefore registered as an **`EntityCategory.DIAGNOSTIC` entity, disabled by
default**: enable it if you want a load fingerprint (~1.0 resistive, 0.5–0.7 switching
supply) or a slow-drift signal for motor loads; otherwise it costs nothing. The byte is
parsed unconditionally either way — identifying it is what settles the frame layout.

`entity_registry_enabled_default` only applies at first registration, so config entries
created before this change carry an enabled entity. `async_migrate_entry` (config-entry
minor version 1 → 2) disables it for them as a one-shot sweep; re-enable it in the entity
settings and it stays enabled, because the sweep never runs again.

### Worked example

`aa 19 00 33 8a 00 03 c0 27 d9 00 1b 00 0a 42 61 00 00 00 05` (flash1228@, checksum valid)

| Bytes | Raw | Parsed |
|-------|-----|--------|
| `00338a` | 13194 | runtime = 13194 s (app would show 219 min) |
| `0003c0` | 960 | energy = 96.0 Wh (= 0.0096 kWh) |
| `27d9` | 10201 | voltage = 102.01 V |
| `001b` | 27 | current = 0.27 A |
| `000a42` | 2626 | power = 26.26 W |
| `61` | 97 | power factor = 97 % |

## Auth flow

The plug releases its token only during a ~5 s window opened by a **short press** of the
physical button.

### Token fetch (`aa b1`)

Response: `aa b1 <status> <8-byte token> <zero padding> <checksum>`, status `0x01` = ready.
Take the token at **`response[3:11]`** — 8 bytes.

Three sources agree:
- **APK:** `SecretController.Companion.c()` — `if (it2[0] == 1) { arraycopy(it2, 1, new byte[8], 0, 8) }`,
  then base64-encodes those 8 bytes for storage.
- **H5080 firmware:** the `aa b1` handler (`LAB_9b01eeb8`, `re/ble_funcs_fw2.c`) loads 8 bytes
  (`FUN_9b021c6c(&local_30, 8)`) and its copy loop terminates at `pbVar13 + 10`, i.e. it fills
  response bytes `[3..10]`. Out of window it fills the same 8 bytes with random filler.
- **Capture:** reydanro@'s valid key reads `0db6be0625333430` followed by 8 zero bytes.

> This integration previously read `response[3:19]` (16 bytes), sweeping up 8 bytes of that
> zero padding into the stored token. Harmless in practice — see below — but wrong.

### Authenticate (`33 b2`)

Send `33 b2 <token>`, zero-padded to 20 bytes. Success = `33 b2 00`.

The H5080 firmware's handler (`LAB_9b01ef54`) loads its stored 8-byte token and compares
request bytes `[2..9]` — **exactly 8 bytes** — then stops. It never inspects the rest of the
frame. That is why a 16-byte token authenticated fine, and why **tokens already stored at 16
bytes keep working after this fix**: only the first 8 bytes were ever examined. No migration
is needed.

Pre-auth control writes are dropped silently by the firmware (no relay action, no response).

## Advertisement format

6-byte manufacturer-data payload:

```
ec 00 01 01 <state> 00
```

`<state>` is the second-to-last byte: `0x01` = ON, `0x00` = OFF. No power data is broadcast —
V/A/W/kWh require an authenticated connection and the `aa 19` query.

The manufacturer ID is **not** recorded here: the integration's H5086 path does not filter on
one, and no ID for this model could be sourced from the APK. (The H5080 path filters `0x8802`
and `0x8843`.) Don't add a filter without a capture to back it.

## APK source references

| Protocol element | Decompiled source |
|------------------|-------------------|
| Service / write characteristic | `h5086/ble/BleComm.java` |
| Notify characteristic | `encryp/ble/Constants.java` |
| Frame builder, XOR checksum, int parsing | `base2kt/utils/BleUtils.java`, `base2light/ble/BleUtil.java` |
| proType, response matching | `base2light/ble/controller/AbsControllerNoEvent4Single.java` |
| `0xEE` notify dispatch | `base2light/ble/comm/AbsNotify.java`, `AbsNotifyParse.java` |
| H5086 notify registrations | `h5086/ble/BleNotifyComm.java`, `DeviceStateNotifyParse.java` |
| Token fetch / auth | `h5086/ble/controller/SecretController.java` |
| Switch on/off | `h5086/ble/controller/SwitchController.java` |
| Power query and parse | `h5086/ble/controller/DeviceElectricController.java`, `network/entity/ElectricData.java` |

A broader APK-derived spec covering every Govee BLE family lives in
`re_apk/GOVEE_BLE_PROTOCOL.md` §6.3 (untracked); this file is the H5086-specific subset that
the integration actually implements.

## Corrections applied to this integration

| # | Element | Before | After | Rests on |
|---|---------|--------|-------|----------|
| 1 | Auth token length | 16 bytes (`r[3:19]`) | 8 bytes (`r[3:11]`) | APK + firmware + capture |
| 2 | Power query command | `aa 00` | `aa 19` | APK |
| 3 | Power response header | `ee 19` only | `aa 19` **or** `ee 19` | APK (both paths) + both captures |
| 4 | Power factor | `data[15]` parsed, sensor enabled | parsing unchanged; sensor now a **disabled diagnostic** | both captures |

Corrections 1–3 originate with flash1228@ in PR #1, from their own APK decompilation.
Correction 3 is broadened from that PR (which swapped the header rather than accepting both).
The PR's proposed removal of the power-factor sensor was not applied — the byte is real — but
the underlying point that it is low-value clutter was: the entity is now diagnostic and
off by default.
