# BLE Advertisement / Broadcast Parsing (`section_id: broadcast`)

How the Govee Home app **discovers**, **identifies**, and **reads passive state from** BLE
advertisements. Covers (1) the raw scan path, (2) device identification by local-name +
manufacturer-specific data, (3) the protocol-info (`pactType` / `pactCode`) decode used during
pairing, and (4) **passive state decode from manufacturer data — including the plug on/off byte.**

All byte values below are converted from jadx's signed decimals to hex via `(v & 0xFF)`.

---

## 1. Scan pipeline (where the bytes come from)

| Stage | File:method | Note |
|---|---|---|
| Android scan callback | `com/govee/ble/scan/BleScanCallbackImp21.java :: j(ScanResult)` | Pulls `scanResult.getScanRecord().getBytes()` — the **entire raw AD payload** (not split into mfr-data fields). De-dups per MAC (3 s window) and optional RSSI gating. |
| Filters | `BleScanCallbackImp21 :: g(ScanParams)` | `ScanFilter` by service-UUID, MAC, or device-name only. **No manufacturer-id ScanFilter** — identification is done in software from the raw bytes. |
| Callback fan-out | `com/govee/ble/scan/ScanResultCallback.java :: onResult(device, byte[] scanRecord, int rssi)` | The raw `scanRecord` byte[] is the unit every parser below consumes. |
| Discovery → event | `ScanResultCallbackFoundImp :: FoundDeviceRunnable.run()` → `com/govee/ble/event/ScanEvent.java :: sendScanEvent` | Used by the **add/pairing** UI. `ScanEvent.c()` returns the raw bytes, `.a()` the `BluetoothDevice`, `.b()` the RSSI. |
| Passive state → event | `com/govee/ble/scan/ScanResultCallbackBroadcastImp.java :: onResult/BroadcastParseRunnable` → `com/govee/base2home/main/ble/BleBroadcastImp.java :: c()` → `com/govee/base2home/main/ble/EventBleBroadcast.java :: sendEventBleBroadcast` | Used by the **device-list / live-status** path. Carries raw `scanRecord` to per-device models. |

The **raw scanRecord is a standard BLE AD structure list** (`[len][type][data…]` repeated). Govee's
parsers all hand-walk it with the loop `i += getUnsignedByte(scanRecord[i]) + 1`. **Almost every
parser hard-requires `scanRecord.length == 62`** (`com/govee/base2home/pact/BleUtil.java`); a record
of any other length returns "not Govee / no state".

---

## 2. Device identification

### 2a. Local-name prefixes (primary discriminator during pairing)
`com/govee/base2home/main/choose/BaseBleProcessor.java :: parse(ScanEvent)` switches on
`BluetoothDevice.getName()`:

| Prefix const | Value | Handler | Name→SKU decode |
|---|---|---|---|
| `f40708b` | `ihoment_` | `c()` (V0) | name `split("_")` → `[1]`=SKU, `[1]_[2]`=full name. e.g. `ihoment_H5080_AB12`. |
| `f40709c` | `Govee_` | `c()` (V0) | same split-by-`_`, length must be 3. |
| `f40710d` | `Minger_` | `c()` (V0) | same. |
| `f40714h` | `GBK_` | `d()` (V1) | same 3-part split. |
| `f40711e` / `f40712f` | `GVH` / `GVR` | `e()` (V2) | `substring(2, indexOf('_'))` = SKU; falls through to `f()` if no `_`. |
| `f40713g` | `GV` | `g()` (V3) | `"H"+substring(2,6)` = SKU (e.g. name `GV5080…` → `H5080`), remainder = id. Sets `bcContent` = raw record. |
| (no `_`, GVH/GVR) | `f()` (V2.1) | `substring(2,7)`=SKU, `substring(7,11)`=id; needs `len ≥ 11`. |

