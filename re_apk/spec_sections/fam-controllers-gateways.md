# Family: Controllers, Gateways & Channel devices (`fam-controllers-gateways`)

Scope: the **unified channel/messaging layer** (`com.govee.ctlchannel`), the BLE-WiFi
**sensor gateways** that enumerate and relay sub-devices (`h5151`, `h5042`, `h5043` —
the last also covers H5044/R5044), and the **Controller** (rootId 1192) / **Gateway**
(rootId 1193) catalog SKUs.

All byte values read directly from frame/mode builders. jadx prints signed decimals;
hex given via `(v & 0xFF)` (`-86→0xAA`, `-93→0xA3`, `-94→0xA2`, `-84→0xAC`, `-85→0xAB`,
`-18→0xEE`, `-17→0xEF`, `-2→0xFE`, `-1→0xFF`).

---

## 0. SKU coverage & BLE-controllability

| SKU | goodsType | Category | Module in APK | BLE-controllable? | Notes |
|---|---|---|---|---|---|
| H5040 | 0 | Gateway | — | No | Wi-Fi only gateway (no BLE module) |
| H5041 | 0 | Gateway (disc.) | — | No | Wi-Fi only |
| H5042 | 198 | Gateway (disc.) | `com.govee.h5042` | **Yes** | hosts H5109 TH sub-device; svc 1910/char 2b11 |
| H5043 | 158 | Gateway | `com.govee.h5043` | **Yes** | hosts H5058/H5107/H5059/H5830/H5310; svc 1910/2b11 |
| H5044 / R5044 | 291 | Gateway | `com.govee.h5043` (shared) | **Yes** | leak gateway path (`H5044LeakageParse`) |
| H5151 | 65 | Gateway | `com.govee.h5151` | **Yes** | Telink `…4857` service; hosts H5112/H5044-bound sub-devices |
| H5080/82/83/85 | 43/50/43/43 | Controller | `com.govee.h5080` | **Yes** | relay plugs — **documented in the Smart-plugs section**, not here |
| H5086 | 195 | Controller | `com.govee.h5086` | **Yes** | energy plug — **plugs section** |
| H5089 | 307 | Controller | `h5080.adjust.h5089` | **Yes** | night-light plug — **plugs section** |
| H5160 | 90 | Controller | `com.govee.h5080` | **Yes** | outdoor plug — **plugs section** |
| H5122 | 131 | Controller | — (none) | **No — broadcast-only** | Button Sensor: app *receives* press broadcasts, sends nothing |
| H5125 | 144 | Controller | — (none) | **No — broadcast-only** | Button Remote |
| H5126 | 145 | Controller | — (none) | **No — broadcast-only** | Button Switch |
| H5901 | 363 | Controller | — (none in this split) | Unknown | Smart Water Timer — likely Wi-Fi/cloud; flag uncertain |

The relay plugs are the bulk of the "Controller" category but their relay/energy frame
layouts live in the dedicated plugs sections. **This section is the channel layer +
gateways.** The three button SKUs have **no BLE control class** anywhere in the decompiled
tree (only a linkage reference in `base2home/reform4dbgw/.../ThDbgwLinkageSupport`) — they
are broadcast-only scene triggers.

---

## 1. Unified channel layer (`com.govee.ctlchannel`)

Newer gateways/controllers route every command through `GMessage` objects that can be
sent over **BLE** (`BleClientProxy`) and/or **IoT/cloud** (`IotProxy`) selected by
`IReq.SendType.{BLE,IOT,BOTH}` (`GMessageBuilder.p`). The wire bytes are identical on both
paths, so the BLE frame layouts below double as the cloud `pt`-passthrough payloads.

### 1.1 Single-frame builders (`GMessageBuilder.Companion`)

| Builder | Bytes | Source |
|---|---|---|
| `buildSingleReadAa(cmd, parser, optByte?)` | `BleUtil.generate20Bytes(0xAA, cmd, [optByte?])` → `[0xAA][cmd][opt?][…][BCC@19]` | `GMessageBuilder.java:106` |
| `buildSingleWrite33(cmd, payload, cb?)` | `BleUtil.generate20Bytes(0x33, cmd, payload)` → `[0x33][cmd][payload…][BCC@19]` | `GMessageBuilder.java:115` |

