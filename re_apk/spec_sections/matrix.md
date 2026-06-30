# Master Device Matrix — goodsType → family/package → SKUs → BLE capability → command set

`section_id: matrix`

This is the index every integration starts from: it maps each **goodsType** (and where
needed the `(pactType, pactCode)` protocol pair) to the **handler package** that owns its
BLE/Mode byte layouts, classifies each device as **BLE-controllable / broadcast-only /
WiFi-cloud-only**, and points at the section that documents the actual frame bytes
(`common-light`, `rgbic`, `sensors`, `plug-h5080`, `plug-h5086`, `plug-h5089`, `broadcast`,
`iot-map`, `transport`, `crypto`).

SKU→goodsType comes from `_sku_catalog.md` (617 SKUs). goodsType→package comes from the
`addSupportPact()` / `Pact.b(goodsType, Protocol)` registrations and the
`DeviceGoodsType` maps in each family's `pact/Support.java`.

---

## 0. How routing actually works (read this first)

A device is identified at runtime by three numbers, not one:

| Field | Meaning | Source |
|---|---|---|
| `goodsType` | numeric product class (the catalog's column 2) | `categories.json`, `DeviceGoodsType` |
| `pactType` (`Protocol.f41313a`) | protocol/transport family (1=BLE-only legacy, 2=BLE+WiFi, 3/10=newer variants, 11=fully data-driven) | `com/govee/base2home/pact/Protocol.java` |
| `pactCode` (`Protocol.f41314b`) | protocol revision within the family | same |

Each family's `Support.addSupportPact()` calls `Pact.f41308c.b(goodsType, Protocol…)`
(legacy) or builds a `DeviceGoodsType` map of `goodsType → [ (pactType,pactCode) … ]`
(newer Kotlin families, e.g. `rgbiclight/Support.java:b()`). **`supportPact(goodsType, protocol)`
returns true only if both the goodsType *and* the advertised `(pactType,pactCode)` match.**
This is why the **same goodsType can appear under several packages** (e.g. gt 13 is claimed by
`barelightv1`, `dreamcolorlightv1`, and `rgbiclight` for different `(pactType,pactCode)`): the
protocol pair disambiguates which Mode/scene byte layouts apply. All of them still build frames
with the one shared 20-byte builder (`base2kt/utils/BleUtils`) and the common command opcodes
(on/off `0x01`, brightness `0x04`, mode `0x05`); see `common-light.md` / `transport.md`.

**Important structural fact:** many modern/middle-era light goodsTypes have **no per-family Java
package at all** (e.g. gt 64 bulbs, 209 Floor Lamp 2, 261, 376 Floor Lamp 3, plus the bulk of the
300+ range). These are driven entirely by the **data-driven detail framework**
(`com/govee/base2light/pact/newdetail/**` + `com/govee/skubusiness/**`): the app downloads the
device's capability/Mode descriptors from the cloud (`LightVersionService`) and renders them on
top of the same `base2light` common command set. For those SKUs the wire protocol is the
**common set documented in `common-light.md`/`rgbic.md`** — there is no extra family-specific
opcode shipped in the APK.

---

## 1. BLE capability by category (covers all 617 catalog SKUs)

| Category (catalog) | BLE capability | Notes |
|---|---|---|
| Indoor / Outdoor / LED Strip / Other Lights | **BLE-controllable** + on/off broadcast | Common `base2light` set + optional per-family Mode bytes. Broadcast on/off in mfr data (see `broadcast.md`). |
| Controller → **plugs** (43/50/90/195/307) | **BLE-controllable** + broadcast state | `h5080`/`h5086` packages. `plug-h5080.md`, `plug-h5086.md`, `plug-h5089.md`. Post-OTA H5080 = encrypted (`crypto.md`). |
| Controller → **buttons/remotes** (H5122/5125/5126 = gt 131/144/145) | **Broadcast-only / gateway-managed** | No BLE control code in this APK; act as scene triggers via gateway. |
| Controller → **water timer** (H5901 = gt 363) | gateway/DB-managed (`base2home/reform4dbgw`) | Not a standalone BLE control target in this APK. |
| Sensor → Thermo/Hygro/Air/CO₂ | **Broadcast-only for state**; BLE GATT used for config + history pull | `thnew` framework. `sensors.md`. Monitor-only (no actuation). |
| Sensor → Leak / Motion / Door / Presence / Pressure (H5121/5123/5127/5129/5130) | **Broadcast-only / gateway-managed** | State via advert or via gateway; no per-SKU BLE control. |
| Kitchen Electronic → **BBQ meat thermometers** | **BLE-connect (monitor)** + broadcast | `pact_bbqnew`, `h5151`, `h5043` probe gateways. `sensors.md`. |
| Kitchen Electronic → **ice maker / kettle / cooker** | **BLE-controllable** (split modules) | `h7172` (ice maker) has full BLE controller set; kettles partly WiFi. |
| Air Treatment → humidifier / purifier / fan / heater / dehumidifier | **BLE-controllable** for split-module ones (`h7160`); many are WiFi/IoT-primary | `h7160` humidifier confirmed BLE controllers. |
| Gateway (H5040–H5044, H5151, R5044) | **WiFi/IoT primary**; BLE only for provisioning + sub-sensor relay | `gateway`, `h5042`, `h5043`, `h5151`. |
| Discontinued (WiFi-only, e.g. H5081 gt 4) | **WiFi/cloud-only** | No BLE stack. |

---

## 2. Master goodsType → package → command-set table (explicit registrations)

Authoritative: each row is a real `Pact.b()` / `DeviceGoodsType.b()` registration. Source =
that family's `pact/Support.java` (`addSupportPact()` / `b()`), verified by extraction.
"Command set" = where the device-specific byte layouts live; everything also inherits the
common set (`common-light.md`).

| goodsType(s) | Package | Representative SKUs | BLE? | Command-set / Mode source | Doc section |
|---|---|---|---|---|---|
| 43, 50, 90, 307 | `com.govee.h5080.pact` | H5080/H5082/H5083/H5085/H5160/H5161/H5089 | Yes (+broadcast) | `h5080/ble/controller/**` (switch, timer, delay, energy) | `plug-h5080`, `plug-h5089`, `iot-map` |
| 195 | `com.govee.h5086.pact` | H5086 Smart Plug Pro | Yes (+broadcast, energy chart) | `h5086/ble/controller/**` (V/A/W, kWh, chart svc `…4857`) | `plug-h5086` |
| 13, 17, 18, 19, 70, 71, 73, 74, 75, 83, 123, 136, 175, 176, 178, 187, 193, 204, 207, 234, 262 | `com.govee.dreamcolorlightv1.pact` / `com.govee.rgbiclight` | H6143-6147, H617x, H618x, H619x, H61Ax neon, TV backlights | Yes | DreamColor v1 Mode/scene/DIY/segment + rgbic capability map (`rgbiclight/Support.java:b()`) | `rgbic`, `common-light` |
| 21 | `com.govee.dreamcolorlightv2.pact` / `rgbiclight` | H611A RGBIC strip | Yes | DreamColor v2 Mode | `rgbic` |
| 44, 141, 351, 352 | `com.govee.rgbiclight` | H7090 car; H61C2/3/5 neon; H617G/H618G strips | Yes | rgbic Mode/segment | `rgbic` |
| 13 (bare) | `com.govee.barelightv1.pact` | H6145/H6146-class bare RGBIC | Yes | bare-light Mode (no segment color) | `rgbic`, `common-light` |
| 16 | `com.govee.homelightv1.pact` | H6148 RGBWW strip | Yes | HomeLightV1 ScenesV0 + BK variant | `common-light` |
| 1, 2, 6, 12, 16, 39, 40, 68, 78, 108, 143 | `com.govee.stringlightv2.pact` | H6121/H6170/H613x/H615x/H6178/H6192 strips & string | Yes | StringLight V2 Mode/scene | `common-light`, `rgbic` |
| 12 | `com.govee.tvlightv1.pact`, `com.govee.rgblight.h6179` | H6179 TV backlight | Yes | TV-light v1 Mode | `rgbic` |
| 23, 52, 112 | `com.govee.pact_tvlightv3.pact` | H6053/H6056/H6046 RGBIC TV light bars | Yes | TV light v3 Mode (DreamView) | `rgbic` |
| 24 | `com.govee.pact_tvlightv2.pact` | H6198/H6199 DreamView T1S/T1 | Yes | TV light v2 Mode | `rgbic` |
| 25 | `com.govee.pact_tvlightv4.pact` | H6049/H6054 DreamView P1/P1S | Yes | TV light v4 Mode | `rgbic` |
| 82, 120, 138, 142, 172, 192, 243, 360 | `com.govee.pact_h605b.pact` | H605B/H605D, H605C, H6601/6602, H6603/6604, H6608/6609, H8604, H2A40/41 TV Backlight 3 | Yes | DreamView/AI-sync-box Mode | `rgbic` |
| 95, 109, 122, 133 | `com.govee.h604a.pact` | H604A/H604B/H604C/H604D DreamView G1 | Yes | DreamView G1 Mode | `rgbic` |
| 27, 37, 42, 58, 59, 84, 395 | `com.govee.hollowlamp.pact` | H6050/H6051/H6052/H6055/H6058/H6059/H1771 Aura/portable/table lamps | Yes | Hollow-lamp Mode | `common-light` |
| 22, 128 | `com.govee.tablelampv1.pact` | H6052 Aura, H6078 Cylinder Floor Lamp | Yes | TableLamp v1 Mode | `common-light` |
| 104 | `com.govee.h6057.origin.pact` | H6057 Night Light | Yes | H6057 night-light Mode | `common-light` |
| 6 | `com.govee.carlightv1.pact` | H6118/H6194 car lights | Yes | Car-light v1 Mode | `rgbic` |
| 3, 5 | `com.govee.bulblightstringv1.pact` | H7002 string light | Yes | Bulb-string v1 Mode | `common-light` |
| 125, 141, 180, 184, 240, 250, 394 | `com.govee.h705a.pact` | H705A-F Permanent Lights, H706x Pro, H7067-9 Deck, H608x String Downlights, H3401 | Yes | Permanent/outdoor segment Mode | `rgbic`, `common-light` |
| 134, 185, 216 | `com.govee.h70b1.origin.pact` | H70B1/H70B3-5/H70BC Curtain Lights | Yes | Curtain-light Mode | `rgbic` |
| 32 | `com.govee.pickupbox.pact` | H1161 Govee Sync (pickup box) | Yes | PickUpBox Mode | — |
| 87, 137, 182, 186 | `com.govee.h1162` | H1162/H1163/H1167/H1168 Music/Sync/Show boxes | Yes | h1162 + Model1168 | — |
| 7, 8, 14, 66, 106, 124, 154, 190, 194, 287, 310, 319, 320, 330, 369 | `com.govee.thnew` | H5100-5112, H5074/75, H5179, H5106 air, H5140 CO₂, H5220 clock, H5310 | BLE GATT (config/history) + broadcast state; **monitor-only** | TH-new opcode map + temp/hum encodings | `sensors` |
| 85, 155, 169, 281, 282, 314, 344 | `com.govee.pact_bbqnew` | H5198/H5199, H5196, H5191/H5192, H5194, H5610 BBQ probes | BLE-connect monitor + broadcast | BBQ multi-probe opcode map | `sensors` |
| 65 | `com.govee.h5151.pact` | H5151 BT-WiFi gateway / legacy BBQ relay | BLE provisioning + relay | Gateway model | `sensors` |
| 158, 291 | `com.govee.h5043.pact` | H5043/H5044/R5044 gateway 2 + leak/TH sub-sensors | WiFi/IoT + BLE setup; sub-sensors broadcast | Maker + Model4Tem/TemHum | `sensors` |
| 198 | `com.govee.h5042.pact` | H5042 gateway 1s | WiFi/IoT + BLE setup | gateway Model | `sensors` |
| 99 | `com.govee.h7160` (split `pact_h7160`) | H7160 humidifier | **BLE-controllable** | `h7160/ble/controller/**` mode/child/abnormal | `sensors` |
| 117, 211 | `com.govee.h7172` (split `pact_h7172`) | H7172/H717D ice maker | **BLE-controllable** | `h7172/ble/controller/**` (ice size, equip status) | `sensors` |

Legacy strip `sku/` packages (`h6102/h6104/h6105/h6127/h6129/h6159/h6160/h612526/h613839/h7022`)
claim the **early RGB/RGBIC goodsTypes 0,1,2,3,4,5,6,7,8,9,10,15,16,21,22** by `(pactType,pactCode)`;
they are the discontinued first-gen strips/bulbs and reuse the common + DreamColor-v1 Mode set.
(The large trailing numbers in their constants are decompiler line artifacts, not goodsTypes.)

---

## 3. goodsTypes with NO per-family package (data-driven / common-set only)

These appear in the catalog but are **not** registered by any `pact/Support.java`. They resolve
through `base2light/pact/newdetail` + `skubusiness` using cloud-downloaded capability descriptors,
and their wire protocol **is** the common `base2light` set (`common-light.md` / `rgbic.md`).
Confirmed absent from all `Pact.b()` registrations: e.g. **64** (H6004-H6013 bulbs), **111**
(downlights), **209** (Floor Lamp 2), **210/249** (table lamps), **235/302/303/356/370/373/390**
(ceiling lights), **261/264/299/123(new)/239/246** (M1/COB strips), **360/327** (TV Backlight 3),
**376/377** (Floor Lamp 3), **386** (Permanent Lights 2 Pro), and essentially the entire **300–400
goodsType band** of Indoor/Outdoor/Strip lights. Treat any catalog light SKU whose goodsType is not
in §2 as: **BLE-controllable via the common command set, no extra family opcodes shipped in-APK.**

---

## 4. Practical SKU→capability rollup

To classify any of the 617 catalog SKUs:

1. Look up its goodsType in `_sku_catalog.md`.
2. If goodsType is in **§2**, use that package's command-set doc.
3. Else if its catalog **category is a light** (Indoor/Outdoor/LED Strip/Other Lights), it is
   **BLE-controllable via the common set** (§3) — `common-light.md` + `rgbic.md`.
4. Else map by category in **§1** (plug / sensor / gateway / appliance).

Plugs (Controller, goodsType 43/50/90/195/307): the only first-class **BLE control + state**
non-light targets, fully documented in `plug-*.md` + `iot-map.md` + `crypto.md`.

---

## 5. Could-not-map / caveats

- **Buttons / remotes / motion / door / leak sensors** (H5121–H5130, H5054): listed in catalog
  (goodsType 130/131/132/139/144/145/183/206/238 etc.) but have **no BLE control or per-family
  package in this APK**; they are scene-trigger / broadcast / gateway-relayed. Classified
  broadcast-only/gateway-managed — not directly BLE-controllable.
- **Many goodsType-0 SKUs** in the catalog (discontinued bulbs/strips/sensors) carry no goodsType
  and rely on `(pactType,pactCode)` + the legacy `sku/` packages or are WiFi-only; exact package
  is ambiguous from goodsType alone.
- **Kettles / cookers / purifiers / fans / heaters / dehumidifiers** (Air Treatment & Kitchen):
  catalog goodsTypes exist but per-SKU BLE controller code is **not in the base APK** (split feature
  modules ship separately, like `pact_h7160`/`pact_h7172`); BLE-controllability is per-module and
  could not be confirmed for all of them here. Confirmed BLE: H7160 (gt 99), H7172/H717D (gt 117/211).
- goodsType↔package is **many-to-many**; always check `(pactType,pactCode)` when a goodsType has
  multiple §2 rows (notably 12, 13, 16, 71, 141, 351, 352).
- Cross-family detail bytes are NOT re-derived here; see the cited sections.
