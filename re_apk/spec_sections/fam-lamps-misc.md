# Family: Lamps & misc light forms (`fam-lamps-misc`)

Covers the lamp / car-light / outdoor-strip / sync-box modules:
`tablelampv1`, `carlightv1`, `barelightv1`, `homelightv1`, `h1162` (+`h1168`),
`h6630`, `pickupbox`. All are decoded from
`re_apk/decompiled/base/sources/com/govee/<module>/...`.

These all ride the **standard 20-byte frame** (`[type][opcode][payload..][BCC]`) and the
common `base2light` command set (on/off `0x01`, brightness `0x04`, mode `0x05` with a
sub-mode selector at `byte[2]`, multi-packet `0xA1/0xA2`, notify `0xEE`). `ModeController`
in every lamp/strip module `extends AbsModeController`, whose `getCommandType()` returns
**`0x05`** (`base2light/ble/controller/AbsModeController`), so every mode frame below is:

```
33 05 <selector> <sub-payload...> 00.. BCC
```

The **selector** byte is the sub-mode's `subModeCommandType()`. This doc records the
device-SPECIFIC sub-payload byte layouts and the families that deviate from the common set.
The two **sync boxes** (`h1162`, `pickupbox`) are *not* lights — they are BLE relays that
drive groups of external Govee devices, and they use a wholly different opcode set.

jadx prints signed bytes; convert via `(v & 0xFF)`. `getSignedBytesFor2(v, littleEndian?)`
returns a 2-byte split; `getSignedShort(hi,lo)` reads back. Color helpers:
`ColorUtils.getRgb(argb)` → `[R,G,B]`.

---

## 1. goodsType / SKU coverage

| Module | goodsType | SKUs (from `_sku_catalog.md`) | Default name | BLE? |
|---|---|---|---|---|
| `tablelampv1` | 22 | **H6052** | Aura Table Lamp | BLE |
| `tablelampv1` | 128 | **H6078** | Cylinder Floor Lamp | BLE+WiFi |
| `carlightv1` | 6 | **H6118, H6194** | Car / Motorcycle LED Lights | BLE (groupable) |
| `barelightv1` | 13 | **H6145, H6146, H6147, H6171** | RGBIC / Outdoor Strip Lights | BLE |
| `homelightv1` | 16 | **H6148** | RGBWW Strip Lights | BLE+WiFi |
| `h1162` | 87,137,182,186 | **H1162, H1163, H1167, H1168** | Music Sync Box / Light Show Box | BLE+WiFi sync box |
| `pickupbox` | 32 | **H1161** | Govee Sync (pickup box) | BLE sync box |
| `h6630` | — (UI only) | H6078 DIY-graffiti UI; no own goodsType | — | shares H6078 |

Sources: `*/pact/Support.java` (`pact.b(goodsType, …)` registrations);
`tablelampv1/pact/Support.getDefDeviceName` ("RGBICWW Floor Lamp" for 128);
`homelightv1/pact/Support` (`{16}`); `carlightv1/pact/Support` (`{6}`);
`barelightv1/pact/Support` (`{13}`, const `f29016e="H6171"`).

H6052 vs H6078 are split in `tablelampv1` by `Support.isH6078(gt)==(gt==128)`. H6078 has a
**v2** sub-mode set (`ble/v2/*`); H6052 uses the **v1** set (`ble/*`).

---

## 2. Floor/table/strip lamps — shared "lamp" sub-mode set

`tablelampv1` (v1), `carlightv1`, `homelightv1` all use the **same** color/scene/diy
layouts; only music differs slightly. `barelightv1` replaces color with a **segment**
layout (§5). The mode-selector dispatch is in each module's `ble/Mode.java#parseSubMode`.

### 2.1 Sub-mode selector map (`byte[2]`)

