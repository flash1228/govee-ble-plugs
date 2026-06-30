# Kitchen & Air-Treatment Appliances — BLE protocol (`fam-kitchen-air`)

Covers Govee BLE+Wi-Fi appliances built on the **`base_h71xx`** framework
(humidifiers, dehumidifiers, purifiers, fans, kettles, heaters, ice makers, rice
cooker) plus two mis-tagged light SKUs that happen to live in the assigned dirs
(`h7022` String Light, `h7017` Plant Grow Light) and the `H5140` CO₂ monitor
(broadcast-only).

All frames use the master 20-byte format (`[type][opcode][payload…][BCC=XOR]`).
jadx prints signed bytes — values below are hex via `(v & 0xFF)`.

---

## 1. Scope / SKU coverage

| Cluster | Module(s) | goodsType(s) | Representative SKUs | BLE control? |
|---|---|---|---|---|
| Humidifier H7160 | `pact_h7160` + `base_h71xx` | 99 | H7160 | **Yes** (connect+frames) |
| Ice maker H7172 / H7178 / H717D | `pact_h7172` + `base_h71xx` | 117, 211, … | H7172, H7178, H717D | **Yes** |
| Kettles | `base_h71xx` (+ `eco` parsers) | 135/168/177/… | H7170/71/73/75/7A | **Yes** |
| Heaters | `base_h71xx` | 60/115/153/… | H7130–H713E | **Yes** |
| Purifiers / Fans / Dehumidifiers / Humidifiers (other) | `base_h71xx` | many (Air Treatment) | H7100‑H7152 | **Yes** |
| Newer ice makers / ice-cream | `base_h71xx` + `eco` | 306/317/321/335/372 | H8102/8120/8121/8122/8131 | **Yes** |
| String Light (mis-tagged) | `h7022` | 24 | H7022 | **Yes** (light; base2light) |
| Plant Grow Light (mis-tagged) | `h7017` | 0 | H7017 | **Yes** (light; base2light) |
| CO₂ Monitor | `widget/.../H5140ThBroadParseImp` | 319 | H5140 | **Broadcast-only** |

> **Note on the assignment label:** `h7022` is a **String Light** (goodsType 24)
> and `h7017` a **Plant Grow Light**, *not* kettle/heater. The kettle/heater/
> humidifier/ice-maker logic actually lives in `base_h71xx` and the `eco`
> action parsers, which is where this section concentrates.

---

## 2. The `base_h71xx` opcode table (runtime-reassignable singleton)

The kitchen/air appliances do **not** hard-code opcodes. Every controller reads
its opcode/sub-byte from a single **mutable static singleton**
`com.govee.base_h71xx.sku_base.BleProtocolConstants` (instance field
`f97224a`, also referenced as `.a`). Controllers call *getters* (e.g.
`getCommandType(){ return …BleProtocolConstants.f97224a.F(); }`) at
frame-build time, so opcodes are **late-bound** — the table can in principle be
rewritten per-SKU (the class exposes a full set of setters such as `S3()`,
`e4()`, `Q2()`). In v7.5.20 no bulk per-SKU reassignment of the
switch/mode/feature opcodes was found (only MCU-version / temp-cali helpers
mutate a few fields), so the **default field values below are the effective
wire opcodes** for this family. Treat them as defaults that a future SKU spec
*may* override.

`proType` (byte[0]) defaults: write `t1()=f97228b=0x33`, read
`O0()=f97236d=0xAA`, secure/alt write `v1()=f97240e=u1()=f97232c=0x3A`.
On/off value bytes: enable `N()=f97252h=0x01`, disable `M()=f97256i=0x00`.

### 2.1 Opcode map (getter → field default → meaning)

