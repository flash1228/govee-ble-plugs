# Family: String / Curtain / Bulb-string & Hollow-lamp Lights (`fam-string`)

Source: `re_apk/decompiled/base/sources/com/govee/{stringlightv2,bulblightstringv1,hollowlamp}/**`.
All three are **BLE-controllable RGB(IC) lights** built on the shared `base2light` common
command set (on/off `0x01`, brightness `0x04`, mode `0x05`). This section documents only
the **device-specific** deviations: sub-mode byte layouts, per-bulb/per-segment color
addressing, color-temp (`0x0D`), scenes/DIY/music codes, and family-private opcodes.

> **Framing recap.** 20-byte frame `[type][opcode][payload…][BCC=XOR(0..18)]`,
> `type 0x33`=write / `0xAA`=read. **Mode** is opcode `0x05` with the sub-mode selector at
> frame `byte[2]`. Each `SubMode.getWriteBytes()` returns the payload **starting with its
> `subModeCommandType()`** (i.e. it produces frame bytes `[2..]`; the framer prepends
> `type` + `0x05` and appends BCC). `Mode.parseMode()` copies frame `bytes[2..18]` (17 B).
>
> **int16 endianness (both confirmed in `base2light/ble/BleUtil.java`):**
> - `getSignedBytesFor2(v,true)` → `[hi,lo]` **big-endian** — used for **color-temp Kelvin**.
> - `getSignedBytesFor2(v,false)` → `[lo,hi]` **little-endian** — used for **scene/DIY codes**.
> - `getSignedShort(h,l) = (h<<8)|(l&0xFF)`.

---

## 1. SKU / goodsType coverage

### 1.1 `stringlightv2` — strip / string / curtain / outdoor / motorcycle "v2 light" module
Broad BK/Telink light module (handles many strip *and* string/curtain SKUs). SKUs seen in
`stringlightv2/pact/Support.java` + module refs (goodsType from `_sku_catalog.md`):

| SKU | gt | Note | SKU | gt | Note |
|---|---|---|---|---|---|
| H6109 | 0 | Strip | H6160 | 0 | Smart Light |
| H6110 | 0 | Strip | H6170 | 2 | Outdoor strip |
| H6118 | 6 | Car | H6178 | 78 | TV backlight |
| H6121 | 1 | Strip | H6192 | 143 | Motorcycle (mic) |
| H6138 | 0 | Strip | H6194 | 6 | Motorcycle |
| H6139 | 0 | Strip | H6195 | 1 | Strip |
| H6141 | 1 | Strip | H6196 | 2 | Strip |
| H6142 | 1 | Strip | H6197 | – | Strip |
| H6154 | 1 | Strip | H613A–F | 39 | RGB strip |
| H6159 | 0 | Strip | H615A–E | 40/108 | RGB strip |
| H614B/H614E | – | Strip | H616B | 68 | RGB strip |

Protocols registered via `GoodsType.beProtocol(category, version)` in `Support.addSupportPact()`:
categories `1,2,10` × versions `1,2` (BLE-only and BLE+Wi-Fi/IoT variants). "BK protocol"
(`Support.isBKProtocol`) gates the newer BK-chip framing.

### 1.2 `bulblightstringv1` — addressable **bulb-string** lights
`bulblightstringv1/pact/Support.java`: **H7002** (gt 3, "String Light"), **H7005**. Up to
**80 individually-addressable bulbs**.

### 1.3 `hollowlamp` — table/floor "hollow" lamps with per-segment local color
`hollowlamp/pact/Support.java` goodsTypes `{27,37,42,59,58,84,395}`:

| SKU | gt | Product |
|---|---|---|
| H6050 | 27 | RGB Table Lamp |
| H6051 | 37 | Table Lamp Lite |
| H6055 | 42 | Portable Table Lamp |
| H6058 | 59 | Portable Table Lamp |
| H6059 | 84 | Aura Mini |
| H6073 | 58 | RGB LED Floor Lamp |

(`395` reserved/grouped in `f129024n`; `42` is the BLE-only sub-set `f129020j`.)

