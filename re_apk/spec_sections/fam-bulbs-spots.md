# Family: Bulbs & spotlights — h61xx device packages (`fam-bulbs-spots`)

Scope: the `com.govee.h6101 / h6102 / h6104 / h6105 / h6113 / h6114 / h6119 / h6127 /
h6129` "adjust/detail" packages. Despite the assignment name ("bulbs & spotlights"),
the SKU catalog classifies these as **TV backlights, LED strips, and car lights**
(see catalog table below) — they are connectable RGB(IC) lights, not the relay plugs.
All are **BLE-controllable** (connection-oriented GATT); none are broadcast-only.

Each package is a thin device-specific layer on the **base2light common command set**
(on/off `0x01`, brightness `0x04`, mode `0x05`, etc. — documented in the master ref).
What is device-specific here is (a) which **mode sub-selectors** the device accepts and
(b) a handful of **extra opcodes** (calibration, brightness-limit, gradual-change, IP,
direction, bulb-string group color). Everything below is read from actual byte arrays in
`getWriteBytes()` / `parse()` / `q()` / `p()`; jadx signed decimals converted via `&0xFF`.

## SKU → package → catalog category

| SKU | Package | goodsType (catalog) | Catalog category |
|---|---|---|---|
| H6101 | `h6101` | 0 | TV Backlight (Discontinued) |
| H6102 | `h6102` | 0 | LED Strip Light |
| H6104 | `h6104` | 0 | TV Backlight (Discontinued) |
| H6105 | `h6105` | 0 | TV Backlight (Discontinued) |
| H6113 | `h6113` | 0 | Car Light (Discontinued) |
| H6114 | `h6114` | 0 | Car Light |
| H6119 | `h6119` | 0 | Car LED Lights |
| H6107, H6116, H6127, H6161 | `h6127` | 0/50/30 | Strip Light |
| H6129 | `h6129` | 0 | Strip Light |

(goodsType shows 0 placeholder in the catalog rows; the SKU strings come from each
`sku/Sku*.java` / `sku/Support.java`. The `h6127` package is multi-SKU: it registers
`SkuH6107`, `SkuH6116`, `SkuH6127`, `SkuH6161`.)

## Frame recap (how sub-modes ride the mode opcode)

Mode command = type `0x33`(write)/`0xAA`(read), **opcode `0x05`**
(`AbsModeController.getCommandType()=5`). The selected `ISubMode.getWriteBytes()` produces
a byte array whose **first byte is the sub-mode selector** (`subModeCommandType()`); that
array becomes the mode payload, so on the wire:

```
33 05 <selector> <subpayload …> 00 … 00 BCC
byte: 0  1   2        3 …
```

`AbsMode.parseSubMode(byte selector, byte[] payload)` (per-package `Mode.java`) dispatches
the **inbound** notify by `byte[2]`. Note the **parse selector and the write selector can
differ for "color"**: every package's color sub-mode writes selector `0x02` but parses as
the `default`/`else` branch.

## Per-device mode sub-selector map

Source: each `ble/Mode.java` (`parseSubMode`) + `ble/BleProtocol.java` constants.

| Package | color | music | scenes | newDIY | oldDIY | video | colorV2 | other |
|---|---|---|---|---|---|---|---|---|
| h6101 | 2 (default) | 1 | – | – | – | 0 | – | calibration |
| h6102 | 2 (default) | 1 | 4 | 10 | – | – | 11¹ | limit, gradual-wifi |
| h6104 | 2 (default) | 1 | 4 | 10 | – | 0 | – | IP, direction |
| h6105 | 2 (default) | 3 | 4 | 10 | – | – | – | limit |
| h6113 | 2 (default) | 3 | – | 10 | – | – | – | – |
| h6114 | 2 (default) | 3 | 4 | 10 | – | – | – | – |
| h6119 | 2 (default) | 12 | 4 | 10 | – | – | 21 | gradual-ble, bulb-string |
| h6127 | 2 (default) | 1 / 3² | 4 | 10 | 7 | – | – | – |
| h6129 | 2 (default) | 3 | 4 | 10 | 7 | – | – | – |

