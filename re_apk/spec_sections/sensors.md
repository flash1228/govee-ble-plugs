# Sensors & Appliances Survey — Thermo-Hygrometers, BBQ Probes, Humidifiers / Ice-Makers / Air

Scope: Govee sensor & small-appliance BLE protocols decompiled from the Govee Home base APK
and the split feature modules `pact_thnew`, `pact_bbqnew`, `pact_h7160`, `pact_h7172`.
This is a *survey* across several product families that share the 20-byte Govee frame
format but use different opcode maps and temperature encodings.

Families covered:

| Family | Module / package | Devices (representative) | Category |
|---|---|---|---|
| TH "newth" framework | `base/.../base2newth`, `pact_thnew` | H5100/H5101/H5104/H5105/H5106/H5108/H5179/H5074-style, H5112 (probe gateway), H5140 (CO₂/air), H5220 (clock), H5107/H5108/H5109/H5310 | Temp/Humidity/Air sensors |
| BBQ (new) | `pact_bbqnew` (`com.govee.pact_bbqnew`, `com.govee.pact_h5199`) | H5055, H5198/H5199, H5610, H5183/H5184-class probes | Multi-probe BBQ thermometers |
| BBQ (legacy) | `base/.../base2newth/bbq` | older BBQ + H5151 gateway | Multi-probe BBQ thermometers |
| Humidifier | `pact_h7160` (`com.govee.h7160`) | H7160 | Humidifier appliance |
| Ice maker | `pact_h7172` (`com.govee.h7172`, `com.govee.h7178`) | H7172 / H7178 / H717D | Ice-maker appliance |
| Gateways w/ sub-sensors | `base/.../h5042`, `h5043`, `h5151` | H5042/H5043 gateways + H5044 leak / H5058 / H5059 / H5107/H5109 sub-devices | Sensor gateway |

> Frame recap (verified ground truth): single packet is 20 bytes, `byte[0]` = command type
> (`0x33` write / `0xAA` read), `byte[1]` = opcode, `byte[2..18]` = payload (zero padded),
> `byte[19]` = XOR BCC of bytes 0..18. Notify frames start `0xEE`. Multi-packet uses
> `0xA1`/`0xA2`. All controllers below build their frame via
> `BleUtil.generate20Bytes(proType, commandType, payload)` (`base2newth.AbsSingleController.c()/d()`
> and `base2light...AbsController`). `getProType()` returns `0x33` when `isWrite()` else `0xAA`.
> The numbers in `getCommandType()` ARE the `byte[1]` opcode.

---

## 1. Temperature & Humidity encodings (shared primitives)

These appear everywhere, so they are defined once.

### 1.1 `ThUtil` (base2newth/ThUtil.java)
- Temperatures are carried internally as **centi-Celsius** (`celTem100 = °C × 100`).
  `tem2Fah(celTem100) = (celTem100/100)*1.8 + 32`.
- Humidity carried as **centi-percent** (`%RH × 100`) in most connected frames, sometimes
  whole-percent in older broadcast layouts (see below).
- Sentinels: invalid temperature = `-100000`; invalid humidity = `-1`; invalid time = `-1`.
  `isValidThData(tem,hum,time)` rejects those. A raw 2-byte `0xFFFF` field also means
  "no data / probe disconnected".

### 1.2 Packed 3-byte temp+hum (`ThBroadcastUtil.m()` / `BleUtil.parseThValue`)
The classic Govee broadcast packing of temperature **and** humidity into a single 24-bit int:
```
raw = signedInt(bytes[0..2], bigEndian, signed)
if MSB(byte0) set:  byte0 -= 128; sign = negative   // top bit = sign flag
tem = (raw / 1000) * 10      // → centi-°C  (divide by 100 downstream for °C)
hum = (raw % 1000) * 10      // → centi-%RH (divide by 100 downstream for %)
negative branch divides by -1000
```
`source: pact_thnew/.../pact/ThBroadcastUtil.m()` and `base2home.pact.BleUtil.parseThValue`.
Net effect: `temp_°C = tem/100`, `hum_% = hum/100`. Range gate applied by callers:
temp valid `-4000..10000` (i.e. -40..100 °C), hum valid `0..10000` (0..100 %).

