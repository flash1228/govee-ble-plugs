# Family: RGBIC lights (`com.govee.rgbiclight` super-family) — `fam-rgbic`

Scope: the `com.govee.rgbiclight` module and the per-SKU `Support*`/`pact`/`mode/*`
classes it hosts. This is the "modern detail" (`base2light.pact.newdetail`) architecture:
the rgbiclight classes are mostly **UI delegates + version pickers**; the actual frame
byte layouts are built by shared `base2light` builders that this module selects into.
Everything here is **connection-controlled BLE** (no broadcast-only control surface found
in this package — see §8).

All frames are the standard 20-byte `[type][opcode][payload…][BCC]` (§3 of master doc).
jadx prints signed bytes; hex via `(v & 0xFF)`.

---

## 1. Devices covered (goodsType / SKU)

The package registers light SKUs (`category 0` lights plus RGBIC sub-goodsTypes 11/13 and
newer panel goodsTypes). goodsType values cross-checked against `_sku_catalog.md`.

| SKU | goodsType | Support class | notes |
|---|---|---|---|
| H6105 | 0 | `Support4H6105` | TV backlight; `Diy4H6105` |
| H6107/H6116/H6127/H6161 | 0 (H6116/H6127=50, H6161=30) | `Support4H6127` | version gate `10120`; `Scenes4H6127`, `Scenes4H6107` |
| H6109/H6110/H6159 | 0 | `SupportV2`/common | strip lights, common set |
| H6119 | 0 (gt 12) | `SupportH6119` | car LED; **Telink-OTA variant uses music selector 0x0C** (see §5) |
| H6129 | 0 | `Support4H6129` | `Diy4H6129` |
| H6143/H6144 | 21 | `Support4DreamColorLightV2` | DreamColor v2 RGBIC strips |
| H6163/H6117/H6125/H6126/H6102 | 0/50 | `Support4DreamColorLightV2` | DreamColor family |
| H6184 | 11 | `Support4H6184` | car underglow; `Diy4H6184` |
| H6185 | 0 | `SupportH6185` | car underglow (`com.govee.h6185.sku.Sku`) |
| H61A9 | 204 | (rgbiclight) | outdoor neon; `ColorMode4H61A9` |
| H61B5 / H80B5 | 123 | `Support.A()` | gated `>=10121` |
| H61BE | 175 | (rgbiclight) | RGBICW; high-color/graffiti path (`mode/highcolor`, `newdiy`) |
| H61C5 | 141 | `Support4H61C5` | RGBIC neon rope |
| H6671/H6672 | 332 (also 351/352) | `SupportV2` | RGBWIC TV backlight (4-color: W channel) |
| BareLightV1 SKUs (H6145/H6146/H6147/H6171…) | 13 | `Support4BareLightV1` | bare-light v1 |

BLE transport: standard modern service `…1910`, unified char `…2b11`
(`rgbiclight/ble/BleComm.java` hard-codes both). Identical to base.

---

## 2. Common set vs deviations

This family **reuses the base2light common command set** for on/off (`0x01`),
brightness (`0x04`), and the `0x05` mode command. Color/scene/music/DIY are all carried as
**sub-modes of opcode `0x05`** (mode), or as multi-packet controllers with their own
commandType. The device-specific work is purely (a) which SKUs map in (§1) and (b) which
sub-mode/selector variant + which `Bytes` builder version is chosen per device.

Mode wrapper: `ControllerMode.f69902n.e(byte[] payload)` →
`com.govee.base2light.kt.general_controller.ControllerMode`, whose `getCommandType()`
returns **`0x05`**. So every payload below is `byte[2…]` of a `33 05 …` frame; the
payload's first byte is the **color/mode sub-mode selector**.
Source: `base2light/kt/general_controller/ControllerMode.java` (`f69904k = (byte)5`).

Encoding helpers (authoritative):
- **RGB** = `ColorUtils.n(color)` → `[R,G,B]` 3 bytes, plain R,G,B order
  (`base2kt/utils/ColorUtils.java`).
- **Kelvin / 16-bit** = `BleUtils.C(v,true)` and `BleUtil.getSignedBytesFor2(v,true)` →
  **big-endian** `[hi,lo]` (`base2kt/utils/BleUtils.java:C`).
- **Segment selection mask, ≤16 segments** = `makeSelectedTwoBytes(posSet,true,…)` (`X()`):
  2 bytes, byte0 = segments 0–7, byte1 = segments 8–15, **bit-reversed within each byte
  so bit value `1<<k` ⇒ segment k** (`z5=true` reverses) — i.e. LSB = lowest-index segment.