All three families are **actively BLE-controllable** (full GATT write path; the modern
`…1910`/`…2b11` service/char). Broadcast adverts are used only for pairing discovery
(`stringlightv2/add/BleBroadcastProcessor.java` → `BaseBleProcessor`), not for state — these
are not broadcast-only devices.

---

## 2. `stringlightv2` device-specific layouts

Opcode/sub-mode constants from `stringlightv2/ble/BleProtocol.java`.

### 2.1 Mode (`0x05`) sub-modes — selector at `byte[2]` (`Mode.parseSubMode`)

| Sel | Class | Write payload (`getWriteBytes`, bytes after `0x05`) |
|---|---|---|
| `0x0D` | `SubModeColor`, `SubModeColor4Ww` | `[0D][R][G][B][KhiBE][KloBE][ctR][ctG][ctB]` |
| `0x02` | `SubModeColorOldV0` | `[02][R][G][B][isCT:0/1][ctR][ctG][ctB]` |
| `0x04` | `SubModeScenes` | `[04][effLo][effHi]` (effect uint16 **LE**) |
| `0x0A` | `SubModeNewDiy` | `[0A][diyLo][diyHi]` (diyCode uint16 **LE**) |
| `0x0E` | `SubModeMusic`, `SubModeMusicMultiV1` | old music (below) |
| `0x13` | `SubModeMusicV2`, `SubModeMusicMultiV2` | new music (below) |
| `0x05` | `SubModeMicH6192` | `[05]` (mic-by-phone, H6192 only; selector only) |

**Color `0x0D`** (`SubModeColor4Ww.getWriteBytes`/`parse`): byte1-3 = primary RGB; byte4-5 =
**Kelvin int16 big-endian**; byte6-8 = color-temp *display* RGB (precomputed white-point
preview). When in pure-RGB mode Kelvin=0 and ct-RGB=0. `SubModeColor.beColorTem(k)` sets
RGB=white(-1), Kelvin=k. Color-temp is therefore **not a separate opcode** — it rides inside
the color sub-mode via the Kelvin field. `SubModeColor4Ww` (named "4Ww") is the warm-white
variant used by IoT bridging; identical wire layout to `SubModeColor`.

**Color-old `0x02`** (`SubModeColorOldV0`): legacy 8-byte form, byte4 is a boolean "is
color-temp" flag instead of a 2-byte Kelvin; bytes5-7 = ct display RGB.

**Scenes `0x04`** (`SubModeScenes`): effect codes (`BleProtocol.value_sub_mode_scenes_*`):
`gm=0, sunset=1, film=4, date=5, romantic=7, blinking=8, cl=9, breath=10, dynamic=16`.
Default `getEffect()`=4. (Actual scene catalog is server-driven; these are the legacy fixed IDs.)

**DIY `0x0A`** (`SubModeNewDiy`): writes only the 2-byte DIY code (LE); the DIY effect
payload itself is uploaded out-of-band (multi-packet, see `DiyLocal`/`ble/DiyLocal.java`).

**Old music `0x0E`** (`SubModeMusic.getWriteBytes`):
`[0E][effect][sensitivity 0..99][autoFlag]` and, when **not** auto, `+[R][G][B]`.
`autoFlag` byte = `0` when auto (`d(true)=0`), `1` when manual color (note inverted sense in
`parse`: `auto = (bArr[2]==0)`). `SubModeMusicMultiV1` (group/whole variants) selector also
`0x0E`: whole-toggle form `[0E][b][c]`; soft/manual forms add the auto + RGB tail.

**New music `0x13`** (`SubModeMusicV2.getWriteBytes`):
`[13][effect][sensitivity][mode=0][autoFlag][R][G][B]` (autoFlag = `!auto?1:0`; RGB zeroed
when auto). `SubModeMusicMultiV2` mirrors this with a leading whole/group selector byte.
Music style values: `power=0, soft=1, party=3` (`value_sub_mode_music_*`);
new-music: `dynamic=0, soft=1`.