¹ h6102 declares `sub_mode_color_v2 = 11` but `parseSubMode` has no branch for it (only
color default) — likely vestigial.
² h6127 has TWO music sub-modes: `0x01` (`SubModeMusic`, IC strips) and `0x03`
(`SubModeMusicV1` / `sub_mode_music_no_ic`).

## Sub-mode byte layouts (payload AFTER the `33 05` header; offsets are within the frame)

### Color — selector `0x02` (ALL nine packages, byte-identical)
`getWriteBytes()` / `parse()` in every `SubModeColor.java`:

| off (frame) | bytes | meaning |
|---|---|---|
| [2] | `02` | selector |
| [3..5] | R G B | static color (8-bit each) |
| [6] | ctFlag | `!=0` ⇒ color-temperature mode active |
| [7..9] | R G B | color-temperature white-point RGB (derived from Kelvin app-side) |

`h6101`, `h6102`, `h6113` only expose `createSubModeColorByColor()` (no colour-temp
factory) but still emit the ctFlag/ctRGB bytes (flag=0). `h6104/h6105/h6114/h6119/h6127/h6129`
add `makeSubModeColorByColorTem(int)` → ctFlag=1, RGB=white-point. No segment data here.

### Music
Three encodings exist:

**selector `0x01`** (`SubModeMusic` in h6101, h6102, h6127):
`[2]=01, [3]=modeByte, [4]=sensitivity`, and **only when auto-colour is OFF** (`g()`):
`[5..7]=R G B`. `modeByte` enum (`value_sub_mode_music_*`): energic=0, spectrum=1,
rolling=2, rhythm=3.

**selector `0x03`** (`SubModeMusic` in h6105/h6113/h6114/h6129, and `SubModeMusicV1` in h6127):
`[2]=03, [3]=autoFlag, [4]=sensitivity(0..99)`, then **when not auto** `[5..7]=R G B`.
`autoFlag = a(z)`: `z(auto-colour on)→0`, off→1. On parse `bArr[0]==0 ⇒ auto`.

**selector `0x0C`** (`SubModeMusic` in h6119) — variant by `byte[3]` music-type:
- type `1`: `[2]=0C [3]=01 [4]=sens [5]=extra`
- type `2`: `[2]=0C [3]=02 [4]=sens [5]=colorFlag(!auto?0:1) [6..8]=R G B`
- else: `[2]=0C [3]=type [4]=sens`

(h6119 enum: energy=0, rhythm=1 [sub power=0/soft=1], scroll=2.)

### Video — selector `0x00`
**h6101** (`SubModeVideo`): `[2]=00, [3]= dynamic?2:0, [4]= allRegion?0:1`.
Parse: `b3==2 ⇒ dynamic`, `b4==0 ⇒ all`. Enums: video_part=0, video_all=1,
video_soft=0, video_dynamic=2.
**h6104** (`SubModeVideo`): `[2]=00, [3]=00, [4]= allRegion?0:1, [5]=level/saturation`.

### Scenes — selector `0x04` (h6102/h6104/h6105/h6114/h6119/h6127/h6129)
`SubModeScenes.getWriteBytes()` = `[2]=04, [3]=sceneId`. Scene IDs from each
`BleProtocol`: common set gm=0, sunset=1, film=4, dating/date=5, romantic=7, blinking=8,
cl=9, snow=15. h6119 carries an extended set: breath=10, dynamic=16, chase=21, stream=22.

### New DIY — selector `0x0A` (h6102/h6104/h6105/h6113/h6114/h6119/h6127/h6129)
`SubModeNewDiy.getWriteBytes()` = `[2]=0A, [3..4]=diyCode` where
`diyCode = BleUtil.getSignedBytesFor2(code, false)` → 2-byte **big-endian** DIY effect index.

### Old DIY — selector `0x07` (h6127, h6129)
`SubModeOldDiy.getWriteBytes()` = `[2]=07, [3..]=raw diy bytes` (variable-length full effect
payload; normally streamed via the multi-packet `0xA1` path, see `MultipleDiyController`).

### Color V2 / segment — selector `0x15` (h6119 `SubModeColorV2`)
Three sub-encodings, chosen by state in `getWriteBytes()`:
- **per-segment colour** (sub-cmd `01`, `c()`):
  `[2]=15 [3]=01 [4..6]=R G B [7..8]=colorTemp(2B, getSignedBytesFor2(...,true)=little-endian)
  [9..11]=ctRGB [12]=00 [13]=segmentBitmask` (bitmask of 6 segments, bit0=seg0).
