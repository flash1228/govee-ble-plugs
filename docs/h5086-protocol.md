# H5086 Smart Plug Pro — BLE Protocol Reference

The Govee H5086 speaks an encrypted, per-connection BLE protocol with token-based auth.
This document records the wire format as recovered by decompiling the Govee Android app
(`com.govee.home`) with jadx. The H5086 code lives in package `com.govee.h5086` (in the
split APKs); the core BLE comm library lives in `base2light` / `base2kt`. File references
below point to the decompiled Java sources.

The integration speaks both the encrypted (post-OTA) and the legacy plaintext (pre-OTA)
protocols and auto-detects which one a plug uses on each connection.

## BLE transport

| UUID | Role | Source |
|------|------|--------|
| `00010203-0405-0607-0809-0a0b0c0d1910` | Service | `BleComm.java` (`getServiceUuid()`) |
| `00010203-0405-0607-0809-0a0b0c0d2b11` | Write characteristic (GATT writes) | `BleComm.java` (`getCharacteristicUuid()`) |
| `00010203-0405-0607-0809-0a0b0c0d2b10` | Notify characteristic (subscriptions) | Sibling of `2b11` under the `1910` service |

`1910` is the **service** UUID — it is NOT a characteristic. Subscribing to it raises
`BleakCharacteristicNotFoundError`. The notify characteristic is `2b10`.

## Frame format

All command and response frames are exactly 20 bytes:

```
[proType] [cmdType] [payload (17 bytes)] [xor-checksum]
```

- `proType` — direction/kind flag. `0xAA` for reads, `0x33` for writes. Source:
  `AbsControllerNoEvent4Single.java` (`getProType()`: `isWrite() ? 0x33 : 0xAA`).
- `cmdType` — the command byte (see table below).
- `payload` — up to 17 bytes, zero-padded. Source: `BleUtils.java` (`p(proType, cmdType, payload)`).
- `xor-checksum` — XOR of bytes[0..18], stored at byte[19]. Source: `BleUtils.java` (`w()`).

### Command bytes (source: `ControllerProtocol.java`)

| Operation | proType | cmdType | Payload | Response |
|------------|---------|---------|---------|----------|
| Read auth token | `0xAA` | `0xB1` | (none) | `aa b1 01 <8-byte token> <padding>` |
| Write auth token | `0x33` | `0xB2` | 8-byte token | `33 b2 <status>` (status `0x00` = ok, `0x01` = fail) |
| Switch ON | `0x33` | `0x01` | `0x01` | `33 01 <state>` (`state != 0` = ON) |
| Switch OFF | `0x33` | `0x01` | `0x00` | `33 01 <state>` (`state != 0` = ON) |
| Read power | `0xAA` | `0x19` | (none) | `aa 19 <13-byte payload> <padding>` |

### Response header convention

The device **echoes the request's `proType + cmdType`** in its response header — it does NOT
use a separate notify byte. This matches the base2light response-matching contract
(`AbsControllerNoEvent4Single.isSameController`):
`getProType() == bytes[0] && getCommandType() == bytes[1]`.

> **Pitfall:** The power response starts with `aa 19`, NOT `ee 19`. An earlier version of
> this integration checked for `0xEE 0x19` and silently dropped every power frame, leaving
> the sensors at "unknown".

## Encryption

Post-OTA firmware encrypts every frame after the E7 02 rekey. Both directions use the same
cipher state.

- **AES-128-ECB** on each full 16-byte block.
- **RC4** on any trailing partial block (the S-box is rekeyed along with the AES key).
- The frame checksum (`xor` of bytes[0..18]) is computed **before** encryption.

### Initial keys

- **AES key:** `MakingLifeSmarte` (hex `4d616b696e674c696665536d61727465`).
  This string was not found in the decompiled Java sources — it's likely in an obfuscated
  native library or constructed at runtime. It was recovered independently from firmware
  reverse-engineering and confirmed by the E7 handshaking working end-to-end.
- **Initial RC4 S-box (256 bytes):**
  ```
  60af1c7186f2b81296216cd9464ae6bb5fc240834e81e363dbedc402013e8254
  c19b525c79a0fb55e9cef48c576253246b72be99f69822976fcfff09a1c32085
  281b0aebcd921a0b9170a619a43d7577006d80de44aaf00db9c7a718ab25b405
  42bd06c031d30310d1aeb1506107cb9f3888dfbc5b66d6ec3c8fd4d79d367ad5
  0f45d03234563bb635b311a98e8d9aee262e17e5f716870874137d0c59307ffd
  c8335a235ed2c5b7f1a576fc5d49414c956ae2892a8469b2a38b931ea24d0490
  ad3a8a1f4b78da64cab57e7329944f9ef3a8671d58e8feea2bf9e7dc37fa7be0
  15bac60ee1b047272f656eacc9ef392cbfccf8435114d848f5dd3f68e49c7c2d
  ```

### Rekey

After the E7 02 reply, both sides rekey:
- new AES key = 16-byte material from the E7 01 reply
- new RC4 S-box = `rc4_ksa(material)` (standard RC4 key-schedule)

## Session handshake

1. Client sends `E7 01` (encrypted with the initial keys).
2. Device replies `E7 01 <16-byte material>`.
3. Client sends `E7 02`.
4. Device replies `E7 02`, then rekeys with the material it just sent.
5. Client rekeys with the same material (after reading the E7 02 reply, so the E7 02 reply
   is decrypted on the OLD keys — order matters).

## Auth flow

Plugs hand out their auth token only after a **short press of the physical button**, which
opens a ~5s window during which `aa b1` returns the token.

### Token fetch (`aa b1`)