### 2.2 Family opcodes (not mode sub-modes)
| Opcode | Class | Purpose |
|---|---|---|
| `0x0E` | `LimitController` (`SINGLE_LIMIT`) | event/limit single-controller (opcode layer — distinct from the `0x0E` music *sub-mode*) |
| `0xEE` | `OtaPrepareController` (`SINGLE_OTA_PREPARE`) | OTA handshake (`0xEE` = notify/`-18`) |

On/off `0x01`, brightness `0x04`, and the raw `0x05` mode frame come from the `base2light`
common set — **not redefined** here.

---

## 3. `bulblightstringv1` — per-bulb addressing (H7002/H7005)

Constants: `bulblightstringv1/ble/BleProtocol.java`.

### 3.1 Mode (`0x05`) sub-modes

| Sel | Class | Payload |
|---|---|---|
| `0x0B` | `SubModeColor` | **per-bulb bitmask color** (below) |
| `0x09` | `SubModeScenes` | `[09][scene+1][0×15]` (fixed 17-byte) |
| `0x0E` | `SubModeMusic` | music (`power=0, soft=1`) |

**Per-bulb color `0x0B`** (`SubModeColor.getWriteBytes`): one RGB applied to a selectable
**subset** of up to 80 bulbs via a bitmask.
Layout: `[0B][R][G][B][mask0][mask1]…[maskN]`. `ctlLight[80]` booleans are packed
**LSB-first within each byte** (`bit i = ctlLight[byte*8+i]`), ceil(80/8)=**10 mask bytes**
→ 14-byte payload when all 80 addressed. `makeSubModeColor(rgb)` lights all bulbs; arbitrary
subsets address individual bulbs/segments. (A separate `makeSubModeColor4SetAllBulb(n,rgb)`
fills an `rgbSet[n]` for the distinct-per-bulb path used by the multi-packet uploader.)

**Scenes `0x09`** (`SubModeScenes`): 17-byte frame, `byte1 = sceneIndex+1`
(`parse` subtracts 1). Effect enum (`BleProtocol`):
`illumination=0, fade=1, raindrops=2, colorful=3, marquee=4, blinking=5, snow=6, sky=7`.

### 3.2 Family opcodes
| Opcode | Class | Dir | Payload / reply |
|---|---|---|---|
| `0x0F` | `BulbNumController` (`SINGLE_BULB_NUM`) | R/W | write `[count]`; reply `[count]` — number of bulbs configured on the string |
| `0xA2` | `BulbStringColorController` (`SINGLE_BULB_COLOR`) | **read-only** | write `[groupIdx]`; reply parsed by `BulbGroupColor`: `[groupByte][R G B]×4` → reads back **4 bulbs' current colors per page** |
| `0x01` | `MultipleScenesController` (`MULTI_SCENE`) | W | multi-packet custom-scene upload |

`BulbGroupColor.parseBytes`: `byte0` = group/count, then 4× RGB triples (12 B) = colors of 4
consecutive bulbs; the app pages through groups to read the whole string.

---

## 4. `hollowlamp` — per-segment "local color" + auto-induction (H6050-series lamps)

Constants: `hollowlamp/ble/BleProtocol.java`.

### 4.1 Mode (`0x05`) sub-modes (`Mode.parseSubMode` / `parseWriteSubMode`)

| Sel | Class | Payload |
|---|---|---|
| `0x0D` | `SubModeColor`, `SubModeColorV2` | `[0D][R][G][B][KhiBE][KloBE][ctR][ctG][ctB]` (identical 9-byte layout to stringlightv2; Kelvin int16 **BE**) |
| `0x04` | `SubModeScenes` | `[04][effLo][effHi]` (uint16 **LE**); default eff=34; toggle special `1074`/`1098` |
| `0x0A` | `SubModeNewDiy` | `[0A][diyLo][diyHi]` (uint16 **LE**) |
| `0x0E` | `SubModeMusic` | music v1 |
| `0x0F` | `SubModeMusicV2` | music v2 |
| `0x13` | `SubModeMusicV3` | music v3 |

