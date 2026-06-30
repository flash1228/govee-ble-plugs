# Govee BLE Protocol — Master Reference

**Source:** Reverse-engineered from the Govee Home Android app, version **7.5.20**
(`re_apk/decompiled/base/sources/...`). Decompiled with jadx; jadx prints signed
decimals, so every negative byte below is given as hex via `(v & 0xFF)`
(e.g. `-86 → 0xAA`, `-95 → 0xA1`, `-18 → 0xEE`, `-79 → 0xB1`, `-78 → 0xB2`).

This document is the single source of truth assembled from nine per-dimension spec
sections. Per-section confidence and open questions are at the end (§9).

---

## 1. Overview & scope

The app talks to devices over BLE GATT using a fixed **20-byte single-command frame**
(or a multi-packet variant for bulk payloads). One "controller" class per command builds
a frame and parses its reply. The same wire bytes are reused by the IoT/cloud
`pt`-passthrough path, so the BLE layouts here are also the canonical cloud passthrough
payloads (§7).

Device families covered:

| Family | Module(s) | Representative SKUs |
|---|---|---|
| Smart plugs (relay) | `com.govee.h5080` | H5080, H5082, H5083, H5085, H5160, H5161 (V1–V4) |
| Energy-metering plug | `com.govee.h5086` | H5086 "Smart Plug Pro" |
| Night-light plug | `com.govee.h5080.adjust.h5089`, `base_h71xx` | H5089, H5085 |
| Common light command set | `com.govee.base2light.ble.controller` | shared across all light/strip/bulb SKUs |
| RGB / RGBIC lights | `rgblight`, `rgbiclight`, `dreamcolorlightv1/v2`, `stringlightv2` | strips, bulbs, string lights |
| Thermo-hygrometers / air | `base2newth`, `pact_thnew` | H5100/01/04/05/06/08/12/40/79, H5220, H5310 |
| BBQ probe thermometers | `pact_bbqnew`, `base2newth/bbq` | H5055, H5198/99, H5610, H5151 (gateway) |
| Humidifier / ice maker | `pact_h7160`, `pact_h7172` | H7160, H7172/H7178 |
| Sensor gateways | `h5042`, `h5043`, `h5151` | leak/TH sub-device relays |

Three independent layers exist and must not be conflated:

1. **Framing** — the 20-byte frame + BCC (§3).
2. **Session encryption** — a transparent wrapper applied at the GATT characteristic
   boundary (V1 AES-ECB+RC4 / V2 AES-GCM), negotiated per device (§4).
3. **Legacy secret-code binding** — the `0xB1`/`0xB2` device-binding token (§4.6), which
   is *not* a session cipher.

---

## 2. BLE transport (GATT, lifecycle, MTU)

### 2.1 GATT UUIDs by chip family

| Role | UUID | Notes / source |
|---|---|---|
| **Modern primary service** | `00010203-0405-0607-0809-0a0b0c0d1910` | default for plugs & `base2light`; `AbsBle.H()`, `EncryptionManager`/`Constants.d()` |
| **Modern unified write+notify char** | `00010203-0405-0607-0809-0a0b0c0d2b11` | single char for both writes and notifications; `AbsBle.z()`, `Constants.a()` |
| Legacy split write char | `00010203-0405-0607-0809-0a0b0c0d1911` | older devices |
| Legacy split notify char | `00010203-0405-0607-0809-0a0b0c0d1912` | older devices / OTA (`OtaManager.f57861i`) |
| Legacy write char (alt) | `00010203-0405-0607-0809-0a0b0c0d2b10` | `Constants.c()` |
| OTA notify char (alt) | `00010203-0405-0607-0809-0a0b0c0d2b12` | `OtaManager.f57862j` |
| **BGC-info / encryption descriptor** | `00010203-0405-0607-0809-0a0b0c0d2b12` | read to learn encrypt version (`Constants.b()`) |
| CCCD | `00002902-0000-1000-8000-00805f9b34fb` | `BleCommImp.f99421d` |
| Telink "INTELL_ROCKS" service | `494e5445-4c4c-495f-524f-434b535f4857` | HW=4857; H5086 chart channel |
| Telink chart write char (G2) | `494e5445-4c4c-495f-524f-434b535f2014` | H5086 chart prepare/time-range |
| Telink chart data char (H2) | `494e5445-4c4c-495f-524f-434b535f2015` | H5086 history-data stream |
| Telink range (other) | `494e5445-4c4c-495f-524f-434b535f****` | range 2011..2015 |
| HM-10 module | `0000ffe0-...` / char `0000ffe1-...` | alternate chip |
| TI | `f000ffc0/ffc1/ffc2-...` | alternate chip |
| (other) | `0000fd00/fd01/fd02-...`, `02f00000-...-fe00/ff01` | alternate chips |

**Chip selection is static, not sniffed.** Each product's `Ble` subclass hard-codes its
service/char pair by calling either the no-arg `AbsBle()` (inherits `1910`/`2b11`) or
`AbsBle(serviceUUID, characteristicUUID)` (stores custom UUIDs returned by `H()`/`z()`).
`BleCommImp.sendMsg()` is UUID-agnostic — the caller supplies the pair, so one transport
serves all families.

### 2.2 Connection lifecycle

`scan → connectGatt → onConnectionStateChange(CONNECTED) → discoverServices →
onServicesDiscovered → (first write) enable notifications + write CCCD → write frames`

- Connect: `BleConnectImp.connectBle()` → `device.connectGatt(ctx, auto, cb, 2 /*TRANSPORT_LE*/)`.
  Transport forced to LE. One pending connection at a time.
- Timeouts (`BleController`): connect supervision **60000 ms**; service-discovery overtime
  **180000 ms**; default connect overtime **15000 ms**.
- State change (`AbsBluetoothGattCallback.h`): `status==0 && newState==2` → `discoverServices()`.
  `status==19` (peer-terminated) → `EventAutoDisconnect`. `newState==0` → disconnect event.
- **Notifications are enabled lazily on first send**, not at discovery. `BleCommImp.sendMsg()`
  keys off a per-service "already enabled" list, then:
  - `c()` standard path: `setCharacteristicNotification(true)` + write CCCD
    `ENABLE_NOTIFICATION_VALUE` `{0x01,0x00}` to `2902`, with 100/300 ms sleeps.
  - `d()` "fast connect" path: `setCharacteristicNotification(true)` only, **skips the CCCD
    descriptor write**. Chosen per device+service by a `BleBroadVersionCache` flag.
- Reconnect is gated by foreground/background + a connect-timeout flag (`BleController.R()/k()`).

### 2.3 Writes

- All frames funnel through `BleController.L(service, char, data)` (`synchronized`, one at a
  time), which delegates to `BleCommImp.sendMsg()` → `EncryptWriter.encryptWriteValue()`.
- **Write type is WRITE_TYPE_DEFAULT (write-with-response)** on the plaintext path — no
  `WRITE_TYPE_NO_RESPONSE` appears in the control path.
- If encryption is enabled, `data` is encrypted into a `List<byte[]>` of 1–2 fragments
  (a 20-byte frame may split into two ciphertext writes); each fragment is written
  separately. The plaintext protocol is unchanged — encryption is a transparent wrapper.
- Retry: `ControllerComm.j()` picks params by direction — **write**: 200 ms interval, 6
  retries, 6000 ms overtime; **read**: 100 ms, 3 retries, 3000 ms overtime
  (`0xAB`/`0xAC` reads get 6000 ms).

### 2.4 MTU

- Control frames are fixed **20 bytes**; no MTU negotiation needed for them.
- `BleController.J(mtu)` → `gatt.requestMtu(mtu)`. OTA requests **512**; usable payload =
  `mtu - 3` (ATT header). MTU-multi encoders accept `mtuSize ∈ [20, 500]`.
- BLE5 / 2M-PHY is probed (`isLe2MPhySupported()`) to gate faster OTA but does not change
  the control-frame format.

### 2.5 Notify dispatch (device→app)

1. `EncryptionBluetoothGattCallback.onCharacteristicChanged()` — if encryption supported,
   decrypts via `EncryptionManagerPool.getEncryptionManager(gatt).f(value)` first
   (transparent), then `e()`.
2. Per-product gatt callback posts `EventCharacteristicChange(addr, service, char, value)`.
3. `AbsBle.W()` fans bytes to every active comm object whose `getServiceUuid()` matches.
4. `AbsBleComm.parse()` matches a notification to its outstanding request by the
   **(type, opcode) pair `(bytes[0], bytes[1])`** via `controller.isSameController()`, then
   `onResult(true, bytes)`.
5. Multi-packet notifies (`0xA1`/`0xA2`) go to `MultiPackageManager.g()` instead (§3.3).

---

## 3. Frame format

### 3.1 Single 20-byte frame

```
 byte:  0      1        2 .............................. 18     19
       +------+--------+-------------------------------------+------+
       | type | opcode |  payload (zero-padded, 17 bytes)    | BCC  |
       +------+--------+-------------------------------------+------+
```

- `byte[0]` **type / proType**: `0x33` (51) = SINGLE_WRITE/control; `0xAA` (-86) =
  SINGLE_READ/query. Also `0x3A` (58) = SINGLE_WRITE_READ "secure write" (used by
  `AbsControllerNoEvent4Single` writeRead flag, and by the H5089 night-light mode
  controller — see §6.4).
- `byte[1]` **opcode (commandType)**: per-feature.
- `byte[2..18]` **payload**, 17 bytes, zero-padded.
- `byte[19]` **BCC** = XOR of bytes[0..18].

Total length is always exactly **20 bytes**.