SKU string → numeric `goodsType` via `com/govee/base2home/pact/Pact.java :: d(sku)`. If
`goodsType == 0` the device falls back to legacy "old light/bulb/car/rgbic" sniffers
(`OldDreamColorUtil`, `OldBulbUtil`, `OldRgbBkUtil`, …) which also read the raw record.

### 2b. Manufacturer-specific data — the Govee company ID
The authoritative byte signature checked by every Govee parser is the constant
`BleUtil.f41010h = { (byte)0x88, (byte)0xEC }` (jadx: `{-120, -20}`, where `-120` resolves through
`IMusicEffectStatic.multi_value_sub_separate_6063 = -120`).

This is the **2-byte Bluetooth SIG company identifier `0xEC88` stored little-endian as `88 EC`**,
carried inside the manufacturer-specific data AD (AD type `0xFF`). Parsers match
`scanRecord[k] == 0x88 && scanRecord[k+1] == 0xEC`.

> **Discrepancy to flag:** project memory records the H5080 advert as "mfr `0x8843`". The app code
> never references `0x8843`/`8843`; it matches `88 EC` (company `0xEC88`). The HA/empirical `0x8843`
> and the app's `0xEC88` are inconsistent — see Open Questions. The implementation-ready value from
> the app is **`88 EC`**.

### 2c. Other ID conventions seen in the app
* **BBQ / legacy service-UUID IDs** `BleUtil.f41011i = {0x51,0x81,0x82,0x83,0x84,0x85,0x86,0x98,0x99,0x92,0x96,0x91,0x94}` and `f41012j = {{0x56,0x10}}` — matched inside a 16-bit-service-UUID AD (type `0x03`) for `parseBleBroadcastPactBbqV1`.
* **`checkBroadcastData()`** scans for the first `0xFF` AD whose first two payload bytes equal `88 EC` and returns the index just past them (used as a generic "is this a Govee mfr block" probe).

---

## 3. Pairing protocol-info decode → `BleBroadCastInfo`

Dispatch: `com/govee/base2home/pact/GoodsType.java :: parseBleBroadcastPactInfo(goodsType, scanRecord, cb)`
selects a `BleUtil.parse…` variant by `goodsType`, then returns
`Protocol(pactType, pactCode)` when the parsed `flag == 1`.

`com/govee/base2home/pact/BleBroadCastInfo.java` fields (getter → meaning):
`h()/a()`=flag (1 = valid Govee block), `j()/b()`=**pactType**, `i()/c()`=**pactCode**,
`g()/d()`=**bbVersion** (broadcast format version), `k()/e()`=**supportEncryption**,
`l()`=ctor-arity marker (3 or 4). The `cb`/`FunCall` (`BaseBleProcessor.FunCall`) is invoked only when
`bbVersion > 3`, persisting `supportEncryption` into `ShortMemoryMgr`.

### 3a. Standard layout — `BleUtil.parseBleBroadcastPact(scanRecord)` (line 808)
Used by the large default `goodsType` set **and explicitly by plug goodsTypes 43/50/90/195/307**.
Walks AD structures; at the AD whose `len ≥ 6` and `type(==scanRecord[i+1]) == 0xFF`:

Let `p = i` (index of the AD length byte). Manufacturer value begins at `scanRecord[p+2]`.

| scanRecord offset | mfr value idx | Meaning |
|---|---|---|
| `p+2` | `v[0]` | **flags/version byte**: low nibble `& 0x0F` = `bbVersion` (accept if `==1` or `≥2`); bit6 `& 0x40` = `supportEncryption`. |
| `p+3` | `v[1]` | company ID low = `0x88` |
| `p+4` | `v[2]` | company ID high = `0xEC` |
| `p+5` | `v[3]` | **pactType** high byte |
| `p+6` | `v[4]` | **pactType** low byte → `pactType = getUnsignedInt(v[3],v[4]) = (v[3]<<8)|v[4]` |
| `p+7` | `v[5]` | **pactCode** (`getUnsignedByte`) |

Returns `BleBroadCastInfo(1, pactType, pactCode, bbVersion, supportEncryption)`.

