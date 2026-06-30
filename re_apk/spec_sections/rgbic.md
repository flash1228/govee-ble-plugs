# RGB / RGBIC Light Protocol Survey (`rgbic`)

Scope: `com/govee/rgblight/**`, `com/govee/rgbiclight/**`, `com/govee/dreamcolorlightv1/**`,
`com/govee/dreamcolorlightv2/**`, `com/govee/stringlightv2/**`, plus the shared frame/controller
layer in `com/govee/base2light/ble/controller/**` and `com/govee/base2kt/utils/BleUtils.java`.

This is a **survey of the patterns**, not an enumeration of every effect. The per‑SKU feature
modules (dreamcolorlightv1/v2, stringlightv2, rgblight, rgbiclight) all reuse one common frame
builder, one `Mode`/sub‑mode dispatcher, and one multi‑packet manager. Once those three are
understood, every light SKU is a small set of sub‑mode payload variants on top of them.

All byte values below are given as hex. jadx prints signed decimals; convert with `v & 0xFF`
(e.g. `-93 → 0xA3`, `-95 → 0xA1`, `-94 → 0xA2`, `-86 → 0xAA`, `-18 → 0xEE`).

---

## 1. Single‑command frame (20 bytes)

Built by `BleUtils.Companion.o()` / `.p()` (`com/govee/base2kt/utils/BleUtils.java:975,1000`),
called from `AbsSingleController.f()/g()` via `generate20Bytes()`
(`base2light/ble/controller/AbsSingleController.java`):

```
byte[0]   proType      0x33 write (SINGLE_WRITE) | 0xAA read (SINGLE_READ)
byte[1]   commandType  per-controller (switch/brightness/mode/...)
byte[2..] payload      controller q() (write) or p() (read), zero-padded
byte[19]  BCC          XOR of bytes[0..18]   (BleUtils.v())
```

`AbsSingleController.getProType()` returns `0x33` when `isWrite()` else `0xAA`. On a **read**
the controller emits `p()` as the payload (mode read sends `{0x01}`); the device reply is parsed
by `parseValidBytes()` after stripping `bytes[0..1]` (`AbsSingleController.m()`).

### 1.1 Top-level command types (`byte[1]`)

These are the common light opcodes (`getCommandType()` across `base2light/ble/controller/*`,
constants in `base2light/ble/controller/BleProtocolConstants.java`):

| Name | `byte[1]` | Dir | Payload | Source |
|------|-----------|-----|---------|--------|
| SINGLE_SWITCH / main switch / heart | 0x01 | write/read | `[0]`=on(1)/off(0) | `SwitchController`, `MainSwitchController`, `HeartController` |
| SINGLE_BRIGHTNESS | 0x04 | write/read | `[0]`=brightness (unsigned, device-scaled 0–100/0xFF) | `BrightnessController` |
| SINGLE_MODE | 0x05 | write/read | `[0]`=sub-mode type, `[1..]`=sub-mode bytes | `AbsModeController` |
| SINGLE_DELAY_CLOSE | 0x0B | write | delay payload | `DelayCloseController` |
| SINGLE_SLEEP | 0x11 | write | sleep params | `SleepController` |
| SINGLE_WAKEUP | 0x12 | write | wake params | `WakeUpController` |
| SINGLE_DEVICE_INFO / soft ver | 0x06/0x07 | read | version bytes | `VersionSoftController`, `SnControllerV1` |
| IC_NUM / segment count | 0x40 | write/read | IC segment count | `IcNumController` |
| SINGLE_WRITE_CHECK_IC / refresh | 0x42 | write | IC refresh | `RefreshIcController` |
| CHECK_IC_AMOUNT | 0x43 | write | IC count check | `CheckICAmountController` |
| OTA_PREPARE | 0xEE | write | OTA handshake | `OtaPrepareController` |
| SINGLE_PACT | 0xEF | read | product/pact id | `PactController` |
| READ_SECRET_KEY / CHECK_SECRET_KEY | 0xB1 / 0xB2 | handshake | encryption key exchange | `BleProtocolConstants` |

> Note: NOTIFY frames start `0xEE` (`NOTIFY = -18`). Detail/status notifies use a second
> selector byte: `NOTIFY_DETAIL_LIGHT_STATUS=0x01`, `..._MUSIC=0x04`, `..._BATTERY=0x03`, etc.

---