Builders (`BleUtils` / `generate20Bytes`):
- `p(type, opcode, payload)` — 2-byte header, payload at offset 2.
- `o(type, opcode, subByte, payload)` — 3-byte header: `byte[2]` = sub-command selector,
  payload shifts to `[3..18]`. Used by mode/scene frames.

`getProType()` returns `0x33` when `isWrite()` else `0xAA`. Read requests use payload from
`p()`; writes use payload from `q()`.

### 3.2 BCC / XOR checksum (worked example)

```java
byte b = packet[0];
for (int i = 1; i < length; i++) b = (byte)(b ^ packet[i]);   // length = 19
packet[19] = b;
```

**Worked example — turn a single-outlet plug ON** (`33 01 01`, rest zero):

```
bytes[0..18] = 33 01 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
XOR          = 33 ^ 01 ^ 01 = 33   (all remaining bytes are 00)
frame        = 33 01 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 33
```

(A separate additive `getByteSum`/`z()` exists elsewhere — **not** used for the 20-byte
frame BCC. The frame uses XOR.)

### 3.3 Multi-packet framing

Type byte (`byte[0]`):

| Name | Hex | Dec | Role |
|---|---|---|---|
| MULTIPLE_WRITE | `0xA1` | -95 | multi write |
| MULTIPLE_READ | `0xA2` | -94 | multi read |
| MULTIPLE_WRITE_V1 | `0xA3` | -93 | multi write v1 |
| MULTIPLE_WRITE_V2 | `0xA4` | -92 | multi write v2 |
| MTU_MULTIPLE_WRITE | `0xA6` | -90 | MTU bulk write |
| MULTI_READ_AB | `0xAB` | -85 | multi read variant |
| MULTI_READ_AC | `0xAC` | -84 | multi read variant |

**A1 multi-write** (`MultiPackageManager.j`), 20-byte packets, 16-byte chunks:

```
START : A1 <comType> 00 <packetCount> 00…00 BCC      (byte[2]=0x00 = start; byte[3]=N chunks)
DATA  : A1 <comType> <idx 1..N> <16-byte chunk> BCC  (byte[2]=1-based index)
END   : A1 <comType> FF 00…00 BCC                    (byte[2]=0xFF = end)
ACK   : ← A1 <comType> <00=fail / !=0… wait>          success byte = (byte[2]==0)
```

- Payload chunked into 16-byte pieces; last chunk zero-padded.
- 300 ms sleep between every packet; max total payload < 4080 bytes.

**A2 multi-read**: `A2 <comType> 00 <payload…> BCC`. Response reassembly
(`MultiPackageManager.g`): header `byte[2]==0x00` (`amount=byte[3]`), middle packets
accepted only if `byte[2]==datas.size()+1` (strict ordering, 16-byte chunk at `[3..18]`),
end `byte[2]==0xFF` (`result = amount==datas.size()`).

**A3/A4 (`MultipleControllerCommV1`)**: 20-byte packets; header `[0]=proType,[1]=0,[2]=0/1,
[3]=packs,[4..]=commBytes`; continuation `[1]=index` with 17-byte chunks; end `[1]=0xFF`.
`AbsMultipleControllerV1.getProType()` returns `0xA3`, but the on-wire fragmenter in
`MultiPackageManager` uses `0xA1` — different SKUs route through one path or the other.

**A6 MTU multi-write**: for MTU-negotiated bulk transfer (scenes/DIY). Header
`[0]=0xA6,[1]=0,[2]=0,[3]=1,[16]=commandType,[17..]=data`, patched with big-pack count,
an 8-byte verify/time block `[6..13]` (millis + 2 random bytes), and small-packet count.

All multi-packet frames carry a BCC at `[19]` (same XOR).

### 3.4 Notify (`0xEE`) frames

Device→app notifications begin **`0xEE`** (-18). Format `[0xEE, comType, payload(17), BCC]`.
`AbsNotify.parse` matches `frame[0]==0xEE`, dispatches by `comType = frame[1]` to the
`AbsNotifyParse` whose `c()` matches, then hands `frame[2..18]` (17 bytes) to the parser.
`NOTIFY_RECOGNITION = 0xED` (-19) is a recognition-notify variant.

### 3.5 Receive-side single-frame validation

- **Read replies** (`!isWrite`): copy `value[2..]` (17 bytes) → `parseValidBytes()`. So
  `validBytes[0]` is the first payload byte after the opcode (often an echoed sub-selector).
- **Write acks**: success byte is `value[2]==0` (`AbsSingleController.t`); payload `value[3..]`.

---

## 4. Encryption & authentication

Three distinct mechanisms — do not conflate:

| Mechanism | Where | Purpose | Crypto |
|---|---|---|---|
| **V1 session** (`EncryptionManager`) | `com/govee/encryp/ble` | encrypt whole 20-byte frame stream after a 2-step handshake | AES-128/ECB-NoPadding (16-byte block) + RC4 keystream (trailing <16 bytes) |
| **V2 session** (`EncryptionManagerV2`) | `com/govee/encryp/ble` | same, newer; per-device key + AEAD with packet counter | AES-128/GCM/NoPadding, 12-byte IV, 96-bit tag (128-bit fallback) |
| **Legacy secret code** (`SecretKeyController`, `SecretController`) | `base2light`, `h5086` | read/write 8-byte device binding token — **not** a session cipher | base64 transport of 8-byte blob; cmd-type `0xB1`/`0xB2` |
| **RSA public key** (`assets/api.key`) | network layer | cloud HTTPS payload crypto only | RSA-2048 public key (not used in BLE) |

The session layer (V1/V2) is transparent: a normal control frame is built in plaintext,
then `IEncryption.c(frame)` encrypts before write and `IEncryption.f(notify)` decrypts
inbound notifications. It is opcode-agnostic.

### 4.1 Version detection

On connect, read characteristic `…2b12` (`Constants.b()`) in service `…1910`. Parse
(`BgcInfoReader.d`):
- `bArr[0]==1` → legacy descriptor; `encryptVersion = bArr[1]`.
- `bArr[0]==2` → `BgcInfoV2`: `bArr[1]`=encryptVersion, `bArr[2]==1`=flag, `bArr[3..4]`=u16 BE,
  `bArr[5]`=u8.

`encryptVersion==2` → `EncryptionManagerV2` (GCM); `==1` → `EncryptionManager` (ECB+RC4).
`EncryptionManagerPool.b()` builds the right manager and can rebuild a V1 manager into a V2
one if the descriptor changes.

### 4.2 Static app keys (`LibTools`)

Three static, app-global secrets, each derived by `AESUtils.decode(cipherResId, keyResId)`
= AES/ECB/PKCS5Padding decrypt → hex string → bytes:

| `LibTools` | Resources | Used as |
|---|---|---|
| `c()` | `decode(app_communication, app_session)` | V1 handshake key `K` (AES-ECB) |
| `a()` | `decode(app_y_com, app_x_name)` | V2 session-key-request GCM key `keyX` |
| `b()` | `decode(app_x_com, app_y_name)` | V2 per-device-key derivation key `keyY` (AES-ECB) |

These are the root of trust for the BLE session handshake — recoverable by decrypting those
string resources.

### 4.3 Crypto primitives

- **V1 (`Safe`)**: `AES/ECB/NoPadding` 16-byte block; any trailing `len%16` bytes are RC4
  (`Safe.g`, standard 256-int KSA/PRGA). A 20-byte frame = one AES-ECB block (0–15) + 4 RC4
  bytes (16–19).
- **V2 (`AesGcmUtils`)**: `AES/GCM/NoPadding`, 16-byte key, 12 random IV bytes, tag tries
  96-bit then falls back to 128-bit. Output `iv ‖ (ct‖tag)`; overhead = 12+4 = 16, MTU budget
  `max(20, mtu-16)`.

### 4.4 V1 handshake (`Controller4Aes`, type byte `0xE7`)

Frame builder `a(opcode, payload, 0xE7)` → `[0]=0xE7,[1]=opcode,[2..18]=random fill,[19]=BCC`,
then AES-ECB+RC4-encrypted with `K`. Timeout 6000 ms, 2 retries.

| Step | type | opcode | dir | meaning |
|---|---|---|---|---|
| Session-key request | `0xE7` | `0x01` | write (enc w/ `K`) | ask device for 16-byte session key |
| Session-key reply | `0xE7` | `0x01` | notify (enc w/ `K`) | `dec[2..18]` (16 bytes) = session key |
| Session-key confirm | `0xE7` | `0x02` | write (enc w/ `K`) | acknowledge key |
| Confirm ACK | `0xE7` | `0x02` | notify (enc w/ `K`) | session ready |

Steady state: outbound `Safe.d(frame, sessionKey)`, inbound `Safe.b(value, sessionKey)`.

### 4.5 V2 handshake (`Controller4AesGcm`, type byte `0xE7`)

| Step | type | opcode | dir | meaning |
|---|---|---|---|---|
| Session-key request (single) | `0xE7` | `0x11` | write (GCM w/ `keyX`) | request session key + device info |
| Session-key reply (single) | `0xE7` | `0x11` | notify (GCM w/ `keyX`) | `[2]`=status, payload → 8B key + 11B devinfo |
| Session-key request (split) | `0xE7` | `0x19` | write (GCM w/ `keyX`) | multi-packet variant (no MTU big-pkt) |
| Session-key reply (split) | `0xE7` | `0x19` | notify (GCM w/ `keyX`) | last pkt marked `0xFF` |
| Encrypted app data (split) | `0xE7` | `0x1A` | write/notify (GCM w/ `deviceKey`) | `[2]`=seqTotal; per-msg counter; last pkt `0xFF` |

