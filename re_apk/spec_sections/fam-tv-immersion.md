# Family: TV / immersion backlights + capture boxes (`fam-tv-immersion`)

Covers the camera/screen-driven immersion light families and the multi-device "feast"
sync boxes. All of these reuse the **base2light common 20-byte frame** (type `0x33`
write / `0xAA` read, opcode at `byte[1]`, BCC = XOR of bytes[0..18]) and the **standard
mode opcode `0x05`** with a sub-mode selector at `byte[2]`. Only the **device-specific
sub-mode byte layouts and the extra opcodes** are documented here; on/off (`0x01`),
brightness (`0x04`), mode (`0x05`), device-info (`0x06/0x07`), time (`0x09`), OTA
(`0xEE`) behave per the master reference.

GATT transport: every module's `ble/Ble.java` extends `com.govee.base2light.ble.AbsBle`
with the **no-arg constructor → default service `…1910` / unified char `…2b11`**. None
override the UUID pair. jadx prints signed bytes; hex via `(v & 0xFF)`.

## Module → SKU → goodsType map

| Module | SKU(s) | goodsType | Product | BLE? | WiFi/cloud passthrough? |
|---|---|---|---|---|---|
| `tvlightv1` | H6179 | 12 | TV Backlights (camera-less) | BLE-controllable | no (BLE-only; no `iot/` pkg) |
| `pact_tvlightv2` | H6198, H6199 | 24 | DreamView T1S / T1 (camera box) | BLE-controllable | yes (`iot/CmdPt` etc.) |
| `pact_tvlightv3` | H6046, H6053, H6056 | 112/23/52 | RGBIC TV Light Bars | BLE-controllable | yes (`iot/`) |
| `pact_tvlightv4` | H6049, H6054 | 25 | DreamView P1S / P1 (camera box) | BLE-controllable | yes (`iot/`) |
| `pickupbox` | H1161 | 32 | Govee Sync box (multi-device music) | BLE-controllable | no (`iot/`-less; cloud only for grouping) |
| `home/.../moviefeast` | (cross-SKU) | — | Movie Feast multi-device director | BLE multi-write | yes |
| `home/.../musicfeast` | (cross-SKU, incl. H1167/H1168) | — | Music Feast multi-device director | BLE multi-write | yes |

These are **connection-based BLE devices, not broadcast-state devices**. The
`add/BleBroadcastProcessor*.java` only parse the advertised **SKU/name during pairing**
(via `BaseBleDeviceModel.getSku()`); no on/off state is broadcast. Control requires a
GATT connection.

`Mode` opcode confirmed `0x05` via `base2light…AbsModeController.getCommandType()`.

---

## 1. Mode sub-mode selector map (`byte[2]` after opcode `0x05`)

Selectors differ per family generation (source: each `ble/Mode.java::parseSubMode` and
each `SubMode*.subModeCommandType()`):

| Sub-mode | tvlightv1 (H6179) | v2 (T1/T1S) | v3 (light bars) | v4 (P1/P1S) |
|---|---|---|---|---|
| Video (camera) | — | `0x00` | — | `0x00` (VideoV2) |
| Scenes | `0x04` | `0x04` | `0x04` | `0x04` |
| NewDiy | `0x0A` | `0x0A` | `0x0A` | `0x0A` |
| Color (legacy) | `0x0D` | `0x0B` | `0x0D` | `0x0D` |
| ColorV2 | — | `0x15` | `0x15` | `0x15` |
| Music (legacy) | `0x0E` | `0x0C` | `0x0C` | `0x0C` |
| MusicV2 | — | `0x13` | `0x13` | `0x13` |
| MusicV3 | — | — | `0x13` | — |

`Mode.parseSubMode` falls through to **Color** for any unmatched selector. The frame is
built by `BleUtils.o(type, 0x05, selector, payload)` so the selector sits at `byte[2]`
and the sub-mode's own `getWriteBytes()[0]` (which equals the selector) is the first
payload byte — i.e. the selector appears at both `byte[2]` and `byte[3]` on the wire.

---

## 2. Video / camera color-region protocol (capture boxes: v2, v4)

### 2.1 Video sub-mode (selector `0x00`)

**v2 `SubModeVideo.getWriteBytes()`** (`pact_tvlightv2/ble/SubModeVideo.java`):
```
[0] 0x00 selector
[1] !gameMode ? 1 : 0        (f148144a — game/movie toggle; 0 = game)
[2] !musicReactive ? 1 : 0   (f148145b)
[3] saturation/vividness 1..100   (f148146c, clamped on parse)
[4] voiceOpen ? 1 : 0        (f148147d)
[5] voice/volume 0..255      (f148148e)
[6] f148150g  (extra param, 0 default)
```
parse() mirrors offsets [0..5].

