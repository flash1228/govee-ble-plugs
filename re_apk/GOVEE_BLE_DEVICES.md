# Govee BLE Devices — All-Device Companion Reference

**Source:** Reverse-engineered from the Govee Home Android app, version **7.5.20**
(`re_apk/decompiled/base/sources/...`), decompiled with jadx. jadx prints **signed**
decimals, so every negative byte below is given as hex via `(v & 0xFF)`
(`-86 → 0xAA`, `-95 → 0xA1`, `-18 → 0xEE`, `-120 → 0x88`, `-20 → 0xEC`).

This document is the **device catalog companion** to
[`GOVEE_BLE_PROTOCOL.md`](GOVEE_BLE_PROTOCOL.md). The protocol doc owns the framing,
crypto, broadcast pipeline, and the smart-plug command sets; **this doc owns the rest of the
fleet** — all light families, appliances, sensors, controllers, and gateways — with their
device-specific byte layouts.

---

## 1. Scope & the key insight

### 1.1 What this covers

Every device family shipped in app v7.5.20: RGB / RGBIC / DreamColor strips, bulbs &
spotlights, TV/immersion backlights & capture boxes, lamps, panels & newer-gen lights,
kitchen & air appliances, the full sensor fleet (TH / air / CO₂ / leak / BBQ probes), and
controllers/gateways. The 617-SKU catalog is at
[`spec_sections/_sku_catalog.md`](spec_sections/_sku_catalog.md).

### 1.2 The one insight that collapses the complexity

**Almost every Govee *light* speaks the same command set.** On/off (`0x01`), brightness
(`0x04`), and a mode opcode (`0x05`) carrying a sub-mode selector at `byte[2]` are defined
once in `com.govee.base2light.ble.controller.AbsModeController` (`getCommandType()==0x05`)
and reused everywhere. A per-family Java package does only two things:

1. **Registers** which `goodsType` / `(pactType, pactCode)` it claims (`pact/Support.java`).
2. **Defines the device-specific Mode/color/scene/music/DIY byte layouts** — i.e. which
   sub-mode selector value the firmware expects and how the color/segment bytes are packed.

So a mode-frame is always:

```
byte[0]=0x33(write)/0xAA(read)  byte[1]=0x05  byte[2]=<sub-mode selector>  byte[3..]=<sub-payload>  byte[19]=BCC
```

The selector value at `byte[2]` is the **main axis of per-family variation** (e.g. color is
`0x02` on old bulbs, `0x0D` on lamps, `0x0B`/`0x15` on RGBIC segment strips). Everything
below documents those selectors and payloads.

**A large fraction of modern SKUs have NO per-family package at all.** goodsTypes like 64
(bulbs), 209 (Floor Lamp 2), and essentially the entire 300–400 band resolve through the
**data-driven detail framework** (`base2light/pact/newdetail/**` + `skubusiness/**`): the app
downloads each device's capability/Mode descriptors from the cloud and renders them on the
*same* `base2light` common command set. For those SKUs the wire protocol **is** the common
set — no extra family opcodes ship in the APK.

### 1.3 Cross-links to the protocol doc

| Topic | See |
|---|---|
| 20-byte frame, BCC, multi-packet `0xA1/0xA2/0xA3`, notify `0xEE` | `GOVEE_BLE_PROTOCOL.md` §3 |
| GATT UUIDs (`…1910`/`…2b11` modern; Telink `…4857`), lifecycle, MTU | §2 |
| Session crypto (V1 ECB+RC4 / V2 GCM, `0xE7` handshake) + legacy secret `0xB1/0xB2` | §4 |
| Broadcast/advert parsing pipeline, `0x88EC` mfr-id, plug on/off bytes | §5 |
| Common light command set (full opcode tables) | §6.1 |
| Smart plugs H5080/82/83/85/89/5160/5161, H5086 energy plug | §6.2, §6.3 |

GATT for all light/appliance/sensor families below is the **modern default** service
`00010203-0405-0607-0809-0a0b0c0d1910` + unified write/notify char `…2b11`, unless a row
notes a Telink `…4857` channel (H5086 chart, H5151 gateway).

---

## 2. Device matrix (goodsType → family → SKUs → BLE? → command set)

This is the centerpiece index. A device is identified at runtime by **three** numbers, not
one: `goodsType` (product class), `pactType` (`Protocol.f41313a`, transport family), and
`pactCode` (`Protocol.f41314b`, revision). `supportPact()` matches on **both** goodsType and
the `(pactType,pactCode)` pair, which is why the **same goodsType can appear under several
packages** — the pair disambiguates which Mode layouts apply. All of them still build frames
with the one shared 20-byte builder.

### 2.1 Master goodsType → package → command-set table (explicit registrations)

Each row is a real `Pact.b()` / `DeviceGoodsType.b()` registration from that family's
`pact/Support.java`. "Command set" = where the device-specific byte layouts live; everything
also inherits the common set.

| goodsType(s) | Package | Representative SKUs | BLE? | Per-family layout source | This-doc § |
|---|---|---|---|---|---|
| 43, 50, 90, 307 | `com.govee.h5080.pact` | H5080/82/83/85/H5160/H5161/H5089 | **Yes** +broadcast | `h5080/ble/controller/**` | PROTOCOL §6.2 |
| 195 | `com.govee.h5086.pact` | H5086 Smart Plug Pro | **Yes** +broadcast +energy | `h5086/ble/controller/**` (Telink `…4857`) | PROTOCOL §6.3 |
| 13,17,18,19,70,71,73,74,75,83,123,136,175,176,178,187,193,204,207,234,262 | `dreamcolorlightv1` / `rgbiclight` | H6143-47, H617x, H618x, H619x, H61Ax neon, TV backlights | **Yes** | DreamColor v1 + rgbic | §3.1, §3.3 |
| 21 | `dreamcolorlightv2` / `rgbiclight` | H611A, H6143/4, H6184 RGBIC | **Yes** | DreamColor v2 | §3.3 |
| 44,141,351,352 | `com.govee.rgbiclight` | H7090 car; H61C2/3/5 neon; H617G/H618G | **Yes** | rgbic Mode/segment | §3.1 |
| 13 (bare) | `com.govee.barelightv1.pact` | H6145/6/7, H6171 bare RGBIC | **Yes** | bare-light Mode | §3.6 |
| 16 | `com.govee.homelightv1.pact` | H6148 RGBWW strip | **Yes** +WiFi | HomeLightV1 ScenesV0 | §3.6 |
| 1,2,6,12,16,39,40,68,78,108,143 | `com.govee.stringlightv2.pact` | H6121/H6170/H613x/H615x/H6178/H6192 | **Yes** | StringLight V2 | §3.2 |
| 12 | `tvlightv1` / `rgblight.h6179` | H6179 TV backlight | **Yes** | TV-light v1 | §3.5, §3.2 |
| 23,52,112 | `pact_tvlightv3` | H6053/H6056/H6046 TV light bars | **Yes** +WiFi | TV light v3 | §3.5 |
| 24 | `pact_tvlightv2` | H6198/H6199 DreamView T1S/T1 | **Yes** +WiFi | TV light v2 | §3.5 |
| 25 | `pact_tvlightv4` | H6049/H6054 DreamView P1/P1S | **Yes** +WiFi | TV light v4 | §3.5 |
| 82,120,138,142,172,192,243,360 | `pact_h605b` | H605B/C/D, H6601-6609, H8604, H2A40/41 | **Yes** | DreamView/AI-sync-box | §3.5 (cross-ref) |
| 95,109,122,133 | `com.govee.h604a.pact` | H604A/B/C/D DreamView G1 | **Yes** | DreamView G1 (cmd `0x15` seg) | §3.7 |
| 27,37,42,58,59,84,395 | `com.govee.hollowlamp.pact` | H6050/51/52/55/58/59/H1771 lamps | **Yes** | Hollow-lamp Mode | §3.4 |
| 22,128 | `com.govee.tablelampv1.pact` | H6052 Aura, H6078 Cylinder Floor Lamp | **Yes** | TableLamp v1/v2 | §3.4 |
| 104 | `com.govee.h6057.origin.pact` | H6057 Night Light | **Yes** | H6057 (battery presets) | §3.7 |
| 6 | `com.govee.carlightv1.pact` | H6118/H6194 car lights | **Yes** (groupable) | Car-light v1 | §3.4 |
| 3,5 | `com.govee.bulblightstringv1.pact` | H7002 string light | **Yes** | Bulb-string v1 | §3.2 |
| 125,141,180,184,240,250,394 | `com.govee.h705a.pact` | H705A-F Permanent, H706x Pro, H7067-9 Deck, H608x, H3401 | **Yes** | Permanent/outdoor seg (cmd `0x15`, ≤40 seg) | §3.7 |
| 134,185,216 | `com.govee.h70b1.origin.pact` | H70B1/B3-5/BC Curtain Lights | **Yes** | Curtain-light (splicing `0x40`) | §3.7 |
| 32 | `com.govee.pickupbox.pact` | H1161 Govee Sync (pickup box) | **Yes** | PickUpBox opcodes `0x10-0x43` | §3.5, §3.4 |
| 87,137,182,186 | `com.govee.h1162` | H1162/H1163/H1167/H1168 Music/Sync/Show boxes | **Yes** +WiFi | h1162 + Model1168 | §3.4 |
| 0–10,15,21,22 (legacy by pact pair) | `sku/h6102/h6104/h6105/h6127/h6129/h6159/h6160/h612526/h613839/h7022` | first-gen strips/bulbs | **Yes** | common + DreamColor-v1 | §3.7, §3.8 |
| 7,8,14,66,106,124,154,190,194,287,310,319,320,330,369 | `com.govee.thnew` | H5100-5112, H5074/75, H5179, H5106 air, H5140 CO₂, H5220, H5310 | **monitor-only** (broadcast state; BLE for config/history) | TH-new opcode map | §5 |
| 85,155,169,281,282,314,344 | `com.govee.pact_bbqnew` | H5198/99, H5196, H5191/92, H5194, H5610 BBQ probes | **BLE-connect monitor** + broadcast | BBQ multi-probe | §5.3 |
| 65 | `com.govee.h5151.pact` | H5151 BT-WiFi gateway | BLE provisioning + relay | Gateway (Telink `…4857`) | §6 |
| 158,291 | `com.govee.h5043.pact` | H5043/H5044/R5044 gateway 2 + sub-sensors | WiFi/IoT + BLE setup | Maker + Model4Tem/TemHum | §6 |
| 198 | `com.govee.h5042.pact` | H5042 gateway 1s + H5109 sub | WiFi/IoT + BLE setup | gateway Model | §6 |
| 99 | `com.govee.h7160` (`pact_h7160`) | H7160 humidifier | **Yes** | `base_h71xx` mode/child/abnormal | §4 |
| 117,211 | `com.govee.h7172` (`pact_h7172`) | H7172/H717D ice maker | **Yes** | `base_h71xx` ice-size/equip | §4 |
| (Air Treatment / Kitchen — many) | `base_h71xx` (split feature modules) | H7100-H7152, H7170-H717A, H713x, etc. | **per-module** (confirmed: H7160, H7172/H717D) | `base_h71xx` opcode singleton | §4 |

