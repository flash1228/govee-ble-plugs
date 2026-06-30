# Section: Panels & newer-gen light families (`fam-panels-newgen`)

Covers the strip/TV/car RGBIC families `h6159 h6160 h613839 h612526 h6181 h6182 h6185`,
the segment-addressable "new color" protocol families `h604a h705a h70b1 h70b2 h6057`,
the cell-graffiti panel families `h70bx h6630`, the plant-grow `h7004 h7017`, and the
cloud relay plug `h7014`.

All byte values below are read directly from frame/mode builders (`getWriteBytes()`,
`q()`) in the decompiled source. jadx prints signed decimals; negatives are given as hex
via `(v & 0xFF)`. Everything sits on the standard 20-byte frame (`[type][opcode][payload
…][BCC]`, §3 of the master doc). Mode writes use opcode `0x05` with the sub-mode selector
at `byte[2]` (`AbsMode`/`BleUtils.o`); per-feature controllers use their own opcode at
`byte[1]` with payload from `q()` starting at `byte[2]`.

---

## 0. Cluster map

| Cluster | Families | Protocol style | Notes |
|---|---|---|---|
| A. Classic base2light RGBIC | h6159, h6160, h613839, h612526, h6181, h6182, h6185 | Common set; `0x05` mode | SubModeColor **cmd 2** (RGB+flag+2nd RGB), Scenes 4, NewDiy 10, Music 3/V2 |
| B. Segment "new color" | h604a, h705a, h70b1, h70b2, h6057 | `0x05` mode + many feature opcodes | SubModeColor **cmd 0x15** with `byte[1]=1/2` + per-segment bitmask |
| C. Cell-graffiti panels | h70bx, h6630 | Kotlin `kt.general_controller` mode op + multi-packet DIY | main/sub effect protocol codes |
| D. Plant grow | h7004, h7017 | Single opcode `0x0D` | red/blue intensity pair; mode submodes are SKU-shape placeholders |
| E. Cloud relay plug | h7014 | **No BLE control path** | IoT/cloud `Cmd*` only |

SKU/goodsType coverage (from `pact/Support.java`, `sku/Support.java`, `_sku_catalog.md`):

| Family module | SKUs (goodsType where known) |
|---|---|
| h6159 | H6159, H6110, H6109, H614B, H614E (strip lights) |
| h6160 | H6160, H6163 (gt15), H6117 (smart light/strip) |
| h613839 | H6138, H6139 (strip, discontinued) |
| h612526 | H6125, H6126 (strip) |
| h6181 | H6181 (TV backlight, discontinued) |
| h6182 | H6182 (TV strip) |
| h6185 | H6185 (car underglow, discontinued) |
| h604a (`h604a/pact/Support`) | H604A(95)/H604C=H604a-type(24 IC); H604B(109)/H604D(133)=H604b-type(14 IC) — DreamView G1/Pro/S |
| h705a (`h705a/pact/Support`) | H705a(125), H706A/B/C(180), H7067/8/9(250), H3401(394), H608A(184), H61C2/3/5, H705b/d/e/f, H805/806/801/808-series, H806A/C — Permanent/Outdoor lights, deck lights, string downlights |
| h70b1/h70b2 (`h70b1/origin/pact/Support`) | H70B1(134), H70BC(216) + H70B2 group — Curtain Lights / Lightwall (older protocol) |
| h6057 (`h6057/origin/pact/Support`) | H6057(104) — Govee Night Light (battery, music, presets) |
| h70bx | H70B3/4/5/6/8, H707x, Lightwall/Curtain Pro — cell-graffiti panels |
| h6630 | H6630(285) Gaming Pixel Light, delegates to `tablelampv1` H6078-Pro graffiti |
| h7004 | H7004 (plant grow, 4:1/6:1/8:1 red:blue) |
| h7017 | H7017 (plant grow) |
| h7014 | H7014 smart plug (cloud) |

---

## A. Classic base2light RGBIC strip/TV/car families