| Getter | Default (hex) | Opcode role | Source |
|---|---|---|---|
| `g1()` f97279o | **0x01** | **Power on/off** | `SwitchH7172ActionParser`, `SwitchH717DActionParser` |
| `d0()` f97311w | **0x05** | **Mode / gear / ice-size** | `ModeKettleActionParser`, `ModeIceActionParser`, `GearActionParser`, H7160 `Mode` |
| `P()` B0 | 0x10 | Thermometer-probe reading notify | `h7160/iot/CmdStatusParseV1` |
| `F()` D0 | 0x11 | Delay-off (timer-off) | `DelayOffController` |
| `j1()` H0 | 0x12 | Timer count (read) | `TimerCountController` |
| `k1()` I0 | 0x13 | Timer group v2 (read/notify) | `TimerCountController`, H7160 parse |
| `J0()` K0 | 0x16 | Do-not-disturb window | `NotDisturbControllerV1` |
| `w()` O0 | 0x17 | Humidifier/appliance **work-status + abnormal** notify | H7160/H7172 parse |
| `Y()` Z0 | 0x18 | Indicator (status) light | `IndicatorLightController` |
| `O()` V | 0x19 | **Ice-maker work-status** notify | `h7172/iot/CmdStatusParseV1.g()` |
| `c0()` f97246f1 | 0x1A | UV-C lamp on/off | `LightUVCController` |
| `b0()` f97254h1 | 0x1B | **Water-box / accent light** (RGB) on/off | `LightSwitchH717DActionParser`, H7160 `LightRgbData` |
| `D()` f97285p1 | **0x1F** | **Multiplexed function-switch / settings** (sub-byte selects feature) | `Lock/Shake/Rewu/SensorTempUnit` controllers; `parseCommSwitchInfo` |
| `A()` f97324z0 | 0x08 | Thermometer-probe pairing notify (MAC in bytes 2..7) | H7160 parse *(low conf.)* |
| `G()` E0 | 0x26 | Delay-off v1 | `DelayOffControllerV1` |
| `C()` G0 | 0x27 | Clean reminder (also `WashRemind` hard-codes 0x27) | `CleanReminderController`, `WashRemindController` |
| `I()` f97237d0 | 0x23 | **Delay-start / reservation** (ice maker) | `h7172/iot/CmdStatusParseV1.f()`, `DelayStartInfo` |
| `h1()` f97281o1 | 0xB5 | Sync RTC time | `SyncTimeController` |

### 2.2 Sub-byte selectors under the 0x1F multiplexed settings opcode

`Lock/Shake/Rewu/SensorTempUnit` all share **commandType `D()`=0x1F**; the first
payload byte (`p()[0]`/`q()[0]`) selects the feature, byte[1] is the on/off value
(`N()`=1 / `M()`=0). Read with the `0xAA` proType returns the state in byte[1]
(byte[7] for temp-unit).

| Feature | Sub-byte (getter) | Default | Source |
|---|---|---|---|
| Shake / oscillation | `d()` f97289q1 | 0x01 | `ShakeController` |
| Child lock | `c()` f97293r1 | 0x02 | `LockController` |
| "Rewu" (warm-mist / heat) | `b()` f97301t1 | 0x08 | `RewuController` |
| Sensor temp unit (°C/°F) | `e()` f97305u1 | 0x08 | `SensorTempUnitController` |

---

## 3. Command frame layouts (writes)

Builder helper `ControllerSingle.Companion.c(opcode, payload)` produces a
single **0x33** write frame: `33 <opcode> <payload…> 00‥ BCC`. The `.d(opcode,
payload)` variant is used on the IoT "multi-sync"/secure path (proType 0x3A);
wire payload is identical. (`AbsSingleController.p()` = read payload,
`q()` = write payload.)

### 3.1 Power on/off — opcode 0x01
- H7172 ice maker ON: `01 01 01`; OFF: `01 00` (`SwitchH7172ActionParser.B`).
- H717D ice maker ON: `01 01 00`; OFF: `01 00` (`SwitchH717DActionParser.B`).
- **byte[2]** = on(1)/off(0); **byte[3]** = sub-target (1 = ice unit on H7172,
  0 = main on H717D). H717D additionally accepts a paired `SecretKeyController`
  binding frame (legacy 0xB1/B2 secret) alongside.