`SubModeColorV2` implements `ISubModeColorTem` and takes an explicit Kelvin range from
`Support.getColorTemRange(27)`; wire bytes identical to `SubModeColor`.

### 4.2 Family opcodes — **device-specific, the interesting part**

| Opcode | Class | Dir | Payload / reply |
|---|---|---|---|
| `0xA5` (`-91`) | `LocalColorSettingMultiControllerV1` | **W** (multi-packet) | per-segment palette set |
| `0xA5` (`-91`) | `LocalColorReadControllerV1` | **R** (paged) | per-segment palette read |
| `0xA6` (`-90`) | `OnOffAutoInductionController` | R/W | write `[bool]` motion/auto-induction enable; reply `[bool]` |
| `0xA7` (`-89`) | `SensitiveController` | R/W | write `[sensitivity]`; reply `[byte]` (mic/induction sensitivity) |
| `0x41` (`65`) | `MultiMusicController` | W (multi-packet) | multi-zone music palette |

**Local color set `0xA5` write** (`LocalColorSettingMultiControllerV1`): builds
`[count] + count×(R,G,B,KhiBE,KloBE)` — **5 bytes per segment color** (RGB + Kelvin int16
big-endian), sent as an `AbsMultipleControllerV1` multi-packet (`0xA1`/`0xA2` chunking).
`getShowColor()` resolves a Kelvin entry to its display RGB before sending. Up to 24 segments
(paged 4/packet, `pages = ceil(count/4)`).

**Local color read `0xA5`** (`LocalColorReadControllerV1`): request `[pageIdx]` (1-based);
reply `[pageIdx][totalPages][R G B]×4` → **4 segment colors per page**, accumulated into a
24-entry table (`byte[24][3]`); auto-advances page (`pageIdx++`, 50 ms) until
`pageIdx==totalPages`, then emits the full segment list. So a hollow-lamp exposes **up to 24
independently-colored segments**.

**Multi-music `0x41`** (`MultiMusicController` ctor): payload
`[flagByte b6][count][ (R,G,B)×count ]` (`new byte[count + 1 + count*3]`, `[0]=flag, [1]=count`,
then RGB triples). Write-ack keyed on reply `bArr[3]==0`. Used for multi-zone music color
assignment alongside the `SubModeMusicV3` (`0x13`) selector.

**Unmapped `BleProtocol` constants** (no controller found in this dump — flag): `0x4B`(75),
`0x4C`(76), `0x36`(54), plus sub-mode value bytes `34`(scene default), `32`, `2`, `10`.
Likely status/notify or battery/timer opcodes (`hollowlamp/BatteryNotification.java`,
`NotificationTimeConfig.java` exist) — not confirmed here.

---

## 5. Status / notify

All three use `BleNotifyComm` + `WifiNotifyParse`; mode state is re-read by `Mode.parseMode`
(copies frame `[2..18]` then dispatches on `byte[2]` selector exactly as the write table
above). No family-private status frame beyond the per-opcode replies already listed
(bulb count `0x0F`, bulb-group color `0xA2`, hollowlamp local-color `0xA5`, auto-induction
`0xA6`, sensitivity `0xA7`).

---

## 6. Open questions / uncertainty
- `stringlightv2` covers strip lights too (gt 1/2/6/…); the per-SKU split between this module
  and `rgblight`/`rgbiclight`/`dreamcolor*` is version-gated (`Support.isBKProtocol`,
  `getNewMusicModeVersion`) — exact dispatch not fully traced here.
- `bulblightstringv1` distinct-per-bulb path (`rgbSet`) is uploaded via a multi-packet
  controller not located in this pass; only the single-color bitmask form (`0x0B`) is byte-exact.
- hollowlamp `0x4B/0x4C/0x36` opcodes and the `34/32/2/10` sub-mode value bytes are declared
  but their controllers weren't found in the decompile slice — flagged, not invented.
- Scene effect codes listed are the legacy fixed IDs; current scenes are server-catalog
  driven (effect uint16 written verbatim).
