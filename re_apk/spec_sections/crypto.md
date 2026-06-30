# Encryption & Authentication — BLE Session / Secret-Key Protocol

Scope: `com/govee/encryp/**`, `com/govee/encryption/**`, the legacy secret-key controllers
(`com/govee/base2light/ble/controller/SecretKeyController`, `com/govee/h5086/ble/controller/SecretController`),
and `assets/api.key`. This is the post-OTA encrypted BLE path used by H5080/H5086 (and the rest of the
modern fleet) once a device advertises encryption support.

There are **three distinct cryptographic mechanisms** in this codebase. Do not conflate them:

| Mechanism | Where | Purpose | Crypto |
|-----------|-------|---------|--------|
| **V1 session encryption** (`EncryptionManager`) | `com/govee/encryp/ble` | Encrypt the entire 20-byte BLE frame stream after a 2-step session handshake | AES-128/ECB-NoPadding (16-byte block) + RC4 keystream (trailing <16 bytes) |
| **V2 session encryption** (`EncryptionManagerV2`) | `com/govee/encryp/ble` | Same, newer scheme; per-device key + AES-GCM AEAD with packet counter | AES-128/GCM/NoPadding, 12-byte IV, 96-bit tag (128-bit fallback) |
| **Legacy "secret key/code"** (`SecretKeyController`, `SecretController`) | `com/govee/base2light/ble/controller`, `com/govee/h5086` | Read/write an 8-byte device "secret code" used for binding/pairing — **not** a session cipher | base64 transport of an 8-byte blob; frame uses cmd-type `0xB1`/`0xB2` |
| **RSA public key** (`assets/api.key`) | network layer | Cloud HTTPS payload crypto only | RSA-2048 public key |

The session-encryption layer (V1/V2) is transparent: it sits between the normal command framing layer
(the `0x33`/`0xAA`/`0xA1` frames documented elsewhere) and the GATT write. A normal control frame is built
in plaintext, then `IEncryption.c(frame)` encrypts it before write, and `IEncryption.f(notify)` decrypts
inbound notifications.

---

## 1. GATT plumbing

All session traffic uses the **modern unified service/characteristic** (`com/govee/encryp/ble/Constants`,
`EncryptionManager.f115468p/f115469q`):

| Role | UUID | Const |
|------|------|-------|
| Primary service | `00010203-0405-0607-0809-0a0b0c0d1910` | `Constants.d()` |
| Write + notify (unified) | `00010203-0405-0607-0809-0a0b0c0d2b11` | `Constants.a()` |
| Legacy write | `00010203-0405-0607-0809-0a0b0c0d2b10` | `Constants.c()` |
| **BGC-info (encryption descriptor)** | `00010203-0405-0607-0809-0a0b0c0d2b12` | `Constants.b()` |

`EncryptionManager$writeBytes$2` confirms handshake + control frames are all written to **`...2b11`** in
service `...1910` (already encrypted by the controller before write — `writeBytes` does no crypto itself).

---

## 2. Encryption-version detection (which scheme a device uses)

Source: `BgcInfoReader.a()` / `.d()` / `.e()`, `BaseBgcInfo`, `BgcInfoV2`, `BgcInfoReaderPool.supportEncryptV2`.

On connect, the app reads characteristic **`...2b12`** (`Constants.b()`) in service `...1910`. The returned
bytes are parsed in `BgcInfoReader.d(byte[])`:

- `bArr[0] == 1` → legacy descriptor; `encryptVersion = bArr[1]`.
- `bArr[0] == 2` → `BaseBgcInfo.Companion.a()` builds a `BgcInfoV2`:
  - `bArr[1]` = encryptVersion (u8)
  - `bArr[2] == 1` → boolean flag
  - `bArr[3..4]` = u16 big-endian (`BytesUtils.c(b3,b4)`)
  - `bArr[5]` = u8

Resolved support flags:
- `BgcInfoReader.h()` → `encryptVersion == 2` → **use `EncryptionManagerV2` (AES-GCM)**.
- otherwise `encryptVersion == 1` → **use `EncryptionManager` V1 (AES-ECB+RC4)**.

