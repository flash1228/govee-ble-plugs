# Common Light Command Set — `base2light` Controllers

Scope: `com/govee/base2light/ble/controller/**` (every `*Controller.java`) plus
`BleProtocolConstants.java`. This is the shared 0x33/0xAA command surface used across
Govee light/strip/bulb products (and reused by some plug/appliance code). Each "controller"
class is a one-command builder/parser: it produces a single 20-byte frame (write or read)
and parses the matching reply.

All byte values below are given as **hex** (the decompiler prints signed decimals;
converted via `v & 0xFF`).

---

## 1. Frame format & checksum (authoritative)

Single-command frames are built by `BleUtils.generate20Bytes(...)` →
`BleUtils.Companion.p(proType, commandType, payload)` (2-byte header) or
`o(proType, commandType, subType, payload)` (3-byte header).
Source: `com/govee/base2kt/utils/BleUtils.java` (methods `o` @L975, `p` @L1000,
`generate20Bytes` @L1332/1338, checksum `v` @L1208).

```
byte[0]   = proType / command-type byte
byte[1]   = commandType / opcode
byte[2..18] = payload (zero-padded to fill 20 bytes)
byte[19]  = BCC = XOR of byte[0..18]      // BleUtils.v(): b=p[0]; for i in 1..18 b^=p[i]
```

`proType` (byte[0]) is decided per-controller by `getProType()`:

| Context | proType | meaning |
|---|---|---|
| `AbsSingleController`, write | `0x33` | SINGLE_WRITE / control |
| `AbsSingleController`, read  | `0xAA` | SINGLE_READ / query |
| `AbsControllerNoEvent4Single`, write, normal | `0x33` | write |
| `AbsControllerNoEvent4Single`, write, "writeRead" flag | `0x3A` (58) | SINGLE_WRITE_READ |
| `AbsControllerNoEvent4Single`, read | `0xAA` | read |

Source: `AbsSingleController.getProType()` @L28; `AbsControllerNoEvent4Single.getProType()` @L135.

### Read vs write payloads
`AbsSingleController` has two payload hooks:
- `q()` → the **write** payload (used when proType=0x33).
- `p()` → the **read** payload, often a single "sub-selector" byte sent with the 0xAA query
  (default `p()` returns `null` = empty payload). Source: `AbsSingleController.f()/g()` @L18-25.

### Reply parsing
- Single reply: `AbsController.onResult()` @L117 → `AbsSingleController.m()` @L38.
  For a **read** reply it copies `value[2..]` (17 bytes) into `validBytes` and calls
  `parseValidBytes()`. For a **write** ack it inspects `value[2]` (`t()`: `value[2]==0` = success)
  and passes `value[3..]` (16 bytes) to `s()`/`r()`.
- So for reads, `validBytes[0]` is the **first payload byte after the opcode** (often the echoed
  sub-selector); for write acks, `value[2]` is the status byte (0 = OK).
- Notify frames begin `0xEE` (`NOTIFY = -18`); recognition notify `0xED` (`NOTIFY_RECOGNITION = -19`).

---

## 2. Master opcode table (byte[1])

Command-type byte (byte[0]) is `0x33` for writes / `0xAA` for reads unless noted.
"Sub" = first payload byte (`p()`/`q()[0]`) used as a selector.

### 2a. Core light control

| Name | opcode | dir | payload | source |
|---|---|---|---|---|
| Main switch (SINGLE_MAIN_SWITCH / SINGLE_SWITCH) | `0x01` | W/R | `[on]` (0/1; write uses raw int byte) | `MainSwitchController` @L37, `SwitchController` @L24 |
| Light switch (SINGLE_LIGHT_SWITCH) | `0x30` | W/R | `[on]` (0/1) | `LightSwitchH6057Controller` @L24 |
| Brightness (SINGLE_BRIGHTNESS) | `0x04` | W/R | `[level]` (1 byte, unsigned 0-100 or 0-255 per model) | `BrightnessController` @L25 |
| Mode / scene (SINGLE_MODE) | `0x05` | W/R | write: `subModeType + subModePayload`; read: `p()=[0x01]` | `AbsModeController` @L34, `AbsMode` @L8 |
| Gradual change on/off (SINGLE_GRADUAL_CHANGE_WIFI_BLE) | `0xA3` | W/R | `[enable]` (0/1) | `GradualChangeBleWifiController` @L24 |