**v4 `SubModeVideoV2.getWriteBytes()`** (`pact_tvlightv4/ble/SubModeVideoV2.java`):
```
[0] 0x00 selector
[1] (videoFlag==2 ? 2 : isMovie?1:0)   (f149306h / f149301c)
[2] !drama ? 1 : 0                      (f149299a — "drama"/movie scene flag)
[3] vividness 1..100                    (f149300b)
[4] voiceOpen ? 1 : 0                   (f149302d)
[5] voice 0..255                        (f149303e)
[6] f149307i (extra)
```
v4 also has a legacy `SubModeVideo` (7-byte: `[0]=0,[1]=0,[2]=!drama,[3]=vividness,
[4]=0,[5]=0,[6]=extra`) and converts both ways with `parseSubModeVideo2Old/New`.

### 2.2 Video-mode parameters opcode `0xA9` (`SINGLE_VIDEO_MODE_PARAMS = -87`)

`base2light/ble/controller/VideoModeParamsController.java`. Single frame, opcode `0xA9`.
Payload `byte[0]` = sub-param selector, `byte[1]` = data length, `byte[2..]` = data:

| sub-param `byte[0]` | meaning | write payload | read reply |
|---|---|---|---|
| `0x00` whiteBalance | RGB white-balance | `[0]=0,[1]=len,[2..]=data` where data = `{enable(0=on), rGain, bGain}` | `[2]=gradualOn(0),[3]=r,[4]=b,[5]=wbEnable(0),[6]=r,[7]=b` |
| `0x01` lingmindu | game sensitivity (default 60) | `[0]=1,[1]=1,[2]=value` | `[2]=value` |
| `0x02` brightness | video brightness (default 50) | `[0]=2,[1]=1,[2]=value` | `[2]=value` |
| `0x06` whiteBalanceV1 | white-balance v1 | `[0]=6,[1]=1,[2]=value` | `[2]=value` |

Helpers `isWhiteBalance/isLingmindu4Game/isBrightness/isWhiteBalanceV1(b1,b2)` match
`b1==0xA9 && b2==selector`. Movie-feast white-balance is set via
`new VideoModeParamsController((byte)0, new byte[]{1,(byte)r,(byte)b})`.

### 2.3 Camera install / position / light-direction opcodes (v2, v4)

Single controllers (`pact_tvlightv2/ble/` and `pact_tvlightv4/ble/`):

| Controller | Opcode | Write payload `q()` | Read/notify | Meaning |
|---|---|---|---|---|
| `LightDirectionController` | `0x30` (48) | `{(byte)direction}` | `EventLightDirection` | light flow direction |
| `CameraPosController` | `0x31` (49) | `{(byte)pos}` | `EventCameraPos` | camera install position |
| `CheckCameraController` | `0x32` (50, `MSG_TYPE_READ_INSTALL_CAMERA`) | `{}` (read) | reply `byte[0]` = install state → `EventCheckCamera` | is camera installed/aligned |
| `GradualController` | `0xA3` (-93, `SINGLE_GRADUAL_CHANGE_WIFI_BLE`) | `{(byte)gradual}` | `EventGradual` | gradual color change toggle |
| `StartTimeController` | `0x34` (52) | `{}` (read) | reply byte clamped to 255 | startup-delay time |
| `StartTimeControllerV1` | `0x35` (53) | — | `EventStartTime` | startup-delay v1 |

Camera-grid **calibration points** (the on-screen color sampling grid) are computed and
uploaded to the cloud, not pushed over BLE: `add/CalibrationReadM.java`,
`add/net/CalibrationPointsRequest/UploadPointsRequest`, `iot/CmdCalibrationPoints.java`.
The BLE side only reports install/position state via the opcodes above.

---

## 3. Color sub-mode byte layouts (segment-from-screen)

### 3.1 v2 legacy Color (selector `0x0B`) — 15-segment

`pact_tvlightv2/ble/SubModeColor.getWriteBytes()` (8 bytes):
```
[0] 0x0B selector
[1..3] RGB (f148109a)
[4..5] color-temp Kelvin, getSignedBytesFor2(v,true) = big-endian (f148110b)
[6] segment bitmap, bits 0..7  (boolean[15] f148112d, LSB-first)
[7] segment bitmap, bits 8..14
```
This is the **color-segment-from-screen layout**: the 15-bit mask selects which of the
strip's 15 logical zones receive the RGB/temp.