`EncryptionManagerPool.b(address)` picks the manager: `supportEncryptV2 == true` ⇒ `EncryptionManagerV2(address)`,
else `EncryptionManager(AESEncryptionStrategy(), address)`. It also tears down and rebuilds a V1 manager into a
V2 manager if a device's descriptor changes ("加密1期->2期，重建manager").

---

## 3. Key material (LibTools — obfuscated app-resource keys)

Source: `com/govee/encryp/LibTools`, `AESUtils.decode`. Three static secrets are lazily derived from string
resources, each by `AESUtils.decode(cipherTextResId, keyResId)` = AES/ECB/PKCS5Padding decrypt → hex string,
then `AESUtils.parseHexStr2Byte()` → raw key bytes.

| `LibTools` method | Cache key | Resources `decode(cipher, key)` | Used as |
|-------------------|-----------|--------------------------------|---------|
| `c()` | `KEY_COMMUNICATION` | `decode(R.string.app_communication, R.string.app_session)` | **V1 handshake key** (AES-ECB) for session-key request/confirm |
| `a()` | `KEY_COMMUNICATION_X` | `decode(R.string.app_y_com, R.string.app_x_name)` | **V2 session-key-request AES-GCM key** |
| `b()` | `KEY_COMMUNICATION_Y` | `decode(R.string.app_x_com, R.string.app_y_name)` | **V2 per-device-key derivation key** (AES-ECB) |

> These three values are static, app-global constants (not per-device), recoverable by decrypting those string
> resources. They are the root of trust for the BLE session handshake. To reproduce the protocol you must
> extract the decrypted hex of `app_communication`, `app_y_com`, and `app_x_com`.

`AESUtils.decode` uses `Safe.f115525d = "AES/ECB/PKCS5Padding"`, key bytes = UTF-8 of the key string.

---

## 4. Crypto primitives

### Safe (V1 cipher: AES-ECB + RC4) — `com/govee/encryp/ble/Safe`
- `AES/ECB/NoPadding`, 16-byte block (`Safe.a` decrypt, `Safe.c` encrypt; key = `SecretKeySpec(key,"AES")`).
- `Safe.d(data,key)` / `Safe.b(data,key)`: process input in 16-byte blocks with AES-ECB; **any trailing
  `len % 16` bytes are encrypted with `Safe.g` = RC4** (key-scheduled by `Safe.f`). So a 20-byte frame =
  one AES-ECB block (bytes 0–15) + 4 RC4 bytes (bytes 16–19). RC4 KSA/PRGA is standard (256-int state, mod-256).

### AesGcmUtils (V2 cipher) — `com/govee/encryp/AesGcmUtils`
- `AES/GCM/NoPadding`, key **must be 16 bytes** (`g()` throws otherwise).
- IV = 12 random bytes (`f()` → `SecureRandom`).
- Tag length: probes 96-bit first (`f115407i=96`, `i()=12` bytes); falls back to 128-bit/16-byte if the
  platform rejects 96 (`j()`/`k()`). Decrypt tries 96 then retries 128.
- `e(plaintext,key,iv,aad)` / `d(plaintext,iv,key,aad)` → returns `iv ‖ (ciphertext‖tag)`.
- `a(cipherMessage,key,aad)` → splits leading 12-byte IV off `cipherMessage`, then `c()` GCM-decrypt.
- `b(cipherMessage,iv,key,aad)` → GCM-decrypt with externally supplied 12-byte IV.
- `h()` overhead = `12 (IV) + 4 = 16`; MTU budget = `max(20, mtu - 16)` (`EncryptionManagerV2.a`).

---

## 5. V1 session handshake (EncryptionManager / Controller4Aes)

Handshake key `K = LibTools.c()` (16-byte). Frame builder `Controller4Aes.Companion.a(opcode, payload, type=0xE7)`
produces a 20-byte frame: `[0]=0xE7, [1]=opcode, [2..]=payload, fill 2..18 with random bytes, [19]=XOR BCC of [0..18]`.
Each handshake frame is then **AES-ECB+RC4 encrypted with `K`** (`Safe.d`) before write.