> Note: opcode `0xA3` here is a *single* command byte (not the multi-write A3); proType still 0x33/0xAA.

### 2b. Modes & sub-modes (payload[0] of a 0x05 MODE frame)

`AbsMode.parse()` reads `validBytes[0]` = subModeType, rest = sub payload. Common subType bytes
(from `BleProtocolConstants`):

| subType | const | hex |
|---|---|---|
| color | `sub_mode_color` | `0x15` |
| color (multi) | `sub_mode_color_multi` | `0x6E` |
| music | `sub_mode_music` | `0x13` |
| abs music | `sub_mode_abs_music` | `0x16` |
| scenes | `sub_mode_scenes` | `0x04` |
| new DIY | `sub_mode_new_diy` | `0x0A` |
| operate | `sub_mode_operate` | `0x20` |
| operate V2 | `sub_mode_operate_V2` | `0x0C` |
| daysync | `SUB_MODE_DAYSYNC` | `0xF0` |
| carousel | `sub_mode_carousel` | `0x82` |
| display | `sub_mode_display` | `0x81` |
| part scenes | `sub_mode_part_scenes` | `0x47` |

Concrete `color_temp` payload encoding lives in the per-product `AbsMode` subclasses
(outside this controller dir); within scope only the subType selector byte is fixed.

### 2c. Timers / schedules / sleep

| Name | opcode | dir | payload (write `q()`) | source |
|---|---|---|---|---|
| Sync time (SINGLE_SYNC_TIME) | `0x09` | W | `[hour, min, sec, week, 0x01, tzHourOff, tzMinOff]` | `SyncTimeController` @L34/39 |
| Auto on/off time (SINGLE_AUTO_TIME) | `0x0A` | W/R | `[on, openH, openM, closeH, closeM, group, repeat]`; read `p()=[group]` | `AutoTimeController` @L57 |
| Delay close (SINGLE_DELAY_CLOSE) | `0x0B` | W/R | `[on, H, M]` (H/M from minutes); reply `[on,h1,m1,h2,m2]` | `DelayCloseController` @L28 |
| Sleep (SINGLE_SLEEP) | `0x11` | W/R | `[enable, startBri, closeTime, curTime]` | `SleepController` @L50 |
| Wake up (SINGLE_WAKEUP) | `0x12` | W/R | `[enable, endBri, wakeHour(0-23), wakeMin(0-59), repeat, wakeTime]` | `WakeUpController` @L68 |
| New timer V1 (SINGLE_NEW_TIME_V1) | `0x23` | W/R | `[group, enableAndType, hour, min, repeat]`; read `p()=[group]`; reply group=0xFF lists 4×4-byte timers | `NewTimerV1Controller` @L76 |
| Set light-start index (value_set_light_start) | `0x24` | W | `[index(≥1), timeLo, timeHi]` (2-byte LE time) | `SetLightStartController` @L26/36 |

### 2d. Settings / behaviour

| Name | opcode | dir | payload | source |
|---|---|---|---|---|
| Energy saving (value_low_energy_on_off) | `0x16` | W/R | `[on]` (0/1) | `EnergySavingController` @L25 |
| Light indicator (VALUE_SETTING_LIGHT_INDICATOR) | `0x16` | W/R | enabled+window: `[en,0xFF,0xFF,0xFF,0xFF]` (forever) or `[en,startH,startM,endH,endM]`; empty read | `LightIndicatorController` @L35/54 |
| Without-interrupt (SINGLE_WITHOUT_INTERRUPT) | `0x35` | W/R | `[value]` (1 byte) | `WithoutInterruptController` @L37 |
| Volume (SINGLE_VOLUME) | `0x33` | W/R | `[volume]` (1 byte) | `VolumeController` @L37 |
| On/off power-loss memory (SINGLE_ON_OFF_MEMORY) | `0x41` | W/R | legacy `[on]`; typed `[0x02, type]`, read `p()=[0x02]`; reply `[bool, value]` | `OnOffMemoryController` @L67/83, `Controller4OnOffMemory` @L61 |
| Logo light (value_logo) | `0xA6` | W/R | off `[0x00]`; on `[0x01, bri, r, g, b]`; reply `[op,bri,r,g,b]` | `LogoController` @L41/54 |
| Init light (PROTOCOL_INIT_LIGHT / SINGLE_GUIDE_LIGHT) | `0x38` | W/R | `[value]` (1 byte) | `InitLightController` @L32 |
| Movie/feast open (movie_feast_on_off) | `0x54` | W/R | `[open]` (1 byte) | `MovieOpenController` @L25 |

