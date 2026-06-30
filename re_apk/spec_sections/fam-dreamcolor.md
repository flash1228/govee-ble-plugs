# Family: DreamColor v1 / v2 RGBIC strips (`fam-dreamcolor`)

Source roots:
- `base/sources/com/govee/dreamcolorlightv1/**` (package `dreamcolorlightv1`)
- `base/sources/com/govee/dreamcolorlightv2/**` (package `dreamcolorlightv2`)
- pact/support: `base/sources/com/govee/base2home/pact/support/Support4DreamColorV1.java`, `Support4DreamColorLightV2.java`, `OldDreamColorUtil.java`, `DreamColorLightBleWifiV2Util.java`

These are the canonical RGBIC **segment** strips. Both packages share an identical command/sub-mode byte layout; the `v2` package mostly adds multi-IC music variants and the BLE+IoT (`bleiot`) plumbing. **Both packages emit the same on-wire frames** — the split is app-side UI/protocol-routing, not a wire difference.

## Transport / framing

Standard Govee light framing (see `GOVEE_BLE_PROTOCOL.md`):
- 20-byte frame `[type][cmd][payload...][BCC=XOR(0..18)]`; `type` `0x33`=write, `0xAA`=read, notify `0xEE`.
- GATT service `...1910`, unified char `...2b11`.
- Multi-packet payloads (DIY graffiti, per-segment color/brightness) use the common `0xA1`/`0xA2` chunking from base2light.

These strips are **BLE-controllable (connection-oriented)**, not broadcast-only. The `add/**` and `add/v3/**` `BleBroadcastProcessor*` classes are pairing/onboarding click handlers (they read SKU/goodsType/Protocol from the scan record and open a connect dialog) — they do **not** carry control state in adverts. BLE-WiFi members (`H61B1/H61B5/H61E0/H61E1/H80B5`, goodsType 123) also accept the same frames over their WiFi/IoT path.

## Common set (reused, not device-specific)

On/off `0x01`, brightness `0x04`, mode `0x05` come from base2light `AbsBleCommProtocol` / `AbsModeController`. Confirmed: `AbsModeController.getCommandType()` = `(byte)5` (`base2light/ble/controller/AbsModeController.java:35`). A mode write is therefore:

```
33 05 <subModeCommandType> <subMode payload...> 00.. BCC
       ^byte[2] = sub-mode selector
```

`AbsMode.getWriteBytes()` just returns `subMode.getWriteBytes()`, whose `[0]` is `subModeCommandType()` → lands at frame byte[2]. All sub-mode selectors below are that byte[2].

## Sub-mode selector map (byte[2] under cmd `0x05`)

| byte[2] | Sub-mode | Class (dreamcolorlightv1/ble) | Notes |
|---|---|---|---|
| `0x0B` (11) | **Segment color v1** | `SubModeColor`, `SubModeColorV2`*…* | 15-seg, RGB + bitmask |
| `0x15` (21) | **Segment color v2** | `SubModeColorV2` / `V3` (10-seg) | RGB + colortemp + per-seg brightness; sub-type at byte[3] |
| `0x04` (4)  | Scene apply | `SubModeScenes` | effect id (2 bytes) |
| `0x0A` (10) | New DIY (RGBIC) | `SubModeNewDiy` | diy code (2 bytes) |
| `0x11` (17) | Music (old) | `SubModeMusic` / `SubModeMusicV2` | effect 16/17/18/19 |
| `0x13` (19) | Music v1 | `SubModeMusicV1` / `SubModeMusicV3` | effect + sub-channel byte |
| `0x16` (22) | Music (shared/new) | base2light `SubModeAbsMusic` | common-set music |

`Mode.parseWriteSubMode()` / `Mode.parseSubMode()` (`dreamcolorlightv1/ble/Mode.java`) is the authoritative dispatch on byte[2]; for `0x15` it picks `SubModeColorV3` when `i6==1` (10-seg goodsType) else `SubModeColorV2`.

---

## Segment color **v1** — selector `0x0B` (`SubModeColor.getWriteBytes`)

