# Transport: BLE GATT, Frame Format & Checksum (`section_id: transport`)

This section is the canonical reference for how the Govee Home Android app talks to
devices over BLE GATT: the service/characteristic/CCCD UUIDs, how a device's chip
family is selected, the connection lifecycle, MTU handling, the 20-byte single-frame
format and its BCC checksum, the multi-packet (A1/A2/A6) protocols, write semantics,
and notify dispatch. Every claim is backed by a `file:method` citation. Byte values
in jadx are printed as signed decimals; this doc gives hex (`v & 0xFF`).

---

## 1. GATT UUIDs

### 1.1 Modern unified profile (current Govee chips, incl. plugs / base2light)

| Role | UUID | Source |
|------|------|--------|
| Primary service | `00010203-0405-0607-0809-0a0b0c0d1910` | `base2light/ble/AbsBle.java` → `BlePtRealMultiComm.f55576e`, and `AbsBle.H()` default |
| Unified write **and** notify characteristic | `00010203-0405-0607-0809-0a0b0c0d2b11` | `AbsBle.java` → `BlePtRealMultiComm.f55577f`, and `AbsBle.z()` default |
| CCCD (Client Characteristic Config Descriptor) | `00002902-0000-1000-8000-00805f9b34fb` | `com/govee/ble/comm/BleCommImp.java` → field `f99421d` |

`2b11` is a single characteristic used for both app→device writes and device→app
notifications. `AbsBle.H()` (service) and `AbsBle.z()` (characteristic) return the
instance UUIDs `f55572n`/`f55573o` if set by the subclass constructor, otherwise fall
back to the `1910`/`2b11` constants above:

```java
// AbsBle.java
public UUID H() { return f55572n != null ? f55572n : UUID.fromString("...0a0b0c0d1910"); }
public UUID z() { return f55573o != null ? f55573o : UUID.fromString("...0a0b0c0d2b11"); }
```

### 1.2 Legacy split profile (older devices, OTA path)

`com/govee/base2light/ble/ota/OtaManager.java` defines a legacy **notify** characteristic
`...0a0b0c0d1912` (`f57861i`) and `...0a0b0c0d2b12` (`f57862j`). The split scheme (per
the verified ground truth) uses write `...1911` / notify `...1912` under the same `1910`
service. The OtaManager confirms `1912` and `2b12` as the OTA notify channels.

### 1.3 Alternate chip families (confirmed ground truth, present app-wide)

These are selected per product by the product's own `Ble` subclass passing custom UUIDs
into the `AbsBle(serviceUUID, characteristicUUID)` constructor (§2):

- Telink "INTELL_ROCKS": `494e5445-4c4c-495f-524f-434b535f****` (HW=4857, range 2011..2015)
- HM-10 module: service `0000ffe0-...`, char `0000ffe1-...`
- TI: `f000ffc0/ffc1/ffc2-...`
- `0000fd00/fd01/fd02-...`
- `02f00000-...-fe00 / ff01`

### 1.4 How the chip family / UUID pair is chosen

There is **no runtime sniffing** of which chip is present. The product-specific `Ble`
subclass hard-codes its service/characteristic pair:

- Most modern products inherit the default (`1910`/`2b11`) by calling the no-arg
  `AbsBle()` constructor (`AbsBle.java` line ~140) and never overriding `H()`/`z()`.
- Legacy/alternate-chip products call `AbsBle(UUID service, UUID characteristic)`
  (line ~189) which stores `f55572n`/`f55573o`, so `H()`/`z()` return those instead.
- Per-product `BleComm`/`Ble` classes (e.g. `barelightv1/ble/BleComm.java`,
  `dreamcolorlightv1/ble/BleComm.java`, `h5151/ble/Ble.java`, etc.) each declare their
  own `getServiceUuid()`/`getCharacteristicUuid()` returning the family UUID.

`BleCommImp.sendMsg()` is UUID-agnostic — it is handed the `(serviceUUID,
characteristicUUID)` pair by the caller and enables notifications on whatever service it
is given (§3.2), so the same transport code serves all chip families.