- **Segment mask, >16 segments** = `BleUtils.W(posSet,true)`: `ceil(N/8)` bytes, same
  per-byte bit-reversed packing. Used for high-density strips/neon.
- White/black sentinels: `ColorUtils.Q()` = white `(255,255,255)`, `E()` = black `(0,0,0)`.

---

## 3. Color / RGBIC segment sub-modes (opcode 0x05)

All layouts from `base2light/pact/newdetail/config/fuc/color/Bytes.java` (the builder set
the rgbiclight `ColorControllerConfig` selects by `colorVersion`). Offsets are **within the
0x05 payload** (so payload[0] = sub-mode selector = frame byte[2]).

| Selector (payload[0..1]) | Builder | Layout (payload bytes) | Meaning |
|---|---|---|---|
| `0x02` | `a(c)` | `02 R G B` | whole-strip single RGB |
| `0x02` | `o(c1,c2)` | `02 R1 G1 B1 01 R2 G2 B2` | two-color whole-strip |
| `0x02` | `y(kelvin)` | `02 FF FF FF 01 Rk Gk Bk` | whole-strip white + color-temp tint |
| `0x08` | `b(c,posSet)` | `08 <2B segMask> R G B` (mask at [1..2], RGB at [4..6]) | per-segment single color |
| `0x0B` (11) | `d(c,posSet)` | `0B R G B <2B segMask@4>` | per-segment color (RGB-first) |
| `0x0B` | `c(k,bri,posSet)` | `0B Rk Gk Bk briHi briLo seg0_7 seg8_14` (8-byte) | color-temp + brightness + 15-seg mask |
| `0x0B` | `z(kelvin,n)` | `0B Rk Gk Bk <2B mask of n>` | color-temp all-segments |
| `0x0C` (12) | `e(c,posSet)` | `0C 02 01 R G B <2B segMask>` | color with sub-selector 02/01 |
| `0x0D` (13) | `f(c)` | `0D R G B` | whole-strip color-temp-as-RGB |
| `0x0D` | `A(kelvin,which)` | `0D Rw Gw Bw kHi kLo [Rk Gk Bk]` | kelvin: white-pt + 16-bit kelvin + tint |
| `0x0D` | `p(c,kelvin)` | `0D R G B kHi kLo [Rk Gk Bk]` | color + kelvin |
| `0x14` (20) | `g(c,posSet)` | `14 R G B <segMask via X@7>` | segment color (gradient form) |
| `0x14` | `k(c,posSet)` | `14 <flagbits@1> [R G B]×≤5` | up-to-5-segment inline colors, bitmap@[1] |
| `0x14` | `q(c,kelvin,posSet)` | `14 FF FF FF kHi kLo R G B <2B mask>` | white+kelvin+color+mask |
| `0x14 0x01` | `v(bool)` | `14 01/00` | toggle (gradient on/off flag) |
| `0x2C` (44) `0x03` | `E(kelvin)` | `2C 03 kHi kLo` | color-temp set (selector 2C/03) |
| `0x2C 0x04` | `s(c,kelvin)` | `2C 04 R G B kHi kLo` | color + kelvin (2C/04) |

### 3.1 The `0x15` RGBIC multi-segment family (selector `0x15`, sub at payload[1])

This is the principal RGBIC per-segment protocol. Frame = `33 05 15 <sub> …`.

| `0x15` sub | Builder | Layout | Meaning |
|---|---|---|---|
| `0x15 0x01` | `h(c,posSet)` | `15 01 R G B <segMask>` | per-segment single color |
| `0x15 0x01` | `l(c,posSet)` | `15 01 R G B <segMask@6>` | per-segment color (variant offset) |
| `0x15 0x01` | `r(c,kelvin,posSet,mode)` | `15 01 R G B kHi kLo R G B <segMask>` (white-pt logic by `mode` 0..3) | color+kelvin per-segment, gamma-aware |
| `0x15 0x01` | `u(kelvin,posSet,c)` | `15 01 Rk Gk Bk kHi kLo <segMask>` | color-temp per-segment |
| `0x15 0x02` | `G(bri,posSet)` | `15 02 <bri> <segMask@3 via W/X>` | set ONE brightness value to selected segments |
| `0x15 0x03` | `F(briArray)` | `15 03 b0 b1 … b14` (≤15 segs) | **per-segment brightness array** |
| `0x15 0x03` | `I(idx,briArray)` | `15 03 <startIdx> b… (≤14)` | brightness array with start index (paging) |
| `0x15 0x04` | `m(idx,colorSet)` | `15 04 <startIdx> [R G B]×≤4` | **per-segment color array (paged, 4/packet)** |
| `0x15 0x04` | `D(c)` | `15 04 cHi cLo` (kelvin form) | single color/temp |
| `0x15 0x05` | `n(colorSet[3],posSet)` | `15 05 R1G1B1 R2G2B2 R3G3B3 <segMask>` | **3-color gradient across selected segments** |
| `0x15 0x05` | `H(idx,posSet)` | `15 05 <flag 1/2/3> <idx>` | gradient direction/flag |
| `0x15 0x15` (when >16 segs in `C()`) | `kelvinByte0x15` | `15 01 Rw Gw Bw kHi kLo Rk Gk Bk <mask, truncated 7B>` | high-segment-count kelvin (analytics-tagged) |