These reuse the **common base2light command set** almost entirely. Mode opcode `0x05`,
sub-mode selector at `byte[2]`. Deviations from the common set are below.

### A.1 Mode sub-mode selectors

From `Mode.parseSubMode()`:

| Family | Color (default) | Scenes | NewDiy | Music | Other |
|---|---|---|---|---|---|
| h6159 | 2 | 4 | 10 (0x0A) | 3 / 14(0x0E `ParamsSubMode4Music`) | — |
| h6160 | 2 | 4 | 10 | 3 | v1 strip color variant (`v1/SubModeColorV1`) |
| h613839 | 2 | 4 | 10 | 3 / V1 / V2 | — |
| h612526 | 2 | 4 | 10 | 3 | `Mode4ColorStrip` |
| h6181 | 2 | 4 | 10 | — | (no music submode) |
| h6182 | 2 | 4 | 10 | 3 | — |
| h6185 | 2 | 4 | 10 | (mic) | Rhythm UI builders |

### A.2 SubModeColor (cmd `0x02`) — shared layout

`h6159/ble/SubModeColor.getWriteBytes()` (identical in h6160, h613839, h6181, h6182,
h6185, h612526):

```
byte[0] = 0x02            sub-mode = color
byte[1..3] = R, G, B      primary color (ColorUtils.getRgb)
byte[4] = flag            f124246b: 0 = single color, 1 = "other"/segment mode
byte[5..7] = R2, G2, B2   secondary/segment color (f124247c)
```
Parse (`SubModeColor.parse`): `[0..2]`=RGB, `[3]`=flag, `[4..6]`=2nd RGB.
Source: `com/govee/h6159/ble/SubModeColor.java:getWriteBytes/parse`.

Scenes (cmd 4) and NewDiy (cmd 10) both write `{cmd, lo, hi}` where the effect/diy code is
a little-endian 2-byte via `BleUtil.getSignedBytesFor2(code, false)`; parse reads
`getSignedShort(b[1], b[0])`. Standard common-set.

### A.3 Music sub-modes

- h6159/h613839 have **three** music encoders chosen by version:
  `SubModeMusic` (cmd 3, legacy), `SubModeMusicV1`, `SubModeMusicV2` (cmd 3, new-order),
  plus `ParamsSubMode4Music` (selector **14 / 0x0E**).
- `SubModeMusicV2.getWriteBytes()` (`h6159`): three shapes —
  - new-music mode: `{cmd, musicCode, sensitivity}`
  - rhythm auto-color: `{cmd, autoColor?0:1, sensitivity, rhythm?0:1}`
  - rhythm fixed-color: `{cmd, autoColor?0:1, sensitivity, rhythm?0:1, 0,0,0}` then RGB
    copied into `[4..6]`.
  Source: `com/govee/h6159/ble/SubModeMusicV2.java:getWriteBytes`.
- "support_new_order" mic is version-gated per SKU (e.g. H6159/H6110/H6109/H614B/H614E ≥
  `1.04.05`; H6160 ≥ `1.04.05`, H6163/H6117 ≥ `1.05.00`). Source: `*/sku/Support.java`.

### A.4 Family-specific opcodes / controllers (beyond common set)

| Family | Class | Opcode (byte[1]) | Payload / role |
|---|---|---|---|
| h6181, h6182, h6185 | `MultipleDiyController` | variable (`this.f…g`, multi-packet DIY) | uploads full DIY effect blob (A1 multi-write) |
| h6185 | `MicController`, `scenes/Rhythm*` | mode/feature | "rhythm" scene builders (switch/color/colorTemp/diy/scene/effect rhythm UIs) |
| h612526 | `GradualController` | **0x14 (20)** | `q() = {gradualFlag}` — gradual on/off |
| h612526 | `LightNumController` | **0x0F (15)** | light/IC count |
| h612526 | `ReadLightColorController`, `Mode4ColorStrip` | read/mode | per-LED color readback for strip |
| h6160 | `v1/Gradual4BleWifiController(V1)`, `v1/BulbStringColorController`, `v1/Mode4ColorStrip` | mode | bulb-string / color-strip v1 variant |