---

## 2. Connection Lifecycle

Sequence: **scan → connectGatt → onConnectionStateChange(CONNECTED) → discoverServices →
onServicesDiscovered → (first write) enable notifications + write CCCD → write frames**.

### 2.1 Connect

`com/govee/ble/connect/BleConnectImp.java` → `connectBle(boolean auto, device, callback)`:

```java
gatt = device.connectGatt(context, auto, callback, 2 /* TRANSPORT_LE */);
```

- Transport is forced to **`TRANSPORT_LE` (2)**.
- Only one pending connection allowed (guards on `f99429b != null`).
- A connect-timeout runnable is armed for `f99428a` ms; `BleController` constructs the
  `BleConnectImp` with **60000 ms** (`BleController.java`: `new BleConnectImp(60000L)`).

`BleController` timeouts (`com/govee/ble/BleController.java`):
- `f99385p = 60000` — connect supervision (passed to `BleConnectImp`).
- `f99386q = 180000` — service-discovery overtime; `G()` posts
  `GattDiscoveringServiceOvertimeRunnable` with `postDelayed(..., 180000L)`.
- `f99387r = 15000` — default connect overtime used by `m()/n()` (`15000L`).

### 2.2 State change → discover services

`com/govee/ble/AbsBluetoothGattCallback.java` → `h(gatt, status, newState)`:
- `status==0 && newState==2 (CONNECTED)` → `gatt.discoverServices()`, posts
  `BTGattConnectEvent.Type.discoveringService`.
- `status!=0` → `operationFail`; if `status==19` (`GATT_CONN_TERMINATE_PEER_USER`)
  also fires `EventAutoDisconnect`.
- `newState==0 (DISCONNECTED)` → `BTGattConnectEvent.Type.disconnect`.

`j(gatt, status)` (`onServicesDiscovered`): `status==0` → `connectedSuc`, else
`discoverServiceFail`. The discovered-services list is logged but **not** filtered — the
service to use is supplied later by the caller.

### 2.3 Enable notifications / CCCD write (lazy, on first send)

Notifications are **not** enabled at discovery; they are enabled lazily the first time a
frame is written to a given service. `BleCommImp.sendMsg()` checks a per-service
"already enabled" list `f99422a`; on first use it calls one of two enablers:

- **`c()` (`enableServiceUUID`)** — default path. For every characteristic in the service:
  `setCharacteristicNotification(char, true)`, then for each descriptor
  `setValue(ENABLE_NOTIFICATION_VALUE)` + `writeDescriptor(...)`, with
  `SystemClock.sleep(100)` per descriptor and `sleep(300)` per characteristic.
- **`d()` (`enableServiceUUIDV2`)** — "fast connect" path. Only calls
  `setCharacteristicNotification(char, true)` for every characteristic; **skips the CCCD
  descriptor write entirely**.

Which path is taken is decided per device+service by
`ShortMemoryMgr.f107296a.c().f(deviceAddress, serviceUuid)` (a `BleBroadVersionCache`
flag): `true` → V2 fast path (`d`), `false` → standard path (`c`). Logged as
"支持蓝牙快速连接的版本" (supports fast connect) vs "不支持" (does not).

The CCCD value written is the standard `BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE`
(`{0x01,0x00}`), written to descriptor `00002902-...`.

### 2.4 Reconnect

`BleController` keeps a `ReconnectInfo` (device, callback, auto flags). On
`operationFail`/`discoverServiceFail`/`disconnect`, `R()` decides via `k()`
(`checkNeedReconnect`) whether to re-run `q()` (reconnect) or surface
`EventBleConnect.ble_connect_fail`. Foreground/background and a connect-timeout flag
(`f99392e`) gate reconnect.

---

## 3. Writing a Frame

### 3.1 Send entry point

All frames funnel through `BleController.L(UUID service, UUID characteristic, byte[] data)`:
- Verifies adapter on, `f99390c` (connected) true, gatt non-null.
- Delegates to `BleCommImp.sendMsg(gatt, service, char, data)`.
- `synchronized` — one write at a time.