### 3b. Variant parsers (same company-ID `88 EC`, different framing)

| Method (BleUtil) | goodsTypes | Key differences |
|---|---|---|
| `parseBleBroadcastPact4Th` (866) | 7,65,158,198,291 | Same offsets as 3a but accepts `bbVersion ≥ 1` (no `==1` special-case). |
| `parseBleBroadcastPact4MultiTh` (834) | 8,66,14,106,124,154,190,194,287,310,319,320,330,363,369 + th fallback | Company ID lives in a **service-data/UUID AD type `0x03`, len 3** (`scanRecord[p+2..p+3]==88 EC`); the following `0xFF` AD holds `flags=scanRecord[p+2]`, `pactType=getUnsignedInt(p+3,p+4)`, `pactCode=getUnsignedByte(p+5)`. |
| `parseBleBroadcastPactBbqV1` (892) | 28,29,33,34,47,48,85,155,169,281,282,314,344 | Match a `0x03` UUID AD against `f41011i`/`f41012j`; then in the `0xFF` AD: `flags=scanRecord[p+5]`, `pactType=getUnsignedInt(p+6,p+7)`, `pactCode=getUnsignedByte(p+8)`. |
| `parseH5140BleBroadcastPact` (1007) | 319 (H5140) | Uses `parseBleAdvertisement()` map; entry with `len==11 && val[0]==0xFF`: `flags=val[1]`, `pactType=getUnsignedInt(val[2],val[3])`, `pactCode=getUnsignedByte(val[4])`. |
| `parseH512xBleAddBroadcast` (995) | 130,131,132,139,144,145,206,238 (H512x) | **Exact-hex match**: record hex must start `0201060b09` and `hex[30:38]=="0fff88ec"` (AD `0x0f 0xFF` + company `88 ec`). Returns `{1,1,1}` (flag,pactType=1,pactCode=1). Confirms AD framing: `02 01 06`(flags) `0b 09`(local-name, 10 B) `0f ff 88 ec …`. |

### 3c. Special local-name → SKU shortcut
`com/govee/base2home/main/ble/BleParseUtil.java :: getParseName` reads **fixed raw offsets** (not AD
walking): `scanRecord[5..6]` → `"H"+hex` (only accepts `H5055`), `scanRecord[9..11]` → id; prefixes
`ihoment_`. Anchored to the `02 01 06 / 0b 09` layout (name payload starts at index 5).

---

## 4. Passive STATE decode from manufacturer data

State is read by the device model base class
`com/govee/kt/ui/device/base/AbsBaseBleModel.java` on each `EventBleBroadcast`
(`AbsPlug2Item.B()` → `AbsPlug2Model4BleIot` → `AbsBaseBleModel.z()/A()/y()`):

* `z(byte[])` (line 391) — re-derives `Protocol` from the record (calls `parseBleBroadcastPactInfo`); no state.
* **`A(byte[])` (line 60) — ON/OFF**: `int[] r = BleUtil.parseBleBroadOnOff(record, sku, device); if (r[0]==1) { boolean on = r[1]==1; DeviceSwitchConfig.setSwitch(...); }`
* `y(byte[])` (line 367) — day-sync flag: `BleUtil.parseBleBroadDaySyncInfo`.

### 4a. **Plug on/off — `BleUtil.parseBleBroadOnOff(scanRecord[,sku,device])`** (lines 728 / 747)
At the AD with `len ≥ 6`, `type == 0xFF`, **and `scanRecord[p+2] (>= signed) ≥ 2`** (i.e. flags/version
byte ≥ 2), company `scanRecord[p+3]==0x88 && scanRecord[p+4]==0xEC`:

```
return { 1, getUnsignedByte(scanRecord[p+8]), getUnsignedByte(scanRecord[p+9]) };
```