`h6182` adds `AbsWifiCmdBuilder` + Wifi notify parse (BLE+Wi-Fi combo TV strip) but the
BLE control bytes are the common set above.

---

## B. Segment-addressable "new color" protocol families

h604a, h705a, h70b1/h70b2, h6057 share a **newer color sub-mode (cmd `0x15` = 21)** that
carries per-segment selection as a bitmask, and each adds a rich set of device-specific
feature opcodes. Mode opcode is still `0x05`.

### B.1 Mode sub-mode selectors

| Family | Color | Scenes | NewDiy | Music | Video | Game | Source |
|---|---|---|---|---|---|---|---|
| h604a | 21/default | 4 | 10 | 19 (0x13) | **0** | — | `h604a/ble/Mode.java` |
| h705a | 21/default | 4 | 10 | 19 (0x13) | — | — | `h705a/mode/Mode.java` |
| h6057 | 13 (0x0D)* | scenesV2 | 10 | music | — | 11 (0x0B) | `h6057/origin/ble/SubMode*` |
| h70b1 | new-color | scenes | diy | music | — | — | `h70b1/origin/ble/Mode.java` |

\* h6057 SubModeColor uses the **older cmd `0x0D`** shape (see B.4), not the cmd-0x15
segment shape — it is single-zone, but the family otherwise belongs to this newer-protocol
cluster because of its large feature-opcode set.

### B.2 SubModeColor cmd `0x15` (21) — segment bitmask layout (h705a, h604a)

`h705a/mode/color/SubModeColor.getWriteBytes()` builds a **17-byte** sub-payload:

```
byte[0]  = 0x15 (subModeCommandType = 21)
byte[1]  = mode: 1 = whole-string RGB+colorTemp, 2 = segment-index mode
─ mode 1 (byte[1]==1):
  byte[2..4]  = R, G, B            (ColorUtils.Companion.m → RGB)
  byte[5..6]  = colorTemp          (getSignedBytesFor2(kelvin, true), little-endian) — only if temp!=0
  byte[7..9]  = colorTemp RGB      (rendered white point) — only if temp!=0
  byte[10] = segment bitmask  segments 0..7   (bit i set ⇒ segment i selected)
  byte[11] = segment bitmask  segments 8..15
  byte[12] = segment bitmask  segments 16..23
  byte[13] = segment bitmask  segments 24..31
  byte[14] = segment bitmask  segments 32..39
─ mode 2 (byte[1]==2):
  byte[2]  = segment index value (f126213d)
  byte[3]  = bitmask segments 0..7
  byte[4]  = bitmask segments 8..15
  byte[5]  = bitmask segments 16..23
  byte[6]  = bitmask segments 24..31
  byte[14] = bitmask segments 32..39
```
Up to 40 segments addressable. Source:
`com/govee/h705a/mode/color/SubModeColor.java:getWriteBytes` (cmd value at `:538`).

`h604a/ble/SubModeColor.java` (cmd `0x15`, `:318`) is the **same** scheme but capped at 3
bitmask bytes (≤24 segments) in mode 1: `byte[10]` segs 0..7, `byte[11]` segs 8..15,
`byte[12]` segs 16..23; mode 2 mirror. Source: `com/govee/h604a/ble/SubModeColor.java`.

### B.3 h604a (DreamView G1/Pro/S) — video sync + IC/compose opcodes

`SubModeVideo` (mode sub-selector **0**, `subModeCommandType = 0`), `getWriteBytes()`
8 bytes:
```
byte[0] = 0x00            sub-mode = video
byte[1] = f120785e        on/off-ish flag
byte[2] = vividness/saturation (f120784d, 0..100)
byte[3] = scene/region    = f120782b (if f120783c!=0; if pactType2==2 && ==1 → 4) else f120781a
byte[4] = f120783c        camera-region enabled flag
byte[5] = f120786f        (saturation-2, 0..100)
byte[6] = f120787g        (extra param)
```
Source: `com/govee/h604a/ble/SubModeVideo.java:getWriteBytes` (cmd `0`, `:211`).