Higher layers wrap `L()` with retry. `RunnableSendMsg.a()`
(`base2light/ble/comm/RunnableSendMsg.java`): calls `L()` once, then retries up to
`retryTimes` with `sleep(interval)` (min 100 ms) while still connected.
`ControllerComm.j()` chooses retry params by direction: **write** → interval 200 ms,
6 retries, 6000 ms overtime; **read** → 100 ms, 3 retries, 3000 ms overtime
(`-85`/`-84` reads get 6000 ms).

### 3.2 Actual GATT write — write **with response**

`BleCommImp.sendMsg()` ends in
`com.govee.encryp.ble.EncryptWriter.encryptWriteValue(gatt, characteristic, data)`.

`com/govee/encryp/ble/EncryptWriter.java`:
- If encryption **not** supported for the address: `characteristic.setValue(data)` then
  `gatt.writeCharacteristic(characteristic)` — i.e. **default write type
  (WRITE_TYPE_DEFAULT = write-with-response)**. No `setWriteType(WRITE_TYPE_NO_RESPONSE)`
  call appears in this path.
- If encryption supported: the manager encrypts `data` into a `List<byte[]>` of size 1
  or 2 (a single 20-byte frame may become two ciphertext fragments); each fragment is
  written via `writeCharacteristic`. Size 1 → `b()` (single write); size 2 → `a()`
  (`blockWriteSplitData`, sequential blocking writes). The plaintext protocol below is
  unchanged by encryption — encryption is a transparent transport wrapper applied at the
  characteristic boundary.

Write completion arrives at `AbsBluetoothGattCallback.g()` (`onCharacteristicWrite`),
forwarded to `IBleWriteCharacteristicResultCallback.onCharacteristicWrite(...)`.

---

## 4. Single 20-Byte Frame Format

### 4.1 Canonical layout

```
 byte:  0      1        2 .............................. 18     19
       +------+--------+-------------------------------------+------+
       | type | opcode |  payload (zero-padded, 17 bytes)    | BCC  |
       +------+--------+-------------------------------------+------+
        0x33 = write/control            payload[0..16]        XOR of
        0xAA = read/query                                     bytes[0..18]
```

- `byte[0]` **command type / proType**: `0x33` (51) = SINGLE_WRITE/control,
  `0xAA` (-86) = SINGLE_READ/query.
- `byte[1]` **opcode (commandType)**: per-feature (see BleProtocolConstants map, §7).
- `byte[2..18]` **payload**, 17 bytes, zero-padded.
- `byte[19]` **BCC** = XOR of bytes[0..18].

Total length is always exactly **20 bytes**.

### 4.2 Builder proof

`com/govee/base2light/ble/controller/AbsSingleController.java`:
```java
public byte getProType() { return isWrite() ? (byte) 51 : (byte) -86; } // 0x33 / 0xAA
public byte[] g() { return BleUtils.generate20Bytes(getProType(), getCommandType(), q()); }
```

`com/govee/base2kt/utils/BleUtils.java` → `generate20Bytes(b6, b10, payload)` →
Companion `p(type, opcode, payload)`:
```java
byte[] bArr2 = new byte[20];
bArr2[0] = type;          // proType
bArr2[1] = opcode;        // commandType
System.arraycopy(payload, 0, bArr2, 2, payload.length);  // payload at offset 2
bArr2[19] = v(bArr2, 19); // BCC
```

### 4.3 Sub-mode variant (3-field builder)

For commands carrying a sub-command byte (e.g. mode/sub-mode frames),
`generate20Bytes(type, opcode, subByte, payload)` → Companion `o()`:
```java
bArr2[0] = type; bArr2[1] = opcode; bArr2[2] = subByte;   // sub-command at offset 2
System.arraycopy(payload, 0, bArr2, 3, payload.length);   // payload at offset 3
bArr2[19] = v(bArr2, 19);
```
So `byte[2]` becomes the sub-mode selector and payload shifts to `[3..18]`. Used by
mode/scene controllers (`sub_mode_*` constants in §7).