- **brightness + segment** (sub-cmd `02`, `b()`):
  `[2]=15 [3]=02 [4]=brightness [5]=segmentBitmask [6]=00`.
- **gradient list** (sub-cmd `03`): `[2]=15 [3]=03 [4..]=color index list` (≤17 bytes).

## Device-specific opcodes (full `0x33`/`0xAA` frames, NOT mode sub-modes)

Source: per-package controller `getCommandType()` + `q()`(write payload)/`p()`(read
payload)/`parseValidBytes()`.

| Opcode (hex) | Dec | Package | Class | Dir | Payload / parse |
|---|---|---|---|---|---|
| `0x08` | 8 | h6101 | `CalibrationController` | write | `q()=null`; INIT/result. `BleProtocol.MSG_TYPE_INIT=8` |
| `0x01` | 1 | h6101 | `CalibrationOkController` | notify | `MSG_TYPE_CALIBRATION_RESULT=1`; ack only |
| `0x0E` | 14 | h6102, h6105 | `LimitController` | r/w | write `q()=[limitByte]`; parse `bArr[0]==1` (brightness-limit / low-power flag). `SINGLE_LIMIT=14` |
| `0x13` | 19 | h6104 | `DirectionController` | r/w | write `q()=[dir]`; parse `dir=bArr[0]` (mount/orientation). `MSG_DIRECTION=19` |
| `0x15` | 21 | h6104 | `IPController` | read | parse: `bArr[0..3]`=IPv4 (`toIpBytes`), `bArr[4..7]`=int (port/handle, big-endian). `MSG_IP=21` (Wi-Fi spotlight) |
| `0x14` | 20 | h6119 | `Gradual4BleController` | r/w | write `q()=[on/off]`; parse `bArr[0]`. `SINGLE_GRADUAL_CHANGE_4_BLE=20` |
| `0xA3` | -93 | h6102 | (gradual, Wi-Fi/multi) | write | `SINGLE_GRADUAL_CHANGE_4_WIFI_BLE=-93` (multi-packet type) |
| `0xA5` | -91 | h6119 | `BulbStringColorController` | read | `p()=[idx]`; parse via `BulbGroupColor.parseBytes`: `[0]`=count, then 3×`[segIdx,R,G,B]` |
| `0xAC` | -92 | h6102 | (color/brightness query) | read | `value_color_brightness=-92` |

### `BulbGroupColor.parseBytes` (h6119 bulb-string)
`bArr[0]` = group/segment count; then for i in 0..2: 4-byte record
`[segIndex, R, G, B]` (starting at offset 1, stride 4) → 3 group colours + indices.

## Multi-packet / shared infrastructure (reused, not device-specific)
- `MultipleDiyController` + `MultipleBleComm` (h6102/h6104/h6105/h6113/h6114/h6119/h6127/h6129):
  DIY effect upload over the standard `0xA1` multi-write framing (master ref §3.3).
  `value_multiple_ble_diy = 2` is the comType used in those A1 packets.
- `EffectOp4Ble` / `AbsEffectOp4Ble` / `SubMaker` / `SubLib` (in each `sku/`): cloud scene/effect
  library plumbing, not wire-format.
- GATT service/char: default `…1910` / `…2b11` (these `Ble` subclasses use the no-arg
  `AbsBle()`; no custom UUIDs observed in the inspected files).

## Notes / uncertainty
- All nine `SubModeColor` classes are byte-identical — strong evidence the colour layout is
  the shared base2light one, just copied per package.
- h6102 `sub_mode_color_v2=11` and `value_color_brightness=0xAC` are declared but I did not
  find a live `getWriteBytes`/controller exercising them in this package (flagged as likely
  vestigial / handled by common code).
- h6104 `IPController` int field at `[4..7]` is parsed as big-endian via `byteToInt(...,true)`;
  semantic (port vs. session id) is inferred, not labelled in source.
- Broadcast/advert parse: none of these packages define a manufacturer-data broadcast parser;
  control is connection-only (consistent with these being connectable lights).