`generate20Bytes(type, cmd, payload)` == `BleUtils.p(type, cmd, payload)`: a 20-byte buffer
`[0]=type [1]=cmd [2..]=payload [19]=BCC(XOR 0..18)` (`BleUtils.java:1000`). Default write-OK
check: reply `frame[2] == 0` (`GMessageBuilder.u`, line 130).

### 1.2 Controller wrapper (`Gmsg4Controller`, `Gmsg4NewthController`)

Wraps a `base2light…AbsController` / `base2newth.IController`:

- `proType` (frame[0]) from `controller.getProType()`: **0x33 write**, **0xAA read**,
  **0x3A (58) "multiSync"** write, **0xA6/0xA3/0xA2** for multi controllers
  (`AbsControllerNoEvent4Single.getProType` line 135: `isWrite ? (multiSync? 0x3A : 0x33) : 0xAA`).
- `commandType` (frame[1]) from `controller.getCommandType()`.
- `checkSameHeadBytesBle()` = `[proType, commandType]` — reply matched on first two bytes
  (`Gmsg4Controller.java:341`).
- `getIotReqType()` maps proType→cloud verb: `0x33→"ptReal"`, `0x3A→"multiSync"`,
  `0xAA / AbsMultipleController → "ptReal"` (`Gmsg4Controller.java:357`).

### 1.3 Multi-packet **READ** reassembly — header `0xAC` (and `0xAB` variant)

`GMessageMultiRead` / `MultipleReadHelper`. Request frame: `BleUtils.p(0xAC, cmd, dataBytes)`.
A `Gmsg4Controller` auto-attaches a helper when its first value byte is `0xAC`/`0xAB`
(`Gmsg4Controller.a0`). Reply packet structure (`MultipleReadHelper.d/e/f`):

| Packet | byte[0] | byte[1] | byte[2..] | Payload |
|---|---|---|---|---|
| **First** | `0xAC` | `0x00` | `[2..3]`=total pkg count (BE, `H()`), `[4]`=last-pkg len (`K()`), `[5]`=cmd, `[6+]`=subCmd match | from `[7]`, 12 bytes |
| **Middle** | `0xAC` | order idx (1..) | — | `[2..18]`, 17 bytes |
| **Last** | `0xAC` | `0xFF` | — | `[2..2+lastLen]` |

`0xAB` variant (`MultipleReadHelper0xab`) additionally matches `byte[6]` (a 2nd sub-cmd
selector) and consumes one extra byte on the first packet (`iK-1` payload). Reassembled
valid bytes via `BleUtils.i(list)`. `isSameController()` validates `byte[0]==header` and the
running order index, with `byte[1]==0xFF` flagging the final packet.

### 1.4 Multi-packet **WRITE** — `MultipleControllerCommV1.makeSendBytesV1/V2`

Used by `AbsMultipleController*` and the gateway sub-device config controllers. proType
passed in (gateways use **0xA3 = MULTIPLE_WRITE**). `makeSendBytesV2(proType, commBytes[], value)`
(line 760):

| Packet | byte[0] | byte[1] | byte[2] | byte[3] | byte[4..] | rest |
|---|---|---|---|---|---|---|
| **First/header** | proType | `0x00` | `0x01` | total pkg count | `commBytes…` then value | value continues; BCC@19 |
| **Middle** | proType | idx (1..) | `[2..18]` = 17 value bytes | | | BCC@19 |
| **Last** | proType | `0xFF` | `[2..]` = remaining value bytes | | | BCC@19 |

`makeSendBytesV1(proType, commByte, value)` = `makeSendBytesV2(proType, [commByte], value)`.
V2 (`AbsControllerNoEvent4MultiImpV2`) puts **two** command bytes at `[4],[5]`.

> Two distinct multipacket framings coexist: the **ctlchannel read** uses `0xAC/0xAB`
> (§1.3); the older **base2light** multi path uses `0xA2 (read) / 0xA3 (write)` +
> `makeSendBytesV*` (§1.4). Gateways use the latter for sub-device list config.

---

## 2. H5151 — Bluetooth-WiFi Gateway (goodsType 65)