### 1.3 PM2.5 packing (`parseThpValue`, 4 bytes)
Used by H5106/H5108-class air monitors. Returns `[tem, hum, pm25]`. `ThBroadcastUtil.j()`
reads 4 payload bytes at offset 3 → `parseThpValue` → `{tem, hum, pm25}`.
`isValidThpData` requires `tem != -100000 && hum > -1 && pm25 > -1`.

---

## 2. Thermo-Hygrometer family (`pact_thnew` / `base2newth`)

All controllers extend `base2newth.AbsSingleController` (or `AbsControllerWithCallback`);
write proType `0x33`, read proType `0xAA`. Notify/heartbeat frames begin `0xEE`.

### 2.1 Connected heartbeat (live temp/hum read) — the key sensor read

**Controller4HeartV0** — `getCommandType() = 0x0A` (10). Read frame `AA 0A ...`.
`source: pact_thnew/.../ble/controller/Controller4HeartV0.parseValidBytes`
Payload parse (17 valid bytes after stripping header):
| bytes | field | encoding |
|---|---|---|
| [0..1] | temperature | `getSignedShort(b[1],b[0])` → centi-°C; `0xFFFF` ⇒ invalid (-1) |
| [2..3] | humidity | `getSignedInt({b2,b3}, false)` → centi-%RH; `0xFFFF` ⇒ invalid |
| (battery default 100) | — | V0 has no battery byte; hard-coded 100 |

**Controller4HeartV1** — `getCommandType() = 0x01` (1). Read frame `AA 01 ...`.
`source: Controller4HeartV1.j()` (standard TH) and `.k()` (H5112 probe variant)
- `.j()` standard: `[0..1]` temp signedShort, `[2..3]` hum signedInt(signed), `[4]` battery%
  (`getUnsignedByte`), `[5]` warning/online flag (`>0`).
- `.k()` H5112 probe gateway: `[0..1]` temp `signedIntV2`, `[2..3]` hum, `[4..5]` a second
  temp (`signedIntV2`, `0xFFFF`⇒-1), `[6]` battery, `[7]` bit-field reversed into three
  2-bit sub-status fields → `Event4H5112Heart`.

### 2.2 Common TH config/control opcodes (proType `0x33` write / `0xAA` read)

| Opcode (hex) | Name | Controller | Payload (write) | Notes |
|---|---|---|---|---|
| 0x01 | Heartbeat V1 | Controller4HeartV1 | — (read) | temp/hum/batt |
| 0x02 | Temp unit | Controller4TemUnit | `[unit]` 0=°C 1=°F | |
| 0x03 | Humidity warning | Controller4HumWarning | `[on, minHi,minLo(2 LE signed), maxHi,maxLo]` | hum bounds centi-%, clamp 0..10000 |
| 0x04 | Temp warning | Controller4TemWarning | `[on, min(2), max(2), type]` | temp bounds centi-°C; clamp ±2000 (°C) or ±20000 (°F device) |
| 0x05 | Upload frequency | Controller4UploadFreq | `[d, e]` two bytes | sample/upload interval |
| 0x06 | Humidity calibration | Controller4HumCali | `signedBytesFor2(cali)` LE | clamp ±2000 (centi-%) |
| 0x07 | Temp calibration | Controller4TemCali | `signedBytesFor2(cali)` LE | clamp ±300 (centi-°C); parse `getSignedShort(b1,b0)` |
| 0x08 | Battery | Controller4Battery | — (read) | `getUnsignedByte(b[0])` = % |
| 0x0A | Heartbeat V0 | Controller4HeartV0 | — (read) | temp/hum |
| 0x10 | Sync time | Controller4SyncTime | `signedBytesFor4(unixSecs)` | 16 = sync clock |
| 0x30 | Volume / buzzer level | Controller4Volume | `[level]` | 48 |
| 0x36 | Multi (chart data) | Controller4ThMulti | empty (`0xA1/0xA2` multi-packet) | 54 = bulk stored-record read |