15 segments. Single color applied to a selected subset; the app emits one frame per distinct color (`makeSubModeColor(Colors)` groups segments by color into multiple `ModeController`s). Sub-mode payload (8 bytes; lands at frame byte[2..]):

| off (in submode) | frame byte | meaning |
|---|---|---|
| 0 | 2 | `0x0B` selector |
| 1 | 3 | R |
| 2 | 4 | G |
| 3 | 5 | B |
| 4 | 6 | segment bitmask, segs 0–7 (bit0=seg0 … bit7=seg7) |
| 5 | 7 | segment bitmask, segs 8–14 (bit0=seg8 … bit6=seg14) |

Parse-back from a write frame: `SubModeColor.parseSubModeColor4Write` reads RGB from bytes[0..2] and two `parseBytes4Bit` masks. Device→app position-color report: `parsePosColor` reads RGB at bytes[3..5], masks at bytes[6] (`parseBytes4BitReverse`, segs0–7) and bytes[7] (segs8–14).

The `dreamcolorlightv2/ble/SubModeColor.java` is byte-identical (selector `0x0B`, 15-seg, same two-mask layout, lines 265–306).

---

## Segment color **v2** — selector `0x15` (`SubModeColorV2.getWriteBytes`)

The richer RGBIC format. A **sub-type** discriminator sits at submode-offset 1 (= frame byte[3]). Default segment count = 15 (`SubModeColorV2`), with 10-seg (`SubModeColorV3`) and 18-seg (H61A9) variants. Clearest reference impl is `dreamcolorlightv2/ble/SubModeColorV2.java` (methods `f()`/`e()`/type-3).

### Sub-type 1 — color (+ optional colortemp) — `f()`
12-byte submode payload:

| submode off | frame byte | meaning |
|---|---|---|
| 0 | 2 | `0x15` |
| 1 | 3 | `0x01` (sub-type: color) |
| 2–4 | 4–6 | R,G,B (primary color) |
| 5–6 | 7–8 | color-temp Kelvin, signed 2-byte (`getSignedBytesFor2(k,true)`); `0` = pure RGB |
| 7–9 | 9–11 | colortemp-equivalent R,G,B (used when Kelvin>0) |
| 10 | 12 | segment bitmask segs 0–7 |
| 11 | 13 | segment bitmask segs 8–14 |

(15-seg uses bytes 10/11 for the two masks. The v1-package `SubModeColorV2` builds the mask via `BleUtil.makeBytes4SelectPosByOneBit(...)` copied at submode-offset 10; for 18-seg H61A9 the mask spans 3 bytes 12/13/14 — see `parsePosColorWithBrightness`.)

### Sub-type 2 — color-by-index — `e()`
5-byte submode payload: `[0]=0x15 [1]=0x02 [2]=color index (f109474h) [3]=mask segs0-7 [4]=mask segs8-14]`. Used when an indexed palette color is selected rather than literal RGB.

### Sub-type 3 — per-segment brightness — type-3 branch of `getWriteBytes`
`[0]=0x15 [1]=0x03 [2..]= one brightness byte per segment` (15 bytes for 15-seg). For 18-seg the array is split/paged: v1-package `SubModeColorV2.getWriteBytes` sets `[2]=1` then 14 brightness bytes for the first page, `[2]=2` for the remainder (`f109115j` selects page); see lines 798–817. Device→app brightness report parsed by `parsePosColorWithBrightness` (byte[3]==1 → color page, ==3 → brightness page).

Device→app color report (`SubModeColorV2.parsePosColor`): RGB at bytes[4..6], colortemp short at bytes[7..8], colortemp-RGB at bytes[9..11], masks at bytes[12]/[13] (reverse bit order).

### Segment-count selection (which color format / how many segments)
`dreamcolorlightv1/pact/Support.java`:
- `isSubModeColorPiece10(gt)` → `gt==75 || gt==187` (H619A) → `SubModeColorV3` (10 seg)
- `isSubModeColorPiece12(gt)` → `gt==83` (H619Z)
- `isSubModeColorPiece18(gt)` → `isGoodsTypeH61A9` (gt 204, H61A9) → 18-seg path in `SubModeColorV2`
- `isSubModeColorPiece20(gt)` → `gt==175` (H61BE)
- otherwise 15 segments (`SubModeColorV2.f109105n` default 15)