Send frame `aa b1` + 17 zero padding bytes + checksum.
Response: `aa b1 <status> <8-byte token> <padding zeros> <checksum>`

- `status == 0x01` → success, token follows
- `status == 0x00` → not ready (button not pressed / window closed)

Extract the **8-byte token** at `response[3:11]` (i.e. `payload[1:9]` after the status
byte). The app Base64-encodes these 8 bytes for storage (`Encode.encryptByBase64`).

> **Pitfall:** An earlier version extracted `response[3:19]` (16 bytes). It "worked" for
> auth only because the extra 8 bytes were zero padding. The app uses exactly 8 bytes.

Source: `SecretController.java` (`Companion.c` reads, `Companion.d` writes,
`getCommandType()` returns `-79` = `0xB1` for read, `-78` = `0xB2` for write).

### Authenticate (`33 b2`)

Send frame `33 b2 <8-byte token> <9 zero padding bytes> <checksum>`.
Response: `33 b2 <status>` — `status == 0x00` = success, `0x01` = wrong token.

After a successful auth, control commands are accepted. Pre-auth control writes are
silently dropped by the firmware.

## Switch command

Send `33 01 01` (ON) or `33 01 00` (OFF), zero-padded to 20 bytes with checksum.
Response: `33 01 <state>` — `state != 0` means ON.

Source: `SwitchController.java` (`Companion.d(boolean)` returns
`new byte[]{ z5 ? 1 : 0 }`, `getCommandType()` returns `1`).

## Power query and parse

Send `aa 19`, zero-padded to 20 bytes with checksum (`0xb3 = 0xaa ^ 0x19`).
Response: `aa 19 <13-byte payload> <4 padding bytes> <checksum>`.

The 13-byte payload (big-endian, parsed by `DeviceElectricController.d()`):

| Bytes (after `aa 19` header) | Field | Divisor | Unit |
|------------------------------|-------|---------|------|
| `[0:3]` | runtime | / 60 | minutes |
| `[3:6]` | energy | / 10000 | kWh |
| `[6:8]` | voltage | / 100 | V |
| `[8:10]` | current | / 100 | A |
| `[10:13]` | active power | / 100 | W |

`[13:17]` is **padding**, not a power-factor byte. The Govee app does not expose a
power-factor field for the H5086; an earlier version of this integration read
`data[15]` as power-factor, which was reading padding.

All four fields use `getSignedInt(bytes, true)` = big-endian unsigned int.

### Worked example

Captured response: `aa 19 00 33 8a 00 03 c0 27 d9 00 1b 00 0a 42 61 00 00 00 05`

| Bytes | Raw | Parsed |
|-------|-----|--------|
| `00338a` | 13194 | runtime = 13194 s (~3.7 h) |
| `0003c0` | 960 | energy = 960/10000 = 0.096 kWh = 96 Wh |
| `27d9` | 10201 | voltage = 102.01 V |
| `001b` | 27 | current = 0.27 A |
| `000a42` | 2626 | power = 26.26 W |

Internally consistent: 0.27 A × 102 V ≈ 27.6 W ≈ 26.26 W.

Source: `DeviceElectricController.java` (`Companion.e(bytes20)` skips the 2-byte header,
`Companion.d(bytes17)` parses the 13-byte payload, `getCommandType()` returns `25` = `0x19`).

## Advertisement format

The H5086 broadcasts a 6-byte manufacturer-data payload (Govee manufacturer ID `0x88DB`):

```
ec 00 01 01 <state> 00
```

- `<state>` is at byte[4]: `0x01` = ON, `0x00` = OFF.
- The on/off state is broadcast passively — no connection is needed for state tracking.
- **No power data is broadcast** — voltage/current/power/energy require an authenticated
  GATT connection and the `aa 19` query.

## APK source references

| Protocol element | Decompiled source file |
|------------------|------------------------|
| Service / write characteristic UUIDs | `BleComm.java` |
| Frame builder (`p(proType, cmdType, payload)`) | `BleUtils.java` (`base2kt`) |
| XOR checksum (`w(packet, len)`) | `BleUtils.java` / `BleUtil.java` |
| proType values (read/write) | `AbsControllerNoEvent4Single.java` |
| Response matching (`isSameController`) | `AbsControllerNoEvent4Single.java` |
| Token fetch / auth (`B1` / `B2`) | `SecretController.java` (`com.govee.h5086.ble.controller`) |
| Switch on/off (`01 01` / `01 00`) | `SwitchController.java` |
| Power query and parse (`19`) | `DeviceElectricController.java` |
| Command byte constants | `ControllerProtocol.java` |
| Notify dispatch (`0xEE` frames) | `AbsBleWithChartDataComm.java` (`Q()`) |
| Base64 token storage | `Encode.java` (`base2home.util`) |
| Big-endian int parsing | `BleUtils.java` (`I(bytes, true)` — `base2kt`) |

## Bugs fixed in this integration

| # | Element | Before | After (per APK) |
|---|---------|--------|-----------------|
| 1 | Auth token length | 16 bytes (`r[3:19]`) | 8 bytes (`r[3:11]`) |
| 2 | Power query command | `aa 00` | `aa 19` |
| 3 | Power response header check | `0xEE 0x19` | `0xAA 0x19` (device echoes request header) |
| 4 | Energy divisor | `/ 10.0` (Wh) | `/ 10000.0 * 1000.0` (kWh → Wh) |
| 5 | Power-factor sensor | `data[15]` (padding) | removed (payload is 13 bytes; `[13:17]` is padding) |

All five corrections were verified against real H5086 hardware (plug `GVH5086A3EF`):
auth succeeds, switch toggles work, and the parsed voltage (~102 V) matches the Govee app.