### 3.2 v2 ColorV2 (selector `0x15`) — two write variants

`pact_tvlightv2/ble/SubModeColorV2.java`. First payload byte after selector is a
**variant tag** (`f148114j=1` single/gradient, `f148115k=2` indexed):

Variant `0x02` (indexed color + segment mask):
```
[0] 0x15 selector
[1] 0x02 variant
[2] color index / preset (f148123h)
[3] segment bits 0..7   (boolean[15] f148120e)
[4] segment bits 8..14
```
Variant `0x01` (gradient two-color + segment mask):
```
[0] 0x15 selector
[1] 0x01 variant
[2..4]  RGB1
[5..6]  color-temp (BE)
[7..9]  RGB2 (gradient end)
[10] segment bits 0..7
[11] segment bits 8..14
```

### 3.3 v3 / v4 Color (selector `0x0D`) — dual light-bar

`pact_tvlightv3/ble/SubModeColor.getWriteBytes()` (7 bytes; v4 identical):
```
[0] 0x0D selector
[1] bar-select: (bar0&&bar1)?0x11 : bar0?0x01 : bar1?0x10 : 0x00   (boolean[2] f148515a)
[2..4] RGB
[5..6] color-temp (BE)
```
The `0x01`/`0x10` nibble pattern selects the left/right TV light bar (the two-piece bar
kit). v3/v4 also have `SubModeColorV2` at selector `0x15` (same two-variant scheme as §3.2).

### 3.4 tvlightv1 Color (selector `0x0D`) — gradient pair

`tvlightv1/ble/SubModeColor.getWriteBytes()` (9 bytes):
```
[0] 0x0D selector
[1..3] RGB1
[4..5] color-temp (BE)
[6..8] RGB2 (gradient end color)
```

---

## 4. Music sub-mode layouts

### 4.1 v2 / v3 legacy Music (selector `0x0C`)

`pact_tvlightv2/ble/SubModeMusic.getWriteBytes()` — variable length:
```
[0] 0x0C selector
[1] effect/mode 0..255   (f148127a)
[2] sensitivity 0..99    (f148128b)
[3] autoColor? 0:1       (only when extended form)
[4..6] manual RGB        (when autoColor off)
```
parse() handles both 3-byte and 7-byte forms.

### 4.2 v2 / v3 / v4 MusicV2 (selector `0x13`) — 8 bytes

`pact_tvlightv2/ble/SubModeMusicV2.getWriteBytes()`:
```
[0] 0x13 selector
[1] effect 0..255    (f148136a, default 5)
[2] sensitivity 0..99 (f148137b)
[3] sub-effect/style (f148138c; 0 = "rgb only", default 16)
[4] !autoColor ? 1 : 0 (f148139d)
[5..7] RGB           (manual color)
```

### 4.3 v3 MusicV3 (selector `0x13`) — `SubModeMusicV3`

Variable length keyed on `f148578h`: when style==3 a 9-byte form is emitted (selector +
8 data bytes). Same selector `0x13` as MusicV2; v3 chooses the class by version.
(See `pact_tvlightv3/ble/SubModeMusicV3.java`; deeper sub-effect tables out of scope.)

### 4.4 tvlightv1 Music (selector `0x0E`)

`tvlightv1/ble/SubModeMusic.getWriteBytes()` = `{0x0E, effect, sensitivity, autoFlag}`.

---

## 5. Scenes & DIY (mostly common set)

- **Scenes** (selector `0x04`): v2/v3/v4 `SubModeScenes` = `{0x04, lo, hi}` where the
  2-byte scene id is `getSignedBytesFor2(id, false)` (**little-endian**); parse reads
  `getSignedShort(bArr[1], bArr[0])`. tvlightv1 uses a **single-byte** id: `{0x04, id}`.
- **NewDiy** (selector `0x0A`): `{0x0A, lo, hi}` 2-byte DIY-code (BE here, `…For2(v,true)`),
  same across families. Bulk DIY definition uploads go through the multi-packet
  `0xA1`/`0xA3` path (`DiyLocal.java`), not the single mode frame.

These match the base2light common set; no per-device deviation beyond the selector and
the scene-id endianness noted above.

---

## 6. tvlightv1-specific: TV-size limit (`0x0E`)