> H5107 / H5109 use **opcode 0x08** for `Controller4TemWarning4H5107/H5109` AND for
> `Controller4SwitchLongLife` (long-life battery mode) — opcode reuse is SKU-scoped.
> H5310 long-life switch = `0x05`.
> `source: pact_thnew/.../ble/controller/{h5107,h5109,h5310}/...`

### 2.3 H5106 / H5108 clock + air monitor extra opcodes

| Opcode | Name | Controller |
|---|---|---|
| 0x12 (18) | Display on/off | Controller4Display |
| 0x13 (19) | Lightness | Controller4Lightness |
| 0x15 (21) | Time zone | Controller4TimeZone |
| 0x16 (22) | PM2.5 warning | Controller4Pm25Warning |
| 0x17 (23) | Time format (12/24h) | Controller4TimeFormat |
| 0x18 (24) | Upload last data | Controller4UploadLastData |
| 0x19 (25) | Lightness V2 | Controller4LightnessV2 |
`source: pact_thnew/.../ble/controller/h5106/*`

### 2.4 H5140 CO₂ / air-quality opcodes

| Opcode | Name | Controller | Payload |
|---|---|---|---|
| 0x16 (22) | CO₂ warning | Controller4Co2Warning | `[on, min(2 signedShort), max(2), grade]`; parse `getSignedShort(b1,b2)` etc. |
| 0x1B (27) | Sound/alarm level | Controller4SoundLevel | `[enable, level]` |
| 0x1C (28) | CO₂ manual calibration | Controller4Co2ManualCali / ControllerCo2ManualCalibration | |
| 0x1D (29) | CO₂ set grade | Controller4Co2SetGrade | `[lo(2), hi(2)]` |
| 0x1E (30) | Do-not-disturb (WuRao) mode | Controller4WuRaoMode | |
| 0x1F (31) | Air-quality switch | Controller4AirQualitySwitch | `[1, state]`; read returns `b[1]==1` |
`source: pact_thnew/.../ble/controller/h5140/*`

### 2.5 H5112 probe-gateway extra opcodes (food/meat probe over Wi-Fi gateway)

| Opcode | Name | Controller | Notes |
|---|---|---|---|
| 0x03 | Hum warning | Controller4HumWarning4H5112 | |
| 0x04 | Temp warning | Controller4TemWarningH5112 | |
| 0x07 | Temp calibration | Controller4TemCaliH5112 | |
| 0x15 (21) | Probe icon | Controller4ProbeIcon | |
| 0x35 (53) | Check network | Controller4CheckNet | gateway Wi-Fi check |
| 0x70 (112) | Probe real-time op | Controller4PtRealOp | start/stop live probe stream |
`source: pact_thnew/.../ble/controller/h5112/*`

### 2.6 TH broadcast (advertisement) layouts — multiple versions

`ThBroadcastUtil` exposes one parser per broadcast generation. All first locate the valid
byte position with `BleUtil.checkBroadcastData` / `parseThBleValidBytePos[V1]` /
`parseMultiThBleValidBytePos`. Returned int[] are `[pactType, pactCode, ...sensorvalues]`.
`source: pact_thnew/.../pact/ThBroadcastUtil.java`

