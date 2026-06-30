# fam-rgb — RGB (non-IC) lights (`com.govee.rgblight` super-family)

**Scope:** the whole-light (non-addressable / non-IC) RGB strips, bulbs, car lights,
string/copper-wire lights and TV backlights handled by
`base/sources/com/govee/rgblight/**` (subdirs `h6113 h6160 h6179 h6181 h6182 h6188 h7308`,
plus the `h60858689` bulb cluster, and the `mode/{color,scene,diy,music}` byte tables).

**Bottom line:** this family is a *thin* device-specific layer over the **common
base2light command set**. There are **no new opcodes** for control: on/off, brightness,
color, color-temp, scene, DIY and music all ride the shared 20-byte frame. The
device-specific content is entirely **(a) which scene/DIY effect *codes* each SKU
supports**, and **(b) the *legacy* sub-mode selector byte** these old products use under
mode opcode `0x05` (which differs from the modern `base2light` numbering). Everything else
is reuse. Uncertain items are flagged inline.

---

## 1. SKU / goodsType routing

All control SKUs in this module are **BLE-connect controllable** (goodsType `0` = pure-BLE
in the catalog; `H6179` = goodsType `12`; `H6117`/`H6163` also expose a Wi-Fi/IoT path but
the BLE layout below is identical and is reused as the cloud `pt` passthrough). None are
broadcast-only.

| Cluster (Support class) | SKUs | Notes |
|---|---|---|
| `h6113/H6113Support` | **H6113, H6114** | Car lights; `Diy4H6113`/`Diy4H6114`, `Scenes4CarLight` |
| `h6160/H6160Support`, `Support4H6160` | **H6160, H6117, H6163** | Strip/Smart light; `Scenes4H6160` (+`v1`/`Night`) |
| `h6179/SupportH6179` | **H6179** | TV backlight; `Diy4H6179` |
| `h6181/H6181Support` | **H6181** | TV backlight; `Diy4H6181`, `Scenes4LocalH6181` |
| `h6182/H6182Support` | **H6182** | TV strip; `Diy4H6182`, `Scenes4H6182` |
| `h6188` | **H6188** | Strip; `H6188BleProtocol`, `Scenes4H6188`, `IotV1ParseHelper` |
| `h7308` | **H7308, H7309, H7311, H7313, H7315, H7316** | Copper-wire / curtain lights; `H7308BleProtocol`, `Scenes4H7308`, delay opcode |
| `h60858689` | **H6085, H6086, H6089** | RGB/warm-white bulbs; `SubModeType`, `H60858689Protocol`, `Scenes4H60858669` |
| `Support4H613839` | **H6138, H6139, H613A–H613F** | Strips; `Diy4H613839`, `Scenes4H613839` |
| `Support4StringLightV2` | **H6194** (+ shared H6109/H6110/H6159/H614B/H614E group) | String light V2; `Scenes4StringLightV2`, `MusicModeV1/V2 4StringLightV2` |

`Support.f152270h` is the union "old RGB" SKU set this module claims; `Support.f152282t`/
`f152283u` are the H6188/H6085/H6086/H6089(+H7308 family) IoT-V1 group.

**rgblight vs rgbiclight split:** addressable / IC strips (per-LED graffiti, segment
control, `MULTI_*` graffiti opcodes 80–98, `sub_mode_color_multi=110`) live in
`rgbiclight`/`dreamcolorlight*`. A product routes **here (rgblight)** when it is a
*whole-light* RGB device — i.e. it has **no IC/segment count** (`Support4StringLightV2.r()`
returns IC info only for the V2 string lights) and uses the single-color sub-modes below.
Color frames here carry **one** RGB triple for the whole fixture; there is no segment index
byte.

---

## 2. Frame anchor (shared, recap)

20-byte frame `[type][opcode][payload…][BCC]`; `type 0x33`=write / `0xAA`=read; BCC =
XOR(bytes 0..18). Confirmed builders used by every class in this module:

| Function | Frame | Source |
|---|---|---|
| Power on/off | `33 01 {01\|00} … BCC` | `base2light…SwitchController`, used in `H7308SmartRoomOp.makeSwitchOpBytes` |
| Brightness | `33 04 {scaled} … BCC`, value = `NumUtil.calculateProgress(254,20,pct)` (range **20..254**) | `H7308SmartRoomOp.makeBrightnessOpBytes` |
| Heartbeat | `HeartController().getValue()` | `H7308SmartRoomOp.heartBytes` |
| Delay-off (H7308) | `DelayCloseController(enable,minutes).getValue()` | `VM4Light` L958 / L1252 |
| Mode (color/scene/DIY/music) | `33 05 [subMode][params…] BCC` | `AbsModeController.getCommandType()==5`; see §3 |

