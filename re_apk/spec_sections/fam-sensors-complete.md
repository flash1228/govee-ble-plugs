# fam-sensors-complete — Sensors complete matrix (TH / air / leak / BBQ / probe gateways)

Section id: `fam-sensors-complete`. Source app: Govee Home Android v7.5.20 (jadx).
Covers the entire sensor fleet: thermo-hygrometers, air-quality (PM/CO₂), leak detectors,
BBQ/meat-probe thermometers, and the BLE↔Wi-Fi gateways that relay sub-sensors.

jadx prints **signed** decimals; every negative byte below is given as hex via `(v & 0xFF)`
(`-1→0xFF`, `-18→0xEE`, `-86→0xAA`, `-120→0x88`, `-20→0xEC`, `-17→0xEF`).

---

## 0. TL;DR — how sensors differ from lights/plugs

- **Most sensors are BROADCAST-ONLY for live data.** Temp/hum/PM/CO₂/battery/leak/probe-temp
  are pushed in the BLE *advertisement* (scan record), parsed without ever connecting. The
  20-byte GATT write frame from the master doc is used by sensors **only** for connected
  *settings* (units, calibration, alarm thresholds), *history sync* (the "heart" data dump),
  and *gateway sub-device management* — never for live readings.
- **No on/off / color / mode sub-commands.** Sensors do not implement the base2light command
  set. Their connected opcode space is its own small set (units/cali/alarm/heart/version).
- Two manufacturer-data shapes coexist: the **0x88EC TH family** (thermo-hygrometers, air,
  CO₂) and the **probe/BBQ family** (16-bit service-UUID `0x5055/0x5198/0x5199/0x5610/...`).
- Leak detectors (H5054/H5058/H5059/H5830) and some thermometers (H5107/H5109/H5310) are
  **sub-devices behind a gateway** (H5042/H5043/H5044/H5151); their telemetry rides either the
  gateway's own BLE broadcast (relayed) or the cloud `pt`/IoT passthrough.

---

## 1. Broadcast framing (0x88EC TH family)

Scan record is the full **62-byte** advertisement+scan-response buffer. Parsers walk the
standard BLE AD-structure list `[len][adType][data…]` (`i += len+1`) looking for an anchor,
then copy a fixed window. The Govee manufacturer flag is `0x88 0xEC`
(`BleUtil.f41010h = {(byte)-120,(byte)-20}`; `IThBroadParse.COMPANY_SELF_FLAG` identical).

Source: `base2home/pact/BleUtil.java`, `pact_thnew/.../ThBroadcastUtil.java`,
`base/.../widget/view/temHumDevice/ble/*`.

### 1.1 Anchor finders (all in `BleUtil`)

| Finder | Match pattern (AD) | Returns pos at | Used by |
|---|---|---|---|
| `checkBroadcastData` | `… FF 88 EC …` (mfr-specific, `[i+1]==FF`, `[i+2,i+3]==88 EC`) | `i+4` (right after `88 EC`) | `ThBroadcastUtil.c/g`, `H50ThBroadParseImp`, `H5072_75ThBroadParseImp` |
| `parseThBleValidBytePos` | AD len≥6, `[i+1]==FF`, `[i+2]==01`, `[i+3,i+4]==88 EC` | `i+5` | `ThBroadcastUtil.e`, `H5179ThBroadParseImp.a` (HW 1.00.02) |
| `parseThBleValidBytePosV1` | preceding `03 03 88 EC` (16-bit UUID list `0xEC88`) **then** mfr `FF 01 …` | `i+3` (after `FF 01`) | `H51`, `H5106`, `H5112`, `H5179.b`, `ThBroadcastUtil.d/f/i/j/l` |
| `parseMultiThBleValidBytePos` | same as V1 but mfr `FF 01` after `03 03 88 EC` | `i+3` | `MultiThBroadParseImp` (B5175/B5178 multi-probe) |

### 1.2 The packed temp/hum value (canonical Govee H5075 encoding)

Three consecutive bytes hold temp+humidity, big-endian, **MSB of byte0 = negative-temp sign**:

```
raw24 = ((b0 & 0x7F)<<16) | (b1<<8) | b2     # sign bit cleared
sign  = (b0 & 0x80) ? negative : positive
tempC = (raw24 / 1000) * 10   -> centi-°C  (i.e. tempC_real = out/100, negate if sign set)
hum%  = (raw24 % 1000) * 10   -> centi-%   (hum_real = out/100)
# raw24 itself = round(tempC*10000) + round(hum*10)
```