Notes:
- `F`/`I` (0x15 0x03) is the **brightness-array** form; `m` (0x15 0x04) is the
  **color-array** form — these are how whole-strip per-segment state is pushed, paged at
  4 colors / 14 brightness per frame, indexed by payload[2].
- When `posSet.length > 16`, builders switch from `makeSelectedTwoBytes` (2-byte mask) to
  `W()` (`ceil(N/8)`-byte mask) and may truncate to fit 17-byte payload.

### 3.2 Multi-packet color strip (whole-strip gradient)
`MultiColorStripControllerNoEvent` (`base2light/kt/general_controller`) wraps
`MultipleColorStripControllerV1` → **commandType `0x40` (64)**, sent as **multi-write V1**
(`comType 3`, the `0xA3` MULTIPLE_WRITE_V1 path; chunked 16-byte). Used by
`ColorControllerConfig.d()/h()` for full color-effect (`EffectData.ColorEffect`) pushes,
often followed by `ControllerMode.e({21})` (a bare `0x05 15` "commit"/apply).

---

## 4. Scene apply (opcode 0x05 sub 0x04)

Local scene library apply is the simple static form:
```
33 05 04 <sceneCode> 00…00 BCC
```
`sceneCode` = `scenesItemBean.d().f73331c` cast to a **single byte**.
Source: `mode/scene/DelegateSceneV1.java:F()` and
`DelegateStaticScene4DreamColorLightV1.java` — both call
`ControllerMode.f69902n.e(new byte[]{4, (byte) code})`.

The scene catalog classes under `mode/scene/config/` (`Scene4H612526`, `Scenes4BleH6185`,
`Scenes4Dreamcolorlightv2`, `Scenes4H6127`, day/`Night` pairs, etc.) hold **scene metadata
only** (IDs/codes/names) — no extra byte builders. Cloud "effect"-scenes with downloaded
parameter bytes go through the shared `base2light` scene-effect multipacket controller
(not redefined in this package).

The `scenes/BleSwitchCmdBuilder.java` is the **smart-home automation** "switch" adapter
(builds a plain `SwitchController` on/off frame for Govee scenes), not a light scene.

---

## 5. Music / mic sub-modes (opcode 0x05)

Music payload selector byte `b6 = Protocols.b(info)` (`com.govee.rgbiclight.Protocols`):

| `b6` | when |
|---|---|
| `0x13` (19) | default / newest UI |
| `0x11` (17) | device supports `v1UIV1` or `v2UIV1`, or DreamColor v2 |
| `0x0C` (12) | **H6119 + Telink OTA** only |

Music **code remap** `Protocols.a(info,code)` swaps codes between UI generations:
`3↔17, 4↔18, 5↔16, 6↔19` (applied when `code ∉ c(info)` whitelist `{5,3,4,6}` or
`{16,17,18,19}` for UIV1).

Music frame payload (`Protocols.d()` for `b6==0x13`, the common shape):
```
13 <musicCode> <sensitivity> <subEffect> <colorFlag 1=manual/0=auto> [R G B if manual]
```
For `b6==0x0C` (H6119 Telink): `0C <code> <sens>` and, if `code==2`, append
`<colorFlag>[R G B]`, else append `<subEffect>`. For `b6==0x11`: like 0x13 but only emits
`<subEffect>` when `code==17`. (`Protocols.d()`.)