### 3.2 Mode — opcode 0x05 (sub-mode selector at byte[2])
The mode "selector" byte (byte[2]) is the device's mode/ice-size value; byte[3+]
carry mode params.

**Ice maker (H7172/H8120…)** — `ModeIceActionParser`/H7172 `Mode`:
`05 <iceSize>` where iceSize = `BIG=g0()=0x01`, `MIDDLE=v0()=0x02`,
`SMALL=E0()=0x03`. Read echo: `AA 05 <iceSize>`.

**Kettle / gear appliances** — `ModeKettleActionParser`:
`05 <j0()> <mode>` where `j0()=B`=0x00 (a mode-prefix byte) and `<mode>` is the
EcologyMode value (per-SKU; see `EcologyModeCons`). `GearActionParser` instead
emits `05 <gear>` (one byte) under the same 0x05 opcode for fan/heat gear.

**Humidifier H7160** — `pact_h7160/adjust/Mode*`. Mode selector byte =
`GEAR=o0()=0x01`, `AUTO=f0()=0x03`, `CUSTOM=k0()=0x02`:
- GEAR: `05 01 <mistGear>` (byte[3] = mist level).
- AUTO: `05 03 <b>` where `b = humidify(0‑100, bit0‑6) | (autoClose<<7)`
  (`ModeAuto.a`; default humidify 50). Parse reverses: `val&0x7F`,
  `(val>>7)==1`.
- CUSTOM: `05 02 <pack> <child0×5> <child1×5> <child2×5>` where
  `pack = setIndex(low nibble) | (curIndex<<4)`; each child =
  `[mistGear(1)] [onTime(2,BE)] [offTime(2,BE)]` (`ModeCustom.b`). Defaults
  children `(8,60,60)(5,60,60)(1,255,255)`. (3 timed mist stages.)

### 3.3 Delay-off / timer-off — opcode 0x11 (`DelayOffController`)
Write payload `q()`: `[enabled(1)][delayMinutes_hi][delayMinutes_lo]` — byte[0]
= on(non-zero)/off; bytes[1..2] = 16-bit BE minutes
(`getSignedBytesFor2`). v1 variant identical under opcode 0x26.
`DelayOffInfo.Companion.a()` parses the same layout on notify.

### 3.4 Delay-start / reservation (ice maker) — opcode 0x23 (`DelayStartInfo`)
Notify/echo payload (`DelayStartInfo.b`):
`[0]=enabled` · `[1..2]=duration(16-bit BE)` · `[3..6]=epoch-seconds(32-bit BE)`
target start time · `[7]=ice-size mode`. App derives start hour/min from the
epoch. enabled→WorkStatus.RESERVATION.

### 3.5 Do-not-disturb — opcode 0x16 (`NotDisturbControllerV1`)
Payload: `[enable][startHour][startMin][endHour][endMin][forever]`.
Parse: bytes[1..4] all-0xFF (signedInt == -1) ⇒ full-day 00:00–23:59;
byte[5]=forever flag.

### 3.6 Clean / wash reminder — opcode 0x27
- `CleanReminderController.q()`: `[openInt][setCleanHour]` (openInt 0/1/2; 2 =
  "reset, remain=setHour"). proType may switch to secure (0x3A/0xAA) per flag.
- `WashRemindController` (commandType **hard-coded 39=0x27**): byte[0] =
  `2` (reset) or enable(0/1); then 2-byte interval (`BleUtils.C`).

### 3.7 Indicator light 0x18 / UV-C lamp 0x1A
Single-value payload `[value]`; parse reads byte[0]. (`IndicatorLightController`,
`LightUVCController`.)