Triggered by `EncryptionManager.k(...)` → `requestEncryptionKey$1` → `r()` (request) then `n()` (confirm).
Timeout 6000 ms, 2 retries (`f115470r=6000`, `f115471s=2`).

### Step 1 — Request session key (`s()`, log "V1 请求会话key 0209")
- Build `Controller4Aes.e()`: `a(0x01, [], 0xE7)` → plaintext `E7 01 <rand…> BCC`, encrypted with `K`.
- Device replies on `...2b11`; `EncryptionManager.m()` → `Controller4Aes.g(resp)`:
  - decrypt with `K` (`Safe.b`); require `dec[0]==0xE7 && dec[1]==0x01`.
  - **session key = `dec[2..18]` (16 bytes)**, stored in `f115477g`.

### Step 2 — Confirm session key (`n()`, log "确认会话key")
- Build `Controller4Aes.f()`: `a(0x02, null, 0xE7)` → `E7 02 …`, encrypted with `K`.
- Device ACK; `EncryptionManager.l()` → `Controller4Aes.h(resp)`: decrypt with `K`, require
  `dec[0]==0xE7 && dec[1]==0x02` ⇒ session established.

### Steady state (`AESEncryptionStrategy`)
- Outbound: `EncryptionManager.c(frame)` → `strategy.encrypt(frame, sessionKey)` = `Safe.d(frame, sessionKey)`
  (whole 20-byte frame, AES-ECB block 0–15 + RC4 16–19).
- Inbound: `f()/g()` → `o()` → `strategy.decrypt(value, sessionKey)` = `Safe.b(value, sessionKey)`.
- The plaintext inside is the normal `0x33/0xAA/0xA1/0xEE…` command frame. The session layer is opcode-agnostic.

| V1 opcode | cmd-type `[0]` | opcode `[1]` | dir | meaning |
|-----------|----------------|--------------|-----|---------|
| Session-key request | `0xE7` | `0x01` | write (enc w/ `K`) | ask device for 16-byte session key |
| Session-key reply | `0xE7` | `0x01` | notify (enc w/ `K`) | `payload[0..15]` = session key |
| Session-key confirm | `0xE7` | `0x02` | write (enc w/ `K`) | acknowledge key |
| Confirm ACK | `0xE7` | `0x02` | notify (enc w/ `K`) | session ready |

---

## 6. V2 session handshake (EncryptionManagerV2 / Controller4AesGcm)

Keys: `keyX = LibTools.a()` (session-key-request GCM key), `keyY = LibTools.b()` (device-key derivation).
Frame type byte is `0xE7`. Two opcodes:
- **`0x11`** = single-packet session-key request/response (`Controller4AesGcm.g/h`).
- **`0x19`** = multi/split session-key request/response (`Controller4AesGcm.f/i`); used when channel can't do MTU
  big-packets ("当前链接通道不支持mtu大包流程").
- **`0x1A`** = encrypted **split** application data (set up in `EncryptionManagerV2.c()` / decoded in `Controller4AesGcm.a`).

### Step 1 — Request session key
`Controller4AesGcm.d(opcode=0x11, type=0xE7, sub=0, payload=ivKey)` (single) builds:
```
[0]=0xE7 [1]=0x11 [2]=0x00            (3-byte header / clear)
[3..14] = 12-byte random GCM IV       (AesGcmUtils.f())
[15]    = tag length in bytes (i())
[16..]  = GCM ciphertext‖tag
```
AAD = `header[0..2] ‖ IV(12) ‖ [tagLen]` (16-byte `bArr3`). GCM key = `keyX`. The split variant `b()` uses a
4-byte header `E7 19 sub 02` and AAD of 17 bytes, then `BytesUtils.splitPackage`.

### Step 2 — Parse session-key reply (`EncryptionManagerV2.l()`)
- If `resp[0]==0xE7 && resp[1]==0x11` → `Controller4AesGcm.h(resp)`: `status=resp[2]` (0 = OK), AAD = `resp[0..14]`
  (first 15 bytes), ciphertext = `resp[3..]`, GCM-decrypt with `keyX`.