GATT: Telink **`494e5445-4c4c-495f-524f-434b535f4857`** service (HW=4857); write+notify
char = **`494e5445-4c4c-495f-524f-434b535f2011`** (`ThBleComm.f93990p`, `BleComm.java`).
Multi-comm uses the same pair.

### 2.1 Command-type constants (`BleConstants.java`)

| Const | Val | Meaning |
|---|---|---|
| SINGLE_WRITE | `0x33` | write proType |
| SINGLE_READ | `0xAA` | read proType |
| MULTIPLE_READ | `0xA2` | multi-read proType |
| MULTIPLE_WRITE | `0xA3` | multi-write proType |
| NOTIFY | `0xEE` | notify proType |
| MULTI_SUB_DEVICE_UUID | `4` | sub-cmd: sub-device address list |
| MULTI_SUB_DEVICE_TH | `5` | sub-cmd: sub-device TH range list |
| SINGLE_DEVICE_ID | `1` / SINGLE_BATTERY `8` / HW `11` / SW `12` / WIFI_MAC `15` / SYNC_TIME `16` | misc reads |
| SINGLE_READ_SECRET_KEY | `0xB1` / SINGLE_CHECK_SECRET_KEY `0xB2` | binding token (see crypto §) |
| SINGLE_INDICATOR | `33 (0x21)` | indicator/light switch |

### 2.2 Sub-device enumeration / config (multi-write, proType `0xA3`)

Built via `AbsControllerNoEvent4MultiImp(commandType, payload, 0xA3, …)`:

| Controller | sub-cmd (byte[4]) | Payload layout | Source |
|---|---|---|---|
| `Controller4SubDeviceUuids` | `4` | `[count][6-byte BLE addr]×count` (`BleUtil.address2Bytes`) | `Controller4SubDeviceUuids.java` |
| `Controller4SubDeviceTemHumRange` | `5` | `[count][TemHum-range bytes]×count` (`Ext4TemHum.toTemHumRangeBytes`) | `Controller4SubDeviceTemHumRange.java` |
| `Controller4SubDeviceThRange4Common` | V2 `{0xFE, 5}` | `[count][th-range+device bytes]×count` (`toThRangeBytes4Common`) | `Controller4SubDeviceThRange4Common.java` |

These tell the gateway which sub-devices to poll and their alarm ranges; the gateway then
forwards each sub-device's readings.

### 2.3 Single controllers

| Controller | cmd | Notes |
|---|---|---|
| `Controller4LightSwitch` | `0x21` | `[on/off]` indicator LED; `b(z)` → payload `[z?1:0]` |
| `HeartControllerV2` | `0x01` | heartbeat; parses 10-byte reply (`EventHeartV2`) |
| `SnController` | `7` (or ctor arg) | reads 8-byte MAC → `toAddressBytes` |
| `Controller4HardVersion`/`…SoftVersion`/`…WifiMac`/`…SyncTime`/`…DataReset` | `11/12/15/16/17` | std reads/writes |
| `Request4BindH5112` + `BindH5112ResultNotifyParse` | — | binds an H5112 sub-device; result via notify (`Event4H5112BindResult`) |

Pairing entry: `BleBroadcastProcessor` consumes the gateway's BLE advert (`goodsType`+
`protocol` matched by `Support.supportPact`) and opens the connect dialog.

---

## 3. H5042 — Wi-Fi Smart Gateway 1s (goodsType 198) → hosts H5109 TH sensor

GATT: **standard** `…1910` service / `…2B11` write+notify char (`BleComm.java`,
`BleMultiComm.java`). Frame = `BleUtils.p(proType, cmd, ext)` (`[proType][cmd][ext…][BCC]`),
proType `0x33` write / `0xAA` read (`kt.ble.AbsController` → `getNextCommBytes`).
Sub-device deviceType code `1` = **H5109** (`Support.l`, `Support.o`).

### 3.1 Write/read command types (`com/govee/h5042/ble/controller/*`)