> Opcode `0x16` is overloaded: `EnergySavingController` and `LightIndicatorController` both use byte[1]=0x16
> (`value_low_energy_on_off` == `VALUE_SETTING_LIGHT_INDICATOR` == 22). Disambiguation is by product/context
> and by payload shape (energy = 1 byte; indicator = 5 bytes). Flagged.

### 2e. Device-info reads — opcode `0x07` (SINGLE_DEVICE_INFO) with sub-selector

These are 0xAA reads; `p()` returns a 1-byte sub-selector, and the reply echoes that selector in
`validBytes[0]` (controllers assert it before parsing).

| Sub (payload[0]) | const | meaning | reply parse | source |
|---|---|---|---|---|
| `0x02` | VALUE_DEVICE_INFO_UUID | device UUID / SN (8 bytes → MAC-style) | `SnController` @L38 | `SnController` |
| `0x03` | VALUE_DEVICE_INFO_HARD_VERSION | hardware version (ASCII) | `HardVersionController` @L28 | `HardVersionController` (default op `0x07`) |
| `0x04` | VALUE_DEVICE_INFO_SOFT_VERSION | software version (ASCII) | `SoftVersionInDeviceInfoController` @L16 | `SoftVersionInDeviceInfoController`, `VersionSoftController` |
| `0x07` | VALUE_DEVICE_INFO_DSP_VERSION | DSP version (2-byte int, `[lo,hi]`) | `DspVersionInDeviceInfoController` @L17 | `DspVersionInDeviceInfoController` |
| `0x0A` | SINGLE_DEVICE_INFO_MCU_SOFT_VERSION | MCU soft version (ASCII) | `McuSoftVersionControllerV1` @L27 | `McuSoftVersionControllerV1` |
| `0x0B` | SINGLE_DEVICE_INFO_MCU_HARD_VERSION / VALUE_MCU_HARD_VERSION | MCU hard version (ASCII) | `McuHardVersionControllerV1` @L27 | `McuHardVersionControllerV1` |
| `0x10` (16) | (basic info) | SN(8) + 2×3-byte versions | `BasicInfoController` @L23 | `BasicInfoController` |
| `0x11` (17) | (basic wifi info) | wifi basic info | `BasicWifiInfoController` p()=`[17]` | `BasicWifiInfoController` |

### 2f. Standalone version reads (own opcode, no sub-selector unless noted)

| Name | opcode | dir | payload | source |
|---|---|---|---|---|
| Soft version (SINGLE_SOFT_VERSION) | `0x06` | R | none → ASCII string | `SoftVersionController` @L23 (default ct `0x06`) |
| SN / device info | `0x07` | R | `p()=[0x02]` | `SnController` @L33 |
| Wifi MAC (SINGLE_WIFI_MAC) | `0x14` | R | none → 6-byte MAC | `WifiMacController` @L23 |
| Wifi hard version (SINGLE_WIFI_HARD_VERSION) | `0x20` | R | none → ASCII | `WifiHardVersionController` @L23 |
| Wifi soft version (SINGLE_WIFI_SOFT_VERSION) | `0x21` | R | none → ASCII | `WifiSoftVersionController` @L23 |
| Wifi DSP version (SINGLE_WIFI_DSP_VERSION) | `0x22` | R | — | const only |
| Wifi "new msg" unified read (SINGLE_WIFI_NEW_MSG) V2 | `0x49` (73) | R | sub: `0x01`=mac, `0x02`=soft, `0x03`=hard | `WifiMacControllerV2` p()=`[1]`, `WifiSoftVersionControllerV2` p()=`[2]`, `WifiHardVersionControllerV2` p()=`[3]` |
| Protocol / pact (SINGLE_PACT) | `0xEF` | R | reply `[typeHi,typeLo,code]` → pactType(2B BE), pactCode | `PactController` @L28/33 |
| IC count (SINGLE_IC_SEGMENT_NUM) | `0x40` (64) | R | reply 2-byte signed short = IC count | `IcNumController` @L28 |
| Dynamic-API support (SINGLE_DYNAMIC_API_SUPPORT) | `0xAB` | R | reply `[version, support(0/1)]` | `DynamicApiSupportController` @L15 |