h604a feature controllers (opcode at byte[1]):

| Controller | Opcode | Role |
|---|---|---|
| `SwapLightController` | 0x34 (52) | swap light belts |
| `StartTimeController` | 0x35 (53) | start-time / sync timing |
| `ComposeLightController`, `ComposeLightHeartController` | 0x36 (54) | compose multi-belt layout / heartbeat |
| `ControllerIcNum` | 0x40 (64) | read IC count |
| `Controller4OnOffMemory` | 0x41 (65) | power-on memory |
| `CaliLightBeltController` | 0xA7 (-89) | calibrate light belt |
| `CheckLightController` | 0xAA (-86, read-type) | check-light query |
| `MultiMusicController` | variable (`f120804i`) | multi-music upload |

Notify parses: `CaliLightParse`, `CheckLightParse`, `CheckPodsParse` →
`EventNotifyCaliLight/CheckLight/CheckPods`. DIY templates for G1S (h604b): chase /
colorful / paomadeng (marquee) / pileUp / swing under `newdiy/h604b/*`.

### B.4 h6057 (Night Light) — battery/music/preset opcodes

SubModeColor (`cmd 0x0D` = 13), single-zone:
```
byte[0] = 0x0D
byte[1..3] = R, G, B
byte[4..5] = colorTemp (getSignedBytesFor2(kelvin, true))
byte[6..8] = colorTemp RGB
```
Source: `com/govee/h6057/origin/ble/SubModeColor.java:getWriteBytes`.
SubModeGame (`cmd 0x0B` = 11): `{0x0B, gameCode}`.

h6057 feature controllers (opcode at byte[1], payload from `q()`):

| Controller | Opcode | Payload |
|---|---|---|
| `MultiPreSetColorController` | 0x0B (11) | multi-packet preset-color upload |
| `EnergySavingController` | 0x16 (22) | `{flag}` |
| `PreSetInfoController` | 0x24 (36) | preset-slot info |
| `PreSetColorController` | 0x25 (37) | preset color |
| `PreSetSceneController` | 0x26 (38) | preset scene |
| `Controller4PreviewEffect` | 0x27 (39) | `{type, p2, p1, p3, p4, (rgb>>16), (rgb>>8), rgb}` (preview) |
| `DeletePreSetSceneController` | 0x28 (40) | delete preset scene |
| `SortPreSetSceneController` | 0x29 (41) | reorder preset scenes |
| `Controller4PlayVoice` | 0x31 (49) | play voice |
| `Controller4PauseVoice` | 0x32 (50) | pause voice |
| `GetDetailInfoController` | 0x34 (52) | request detail/status |
| `WorryFreeAtNightController` | 0x36 (54) | `{enabled, startH, startM, endH, endM, p5, p6}` (night-mode schedule) |
| `PromptToneController` | 0x37 (55) | `{flag}` prompt tone on/off |
| `GuideLightController` | 0x38 (56) | `{flag}` night guide light |
| `LocalColorReadControllerV1`, `LocalColorSettingMultiControllerV1` | 0xA5 (-91) | local preset-color read / multi-set (multi-packet) |

Status notify (`h6057/origin/ble/notify/DeviceInfoNotifyParse.e()`): `switch(bArr[0] &
0xFF)` selector → case 1 main-switch, 2 brightness, 3 mode, 4 `(b1,b2)` color, 5..7
further status; emits `EventNotifyMainSwitch/.../Color/...`. Battery & high-temp
notifications via `EventNotifyBatteryInfo` (h6057 is a battery night-light).

### B.5 h70b1 / h70b2 (Curtain Lights / Lightwall, older protocol)