### 2.2 Categories with no per-SKU BLE control

| Category | SKUs (goodsType) | Capability |
|---|---|---|
| Controller → buttons/remotes | H5122/H5125/H5126 (131/144/145) | **Broadcast-only** scene triggers; no BLE control class in APK |
| Controller → water timer | H5901 (363) | Wi-Fi/cloud likely; no BLE module (flag) |
| Cloud relay plug | H7014 | **Cloud/IoT only** — no `ble/` package |
| Sensor → leak/motion/door/presence/pressure | H5121/23/27/29/30, H5054 | Broadcast-only / gateway-relayed; no per-SKU BLE control |
| Discontinued Wi-Fi-only | H5081 (gt 4), H5040/41 gateways | No BLE stack |

### 2.3 Data-driven (common-set-only) light goodsTypes

Not registered by any `pact/Support.java`; resolved via `newdetail` + `skubusiness` cloud
descriptors. Wire protocol **is** the common `base2light` set. Confirmed examples: **64**
(H6004-H6013 bulbs), **111** (downlights), **209** (Floor Lamp 2), **210/249** (table lamps),
**235/302/303/356/370/373/390** (ceiling lights), **261/264/299/239/246** (M1/COB strips),
**360/327** (TV Backlight 3), **376/377** (Floor Lamp 3), **386** (Permanent Lights 2 Pro),
and essentially the whole **300–400 band**. **Rule:** any catalog light SKU whose goodsType
is not in §2.1 → BLE-controllable via the common command set, no extra family opcodes.

### 2.4 How to classify any of the 617 SKUs

1. Look up its goodsType in `_sku_catalog.md`.
2. If goodsType is in §2.1 → use that package's layout section.
3. Else if its catalog category is a **light** (Indoor/Outdoor/LED Strip/Other Lights) → it
   is BLE-controllable via the common set (§2.3).
4. Else map by category in §2.2 (plug / sensor / gateway / appliance).

> **Caveat — many-to-many:** goodsType↔package is many-to-many; always check
> `(pactType,pactCode)` when a goodsType has multiple §2.1 rows (notably 12, 13, 16, 71, 141,
> 351, 352). The large trailing numbers in legacy `sku/` package constants are decompiler line
> artifacts, **not** goodsTypes. Many goodsType-0 catalog SKUs are discontinued/WiFi-only and
> ambiguous from goodsType alone.

---

## 3. Per-family light protocols

All frames are the standard 20-byte `[type][0x05][selector][sub-payload…][BCC]`. RGB encoding
= `ColorUtils.n(color)`/`getRgb()` → `[R,G,B]` plain order. Kelvin/16-bit = `BleUtils.C(v,true)`
= **big-endian** `[hi,lo]` (except where a layout notes `getSignedBytesFor2(v,false)` =
little-endian). Segment masks ≤16 segs = `makeSelectedTwoBytes` (LSB = lowest segment index);
>16 segs = `W()` (`ceil(N/8)` bytes).

### 3.1 RGBIC super-family (`com.govee.rgbiclight`)

Modern "detail" architecture: rgbiclight classes are mostly UI delegates + version pickers;
the byte layouts are built by shared `base2light` builders selected by `colorVersion`. All
control is **connection-oriented** (no broadcast control surface). Members include H6105,
H6107/16/27/61, H6109/10/59, H6119 (car), H6129, H6143/44 (DC v2), H6163/17/25/26/02, H6184
(car underglow), H6185, H61A9, H61B5/H80B5, H61BE, H61C5, H6671/72 (RGBWIC), bare-light SKUs.

**Color sub-modes (selector at payload[0] = frame byte[2])** — from
`base2light/pact/newdetail/config/fuc/color/Bytes.java`:

| Selector | Builder | Layout (frame byte[2]…) | Meaning |
|---|---|---|---|
| `0x02` | `a(c)` | `02 R G B` | whole-strip single RGB |
| `0x02` | `o(c1,c2)` | `02 R1 G1 B1 01 R2 G2 B2` | two-color whole-strip |
| `0x02` | `y(k)` | `02 FF FF FF 01 Rk Gk Bk` | white + color-temp tint |
| `0x08` | `b(c,pos)` | `08 <2B segMask> R G B` | per-segment single color |
| `0x0B` | `d(c,pos)` | `0B R G B <2B segMask@4>` | per-segment (RGB-first) |
| `0x0B` | `c(k,bri,pos)` | `0B Rk Gk Bk briHi briLo seg0_7 seg8_14` | color-temp + brightness + 15-seg mask |
| `0x0C` | `e(c,pos)` | `0C 02 01 R G B <2B segMask>` | color w/ sub-selector |
| `0x0D` | `f(c)` | `0D R G B` | whole-strip color-temp-as-RGB |
| `0x0D` | `p(c,k)` | `0D R G B kHi kLo [Rk Gk Bk]` | color + kelvin |
| `0x14` | `g(c,pos)` | `14 R G B <segMask@7>` | segment color (gradient form) |
| `0x14` | `k(c,pos)` | `14 <flagbits@1> [R G B]×≤5` | up-to-5 inline segment colors |
| `0x14 0x01` | `v(bool)` | `14 01/00` | gradient on/off toggle |
| `0x2C 0x03` | `E(k)` | `2C 03 kHi kLo` | color-temp set |
| `0x2C 0x04` | `s(c,k)` | `2C 04 R G B kHi kLo` | color + kelvin |