---

## Scene apply — selector `0x04` (`SubModeScenes`)

3-byte submode: `[0]=0x04 [1..2]=effect id` via `BleUtil.getSignedBytesFor2(effect,false)` (little-endian-ish: write `signedBytesFor2[0],[1]`; parse reads `getSignedShort(bArr[1],bArr[0])`). Scene catalog comes from cloud/`ScenesV0.java`; the strip only receives the numeric effect id. Identical in both packages (`dreamcolorlightv2/ble/SubModeScenes.java` selector `0x04`).

## DIY — selector `0x0A` "new DIY" (`SubModeNewDiy`) + graffiti

- **Apply a stored DIY effect:** `SubModeNewDiy.getWriteBytes` = `[0]=0x0A [1..2]=diyCode` (`getSignedBytesFor2(code,false)`). Just selects a slot already programmed into the device.
- **Programming DIY / graffiti** (the actual per-LED frames) is delegated to the common base2light DIY engine, not a device-specific opcode here. `pact/ble/AbsDiyOp4Ble.java` routes to:
  - `OpDiyCommDialog4Ble` / `OpDiyCommDialog4SquareBle` for classic `DiyProtocol`
  - `DiyGraffitiV2` (`ShareDiy.parseDiyGraffiti4Rgbic`) for RGBIC graffiti — written by the shared graffiti uploader (multi-packet) in base2light, gated by `Support.isBkProtocol(...)` (BK vs Telink chipset) and `Support.getDiyVersion(...)`.
  - `OpDiyCommDialog4BleV1/V2` and `…4SquareBleV1/V2` are graffiti-version-specific dialogs.
  So: **DIY-slot select is device-specific (`0x0A`), graffiti pixel upload is common-set.** Flag: exact graffiti packet layout lives in base2light `ac/diy`, out of this family's files.

## Music

Two opcodes, several payload shapes (effect id chooses shape). `getWriteBytes` source `dreamcolorlightv1/ble/SubModeMusic*.java`:

### Selector `0x11` (`SubModeMusic`, old)
- effect `16` (energetic): `[0]=0x11 [1]=effect(16) [2]=sensitivity(0–99)` (3 bytes, no color)
- effect `17` (rhythm): 8 bytes `[0]=0x11 [1]=17 [2]=sensitivity [3]=!dynamic(0/1) [4]=!autoColor(0/1) [5..7]=R,G,B` (RGB only when not autoColor)
- other effects (18/19): 7 bytes `[0]=0x11 [1]=effect [2]=sensitivity [3]=!autoColor [4..6]=R,G,B`

`SubModeMusicV2` is the same selector `0x11` with a "new music code" branch: if `Support.isNewMusicCode(code)` → 3-byte `[0x11, code, sensitivity]`; else same 7/8-byte shapes as above.

### Selector `0x13` (`SubModeMusicV1` / `V3`)
8 bytes: `[0]=0x13 [1]=effect [2]=sensitivity(0–99) [3]=sub-channel(f109191c) [4]=!autoColor [5..7]=R,G,B`. `V3` differs only in default effect id (3 vs 5) and uses `[3]=!dynamic`. New-music-code shortcut → 3-byte `[0x13, code, sensitivity]`.

`isNewMusicCode` (Support.java:1109) = membership in `AbsNewMusicEffect.newMusicCode4RgbicList`/`…4RgbList`. The `dreamcolorlightv2/ble/SubModeMusicMultiV1..V3` add multi-IC (per-segment) music for newer SKUs — same `0x11/0x13` selectors, longer payloads; flag for deeper RE if multi-IC music byte layout is needed.

---

## Device-specific opcodes (NOT under mode `0x05`)

These are top-level `cmd` bytes (frame byte[1]) — IC/segment configuration, unique to RGBIC strips. Source: `dreamcolorlightv1/ble/*Controller.java`.