| Method | Layout (relative to valid pos) | Yields |
|---|---|---|
| `c()` | `[0]=order, [1..2]=temp signedShort, [3..4]=hum signedIntV2, [5]=batt signedIntV2` | temp(centi-°C), hum(centi-%), batt |
| `d()` | `[0..1]=pactType, [2]=pactCode, [3..5]=packed m(), [6]=batt` | packed temp+hum + batt |
| `e()` | `[3..4]=temp signedShort, [5..6]=hum signedShort, [7]=batt` (8-byte) | separate temp/hum shorts |
| `f()` | `[3..5]=parseThValue (packed), [6]=batt, [7]=flag>0` (8-byte) | packed temp+hum + flag |
| `g()` | `[1..3]=packed m(), [4]=batt` (7-byte, no pact) | packed |
| `h()` | 10-byte multi-sensor: `[3]=order, [4..6]=m(), [7]=status bits, [8..9]=extra uint` | multi-probe TH |
| `i()` | 9-byte: `[3..5]=parseThValue, [6]=batt, [7]=reversed-bit substatus, [8]=probe sel/extra` | probe TH (H5112-ish) |
| `j()` | 7-byte THP: `[3..6]=parseThpValue` | temp+hum+**pm2.5** |
| `k()` | iBeacon/AD type **0x0B** (11), 11 bytes, `[0]==0xFF`: `[2..3]=pactType, [4]=code, [5..7]=parseThValue, [8..9]=signedIntV2` | packed temp+hum + extra |
| `l()` | 8-byte: `[3..5]=m(), [6]=batt, [7]=reversed-2bit fields` | |

`m()` helper = the packed 3-byte temp/hum splitter from §1.2 (the workhorse).
`a()` = "all 0xFF ⇒ no data". The temp/hum scaling for ALL of these is centi-units → divide
by 100 for °C / %. Humidity in some legacy layouts (`signedIntV2` single byte) is whole-percent.

---

## 3. BBQ multi-probe thermometers (`pact_bbqnew`)

Newer BBQ stack. Controllers extend `base2light...AbsController` / `AbsOnlyReadSingleController`;
write proType `0x33`, read `0xAA`. Opcode constants live in
`pact_bbqnew/.../ble/BbqBleProtocol.java`. Handshake uses secret key (`0xB1`) like other Govee.

### 3.1 BbqBleProtocol opcode constants (decimal → hex)

| Const | Dec | Hex | Used by |
|---|---|---|---|
| b | 3 | 0x03 | heartbeat (Controller4BbqHeart) / TdToPrepare |
| c,f,U | 1 | 0x01 | preset inner temp (legacy product) |
| T | 9 | 0x09 | preset inner temp (new product) |
| V,u | 17 | 0x11 | preset **env/ambient** temp (PresetEnvTempController) |
| w,g | 12 | 0x0C | pre-warn (legacy) / DeviceId(new) |
| h | 6 | 0x06 | DeviceId (legacy) |
| n,W | 5 | 0x05 | upload interval |
| v,e | 7 | 0x07 | switch buzzer |
| o,p | 14 | 0x0E | (sync/hard ver area) |
| i | 10 | 0x0A | sync time (Controller4SyncTime) |
| t | 15 | 0x0F | probe-count mask `&0x0F` |
| q,H | 33 | 0x21 | (alarm/threshold) |
| s,z | 32 | 0x20 | |
| x | 39 | 0x27 | pre-warn (new product) |
| B | 64 | 0x40 | clear-probe / connected-bitmask |
| C | 65 | 0x41 | **probe pair** (write + notify result) |
| D | 66 | 0x42 | break probe pair |
| E | 51 | 0x33 | close alarm |
| F | 35 | 0x23 | |
| M,N | 36 | 0x24 | heartbeat V1 (new product cmd) |
| O | 37 | 0x25 | buzzer gear |
| P,X | 38 | 0x26 | auto-shutdown / auto-reduce-brightness |
| A,s | 40/32 | 0x28 | |
| J | 16 | 0x10 | inner-alarm bitmask |
`source: pact_bbqnew/.../ble/BbqBleProtocol.java`

### 3.2 BBQ control opcodes (resolved)