`SplicingController` opcode **0x40 (64)**, `q()`:
```
exit splicing  (f126772f == -1):  {0x02, 0x00}
enter splicing (color != -1):     {0x02, 0x01, R, G, B}   (ColorUtils.n(color))
```
Source: `com/govee/h70b1/origin/ble/SplicingController.java`. h70b2 reuses the same
opcode 0x40 (`h70b2/origin/controller/SplicingController.java`).
`DiyModeComposeController` uploads composed DIY; `BrightnessNotifyParse` opcode **0x20
(32)** → `EventBrightnessNotify(getUnsignedByte(b[0]))`.

`h70b1/origin/pact/Support` encodes per-goodsType **scene effect codes** and **music
codes** as bytes, e.g. goodsType-dependent maps returning effect ids
{604,605,645,646,647,467,…} and music bytes {83,91,52,53,54,24,36,37,93,92}. Source:
`h70b1/origin/pact/Support.java:a/b/c`.

---

## C. Cell-graffiti panel families (newer Kotlin protocol)

### C.1 h70bx (Lightwall / Curtain Pro)

h70bx uses the **Kotlin `base2light.kt` controller framework** (no legacy `Mode.java`):
- Frame builder: `kt.ble.AbsController.getNextCommBytes()` → `BleUtils.p(proType,
  commandType, extBytes)` (standard 20-byte frame; ext payload truncated to ≤17 bytes).
- Mode op goes through `kt.general_controller.ControllerMode` (server-driven mode op),
  invoked by `VM4H70BXNewDetail.syncOpMode()`.

`ControllerChangeSplicing` opcode **0x40 (64)**:
```
makeSplicingController(idx, dir, macList):
  byte[0] = 0x01
  byte[1] = idx (panel index)
  byte[2] = direction bitfield a(dir, idx):
              idx==0: dir==1 → 0b01100000 (0x60) else 0b01101100 (0x6C)
              idx==1: dir==1 → 0b10010000 (0x90) else 0b10011100 (0x9C)
              else   :          0b11011000 (0xD8)
  byte[3..] = packed MAC addresses (BleUtils.d(mac, true), 6 bytes each)
release form  b(): {0x01, 0xFF}
```
Source: `com/govee/h70bx/controller/ControllerChangeSplicing.java:a/b/c`.

**Cell-graffiti DIY** (`diy/protocol`): a nested main/sub effect byte stream uploaded via
multi-packet write. Main effect codes (`IMainEffectProtocol`):

| Effect | Code |
|---|---|
| BO_DONG (wave) | 1 |
| LIU_DONG (flow) | 2 |
| SUI_JI (random) | 3 |
| DUI_JI (stack/collide) | 4 |
| XIAN_XING (linear) | 5 |
| XUAN_ZHUAN (rotate) | 6 |
| YUN_RAN (render) | 7 |
| GIF | 93 (0x5D) |
| TU_YA (graffiti) | 94 (0x5E) |

Each main effect's `getBytes()` emits `{mainCode, ...subEffect.getBytes()}`. E.g.
`EffectLiuDong.getBytes()` = `{0x02} + subEffect.getBytes()`; sub-effect selector byte
chooses ShenSuo(1)/DieJia(2)/QiFu(3)/JiaoTi(4)/… Parse mirrors at the same offsets.
Source: `com/govee/h70bx/diy/protocol/EffectLiuDong.java`, sibling `SubEffect*.java`.
Effect-id constants (server effect ids) in `diy/protocol/EffectCodeManager.java`
(e.g. 467, 531–556, 604–663, 762/763). Other controllers: `ControllerReadSubDeviceVersion`,
`AfterConnectSuccessReadDeviceInfo/WifiInfo`, `DeviceInfoFromDevice`.

### C.2 h6630 (Gaming Pixel Light)