### 2g. Heart / liveness

| Name | opcode | dir | payload | source |
|---|---|---|---|---|
| Heart (SINGLE_HEART) | `0x01` | R | reply `validBytes[0]!=0` = alive | `HeartController` @L21 |
| Heart variants (lamp / w-battery / noEvent) | `0x01` / model-set | R | — | `HeartControllerLamp`, `HeartControllerWithBattery`, `HeartControllerNoEvent` |

### 2h. Encryption handshake (see crypto notes)

| Name | command/opcode | dir | payload | source |
|---|---|---|---|---|
| Read secret key (SINGLE_READ_SECRET_KEY) | byte[1]=`0xB1`, proType=0xAA | R | reply `[0x01, key(8)]` → base64 stored | `SecretKeyController` @L17/51 |
| Check secret key (SINGLE_CHECK_SECRET_KEY) | byte[1]=`0xB2`, proType=0x33 | W | `q()` = base64-decoded secret bytes | `SecretKeyController` @L24/71 |

`SecretKeyController` sets `getCommandType()` to `0xB1` for the read ctor and `0xB2` for the write ctor.

### 2i. OTA / IC / camera / misc writes

| Name | opcode | dir | payload | source |
|---|---|---|---|---|
| OTA prepare (SINGLE_OTA_PREPARE) | `0xEE` | W | none | `OtaPrepareController` @L11 |
| Refresh / check IC (SINGLE_WRITE_CHECK_IC) | `0x42` (66) | W | empty | `RefreshIcController` @L11 |
| Check IC amount (SINGLE_WRITE_CHECK_IC_AMOUNT) | `0x43` (67) | W | — | `CheckICAmountController` |
| Check camera install (MSG_TYPE_READ_INSTALL_CAMERA) | `0x32` (50) | R | — | `CheckCameraController` |
| Check direction finish (PROTOCOL_CHECK_DIRECTION) | `0x39` (57) | — | — | `CheckDirectionFinishController` |
| Wifi link-start (value_wifi_link_start) | `0x17` (23) | W | `[open]` (0/1) | `WifiLinkStarController` @L19 |
| Video mode params (SINGLE_VIDEO_MODE_PARAMS) | `0xA9` | R/W | read `p()=[type]` | `VideoModeParamsController`, `AiIdentifyModelController` |
| AI identify / video recognition | `0xA9` / set | — | — | `AiIdentifyModelController`, `VideoRecognitionController` |
| Movie open V2 / heart | `0x01` w/ `p()=[1]` | — | — | `MovieOpenControllerV2` |

### 2j. Multi-packet builders (A1/A3 families, scope overlap)

These controllers extend the `*NoEvent4Multi*` bases and emit multi-packet frames
(byte[0]=`0xA1` write / `0xA2` read / `0xA3` MULTI_WRITE_V1 / `0xA4` V2 / `0xA6` MTU, byte[1]=comType,
byte[2]=index, byte[3..18]=chunk, byte[19]=XOR). Their `getCommandType()` returns the **comType**
placed in multi byte[1]:

| comType | const | controllers |
|---|---|---|
| `0x01` | MULTI_V1_NEW_SCENES | `MultiNewScenesControllerV1` |
| `0x02` | MULTI_V2_NEW_SCENES / MULTI_DIY | `MultiNewScenesControllerV2`, `MultiDiyTempalteController`, `MultipleDiyController` |
| `0x03` | MULTI_V1_NEW_DIY_GRAFFITI | `MultiDiyGraffitiController(V2)`, `Controller4ReadWifiFuncList` |
| `0x04` | MULTI_V1_NEW_DIY | `MultipleDiyControllerV1/V2`, `MultiNewScenesControllerV4` |
| `0x07` | MULTI_V3_NEW_SCENES | `MultiNewScenesControllerV3` |
| `0x09` | MULTI_V1_GRAFFITI_MULTI_LAYER | `MultiDiyGraffitiControllerV1` |
| `0x0A` (10) | MULTI_V4_NEW_SCENES | `MultiNewScenesControllerV5`, `MultiDiyTempalteControllerV2` |
| `0x0C` (12) | MULTI_DIY_PROTOCOL_SCENES | `MultiNewScenesControllerV6/V7` |
| `0x11` (17) | MULTI_WIFI | `MultipleWifiController` |
| `0x40` (64) | MULTI_V1_NEW_COLOR | `MultipleColorStripControllerV1`, `MultipleColorTemStripController`, `MultipleGradientColorTemStripController` |
| `0x41` (65) | MULTI_V1_NEW_MUSIC | `MultiMusicController`, `MultipleController4Music` |
| `0x50` (80) | MULTI_SET_DEVICE_4_MOVIE_FEAST | `MultiSetSubDeviceController4MovieFeast` |
| `0x56`..`0x5A` (86-90) | graffiti / cube / scene-apply | `MultiNewScenesControllerV8/V9/V10/H60B0/H70CX`, `MultiDiyFixedDeviceController` |

(Full multi-packet wire format is documented in the multi-packet spec section; listed here only
to map the shared light comType bytes.)

---

## 3. Notable payload encodings

- **Sync time** (`SyncTimeController.q()` @L39): 7 bytes `hour,min,sec,week(1-7),0x01,
  tzHourOffset,tzMinOffset`. Week: `Calendar.DAY_OF_WEEK-1`, with 0→7 (`SyncTimeInfo` @L49).
- **Wake up**: hour clamped 0-23, minute 0-59 (`WakeUpController.u/v` @L54-60); reply parsed at
  `validBytes[0..5]`.
- **Delay close** write packs minutes→`[H,M]` via `TimeUtils.getHM`; reply gives two H:M pairs
  (set & remaining), with a `+1` fix when remaining is 0 (`DelayCloseController` @L39).
- **Logo**: RGB packed `r,g,b` (`ColorUtils.getRgb`), brightness 1 byte; off frame is just `[0x00]`.
- **Light indicator** "forever" sentinel = `0xFF,0xFF,0xFF,0xFF` after the enable byte
  (`VALUE_SETTING_LIGHT_INDICATOR_FOREVER = -1`).
- **Device-info string reads** decode ASCII via `BleUtil.getStrData` (trims at first 0x00).
- **DSP version**: `BleUtil.getUnsignedBytes(validBytes[2], validBytes[1])` — little-endian 16-bit
  (note arg order hi=byte[2], lo=byte[1]).
- **SN/UUID**: 8 bytes → `BleUtil.toAddressBytes`, strips a leading `00:00:` (`SnController` @L56,
  `BasicInfoController` @L36).
- **On/off memory typed form**: write `[0x02, type]`, read selector `[0x02]`; legacy form is bare
  `[on]`. The reply's `validBytes[1]` is the stored value.

---

## 4. Constant cross-reference (`BleProtocolConstants.java`)

Calibration (`CALIBRATION = 0x30`, `CALI_LEN = 0x5A`) shares the byte value of
`SINGLE_LIGHT_SWITCH = 0x30`; the two are distinguished only by product context (no separate
calibration controller class is present in this directory — it is driven by raw
`Bytes4Controller` frames). `CUSTOM_SHORTCUT = 0x7C` (124) and
`SINGLE_WORRY_FREE_AT_NIGHT = 0x36` (54) have constants and Event/Bean classes but no dedicated
`*Controller` in this directory (built elsewhere as raw frames / NoEvent controllers). Flagged as
uncertain — opcode bytes are confirmed from constants, payload layout is not in-scope here.

Key multi/notify command-type bytes also defined here: `MULTIPLE_WRITE=0xA1`, `MULTIPLE_READ=0xA2`,
`MULTIPLE_WRITE_V1=0xA3`, `MULTIPLE_WRITE_V2=0xA4`, `MTU_MULTIPLE_WRITE=0xA6`,
`MULTI_READ_AB=0xAB`, `MULTI_READ_AC=0xAC`, `NOTIFY=0xEE`, `NOTIFY_RECOGNITION=0xED`.