Sentinels: `b0,b1,b2 == FF FF FF` (or `b0==0x7F`) → invalid → temp=hum=0.
Range gate: temp clamped to `[-4000,10000]` centi-°C, hum to `[0,10000]` centi-%.
Implemented identically in `BleUtil.parseThValue`, `IThBroadParse.parseThValue`,
`ThBroadcastUtil.m`.

**4-byte THP variant (`BleUtil.parseThpValue`, H5106 air):** big-endian `raw32` over 4 bytes,
sign on MSB of byte0:
```
tempC_out = (raw32 / 1_000_000) * 10     # centi-°C
hum_out   = ((raw32 / 1000) % 1000) * 10 # centi-%
pm_out    = raw32 % 1000                 # 0..999 (PM2.5 µg/m³, third channel)
```
Sentinel `FF FF FF …` → all zero.

### 1.3 Scalar helpers

| Helper | Meaning |
|---|---|
| `getUnsignedByte(b)` | `b & 0xFF` |
| `getUnsignedInt(hi,lo)` | unsigned 16-bit, **big-endian** (`hi<<8 \| lo`) |
| `getSignedShort(hi,lo)` | signed 16-bit big-endian `(short)((hi<<8)\|(lo&0xFF))` |
| `getSignedInt(bytes,hFirst=true)` | unsigned N-byte big-endian accumulate (no sign-extend) |
| `getSignedIntV2(bytes,hFirst)` | 16-bit with explicit sign: `v>0x7FFF ? v-0x10000 : v` |

---

## 2. Per-SKU broadcast layouts (TH / air / CO₂)

Window = the bytes copied starting at the anchor pos. Offsets are **relative to the anchor
window** (pos+0 = first valid byte). Output arrays are listed in code order.

### 2.1 Legacy 2-byte temp/hum (`H50ThBroadParseImp`, anchor `checkBroadcastData`, 7-byte win)
SKUs: **H5051, H5052, H5053, H5071, H5074** (`supportSku` = Constant4L5 U,R,"H5053",S,W).

| off | bytes | field | scaling |
|---|---|---|---|
| 1–2 | LE | temperature | `getSignedShort(b[2],b[1])` → signed 16-bit **little-endian**, centi-°C (gate −4000..10000) |
| 3–4 | LE | humidity | `getSignedInt(b[3..4],false)` unsigned 16-bit LE, centi-% (gate 0..10000) |
| 5 | u8 | battery | `getSignedInt(b[5..5])` = % |

Invalid when `b1=b2=b3=b4=FF`. Note: this older family uses raw LE 16-bit fields, **not**
the packed 24-bit encoding. Returns `{temp, hum, battery}`.

### 2.2 Packed 24-bit (`H5072_75ThBroadParseImp`, anchor `checkBroadcastData`, 7-byte win)
SKUs: **H5072, H5075**.

| off | field | scaling |
|---|---|---|
| 1–3 | temp+hum | `parseThValue(b[1..3])` packed-24 (§1.2) |
| 4 | battery | `getUnsignedByte` % |

### 2.3 H5100-class (`H51ThBroadParseImp`, anchor V1, 7-byte win)
SKUs: **H5100,H5101,H5102,H5103,H5104,H5105,H5108,H5110,H5111,H5174,H5177,H5171,H5220**
(Constant4L5 Y,Z,a0,b0,c0,d0,h0,j0,k0,m0,n0,q0,t0).

| off | field | scaling |
|---|---|---|
| 0–1 | (pactType, unused here) | `getUnsignedInt` |
| 2 | (pactCode, unused) | u8 |
| 3–5 | temp+hum | `parseThValue` packed-24; invalid if `b3∈{FF,7F} && b4=b5=FF` |
| 6 | battery | u8 % |

Returns `{temp, hum, battery}`. (`ThBroadcastUtil.d` is the Kotlin twin, returning
`{pactType,pactCode,temp,hum,battery}`.)