### 4.4 BCC / XOR checksum algorithm (proven)

Three identical implementations exist; all compute XOR of bytes `[0..length-1]` and the
caller stores it at `byte[19]` with `length = 19`:

```java
// BleUtils.Companion.v(packet, i6)   AND   BleUtil.getBCC(packet, length)
//                                     AND   MultiPackageManager.b(arr, i6)
byte b6 = packet[0];
for (int i7 = 1; i7 < length; i7++) {
    b6 = (byte) (b6 ^ packet[i7]);
}
return b6;
```
With `length = 19`, `byte[19] = XOR(byte[0] … byte[18])`. (Note: a separate
`getByteSum`/`z()` exists computing an additive sum, used elsewhere — **not** for the
20-byte frame BCC. The frame uses XOR.)

### 4.5 Receive-side single-frame validation

`AbsSingleController.m(value)`:
- **Read replies** (`!isWrite`): copies `value[2..]` (up to 17 bytes) →
  `parseValidBytes()`.
- **Write acks**: `t(value)` = `value[2] == 0` (success byte at offset 2), then payload
  `value[3..]` (16 bytes) → `s()`/`r()`.

`AbsController.isSameController(proType, commandType)` =
`getProType()==proType && getCommandType()==commandType` — i.e. a notification is matched
to a pending controller by **bytes[0] and bytes[1]** (`AbsController.java`).

---

## 5. Multi-Packet Protocols

The app has several multi-packet schemes. The base A1/A2 scheme below is the canonical
one in `MultiPackageManager` / `BleUtil`; A3/A4/A6 are richer variants in
`MultipleControllerCommV1`.

### 5.1 Command-type bytes (frame `byte[0]`)

| Name | Hex | Dec | Source |
|------|-----|-----|--------|
| MULTIPLE_WRITE (A1) | `0xA1` | -95 | `MultiPackageManager.f99553e`; `BleProtocolConstants.MULTIPLE_WRITE` |
| MULTIPLE_READ (A2) | `0xA2` | -94 | `MultiPackageManager.f99554f`; `BleProtocolConstants.MULTIPLE_READ` |
| MULTIPLE_WRITE_V1 (A3) | `0xA3` | -93 | `BleProtocolConstants.MULTIPLE_WRITE_V1` / `MULTI_WRITE` |
| MULTIPLE_WRITE_V2 (A4) | `0xA4` | -92 | `BleProtocolConstants.MULTIPLE_WRITE_V2` |
| MTU_MULTIPLE_WRITE (A6) | `0xA6` | -90 | `BleProtocolConstants.MTU_MULTIPLE_WRITE` |
| MULTI_READ_AB | `0xAB` | -85 | `BleProtocolConstants.MULTI_READ_AB` |
| MULTI_READ_AC | `0xAC` | -84 | `BleProtocolConstants.MULTI_READ_AC` |

### 5.2 A1 multi-write (20-byte packets, 16-byte chunks)

Two equivalent encoders: `BleUtil.getMultiWriteString()` (base64 list, plaintext) and
`MultiPackageManager.j()` (live, with sleeps). Per-chunk builder `BleUtil.a()` /
`MultiPackageManager.c()`:

```
 A1 data packet (BleUtil.a(type, position, chunk16)):
 byte[0]=0xA1  byte[1]=comType  byte[2]=position(1..N)  byte[3..18]=chunk(16B)  byte[19]=BCC
```

Full transfer (`MultiPackageManager.j(service, char, comType, data)`):

| Phase | byte0 | byte1 | byte2 | byte3 | byte[3..18] | Notes |
|-------|-------|-------|-------|-------|-------------|-------|
| **Start** | `0xA1` | comType | `0x00` | packetCount | — | count = ceil(len/16) |
| **Data×N** | `0xA1` | comType | index `1..N` | — | 16-byte chunk | last chunk zero-padded |
| **End** | `0xA1` | comType | `0xFF` | — | — | terminator |