| Opcode | Name | Controller | Payload |
|---|---|---|---|
| 0x01 / 0x09 | Preset inner-meat target temp | PresetInnerTempController | see §3.4 (probeId, hi/lo target, foodType) |
| 0x11 (17) | Preset ambient/env temp | PresetEnvTempController | `[probeId, hiTemp(2 LE ×100), loTemp(2 LE ×100), foodType, foodSubType(2)]`; `<-10` ⇒ `0xFFFF` |
| 0x0C / 0x27 | Pre-warn threshold | Controller4PreWarn | `[on, temp(2 LE ×100)]` (legacy 0x0C, new product 0x27) |
| 0x41 (65) | Probe pair (start) | Controller4ProbePair | `[probeId]`; notify result via `ProbePairResultParse` |
| 0x42 (66) | Break/unpair probe | Controller4BreakProbePair | `[probeId]` |
| 0x40 (64) | Clear probe | Controller4ClearProbe | |
| 0x33 (51) | Close alarm | Controller4CloseAlarm | |
| 0x25 (37) | Buzzer gear | Controller4BuzzerGear | gear level |
| 0x07 | Switch buzzer | Controller4SwitchBuzzer | on/off |
| 0x05 | Upload interval | Controller4UploadInterval | interval |
| 0x26 (38) | Auto shutdown | ControllerAutoShutdown | |
| 0x26 (38) | Auto-reduce brightness | Controller4AutoReduceBrightness | |
| 0x02 / 0x03 | Temp unit | Controller4TemUnit | `[unitOrdinal]` (0x02 standard / new, 0x03 legacy-non-new) |
| 0x0A (10) | Sync time | Controller4SyncTime | unix |
| 0x06 / 0x0C | Device id | Controller4DeviceId | (0x0C when new product flag set) |
| 0x03 (heart) | Heartbeat (toggle byte) | Controller4BbqHeart | `[toggle]` (alternating 0/1) |
| 0x00 / 0x24 / 0x01 | Heartbeat V1 | Controller4BbqHeartV1 | SKU-dependent cmd & proType (`0xBB` legacy non-new) |
`source: pact_bbqnew/.../ble/controller/*`

### 3.3 BBQ probe temperature encoding (`BcDeviceInfoParseUtil`)

Two scaling helpers (`source: pact_bbqnew/.../pact/BcDeviceInfoParseUtil`):
- **`b(b2,b3)`** = `signedIntV2({b2,b3}, littleEndian) / 100.0` → **°C with 0.01 resolution**,
  signed (sub-zero supported). `0xFFFF` ⇒ `-10000.0f` sentinel (probe disconnected/no reading).
  This is the modern high-resolution format.
- **`c(b2,b3)`** = `getUnsignedByte(b2) + getUnsignedByte(b3)*256` → **whole-degree** unsigned
  little-endian (older format). `0xFFFF` ⇒ `-10000.0f`.

### 3.4 BBQ connected heartbeat parse (`Controller4BbqHeartV1.Companion`)
Four SKU variants `a()/b()/c()/d()`. Common structure (`a()` shown, 6 probes):
| byte | field |
|---|---|
| [0] bits0-6 | pedestal battery % ; bit7 = temp unit (1=°F) |
| [1] bit i | probe i connected (8-bit mask) |
| [2] bit i | probe i inner-alarm (8-bit mask) |
| [3] bit7/6/5/4 | pedestal charging / full-battery / batt-high-alarm / charge-alarm |
| [4+2k] (k=0..5) | probe k current temp via `b(lo,hi)` (centi-°C) |
6 probes, each `IbProbeInfo{probeId, connected, innerAlarm, innerCurrTemp}`.
Variant `b()` packs unit+battery into byte[0] nibble fields, probes start at byte[3].
Variant `c()` uses the whole-degree `c()` scaler. Variant `d()` (H5610 "V3") uses
`BleUtils.w(byte,bit)` bit extraction. `source: Controller4BbqHeartV1` lines 23-215.

### 3.5 BBQ broadcast (advertisement) parse — multiple versions