### 2.4 H5179 (`H5179ThBroadParseImp`)
Single SKU **H5179**. Picks format by `versionHard`:
- **HW "1.00.02"** → `a()`, anchor `parseThBleValidBytePos`, 8-byte win:
  `temp=getSignedShort(b[4],b[3])` (BE 16-bit), `hum=getSignedShort(b[6],b[5])`, `batt=b[7]`.
  Invalid if `b3=b4=b5=b6=FF`.
- **else** → `b()`, anchor V1, 7-byte win: `parseThValue(b[3..5])` packed-24, `batt=b[6]`.

### 2.5 H5106 air-quality (`H5106ThBroadParseImp` / `ThBroadcastUtil.j`, anchor V1)
Single SKU **H5106**. Window 7 bytes; `parseThpValue(b[3..6])` (4-byte THP, §1.2) →
`{temp, hum, pm2.5}`. `pact_thnew/.../h5106/Model.O` stores `tem,hum,pm` from indices 2,3,4.
PM2.5 channel range 0..999 µg/m³.

### 2.6 H5140 CO₂ (`H5140ThBroadParseImp` / `ThBroadcastUtil.k`)
Single SKU **H5140**. Anchor = `parseBleAdvertisement` entry with key `0x0B` (AD type 11),
11-byte mfr block, `data[0]==FF`:
| off (in 11-byte block) | field | scaling |
|---|---|---|
| 2–3 | pactType | `getUnsignedInt` BE |
| 4 | pactCode | u8 |
| 5–7 | temp+hum | `parseThValue` packed-24 |
| 8–9 | CO₂ ppm | `(b8&0xFF)<<8 \| (b9&0xFF)` big-endian 16-bit, validated by `WidgetTemHumModel.isValidCo2`, else −1 |

`ThBroadcastUtil.k` additionally appends `getSignedIntV2(b8,b9,hFirst)` as a signed variant.

### 2.7 H5107 dual-channel (`H5107BroadParseImp`)
Single SKU **H5107** (also a gateway sub of H5043). Uses `BleUtils.parseScanRecord4SelfProtocols`
(self-protocol blob ≥27 B); parses **two** 10-byte channels at offsets 6 and 16. Per channel:
`b1==0xF1` gate; `b0`=index; `parseOneByte(b2,{1,7})` → flag + sno; `parseTemHumBy3Bytes(b3..5)*10`
→ temp,hum; `getSignedInt(b6..9,true)` = epoch timestamp. Result =
`{sno_a,time_a,temp_a,hum_a, sno_b,time_b,temp_b,hum_b}` (−1 where absent).

### 2.8 H5109 probe (`H5109BroadParseImp`)
Single SKU **H5109** (gateway sub of H5042). Window = `scanRecord[31..47]` (17 B, scan-response
half): `b0`=sno/index (u8); `getSignedInt(b[7..10],true)` (4-byte BE, epoch/value); 
`getSignedIntV2(b[11..12],false)` signed 16-bit LE temperature. ⚠️ exact field semantics of the
middle 32-bit not fully pinned (timestamp vs reading) — flag.

### 2.9 B5175 / B5178 multi-probe (`MultiThBroadParseImp` / `ThBroadcastUtil.h`)
SKU **B5178** (Constant4L5 p0). Anchor `parseMultiThBleValidBytePos`, 10-byte win:
`b3`=probe order/index, `parseThValue(b4..6)` temp/hum, `b7` high-bit=sign + low7=channel
(`b()` split), `getUnsignedInt(b8,b9)` trailing. Returns `{temp,hum,0,order}`.
`ThBroadcastUtil.h` richer: `{pactType,pactCode,order,temp,hum,chLow7,chSign,u16}`.

### 2.10 H5112 / R5112 (`H5112ThBroadParseImp` / `ThBroadcastUtil.i`)
SKUs **H5112, R5112** ("Thermometer R1 Pro", Constant4L5 l0,r0). Anchor V1, 9-byte win:
`parseThValue(b3..5)` temp/hum, `b6`=battery; `b8` bits[0:2]=`i5` mode/flag, bits[2:8]=`i6`.
`ThBroadcastUtil.i` is the full decoder (also splits `b7` into 2-bit fields for dual sub-channel
temp/hum, selected by `i5`: 1→ch-a, 2→ch-b).

### Broadcast SKU → parser quick map