| Selector hex | Sub-mode | tablelamp v1 | carlight | homelight | barelight |
|---|---|---|---|---|---|
| `0x0D` (13) | Color (RGB+CT+tint) | ✓ | ✓ | ✓ | — |
| `0x0B` (11) | Color (RGB + segment mask) | — | — | — | ✓ legacy |
| `0x15` (21) | Color V2 (segment + CT + per-seg brightness) | — | — | — | ✓ |
| `0x04` (4)  | Scenes | ✓ | ✓ | ✓ | ✓ |
| `0x0A` (10) | New DIY (code ref) | ✓ | ✓ | ✓ | ✓ |
| `0x0F` (15) | Music v1 | ✓ | — | ✓ | — |
| `0x0E` (14) | Music v1 | — | ✓ | — | — |
| `0x0C` (12) | Music (`ParamsSubMode4Music` → v1/v2) | — | — | — | ✓ |
| `0x13` (19) | Music v2 | ✓ (H6078) | ✓ | — | ✓ |
| `0x14` (20) | Gradual-change toggle (own opcode, not mode) | — | — | — | ✓ |

### 2.2 Color sub-mode `0x0D` — RGB + colour-temp + white-tint (9 bytes)

`tablelampv1/ble/SubModeColor.getWriteBytes`, identical in
`carlightv1/ble/SubModeColor`, `homelightv1/ble/SubModeColor`,
`tablelampv1/ble/v2/SubModeColorV2`:

```
[0]=0x0D  [1..3]=R,G,B  [4..5]=Kelvin (big-endian, getSignedBytesFor2(k,true))  [6..8]=tintR,tintG,tintB
```

- Pure RGB → set `[1..3]`, Kelvin `=0`, tint `=0`.
- Colour-temp → RGB = white sentinel, `[4..5]` = Kelvin, `[6..8]` = `getTemColorByKelvin(k)[2]`
  (the warm/cool tint RGB). `parse()` reads `getSignedShort(b[3],b[4])` as Kelvin.
- H6078 clamps Kelvin to **2200..6500** (`Support.getColorTemKelvinRange` /
  `getInvalidKelvinH6078`); H6052 colorSize=2, H6078 colorSize=1
  (`Support.getColorSize`).

### 2.3 Scenes `0x04` & New-DIY `0x0A` — 3-byte (little-endian id)

`SubModeScenes`/`SubModeNewDiy` in every module:
```
[0]=selector  [1..2]=getSignedBytesFor2(id, false)   // little-endian: [low, high]
```
`parse()` = `getSignedShort(b[1], b[0])`. Scenes id is the cloud scene code; DIY id is the
stored `diyCode`. The DIY *content* (per-pixel frames) is uploaded separately via the
multi-packet `0xA1` path; `0x0A` only selects an already-loaded effect slot.
Scene-op capability set: `tablelampv1/Support.supportScenesOpSet` → H6078 `{0,1,5,9}`, else
`{0,1,4,5}`.

### 2.4 Music v1 — `tablelamp 0x0F`, `homelight 0x0F`, `car 0x0E`

`tablelampv1/ble/SubModeMusic.getWriteBytes` (selector `0x0F`):
```
type != 4:  [0]=0x0F [1]=type [2]=sensitivity(0..99) [3]=autoColorFlag [4..6]=R,G,B
type == 4:  [0]=0x0F [1]=type [2]=sensitivity        [3]=mode(0/1) [4]=autoColorFlag [5..7]=R,G,B
```
`autoColorFlag`: `byte = !auto ? 1 : 0` → **0 = device auto-colour (no RGB sent), 1 = manual RGB
follows**. `type` analytic map: 0=Energic, 4=Rhythm, 7=…(see `ModeStr`). `homelightv1` is
byte-identical at `0x0F`.

`carlightv1/ble/SubModeMusic` (selector `0x0E`):
```
auto:   [0]=0x0E [1]=type [2]=sensitivity [3]=0
manual: [0]=0x0E [1]=type [2]=sensitivity [3]=1 [4..6]=R,G,B
```
(`a(z5) = z5?0:1`; `f100431d` is the "auto" flag.)

### 2.5 Music v2 — selector `0x13`

- **H6078** (`tablelampv1/ble/v2/SubModeMusicV2`): minimal `[0]=0x13 [1]=musicCode [2]=sensitivity`.
  Default musicCode `105`. `IMusicEffectStatic.parseSubStr4New(code)` names it.
- **carlight** (`carlightv1/ble/SubModeMusicV2`):
  `[0]=0x13 [1]=type [2]=sensitivity [3]=f100438c(mode,0) [4]=(!auto?1:0) [5..7]=R,G,B`.
- **barelight** (`barelightv1/ble/SubModeMusicV2`): selector `0x0C` not `0x13` (see §5.4).