**Mode frame assembly (`AbsMode`/`AbsModeController`):**
`q() = subMode.getWriteBytes()`, prepended with opcode `0x05`. The sub-mode's own
`getWriteBytes()[0]` = **`subModeCommandType()`** (the selector), so in the wire frame:

```
byte[0]=0x33  byte[1]=0x05  byte[2]=<sub-mode selector>  byte[3..]=<sub-mode params>  byte[19]=BCC
```

On parse (`AbsMode.parse`): `validBytes[0]` = sub-mode selector, `validBytes[1..]` handed to
`parseSubMode(selector, payload)`.

---

## 3. Device-specific sub-mode selectors (the key deviation)

These old RGB products use **legacy sub-mode numbers** at `byte[2]`, *not* the modern
`base2light` set (`sub_mode_color=21/0x15`, `sub_mode_music=19/0x13`, `sub_mode_new_diy=10`).
Read the actual constants:

### 3a. H6188 — `h6188/H6188BleProtocol.java`
| Selector (`byte[2]`) | Hex | Meaning |
|---|---|---|
| `sub_mode_scenes` | `0x04` | scene apply (code at `byte[3]`) |
| `sub_mode_music` | `0x03` | music |
| `sub_mode_new_diy` | `0x0A` | new-DIY |
| `sub_mode_color` | `0x0D` | whole-light color |
| `value_multiple_ble_diy` | `0x02` | DIY multi-write subtype |

Scene **codes** (= `byte[3]` under selector `0x04`), `Scenes4H6188.f152730g`:
`film=4, date=5, read=13, brightness=23, aurora=24, cl=9, dynamic=16, romantic=7, fade=17`
→ `{4,5,13,23,24,9,16,7,17}`. (Names mirror `H6188BleProtocol.value_sub_mode_scenes_*`.)

### 3b. H6085/H6086/H6089 bulbs — `h60858689/SubModeType.java` + `H60858689Protocol.java`
| Selector (`byte[2]`) | Hex | Meaning |
|---|---|---|
| `sub_mode_color` | `0x02` | whole-light color |
| `sub_mode_scenes` | `0x04` | scene apply |
| `sub_mode_new_diy` | `0x0A` | new-DIY |

Scene codes (`Scenes4H60858669.f152698g`): `{13,17,10,7,20,16,18,19}` =
`reading=13, fade=17, breath=10, romantic=7, heartbeat=20, energetic=16, forest=18,
fantasy=19`.
DIY in-scene sub-modes (`SubModeType.value_diy_scenes_mode_*`):
`gradual=0, jumping=1, breath=5, blinking=7, mix=255`.
**Note:** the bulbs also expose a **cloud IoT (JSON) path** — `iot/CmdColorTem` (`"colorTem"`,
kelvin + `CmdOldColor`), `iot/CmdScenes` (`"mode"`, `{mode:4, code}`), `scenes/CmdTurn`
(`"turn"` 1/0). These are MQTT/V1 JSON, not BLE frames; the BLE path uses the selectors above.

### 3c. H7308 (+H7309/11/13/15/16) — `h7308/H7308BleProtocol.java`
| Selector | Hex | Meaning |
|---|---|---|
| `sub_mode_scenes` | `0xA1` (−95) | scene apply — **anomalous** (collides with `MULTIPLE_WRITE` type byte). Flagged: H7308 scene apply likely uses a distinct path; treat `0xA1` as the selector value at `byte[2]`, not a multi-packet header. |

Scene codes (`Scenes4H7308.f152738b`): `{20,21,22,23,24,25,26,27}` =
`combination, in_waves, sequential, slow_glow, chasing, slow_fade, twinkle, steady_on`.
H7308 is effectively **brightness + scenes only**: `H7308SmartRoomOp.onlySupportBrightness()`
returns true and `supportColorSize()`/color-op bytes return 0/null — no whole-light RGB color
exposed via the smart-room op.