- Payload chunked into **16-byte** pieces (`length % 16`, `length / 16`).
- 300 ms `Thread.sleep` between every packet.
- Max total payload **< 4080 bytes** (`bArr.length >= 4080` rejected).
- `f99558a` cancel flag aborts mid-stream.
- All bytes validated with BCC at `[19]`.

### 5.3 A2 multi-read request

`MultiPackageManager.i(service, char, comType, payload)`:
```
 byte[0]=0xA2  byte[1]=comType  byte[2]=0x00  byte[3..]=payload  byte[19]=BCC
```

### 5.4 Reassembly / response parsing — `MultiPackageManager.g(byte[])`

Dispatch on `byte[0]`:

- **`0xA1` (write ack)** → `MultiWriteResponse{ comType = byte[1], result = (byte[2]==0) }`,
  posted on EventBus. **Success byte = `byte[2]==0`.**
- **`0xA2` (read reply)**, dispatch on position `byte[2]`:
  - `0x00` **header**: start new `MultiReadResponse{ comType=byte[1], amount=byte[3],
    datas=[] }`.
  - `0xFF` **end**: `result = (amount == datas.size())`; post and clear.
  - else **middle**: only accepted if `byte[2] == datas.size()+1` (strict ordering);
    copy `byte[3..18]` (16 bytes) into `datas`.
  - A `comType` mismatch vs the in-flight response aborts with `result=false`.

`MultiReadResponse` fields: `comType`, `amount` (expected packet count), `datas`
(`List<byte[16]>`), `result`. `MultiWriteResponse`: `comType`, `result`.

### 5.5 A3/A4 variants (`MultipleControllerCommV1`, 20-byte packets)

`makeSendBytesV0/V1/V2` build 20-byte packet lists; `proType = controller.getProType()`
(0xA3/0xA4 family):

- **V0** (`makeSendBytesV0`): header `[0]=proType,[1]=0,[2]=0,[3]=packs+2,[4]=commByte`;
  middle packets `[1]=index`, data at `[2..18]` (17 bytes); end `[1]=0xFF`.
- **V2** (`makeSendBytesV2`, used by V1/V3): header `[0]=proType,[1]=0,[2]=1,[3]=pktCount,
  [4..]=commBytes`, data fills from `[4+len(commBytes)]`; continuation packets `[1]=index`
  carry 17-byte chunks; end packet `[1]=0xFF`. All BCC at `[19]`.
- `AbsMultipleControllerV2` sends `commBytes = {commandType, p()}` (opcode + sub-byte).

### 5.6 A6 MTU multi-write (`makeSendBytesMtu0xA6`, large packets)

For MTU-negotiated bulk transfer (scenes/DIY/graffiti). `mtuSize` ∈ [20, 500].
Each "big package" is a list of frames:

- **Header** `[0]=0xA6,[1]=0,[2]=0,[3]=1,[16]=commandType,[17..]=data`. After assembly the
  header is patched: `[4]=bigPackCount, [5]=curBig+1, [6..13]=8-byte verify/time block
  (millis via getSignedBytesFor6 + 2 random bytes), [14..15]=small-packet-count(low,high)`.
- **Middle** `[0]=0xA6,[1..2]=index(low,high),[3..]=data`.
- **End** `[0]=0xA6,[1]=0xFF,[2]=0xFF,[3..]=data`, BCC at last byte.

`makeSendBytesMtu` (proType-generic V1 MTU): header
`[0]=proType,[1]=0,[2]=0,[3]=1,[4..5]=count(low,high),[6]=commandType,[7..]=data`;
end `[0]=proType,[1]=0xFF,[2]=0xFF`.

Sender `MultipleControllerCommV1.R()`: single-thread executor walks the packet queue,
`Q()` writes each via `BleController.L()` with up to 3 retries (`sleep(i*100+300)`), then
`sleep(f57003a)` (default 300 ms, overridable per controller) between packets.

---

## 6. MTU

- Normal control frames are fixed **20 bytes**; no MTU negotiation is required for them.
- `BleController.J(int mtu)` → `gatt.requestMtu(mtu)` (returns false if no gatt).
- OTA requests **512**: `base2light/ble/ota/v3/Ota4FrkSupportABArea.java` →
  `iOtherOtaOp.requestMtu(512)`.