| cmd | Controller | Dir | Payload / meaning |
|---|---|---|---|
| `0x01` | `Controller4Uuid` (read) / `Controller4SubDevicePairInfo4Bind` (write) | R / W | gateway MAC; pairing info, single-send-multi-back |
| `0x03` | `Controller4SubDeviceNum` | R | sub-device count |
| `0x04` | `Controller4SubDeviceInfo4Bind` | R(multi) | enumerate bound sub-devices |
| `0x05` | `Controller4StudyMode` | W | enter pairing/learn mode |
| `0x06` | `Controller4BindSubDeviceSuc` | W | confirm bind success |
| `0x08` | `Controller4TemWarning` / `Controller4SwitchLongLife` | W | temp-alarm range / long-life mode (sub-cmd multiplexed) |
| `0x10` (16) | `Controller4SyncTime` | W | sync clock |
| `0x11` (17) | `Controller4DeleteSubDevice` | W | `[subIndex]` or `[0xFF]`=delete all (`Companion.a/b`) |
| `0x14` (20) | `Controller4DeleteSubDevData` | W | clear sub-device history |
| `0x21` (33) | `Controller4LightSwitch` | W | `[on/off]` gateway indicator |
| `0xB1/0xB2` | `Controller4Secret` | R/W | binding-token (secret-code) handshake |

`Controller4SyncSubDevice`: multi-write, sub-cmd `1` (proType 0xA3) — pushes the sub-device
roster (`AbsControllerNoEvent4MultiImp(1, bytes, 0,0,12)`).

### 3.2 Notify / forwarded sub-device frames

Dispatch (`AbsNotify.parse`): frame[0] must be `0xEE`; strip → match by frame[1]=cmd
(`AbsNotifyParse.c()`); each parser then sees the **17-byte payload = frame[2..18]**
(`AbsNotifyParse.d` copies `value[1..17]`).

| frame[1] cmd | Parser | Event / parse |
|---|---|---|
| `0x31` (49) | `SubDeviceAddNotifyParse` | `Event4AddSubDevice` → `ParseUtils.b` (enumeration, §3.3) |
| `0x32` (50) | `SubDeviceIdentifyNotifyParse` | `Event4IdentitySubDevice` |
| `0x34` (52) | `SubDeviceInfoNotifyParse` | `Event4SubDeviceInfoUpdate` → `ParseUtils4H5109.a` (§3.4) |
| `0x35` (53) | `SubDeviceOpResultParse` | `Event4SubOpResult`: `[0]`=subIndex/sno, `[1]`==0 success, `[2]`=opType |
| `0x11` (17) | `WifiNotifyParse` | `[0]`==0 → Wi-Fi connected |

### 3.3 Add-sub enumeration packet (`ParseUtils.b`, 17-byte payload)

`payload[0]` hex → binary: **bit7 (MSB) = "is-address packet"**, **bits6..0 = subIndex/sno**.

- If bit7 == 1 → **address packet**: `payload[1..16]` (16 bytes) = device address (`BleUtils.t0`).
- Else → **info packet**: `K(payload[1])` = deviceType code → SKU (`Support.l`);
  `payload[2]` nibbles `{hi.lo}` = soft version, `payload[3]` nibbles = hard version.

A sub-device record completes once both packets seen (`hasNotifyAllSubInfo`), then a
`SubDevice4H5109` is emitted and the accumulator cleared.

### 3.4 H5109 TH info record (`ParseUtils4H5109.a`, 17-byte payload)

| Off | Field | Decode |
|---|---|---|
| `[0]` | subIndex | unsigned |
| `[1]` | deviceType | unsigned (1=H5109) |
| `[2]` | online status | unsigned |
| `[3]` | battery % | unsigned |
| `[4]` | soft version | nibbles `hi.lo` (`h0(b,{4,4})`) |
| `[5]` | hard version | nibbles `hi.lo` |
| `[6]` | signal (RSSI) | signed byte |
| `[7..10]` | update time | signed int **big-endian** seconds ×1000 |
| `[11..12]` | temperature | `getSignedIntV2(LE)` |
| `[13..14]` | temp calibration | `getSignedIntV2(LE)` |
| `[15]` | power-save mode | `==1` |
| `[16]` | flags (reversed bits) | bit0=temCaliEnable (0=on), bit1=longLifeEnable (0=on) |

`ParseUtils.c` / `…4H5109.b` parse a temp-warning record: `[0]`=sno, `[1]`==0 gate,
`[2]`=enable flag, `[3..4]`=low limit (BE signed), `[5..6]`=high limit (BE signed).