- else → `Controller4AesGcm.i(resp)`: split reassembly, header `E7 19 status seqTotal`, last packet marked `0xFF`,
  total length must equal `i()+35`; decrypt AAD = first 16 bytes, ciphertext = `[4..]`.
- Decrypted material is **19 bytes**, carved in `l()`:
  - `bytes[0..8)`  (8 bytes) → **session key / IV-base** (`f115498g`)
  - `bytes[8..13)` (5 bytes) → device-info part A
  - `bytes[13..19)` (6 bytes) → device-info part B

### Step 3 — Derive per-device key (`EncryptionManagerV2.v()`)
```
devInfo = partA(5) ‖ partB(6)        (11 bytes)
key16   = devInfo padded to 16 bytes with zeros
deviceKey = Safe.d(key16, keyY)      (AES-ECB encrypt of the 16-byte block with keyY)
```
`deviceKey` (16 bytes, `f115500i`) is the GCM key for all subsequent app traffic; the 8-byte session key
(`f115498g`) is the IV base; a per-message 32-bit counter (`f115508q`, starts at 1) is the nonce/AAD salt.

### Steady-state encryption (`EncryptionManagerV2.c(data)`)
- `counter4 = BytesUtils.d(pgkCounter)` (big-endian 4 bytes).
- `nonce/IV = sessionKey(8) ‖ counter4` (12 bytes) — the GCM IV (`bArrPlus`).
- **Large-MTU path** (`f115494c`, mtu > `i()+35`): `AesGcmUtils.d(plaintext, iv=sessionKey‖counter, key=deviceKey, aad=counter4)`;
  wire frame = `counter4 ‖ (ciphertext‖tag)` (the redundant 12-byte IV prefix is stripped — receiver rebuilds it
  from the known session key + counter). Counter then increments.
- **Small-MTU path**: same GCM with AAD = `E7 1A 02 ‖ counter4`, output `counter4 ‖ ct`, then `splitPackage`
  with a leading `E7 1A 02` 3-byte header → multi-packet `0xE7 0x1A` frames.

### Steady-state decryption (`EncryptionManagerV2.m()`)
- Large-MTU: `counter4 = in[0..4)`, IV = `sessionKey ‖ counter4`, `AesGcmUtils.b(ct=in[4..], iv, deviceKey, aad=counter4)`.
- Small-MTU: `Controller4AesGcm.a(in, deviceKey, ivKey=sessionKey)` reassembles `E7 1A` split packets
  (seq check, last == `0xFF`), then GCM-decrypt with IV = `sessionKey ‖ reassembled[3..7]`, AAD = first 7 bytes.

| V2 opcode | type `[0]` | opcode `[1]` | dir | meaning |
|-----------|-----------|--------------|-----|---------|
| Session-key request (single) | `0xE7` | `0x11` | write (GCM w/ `keyX`) | request session key + device info |
| Session-key reply (single) | `0xE7` | `0x11` | notify (GCM w/ `keyX`) | `[2]`=status, payload→8B key + 11B devinfo |
| Session-key request (split) | `0xE7` | `0x19` | write (GCM w/ `keyX`) | multi-packet variant |
| Session-key reply (split) | `0xE7` | `0x19` | notify (GCM w/ `keyX`) | multi-packet variant; last pkt `0xFF` |
| Encrypted app data (split) | `0xE7` | `0x1A` | write/notify (GCM w/ `deviceKey`) | `[2]`=seqTotal; per-msg counter; last pkt `0xFF` |

---

## 7. Legacy "secret key / secret code" (NOT a session cipher)

Source: `com/govee/base2light/ble/controller/SecretKeyController`, `EventSecretKey`,
`com/govee/h5086/ble/controller/SecretController`, `com/govee/h5080/config/SecretKeyConfig`,
`com/govee/base2light/ble/AbsConnectDialog4Secret`, `BleProtocolConstants`.

This is an **older binding/pairing mechanism** that reads or writes an 8-byte "secret code" over a normal
(possibly plaintext) frame. Command-type bytes (from `BleProtocolConstants`):

- `SINGLE_READ_SECRET_KEY = -79` = **`0xB1`** — read the device's secret.
- `SINGLE_CHECK_SECRET_KEY = -78` = **`0xB2`** — write/verify the secret.