**The `0x15` RGBIC multi-segment family** (principal per-segment protocol; sub at payload[1]):

| `0x15` sub | Builder | Layout | Meaning |
|---|---|---|---|
| `0x15 0x01` | `h/l(c,pos)` | `15 01 R G B <segMask>` | per-segment single color |
| `0x15 0x01` | `r(c,k,pos,mode)` | `15 01 R G B kHi kLo R G B <segMask>` | color+kelvin per-segment (gamma-aware, white-pt by `mode` 0..3) |
| `0x15 0x01` | `u(k,pos,c)` | `15 01 Rk Gk Bk kHi kLo <segMask>` | color-temp per-segment |
| `0x15 0x02` | `G(bri,pos)` | `15 02 <bri> <segMask@3>` | one brightness to selected segments |
| `0x15 0x03` | `F(briArr)` | `15 03 b0 b1 … b14` | **per-segment brightness array** (≤15) |
| `0x15 0x03` | `I(idx,briArr)` | `15 03 <startIdx> b… (≤14)` | brightness array, paged |
| `0x15 0x04` | `m(idx,colorSet)` | `15 04 <startIdx> [R G B]×≤4` | **per-segment color array** (paged, 4/pkt) |
| `0x15 0x05` | `n(colorSet[3],pos)` | `15 05 R1G1B1 R2G2B2 R3G3B3 <segMask>` | 3-color gradient across selected segments |

**Scene apply** (selector `0x04`): `33 05 04 <sceneCode> …` — `sceneCode` is a single byte
(`DelegateSceneV1.F`). **Multi-color whole-strip gradient**: `MultipleColorStripControllerV1`,
**commandType `0x40`**, sent multi-write V1 (`0xA3`/`0xA1` chunked), often followed by a bare
`0x05 15` commit.

**Music** (selector `b6 = Protocols.b(info)`): `0x13` default, `0x11` for v1UIV1/v2UIV1/DC-v2,
`0x0C` for H6119+Telink-OTA. Default shape (`0x13`):
`13 <musicCode> <sensitivity> <subEffect> <colorFlag 1=manual> [R G B if manual]`. Codes 7/48/49/55
emit a two-controller sequence: `MultipleController4Music` (**commandType `0x41`**, multi-packet
color list `[count][R G B]…`) + the `0x05` mode controller. Music code remap
`Protocols.a`: `3↔17, 4↔18, 5↔16, 6↔19`.

**DIY**: standard graffiti V3 = `MultiDiyGraffitiControllerV3`, **commandType `0x57`**, multi-write
V1. H61BE high-color enable: `ControllerMode.e({10,32,3})` → `33 05 0A 20 03 …` before the
graffiti push. DIY-slot select (apply stored effect) = selector `0x0A` `[code lo hi]`.

### 3.2 String lights & whole-light RGB (`com.govee.rgblight`, `stringlightv2`)

Thin device-specific layer over the common set; **no new control opcodes**. Whole-light (non-IC)
RGB strips/bulbs/car/string/copper-wire/TV-backlights. Color carries **one** RGB triple for the
whole fixture (no segment index). The deviation is the **legacy sub-mode selector byte** these
old products use (differs from the modern numbering).

Clusters: `h6113/H6113Support` (H6113/14 car), `h6160/H6160Support` (H6160/H6117/H6163 strip),
`h6179/SupportH6179` (H6179 TV), `h6181/H6181Support` (H6181 TV), `h6182/H6182Support` (H6182 TV
strip), `h6188` (H6188), `h7308` (H7308/09/11/13/15/16 copper-wire/curtain), `h60858689`
(H6085/86/89 bulbs), `Support4H613839` (H6138/39/H613A-F), `Support4StringLightV2` (H6194 +
H6109/10/59/H614B/E).

**Legacy selectors at byte[2]:**

| Cluster | color | scenes | music | new-DIY | source |
|---|---|---|---|---|---|
| H6188 | `0x0D` | `0x04` | `0x03` | `0x0A` | `h6188/H6188BleProtocol` |
| Bulbs H6085/86/89 | `0x02` | `0x04` | — | `0x0A` | `h60858689/SubModeType` |
| H7308 copper-wire | (brightness+scenes only) | `0x A1`* | — | — | `h7308/H7308BleProtocol` |
| Strip/car/string (H6160/H6181/H6182/H6113-14/H613x/SLv2) | via generic old-RGB controller | `0x04` | `0x03` | `0x0A` | base2light |

\* H7308 `sub_mode_scenes = 0xA1` collides with the `MULTIPLE_WRITE` type byte — flagged as
possibly a distinct path. H7308 is brightness + scenes only (no whole-light RGB exposed).

**Whole-light color/color-temp layout** (`ModeParseStrategyConfig`, `validBytes` after selector):
- Plain color: `validBytes[0..2]` = R,G,B.
- With color-temp: `validBytes[3..4]` = kelvin signed short, `validBytes[5..7]` = its RGB.
  On the wire: `33 05 <colorSel> RR GG BB …`; color-temp carries kelvin at frame byte[6..7], RGB
  at byte[8..10].

**Music V2** (`SubMode4MusicV2`): `[0]=mode (48/49 literal else 3/255) [1]=sensitivity
[2]=auto-color-flag (0=device color) [3..5]=R,G,B (when manual)`.

**Scene effect-code tables** (the only per-SKU data; frame `33 05 <sceneSel> <code>`):

| Class / SKU | Effect codes |
|---|---|
| `Scenes4H6160` (H6160/17/63) | `{0,1,4,5,7,8,9}` |
| `Scenes4LocalH6181` | `{0,1,4,5,7,8,9}` |
| `Scenes4H6182` | `{4,5,9,7,10,8,16}` |
| `Scenes4CarLight` (H6113/14) | `{4,5,7,8,9,10,16}` |
| `Scenes4H613839` | `{4,5,7,8,9,16,10}` |
| `Scenes4StringLightV2` (H6194) | `{4,5,7,8,9,10,16}` |
| `Scenes4H6188` | `{4,5,13,23,24,9,16,7,17}` |
| `Scenes4H7308` (copper-wire) | `{20,21,22,23,24,25,26,27}` |
| `Scenes4H60858669` (bulbs) | `{13,17,10,7,20,16,18,19}` |

Generic code meanings: `0=gradual 1=jumping 4=film 5=date 7=romantic 9=candle 10=breath
13=reading 16=energetic/dynamic 17=fade 18=forest 19=fantasy 20=heartbeat 23=brightness
24=aurora` (8/15 unlabeled in this module). `*Night` scene variants differ only in icons.

**DIY** is a `DiySupportV1` capability descriptor (`mix4EffectsNum=4`, max 8 colors, max speed
100); the DIY frame rides the shared `0x0A` / multi-packet `0xA1` path. **Brightness** scaling
here is range **20..254** (`NumUtil.calculateProgress(254,20,pct)`).

### 3.3 DreamColor v1 / v2 RGBIC segment strips (`dreamcolorlightv1` / `dreamcolorlightv2`)

The canonical RGBIC segment strips. Both packages emit **identical on-wire frames** (the split
is app-side UI routing). BLE-controllable (connection-oriented). The `add/**`
`BleBroadcastProcessor*` classes are pairing handlers, **not** control-state adverts.

**Sub-mode selector map (byte[2] under cmd `0x05`):**

| byte[2] | Sub-mode | Notes |
|---|---|---|
| `0x0B` | Segment color v1 | 15-seg, RGB + 2-byte mask |
| `0x15` | Segment color v2 | RGB + colortemp + per-seg brightness; sub-type at byte[3] |
| `0x04` | Scene apply | effect id (2 bytes) |
| `0x0A` | New DIY (slot select) | diy code (2 bytes) |
| `0x11` | Music (old) | effects 16/17/18/19 |
| `0x13` | Music v1 | effect + sub-channel |
| `0x16` | Music (shared/new) | base2light `SubModeAbsMusic` |

**Segment color v1 — selector `0x0B`** (`SubModeColor`, 15 segments, 8-byte submode):