### 3.8 Water-box / accent RGB light — opcode 0x1B
`LightSwitchH717DActionParser.x`: `1B 01 01 <isWaterBoxLight>` (on); the H7160
side decodes the same opcode as `LightRgbData` (RGB accent on the humidifier).

### 3.9 Sync time — opcode 0xB5 (`SyncTimeController`)
Payload (7 B): `[epoch-seconds 32-bit BE][0x01][tzHourOffset][tzMinuteOffset]`.

### 3.10 Function switches (Lock/Shake/Rewu/TempUnit) — opcode 0x1F
Write `q()`: `[subByte][value]` (subByte per §2.2, value `N()`/`M()`).
Read `p()`: `[subByte]`. Notify parsed by `BaseSwitchControllerKt
.parseCommSwitchInfo` (H7172) — byte[1] (or byte[7] for unit) holds state.

---

## 4. Status / notify parsing

Both BLE notifies and IoT `pt`-passthrough frames are dispatched by opcode
(byte[1]) through the same parsers (`CmdStatusParseV1`). IoT `state.onOff==1`
gives top-level power.

### 4.1 Humidifier H7160 (`h7160/iot/CmdStatusParseV1.a`)
Dispatch on byte[1]:
| Opcode | Meaning | Payload notes |
|---|---|---|
| `d0()`=0x05 | mode change | → `ParseModeEvent` (GEAR/AUTO/CUSTOM as §3.2) |
| `k1()`=0x13 | timer group entry | `TimerInfoV2.parseBytes` (group index in frame) |
| `j1()`=0x12 | timer clear | byte0==0 ⇒ clear all timers |
| `F()`=0x11 | delay-off | `DelayOffInfo` |
| `b0()`=0x1B | accent light RGB | `LightRgbData.b` |
| `J0()`=0x16 | do-not-disturb | `NotDisturbInfo` |
| `w()`=0x17 | **work-status / water** | byte0=clear-72h flag; byte1=water-shortage(1); byte2 work-state (1 or 2 → 1/2 else 0) |
| `A()`=0x08 | thermometer pair | bytes2..7 = probe MAC (0 ⇒ unbind) |
| `P()`=0x10 | thermometer reading | byte0=valid; bytes1..3 = signed temp ×; byte4 = humidity/index |

### 4.2 Ice maker H7172 (`h7172/iot/CmdStatusParseV1`)
| Opcode | Method | Meaning |
|---|---|---|
| `O()`=0x19 | `g()`/`d()` | **Work-status** byte0 → `WorkStatus` (see §4.3) |
| `d0()`=0x05 (read `AA`) | `c()` | current ice-size `Mode` (byte2) |
| `I()`=0x23 | `f()` | delay-start/reservation (§3.4) |
| `w()`=0x17 | `a()` | **abnormal/fault** → `AbnormalInfoControllerKt.parseAbnormalInfo` |
| `D()`=0x1F | `h()` | function-switch state → `parseCommSwitchInfo` |

### 4.3 Ice-maker work-status enums
**H7172** (`WorkStatus`, value from `BleProtocolConstants`):
IDLE=`y1()`=0, ICE_MAKING=`x1()`=1, ICE_MAKE_FINISH=`w1()`=2,
WASHING=`A1()`=3, WASH_FINISH=`B1()`=4, RESERVATION=`z1()`=5.

**H7178** (`H7178WorkStatus`, literal bytes — superset):
0 IDLE · 1 ICE_MAKING · 2 ICE_MAKE_FINISH · 3 RESERVATION · 4 WASHING ·
5/6/7 DEFROST_1/2/3 · 8 WASH_FINISH · 9 SINGLE_ICE · 10 CYCLE_ICE ·
11 SINGLE_ICE_FULL · 12 CYCLE_ICE_FULL. (`H7178DeviceState`:
ice-full states = {5,6,7}; "working" set = {1,9,10}.)