---

## 4. H5043 — Wi-Fi Smart Gateway 2 (gt 158) + H5044/R5044 (gt 291)

GATT: standard `…1910` / `…2B11`. Hosts a richer sub-device set. Notify dispatch identical
to §3.2 (`[0xEE][cmd][17 payload]`). The module branches on gateway goodsType: `158` →
`H5043LeakageParse`, `291` → `H5044LeakageParse` (`Parser.c`).

### 4.1 Sub-device type codes → SKU (`H5043Cons` static + `Support.s`)

| code (`K(byte)`) | SKU | Kind |
|---|---|---|
| `12`, `13` | **H5058** | water-leak sensor |
| `0xF1` (241, `ThSubCons.a()` = `K(-15)`) | **H5107** | TH sensor |
| `2` | **H5059** | leak |
| `4` | **H5830** | leak/sensor |
| `8` | **H5310** | (TH/clock) |
| `3`,`5`,`6`,`7` | reserved | (`h()/l()/m()/i()`) |

### 4.2 Command types (`com/govee/h5043/ble/controller/*`)

| cmd | Controller(s) |
|---|---|
| `0x03` | `Controller4SubDeviceNum` |
| `0x04` | `Controller4H5107Info` (read sub TH) |
| `0x05` | `Controller4StudyMode` |
| `0x08` | `Controller4FindDevice`, `Controller4SetVolume`, `Controller4TemWarning`, `Controller4HumWarning`, `Controller4CheckSignal` (sub-cmd multiplexed) |
| `0x11` (17) | `Controller4DeleteSubDevice` |
| `0x15` (21) | `Controller4BuzzerGear` |
| `0x21` (33) | `Controller4LightSwitch` |
| — | `Controller4SyncSubDevice` (multi-write), `…WriteTemCali/…WriteHumCali`, `…SwitchLongLife`, `…LowBatSwitch`, `…SetVolume4H5058New`, `…FactoryFlag`, Lora HW/SW/Spec reads |

### 4.3 Notify parsers (`BleNotifyComm.g`) & frame parse (`Parser.a`)

`WifiNotifyParse`, `AddSubDeviceNotifyParse`, `IdentifySubDeviceNotifyParse`,
`SubDeviceStatusUpdateNotifyParse`, `SubDevice4ThOpResultParse`, `BindH5112ResultNotifyParse`.

`Parser.a(frame, sno)` (`Parser.java`): requires `frame[0]==0xEE`; payload=`frame[2..18]`:

- `frame[1]==0x34` (52): sub-device **TH info** → `Info4ThWithCali.a(payload)` (only when
  `K(payload[0])==sno` and `K(payload[1])` maps to `H5107`). Emits
  `[type, online, battery, tem, hum, updateTimeSec, temCali, humCali, powerSave, signal]`.
- `frame[1]==0x33` (51): **op result** → `K(payload[0])==sno && payload[1]==0` ⇒ success.

### 4.4 Cloud passthrough mirror (`Parser.b/c`)

The cloud path delivers `ResultPt.bytes()` lists where each element is a **verbatim 20-byte
BLE frame**. `Parser.b` scans for `[0xAA][0x04]…` (read-reply of H5107 TH) and reuses
`Info4ThWithCali.a`. `Parser.c` runs leak-parse per gateway goodsType. So gateway-forwarded
sub-device frames are byte-identical over BLE and IoT.

---

## 5. Confidence & open questions

- **High confidence:** ctlchannel single/multi frame builders (§1), H5042/H5043 command-type
  maps and notify dispatch, H5109 TH record layout (§3.4), sub-device type-code→SKU maps.
- **Medium:** exact bit semantics of the `payload[16]` flags byte (reversed-bit decode read
  from source but not hardware-verified); `Info4ThWithCali` internal offsets (parser referenced
  but its byte map not expanded here — same shape as H5109 minus humidity additions).
- **Open:**
  - H5901 Smart Water Timer: no module in this APK split; control path (BLE vs Wi-Fi) unknown.
  - Buttons H5122/H5125/H5126: confirmed **no BLE control class**; their advert/broadcast
    button-press payload format is not defined in these modules (belongs to a broadcast/sensor
    section).