---

## 3. carlightv1 specifics (H6118 / H6194)

- Same color(`0x0D`)/scene(`0x04`)/diy(`0x0A`) as the lamps; music at `0x0E` (v1) / `0x13` (v2).
  `ble/Mode.java#parseSubMode`: 14→music, 4→scenes, 10→newdiy, else→color.
- **Grouping:** `ble/GroupBle extends AbsGroupBle`, `ble/BleCommGroup extends AbsBleCommGroup`
  — broadcasts identical frames to a group of paired car lights over BLE; no new wire format.
- **Rhythm / smart-scene builders** (`scenes/Rhythm*UI.java`, `scenes/RhythmBuilder.java`):
  these are *automation* composers for the "rhythm" smart-scene feature; they emit the
  **standard** switch/brightness/color/colorTem builder frames
  (`scenes/Ble{Switch,Brightness,Color,ColorTem}CmdBuilderV1`), not a car-specific opcode.
  `RhythmBuilder.supportFuc` gates on goodsType ∈ `{6}`.

---

## 4. homelightv1 specifics (H6148, RGBWW strip)

Pure common-set reuse — color/scene/music/diy selectors `0x0D / 0x04 / 0x0F / 0x0A`
(byte-identical to tablelamp v1). The only family-specific surface is **WiFi + IoT**:

- `ble/WifiNotifyParse.java` parses the device's Wi-Fi provisioning notify (BLE side).
- `iot/Cmd*.java` define the cloud `pt`-passthrough mirror of the BLE frames:
  `CmdTurn` (on/off), `CmdBrightness`, `CmdColor`, `CmdColorTem`, `CmdColorWc`,
  `CmdStatus`/`CmdStatusV0` (status query), `CmdPt` (raw passthrough), `ResultPt`.
  Payloads equal the BLE frames per the global "pt == BLE" rule. No new byte layout.
- `newdetail/mode/H6148OldMusicMode` drives the `0x0F` music sub-mode for older firmware.

H6148 has no segment/colour-V2 path (unlike barelight) — it is a single-zone RGBWW strip.

---

## 5. barelightv1 specifics (H6145/6/7, H6171 — RGBIC / Outdoor strips)

The interesting family: **15-segment addressable** strips. `ble/Mode.java#parseSubMode`:
`12→music(ParamsSubMode4Music)`, `4→scenes`, `10→newdiy`, `21→ColorV2`, else→`Color(0x0B)`.
A second mode wrapper `ble/Mode4ColorStrip` carries a `boolean f28943a` "last segment write"
flag used to chain multi-segment writes (last write also triggers gradual transition).

### 5.1 Legacy color `0x0B` (8 bytes) — single colour + segment mask

`barelightv1/ble/SubModeColor.getWriteBytes`:
```
[0]=0x0B  [1..3]=R,G,B  [4]=segMaskLow(seg0..7)  [5]=segMaskHigh(seg8..14)
```
Segment selection is a 15-bit mask packed LSB-first across two bytes (`boolean[15]`). To
paint a multi-colour pattern the app emits one `0x0B` frame *per distinct colour*, each with
its own mask (grouping built in the static `makeSubModeColor(int[15],…)`).

### 5.2 Color V2 `0x15` (17 bytes) — colour / CT / per-segment brightness

`barelightv1/ble/SubModeColorV2.getWriteBytes`, `byte[1]` selects the operation:

| `byte[1]` | Meaning | Layout |
|---|---|---|
| `1` | RGB(+optional CT tint) on a segment set | `[2..4]=R,G,B`; if Kelvin≠0 `[5..6]=Kelvin(BE)` `[7..9]=tintRGB`; `[10]=segMaskLow` `[11]=segMaskHigh` |
| `2` | Set a whole-strip preset index on a segment set | `[2]=index(f28972f)` `[3]=segMaskLow` `[4]=segMaskHigh` |
| `3` | Per-segment brightness | `[2..16]=brightness[seg0..14]` (15 bytes) |

Same 15-bit LSB-first mask convention as §5.1. `makeSubModeColorByKelvin` uses op `1` with
RGB=white sentinel.

### 5.3 Gradual-change controller `0x14` (own opcode)