### 3d. The remaining strip/car/string SKUs (H6160/H6117/H6163, H6181, H6182, H6113/14,
H613x, StringLightV2)
These have **no dedicated `*BleProtocol` interface** — they go through the generic old-RGB
mode controllers in `base2light`, using the common legacy selectors. Their device-specific
data is only the **scene code table** (§4) and the **DIY support descriptor** (§5).

---

## 4. Scene effect-code tables (per SKU)

Scene apply frame = `33 05 [scene-selector] [code] …`. The `Scenes4*` classes only supply
the **ordered list of effect codes** (plus icons/labels); the frame is built by the common
controller. Codes (the `int[]` effect-set field in each file):

| Class / SKU | Effect codes | Source field |
|---|---|---|
| `Scenes4H6160` (H6160/H6117/H6163) | `{0,1,4,5,7,8,9}` | `f152510d` |
| `Scenes4H6160v1` | `{0,1,4,5,7,8,9,15}` | `f152522d` |
| `Scenes4LocalH6181` (H6181) | `{0,1,4,5,7,8,9}` | `f152744f` |
| `Scenes4H6182` (H6182) | `{4,5,9,7,10,8,16}` | `f152717f` |
| `Scenes4CarLight` (H6113/H6114) | `{4,5,7,8,9,10,16}` | `f152685d` |
| `Scenes4H613839` (H613x) | `{4,5,7,8,9,16,10}` | `f152705d` |
| `Scenes4StringLightV2` (H6194 etc.) | `{4,5,7,8,9,10,16}` | `f152756d` = `{4,5,7,8,9,10,16}` |
| `Scenes4H6188` (H6188) | `{4,5,13,23,24,9,16,7,17}` | `f152730g` |
| `Scenes4H7308` (copper-wire) | `{20,21,22,23,24,25,26,27}` | `f152738b` |
| `Scenes4H60858669` (bulbs) | `{13,17,10,7,20,16,18,19}` | `f152698g` |

Each `Scenes4*` also defines a parallel `*Night` variant (e.g. `Scenes4H6182Night`,
`Scenes4H6160Night`) — same codes, dark-themed icons only; no protocol difference. Generic
effect-code meaning (shared across the family): `0=gradual 1=jumping 4=film 5=date 7=romantic
8=? 9=candle/cl 10=breath 13=reading 15=? 16=energetic/dynamic 17=fade 18=forest 19=fantasy
20=heartbeat 23=brightness 24=aurora`. (Codes 8/15 unlabeled in this module — flagged.)

---

## 5. DIY (whole-light) — `mode/diy/Diy4*.java`

These classes are **DIY *capability descriptors*** (`DiySupportV1`), not raw frames. The DIY
frame itself is emitted by the shared `DiyControllerNoEventV*` / `DiyM` path
(`sub_mode_new_diy = 0x0A`, see §3). Each `Diy4*.a()` declares:

- supported DIY **effect templates** via `DiyM.EffectCode.f462xx` arrays (gradual / jumping /
  flicker / music groups) and `Effect.makeEffectWithSubSet(...)`.
- **`mix4EffectsNum = 4`** — every SKU in this family mixes up to **4** effects.
- **max colors per effect = 8** (`Effect4Color.makeMaxColor4Effect(code, 8)`).
- **max speed = 100** (`Effect4Speed.makeMaxSpeed4Effect(code, 100)`).
- `effectCodes = new EffectCodes(DiyM.s(effects), DiyM.s(mixEffects))` — the encoded code set
  pushed to the device.