| frame byte | meaning |
|---|---|
| 2 | `0x0B` |
| 3..5 | R,G,B |
| 6 | segment mask segs 0–7 (bit0=seg0) |
| 7 | segment mask segs 8–14 |

App emits one frame per distinct color. Device→app report (`parsePosColor`) reads RGB at
bytes[3..5], masks at bytes[6]/[7] reverse-bit order.

**Segment color v2 — selector `0x15`** (`SubModeColorV2`). Sub-type discriminator at byte[3]:

- **Sub-type 1 (color, `f()`)**, 12-byte submode: byte[2]=`0x15` byte[3]=`0x01`
  byte[4..6]=R,G,B byte[7..8]=kelvin signed (BE, `0`=pure RGB) byte[9..11]=colortemp-RGB
  byte[12]=mask segs0-7 byte[13]=mask segs8-14. (18-seg H61A9 mask spans bytes 12/13/14.)
- **Sub-type 2 (color-by-index, `e()`)**: `15 02 <colorIdx> <mask0-7> <mask8-14>`.
- **Sub-type 3 (per-segment brightness)**: `15 03 <bri per seg>` (15 bytes; 18-seg paged with
  byte[2]=1 then 14 bri bytes, byte[2]=2 for remainder).

**Segment-count selection** (`Support.java`): `isSubModeColorPiece10` → gt 75/187 (10-seg,
`SubModeColorV3`); `Piece12` → gt 83 (H619Z); `Piece18` → gt 204 (H61A9); `Piece20` → gt 175
(H61BE); otherwise 15 segments.

**Scene** (selector `0x04`): `[0x04][effect lo,hi]` via `getSignedBytesFor2(effect,false)`
(write little-endian; parse `getSignedShort(b1,b0)`). **DIY** (`0x0A`): `[0x0A][diyCode lo,hi]`
selects a stored slot; graffiti pixel upload is shared base2light multi-packet.

**Music:**
- Selector `0x11`: effect 16 = `[0x11,16,sens]`; effect 17 = `[0x11,17,sens,!dynamic,!autoColor,R,G,B]`;
  18/19 = `[0x11,effect,sens,!autoColor,R,G,B]`.
- Selector `0x13`: `[0x13,effect,sens,sub-channel,!autoColor,R,G,B]` (8 bytes).
- New-music-code shortcut → 3-byte `[selector, code, sensitivity]`. Multi-IC music
  (`SubModeMusicMultiV1..V3`, DC v2) uses the same selectors with longer per-segment payloads
  (not fully byte-mapped).

**Device-specific top-level opcodes (NOT under mode `0x05`):**

| cmd byte[1] | dir | class | role |
|---|---|---|---|
| `0x0E` | w/r | `LimitController` | power/length limit toggle |
| `0x0F` | r | `LightNumController` | bulb count |
| `0x14` | w/r | `GradualController` | smooth-change flag |
| `0xA3` | w/r | `Gradual4BleWifiController` | BLE-WiFi gradual variant |
| `0x40` | r | `ReadIcController` | IC config (`bArr[1]=='@'`) |
| `0x42` | w | `RefreshIcController` | trigger IC re-detect |
| `0x46` | w | `CheckIcController` | `[icIndex,icType,signed2(value)]` |
| `0x22` | notify | `CheckIcNumParse` | `0xEE 22` → detected IC count |

### 3.4 Lamps & misc (`tablelampv1`, `carlightv1`, `homelightv1`, `hollowlamp`, sync boxes)

Floor/table/strip lamps share a **combined RGB+Kelvin+tint** color form; sync boxes are NOT
lights (they relay external devices).

**Lamp color — selector `0x0D`** (9 bytes; `tablelampv1`/`carlightv1`/`homelightv1`
byte-identical):
```
[0x0D] [R G B] [Kelvin hi,lo BE] [tintR tintG tintB]
```
Pure RGB → kelvin=0, tint=0. Color-temp → RGB=white sentinel, kelvin set, tint = warm/cool RGB.
H6078 clamps kelvin 2200..6500.

**Scenes/New-DIY — `0x04`/`0x0A`** (3 bytes): `[selector][id lo,hi]` little-endian
(`getSignedBytesFor2(id,false)`).

**Music**: tablelamp/homelight v1 = selector `0x0F`; carlight v1 = `0x0E`; H6078 v2 = `0x13`.
v1 shape: `[sel][type][sensitivity][autoFlag][R,G,B]` (autoFlag: 0=device-auto-color,
1=manual RGB follows). type==4 (Rhythm) inserts a mode byte.

**carlightv1 grouping**: `GroupBle` broadcasts identical frames to a paired group; no new
format. Rhythm/smart-scene builders emit standard switch/brightness/color builder frames.

**Sync boxes — H1161 (pickupbox) & H1162/63/67/68 (h1162)**: dedicated opcode block (not the
light set), declared in `*/ble/BleProtocol.java`:

| Const | Hex | Role |
|---|---|---|
| `single_open` | `0x10` | box on/off |
| `single_brightness` | `0x11` | box brightness |
| `notify_brightness` | `0x20` | brightness notify |
| `sub_mode_color` | `0x14` | color sub-mode selector |
| `sub_mode_music` / `_new` | `0x0F` / `0x13` | music v1 / v2 |
| `value_device_num` / `connect_status_notify` | `0x40` | #paired subs (read) / connect notify |
| `value_multiple_set_music` / `device_info` | `0x41` | multi-device music push / per-device info |
| `value_clear_device` | `0x42` | clear paired subs |
| `value_op_device` | `0x43` | turn one sub on/off (`[idx][op]`) |
| music sub-effects | `0x30..0x36` | rhythm/bloom/sparkle/wave/beat/spectrum/scroll |

**pickupbox color (selector `0x14`)** — per-zone RGB, 17 bytes: `[0x14][zone bitmap bits0-4]
[zone0 RGB][zone1 RGB][zone2 RGB][zone3 RGB][zone4 RGB]` (5 zones).
**`0x41` read** (`DeviceInfoController`): `[pos][flag]`; flag0 → `[6-byte MAC][int slot]`, flag1
→ `[nameLen][ASCII][int slot]`. **`0x41` write** (`MultiMusicController`, `0xA1` multi):
`[musicMode][N][R G B ×N]`.

h1162 is the newer sync box on the `base2light` pact framework — on/off uses common
`SwitchController` (`0x01`) not `OpenController` (`0x10`); adds AI/DSP path and Wi-Fi sync.

### 3.5 TV / immersion backlights & capture boxes (`tvlightv1`, `pact_tvlightv2/3/4`, feast)

Camera/screen-driven immersion lights + multi-device "feast" directors. All on the common
20-byte frame; selectors differ per generation.

**Mode sub-mode selectors (byte[2]):**

| Sub-mode | tvlightv1 (H6179) | v2 (T1/T1S) | v3 (light bars) | v4 (P1/P1S) |
|---|---|---|---|---|
| Video (camera) | — | `0x00` | — | `0x00` |
| Scenes | `0x04` | `0x04` | `0x04` | `0x04` |
| NewDiy | `0x0A` | `0x0A` | `0x0A` | `0x0A` |
| Color (legacy) | `0x0D` | `0x0B` | `0x0D` | `0x0D` |
| ColorV2 | — | `0x15` | `0x15` | `0x15` |
| Music (legacy) | `0x0E` | `0x0C` | `0x0C` | `0x0C` |
| MusicV2/V3 | — | `0x13` | `0x13` | `0x13` |

**Video sub-mode (selector `0x00`)** — v2 `SubModeVideo` (7 bytes):
`[0x00][!gameMode][!musicReactive][saturation 1..100][voiceOpen][voice 0..255][extra]`.
v4 `SubModeVideoV2`: `[0x00][videoFlag/movie][!drama][vividness 1..100][voiceOpen][voice][extra]`.

**Video-mode params opcode `0xA9`** (`VideoModeParamsController`): `[selector][len][data]`:
`0x00`=whiteBalance `{enable,rGain,bGain}`, `0x01`=game sensitivity, `0x02`=video brightness,
`0x06`=whiteBalanceV1.

**Camera/position opcodes**: `0x30` LightDirection, `0x31` CameraPos, `0x32` CheckCamera (read
install state), `0xA3` Gradual, `0x34/0x35` StartTime. Camera calibration grid is uploaded to
cloud, not BLE.