| scanRecord offset | mfr value idx | Meaning |
|---|---|---|
| `p+2` | `v[0]` | flags/version, **must be ≥ 2** for state to be present |
| `p+3,p+4` | `v[1],v[2]` | company `88 EC` |
| `p+5..p+7` | `v[3..5]` | pactType(hi,lo), pactCode (per §3a) |
| **`p+8`** | **`v[6]`** | **switch state → result[1]; `1 = ON`, `0 = OFF`** (`AbsBaseBleModel.A`: `on = r[1]==1`) |
| `p+9` | `v[7]` | second state byte → result[2] (likely the 2nd relay on dual-outlet plugs / aux state; not consumed by `A()`) |

So the plug on/off is the **7th byte of the manufacturer-specific value (`v[6]`), i.e. raw record
index `p+8`**, where `p` is the index of the manufacturer-data AD length byte. It is **not** literally
the last byte of the record (that's an artifact of short H5080 adverts where `v[6]` happens to be the
final populated byte). The companion `parseBleBroadOnOff(scanRecord)` (no sku) returns the same two
bytes.

Applicable plug goodsTypes (route through `parseBleBroadcastPact` per §3a and use the Plug2 model):
**43 (H5080 single), 50 (dual plug), 90 (triple, H5160), 307** — from
`com/govee/h5080/pact/Support.java` (`f118651m={43,90}`, `f118652n={50,307}`,
`f118653o={43,50,90,307}`). `isOldH5080(sku,ver)` = `H5080 && version ≤ 10008`.

> Dual-outlet note: `AbsPlug2Model4BleIot.K0()` inverts switch index logic for `goodsType == 50`
> (`goodsType!=50 ? !on : on`), so the two state bytes `v[6]`/`v[7]` map to left/right outlets with a
> per-goodsType polarity convention — confirm offset-to-outlet mapping on hardware.

### 4b. Other state-from-broadcast parsers (same `88 EC` block, `v[0] ≥ 2`)
| Method (BleUtil) | Returns | Meaning |
|---|---|---|
| `parseBleBroadDaySyncInfo` (649) | `{1, ub(scanRecord[p+9])}` | `v[7]` day-sync byte (`y()`). |
| `parseBleBroadTankState` (775) | `{1, ub(p+8)}` | `v[6]` tank state. |
| `parseBleBroadKettle` (704) | `{1, ub(p+8), ub(p+9), ub(p+10), signedInt(p+11..p+14)}` | kettle: state, target, current, temp32. |
| `parseBleBroadIceMaker` (678) | `{1, ub(p+8), ub(p+10), bit7(p+9), signedInt(p+11..14), ub(p+9)}` | ice-maker multi-field. |
| `parseBleBroadVersion` (794) | `scanRecord[p+2]` | raw broadcast version byte (default 2). |

All share the §4a framing: `0xFF` AD, `v[0] ≥ 2`, company `88 EC`, state fields begin at `v[6]`
(`p+8`).

---

## 5. Service / CCCD UUIDs used during pairing (context)
Scan filters can target service UUIDs (`BleScanCallbackImp21.g`), but Govee adverts are matched by
local-name + mfr-data, not service UUID. GATT service/char UUIDs (primary `…1910`, write+notify
`…2b11`, legacy split `…1911/1912`, CCCD `2902`) are established in the GATT section and are not part
of advertisement parsing.

---

## 6. Quick reference — manufacturer-data byte map (standard Govee block)

```
AD:  [p]=len  [p+1]=0xFF(type)  [p+2..]=mfr value
mfr value:
  v[0] = flags/version   (low nibble = bbVersion; bit6 0x40 = encryption; state requires >=2)
  v[1] = 0x88            company id low   ─┐ company 0xEC88 (LE 88 EC)
  v[2] = 0xEC            company id high  ─┘
  v[3] = pactType hi     ─┐ pactType = (v[3]<<8)|v[4]
  v[4] = pactType lo     ─┘
  v[5] = pactCode
  v[6] = switch/on-off   (1=ON, 0=OFF)   ← plug primary relay   [raw idx p+8]
  v[7] = switch2/aux                      ← plug 2nd relay       [raw idx p+9]
```