Single request frame: `[0]=0xE7,[1]=0x11,[2]=0x00,[3..14]=12B IV,[15]=tagLen,[16..]=ct‖tag`,
AAD = first 15/16 bytes, GCM key `keyX`.

Reply carving (19 decrypted bytes): `[0..8)` = 8-byte session key / IV-base; `[8..13)` =
devinfo A (5B); `[13..19)` = devinfo B (6B).

Per-device key derivation: `devInfo = A‖B (11B)`, padded to 16B, `deviceKey = Safe.d(key16,
keyY)` (AES-ECB). Steady state GCM: IV = `sessionKey(8) ‖ counter4`, AAD = `counter4`, wire
frame `counter4 ‖ ct‖tag`, counter increments per message (starts at 1). Small-MTU path
splits via `0xE7 0x1A` packets.

### 4.6 Legacy secret code (`0xB1`/`0xB2`) — binding token, NOT session cipher

An older device-binding mechanism reading/writing an 8-byte "secret code" over a normal
(possibly plaintext) frame.

| Name | cmd-type `[0]` | opcode `[1]` | dir | payload | source |
|---|---|---|---|---|---|
| Read secret code (SINGLE_READ_SECRET_KEY) | `0xAA` | `0xB1` | write→notify | reply `[0]=1` ok, `[1..8]` = 8-byte secret | `SecretKeyController` (read ctor = `super(false)`) |
| Write/verify secret code (SINGLE_CHECK_SECRET_KEY) | `0x33` | `0xB2` | write | 8-byte secret (base64-decoded from store) | `SecretKeyController` (write ctor = `super(true)`) |

> **Correction applied (plug-h5080):** the read and check directions use **two distinct
> opcodes**, not one. `0xB1` (read) is `super(false)` → frame `byte[0]=0xAA`; `0xB2` (check)
> is `super(true)` → frame `byte[0]=0x33`. The byte definitions live in
> `com/govee/base2light/ble/controller/SecretKeyController.java:17,24,33` (and H5086
> `SecretController`: `getCommandType() = d() ? 0xB2 : 0xB1`). `BlePactV1.java`/`BleOpV2.java`
> only instantiate `SecretKeyController(secretKey)` (the write/check variant); they do not
> contain the literal opcode bytes.

The secret-code exchange maps to the `0xB1`/`0xB2` of the project ground-truth — it is the
binding step, **not** the AES session handshake (`0xE7 01/02` V1, `0xE7 11/19/1A` V2).

### 4.7 RSA public key

`assets/base_assets/assets/api.key` is an X.509 RSA-2048 public key used only by the
network/cloud crypto layer (HTTPS payload). **Not used anywhere in the BLE path.**

---

## 5. Broadcast / advertisement parsing

### 5.1 Scan pipeline

`BleScanCallbackImp21.j(ScanResult)` pulls the **entire raw AD payload** (`scanRecord`), de-dups
per MAC (3 s), optional RSSI gate. `ScanFilter` matches by service-UUID/MAC/name only —
**no manufacturer-id ScanFilter**; identification is done in software from raw bytes.
**Almost every parser hard-requires `scanRecord.length == 62`.**

### 5.2 Device identification

Local-name prefix (`BaseBleProcessor.parse`) → handler + SKU decode:

| Prefix | Value | SKU decode |
|---|---|---|
| `ihoment_` / `Govee_` / `Minger_` | V0 | `split("_")` → `[1]`=SKU (e.g. `ihoment_H5080_AB12`) |
| `GBK_` | V1 | same 3-part split |
| `GVH` / `GVR` | V2 | `substring(2, indexOf('_'))` = SKU |
| `GV` | V3 | `"H"+substring(2,6)` = SKU (e.g. `GV5080…` → `H5080`) |

SKU string → numeric `goodsType` via `Pact.d(sku)`.

**Manufacturer company ID** checked by every Govee parser: `BleUtil.f41010h = {0x88, 0xEC}`
— the Bluetooth SIG company `0xEC88` stored little-endian as **`88 EC`**, inside the
manufacturer-specific AD (type `0xFF`). `checkBroadcastData()` is the generic "is this a Govee
mfr block" probe.

> **Discrepancy RESOLVED (reconciled against working hardware).** The app's generic parser
> (`base2home/pact/BleUtil.f41010h = {0x88, 0xEC}`) matches company `0xEC88` — this is the
> **modern unified** path used by current-generation Govee devices. The **H5080 is a legacy
> plug** and does **not** use it: real H5080 hardware broadcasts manufacturer company IDs
> **`0x8802` and `0x8843`** (the firmware rotates between them), with the relay on/off state in
> the **last byte** of the manufacturer-specific data (`mfr_data[-1] == 0x01` = ON). This is
> confirmed by the maintainer's own working HA integration
> (`custom_components/govee_ble_plugs/plugs.py:503`, `GOvee_MANUFACTURER_IDS = (34818, 34883)`)
> and live hardware — it is the authoritative value for H5080. The app parses H5080 state mainly
> over the connected GATT path; its `0xEC88` broadcast parser targets newer SKUs.
>
> **Net rule:** for H5080/H5081 use company IDs `0x8802`/`0x8843`, on/off = last mfr byte. For
> modern SKUs use `0xEC88`, on/off at `v[6]` (raw idx `p+8`).

### 5.3 Standard manufacturer-data byte map (`parseBleBroadcastPact`)

At the AD where `len ≥ 6` and `type == 0xFF`, manufacturer value begins at `scanRecord[p+2]`
(`p` = index of the AD length byte):

```
v[0] = flags/version   (low nibble = bbVersion; bit6 0x40 = supportEncryption; state requires >=2)
v[1] = 0x88            company id low   ─┐ company 0xEC88 (LE 88 EC)
v[2] = 0xEC            company id high  ─┘
v[3] = pactType hi     ─┐ pactType = (v[3]<<8)|v[4]
v[4] = pactType lo     ─┘
v[5] = pactCode
v[6] = switch/on-off   (1=ON, 0=OFF)   ← plug primary relay   [raw idx p+8]
v[7] = switch2/aux                      ← plug 2nd relay       [raw idx p+9]
```

`BleBroadCastInfo` getters: `h()/a()`=flag (1=valid Govee block), `j()/b()`=pactType,
`i()/c()`=pactCode, `g()/d()`=bbVersion, `k()/e()`=supportEncryption, `l()`=ctor-arity marker.

> **Correction applied (broadcast §3 prose):** the `FunCall`/`broadcastVersionCall` is invoked
> when **`bleBroadcastPact.l() > 3`**, where `l()` is the **ctor-arity marker** (3 for the 3-arg
> ctor, 4 for the 4/5-arg version-bearing ctors) — **NOT** `bbVersion` (which is `g()/d()`).
> The condition means "the info was built with the version-bearing constructor", then it
> persists `supportEncryption` into `ShortMemoryMgr`. Source:
> `GoodsType.parseBleBroadcastPactInfo` (L1976/1984/2024/2032); `BleBroadCastInfo.l()` (L128).

### 5.4 Plug on/off state — `parseBleBroadOnOff`

At the AD with `len ≥ 6`, `type == 0xFF`, **and `scanRecord[p+2] (v[0]) ≥ 2`**, company
`88 EC`:

```
return { 1, getUnsignedByte(scanRecord[p+8]), getUnsignedByte(scanRecord[p+9]) };
```

- **`v[6]` (raw idx `p+8`) = primary relay**: `1 = ON`, `0 = OFF` (`AbsBaseBleModel.A`: `on = r[1]==1`).
- `v[7]` (raw idx `p+9`) = second state byte (2nd relay on dual-outlet plugs / aux).