- Usable payload after MTU change is `mtu - 3` (ATT header) — `OtaManagerV1.onMtuChanged`
  sets `f57931e = mtu - 3`. If MTU negotiation fails, OTA falls back to `mtuChange(20)`.
- The A6/V1 MTU multi encoders accept `mtuSize` in `[20, 500]` and compute per-frame
  data capacity as `mtuSize - {4,8,16,18}` depending on packet role.
- BLE 5 / 2M PHY support is probed in `BleController.P()` via `isLe2MPhySupported()`
  (used to gate faster OTA), but does not change the control-frame format.

---

## 7. Opcode Constant Map (`BleProtocolConstants.java`)

`com/govee/base2light/ble/controller/BleProtocolConstants.java`. These are `byte[1]`
opcodes used with proType `0x33` (write) / `0xAA` (read), plus the multi/notify
type bytes. Hex shown via `&0xFF`. (Feature semantics belong to other sections; listed
here for transport completeness.)

| Constant | Hex | Dec | Role |
|----------|-----|-----|------|
| SINGLE_WRITE / SINGLE_LIGHT_SWITCH | `0x33` / `0x30` | 51 / 48 | proType write byte / light-switch opcode |
| SINGLE_READ | `0xAA` | -86 | proType read byte |
| SINGLE_MAIN_SWITCH / SINGLE_SWITCH | `0x01` | 1 | main on/off opcode |
| SINGLE_BRIGHTNESS | `0x04` | 4 | brightness |
| SINGLE_MODE | `0x05` | 5 | mode select |
| SINGLE_HEART / SINGLE_HEART_BEAT | `0x01` / `0x00` | 1 / 0 | heartbeat |
| SINGLE_DEVICE_INFO | `0x07` | 7 | device info |
| SINGLE_SOFT_VERSION | `0x06` | 6 | sw version |
| SINGLE_SYNC_TIME | `0x09` | 9 | time sync |
| SINGLE_WIFI_MAC | `0x14` | 20 | wifi mac |
| SINGLE_READ_SECRET_KEY | `0xB1` | -79 | encryption handshake: read key |
| SINGLE_CHECK_SECRET_KEY | `0xB2` | -78 | encryption handshake: check key |
| SINGLE_PACT | `0xEF` | -17 | pact/protocol marker |
| SINGLE_OTA_PREPARE | `0xEE` | -18 | OTA prepare |
| NOTIFY | `0xEE` | -18 | notify frame leading byte |
| NOTIFY_RECOGNITION | `0xED` | -19 | recognition notify |
| MULTIPLE_WRITE (A1) | `0xA1` | -95 | multi write |
| MULTIPLE_READ (A2) | `0xA2` | -94 | multi read |
| MULTIPLE_WRITE_V1 (A3) | `0xA3` | -93 | multi write v1 |
| MULTIPLE_WRITE_V2 (A4) | `0xA4` | -92 | multi write v2 |
| MTU_MULTIPLE_WRITE (A6) | `0xA6` | -90 | MTU bulk write |
| MULTI_READ_AB | `0xAB` | -85 | multi read variant |
| MULTI_READ_AC | `0xAC` | -84 | multi read variant |
| sub_mode_color / music / scenes / operate | `0x15`/`0x13`/`0x04`/`0x20` | 21/19/4/32 | mode sub-selectors (frame `byte[2]` in 3-field builder) |

---

## 8. Notify Dispatch (device→app)

1. `EncryptionBluetoothGattCallback.onCharacteristicChanged(gatt, char)`
   (`com/govee/encryp/ble/EncryptionBluetoothGattCallback.java`):
   - If encryption unsupported → pass raw value to `e()`.
   - Else decrypt via `EncryptionManagerPool.getEncryptionManager(gatt).f(value)`, set the
     decrypted bytes back on the characteristic, then `e()`. (Notify frames are decrypted
     transparently before any protocol parsing.)