| cmd (byte[1]) | dir | class | payload / parse |
|---|---|---|---|
| `0x0E` (14) | w/r | `LimitController` | write `[bool]`; read `[0]==1` → limit on. Power/length limit toggle. |
| `0x0F` (15) | r | `LightNumController` | read `[0]` = light/bulb count (>0 valid). |
| `0x14` (20) | w/r | `GradualController` | write `[gradual 0/1]` (smooth-change flag). |
| `0xA3` (-93) | w/r | `Gradual4BleWifiController` | BLE-WiFi variant of gradual; write frame `33 A3 <v>`, read frame `AA A3 …`. `parseGradual` reads validBytes[0]. |
| `0x40` (64,'@') | r | `ReadIcController` | read IC config; parse: short@[0..1], byte@[2], byte@[3]=?, short@[3..4]… Multi-frame `parseIc` keys on `bArr[1]=='@'`, returns `{short(2,3), b4, short(5,6), b7}`. |
| `0x42` (66) | w | `RefreshIcController` | empty payload; triggers device IC re-detect. |
| `0x46` (70) | w | `CheckIcController` | `[icIndex, icType, signed2(value)]` — set/validate IC count per segment. |
| `0x22` (34) | notify | `CheckIcNumParse` | notify (`0xEE 22 …`): `getSignedShort(b0,b1)` = detected IC count → `EventIcNotify`. |

`getBulbStringMaxNum(...)` in Support.java caps segment/IC counts per goodsType (e.g. H612x special-cased). Bulb-string color (vs strip segment) uses `BulbStringColorController*` / `BulbGroupColor*` — RGBIC bulb strings (e.g. H70A1/2/3 curtain/bulb-string), same `0x05`/`0x15` color path but addressed per bulb group.

---

## SKU / goodsType coverage

### dreamcolorlightv1 package (`pact/Support.java`)
SKUs registered: **H6102, H6116, H6117, H611B, H611Z, H6123, H6125, H6126, H6127, H612A–H612F, H612x, H6145–H6147, H614C, H6161, H6163, H6168, H616C/D/E, H6171, H6172, H6173, H6175, H6176, H617A/B/C, H617E, H617F, H618A/B/C, H618F, H619A/B/C/D/E, H619Z, H61A0/1/2/3/5, H61A8, H61A9, H61B1, H61B2, H61B5, H61BA, H61BC, H61BE, H61E0, H61E1, H70A1/2/3, H802A, H80B5** (RGBIC Pro / Neon Rope / Outdoor strips, RGBICW, M1, DreamView strip members). goodsTypes incl. 71 (most Pro/Neon), 75 (H619A, 10-seg), 83 (H619Z, 12-seg), 204 (H61A9, 18-seg), 175 (H61BE, 20-seg), 123 (RGBICW/M1 BLE-WiFi), 176/178 (H61BA/BC), 193 (H70Ax).

### dreamcolorlightv2 package (`pact/Support.java`)
SKUs: **H6102, H6116, H6117, H611A, H6125, H6126, H6127, H6143, H6144, H6145, H6146, H6147, H6161, H6163, H6171, H6184** — overlap with v1 plus newer multi-IC-music members (H6143/4, H6184). Same wire protocol; routing differs (`isUi4BleIotProtocol4*`, Telink vs BK via `isTelinkBle`/`isBkProtocol`).

## Open questions / flags
- RGBIC **graffiti pixel-upload** packet layout is in shared base2light `ac/diy` (multi-packet), not these files — not byte-mapped here.
- **Multi-IC music** (`dreamcolorlightv2 SubModeMusicMultiV1..V3`) payload bytes not fully mapped (selectors `0x11`/`0x13`, longer per-segment forms).
- `ReadIcController` byte semantics (which field is IC-type vs count vs per-IC LED count) inferred from field order; not cross-checked against a live capture.
- `getSignedBytesFor2(x,false/true)` endianness: scenes/diy use `false`, colortemp uses `true`; treat as little-endian write with `getSignedShort(b1,b0)` read.