Thin wrapper: `h6630/detail/diy/advance/H6078ProGraffitiEffect` **delegates to the shared
`com.govee.tablelampv1` H6078-Pro graffiti machinery** (`H6078NewDiyConfig`,
`H6078ProGraffitiParse`). No h6630-specific frame bytes here — the cell-graffiti protocol
lives in `tablelampv1` (max 3 pages, `GraffitiCommonData`). Flag for follow-up if the
tablelampv1 graffiti wire format isn't covered by another section.

---

## D. Plant-grow lights (h7004, h7017)

Single dedicated opcode **0x0D (13)** `RedBlueController`:
```
byte[0] = 0x33/0xAA   write/read
byte[1] = 0x0D
byte[2] = redIntensity   (f…f)
byte[3] = blueIntensity  (f…g)
```
`q() = {(byte)red, (byte)blue}`; parse reads `getUnsignedByte(b[0])`=red,
`getUnsignedByte(b[1])`=blue → `EventRedBlue`. Sources:
`com/govee/h7004/ble/RedBlueController.java`, `com/govee/h7017/adjust/RedBlueController.java`.

The h7004 `Mode` sub-modes `SubModeRedBlue41/61/81` (cmd 1/2/3) are **SKU-shape
placeholders only** — `getWriteBytes()` returns `null`; they merely identify the panel's
red:blue LED ratio (4:1 / 6:1 / 8:1). Source: `com/govee/h7004/ble/Mode.java` +
`SubModeRedBlue*.java`. h7017 adds a `PlantModeInfo` (4-field schedule struct) for grow
timing UI; the wire command is still opcode 0x0D.

---

## E. h7014 — cloud relay plug (no BLE control)

`com.govee.h7014` is a **Wi-Fi/cloud smart plug**: only an `iot/` command set
(`CmdTurn`, `CmdDelayClose`, `CmdTimer`, `CmdStatusV0`, `Cmd`) and an AP-pairing flow
(`add/Ap*`). There is **no `ble/` package and no BLE control characteristic** — control is
cloud/IoT passthrough only. `scenes/SmartRoomOp` and `scenes/SwitchCmdBuilder` are
empty/stub. Treat H7014 as cloud-only for control purposes.

---

## Confidence & open questions

**Confidence: medium-high.** Byte layouts for the segment color (h705a/h604a), video sync
(h604a), plant grow (h7004/h7017), splicing (h70b1/h70bx), and the h6057 opcode table are
read directly from `getWriteBytes()/q()`. The classic strip families are confidently
common-set.

Open questions:
1. **h70bx full DIY frame envelope** — the main/sub effect codes are confirmed, but the
   exact multi-packet opcode/segmentation used by `ControllerMode`/`kt.general_controller`
   to ship the graffiti blob wasn't traced end-to-end (server-driven). Flagged.
2. **h6630 graffiti wire format** lives in `tablelampv1` (not in this section's dirs);
   needs the table-lamp section to cover the actual bytes.
3. **h6057 status notify cases 5–7** semantics (volume/play-status/etc.) inferred from
   `EventNotify*` class names, not byte-decoded.
4. **h705a `0x40/0x43/0x44/0x0F` controllers** (IcSegmentNum=0x40, CheckIc=0x43,
   CutCali=0x44, SegmentSetting=0x0F) payloads captured (see below) but field meanings
   beyond IC/segment counts are partial.

### h705a feature-opcode quick reference (captured)

| Controller | Opcode | Payload `q()` |
|---|---|---|
| `SegmentSettingController` | 0x0F (15) | `{segmentNum}` |
| `IcSegmentNumController` | 0x40 (64) | parse → `getSignedShort(b0,b1)` + `b2` (IC/segment count) |
| `CheckIcController` | 0x43 (67) | `{b1, b2, (byte)i}` |
| `CutCaliController` | 0x44 (68) | `{1}` / `{0}` / `{2, g, h}` (start/end/calibrate) |
| `SetSegmentIcMultiController` | 0x43 (67), sub 0x0A | `{flag} + writeBytes` (multi-packet IC map) |

Sources: `com/govee/h705a/ble/controller/*.java`.