2. `e()` is implemented by the per-product gatt callback (e.g.
   `base2light/CommEventGattCallback.java`, `pact/newdetail/ble/GattCallbackImp.java`),
   which posts `EventCharacteristicChange(address, serviceUuid, characteristicUuid, value)`.
3. `AbsBle.W(serviceUuidStr, charUuidStr, value)` receives it and fans the bytes out to
   every active comm object whose `getServiceUuid()` matches:
   `f55561c` (single `AbsBleComm`), `f55560b` (`ComposeBleComm`), `f55562d`
   (`AbsMultipleBleComm`), `f55563e` (`AbsMultiple4PtRealBleComm`), `f55564f`
   (`INotify`), `f55571m` (`IDataComm`).
4. `AbsBleComm.parse(bytes, heartService, heartChar)`
   (`base2light/ble/comm/AbsBleComm.java`):
   - Requires `bytes.length >= 2`; reads `b6=bytes[0]`, `b10=bytes[1]`.
   - If no controller queued, or the frame matches the registered heartbeat
     service/char, routes to `e()` (heartbeat/unsolicited handler).
   - Else peeks the queued `AbsSingleController`; if
     `controller.isSameController(b6,b10)` **and** `controller.b(bytes)` validate, calls
     `controller.onResult(true, bytes)` and dequeues it (unless `b6==0xAB`, a multi-read
     that stays queued).
   - So the **(type, opcode)** pair `(bytes[0], bytes[1])` is the routing key for matching
     a notification to its outstanding request.
5. Multi-packet notifies (`0xA1`/`0xA2`) are instead handled by `MultiPackageManager.g()`
   (§5.4) which reassembles and posts `MultiWriteResponse`/`MultiReadResponse`.

---

## 9. Quick Reference — Canonical Diagrams

```
Single control write (turn on):
  [33][01][01 00 00 … 00][BCC]      type=0x33 write, opcode=0x01 main switch, payload[0]=01

Single read (query state):
  [AA][01][00 … 00][BCC]            type=0xAA read, opcode=0x01

Single write ACK (device→app):
  [33][01][00 …][BCC]               byte[2]==0 ⇒ success (AbsSingleController.t)

Multi write (A1) sequence:
  [A1][CT][00][N ……][BCC]           start: count=N
  [A1][CT][01][chunk0(16B)][BCC]     data #1
  …
  [A1][CT][N ][chunkN][BCC]          data #N
  [A1][CT][FF][……][BCC]             end
  ← [A1][CT][00 ⇒ ok …][BCC]        write ack, byte[2]==0

Multi read (A2):
  → [A2][CT][00][payload][BCC]       read request
  ← [A2][CT][00][amount …][BCC]      header (amount=byte[3])
  ← [A2][CT][01][chunk(16B)][BCC]    data, ordered byte[2]==datas.size()+1
  ← [A2][CT][FF][……][BCC]           end; ok if amount==datas.size()

BCC (all frames): byte[last] = XOR(byte[0] … byte[last-1])
```

---

## 10. Uncertain / Out of Scope (flagged)

- **Write type**: code uses `gatt.writeCharacteristic` with default value type = WITH
  RESPONSE on the plaintext path. No `WRITE_TYPE_NO_RESPONSE` was found in the control
  path (`EncryptWriter`, `BleCommImp`). OTA paths may differ (not fully traced here).
- **Encryption fragment format**: when encryption is enabled a 20-byte frame may split
  into 2 ciphertext writes (`EncryptWriter.a`). The exact cipher/handshake (B1/B2 key
  exchange, AES details) is owned by the crypto/auth section; here it is treated as a
  transparent transport wrapper.
- **Exact CCCD-skip flag semantics**: the V2 "fast connect" path keys off
  `BleBroadVersionCache.f(address, serviceUuid)`; the source of that flag (broadcast
  version cache) is not fully traced in this section.
- The A6 8-byte "verify/time block" `[6..13]` is millis(low-first via getSignedBytesFor6)
  plus 2 random bytes; its device-side validation semantics are not visible from the app.