## 2. Mode + sub-mode dispatch (the core of color / scene / DIY / music)

Almost everything light-specific rides inside **command type `0x05` (SINGLE_MODE)**. The
frame is `33 05 <subModeType> <sub-mode payload...> XOR`. The first payload byte after `0x05`
is the **sub-mode command type**, returned by each sub-mode's `subModeCommandType()`.

`AbsModeController.q()` returns `mode.getWriteBytes()` → `subMode.getWriteBytes()`, whose
`[0]` is the sub-mode type (`base2light/ble/controller/AbsModeController.java`,
`AbsMode.java`). Read dispatch is `Mode.parseSubMode()` /`Mode.parseWriteSubMode()`
(e.g. `dreamcolorlightv1/ble/Mode.java`).

### 2.1 Sub-mode command types (`byte[2]`)

From `BleProtocolConstants` plus each `SubMode*.subModeCommandType()`:

| Sub-mode | `byte[2]` | Meaning | Representative source |
|----------|-----------|---------|------------------------|
| `sub_mode_scenes` | 0x04 | apply scene id (single-packet) | `dreamcolorlightv1/ble/SubModeScenes.java` |
| `sub_mode_new_diy` | 0x0A | apply DIY code | `dreamcolorlightv1/ble/SubModeNewDiy.java` |
| color (legacy 15-seg) | 0x0B | RGBIC segment color v1 | `dreamcolorlightv1/ble/SubModeColor.java` |
| color WW (white+temp) | 0x0D | whole-light RGB + color temp | `stringlightv2/ble/SubModeColor4Ww.java`, `SubModeColor.java` |
| `sub_mode_music` | 0x13 | music reactive (v1 variants) | `dreamcolorlightv1/ble/SubModeMusic.java` |
| `sub_mode_color` | 0x15 | RGBIC segment color v2 (+temp/brightness) | `dreamcolorlightv1/ble/SubModeColorV2.java` |
| `sub_mode_abs_music` | 0x16 | unified music (effect + sensitivity) | `base2light/ble/controller/SubModeAbsMusic.java` |
| mic (H6192) | 0x05 | mic on | `stringlightv2/ble/SubModeMicH6192.java` |
| `sub_mode_operate` | 0x20 | operate/cut-cali | `BleProtocolConstants` |
| `sub_mode_operate_V2` | 0x0C | operate v2 | `BleProtocolConstants` |
| `sub_mode_part_scenes` | 0x47 | partial-segment scene | `BleProtocolConstants` |
| `sub_mode_color_multi` | 0x6E | multi color sub | `BleProtocolConstants` |
| `sub_mode_carousel` | 0x82 | carousel | `BleProtocolConstants` |
| `sub_mode_display` | 0x81 | display | `BleProtocolConstants` |
| `SUB_MODE_DAYSYNC` | 0xF0 | day-sync | `BleProtocolConstants` |

---

## 3. Whole-light color & color temperature

### 3.1 Whole-light RGB + color temp — `SubModeColor4Ww` (sub-mode 0x0D)
`stringlightv2/ble/SubModeColor4Ww.getWriteBytes()`:

```
[0] 0x0D            sub-mode type (sub_mode color WW)
[1] R               main RGB red
[2] G               main RGB green
[3] B               main RGB blue
[4] kelvin_hi       color temp kelvin, signed 16-bit BIG-endian (getSignedBytesFor2(k,true))
[5] kelvin_lo
[6] tempR           RGB equivalent of the white point for that kelvin
[7] tempG
[8] tempB
```
Full frame: `33 05 0D RR GG BB Khi Klo tR tG tB 00..00 XOR`. To set a pure RGB color, kelvin=0
and tempRGB=0 (`beRgb()`); to set white at a CCT, main RGB = `ColorUtils.toWhite()` and
kelvin/tempRGB filled (`beTemRgb()`). `stringlightv2/ble/SubModeColor.java` is the same layout
(also sub-mode 0x0D).

> `dreamcolorlightv2/scenes/BleColorCmdBuilderV1.java` /`BleColorTemCmdBuilderV1.java` and the
> `stringlightv2/scenes/*` builders wrap the same sub-mode for rhythm/automation use.

---

## 4. RGBIC segment color

### 4.1 Legacy segment color v1 — `SubModeColor` (sub-mode 0x0B)
`dreamcolorlightv1/ble/SubModeColor.getWriteBytes()` (15 segments, one color per call;
multiple colors → multiple frames, one per distinct color):