**Color layouts:**
- v2 legacy `0x0B` (15-seg): `[0x0B][R G B][kelvin BE][mask0-7][mask8-14]`.
- v2 ColorV2 `0x15`: variant `0x02` = `[idx][mask0-7][mask8-14]`; variant `0x01` =
  `[RGB1][kelvin BE][RGB2][mask0-7][mask8-14]`.
- v3/v4 `0x0D` (dual bar): `[0x0D][bar-select 0x11/0x01/0x10/0x00][R G B][kelvin BE]`.
- tvlightv1 `0x0D` (gradient pair): `[0x0D][RGB1][kelvin BE][RGB2]`.

**Music**: v2/v3 legacy `0x0C` = `[effect][sens][autoColor?][RGB]`; MusicV2 `0x13` (8 bytes) =
`[effect][sens][sub-effect][!autoColor][RGB]`; tvlightv1 `0x0E` = `[effect][sens][autoFlag]`.

**Scenes** (`0x04`): v2/v3/v4 = `[0x04][id lo,hi]` little-endian; tvlightv1 = single byte
`[0x04][id]`. **NewDiy** (`0x0A`): `[0x0A][id lo,hi]` big-endian.

**tvlightv1 TV-size limit** (`0x0E`): `[size-bucket]` — maps colors to strip length for the
camera-less H6179.

**Movie Feast / Music Feast** (cross-SKU multi-device directors):
- Single opcodes: `0x54` MovieOpen, `0x50` brightness, `0x51` saturation, `0x52` getColor, `0x53`
  sound, `0x42` clearSub, `0x43` subDevice, `0x56` delete.
- **Set-sub-device multi-write `0x50`** (`MultiSetSubDeviceController4MovieFeast`): payload
  `[N][per Area4Device: isRgbic, ble-empty-flag, protocolId, (name or 6 reversed MAC bytes),
  zoneCount, zone-index bytes (0xFF=disabled)]`.
- Music Feast: `0x41` MultiMusic (`[subModeCode][colorCount][RGB×count]`), `0x55`
  sub-device-protocol, `0x60` set-sub-device.

**Cloud passthrough**: v2/v3/v4 wrap identical BLE frames via `iot/CmdPt`/`CmdPtReal`. tvlightv1
(H6179) and pickupbox (H1161) are BLE-only.

### 3.6 Bare RGBIC strips & RGBWW (`barelightv1`, `homelightv1`)

**barelightv1** (H6145/6/7, H6171 — 15-segment addressable):
- Legacy color `0x0B` (8 bytes): `[0x0B][R G B][segMaskLow seg0-7][segMaskHigh seg8-14]`.
- Color V2 `0x15` (17 bytes), op at byte[1]: `1`=RGB(+CT tint)+mask, `2`=preset index+mask,
  `3`=per-segment brightness `[2..16]` (15 bytes).
- Standalone **gradual controller `0x14`** (own opcode, `[flag]`).
- Music `0x0C` (v1+v2 share selector): forks by firmware param.

**homelightv1** (H6148 RGBWW, single-zone): pure common-set reuse (color `0x0D`, scene `0x04`,
music `0x0F`, DIY `0x0A`) + Wi-Fi/IoT `Cmd*` passthrough. No segment path.

### 3.7 Panels & newer-gen (`h604a`, `h705a`, `h70b1/b2`, `h6057`, `h70bx`, plant-grow)

**Segment "new color" cmd `0x15`** (h705a, h604a — up to 40 segments):
```
[0x15] [mode 1=whole RGB+CT / 2=segment-index]
mode 1: [R G B] [kelvin LE if≠0] [ct-RGB if≠0] [mask segs0-7][8-15][16-23][24-31][32-39]
mode 2: [seg index] [mask0-7][8-15][16-23][24-31] … [mask32-39 @ byte14]
```
h604a caps at 3 mask bytes (≤24 seg).

**h604a (DreamView G1) video sync (selector `0x00`)**, 8 bytes: `[0x00][on/off flag][vividness
0..100][scene/region][camera-region flag][saturation2][extra]`. Feature opcodes: `0x34`
SwapLight, `0x35` StartTime, `0x36` ComposeLight, `0x40` IcNum, `0x41` OnOffMemory, `0xA7`
CaliLightBelt, `0xAA` CheckLight.

**h6057 (Night Light)** — single-zone color `0x0D`: `[0x0D][R G B][kelvin LE][ct-RGB]`; game
`0x0B`. Rich opcode set: `0x16` EnergySaving, `0x24-0x29` preset slots, `0x27` preview, `0x31/0x32`
voice, `0x36` WorryFreeAtNight `[enabled,startH,startM,endH,endM,…]`, `0x37` PromptTone, `0x38`
GuideLight, `0xA5` local preset color. Status notify (`DeviceInfoNotifyParse`): byte[0] selector
→ 1=switch 2=brightness 3=mode 4=color 5-7=status; battery via `EventNotifyBatteryInfo`.

**h70b1/h70b2 (Curtain/Lightwall)** — `SplicingController` opcode `0x40`: exit = `{0x02,0x00}`,
enter = `{0x02,0x01,R,G,B}`. Brightness notify opcode `0x20`. Per-goodsType scene/music byte
codes in `Support.java`.

**h70bx (Lightwall/Curtain Pro)** — Kotlin `kt.general_controller` framework.
`ControllerChangeSplicing` opcode `0x40`: `[0x01][panelIdx][dir bitfield][packed MAC ×6 each]`;
release = `{0x01,0xFF}`. Cell-graffiti DIY main effect codes: BoDong=1, LiuDong=2, SuiJi=3,
DuiJi=4, XianXing=5, XuanZhuan=6, YunRan=7, GIF=93, TuYa=94.

**h705a feature opcodes**: `0x0F` SegmentSetting, `0x40` IcSegmentNum, `0x43` CheckIc, `0x44`
CutCali, `0x43 sub-0x0A` SetSegmentIcMulti.

**Plant grow (h7004, h7017)** — opcode `0x0D` `RedBlueController`: `q()=[redIntensity,
blueIntensity]` (two unsigned 0-255 ratio bytes); notify mirrors. h7004 Mode submodes
`SubModeRedBlue41/61/81` (cmd 1/2/3) are SKU-shape placeholders (`getWriteBytes()` returns null,
identify 4:1/6:1/8:1 LED ratio).

**h7014** — cloud relay plug; **no BLE path** (IoT `Cmd*` only).

### 3.8 Bulbs & spotlights (`h6101/02/04/05/13/14/19/27/29` adjust packages)

Despite the package names these are TV backlights / strips / car lights (connectable RGB(IC),
not plugs). Thin device layer on the common set.

**Color — selector `0x02`** (all nine packages byte-identical):
```
[0x02] [R G B static] [ctFlag !=0=temp-mode] [R G B color-temp white-point]
```
Note: color **writes** selector `0x02` but **parses** as the default/else branch in `Mode.java`.

**Music** — three encodings: `0x01` (`[modeByte][sens][R G B if not-auto]`, mode enum
energic=0/spectrum=1/rolling=2/rhythm=3); `0x03` (`[autoFlag][sens(0..99)][R G B if not-auto]`);
`0x0C` (h6119, variant by byte[3] music-type). **Video** — `0x00` (h6101: `[dynamic?2:0]
[allRegion?0:1]`; h6104 adds saturation byte). **Scenes** `0x04` (`[sceneId]`). **NewDIY** `0x0A`
(`[diyCode lo,hi]` BE). **OldDIY** `0x07` (h6127/29, raw bytes via `0xA1` multi). **ColorV2/seg**
`0x15` (h6119, sub-cmd 01=per-segment color w/ 6-seg bitmask, 02=brightness+seg, 03=gradient list).

**Device-specific opcodes**: `0x08` Calibration (h6101), `0x0E` Limit (h6102/05), `0x13`
Direction (h6104), `0x15` IPController (h6104, `[IPv4][int port]`), `0x14` Gradual4Ble (h6119),
`0xA5` BulbStringColor (h6119, `[count][segIdx,R,G,B ×3]`).

---

## 4. Appliances (kitchen & air — `base_h71xx` framework)