`barelightv1/ble/GradualController` — NOT a mode sub-byte; a standalone single controller,
`getCommandType()=0x14` (20), payload `q()=[flag]` (1 byte: `1`=enable gradual, `0`=off).
Notify → `EventGradualChange`. Emitted as the trailing controller of a multi-segment colour
batch (`makeSubModeColor(…, gradual)` appends a `GradualController`).

### 5.4 Music `0x0C` (v1 + v2 share the selector)

`ParamsSubMode4Music.subModeCommandType()=0x0C`; on parse it forks to `SubModeMusic` or
`SubModeMusicV2` by a firmware param (`a(int)` → 1 = v2). Both write under `0x0C`:
- v1 (`barelightv1/ble/SubModeMusic`): `type==0`: `[0]=0x0C [1]=type [2]=sens`;
  `type==5`: `[0]=0x0C [1]=type [2]=sens [3]=(!f28980c?1:0) [4]=autoFlag [5..7]=RGB`;
  else: `[0]=0x0C [1]=type [2]=sens [3]=autoFlag [4..6]=RGB`.
- v2 (`barelightv1/ble/SubModeMusicV2`): mode 0 → `[0]=0x0C [1]=type [2]=sens`; mode 5 →
  8 bytes `[…][3]=(!e?1:0)[4]=autoFlag[5..7]=RGB`; else 7 bytes `[…][3]=autoFlag[4..6]=RGB`.
  `autoFlag`: `!auto ? 1 : 0` (0 = device auto-colour).

---

## 6. Sync boxes — `h1162` & `pickupbox` (NOT lights)

These boxes pair to N **external** Govee light devices and orchestrate them (music-reactive
multi-device shows). They expose a dedicated opcode set declared identically in
`h1162/ble/BleProtocol.java` and `pickupbox/ble/BleProtocol.java`:

| Const | Hex | Role |
|---|---|---|
| `single_open` | `0x10` | box on/off (write+read) |
| `single_brightness` | `0x11` | box brightness |
| `notify_brightness` | `0x20` | brightness notify |
| `sub_mode_color` | `0x14` | color sub-mode selector |
| `sub_mode_music` | `0x0F` | music sub-mode (v1) |
| `sub_mode_music_new` | `0x13` | music sub-mode (v2) |
| `value_device_num` / `value_connect_status_notify` | `0x40` | # paired sub-devices (read) / connect-status notify |
| `value_multiple_set_music` / `value_device_info` | `0x41` | multi-device music push (write) / per-device info (read) |
| `value_clear_device` | `0x42` | clear all paired sub-devices |
| `value_op_device` | `0x43` | turn one sub-device on/off |
| `value_setting_device` | `0x30` | device-setting frame base |
| `value_device_flag_4_ble_address` / `_name` | `0`/`1` | sub-device info kind selector |
| music sub-effects `single_value_sub_*` | `0x30..0x36` | rhythm `0x30`, zhanfang/bloom `0x31`, cuican/sparkle `0x32`, bolang/wave `0x33`, jiepai/beat `0x34`, pinpu/spectrum `0x35`, gundong/scroll `0x36` |
| `value_sub_mode_music_soft`/`_power` | `0`/`1` | music style flag |
| `value_music_mode_rhythm` | `4` | music-mode = rhythm |

### 6.1 pickupbox (H1161) — verified controller payloads

(`pickupbox/ble/*Controller.java`; type byte `0x33` write / `0xAA` read.)

| Opcode | Class | Write payload `q()` | Read/notify parse |
|---|---|---|---|
| `0x10` | `OpenController` | `[0x10][flag]` | reply `[0]==1` → on |
| `0x11` | `BrightnessController` | `[0x11][value]` | reply `[0]`=brightness |
| `0x40` | `DeviceNumController` | read | reply `[0]`=count (`<0`→fail) |
| `0x40` | `DeviceStatusNotifyParse` | — | notify, 5-byte status block → `EventDeviceStatus` |
| `0x41` | `DeviceInfoController` (read) | per-index | see §6.2 |
| `0x41` | `MultiMusicController` (write, `0xA1` multi) | see §6.3 | — |
| `0x42` | `ClearDeviceController` | clear | ack |
| `0x43` | `OpDeviceController` | `[idx][op]` (2 bytes) | ack |

### 6.2 `0x41` read — `DeviceInfoController.parseValidBytes`