```
[0] 0x0B            sub-mode type
[1] R
[2] G
[3] B
[4] segMask 0..7    bit i set → segment i uses this color (LSB = seg0)
[5] segMask 8..14   bits 0..6 → segments 8..14
```
Detection helper `isSetMode2Color()` checks `bArr[0]==0x33 && [1]==0x05 && [2]==0x0B`.

### 4.2 Segment color v2 (+ temp + per-segment brightness) — `SubModeColorV2` (sub-mode 0x15)
`dreamcolorlightv1/ble/SubModeColorV2.getWriteBytes()` — a `byte[17]` payload whose **`[1]` is a
format selector**:

**Format 1 (`[1]=0x01`) — RGB (optionally with color temp) applied to a segment selection:**
```
[0]  0x15           sub-mode type (sub_mode_color)
[1]  0x01           format = solid RGB
[2]  R
[3]  G
[4]  B
[5]  kelvin_hi      color temp, signed 16-bit BIG-endian (0 if pure RGB; getSignedBytesFor2(k,true))
[6]  kelvin_lo
[7]  tempR          white-point RGB for that kelvin (only when kelvin != 0)
[8]  tempG
[9]  tempB
[10..] segment bitmask  BleUtil.makeBytes4SelectPosByOneBit(selectedSegments[])
```

**Format 2 (`[1]=0x02`) — segment selection by stored index:**
```
[0]  0x15
[1]  0x02
[2]  index (f109111f)
[3..] segment bitmask (makeBytes4SelectPosByOneBit)
```

**Format 3 (`[1]=0x03`) — per-segment brightness array:**
```
[0]  0x15
[1]  0x03
[2..N] one brightness byte per segment   (for 18-seg parts: [2]=page 1/2, then 14 brightness bytes)
```

Number of segments (`f109105n`) is 15 or 18 depending on SKU. The notify/read parser
(`parseSubModeColor4Write`, `parsePosColorWithBrightness`) inverts this exactly:
`[0]`=1 → RGB+temp+mask, `[0]`=2 → index+mask, `[3]`=3 → brightness page.

### 4.3 Multi-packet whole-strip color — comType 0x40 (`MULTI_V1_NEW_COLOR`)
`base2light/ble/controller/MultipleColorStripControllerV1.java` (getCommandType `0x40`),
payload built by `AbsMultipleControllerV14ColorStrip` ctor (`g()` returns `f57232k`). This is
sent **multi-packet** (proType `0xA1`, see §7). Payload layout:

```
[0] groupCount                       number of color-groups + brightness-groups
  per color group:  type=0x00, count, R, G, B, pos0, pos1, ... (count position bytes)
  per brightness group: type=0x01, count, brightnessValue, pos0, pos1, ...
```
`MultipleColorTemStripController` / `MultipleGradientColorTemStripController` also use comType
`0x40` for color-temperature strips (gradient variants).

---

## 5. Scene application

### 5.1 Single-packet scene id — `SubModeScenes` (sub-mode 0x04)
`dreamcolorlightv1/ble/SubModeScenes.getWriteBytes()`:
```
[0] 0x04            sub_mode_scenes
[1] scene_lo        scene/effect code, signed 16-bit LITTLE-endian (getSignedBytesFor2(code,false))
[2] scene_hi
```
Full frame: `33 05 04 <lo> <hi> 00..00 XOR`. Read parse: `getSignedShort(bArr[1], bArr[0])`
(note byte order swap → little-endian on the wire).

### 5.2 Multi-packet scene/effect — comType varies (`MULTI_*_NEW_SCENES`)
Richer scenes (with embedded effect blobs, speed, direction, music sub-effects) are sent
multi-packet via `AbsMultipleControllerV14Scenes` (`base2light/ble/controller/`). The
**comType (`byte[1]` of the `0xA1` frame)** selects the scene protocol version:

| comType | Constant | Controller |
|---------|----------|------------|
| 0x01 | `MULTI_V1_NEW_SCENES` | `MultiNewScenesControllerV1` |
| 0x02 | `MULTI_V2_NEW_SCENES` | `MultiNewScenesControllerV2` |
| 0x07 | `MULTI_V3_NEW_SCENES` | `MultiNewScenesControllerV3` |
| 0x0A | `MULTI_V4_NEW_SCENES` | `MultiNewScenesControllerV5` |
| 0x0C | `MULTI_PREVIEW_EFFECT` / scene preview | `MultiNewScenesControllerV6/V7` |
| 0x56 | `MULTI_V1_NEW_DIY_h7033` | `MultiNewScenesControllerV8` |
| 0x58 | `MULTI_CUBE_IN_DIY` / fixed-device | `MultiNewScenesControllerV10`, `MultiDiyFixedDeviceController` |
| 0x5A | `SUB_MODE_SCENE_APPLY_H60B0` | `MultiNewScenesControllerH60B0` |

The multi-packet **payload** for a scene = `AbsMultipleControllerV14Scenes.g()` = the raw
`effectBytes` (`f57242j`) — an opaque per-scene effect blob. Those blobs come from the scene
tables/composers `base2light/ble/scenes/RgbIcScenesV1.java`, `RgbScenesV1.java`,
`base2light/ble/ScenesCompose.java`, keyed by scene id. The controller also carries
`scenesCode`, `direction`, `x`, `y`, `speed`, `musicCode`, `musicSwitch` (setters `D()`–`L()`),
which the higher scene versions append into the effect stream. The scene id itself is `f57241i`.

> For implementation, the practical path is: pick the scene's prebuilt effect byte array
> (downloaded/embedded), and stream it as a comType-`0x01` (or version-appropriate) multi-write.

---

## 6. DIY effects & music / mic modes

### 6.1 DIY apply (single) — `SubModeNewDiy` (sub-mode 0x0A)
`dreamcolorlightv1/ble/SubModeNewDiy.getWriteBytes()`:
```
[0] 0x0A            sub_mode_new_diy
[1] diy_lo          DIY code, signed 16-bit LITTLE-endian
[2] diy_hi
```
Frame `33 05 0A <lo> <hi> ... XOR`. The full DIY *definition* (per-pixel frames) is uploaded
separately via the multi-packet DIY controllers below; this sub-mode just **selects/activates**
a stored DIY code.

### 6.2 DIY upload — multi-packet comTypes
`base2light/ble/controller/`:

| comType | Constant | Controller |
|---------|----------|------------|
| 0x02 | `MULTI_DIY` | `MultipleDiyController`, `MultiDiyTempalteController` |
| 0x04 | `MULTI_V1_NEW_DIY` | `MultipleDiyControllerV1/V2` |
| 0x03 | `MULTI_V1_NEW_DIY_GRAFFITI` | `MultiDiyGraffitiController(V…)` |
| 0x09 | `MULTI_V1_GRAFFITI_MULTI_LAYER` | `MultiDiyGraffitiControllerV1` |
| 0x0A | template v2 | `MultiDiyTempalteControllerV2` |
| 0x01 | RGB DIY template | `MultiDiyTempalteController4Rgb` |
| 0x58/0x59 | `MULTI_CUBE_IN_DIY` / `…_4_70dx` | cube-in-DIY controllers |

Payload = raw DIY/graffiti effect bytes (frames, palette, coordinates) streamed per §7.

### 6.3 Unified music — `SubModeAbsMusic` (sub-mode 0x16)
`base2light/ble/controller/SubModeAbsMusic.getWriteBytes()`:
```
[0] 0x16            sub_mode_abs_music
[1] effect_lo       music effect code, 16-bit LITTLE-endian (ByteUtils.getLowHighBytes)
[2] effect_hi
[3] sensitivity     0..99
```

### 6.4 Legacy music — `SubModeMusic` (sub-mode 0x13, type-dependent layout)
`dreamcolorlightv1/ble/SubModeMusic.getWriteBytes()` — layout depends on the music effect
type in `[1]` (`f109180a`, e.g. 16/17/18/19):
```
[0] 0x13                       sub_mode_music (subModeCommandType()=0x11 for some variants)
[1] musicEffectType            16=energetic, 17=rhythm, 18/19=…
[2] sensitivity                0..99
[3] (type 17) autoColor? inverse flag
[3 or 4] colorMode             0 = use color (autoColor off), 1 = device auto-color
[+1..+3] R,G,B                 present only when a fixed color is chosen (autoColor off)
```
(Exact offsets shift by effect type; types 16/17 differ — see method body. Whole-light color
in music = R,G,B appended; auto-color = flag set and RGB omitted.)