`SecretKeyController.getCommandType()` returns `0xB1` when reading, `0xB2` when writing (`SecretController` in
H5086 mirrors this: `getCommandType() = d() ? 0xB2 : 0xB1`).

Notify/read parse (`SecretKeyController.parseValidBytes`, `SecretController.Companion.c`):
- `value[0] == 1` AND `value.length > 8` ⇒ success; the 8-byte secret = `value[1..9)`, encoded to string via
  `Encode.encryptByBase64` (base64). Stored per-SKU in `SecretKeyConfig.secretKeyMap`.
- otherwise ⇒ failure (`EventSecretKey.sendFail`).

Write path (`SecretKeyController.q()`): the stored base64 secret is `Encode.decryByBase64`'d back to 8 raw
bytes and written as the payload.

| Name | cmd-type `[0]` | dir | payload |
|------|----------------|-----|---------|
| Read secret code | `0xB1` | write→notify | reply `[0]=1` ok, `[1..8]` = 8-byte secret |
| Write/verify secret code | `0xB2` | write | 8-byte secret (decoded from stored base64) |

> This is unrelated to the V1/V2 AES session and predates it; it is essentially a device-binding token. The
> 0xB1/0xB2 handshake referenced in the project ground-truth maps to **this** mechanism, not to the AES session
> handshake (which uses `0xE7 01/02` for V1 and `0xE7 11/19/1A` for V2).

---

## 8. RSA public key (`assets/api.key`)

`assets/base_assets/assets/api.key` is a base64 **X.509 SubjectPublicKeyInfo, RSA-2048** public key
(393 bytes, header `MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A…`). Referenced only by the **network/cloud** crypto layer
(`com/govee/base2kt/utils/RsaAesUtils`, `com/govee/network/core/crypto/NetworkCryptoHelper`,
`com/ihoment/base2app/network/*`) for HTTPS request-payload encryption/signing. **It is not used anywhere in the
BLE session handshake** — the BLE session is symmetric (the keys in §3). Flagged here only to disambiguate.

---

## 9. Implementation checklist (to talk to a post-OTA H5080/H5086)

1. Connect; read `...2b12` to learn `encryptVersion` (1 ⇒ V1, 2 ⇒ V2).
2. Recover the static app keys by decrypting the relevant string resources (`app_communication`/`app_session`
   for V1; `app_y_com`/`app_x_name` and `app_x_com`/`app_y_name` for V2) with AES/ECB/PKCS5; hex→bytes.
3. **V1**: send `E7 01` (AES-ECB+RC4 w/ commKey) → get 16-byte session key from reply `E7 01`; send `E7 02`,
   await ACK; thereafter wrap every 20-byte command frame with `Safe.d`(sessionKey) and unwrap notifications
   with `Safe.b`(sessionKey).
4. **V2**: send `E7 11` (AES-GCM w/ keyX, 12-byte IV, 96-bit tag) → reply yields 8-byte sessionKey + 11-byte
   devinfo; derive `deviceKey = AES-ECB(keyY, devinfo‖zeros[16])`; thereafter GCM-encrypt with IV =
   `sessionKey‖counter4`, AAD = `counter4`, prepend `counter4`, increment counter (split via `E7 1A` on small MTU).
5. The secret-code (`0xB1`/`0xB2`) exchange is a separate, optional binding step, not part of session setup.

### Uncertainties / flags
- The exact **plaintext content of the V2 session-key request payload** (`ivKey` arg into `Controller4AesGcm.g`)
  was not fully traced from `EncryptionManagerV2.s()` (decompiler skipped the body); treat the request payload as
  a client nonce/IV blob. The response carving (8+5+6) and device-key derivation are confirmed from `l()`/`v()`.
- 96- vs 128-bit GCM tag is negotiated at runtime by capability probing (`AesGcmUtils.j/k`); a reimplementation
  should try 96-bit first and fall back to 128-bit.
- The V1 frame padding bytes 2..18 are random fill (`Random.nextInt(256)+const`); only `[0]`, `[1]`, and the BCC
  are semantically meaningful in the handshake frames.