`tvlightv1/ble/LimitController.java`, opcode `0x0E` (14). `q()` = `{(byte)f159534f}`.
Sets/reads the backlight's configured TV-size bucket (number of LEDs per edge) so the
camera-less H6179 maps colors to the correct strip length. `EventLimit`/`EventChangeLimit`
carry the result.

---

## 7. pickupbox / Govee Sync box (H1161) — multi-device music director

The H1161 ("Govee Sync") is a BLE hub that drives **up to 5 attached light zones** in a
music/color group. It does NOT use the camera path. Distinct single-frame opcodes
(`pickupbox/ble/*Controller.java`, type `0x33`/`0xAA`):

| Controller | Opcode | Payload / meaning |
|---|---|---|
| `OpenController` | `0x10` (16) | on/off |
| `BrightnessController` | `0x11` (17) | brightness |
| `ModeController` | `0x05` (5) | standard mode (selector at `byte[2]`) |
| `MultiDeviceController` | `0x30` (48) | configure the multi-device set |
| `DeviceNumController` | `0x40` (64) | number of attached sub-devices |
| `DeviceInfoController` | `0x41` (65) | sub-device info |
| `ClearDeviceController` | `0x42` (66) | clear/remove sub-devices |
| `OpDeviceController` | `0x43` (67) | `q()={(byte)idx,(byte)op}` — operate one sub-device |
| `MultiMusicController` | `0x41` (65) | music-feast RGB set (see §8) |

Notify parsers: `DeviceStatusNotifyParse`, `BrightnessNotifyParse`,
`ResetDeviceNotifyParse`; events `EventH1161`, `EventOpen`, `EventBrightnessNotify`,
`EventSetMultiMusicEffect/Result`.

**pickupbox Color sub-mode (selector `0x14`)** — per-zone RGB,
`pickupbox/adjust/ui/v2/SubModeColor.getWriteBytes()` (17 bytes):
```
[0] 0x14 selector
[1] zone bitmap, bits 0..4 (5 zones, f149947c)
[2..4]   zone0 RGB
[5..7]   zone1 RGB
[8..10]  zone2 RGB
[11..13] zone3 RGB
[14..16] zone4 RGB
```
**pickupbox MusicV2 sub-mode** = `{selector, effect, sensitivity, autoFlag, 0,0,0,0}`
(`adjust/v2/SubModeMusicV2`).

---

## 8. Movie Feast / Music Feast (multi-device "director", cross-SKU)

Two shared subsystems orchestrate several Govee devices to react to one screen/audio
source. Both layer extra opcodes on the common frame and use the **multi-packet write**
(`0xA1`/`0xA3`) for the bulk "which sub-devices + their zones" payload.

### 8.1 Movie Feast — single-frame opcodes

`home/main/device/moment/moviefeast/ble/controller/*` and
`base2light/ble/controller/MovieOpenController.java` (type `0x33` write / `0xAA` read):

| Controller | Opcode | Payload `q()` | Reply parse |
|---|---|---|---|
| `MovieOpenController` | `0x54` (84, `movie_feast_on_off`) | `{(byte)open}` | `validBytes[0]` = state |
| `MovieBrightnessController` | `0x50` (80) | `{(byte)b1,(byte)b2}` | int[] of all bytes |
| `MovieSaturationController` | `0x51` (81) | `{(byte)sat}` | — |
| `MovieGetColorController` | `0x52` (82) | `{(byte)a,(byte)b}` | reply `[0],[1]` = region color params (`EventMovieGetColor`) |
| `MovieSoundController` | `0x53` (83) | `{(byte)s1,(byte)s2}` | reply `[0],[1]` |
| `MovieClearSubDeviceController` | `0x42` (66) | — | clear sub-device list |
| `MovieSubDeviceController` | `0x43` (67) | `{(byte)g,(byte)f}` (note: g then f, swapped) | sub-device op |
| `MovieDeleteController` | `0x56` (86) | — | delete feast |

White-balance / video params reuse `VideoModeParamsController` (`0xA9`, §2.2).

### 8.2 Movie Feast — set-sub-device multi-write (opcode `0x50`)

`base2light/ble/controller/MultiSetSubDeviceController4MovieFeast.java`,
`getCommandType()` = **`0x50` (80, `MULTI_SET_DEVICE_4_MOVIE_FEAST`)**, sent as a
multi-packet `0xA1/A3` write whose reassembled payload is built by
`home/main/device/moment/Constant.makeSubDeviceBytes(List<Area4Device>)`:

```
payload[0] = N  (sub-device count)
then for each Area4Device, Area4Device.j():
  [+0] isRgbic ? 1 : 0
  [+1] flag: bleAddress empty ? 1 : 0   (1 = identify by BLE name instead of MAC)
  [+2] device protocol id (f134792f)
  if identify-by-name:  [len][name bytes...]
  else:                 6 MAC bytes, REVERSED (LSB first)
  zones:
    if rgbic && areaNum>1:
       [areaNum]                         (zone count)
       areaNum × zone-index bytes        (0xFF for a disabled zone;
                                           else Constant.getIndex4Portocol(zoneId))
    else:
       [areaNum]                         (==1 for plain RGB)
       1 × zone-index byte
```
(`home/main/device/moment/moviefeast/Area4Device.java::j()`.) This is the canonical
"assign these physical devices + their screen regions to the movie director" command.
A **V2** variant exists (`home/.../moviefeast/ble/controllerV2/MultiSetSubDeviceController4MovieFeastV2`
+ `EventSetSubDevice4MovieFeastV2`) for the newer feast firmware; same opcode family.

`maxSubDeviceNumMovie()` caps the count (5/7/10 by goodsType); `movieFeastVersion()`
selects v0 vs v1 wire format.

### 8.3 Music Feast — multi-controllers (opcodes `0x41`, `0x55`, `0x60`)

- `base2light/ble/controller/MultiMusicController.java` — **opcode `0x41` (65,
  `MULTI_V1_NEW_MUSIC`)**. Payload `g()`:
  `[0]=subModeCode, [1]=colorCount, then colorCount × RGB (3 bytes each)`. Used by both
  pickupbox and the music-feast director to push the reactive palette. ACK success =
  `value[3]==0`.
- `home/main/device/moment/musicfeast/v2/ble/SubDeviceProtocolMultiController.java` —
  **opcode `0x55` (85, `MULTI_MUSIC_FEAST_SUB_DEVICE_PROTOCOL`)**, sent as
  `MultipleControllerCommV1.makeSendBytesV1(0xA3, 0x55, [0x00 || protocolBytes])`
  (a leading `0x00` byte is prepended to the protocol byte array).
- `home/main/device/moment/musicfeast/v2/ble/SetSubDeviceMultiController.java` —
  **opcode `0x60` (96, `MULTI_MUSIC_FEAST_SET_SUB_DEVICE` / `MODULE_FEAST`)** — the
  music-feast analogue of the movie-feast set-sub-device list.

Constants: `BleProtocolConstants` — `MULTI_SET_DEVICE_4_MOVIE_FEAST=80`,
`MULTI_MUSIC_FEAST_SUB_DEVICE_PROTOCOL=85`, `MULTI_MUSIC_FEAST_SET_SUB_DEVICE=96`,
`movie_feast_on_off=84`, `MODULE_FEAST=96`, `feast_switch=1`,
`op_sub_device_read_splicing_status=68`, `SINGLE_VIDEO_MODE_PARAMS=-87 (0xA9)`,
`SINGLE_VIDEO_BRIGHTNESS=-82 (0xAE)`.

---

## 9. Cloud passthrough (v2/v3/v4)

The WiFi-capable capture boxes/light bars wrap the identical BLE frames for cloud
control: `iot/CmdPt.java`/`CmdPtReal.java` (raw 20-byte `pt`), plus typed convenience
commands `CmdTurn`, `CmdBrightness`, `CmdColorWc`, `CmdCameraPos`, `CmdCalibrationPoints`,
`CmdDirection`. So every BLE layout above is also the cloud passthrough payload for these
SKUs. tvlightv1 (H6179) and pickupbox (H1161) have no `iot/` passthrough → BLE-only.

---

## Open questions / uncertainty

- `SubModeVideo` byte[6] (`f148150g` v2 / `f149298c` v4) and `SubModeVideoV2.f149307i`
  are carried but their UI meaning isn't pinned (likely a secondary sensitivity / scene
  index). Flagged.
- `CameraPosController` payload is a single position byte; the value↔orientation mapping
  (top/bottom, degrees) is set in the calibration UI and not enumerated here.
- v3 `SubModeMusicV3` sub-effect tables (the 9-byte style-3 form) were not fully expanded.
- `getIndex4Portocol(zoneId)` zone-id remapping table (movie feast) lives in
  `moment/Constant.java`; values not transcribed.
- `MovieSubDeviceController.q()` writes `{g, f}` (constructor args swapped vs the field
  names) — intentional per source, but worth a live check.