### 6.5 Mic mode — `SubModeMicH6192` (sub-mode 0x05)
`stringlightv2/ble/SubModeMicH6192.getWriteBytes()` → `{0x05}` only (single byte selecting
mic mode; parameters set via related controllers). Frame `33 05 05 00..00 XOR`.

---

## 7. Multi-packet protocol (`0xA1` write / `0xA2` read)

`com/govee/ble/multi/MultiPackageManager.java`. A logical payload `P` (e.g. a scene effect
blob, multi-color strip array, DIY frames) is fragmented into 16-byte chunks and sent as a
START → DATA… → END sequence; each frame is still 20 bytes with an XOR at `[19]`
(`MultiPackageManager.b()` = XOR over `[0..18]`, same as single frames).

```
START : A1 <comType> 00 <packetCount> 00 .. 00  XOR     (byte[2]=0x00 marks start;
                                                         byte[3]=number of 16-byte chunks)
DATA  : A1 <comType> <idx 1..N> <16 data bytes>  XOR     (byte[2]=1-based chunk index)
END   : A1 <comType> FF 00 .. 00                 XOR     (byte[2]=0xFF marks end)
```
Source: `MultiPackageManager` chunking loop (`length/16` packets, last partial padded) and
`c(comType, index, chunk)` builder. ~300 ms inter-packet sleep. `comType` = the multi
controller's `getCommandType()` (see §4.3, §5.2, §6.2). Device ACK is a `0xA1 <comType> <00=fail/!=0=ok>`
`MultiWriteResponse` (`MultiPackageManager.g()`).

Multi-write proType constants (`BleProtocolConstants`): `MULTIPLE_WRITE=0xA1`,
`MULTIPLE_READ=0xA2`, `MULTIPLE_WRITE_V1/MULTI_WRITE=0xA3`, `MULTIPLE_WRITE_V2=0xA4`,
`MTU_MULTIPLE_WRITE=0xA6`, `MULTI_READ_AB=0xAB`, `MULTI_READ_AC=0xAC`.
`AbsMultipleControllerV1.getProType()` returns `0xA3` (the controller-level multi proType);
the on-wire fragmenter in `MultiPackageManager` uses `0xA1`. (Different SKUs route through
either the `0xA1` MultiPackageManager path or the `0xA3` `MULTIPLE_WRITE_V1` controller path.)

---

## 8. Encoding helpers (reference)

- **XOR BCC**: `BleUtils.v(frame,19)` / `MultiPackageManager.b()` = XOR of bytes `[0..18]`.
- **RGB**: `ColorUtils.getRgb(int)` → `[R,G,B]`; `ColorUtils.toColor(r,g,b)` packs back.
- **Color temp kelvin**: `BleUtil.getSignedBytesFor2(kelvin, true)` = **big-endian** 2 bytes.
- **Scene / DIY codes**: `BleUtil.getSignedBytesFor2(code, false)` = **little-endian** 2 bytes;
  music effect via `ByteUtils.getLowHighBytes()` (little-endian).
- **Segment bitmask**: `BleUtil.makeBytes4SelectPosByOneBit(boolean[])` — one bit per segment,
  LSB = lowest segment; read back with `BleUtil.parseBytes4Bit` / `parseBytes4BitReverse`.

---

## 9. Uncertainties / flags

- **Scene effect blobs** (§5.2) are opaque per-scene byte arrays sourced from tables in
  `base2light/ble/scenes/*` (and remote scene definitions). I captured the *container* (comType,
  multi-packet framing, scene id) but did not decode the internal effect-byte grammar — that
  varies per scene version and is largely data, not code.
- **Legacy `SubModeMusic` (0x13)** offsets shift with the music effect type byte; treat the
  per-type layout in §6.4 as indicative — read `SubModeMusic.getWriteBytes()` for the exact
  branch when targeting a specific effect type.
- **`subModeCommandType` collisions**: value `0x0D` is used for both stringlightv2 `SubModeColor`
  and `SubModeColor4Ww`; `0x13`/`0x11` appear across the v1 music sub-modes. The active class is
  chosen by `Mode.parseSubMode()` per SKU — confirm against the specific feature module.
- Encryption (`0xB1`/`0xB2` secret-key handshake) is referenced but out of scope for this section;
  RGB/RGBIC light frames themselves are plaintext in these modules.