| SKU(s) | parser | encoding |
|---|---|---|
| H5051/52/53/71/74 | H50 | LE 2-byte temp + LE 2-byte hum + batt |
| H5072/75 | H5072_75 | packed-24 + batt |
| H5100/01/02/03/04/05/08/10/11/74/77/71/220 | H51 | packed-24 + batt |
| H5179 | H5179 | BE-shorts (HW1.00.02) or packed-24 |
| H5106 | H5106 | packed-32 THP (temp/hum/**pm2.5**) |
| H5140 | H5140 | AD-11 block, packed-24 + **CO₂** BE16 |
| H5107 | H5107 | self-protocol, 2×(sno/time/temp/hum) |
| H5109 | H5109 | scan-resp window, sno/u32/temp |
| H5112/R5112 | H5112 | packed-24 + flags/dual-channel |
| B5178 | Multi | multi-probe packed-24 |

---

## 3. BBQ / meat-probe thermometers (broadcast)

Source: `pact_bbqnew/.../pact/BcDeviceInfoParseUtil.java`, `pact_bbqnew/.../ble/BbqBleProtocol.java`,
`BleUtil.parseBbqBleValidBytePosV1/V2`.

Probe devices advertise a 16-bit service-UUID + mfr block. `BbqConstant` filter prefixes
(hex of the leading AD bytes) select the parse path:

| filter const | hex prefix | SKU | parse method |
|---|---|---|---|
| `k0` | `0201050303505517ff` | **H5055** | `e()` valid → `l()` (new), else `k()` (legacy) |
| `j0` | `0201050303561017ff` | **H5610** | `m()` |
| `i0` | `0201060303519817ff` | **H5198** | `j()` |
| `d0` | `0201060303519917ff` | **H5199** | `g()` (jadx method-dump; layout not recovered) |
| `g0` | `0201060303519117ff` | H5191 | `h()` (method-dump) |
| `e0` | `0201060303519217ff` | H5192 | `h()` (method-dump) |
| `h0` | `0201060303519417ff` | H5194 | `i()` (method-dump) |
| `f0` | `0201060303519617ff` | H5196 | `g()` (method-dump) |

`0201 06` = flags AD; `0303 5599/5610/5198/...` = 16-bit service-UUID list (little-endian, so
service UUID `0x9955`, `0x1056`, `0x9851`, …); `17 ff` = len 0x17, mfr-specific AD type.

### 3.1 Temperature decode helpers (`BcDeviceInfoParseUtil`)
- `b(b2,b3)` = `getSignedIntV2({b2,b3},hFirst=true)/100.0` → signed 16-bit **big-endian**,
  /100 → °C or °F (per unit flag). `b2=b3=FF` → `-10000.0` (probe absent).
- `c(b2,b3)` = `(b2&0xFF) + (b3&0xFF)*256` → unsigned 16-bit **little-endian**, no scaling
  (legacy H5055 `k()`). `FF FF` → −10000.

### 3.2 H5198 / H5610 / new-H5055 18-byte format (`j()`, `m()`, `l()`)
Anchor: `parseBbqBleValidBytePosV2` (H5198 `j`) / `parseBbqBleValidBytePosV1` (H5610 `m`);
new-H5055 `l()` copies `scanRecord[13..]` (≥16 B). Layout of the 18-byte block:

| off | field | notes |
|---|---|---|
| 0–1 | pactType | `getUnsignedInt` BE |
| 2 | pactCode | u8 |
| 3 | bit7 = temp-unit (1=°F/0=°C); bits0–6 = pedestal battery % | |
| 4 | bits6–7 = broadcast order (`0/1/2` → probe pair 1-2 / 3-4 / 5-6); per-bit probe-connected | mask `t=0x0F` low nibble, `B=0x40`, `0x80` |
| 5 | per-bit probe-alarm; (in `j()`) bits 4–7 = pedestal charge / full-bat / hi-bat-alarm / charge-alarm | |
| 6–7 | probe-A current temp | `b()` BE16/100 |
| 8–9 | probe-A high (target) temp | |
| 10–11 | probe-A low (min) temp | |
| 12–13 | probe-B current temp | |
| 14–15 | probe-B high temp | |
| 16–17 | probe-B low temp | |

`j()` (H5198) reads probe-connected/alarm via fixed bit masks
(`BbqBleProtocol.B=0x40`, `0x80`, `J=0x10`, `0x20`); `m()` (H5610) and `l()` derive the bits
from the broadcast-order nibble via `BleUtils.w(byte,bit)`. Each broadcast carries only **one
probe pair**; the app reassembles up to 6 probes (`ProbeId 1..6`) across successive adverts.

### 3.3 Legacy H5055 16-byte format (`k()`, anchor `scanRecord[13..]`)
| off | field |
|---|---|
| 0 | pedestal battery % (u8) |
| 1 | bits6–7 = probe-pair selector; bits0–5 = per-probe insert/connected state |
| 2 | bit5 = temp-unit; bit4 = probe-A alarm |
| 3–4 | probe-A current temp `c()` LE16 |
| 5–6 | probe-A low temp |
| 7–8 | probe-A high temp |
| 9 | bit4 = probe-B alarm |
| 10–11 | probe-B current temp |
| 12–13 | probe-B low temp |
| 14–15 | probe-B high temp |

`e()` quick presence check returns `BleBroadCastInfo(valid, pactType=getUnsignedInt(b6,b7),
pactCode=b8, serial=b4&0x0F, connectedFlag=b4&0x40)` from the V1-style anchor.

### 3.4 BBQ connected protocol (`BbqBleProtocol`, base2newth/bbq/ble/controller/*)
These probe stations also support a connected GATT path for setup/history. Frame = standard
20-byte `[type][opcode]…[BCC]`. Notable `BbqBleProtocol` constants (opcode bytes; names
obfuscated — values verified): device-id/version reads, `SecretKeyController` /
`SecretKeyControllerV2` (binding token), `ControllerSyncTime`, and a probe-alarm/target-temp
write set. Masks: `B=0x40` (probe connected), `t=0x0F` (probe-pair / low-nibble),
`J=0x10`,`s=0x20`,`A=0x28` (alarm/state bits). Per-opcode payloads for target-temp writes were
not exhaustively decompiled (several `BcDeviceInfoParseUtil.g/h/i` bodies are jadx
method-dumps) — flag for live capture.

---

## 4. Leak detectors & gateway sub-devices

Leak/sub thermometers are **not** direct broadcasters in most cases; they report through a
gateway (`H5042`/`H5043`/`H5044`/`H5151`) over (a) the gateway's relayed BLE broadcast,
(b) a notify on connect, or (c) cloud `pt`/IoT JSON (`ResultPt.bytes()`).

### 4.1 Gateway ↔ sub coverage

| Gateway | goodsType | sub SKUs hosted | source |
|---|---|---|---|
| H5042 | 198 | H5109 (thermometer, subType 1) | `h5042/pact/Support.java` |
| H5043 | 158 | H5058, H5059 (leak), H5107 (TH), H5310, H5830 | `h5043/pact/Support.java` |
| H5044 | 291 | H5059, H5830 (leak), H5310 | `h5043/pact/Support.java` |
| H5151 | 65 | TH sub-devices (H5100-class) | `h5151/pact/Support.java` |

H5043 sub `deviceType` byte values (`H5043Cons`): `12/13`=H5058 (v0 / new-with-leak),
`2`=H5059, ThSubCons=H5107, plus H5830/H5310.

### 4.2 Leak frame envelope (`H5043LeakageParse.a`)
20-byte notify/IoT frame; dispatch on `[0],[1]`:
| `[0]` | `[1]` | meaning | handler |
|---|---|---|---|
| `0xEE` | `0x34`(52) | warning push (status) | `e()` over `bytes[2..]` |
| `0xEE` | `0x32`(50) | sub-device info v1 (with 8-byte addr prefix) | `f()` over `bytes[2..]` |
| `0xAA` | `0x04`(4) | read reply (status) | `e()` over `bytes[2..]` |
| `0xEE` | `0x35`(53) | op-result ack | `Event4SubOpResult` |

### 4.3 H5058 leak status decode (`H5043LeakageParse.e`, valid bytes after envelope)
| off | field | notes |
|---|---|---|
| 0 | deviceType (`K(b0)`) | matches H5043Cons |
| 1 | subType (`K(b1)`) | 13 → has leak-status block |
| 2 | bit7 = online flag; bits0–6 = sno (`h0(b2,{1,7})`) | |
| 3 | (b[0] of 3-byte) misc | |
| 4 | rssi/level (`K`) | |
| 6–9 | leak-event epoch (`H(b6..9,true)`, BE32) | when valid |
| 12 | battery (`e()` ctor arg) | |
| 3rd byte bit-field `d0(b[2])` (subType 13) | bit0=up-leak, bit1=mid-leak, bit2=down-leak, bit3=low-bat-open, bit4=!gateway-warning, bit5=low-battery, bit6=!setBatLowValid, bit7=!setMuteValid |

`c()` extracts the 10-byte sub-block from a relayed broadcast (`j0()` self-protocol, windows at
offset 6 and 16), matching on `sno`.

### 4.4 H5059 / H5830 leak (`H5044LeakageParse.d`, 17-byte valid block)
Anchor for broadcast: `scanRecord[31..47]`; `b0`=sno, `b1`=deviceType (`Support.s()` →
"H5059"/"H5830").
| off | field |
|---|---|
| 0 | sno |
| 1 | deviceType |
| 2 | online (`==0`) |
| 3 | bit7 = flag `z5`; bits0–6 = sno2 |
| 4 | HW ver `hi.lo` (`h0(b4,{4,4})`) |
| 5 | SW ver `hi.lo` |
| 6 | level |
| 7–10 | leak epoch (`H(b7..10,true)` BE32) |
| 11,12 | thresholds |
| 13 | battery (`getUnsignedByte`) |
| 14 | misc |
| 15 | bit7 = lowBattery; bit6 = !gateway-warning; bit5 = leakMode (H5830 only) |

### 4.5 H5054 (older standalone leak, `com.govee.gateway`)
H5054 ("Water Leak Detector") is handled by the legacy `com.govee.gateway` module
(`gateway/pair/SkuH5054.java`, `gateway/mode/H5054Data.java`, `gateway/push/H5054Msg.java`),
behind the older H5040-series gateway — outside the base2newth pipeline. Leak warnings arrive
as cloud push (`GateWayLeakWarnResponse`) rather than BLE broadcast. (Out of the primary
base2newth scope; noted for completeness — byte layout not extracted here.)

---

## 5. Connected opcode map (TH settings / history)

All use the standard 20-byte frame: `proType` `0x33`(write)/`0xAA`(read), `byte[1]`=opcode
below, payload at `[2..]`, BCC=XOR. Service/char = modern `…1910`/`…2b11` (AbsThBle).
Source: `pact_thnew/.../ble/controller/Controller4*.java` (opcode = `getCommandType()`),
`base2newth/.../BleThProtocol.java`, `base2newth/data/controller/*`.

| opcode (dec / hex) | controller | direction | payload |
|---|---|---|---|
| 1 / 0x01 | HeartV1 / HeartPrepare | R/W | history-dump prepare (multi-packet `0xA1/0xA2`) |
| 2 / 0x02 | TemUnit | R/W | `[unit]` (1 byte; 1=°F-mode flag) |
| 3 / 0x03 | HumWarning | R/W | enable + 2×LE16 thresholds + flags |
| 4 / 0x04 | TemWarning | R/W | `[enable, lowTemp LE16, highTemp LE16, hyst]` (`getSignedBytesFor2`) |
| 5 / 0x05 | UploadFreq | R/W | reporting interval |
| 6 / 0x06 | HumCali | R/W | signed LE16 humidity offset |
| 7 / 0x07 | TemCali | R/W | signed LE16 temp offset (`getSignedShort(b1,b0)`) |
| 8 / 0x08 | Battery | R | reply `[0]` = battery % (`getUnsignedByte`) |
| 10 / 0x0A | HeartV0 | R/W | legacy history prepare |
| 12 / 0x0C | DeviceId | R | device id |
| 13 / 0x0D | BleHv | R | BLE hardware version |
| 14 / 0x0E | BleSv | R | BLE software version |
| 16 / 0x10 | SyncTime / SyncDstTime | W | epoch + DST |
| 17 / 0x11 | ClearData | W | wipe stored history |
| 31 / 0x1F | AirNotify | notify | air-quality push enable (H5106/H5140) |
| 32 / 0x20 | WifiHv | R | Wi-Fi hardware version (gateway-capable SKUs) |
| 33 / 0x21 | WifiSv | R | Wi-Fi software version |
| 48 / 0x30 | Volume | R/W | buzzer volume (probe/air) |
| 54 / 0x36 | ThMulti | R/W | multi-channel TH config (B5178) |
| 0xFE | SecretKeyV0/V1 | W | binding secret-key handshake |

base2newth history-dump controllers: `ControllerHeartPrepare`=2, `ControllerHeartTimeRange(4H5140)`=1,
`ControllerStopSend`=3 (the "heart" stream uses `0xA1`/`0xA2` multi-packet; notify type `0xEE`,
`BleThProtocol.f91070f`). Gateway sub real-time op: `gwsub/Controller4SubPtRealOp`=112 (0x70);
`gwsub/Controller4H5310CloseWarn`=22 (0x16). Form4Dbgw: `ControllerBdType`=0xBD,
`ControllerCheckNetwork`=0x12.

---

## 6. Per-SKU summary matrix

| SKU | goodsType | category | BLE? | live data via | notes |
|---|---|---|---|---|---|
| H5051 | 0 | TH | broadcast | adv (H50, LE16) | legacy |
| H5052 | 0 | TH | broadcast | adv (H50) | |
| H5053 | 0 | TH | broadcast | adv (H50) | |
| H5054 | 0 | leak | gateway | cloud push (H5040 gw) | legacy module |
| H5055 | 0 | BBQ probe | broadcast (+connect) | adv (`l`/`k`, 0x5055) | dual-probe, high/low temps |
| H5074 | 0 | TH | broadcast | adv (H50) | |
| H5075 | 0 | TH | broadcast | adv (H5072_75, packed-24) | |
| H5100 | 66 | TH | broadcast (+connect) | adv (H51) + settings | |
| H5101 | 8 | TH | broadcast | adv (H51) | |
| H5104 | 154 | TH | broadcast | adv (H51) | |
| H5105 | 190 | TH | broadcast | adv (H51) | |
| H5106 | 124 | air (PM2.5) | broadcast (+connect) | adv (THP-32) + AirNotify | temp/hum/**pm2.5** |
| H5108 | 194 | TH | broadcast | adv (H51) | |
| H5109 | 199 | TH probe | gateway (H5042) | relayed adv / pt | sub subType 1 |
| H5110 | 287 | TH | broadcast | adv (H51) | |
| H5112 | 330 | TH (R1 Pro) | broadcast (+connect) | adv (H5112, flags) | dual-channel |
| H5140 | 319 | CO₂ | broadcast (+connect) | adv (AD-11, **CO₂ BE16**) | temp/hum/co2 |
| H5179 | 7 | Wi-Fi TH | broadcast (+wifi) | adv (HW-gated) | |
| H5198 | 85 | meat probe | broadcast (+connect) | adv (`j`, 0x5198) | dual-probe |
| H5199 | 155 | meat probe | broadcast | adv (`g`, 0x5199) | layout = jadx method-dump (flag) |
| H5610 | 344 | meat probe | broadcast (+connect) | adv (`m`, 0x5610) | dual-probe |
| H5055(BBQ) | — | kitchen | broadcast | see H5055 | |
| H5042 | 198 | gateway | connect/wifi | hosts H5109 | |
| H5043 | 158 | gateway | connect/wifi | hosts H5058/59/107/310/830 | |
| H5044 | 291 | gateway | connect/wifi | hosts H5059/830/310 | |
| H5151 | 65 | gateway | connect/wifi | hosts TH subs | BleProtocol opcodes 1..11 |

---

## 7. Open questions / uncertainty flags

1. **H5199/H5191/H5192/H5194/H5196 probe layouts** — `BcDeviceInfoParseUtil.g/h/i` are jadx
   method-dumps (`UnsupportedOperationException`), so exact byte offsets are inferred from the
   sibling readable formats (`j`/`m`/`l`) but not byte-confirmed. Capture needed.
2. **H5109 middle 32-bit** (`H5109BroadParseImp`) — timestamp vs reading unconfirmed.
3. **BBQ connected target-temp/alarm write payloads** — `BbqBleProtocol` opcode→payload mapping
   only partially recovered (obfuscated single-letter fields).
4. **H5054 legacy leak** — handled in `com.govee.gateway` (out of base2newth); byte layout not
   extracted here.
5. **Temp-unit byte semantics** (opcode 0x02): payload is `[d]` with default `d=1`; whether
   `1=°C` or `1=°F` not cross-checked against UI.
6. **`parseThpValue` PM channel cap** at 0..999 — PM2.5 readings ≥1000 µg/m³ would wrap; assumed
   never hit in practice.
</content>
</invoke>