### 4.4 Fault / abnormal
H7172 fault frames arrive under **opcode 0x17** (`w()`); decoded by
`com.govee.h7172.ble.controller.AbnormalInfoControllerKt.parseAbnormalInfo`
into `DeviceAbnormalState` (e.g. no-water, full-ice, high-temp protect — see
`ConsV1Expand` keys `no_water`, `full_ice`, `high_temperature_protected`).
H7160 surfaces water-shortage / high-temp via the 0x17 work-status frame
(§4.1) and `intent_ac_water_leak_open`.

---

## 5. Broadcast formats

These appliances broadcast mainly for **discovery** (BLE name + Govee mfr data);
they do **not** publish full operating state in the advert — `BleBroadcastProcessor`
(`pact_h7160/add`) only matches SKU+protocol to open the connect dialog. Live
state requires a BLE connection (or the Wi-Fi/IoT path).

### 5.1 H5140 CO₂ monitor — broadcast-only (`H5140ThBroadParseImp`)
Manufacturer advert, AD structure key **11** (`0x0B`), data length 11:
- `[0]` == 0xFF marker
- `[5][6][7]` = packed temp+humidity → `BleUtil.parseThValue` ⇒ `[temp,humidity]`
- `[8][9]` = **CO₂ ppm**, big-endian uint16 (`(b8<<8)|b9`); validated by
  `WidgetTemHumModel.isValidCo2`, else -1.

No BLE write/control path for H5140 in this build — read-only sensor.

---

## 6. Mis-tagged light SKUs (reuse base2light common set)

### 6.1 H7022 String Light (`com.govee.h7022`)
Standard base2light light: on/off 0x01, brightness 0x04, mode 0x05.
Device-specific sub-modes (`h7022/ble/BleProtocol`): **color=0x0B**,
**scenes=0x09**, **music=0x01** (music sub-values: soft=4, power=5).
Scene values (illumination0, fade1, raindrops2, colorful3, marquee4, blinking5,
snow6, sky7).
- **Multi-scene** uses multi-packet opcode `1` (`ScenesModeController.g`):
  payload `[code][effectType][subEffectType][speed][colorCount][colors…]`
  (3 bytes/color).
- **Bulb color read** opcode `0xA2` (-94, `ReadBulbColorController`): paged read,
  `p()=[page]`; reply `[page][4×RGB(3B each)]`, paged until `bulbNum` covered
  (24 bulbs max). `SINGLE_BULB_NUM` opcode = 0x0F.

### 6.2 H7017 Plant Grow Light (`com.govee.h7017`)
Standard base2light light + one device-specific opcode:
**Red/Blue proportion = 0x0D** (`RedBlueController`): write `q()=[red,blue]`
(two unsigned 0‑255 ratio bytes); notify parses the same two bytes.

---

## 7. Confidence & open questions

- **High confidence:** opcode table defaults (read directly from
  `BleProtocolConstants` fields), switch/mode/ice-size/delay-off/delay-start/
  do-not-disturb/sync-time payloads, H7172/H7178 work-status enums, H5140
  broadcast, h7022/h7017 light deviations.
- **Medium:** thermometer-probe opcodes `A()`=0x08 / `P()`=0x10 (external probe
  paired to H7160 — value derived from getter→field default, not seen on wire).
- **Open questions:**
  - **Kettle/heater target temperature scaling** — encoded as the `<mode>`/
    `<gear>` value under opcode 0x05, but the °C↔byte mapping lives in the
    per-SKU `EcologyModeCons`/spec JSON, not extractable from these classes.
  - Whether any shipping SKU actually rewrites the `BleProtocolConstants`
    singleton at runtime (no bulk reassignment found; assumed defaults).
  - `.c()` vs `.d()` builder distinction (standard 0x33 vs secure/multi-sync
    0x3A) inferred from `proType` getters, not byte-traced here.
  - Newer ice/ice-cream makers (H8120/8121/8122/8131, H8102) reuse the same
    `eco` Mode/Switch parsers but may have extra mode params not enumerated.