`Diy4H6181`, `Diy4H6182`, `Diy4H6179`, `Diy4H6113`, `Diy4H6114`, `Diy4SpecialRgb`,
`Diy4H613839`, `Diy4H6159`, `Diy4StringLightV2`, `Diy4CarLight` are structurally identical
(same 8-color / 100-speed / 4-mix caps) and differ only in **which `EffectCode` arrays** they
list (i.e. which DIY animation templates the SKU's firmware accepts). No per-SKU byte-layout
deviation in the DIY frame itself.

---

## 6. Whole-light COLOR & COLOR-TEMP layout

Read from the parse strategies in `mode/ModeParseStrategyConfig.java` (these mirror the write
layout the device echoes). `validBytes` below = sub-mode payload **after** the selector byte
(i.e. frame `byte[3]` = `validBytes[0]`).

### Color sub-mode, V1 (`ModeParseStrategyConfig.a()` → `SubMode4Color`)
- `validBytes[0..2]` = **R,G,B** when no color-temp component (`g()==0`).
- When color-temp present (`g()!=0`):
  - `validBytes[3..4]` = **color-temp** as signed short (`BleUtil.getSignedShort(b3,b4)`).
  - `validBytes[5..7]` = **R,G,B** (the RGB rendering of that temp).

So a plain color write is `33 05 <colorSel> RR GG BB …`; a color-temp write carries the
kelvin short at frame `byte[6..7]` and its RGB at `byte[8..10]`. `<colorSel>` is the legacy
selector per SKU (H6188 `0x0D`, bulbs `0x02`, generic old-RGB via common controller).

### Color sub-mode, V2 (`ModeParseStrategyConfig.b()`)
- RGB at `validBytes[4..6]` when temp-mode flag set, else `validBytes[0..2]`; kelvin derived
  via `KelvinConfig.c(rgb, info)`. Used by the newer (H6163-class) `DelegateColor4H6163`
  which also supports **segmented** color (`DelegateColorV2.J1`, "支持分段") when
  `connectSuccessType ∈ {0,1}` — but that segmentation rides the shared colorv2 path, not a
  rgblight-specific opcode.

---

## 7. MUSIC layout — `ModeParseStrategyConfig.c()/d()` (+ `mode/music/*`)

`sub_mode_music` selector = `0x03` (H6188) / common old value. Two variants:

### Music V2 (`SubMode4MusicV2`, `ModeParseStrategyConfig.c()`)
- `validBytes[0]` = music mode (`48`/`49` ⇒ kept literally; else mapped to `3` or `255`).
- `validBytes[1]` = **sensitivity**.
- `validBytes[2]` = **auto-color flag** (0 = use device color).
- `validBytes[3..5]` (or `[4..6]` in the 255/mix branch) = **R,G,B** of the manual music color
  (only when auto-color flag ≠ 0).

### Music V1 (`ModeParseStrategyConfig.d()` → `SubMode4MusicV1`) — older, simpler scalar
sensitivity layout (no RGB triple). `MusicModeV14StringLightV2` / `MusicModeV24StringLightV2`
and the `OldDevicePickSound*` classes select V1 vs V2 per SKU/firmware; H6160 gains "new
order" mic support only at fw ≥ `1.04.05` (`H6160Support.b`).

---

## 8. Device-specific opcodes / status

- **H7308 delay-off**: built via `base2light…DelayCloseController(enable, minutes)`; the
  reply is parsed in `VM4Light` (~L338): `minutes = b*60 + b2`, `leftMinutes = b3*60 + b4`,
  with an `enable` flag — i.e. the delay-status payload packs total and remaining as
  hour/minute byte pairs. Delay presets (`DelayItem.getDefItems`): 0,15,30,45,60,120,180,240,
  360,480 min.
- **H6188 / H7308 IoT-V1 parse helpers** (`h6188/IotV1ParseHelper`,
  `h60858689/H60858689IotV1ParseHelper`) translate the same BLE mode payloads to/from the
  cloud V1 JSON — confirming the BLE layouts above double as the `pt` passthrough.
- No segment/IC, no graffiti, no `MULTI_*` bulk opcodes in this module (those are
  rgbiclight-only) — consistent with whole-light routing.

---

## 9. Confidence & open questions

- **High:** SKU/goodsType routing; scene/DIY code tables (read directly); mode opcode `0x05`
  and sub-mode-selector framing (`AbsMode`/`AbsModeController`); legacy selector values per
  cluster (read from the `*BleProtocol`/`SubModeType` constants); brightness scaling 20..254;
  H7308 brightness-only + delay.
- **Medium:** color/color-temp/music *byte offsets* — derived from the **parse** strategies
  (device→app echo) in `ModeParseStrategyConfig`; the write builder lives in shared
  `base2light` `SubMode4Color`/`SubMode4MusicV*` (not re-read here) but is the same layout by
  construction.
- **Open:** H7308 `sub_mode_scenes = 0xA1` collides with the `MULTIPLE_WRITE` type byte —
  could indicate H7308 scenes are sent as a different command class; not resolved from this
  module alone. Effect-code meanings `8` and `15` are unlabeled in rgblight (defined in the
  shared scene-name map). The generic old-RGB color *write* selector for the
  no-`*BleProtocol` SKUs (H6160/H6181/H6182/H613x/StringLightV2) is assumed to match the
  common old-RGB controller value — worth confirming against the `base2light` old-color
  controller if exact byte fidelity is needed.