`BcDeviceInfoParseUtil.f()` dispatches on `filterStr` (SKU). 18-byte payloads after locating
the valid index via `BleUtil.parseBbqBleValidBytePosV1/V2`. Representative (`m()` = V5 / `j()`):
| byte | field |
|---|---|
| [0..1] | pactType (`getUnsignedInt` LE) |
| [2] | pactCode |
| [3] bits0-6 / bit7 | pedestal battery / temp unit (1=°F) |
| [4] bits6-7 | broadcast "probe group" index (0→probes 1&2, 1→3&4, 2→5&6) |
| [4] low bits | probe-connected flags (via `BleUtils.w`) |
| [5] | inner-alarm flags + pedestal charge/full/high-alarm/charge-alarm (bits 7..4) |
| [6..7] | probe-A current temp `b()` (centi-°C) |
| [8..9] | probe-A high target `b()` |
| [10..11] | probe-A low target `b()` |
| [12..13] | probe-B current temp `b()` |
| [14..15] | probe-B high target `b()` |
| [16..17] | probe-B low target `b()` |
Because only 2 probes fit per advert, the device round-robins groups via the byte[4] index;
the app merges groups across adverts. `k()`/`l()` are older 16-byte variants using `c()`
(whole-degree) or hex-string bit parsing. `e()` validates the AD: header `[i+1]==0x03`,
`[i+2]==0x50` ('P'), `[i+3] ∈ {0x50,0x55}` ('P'/'U') (`c = {80,85}`), then a status nibble.
`source: pact_bbqnew/.../pact/BcDeviceInfoParseUtil.{e,j,k,l,m}`

### 3.6 BBQ notify parses
- `ProbePairResultParse` — notify opcode `0x41` (BbqBleProtocol.C); body `[0]==0` ⇒ pair success.
- `CookPredictTimeParse` — predicted cook-time notify.
`source: pact_bbqnew/.../ble/{ProbePairResultParse,CookPredictTimeParse}.java`

### 3.7 Legacy BBQ (`base2newth/bbq/ble/BleProtocol`)
Opcode constants (`source: base/.../base2newth/bbq/ble/BleProtocol.java`):
`3,4,5,6,7,8,10,12,13,14,16,17,32,33` = various read/config; `f91678o = -79 = 0xB1`
(SINGLE_READ_SECRET_KEY handshake); `f91679p = -2 = 0xFE`; default heart `f91680q = 6`;
`f91681r = 20`; notify prefix `f91682s = -18 = 0xEE`. Secret-key handshake handled by
`SecretKeyController` / `SecretKeyControllerV2`. H5151 is the BBQ Wi-Fi gateway
(`base/.../h5151`, broadcast handled by `h5151/add/BleBroadcastProcessor`).

---

## 4. H7160 Humidifier (`pact_h7160`)

Uses the shared `base_h71xx` framework: opcode bytes come from
`base_h71xx.sku_base.BleProtocolConstants` and are **re-assigned per-SKU at runtime**
(configurable; defaults shown). write `0x33` / read `0xAA`.

### 4.1 Heartbeat (live status) — `HeartControllerV1`
`source: pact_h7160/.../ble/HeartControllerV1.parseValidBytes`
| byte | field | encoding |
|---|---|---|
| [0] | on/off | `==1` |
| [1] | (mode/gear value) | `b[1]` |
| [2] | secondary on flag | `==1` |
| [3..5] | a 24-bit value | `getSignedInt({b3,b4,b5}, signed)` (e.g. remaining/level, default 0xFFFFFF) |
| [6] | extra status | `b[6]` |

### 4.2 Mode / setting controllers
All mode controllers share command type `d0()` (default field `f97311w = 5` ⇒ **0x05**),
and select the sub-mode through `payload[0]`:
| Controller | sub-mode selector (payload[0]) | const | default |
|---|---|---|---|
| ModeCurController | `j0()` | B | 0 (0x00) current/manual |
| ModeGearController | `o0()` | C | gear; write `[o0, gear]` |
| ModeAutoController | `f0()` | E | 3 (0x03) auto/target-humidity |
| ModeCustomController | `k0()` | D | 2 (0x02) custom schedule |
| ModeChildController | `payload[0]=childValue` | — | child of custom |
| AbnormalInfoController | cmd `w()` = `O0` = **0x17 (23)** | read | parse `[0]=fault,[1]=flag,[2]=code` |
| RhythmModeController | (rhythm/diy) | — | |
`source: pact_h7160/.../ble/controller/*` + `base_h71xx/sku_base/BleProtocolConstants`.
> NOTE: because `BleProtocolConstants` fields are mutated at SKU init (e.g. line 756
> `f97311w = b6`), treat the default values as indicative; the live values are negotiated /
> configured per device. Mode command type is consistently `d0()`; sub-mode is in `payload[0]`.