`mode/music/MusicMode.java` builds richer variants and, for **codes 7 / 48 / 49 / 55**,
emits a **two-controller** sequence: a `MultipleController4Music`
(**commandType `0x41` (65)**, multi-packet, carries a color list `[count][R G B]…[params]`)
followed by the `0x05` mode controller. Example (code 55):
`bArr = [count][R G B]×count [subEff0][subEff1][onoff]`.
Per-UI music selectors elsewhere:
- `MusicMode4DreamColorLightV2.java`: selector `0x11` (17), then
  `<subMode><sens>[subEff][R G B]`.
- `MusicMode4BareLightV1.java`: selector `0x0C` (12), then
  `<subMode><sens>[subEff0][subEff1][R G B]`; codes 48/49 add a trailing
  `0x0A,<speed>` / `<a><b>0x0A` tail and a `0x41` multi-packet color list.

`OldDevicePickSound` / `OldMusicConfig` handle the legacy mic "pick sound" path
(sensitivity-only `applySensitivity()` via a mode controller).

---

## 6. DIY

- **Standard DIY graffiti (V3)**: `DiyControllerNoEventV3_1` →
  `MultiDiyGraffitiControllerV3`, **commandType `0x57` (87)**, multi-write V1
  (`base2light/ble/controller/MultiDiyGraffitiControllerV3.java:getCommandType()=87`).
- **H61BE RGBIC graffiti (new path)**: `newdiy/RgbIcGraffitiShare0x084H61BE` →
  `MultiController.b(toBytes(), (byte)87, 2)` — same **commandType `0x57`**, **comType 2**
  (multi-write), share-type `0x08`. The DIY config (`newdiy/RgbicDiyConfig.java`) registers
  parsers `DiyProtocolParseShare0x00` + `RgbIcGraffitiShare0x08`.
- **H61BE high-color / wide-gamut enable**: before pushing a high-color graffiti,
  `mode/highcolor/DelegateHighColor4H61BE.java` and `DelegateNewHighColor4H61BE.java` send
  `ControllerMode.e(new byte[]{10, 32, 3})` → frame `33 05 0A 20 03 …` ("set tuYa mode"),
  bundled with a `DiyControllerNoEventV3_1` in one `Compose4DefWrite4Multi`.
- Per-SKU `Diy4H61xx` classes (`Diy4H6105/6119/6129/6184/61C3/GoodsType13`) only configure
  `DiySupportV1` UI metadata (e.g. `mix4EffectsNum = 4`), not new wire formats.

---

## 7. Status / read

Reads use the shared `base2light` controllers (HeartController, brightness/color/mode
read = `AA <opcode>` query frames). `VM4Light.java` / `h61050729/H6105VM4Light.java` /
`h667172/VM4LightH667172.java` drive `afterConnectedSingleReadDeviceInfo` polling of the
common opcodes; no rgbic-specific status opcode/notify parse beyond the common set was
found (notify match is by `(type,opcode)` per master §2.5). `EffectOp4Ble` exposes a
`heartBytes()` = `HeartController().getValue()` for the Govee-scenes keepalive.

---

## 8. Broadcast

No broadcast/advert parser exists in `com.govee.rgbiclight` (grep for
`scanRecord`/`manufacturer`/`getBroadcast` = none). These are **connection-controlled**
RGBIC lights — control and state both go over the GATT link, not BLE advertisements.

---

## 9. Confidence & open questions

- **High** on: opcode `0x05` = mode; the color sub-mode selector table and `0x15` segment
  family (read directly from `Bytes.java`); multi-color-strip `0x40`/MWV1; DIY `0x57`;
  music `0x41` multipacket + selectors `0x13/0x11/0x0C`; scene static apply `05 04 <code>`;
  H61BE high-color `05 0A 20 03`; segment-mask bit packing; RGB/kelvin byte order.
- **Medium**: exact `colorVersion → Bytes.fn` mapping per SKU lives in
  `base2light…config/fuc/color/Config.java` (18k lines) keyed by a version int chosen in
  `Support`; I documented the builders themselves rather than enumerating every
  version→builder edge. The `r()` white-point `mode 0..3` branch logic is gamma/temp
  handling — layout is certain, semantics of `mode` partially inferred.
- **Open**: 4-color RGBWIC (H6671/H6672, goodsType 332) W-channel encoding — `SupportV2`
  registers them and `h667172/*` exists, but the W byte position wasn't traced to a
  distinct builder here (likely a `0x15 0x04` color-array entry with an extra channel);
  flag for follow-up. Cloud effect-scene parameter-byte format (downloaded scenes) is in
  shared base2light, not this package.