```
[0]=pos (sub-device index)   [1]=flag
flag==0 (address):  [2..7]=6-byte BLE MAC (toAddressBytes, LSB order=false)  [8]=int (type/slot)
flag==1 (name):     [2]=nameLen L  [3..3+L]=ASCII name  [3+L]=int (type/slot)
```

### 6.3 `0x41` write — `MultiMusicController` (multi-packet `0xA1`)

`pickupbox/ble/MultiMusicController`: payload `g()` =
```
[0]=musicMode byte   [1]=N (#devices)   [2..]=R,G,B repeated N times (3*N bytes)
```
Pushes a music effect + per-device colour list across N paired devices in one bulk write.
Backed by `pickupbox/adjust/v2/SubModeMusicV2` (selector `0x13`):
`[0]=0x13 [1]=musicCode [2]=sensitivity [3]=autoFlag(1/0) [4..7]=0`.

### 6.4 h1162 (H1162/63/67/68) vs pickupbox

`h1162` is the newer sync box and runs through the **pact** `base2light` framework
(`adjust/v1/{FrameV1,BlePactV1,UiV1,BleOpV1}`); its on/off path uses the common
`SwitchController` (`0x01`) via `BleOpV1.onEventSwitch`, while `pickupbox` (older H1161)
uses its own `OpenController` (`0x10`). Both declare the same `BleProtocol` opcode interface
(`0x10/0x11/0x40-0x43`, music sub-effects `0x30-0x36`). `h1162` adds an **AI/DSP** path
(`Support.otaType4Ai`, `EventDspVersion`, battery in `HeartControllerWithBattery`) and a
Wi-Fi/cloud REST sync layer (`adjust/net/*`, `H1162StatusRequest/Response`). `DeviceNumController`
(`0x40`) is the verified BLE read on h1162. SmartRoom scene bytes are mostly stubbed
(`SmartRoomOp4H1162` returns empty arrays for color/CT/brightness; only `switch`/`heart`
emit standard controller frames). Sub-device pairing/music orchestration mirrors pickupbox.

---

## 7. h6630 — UI only

`h6630/detail/diy/advance/H6078ProGraffitiEffect` is a Kotlin DIY "graffiti" effect editor
that `extends base2light AbsBasicDiyEffect` and delegates to
`tablelampv1.newAdjust.diy.parse.H6078ProGraffitiParse`. No own goodsType, no own BLE frame
— the produced per-pixel DIY frames are uploaded through the standard multi-packet `0xA1`
DIY path of the H6078 floor lamp. Treat as part of the H6078 (`tablelampv1`/128) surface.

---

## 8. Deviations summary vs common set

- **Lamps (tablelamp/car/home):** color is the combined **RGB+Kelvin+tint** 9-byte form at
  `0x0D`; everything else common. carlight music at `0x0E`; H6078 music v2 at `0x13`.
- **barelight:** segment model — legacy color `0x0B` (RGB+15-bit mask), color V2 `0x15`
  (op 1/2/3 = color/preset/per-seg-brightness), standalone gradual opcode `0x14`, music `0x0C`.
- **Sync boxes:** entirely non-standard opcode block `0x10/0x11/0x40-0x43` + music sub-effects
  `0x30-0x36`; they relay/orchestrate external devices rather than emit light themselves.
- **h6630:** UI-only, no protocol.

---

## 9. Confidence & open questions

- Byte layouts in §2–§6.3 are read directly from `getWriteBytes`/`q()`/`parse` — **high**.
- The music `type`/`musicCode` enumerations (which integer = which named effect) come from
  `ModeStr`/`IMusicEffectStatic` lookup tables not fully expanded here — **medium**; the
  frame *shape* is certain, the *meaning of the code* is partial.
- `DeviceInfoController` `[8]`/`[3+L]` trailing int is logged but its semantic (slot vs type
  vs online flag) is unconfirmed — **flagged**.
- h1162 `single_open=0x10` is declared in `BleProtocol` but the verified switch path uses the
  common `0x01` `SwitchController`; whether any h1162 firmware actually accepts `0x10` is
  **uncertain** (pickupbox H1161 `0x10` is verified).
- `DeviceStatusNotifyParse` 5-byte status block fields not decoded — **flagged**.