Humidifiers, dehumidifiers, purifiers, fans, kettles, heaters, ice makers, rice cooker.
Confirmed BLE-controllable: **H7160** (gt 99 humidifier), **H7172/H717D** (gt 117/211 ice
maker). Others are per-module (split feature modules ship separately; not all confirmable from
the base APK).

**Opcodes are late-bound** from a mutable singleton `base_h71xx.sku_base.BleProtocolConstants`
(controllers call getters at frame-build time). In v7.5.20 no bulk per-SKU reassignment was
found, so the **default field values are the effective wire opcodes**:

| Getter | Default | Role |
|---|---|---|
| `g1()` | `0x01` | **Power on/off** |
| `d0()` | `0x05` | **Mode / gear / ice-size** |
| `P()` | `0x10` | Thermometer-probe reading notify |
| `F()` | `0x11` | Delay-off (timer-off) |
| `j1()`/`k1()` | `0x12`/`0x13` | Timer count / timer group v2 |
| `J0()` | `0x16` | Do-not-disturb window |
| `w()` | `0x17` | **Work-status + abnormal/fault** notify |
| `Y()` | `0x18` | Indicator light |
| `O()` | `0x19` | **Ice-maker work-status** notify |
| `c0()` | `0x1A` | UV-C lamp on/off |
| `b0()` | `0x1B` | Water-box / accent RGB light |
| `D()` | `0x1F` | **Multiplexed function-switch** (sub-byte selects) |
| `I()` | `0x23` | Delay-start / reservation (ice maker) |
| `G()` | `0x26` | Delay-off v1 |
| `C()` | `0x27` | Clean / wash reminder |
| `h1()` | `0xB5` | Sync RTC time |

`proType`: write `0x33`, read `0xAA`, secure/multi-sync `0x3A`. On/off values: enable `0x01`,
disable `0x00`.

**Function-switch sub-bytes under `0x1F`** (`[subByte][value]`): Shake=`0x01`, Child-lock=`0x02`,
Rewu/warm-mist=`0x08`, Sensor-temp-unit=`0x08`.

**Mode (`0x05`) layouts:**
- **Ice maker**: `05 <iceSize>` — BIG=`0x01`, MIDDLE=`0x02`, SMALL=`0x03`.
- **Kettle/gear**: `05 <0x00> <ecologyMode>` (kettle) or `05 <gear>` (fan/heat).
- **Humidifier H7160**: GEAR `05 01 <mistGear>`; AUTO `05 03 <humidify(bit0-6)|autoClose<<7>`;
  CUSTOM `05 02 <pack> <child0×5><child1×5><child2×5>` where pack = setIndex|curIndex<<4, each
  child = `[mistGear][onTime BE16][offTime BE16]`.

**Other write payloads:**
- Delay-off `0x11`: `[enabled][delayMinutes BE16]`.
- Delay-start `0x23` (notify/echo): `[enabled][duration BE16][epoch BE32][ice-size]`.
- Do-not-disturb `0x16`: `[enable][startH][startM][endH][endM][forever]` (all-0xFF = full day).
- Clean reminder `0x27`: `[openInt 0/1/2][setCleanHour]`.
- Sync time `0xB5`: `[epoch BE32][0x01][tzH][tzM]`.

**Status notify (H7160, dispatch on byte[1]):** `0x17` work-status (byte0=clear-72h,
byte1=water-shortage, byte2=work-state); `0x10` probe reading (`[valid][temp signed ×][humidity]`);
`0x08` probe pairing (bytes2-7=MAC); `0x1B` accent RGB.

**Ice-maker work-status (H7172):** IDLE=0, ICE_MAKING=1, ICE_MAKE_FINISH=2, WASHING=3,
WASH_FINISH=4, RESERVATION=5. **H7178** superset adds DEFROST_1/2/3=5/6/7, SINGLE/CYCLE_ICE=9/10,
FULL=11/12. Faults arrive under `0x17` → `parseAbnormalInfo` (no_water, full_ice,
high_temperature_protected).

**Broadcast:** appliances broadcast for **discovery only** (SKU + mfr data); live state needs a
connection or the Wi-Fi/IoT path.

---

## 5. Sensors (complete per-SKU table)

**Most sensors are BROADCAST-ONLY for live data** — temp/hum/PM/CO₂/battery/leak/probe-temp are
in the BLE advertisement, parsed without connecting. The 20-byte GATT frame is used only for
*settings* (units/cali/alarm), *history sync*, and *gateway sub-device management*. Sensors do
**not** implement the base2light command set.

### 5.1 Broadcast framing (0x88EC TH family)

Scan record = full **62-byte** advert+scan-response. Govee mfr flag `0x88 0xEC`
(`BleUtil.f41010h`). Anchor finders: `checkBroadcastData` (`… FF 88 EC …` → pos i+4);
`parseThBleValidBytePos` (`FF 01 88 EC` → i+5); `parseThBleValidBytePosV1` (`03 03 88 EC` UUID
list then `FF 01` → i+3).

**Packed temp/hum value** (canonical H5075 encoding, 3 bytes BE, MSB of byte0 = sign):
```
raw24 = ((b0 & 0x7F)<<16) | (b1<<8) | b2     # sign bit cleared
tempC = (raw24 / 1000) * 10  -> centi-°C  (negate if b0&0x80)
hum%  = (raw24 % 1000) * 10  -> centi-%
```
Sentinel `FF FF FF` (or `b0==0x7F`) → invalid. Range: temp −4000..10000 centi-°C, hum 0..10000
centi-%.

**4-byte THP variant** (H5106 air): `raw32` over 4 bytes; `temp=(raw32/1e6)*10` centi-°C,
`hum=((raw32/1000)%1000)*10` centi-%, `pm=raw32%1000` µg/m³.

### 5.2 Per-SKU broadcast layouts (TH / air / CO₂)