---

## 5. H7172 / H7178 Ice Maker (`pact_h7172`)

Also a `base_h71xx`-framework appliance. write `0x33` / read `0xAA`.
`source: pact_h7172/.../ble/controller/*`

| Opcode | Name | Controller | Payload |
|---|---|---|---|
| 0x01 | Main switch | SwitchController | on/off |
| `d0()` (~0x05) | Ice size (mode) | IceSizeController | `[size]` (small/med/large via Mode enum) |
| `I()` | Delay start | DelayStartController | timer |
| `O()` (0x17?) | Equipment status | EquipmentStatusController | read device state |
| `w()` = 0x17 (23) | Abnormal/fault info | AbnormalInfoController | `[fault,flag,code]` |
| `d0()` | Current mode | ModeCurController | `[modeValue]`; parse `Mode.a(getUnsignedByte(b[0]))` |
Heartbeat via `HeartControllerV1`. Most of the H7178 chart/log/ice-prediction logic is
IoT/cloud (`com.govee.h7178.network` / `viewmodel`), not BLE.

---

## 6. Sensor gateways with sub-devices (H5042 / H5043 / H5151)

These are multi-sensor **gateways**; they do not themselves carry temp/hum but relay
sub-device frames over multi-packet (`0xA1/0xA2/0xA6` etc.). The sub-device temp/hum/leak
data is delivered through notify parses that hand the raw bytes to `Event4*` classes.

- **H5042** (`base/.../h5042/ble`): sub-device info notify `SubDeviceInfoNotifyParse.c() = 0x34`
  (52) → `Event4SubDeviceInfoUpdate.a(value)`. Other parses: `SubDeviceAddNotifyParse`,
  `SubDeviceIdentifyNotifyParse`, `SubDeviceOpResultParse`, `WifiNotifyParse`.
  Sub-device add controller `Controller4SyncSubDevice`.
- **H5043** (`base/.../h5043/ble`): leak parses `H5043LeakageParse`, `H5044LeakageParse`;
  status `SubDeviceStatusUpdateNotifyParse`, `SubDevice4ThOpResultParse`; per-SKU events for
  H5058/H5059/H5107/H830 sub-devices. H5044 = water-leak sensor.
- **H5151** (`base/.../h5151`): BBQ/TH Wi-Fi gateway; `ble/BleProtocol`, broadcast via
  `h5151/add/BleBroadcastProcessor` → `base2newth.bbq.model.DeviceInfo`.

Exact sub-device byte layouts are delegated to `Event4*` classes (mostly obfuscated to
`a(byte[])`); flagged as not fully resolved here (see Open Questions).

---

## 7. Checksum / framing notes
- All single-packet frames: `byte[19] = XOR(bytes[0..18])` (`BleUtil.generate20Bytes`).
- Read replies / heartbeats arrive as `0xEE`-prefixed notify frames; controllers strip the
  first two header bytes (`proType`, `opcode`) before `parseValidBytes` (`AbsSingleController.onResult`
  copies `value[2..]` into a 17-byte buffer, unless `value[0]==0xAB` legacy).
- Multi-byte temps: little-endian (`signedIntV2`, `getSignedBytesFor2(...,true)`) in BBQ &
  H5112; big-endian packed 3-byte in classic TH broadcast (`m()`); `getSignedShort(lo,hi)`
  arg order varies per call site — verify per controller.
- Encryption: secret-key handshake `0xB1`/`0xB2` (`SecretKeyController*`, `Controller4SecretKeyV0/V1`)
  precedes config on secured SKUs; BBQ pairing uses `AbsPairAc4SecretV1`.