The plug on/off is the **7th byte of the manufacturer value (`v[6]`)** — *not* literally the
last byte of the record (that's an artifact of short H5080 adverts).

Applicable plug goodsTypes: **43 (H5080 single), 50 (dual), 90 (triple H5160), 307** (from
`h5080/pact/Support.java`). `isOldH5080 = H5080 && version ≤ 10008`.

> Dual-outlet note: `AbsPlug2Model4BleIot.K0()` inverts switch index for `goodsType==50`
> (`goodsType!=50 ? !on : on`), so `v[6]`/`v[7]` map to left/right outlets with a per-goodsType
> polarity convention — confirm offset-to-outlet mapping on hardware.

### 5.5 Other state-from-broadcast parsers (same `88 EC` block, `v[0] ≥ 2`)

| Method (BleUtil) | Returns | Meaning |
|---|---|---|
| `parseBleBroadDaySyncInfo` | `{1, ub(p+9)}` | `v[7]` day-sync byte |
| `parseBleBroadTankState` | `{1, ub(p+8)}` | `v[6]` tank state |
| `parseBleBroadKettle` | `{1, ub(p+8), ub(p+9), ub(p+10), int(p+11..14)}` | kettle state/target/current/temp32 |
| `parseBleBroadIceMaker` | `{1, ub(p+8), ub(p+10), bit7(p+9), int(p+11..14), ub(p+9)}` | ice-maker multi-field |
| `parseBleBroadVersion` | `scanRecord[p+2]` | raw broadcast version byte (default 2) |

> **Correction applied (broadcast §4b):** `parseBleBroadVersion` does **NOT** check the
> company ID (`88 EC`) and does **NOT** require `v[0] >= 2`. It matches the first AD with
> `len>=6` and `type==0xFF` and returns `scanRecord[p+2]` unconditionally (default 2). The
> blanket "all share the §4a framing" statement over-generalizes for this one method; the
> other four parsers above do use the `v[0] ≥ 2` + `88 EC` framing. Source:
> `BleUtil.parseBleBroadVersion` (L794-806).

### 5.6 Variant parsers (same company-ID, different framing)

| Method | goodsTypes | Key difference |
|---|---|---|
| `parseBleBroadcastPact4Th` | 7,65,158,198,291 | accepts `bbVersion ≥ 1` (no `==1` special-case) |
| `parseBleBroadcastPact4MultiTh` | 8,66,14,106,… | company ID in a `0x03` service-data AD; following `0xFF` AD holds flags/pactType/pactCode |
| `parseBleBroadcastPactBbqV1` | 28,29,33,34,… | match `0x03` UUID AD against `f41011i`/`f41012j`; `0xFF` AD: flags `p+5`, pactType `p+6..7`, pactCode `p+8` |
| `parseH5140BleBroadcastPact` | 319 | `parseBleAdvertisement()` map, `len==11 && val[0]==0xFF` |
| `parseH512xBleAddBroadcast` | 130,131,132,139,… | exact-hex match: record starts `0201060b09`, `hex[30:38]=="0fff88ec"` |

---

## 6. Command reference by category

In every table, `byte[0]` is `0x33` for the write form and `0xAA` for the read form of the
same opcode (`byte[1]`) unless noted otherwise. Tables list the `byte[1]` opcode.

### 6.1 Common light command set (`base2light` controllers)

#### Core control

| Name | byte[0] | opcode | payload | dir | source |
|---|---|---|---|---|---|
| Main switch (SINGLE_SWITCH) | 33/AA | `0x01` | `[on]` 0/1 | W/R | `MainSwitchController`, `SwitchController` |
| Light switch | 33/AA | `0x30` | `[on]` 0/1 | W/R | `LightSwitchH6057Controller` |
| Brightness | 33/AA | `0x04` | `[level]` (0-100 or 0-255 per model) | W/R | `BrightnessController` |
| Mode / scene | 33/AA | `0x05` | write `subModeType + subPayload`; read `p()=[0x01]` | W/R | `AbsModeController` |
| Gradual change on/off | 33/AA | `0xA3` | `[enable]` 0/1 | W/R | `GradualChangeBleWifiController` (single cmd, not multi-A3) |

#### Mode sub-selectors (`byte[2]` of a `0x05` frame)

| sub-mode | byte | sub-mode | byte |
|---|---|---|---|
| color | `0x15` | new DIY | `0x0A` |
| color (multi) | `0x6E` | operate | `0x20` |
| music | `0x13` | operate V2 | `0x0C` |
| abs music | `0x16` | daysync | `0xF0` |
| scenes | `0x04` | carousel | `0x82` |
| part scenes | `0x47` | display | `0x81` |

#### Timers / schedules

| Name | byte[0] | opcode | payload | source |
|---|---|---|---|---|
| Sync time | 33 | `0x09` | `[hour,min,sec,week,0x01,tzH,tzM]` | `SyncTimeController` |
| Auto on/off time | 33/AA | `0x0A` | `[on,openH,openM,closeH,closeM,group,repeat]`; read `p()=[group]` | `AutoTimeController` |
| Delay close | 33/AA | `0x0B` | `[on,H,M]`; reply `[on,h1,m1,h2,m2]` | `DelayCloseController` |
| Sleep | 33/AA | `0x11` | `[enable,startBri,closeTime,curTime]` | `SleepController` |
| Wake up | 33/AA | `0x12` | `[enable,endBri,wakeH,wakeM,repeat,wakeTime]` | `WakeUpController` |
| New timer V1 | 33/AA | `0x23` | `[group,enableAndType,hour,min,repeat]`; read `p()=[group]` | `NewTimerV1Controller` |
| Set light-start index | 33 | `0x24` | `[index≥1, timeLo, timeHi]` | `SetLightStartController` |

#### Settings / behaviour

| Name | byte[0] | opcode | payload | source |
|---|---|---|---|---|
| Energy saving | 33/AA | `0x16` | `[on]` (1 byte) | `EnergySavingController` |
| Light indicator | 33/AA | `0x16` | `[en, startH,startM,endH,endM]` or `[en,FF,FF,FF,FF]` forever (5 bytes) | `LightIndicatorController` |
| Without-interrupt | 33/AA | `0x35` | `[value]` | `WithoutInterruptController` |
| Volume | 33/AA | `0x33` | `[volume]` | `VolumeController` |
| On/off power-loss memory | 33/AA | `0x41` | legacy `[on]`; typed `[0x02,type]`, read `p()=[0x02]` | `OnOffMemoryController` |
| Logo light | 33/AA | `0xA6` | off `[0x00]`; on `[0x01,bri,r,g,b]` | `LogoController` |
| Init/guide light | 33/AA | `0x38` | `[value]` | `InitLightController` |
| Movie/feast open | 33/AA | `0x54` | `[open]` | `MovieOpenController` |

> Opcode `0x16` is overloaded (energy = 1-byte payload; indicator = 5-byte). Disambiguate by
> product/context and payload shape.

#### Device-info reads — opcode `0x07` with sub-selector

| sub (`p()[0]`) | meaning | reply | source |
|---|---|---|---|
| `0x02` | device UUID/SN (8 bytes → MAC) | `SnController` | |
| `0x03` | hardware version (ASCII) | `HardVersionController` | |
| `0x04` | software version (ASCII) | `SoftVersionInDeviceInfoController` | |
| `0x07` | DSP version (2-byte int `[lo,hi]`) | `DspVersionInDeviceInfoController` | |
| `0x0A` | MCU soft version (ASCII) | `McuSoftVersionControllerV1` | |
| `0x0B` | MCU hard version (ASCII) | `McuHardVersionControllerV1` | |
| `0x10` | SN(8) + 2×3-byte versions | `BasicInfoController` | |
| `0x11` | wifi basic info | `BasicWifiInfoController` | |

#### Standalone reads

| Name | byte[0] | opcode | reply | source |
|---|---|---|---|---|
| Soft version | AA | `0x06` | ASCII | `SoftVersionController` |
| Wifi MAC | AA | `0x14` | 6-byte MAC | `WifiMacController` |
| Wifi hard version | AA | `0x20` | ASCII | `WifiHardVersionController` |
| Wifi soft version | AA | `0x21` | ASCII | `WifiSoftVersionController` |
| Wifi new-msg unified (V2) | AA | `0x49` | sub `0x01`=mac, `0x02`=soft, `0x03`=hard | `WifiMacControllerV2` etc. |
| Protocol / pact | AA | `0xEF` | `[typeHi,typeLo,code]` | `PactController` |
| IC count | AA | `0x40` | 2-byte signed short | `IcNumController` |
| Dynamic-API support | AA | `0xAB` | `[version, support]` | `DynamicApiSupportController` |
| Heart / liveness | AA | `0x01` | `validBytes[0]!=0` = alive | `HeartController` |

#### OTA / IC / misc writes

| Name | byte[0] | opcode | payload | source |
|---|---|---|---|---|
| OTA prepare | 33 | `0xEE` | none | `OtaPrepareController` |
| Refresh / check IC | 33 | `0x42` | empty | `RefreshIcController` |
| Check IC amount | 33 | `0x43` | — | `CheckICAmountController` |
| Check camera install | AA | `0x32` | — | `CheckCameraController` |
| Check direction finish | — | `0x39` | — | `CheckDirectionFinishController` |
| Wifi link-start | 33 | `0x17` | `[open]` 0/1 | `WifiLinkStarController` |
| Video mode params | 33/AA | `0xA9` | read `p()=[type]` | `VideoModeParamsController` |

#### Multi-packet comTypes (light, carried in `byte[1]` of an `0xA1`/`0xA3` frame)

| comType | const | controllers |
|---|---|---|
| `0x01` | MULTI_V1_NEW_SCENES | `MultiNewScenesControllerV1` |
| `0x02` | MULTI_V2_NEW_SCENES / MULTI_DIY | `MultiNewScenesControllerV2`, `MultipleDiyController` |
| `0x03` | MULTI_V1_NEW_DIY_GRAFFITI | `MultiDiyGraffitiController` |
| `0x04` | MULTI_V1_NEW_DIY | `MultipleDiyControllerV1/V2` |
| `0x07` | MULTI_V3_NEW_SCENES | `MultiNewScenesControllerV3` |
| `0x0A` | MULTI_V4_NEW_SCENES | `MultiNewScenesControllerV5` |
| `0x0C` | MULTI_DIY_PROTOCOL_SCENES | `MultiNewScenesControllerV6/V7` |
| `0x11` | MULTI_WIFI | `MultipleWifiController` |
| `0x40` | MULTI_V1_NEW_COLOR | `MultipleColorStripControllerV1` |
| `0x41` | MULTI_V1_NEW_MUSIC | `MultiMusicController` |
| `0x50` | MULTI_SET_DEVICE_4_MOVIE_FEAST | `MultiSetSubDeviceController4MovieFeast` |
| `0x56`..`0x5A` | graffiti / cube / scene-apply | `MultiNewScenesControllerV8/V9/V10/H60B0` |

#### Encryption handshake (common-light view)

| Name | byte[0] | opcode | dir | payload | source |
|---|---|---|---|---|---|
| Read secret key | AA | `0xB1` | R | reply `[0x01, key(8)]` → base64 stored | `SecretKeyController` (read ctor) |
| Check secret key | 33 | `0xB2` | W | base64-decoded secret bytes | `SecretKeyController` (write ctor) |

### 6.2 Plugs H5080 / H5082 / H5083 / H5085 / H5160 / H5161 (V1–V4)

GATT: service `…1910`, unified write+notify `…2b11`. Frame = standard 20-byte. The same
controllers drive the IoT/cloud `ptReal` passthrough (§7).

#### SKU ↔ goodsType ↔ frame builder

| goodsType | frame builder | outlets | SKUs |
|---|---|---|---|
| 43 | `adjust/v1/FrameV1` (+ `v3/UiV3`) | 1 | H5080, H5082, H5083, H5085 |
| 50 | `adjust/v2/FrameV2` | 2 | dual-outlet plug |
| 90 | `adjust/v4_h5160/FrameV4` | 3 | H5160, H5161 |
| 307 | `adjust/h5089/Frame4H5089` | 2 | H5089 night-light plug |

Accepted `(pactType, pactCode)` pairs (`Support.addSupportPact`): 43 → (1,1)(1,2)(2,1)(2,2);
50 → (1,1)(1,2)(2,1); 90 → (1,1)(2,1); 307 → (1,2)(2,2). Newer H5083/H5085 firmware routes to
the generic `base_h71xx` "newdetail" path (§6.2 last row).

#### Opcode map (`ble/BleConstants.java`)

| Name | byte[0] | opcode | payload / meaning | dir | source |
|---|---|---|---|---|---|
| Relay switch | 33/AA | `0x01` | value byte (nibble mask, see below) | W/R | `SwitchControllerV2` |
| Battery | AA | `0x08` | read | R | `BleConstants` (legacy) |
| Wifi status | AA | `0x09` | read | R | `BleConstants` |
| Temp/humidity | AA | `0x0A` | read | R | `BleConstants` |
| Device id | AA | `0x0C` | read | R | `BleConstants` |
| Device hard version (legacy) | AA | `0x0D` | ASCII | R | `BleConstants` |
| Device soft version (legacy) | AA | `0x0E` | ASCII | R | `BleConstants` |
| Listener pair | — | `0x0F` | pairing listener | — | `BleConstants` |
| Date reset / wifi-connect notify | — | `0x11` | — | — | `BleConstants` |
| Timer count | AA | `0x12` | `p()=[outlet/group]`; reply `count=byte[1], group=byte[0]` | R | `NewTimerCountController` |
| Timer V2 (per-outlet) | 33/AA | `0x13` | write `[subIndex,group,enSw,hour,min,repeat]`; read `[subIndex,group]` | W/R | `NewTimerControllerV2` |
| Delete timer | 33 | `0x15` | `[outletIndex, timerGroup]` | W | `TimerDeleteController` |
| Indicator light op-type | 33/AA | `0x16` | — | W/R | `BleConstants` |
| Total switch (H5089) | 33/AA | `0x02` | `[on]` | W/R | `Controller4TotalSwitch` |
| Child-lock op-type (H5089) | 33/AA | `0x1F` | `[0x02, on]` | W/R | `Controller4ChildLock` |
| Wifi hard version | AA | `0x20` | ASCII | R | `WifiHardVersionController` |
| Wifi soft version | AA | `0x21` | ASCII | R | `WifiSoftVersionController` |
| Night-light sleep (H5089) | 33/AA | `0x28` | 10-byte sleep payload | W/R | `Controller4NlSleep` |
| Night-light wake (H5089) | 33/AA | `0x29` | 12-byte wake payload | W/R | `Controller4NlWakeUp` |
| Read secret key | AA | `0xB1` | crypto handshake | R | `SecretKeyController` |
| Check secret key | 33 | `0xB2` | crypto handshake | W | `SecretKeyController` |
| Spec read | AA | `0xB3` | reply `spec=byte[0]` | R | `SpecController` |
| Legacy new timer (V1) | 33/AA | `0xB4` | see §timers below | W/R | `NewTimerController` |
| Sync time | 33 | `0xB5` | `[ts(4B BE), 0x01, hOff, mOff]` | W | `SyncTimeController` |
| Delay on/off | 33/AA | `0xB0` | `[outlet, delayType, min/60, min%60]` | W/R | `TurnOnOffDelayController` |
| Multi-write wifi-setting | A1 | sub `0x01` | provisioning | W | `BleMultiComm` |

> **Live-read opcode note:** modern init (`BleOpV2`/`BleOpV4`) reads versions with the
> *generic* `base2light` controllers (soft `0x06`, hard `0x07`, wifiMac `0x14`, wifiSoft
> `0x21`, wifiHard `0x20`). The `BleConstants` `0x0D`/`0x0E` device soft/hard opcodes are the
> older V1-firmware values. Treat `0x06`/`0x07` as the live read opcodes, `0x0D`/`0x0E` as
> legacy.

#### Relay ON/OFF value byte (`SwitchControllerV2.q`, mirrored in `iot/CmdTurn`)

The single payload byte packs an **outlet-select mask in the high nibble** and the **desired
states in the low nibble**:

| outlet arg | high-nibble mask | low-nibble (ON) | value ON | value OFF |
|---|---|---|---|---|
| 0 | `0x10` | bit0 | `0x11` | `0x10` |
| 1 | `0x20` | bit1 → `0x02` | `0x22` | `0x20` |
| 2 | `0x40` | bit2 → `0x04` | `0x44` | `0x40` |
| else (= "all", arg 15) | `0xF0` | `0x0F` | `0xFF` | `0xF0` |

Frame: `33 01 <value> 00…00 <BCC>`. Whole-plug toggle uses arg 15 (`0xFF`/`0xF0`); per-outlet
uses the outlet index. Read uses no-arg `SwitchControllerV2()` (`AA 01`); response `byte[0]`
is a bitfield where **bit i = outlet i on/off** → `List<Boolean>` of 8 flags (`EventSwitchV2`).
`HeartControllerV2` (opcode `0x01`) parses the same 8-bit field. `EventSwitchV2.h()` reconciles
a pending write via `(mask >> (i+4)) & 1`.

#### Timers

- **Legacy timer `0xB4`** (`NewTimerController`): write `[group|(outlet?0x10:0), enableAndType,
  hour, minute, repeat]`; read `[(readType?1:0), 0xFF]` (`0xFF` = all groups). Parse: group
  `0xFF` reads 4 timers × 4 bytes `[enableAndType,hour,minute,repeat]` from offset 1.
  `parseGroup = bytes[0]&0x0F`, `parseIndex = (bytes[0]&0x10)>>4`.
- **Timer V2 `0x13`** (`NewTimerControllerV2`): write `[subIndex, group, enableAndSwitch, hour,
  min, repeat]`; read `[subIndex, group]`. Parse: `byte[0]` split into `[groupHigh, outlet]`
  nibbles, then 16 bytes = 4 timers × 4 bytes.
- **H5089 timer V2 `0x13`** (`Controller4H5089TimerInfo`): read `p()=[(group<<4)|outlet]`.
- **Timer count `0x12`** (read-only); **Delete timer `0x15`** (write `[outletIndex, timerGroup]`).

#### Delay / sync-time / spec

- **Delay on/off `0xB0`** (`TurnOnOffDelayController`): write `[outletIndex, delayType,
  minutes/60, minutes%60]`; read `[outletIndex, delayType]`. **delayType: 0 = off/sleep delay,
  1 = on/wake delay.** Parse: `minutesConfigured = bytes[2]*60+bytes[3]`, `remaining` = signed
  int from bytes[4..6].
- **Sync time `0xB5`** (write): `[ts(4-byte signed BE, epoch seconds), 0x01, hourOffset, minuteOffset]`.
- **Spec read `0xB3`** (read): no payload; reply `spec = byte[0]`.

#### H5083 / H5085 "newdetail" path (generic `base_h71xx`)

`H5083NewDetailRepository.necessaryMessages()` (on connect) sends a `base_h71xx` SyncTime, a
`base2light` `SwitchController`, then dynamic `H()/D()/J0()/j1()` opcodes (per-SKU,
server-driven `BleProtocolConstants` table — not pinnable from static constants).

> **Correction applied (plug-h5080 §8):** at `H5083NewDetailRepository.java:302` the switch is
> built with the **no-arg** `new SwitchController()` = `super(false)` = **READ**, so as built at
> that line the frame is `byte[0]=0xAA` (a state poll inside `necessaryMessages()`), not a `0x33`
> write. Opcode `0x01` is correct (base `SwitchController.getCommandType()` returns 1); the
> on-write path (`SwitchController(boolean) → super(true)`) does use `0x33 0x01`, so the opcode
> is right but the "dir=write" label is imprecise for that cited line. Source:
> `SwitchController.java:9-11,24-26`; `H5083NewDetailRepository.java:302`.

#### Notify parsing

| Parser | notify comType (`byte[1]`) | payload | meaning |
|---|---|---|---|
| `WifiNotifyParse` | `0x11` | `byte[0]==0` ⇒ connected | wifi connect |
| `h5089/Notify4NightLight` | `0x1B` | night-light state | NL UI update |

All multi-byte control commands are single 20-byte frames — even the "read all 4 timers"
response packs 4 timers into one frame rather than multi-packeting. Multi-packet (`0xA1`/`0xA2`)
is used only for the Wi-Fi provisioning blob during pairing.

### 6.3 H5086 Smart Plug Pro (energy + chart)

Energy-metering plug: instantaneous V/A/W + cumulative kWh, hourly/10-min energy charts,
power-warning + auto-off thresholds, runtime "time monitor", child-lock, indicator schedule,
delay on/off, 4-slot timers. Two channels on one connection: command `…1910/2b11` and Telink
chart `…4857/2014/2015`.

#### Command-channel opcode map (`…1910/2b11`)

| Feature | byte[0] | opcode | sub-byte (`payload[0]`) | source |
|---|---|---|---|---|
| Main switch | 33/AA | `0x01` | — | `SwitchController` |
| Delay on/off | 33/AA | `0xB0` | 0=off-timer, 1=on-timer | `DelayOnOffController` |
| Child lock | 33/AA | `0x1F` | 2 | `ChildLockController` |
| Indicator light (do-not-disturb) | 33/AA | `0x16` | — | `LightController` |
| Instantaneous electric read | AA + notify `0xEE 0x19` | `0x19` | — | `DeviceElectricController` |
| Power warning (V1, combined) | 33/AA | `0x27` | (write-off uses sub 2) | `PowerWarningController` |
| Power warning (V2) | 33 | `0x28` | 1=warning, 2=auto-off | `PowerWarningControllerV2` |
| Device basic info (MAC+fw) | AA | `0x07` | `0x10` | `DeviceBasicInfoController` |
| Wi-Fi module info | AA + notify `0xEE 0x11` | `0x07` | `0x11` | `WifiInfoController` |
| Exception / fault state | 33(query)/AA | `0x17` | — | `ExceptionStateController` |
| Sync time | 33 | `0xB5` | — | `SyncTimeController` |
| Recent-1-hour chart (10-min) | single-send/multi-back | `0x01` | `0x0D` | `RecentOneHourChartController` |
| Timer read (4 slots) | single-send/multi-back | `0x01` | `0x13` | `TimerReadController` |
| Timer write | 33 | `0xB4` | — | `TimerWriteController` |
| Timer delete | 33 | `0x15` | — | `TimerDeleteController` |
| Time-monitor session | 33/AA + notify `0xEE 0x1A` | `0x1A` | — | `TimeMonitorController` |
| Secret key (read) | AA | `0xB1` | — | `SecretController` |
| Secret key (write) | 33 | `0xB2` | — | `SecretController` |
| "Read-all" refresh trigger | notify `0xEE 0xAA` | `0xAA` | — | `ReadAllNotifyParse` |

#### Instantaneous electric read `0x19` (13 payload bytes, all big-endian signed)

| bytes | field | decode | unit |
|---|---|---|---|
| `[0..2]` | runtime | `getSignedInt / 60` | minutes (raw seconds) |
| `[3..5]` | electricUse | `getSignedInt / 10000.0` | kWh (cumulative) |
| `[6..7]` | volts | `getSignedInt / 100.0` | V |
| `[8..9]` | amps | `getSignedInt / 100.0` | A |
| `[10..12]` | activePower | `getSignedInt / 100.0` | W |

Pushed as notify `0xEE 0x19` (`DeviceStateNotifyParse`). Result `ElectricData`.

#### Power warning

- **V1 `0x27`** read parses `[warningIsSet=it2[0]==1, warningOpen=it2[1]==1,
  warningValue=H(it2[2..3])W, offIsSet=it2[4]==1, offOpen=it2[5]==1, offValue=H(it2[6..7])W]`.
  Write warning `d()` → `[flag, valHi, valLo]`; write auto-off `e()` → `[2, offOpen, valHi, valLo]`.
- **V2 `0x28`** (write-only, fw ≥2): warning `b()` → `[1, on, valHi, valLo]`; auto-off `a()` →
  `[2, on, valHi, valLo]`. Null value → `{-1,-1}`.

#### Time-monitor session `0x1A`

Write `[running, hour, min, id(4B BE)]`. Parse `TimeMonitorInfo`: `id=[0..3]`, `state=[4]`,
`hour=[5]`, `minute=[6]`, `remainSeconds=[7..9]`, `electUse=[10..12]` (raw int; kWh scale
applied downstream).

#### Chart history

- **Recent 1 hour @ 10-min (`0x01`/`0x0D`)**: single write → multiple `0xAA` packets
  reassembled. Buffer: `[0..3]`=start timestamp (seconds, rounded to 10-min boundary), then
  3-byte entries from offset 4: sample = `start + i*600 s`; all-`0xFF` = empty;
  `value0=H(entry[0])`, `valueFloat=H(entry[1..2])/10000.0` kWh.
- **Bulk multi-hour (Telink `…4857`)**: (1) Prepare `33 02` empty on char G2 `…2014`; (2)
  Time-range `33 01` 8-byte `{start(4B BE), end(4B BE)}` on G2; (3) device streams on char H2
  `…2015` — packets `packetIndex=H(bArr[0..1])`, 5 hourly entries × 3 bytes from offset 4,
  sample = `start + (packetIndex+i)*3600 s`. (4) Flow-control notifies on the Telink chip
  service, marker `0xEE`: `payload[0]==2` querying, `payload[0]==1` complete (`totalPackets=
  getSignedInt(payload[1..2])`). Watchdog 10000 ms.

#### Device / Wi-Fi info (`0x07`, sub-byte disambiguated)

- **Sub `0x10`** `DeviceBasicInfoController`: `[1..8]`=BLE address, `[9..11]`=soft version
  (`major.%02d.%02d`), `[12..14]`=hard version, `[15]`=unknown 1-byte (flagged).
- **Sub `0x11`** `WifiInfoController`: `[1..6]`=Wi-Fi MAC, `[7..9]`=wifi soft, `[10..12]`=wifi hard.

#### Timers (4 slots)

- Read `0x01`/`0x13`: 4-byte records, `record[0]` bit `0x80`=enable, low nibble==1=open,
  `[1]`=hour, `[2]`=min, `[3]`=repeat bitmask.
- Write `0xB4`: `[group, enableAndSwitch, hour, min, repeat]`. Delete `0x15`: `[group]`.

#### Composite read

`ReadInfoController(full, version)` chains many controllers; **`version ≥ 2`** gates the
RecentOneHourChart + PowerWarning-V1 path (the practical "which variant the firmware supports"
signal). `PairToDeviceInfoReadController` is the lighter pairing composite.

### 6.4 H5089 / H5085 night-light plug

Built on the H5080 frame stack (`com.govee.h5080.*`), adds a total switch, per-outlet switches
(shared `SwitchControllerV2`), child lock, an RGB night-light sub-protocol (via `base_h71xx`
"light71xx"), NL sleep/wake schedules, H5089 timer enumeration, and Matter onboarding hints.

#### Opcode map (`byte[1]`)

| Feature | byte[0] | opcode | controller |
|---|---|---|---|
| Total (master) switch | 33/AA | `0x02` | `Controller4TotalSwitch` |
| Per-outlet switch (idx 0/1) | 33/AA | shared `SwitchControllerV2` (`0x01`) | `BleOp4H5089.onEventSwitchV2` |
| Child lock | 33/AA | `0x1F` | `Controller4ChildLock` |
| Night-light switch / brightness | 33/AA | `0x1B` (= `b0()=27`) | `Controller4NlSwitch` |
| Night-light mode (color/scene/diy) | **`0x3A` wr / `0xAA` rd** | `0x1B` | `LightRgbController` (base_h71xx) |
| Night-light DIY upload (multi) | A3 | comType `0x04` | `DiyMultipleControl` |
| Night-light notify | EE | `0x1B` | `Notify4NightLight` |
| Night-light sleep schedule | 33/AA | `0x28` | `Controller4NlSleep` |
| Night-light wake-up schedule | 33/AA | `0x29` | `Controller4NlWakeUp` |
| Timer count (per index) | 33/AA | `0x12` | `NewTimerCountController` |
| Timer info (read, 4 groups/pkt) | AA | `0x13` | `Controller4H5089TimerInfo` |
| Turn-on/off delay | 33/AA | `0xB0` | `TurnOnOffDelayController` |
| Indicator / "do not disturb" | 33/AA | `0x16` | `NotDisturbController` |

`BleProtocolConstants` resolved defaults: `b0()=0x1B`, `h()=1`, `i()=2`, `m()=1`, `g()=5`,
`j()=0x0D`, `n()=0x13`, `l()=0x0A`, `k()=0xFC`, `v1()=0x3A`, `O0()=0xAA`.

> **proType override (flagged):** `LightRgbController.getProType()` returns `v1()` (default
> `0x3A`=58) on write and `O0()` (default `0xAA`) on read instead of `0x33/0xAA`. These come
> from runtime-configurable `BleProtocolConstants`, so a per-SKU init may reset them — treat
> `0x3A`(write)/`0xAA`(read) as the decompiled default and verify on-wire.

#### Key payloads

- **Total switch `0x02`**: write `[on?1:0]`; sets both outlets together.
- **Child lock `0x1F`**: read `p()=[0x02]`; write `[0x02, on]`; parse requires `[0]==0x02`,
  locked = `[1]==1`.
- **Night-light on/off & brightness (`0x1B` sub `0x01`)**: read `p()=[0x01]`; write switch
  `[0x01, 0x01, on]` (`33 1B 01 01 <on>`); write brightness `[0x01, 0x02, bri(0-100)]`
  (`33 1B 01 02 <bri>`). Return path `[01, on, brightness]` — note writes insert the `m()/i()`
  field-selector at `[1]`, reads omit it.
- **Night-light mode (`0x1B` sub `0x05`)** via `LightRgbController` (proType `0x3A`/`0xAA`):
  payload `[subCmd(0x05), (optional deviceState), subModeByte, ...modeData]`. Sub-mode bytes:
  COLOR `0x0D`, SCENE `0x13`, DIY `0x0A`, DEFAULT `0xFC`.
  - COLOR: `3A 1B 05 0D <R> <G> <B> <Kh> <Kl>` (kelvin big-endian, 0 for pure RGB).
  - SCENE: `3A 1B 05 13 00 <scene>`.
  - DIY: `3A 1B 05 0A <diyRef…>` (DIY program uploaded separately via `0xA3` multi).
  - DEFAULT: `3A 1B 05 FC`.
- **NL sleep `0x28`** (10-byte): `[enable, startBri, closeTime, curTime, defaultLight,
  rgb0..2, ct0, ct1]` (ct only when color-temp, else `{0,0}`).
- **NL wake `0x29`** (12-byte): `[enable, endBri, wakeHour, wakeMin, repeat, wakeTime,
  defaultLight, rgb0..2, ct0, ct1]`.

#### H5089 timers (three scopes: outlet0=0, outlet1=1, night-light=2)

`Controller4H5089TimerInfo` (`0x13`): read `p()=[(group<<4)|index]`; parse splits
`bArr[0]` into `[index, group]` nibbles, then 16 bytes = 4 timer records.
`NewTimerCountController` (`0x12`) returns count; flow issues `ceil(count/4)` info reads.

IoT mirror: `state.onOff` is a 2-outlet bitmask (`outlet0 = onOff&1`, `outlet1 = onOff&2`);
`op.ptBytes` are raw 20-byte BLE frames dispatched by `bArr[1]` exactly like notify.

Matter (`H5085MatterHelper`): eligibility gate only (goodsType 43+H5085 needs wifi soft/hard
`"3.01.00"`+; goodsType 307 unconditional) — does not change the BLE protocol.

### 6.5 RGB / RGBIC light survey

Almost everything light-specific rides inside command type **`0x05` (SINGLE_MODE)**; the frame
is `33 05 <subModeType> <sub-mode payload…> XOR`. The first payload byte after `0x05` is the
sub-mode command type.

#### Sub-mode command types (`byte[2]`)

| sub-mode | byte | meaning | source |
|---|---|---|---|
| scenes | `0x04` | apply scene id (single-packet) | `SubModeScenes` |
| new DIY | `0x0A` | apply DIY code | `SubModeNewDiy` |
| color (legacy 15-seg) | `0x0B` | RGBIC segment color v1 | `SubModeColor` (dreamcolorv1) |
| color WW | `0x0D` | whole-light RGB + color temp | `SubModeColor4Ww` (stringlightv2) |
| music | `0x13` | music reactive (v1 variants) | `SubModeMusic` |
| color v2 | `0x15` | RGBIC segment color v2 (+temp/bri) | `SubModeColorV2` |
| abs music | `0x16` | unified music (effect + sensitivity) | `SubModeAbsMusic` |
| mic (H6192) | `0x05` | mic on | `SubModeMicH6192` |
| operate | `0x20` | operate/cut-cali | `BleProtocolConstants` |
| part scenes | `0x47` | partial-segment scene | `BleProtocolConstants` |
| color multi | `0x6E` / carousel `0x82` / display `0x81` / daysync `0xF0` | — | `BleProtocolConstants` |

#### Whole-light RGB + color temp — `SubModeColor4Ww` (0x0D)

```
[0] 0x0D   [1] R  [2] G  [3] B  [4] kelvin_hi  [5] kelvin_lo (signed 16-bit BIG-endian)
[6] tempR  [7] tempG  [8] tempB    (white-point RGB for that kelvin)
```
Pure RGB: kelvin=0, tempRGB=0. White at CCT: main RGB = `ColorUtils.toWhite()`, kelvin/tempRGB filled.

#### RGBIC segment color

- **v1 `SubModeColor` (0x0B)**: `[0]=0x0B, [1..3]=R,G,B, [4]=segMask0..7, [5]=segMask8..14`.
- **v2 `SubModeColorV2` (0x15)** — `byte[1]` is a format selector:
  - Format 1 (`[1]=0x01`): `R,G,B, kelvin_hi, kelvin_lo, tempR,tempG,tempB, segmentBitmask`.
  - Format 2 (`[1]=0x02`): `index, segmentBitmask`.
  - Format 3 (`[1]=0x03`): per-segment brightness array (`[2]`=page for 18-seg, then 14 bytes).
- **Multi-packet whole-strip color — comType `0x40`** (`MultipleColorStripControllerV1`): payload
  `[groupCount, (per color group: 0x00, count, R,G,B, pos…), (per brightness group: 0x01, count,
  bri, pos…)]`, sent multi-packet.

#### Scene

- **Single-packet `SubModeScenes` (0x04)**: `[0]=0x04, [1]=scene_lo, [2]=scene_hi]` (16-bit
  **little-endian**).
- **Multi-packet `MULTI_*_NEW_SCENES`**: comType selects version (`0x01` V1, `0x02` V2, `0x07`
  V3, `0x0A` V4, `0x0C` preview, `0x56/0x58/0x5A` graffiti/cube/H60B0). Payload = opaque
  per-scene effect blob (`base2light/ble/scenes/*`). Practical path: stream the prebuilt effect
  byte array as a comType-appropriate multi-write.

#### DIY / music / mic

- **DIY apply `SubModeNewDiy` (0x0A)**: `[0]=0x0A, [1]=diy_lo, [2]=diy_hi]` (16-bit LE; selects
  a stored DIY code). DIY *definition* uploaded via multi comTypes `0x02/0x04/0x03/0x09`.
- **Unified music `SubModeAbsMusic` (0x16)**: `[0]=0x16, [1]=effect_lo, [2]=effect_hi (16-bit LE),
  [3]=sensitivity 0..99]`.
- **Legacy music `SubModeMusic` (0x13)**: layout depends on effect type in `[1]` (16/17/18/19);
  `[2]`=sensitivity, then color-mode flag and optional R,G,B (offsets shift per type).
- **Mic `SubModeMicH6192` (0x05)**: `{0x05}` only.

#### Encoding helpers

- Color temp kelvin: `getSignedBytesFor2(kelvin, true)` = **big-endian** 2 bytes.
- Scene/DIY codes: `getSignedBytesFor2(code, false)` = **little-endian** 2 bytes.
- Segment bitmask: `makeBytes4SelectPosByOneBit(boolean[])`, LSB = lowest segment.

### 6.6 Sensors & appliances survey

Shared 20-byte frame; write `0x33` / read `0xAA`; notify `0xEE`; multi `0xA1`/`0xA2`.

#### Temperature / humidity encodings

- **Centi-units**: temp = °C × 100; humidity = %RH × 100 (most connected frames). Sentinels:
  invalid temp `-100000`, invalid hum `-1`, raw `0xFFFF` = no data / probe disconnected.
- **Packed 3-byte (`ThBroadcastUtil.m()` / `parseThValue`)**: `raw = signedInt(bytes[0..2], BE)`;
  MSB of byte0 = sign flag (subtract 128); `tem = (raw/1000)*10` centi-°C, `hum = (raw%1000)*10`
  centi-%. Net `temp_°C = tem/100`, `hum_% = hum/100`.
- **PM2.5 packing (`parseThpValue`, 4 bytes)**: `[tem, hum, pm25]` for H5106/H5108 air monitors.

#### Thermo-hygrometer opcodes (`pact_thnew` / `base2newth`)

| opcode | name | controller | payload |
|---|---|---|---|
| `0x01` | Heartbeat V1 | `Controller4HeartV1` | read → `[temp(2), hum(2), batt, flag]` |
| `0x02` | Temp unit | `Controller4TemUnit` | `[unit]` 0=°C 1=°F |
| `0x03` | Humidity warning | `Controller4HumWarning` | `[on, min(2 LE), max(2)]` centi-% |
| `0x04` | Temp warning | `Controller4TemWarning` | `[on, min(2), max(2), type]` centi-°C |
| `0x05` | Upload frequency | `Controller4UploadFreq` | `[d, e]` |
| `0x06` | Humidity calibration | `Controller4HumCali` | `signedBytesFor2(cali)` LE |
| `0x07` | Temp calibration | `Controller4TemCali` | `signedBytesFor2(cali)` LE |
| `0x08` | Battery | `Controller4Battery` | read → `%` |
| `0x0A` | Heartbeat V0 | `Controller4HeartV0` | read → temp/hum |
| `0x10` | Sync time | `Controller4SyncTime` | `signedBytesFor4(unixSecs)` |
| `0x30` | Volume / buzzer | `Controller4Volume` | `[level]` |
| `0x36` | Multi (chart data) | `Controller4ThMulti` | empty (`0xA1/0xA2` multi) |

Heartbeat V1 `.j()` standard: `[0..1]`=temp signedShort, `[2..3]`=hum signedInt, `[4]`=battery%,
`[5]`=warning/online flag. `.k()` H5112 probe: adds a second temp `[4..5]`, battery `[6]`,
bit-field status `[7]`. SKU-scoped opcode reuse: H5107/H5109 use `0x08` for both temp-warning
and long-life switch; H5310 long-life = `0x05`.

Extra families: H5106/H5108 clock+air (`0x12` display, `0x13` lightness, `0x15` timezone,
`0x16` PM2.5 warning, `0x17` time format, `0x18` upload-last, `0x19` lightness V2); H5140 CO₂
(`0x16` CO₂ warning, `0x1B` sound level, `0x1C` manual cali, `0x1D` set grade, `0x1E` do-not-
disturb, `0x1F` air-quality switch); H5112 probe gateway (`0x15` probe icon, `0x35` check net,
`0x70` probe real-time op).

#### BBQ multi-probe (`pact_bbqnew`)

Opcode constants (`BbqBleProtocol`): heartbeat `0x03`; preset inner temp `0x01`(legacy)/`0x09`(new);
preset env temp `0x11`; device id `0x06`(legacy)/`0x0C`(new); upload interval `0x05`; switch
buzzer `0x07`; sync time `0x0A`; probe pair `0x41`; break pair `0x42`; clear probe `0x40`; close
alarm `0x33`; buzzer gear `0x25`; auto-shutdown / auto-reduce-brightness `0x26`; pre-warn
`0x0C`(legacy)/`0x27`(new); heartbeat V1 (new) `0x24`.

| opcode | name | controller | payload |
|---|---|---|---|
| `0x01`/`0x09` | Preset inner-meat target | `PresetInnerTempController` | probeId, hi/lo target, foodType |
| `0x11` | Preset ambient temp | `PresetEnvTempController` | `[probeId, hi(2 LE ×100), lo(2), foodType, sub(2)]` |
| `0x0C`/`0x27` | Pre-warn threshold | `Controller4PreWarn` | `[on, temp(2 LE ×100)]` |
| `0x41` | Probe pair | `Controller4ProbePair` | `[probeId]`; notify result `ProbePairResultParse` |
| `0x42` | Break pair | `Controller4BreakProbePair` | `[probeId]` |
| `0x40` | Clear probe | `Controller4ClearProbe` | — |
| `0x33` | Close alarm | `Controller4CloseAlarm` | — |
| `0x03` | Heartbeat | `Controller4BbqHeart` | `[toggle]` |

Probe temperature: `b(lo,hi) = signedIntV2(LE)/100.0` (°C, 0.01 res, signed; `0xFFFF` → `-10000`
sentinel) modern; `c(lo,hi) = ub(lo)+ub(hi)*256` whole-degree (older). Heartbeat V1 (6 probes):
`[0]`=battery%+unit bit7, `[1]`=connected mask, `[2]`=inner-alarm mask, `[3]`=charge bits,
`[4+2k]`=probe k temp. Broadcast round-robins 2 probes per advert via a byte[4] group index.

#### Humidifier H7160 / Ice maker H7172 (`base_h71xx` framework)

Opcodes re-assigned per-SKU at runtime (`base_h71xx.sku_base.BleProtocolConstants`; defaults
indicative). Heartbeat `HeartControllerV1`. Mode controllers share command type `d0()`
(default `0x05`), sub-mode in `payload[0]`. Abnormal/fault info `w()` = `0x17`. Ice maker adds
main switch `0x01`, ice-size mode, delay start, equipment status.

#### Sensor gateways (H5042/H5043/H5151)

Relay sub-device frames over multi-packet. H5042 sub-device info notify `0x34`; H5043 leak
parses (H5044 = water-leak); H5151 = BBQ/TH Wi-Fi gateway. Sub-device byte layouts are
delegated to obfuscated `Event4*` classes — not fully resolved.

---

## 7. BLE ↔ cloud passthrough cross-reference

The plug controllers double as cloud passthrough payload builders:

- `iot/CmdTurn(boolean, int)` reproduces the exact §6.2 nibble-mask math, sent as the `"turn"`
  command.
- `iot/CmdPtReal` wraps any `AbsSingleController` so its 20-byte BLE frame is forwarded
  verbatim through the cloud (`writeCmd(new CmdPtReal(controller))` throughout `UiV1..UiV4`).
- H5089 `CmdStatus4H5089` parses the cloud "state"+"op" mirror: `op.ptBytes` is a list of raw
  20-byte BLE frames dispatched by `bArr[1]` exactly like the BLE notify path.
- H5089 DIY uploads over IoT use `CmdMultiSync` wrapping the multi frames plus a trailing
  `LightRgbController` DIY-mode frame.

**Net effect: the BLE byte layouts in this document are also the canonical IoT/`ptReal`
passthrough payloads.** The same is true for the H5080/H5086 controllers reused by their `iot/`
mirrors.

---

## 8. Quick-reference diagrams

```
Single control write (turn on):
  [33][01][01 00 … 00][BCC]      type=0x33 write, opcode=0x01 switch, payload[0]=01

Single read (query state):
  [AA][01][00 … 00][BCC]         type=0xAA read, opcode=0x01

Single write ACK (device→app):
  [33][01][00 …][BCC]            byte[2]==0 ⇒ success

Plug relay value byte (high nibble = outlet mask, low nibble = states):
  outlet0 ON=0x11 OFF=0x10 | outlet1 ON=0x22 OFF=0x20 | outlet2 ON=0x44 OFF=0x40 | all ON=0xFF OFF=0xF0

Multi write (A1):
  [A1][CT][00][N …][BCC]         start (count=N)
  [A1][CT][01][chunk(16B)][BCC]  data #1 …
  [A1][CT][FF][…][BCC]           end
  ← [A1][CT][00 ⇒ ok …][BCC]     write ack (byte[2]==0)

Notify (device→app):
  [EE][comType][payload(17)][BCC]

V1 session handshake (encrypted w/ K = LibTools.c()):
  → E7 01 …   ← E7 01 <16B sessionKey>   → E7 02 …   ← E7 02   (ready)

Broadcast plug on/off (manufacturer AD, type 0xFF, v[0]>=2, company 88 EC):
  v[6] (raw idx p+8) = primary relay  1=ON 0=OFF ; v[7] = 2nd relay/aux

BCC (all frames): byte[last] = XOR(byte[0] … byte[last-1])
```

---

## 9. Open questions & confidence summary

### Per-section confidence

| Section | Confidence | Notes |
|---|---|---|
| Transport (GATT / frame / checksum) | **High** | confirmed, 0 corrections |
| Crypto (encryption / auth) | **High** | confirmed, 0 corrections |
| Broadcast / advertisement | **High** | 2 minor corrections applied (FunCall guard `l()>3`; `parseBleBroadVersion` framing) |
| Common light command set | **High** | confirmed |
| Plug H5080 (V1–V4) | **High** | 2 minor corrections applied (`0xB1`/`0xB2` two opcodes; H5083 `SwitchController` read-not-write at line 302) |
| Plug H5086 (energy) | **High** | confirmed, 0 corrections |
| Plug H5089 (night light) | **High** | proType override flagged below |
| RGB / RGBIC survey | **High** | survey of patterns, not every effect |
| Sensors / BBQ / appliance survey | **High** | survey; sub-device layouts delegated to obfuscated classes |

No section is low-confidence. The lower-confidence *items* (not sections) are the flagged
uncertainties below.

### Top open questions

1. **`0x8843` vs `88 EC` manufacturer ID — RESOLVED.** Real H5080 hardware broadcasts company
   IDs `0x8802`/`0x8843` (on/off = last mfr byte), confirmed by the maintainer's working
   integration (`plugs.py:503`). The app's `0xEC88` (`88 EC`) generic parser is the modern-SKU
   path; H5080 is legacy and isn't parsed through it (see §5.2). No longer open.
2. **H5089 night-light mode proType (`0x3A` vs `0x33`).** `LightRgbController` defaults to
   `0x3A` write / `0xAA` read from the mutable `BleProtocolConstants`; a per-SKU init could
   reset to `0x33`. Verify on-wire.
3. **Dual-outlet broadcast offset→outlet mapping.** `goodsType==50` inverts switch index
   polarity; confirm which of `v[6]`/`v[7]` is left vs right on hardware.
4. **Plug legacy vs live read opcodes.** `0x0D`/`0x0E` (BleConstants device hard/soft) vs
   `0x06`/`0x07` (generic base2light) — both exist; which is honored is firmware-dependent.
5. **H5083/H5085 "newdetail" dynamic opcodes `H()/D()/J0()/j1()`** are server-driven per-SKU
   and cannot be pinned from static constants.
6. **H5086 raw kWh scaling.** Chart bulk-history energy (`entry[1..2]`) and
   `TimeMonitorInfo.electUse` are stored raw; the `/10000` kWh scale is applied downstream, not
   confirmed in the BLE parse. `DeviceBasicInfo` payload[15] semantics unknown.
7. **V2 session-key request payload (`ivKey`)** body was not fully traced (decompiler skipped);
   treat as a client nonce/IV blob. Response carving (8+5+6) and device-key derivation are
   confirmed.
8. **Scene/DIY effect blobs** (RGBIC §6.5) are opaque per-scene byte arrays — the container
   framing is captured; the internal effect-byte grammar is data, not decoded.
9. **Sensor-gateway sub-device byte layouts** (H5042/H5043) are delegated to obfuscated
   `Event4*.a(byte[])` classes — not fully resolved.
10. **A6 8-byte verify/time block** `[6..13]` (millis + 2 random bytes) device-side validation
    semantics are not visible from the app.

---

## 10. Source sections (supplementary detail)

This master doc was synthesized from ten per-dimension extractions in `re_apk/spec_sections/`.
Each contains more byte-level detail, additional source `file:line` citations, and per-item
notes than fit here:

| File | Covers |
|---|---|
| `transport.md` | GATT, lifecycle, MTU, frame/checksum, multi-packet internals |
| `crypto.md` | V1/V2 session handshake, `LibTools` key derivation, primitives |
| `broadcast.md` | scan pipeline, all advert/state parsers |
| `common-light.md` | every `base2light` controller |
| `plug-h5080.md` | H5080 V1–V4 controllers + frame builders |
| `plug-h5086.md` | H5086 energy/chart channels |
| `plug-h5089.md` | H5089 night-light sub-protocol |
| `rgbic.md` | RGB/RGBIC sub-modes, scene/DIY/music |
| `sensors.md` | TH / BBQ / humidifier / ice-maker / gateways |
| `iot-map.md` | BLE↔cloud `ptReal` passthrough (expands §7; not auto-merged — read directly) |

Decompiled source root for all citations: `re_apk/decompiled/base/sources/`. App version 7.5.20.