| SKU(s) | parser | anchor | layout |
|---|---|---|---|
| H5051/52/53/71/74 | `H50ThBroadParseImp` | checkBroadcastData (7B win) | temp = `getSignedShort(b2,b1)` LE16 centi-°C; hum = LE16 `b3..4`; battery `b5` |
| H5072/75 | `H5072_75ThBroadParseImp` | checkBroadcastData (7B) | `parseThValue(b1..3)` packed-24; battery `b4` |
| H5100/01/02/03/04/05/08/10/11/74/77/71/220 | `H51ThBroadParseImp` | V1 (7B) | `parseThValue(b3..5)` packed-24; battery `b6` |
| H5179 | `H5179ThBroadParseImp` | HW-gated | HW 1.00.02: temp=`getSignedShort(b4,b3)` BE16, hum=`(b6,b5)`, batt `b7`; else packed-24 `b3..5`, batt `b6` |
| H5106 | `H5106ThBroadParseImp` | V1 (7B) | `parseThpValue(b3..6)` → temp/hum/**pm2.5** |
| H5140 (CO₂) | `H5140ThBroadParseImp` | AD-key-0x0B (11B) | `parseThValue(b5..7)` + **CO₂** `(b8<<8)\|b9` BE16 |
| H5107 | `H5107BroadParseImp` | self-protocol blob | 2× 10-byte channels @ off 6,16: `[idx][F1 gate][flag+sno][temp/hum ×3][epoch BE32]` |
| H5109 | `H5109BroadParseImp` | scanRecord[31..47] | `[sno]`; `getSignedInt(b7..10)` BE32; `getSignedIntV2(b11..12)` LE16 temp ⚠️ middle-32 semantics unconfirmed |
| H5112/R5112 | `H5112ThBroadParseImp` | V1 (9B) | packed-24 `b3..5`; battery `b6`; `b8` mode/flag bits; dual sub-channel |
| B5178 | `MultiThBroadParseImp` | parseMultiThBleValidBytePos (10B) | `b3`=probe order; `parseThValue(b4..6)`; `b7` sign+channel |

### 5.3 BBQ / meat-probe thermometers (broadcast)

Probe devices advertise a 16-bit service-UUID + mfr block. `BbqConstant` filter prefixes select
the parse path:

| hex prefix | SKU | method |
|---|---|---|
| `0201050303505517ff` | H5055 | `l()` (new) / `k()` (legacy) |
| `0201050303561017ff` | H5610 | `m()` |
| `0201060303519817ff` | H5198 | `j()` |
| `0201060303519917ff` | H5199 | `g()` (method-dump, flag) |
| `0201060303519117ff` | H5191 | `h()` (method-dump) |
| `0201060303519217ff` | H5192 | `h()` (method-dump) |
| `0201060303519417ff` | H5194 | `i()` (method-dump) |
| `0201060303519617ff` | H5196 | `g()` (method-dump) |

**Temp decode**: `b(b2,b3)` = `getSignedIntV2(BE)/100.0` °C/°F (FF FF → −10000 = absent);
legacy `c(b2,b3)` = LE16 no-scale.

**18-byte format (H5198 `j` / H5610 `m` / new-H5055 `l`):** `[pactType BE16][pactCode]
[bit7=°F unit, bits0-6=pedestal batt%][broadcast-order+probe-connected bits][probe-alarm bits]
[probe-A current/high/low temp ×2B each][probe-B current/high/low ×2B each]`. Each broadcast
carries one probe pair; the app reassembles up to 6 probes across successive adverts.

**Connected path** (`BbqBleProtocol`): standard 20-byte frame for setup/history;
`SecretKeyController` binding; target-temp/alarm writes partially recovered. Masks: B=`0x40`
(probe connected), t=`0x0F`, J=`0x10`, s=`0x20`, A=`0x28` (alarm/state).

### 5.4 Leak detectors & gateway sub-devices

Leak/sub thermometers report **through a gateway** (broadcast relay, notify-on-connect, or cloud
`pt`). Gateway↔sub coverage: H5042(198)→H5109; H5043(158)→H5058/59/107/310/830; H5044(291)→
H5059/830/310; H5151(65)→TH subs.

**Leak frame envelope** (`H5043LeakageParse`, dispatch on `[0],[1]`): `0xEE 0x34`=warning,
`0xEE 0x32`=sub info, `0xAA 0x04`=read reply, `0xEE 0x35`=op-result.

**H5058 leak status** (subType 13): byte3 bit-field — bit0=up-leak, bit1=mid-leak, bit2=down-leak,
bit3=low-bat-open, bit5=low-battery; leak-event epoch BE32 at bytes 6-9; battery at byte 12.

**H5059/H5830** (17-byte, scanRecord[31..47]): `[sno][deviceType][online][sno2][HW][SW][level]
[leak epoch BE32 @7-10][thresholds][battery @13][bit7=lowBattery, bit6=!gw-warning, bit5=leakMode]`.

H5054 (older standalone leak) is in legacy `com.govee.gateway`; warnings via cloud push.

### 5.5 Connected opcode map (TH settings / history)

Standard 20-byte frame, svc `…1910`/`…2b11`. From `pact_thnew/.../ble/controller/Controller4*`:

| opcode | controller | dir | payload |
|---|---|---|---|
| `0x01` | HeartV1 / HeartPrepare | R/W | history-dump prepare (multi-packet `0xA1/A2`) |
| `0x02` | TemUnit | R/W | `[unit]` (1=°F-mode flag) |
| `0x03` | HumWarning | R/W | enable + 2× LE16 thresholds |
| `0x04` | TemWarning | R/W | `[enable][lowTemp LE16][highTemp LE16][hyst]` |
| `0x06`/`0x07` | HumCali / TemCali | R/W | signed LE16 offset |
| `0x08` | Battery | R | reply `[0]` = % |
| `0x0C`/`0x0D`/`0x0E` | DeviceId / BleHv / BleSv | R | id / versions |
| `0x10`/`0x11` | SyncTime / ClearData | W | epoch+DST / wipe history |
| `0x1F` | AirNotify | notify | air-quality push (H5106/H5140) |
| `0x20`/`0x21` | WifiHv / WifiSv | R | Wi-Fi versions |
| `0x30` | Volume | R/W | buzzer volume |
| `0x36` | ThMulti | R/W | multi-channel TH config (B5178) |
| `0xFE` | SecretKeyV0/V1 | W | binding secret-key |

### 5.6 Per-SKU summary

| SKU | gt | category | BLE? | live data via |
|---|---|---|---|---|
| H5051/52/53/74 | 0 | TH | broadcast | adv (H50, LE16) |
| H5072/75 | 0 | TH | broadcast | adv (packed-24) |
| H5100/01/04/05/08/10 | 66/8/154/190/194/287 | TH | broadcast (+connect) | adv (H51) + settings |
| H5106 | 124 | air PM2.5 | broadcast (+connect) | adv (THP-32) + AirNotify |
| H5107 | 220 | TH | gateway (H5043) | relayed adv / pt |
| H5109 | 199 | TH probe | gateway (H5042) | relayed adv / pt |
| H5112/R5112 | 330 | TH R1 Pro | broadcast (+connect) | adv (flags, dual-ch) |
| H5140 | 319 | CO₂ | broadcast (+connect) | adv (AD-11, CO₂ BE16) |
| H5179 | 7 | Wi-Fi TH | broadcast (+wifi) | adv (HW-gated) |
| H5198/H5199/H5610 | 85/155/344 | meat probe | broadcast (+connect) | adv (BBQ) |
| H5054 | 0 | leak | gateway | cloud push (legacy) |
| H5042/H5043/H5044/H5151 | 198/158/291/65 | gateway | connect/wifi | hosts sub-devices |

---

## 6. Controllers & gateways

### 6.1 Unified channel layer (`com.govee.ctlchannel`)

Newer gateways/controllers route commands through `GMessage` objects sendable over BLE or
IoT/cloud (`IReq.SendType.{BLE,IOT,BOTH}`) — wire bytes identical on both paths.

**Single-frame builders** (`GMessageBuilder`): `buildSingleReadAa(cmd)` →
`[0xAA][cmd][opt?][…][BCC]`; `buildSingleWrite33(cmd,payload)` → `[0x33][cmd][payload][BCC]`.
Write-OK check: reply `frame[2]==0`. proType: write `0x33`, read `0xAA`, multi-sync `0x3A`,
multi `0xA6/0xA3/0xA2`. IoT verb map: `0x33→ptReal`, `0x3A→multiSync`.

**Multi-packet READ** (`0xAC`/`0xAB` header): request `BleUtils.p(0xAC, cmd, data)`; reply first
packet `[0xAC][0x00][total BE @2-3][lastLen @4][cmd @5][subCmd @6][payload from 7]`, middle
`[0xAC][idx][17B @2-18]`, last `[0xAC][0xFF][lastLen bytes]`. **Multi-packet WRITE**
(`makeSendBytesV1/V2`, proType `0xA3`): header `[proType][0x00][0x01][total][commBytes…value]`,
middle `[proType][idx][17 value bytes]`, last `[proType][0xFF][remaining]`.

### 6.2 H5151 — Bluetooth-WiFi Gateway (gt 65)

GATT: **Telink `…4857`** service, write+notify char `…2011`. Command consts: SINGLE_WRITE
`0x33`, READ `0xAA`, MULTIPLE_READ `0xA2`, MULTIPLE_WRITE `0xA3`, NOTIFY `0xEE`,
MULTI_SUB_DEVICE_UUID `4`, MULTI_SUB_DEVICE_TH `5`, secret `0xB1/0xB2`, indicator `0x21`.

Sub-device config (multi-write `0xA3`): `Controller4SubDeviceUuids` (sub-cmd 4,
`[count][6-byte addr ×count]`); `Controller4SubDeviceTemHumRange` (sub-cmd 5, TH-range bytes);
`Controller4SubDeviceThRange4Common` (V2 `{0xFE,5}`). Singles: `0x21` LightSwitch, `0x01`
HeartV2, version/MAC/time reads, `Request4BindH5112`.

### 6.3 H5042 — Wi-Fi Smart Gateway 1s (gt 198) + H5109 sub

GATT standard `…1910`/`…2b11`. Sub deviceType `1` = H5109.

| cmd | controller | dir | meaning |
|---|---|---|---|
| `0x01` | Uuid (R) / SubDevicePairInfo4Bind (W) | R/W | gateway MAC / pairing |
| `0x03` | SubDeviceNum | R | sub count |
| `0x04` | SubDeviceInfo4Bind | R(multi) | enumerate subs |
| `0x05`/`0x06` | StudyMode / BindSubDeviceSuc | W | pairing / confirm |
| `0x08` | TemWarning / SwitchLongLife | W | alarm range / long-life (sub-cmd mux) |
| `0x10` | SyncTime | W | clock |
| `0x11` | DeleteSubDevice | W | `[subIndex]` or `[0xFF]`=all |
| `0x14` | DeleteSubDevData | W | clear history |
| `0x21` | LightSwitch | W | indicator |
| `0xB1/0xB2` | Secret | R/W | binding token |

**Notify** (`0xEE` + cmd): `0x31` add-sub, `0x32` identify, `0x34` info-update, `0x35` op-result,
`0x11` wifi. **H5109 TH info record** (17-byte payload): `[0]=subIndex [1]=deviceType
[2]=online [3]=battery% [4]=softVer nibbles [5]=hardVer nibbles [6]=RSSI signed [7..10]=updateTime
BE32 sec×1000 [11..12]=temp LE [13..14]=tempCali LE [15]=power-save [16]=flags reversed-bits]`.

### 6.4 H5043 — Wi-Fi Smart Gateway 2 (gt 158) + H5044/R5044 (gt 291)

GATT standard `…1910`/`…2b11`. Sub-device type codes: `12`/`13`=H5058, `0xF1`=H5107, `2`=H5059,
`4`=H5830, `8`=H5310. Command types: `0x03` SubDeviceNum, `0x04` H5107Info, `0x05` StudyMode,
`0x08` (FindDevice/SetVolume/TemWarning/HumWarning/CheckSignal mux), `0x11` Delete, `0x15`
BuzzerGear, `0x21` LightSwitch, multi-write SyncSubDevice/cali/long-life.

Notify dispatch (`Parser.a`, `frame[0]==0xEE`): `0x34` sub TH info → `Info4ThWithCali.a`; `0x33`
op-result. Cloud passthrough delivers verbatim 20-byte BLE frames (`ResultPt.bytes()`), so
gateway-forwarded sub frames are byte-identical over BLE and IoT.

### 6.5 Broadcast-only controllers

H5122/H5125/H5126 (buttons/remotes, gt 131/144/145): **no BLE control class** anywhere — they
are broadcast-only scene triggers (app receives press adverts, sends nothing). H5901 Smart Water
Timer (gt 363): no module in this APK split; control path unknown (likely Wi-Fi/cloud).

---

## 7. BLE-controllability summary (integration input)

### Fully BLE-controllable (connect + control, common command set + family layouts)

- **All light families**: RGB/whole-light (`rgblight`, `stringlightv2`), RGBIC segment
  (`rgbiclight`, `dreamcolorlightv1/v2`, `barelightv1`), bulbs/spots (`h61xx`), lamps
  (`tablelampv1`, `carlightv1`, `homelightv1`, `hollowlamp`), TV/immersion (`tvlightv1`,
  `pact_tvlightv2/3/4`, `pact_h605b`, `h604a`), panels/new-gen (`h705a`, `h70b1/b2`, `h70bx`,
  `h6057`), sync boxes (`pickupbox` H1161, `h1162`), plant-grow (`h7004/h7017`), feast directors.
- **Smart plugs** (PROTOCOL §6.2/6.3): H5080/82/83/85/89, H5160/5161, H5086.
- **Appliances confirmed**: H7160 humidifier, H7172/H717D ice maker (others per split module).
- **Data-driven light SKUs** (§2.3): controllable via common set, no extra opcodes.

### Broadcast-monitor-only (state in adverts, no actuation)

- **Sensors**: all TH (H5051-H5112, H5179), air (H5106), CO₂ (H5140), BBQ probes
  (H5055/H5198/99/H5610/etc.). BLE connect used only for settings/history.
- **Buttons/remotes**: H5122/H5125/H5126 (scene triggers).
- **Leak/motion/door/presence/pressure sensors**: H5054, H5121/23/27/29/30 (gateway-relayed).

### Gateway-mediated (BLE for provisioning + sub-device relay, primary path Wi-Fi/IoT)

- H5042 (gt 198), H5043 (gt 158), H5044/R5044 (gt 291), H5151 (gt 65). Sub-sensors broadcast or
  relay through these.

### Not BLE (cloud/Wi-Fi only)

- H7014 cloud relay plug; H5081 (gt 4); H5040/H5041 gateways; H5901 water timer (unconfirmed).

---

## 8. Open questions & per-section confidence

| Section | Confidence | Open items |
|---|---|---|
| §2 matrix | High | goodsType↔package many-to-many — check `(pactType,pactCode)` for gt 12/13/16/71/141/351/352; legacy goodsType-0 SKUs ambiguous |
| §3.1 RGBIC | High on selectors/`0x15` family/`0x40`/`0x41`/`0x57` | exact `colorVersion→Bytes.fn` per-SKU mapping in 18k-line `Config.java`; 4-color RGBWIC (H6671/72 gt 332) W-channel byte position untraced; `r()` white-pt `mode 0..3` semantics partial |
| §3.2 RGB/string | High on routing/scene codes/selectors | color/music byte offsets from **parse** strategies (write builder in shared base2light); H7308 `0xA1` scene-selector collision unresolved; code meanings 8/15 unlabeled |
| §3.3 DreamColor | High on selectors + v1/v2 color layouts | RGBIC graffiti pixel-upload layout in shared `ac/diy` (not mapped); multi-IC music (`SubModeMusicMultiV1..V3`) longer payloads not byte-mapped; `ReadIcController` field semantics inferred |
| §3.4 lamps/boxes | High on read layouts | music `type`/`musicCode` enum meanings partial; `DeviceInfoController` trailing int (slot vs type vs online) unconfirmed; h1162 `0x10` vs common `0x01` switch path; `DeviceStatusNotifyParse` 5-byte block undecoded |
| §3.5 TV/immersion | High on selectors/layouts | `SubModeVideo` byte[6] meaning unpinned; `CameraPos` value↔orientation mapping not enumerated; v3 `SubModeMusicV3` 9-byte style-3 form; `getIndex4Portocol` zone-remap table not transcribed |
| §3.7 panels | Medium-high | h70bx full DIY multi-packet envelope not traced end-to-end; h6630 graffiti wire format lives in `tablelampv1`; h6057 status cases 5-7 inferred; h705a `0x40/0x43/0x44` field meanings partial |
| §3.8 bulbs/spots | High (color layouts byte-identical) | h6102 `0x0B`/`0xAC` declared but vestigial; h6104 IPController int[4..7] semantic inferred |
| §4 appliances | High on opcode-table defaults | kettle/heater target-temp °C↔byte scaling lives in per-SKU `EcologyModeCons`/spec JSON (not extractable); whether any SKU rewrites the `BleProtocolConstants` singleton at runtime; `.c()` vs `.d()` (0x33 vs 0x3A) not byte-traced; newer ice makers (H8120/21/22/31) extra mode params |
| §5 sensors | High on TH/CO₂/air, H50/H51/packed-24 | H5199/H5191/H5192/H5194/H5196 probe layouts are jadx method-dumps (offsets inferred, not byte-confirmed); H5109 middle-32 timestamp-vs-reading unconfirmed; BBQ connected target-temp/alarm payloads partial; temp-unit `0x02` byte (1=°C?/°F?) not UI-cross-checked |
| §6 controllers/gw | High on ctlchannel builders + H5042/43 maps + H5109 record | `payload[16]` flags-byte bit semantics not HW-verified; `Info4ThWithCali` internal offsets not expanded; H5901 control path unknown; button advert payload format not in these modules |

### Top unmapped SKUs / gaps

1. **H5199 / H5191 / H5192 / H5194 / H5196** BBQ probes — broadcast layouts are jadx method-dumps; need a live capture.
2. **H6671 / H6672** (gt 332) RGBWIC — 4th (W) color-channel byte position not traced to a builder.
3. **H5901** Smart Water Timer (gt 363) — no APK module; BLE vs Wi-Fi control path unknown.
4. **Kettle/heater target-temperature** scaling — encoded under mode `0x05` but °C↔byte map is in cloud spec JSON, not the APK.
5. **Multi-IC music** (DC v2 `SubModeMusicMultiV1..V3`) and **RGBIC graffiti pixel-upload** — payload bytes live in shared base2light, not byte-mapped.
