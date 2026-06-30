# H5086 Smart Plug Pro (energy-monitoring) — BLE protocol

Section ID: `plug-h5086`
SKU `H5086`, model name "Smart Plug Pro" (`H5086Constants.java`). This is the energy-metering plug: instantaneous V/A/W + cumulative kWh, hourly/10-minute energy charts, power-warning + auto-off thresholds, a runtime "time monitor" session, child-lock, indicator-light schedule, delay on/off, and 4-slot timers.

Source root: `re_apk/decompiled/base/sources/com/govee/h5086/ble/**`.

---

## 1. Transport / GATT

| Role | UUID | Source |
|------|------|--------|
| Primary service | `00010203-0405-0607-0809-0a0b0c0d1910` | `BleComm.getServiceUuid` |
| Unified write+notify char (control/read) | `00010203-0405-0607-0809-0a0b0c0d2b11` | `BleComm.getCharacteristicUuid`, `BleMultiComm.getCharacteristicUuid` |
| Notify service (device-state notifies) | `00010203-0405-0607-0809-0a0b0c0d1910` | `BleNotifyComm.getServiceUuid` |
| Chart "self-comm" chip service (Telink INTELL_ROCKS, HW=4857) | `494e5445-4c4c-495f-524f-434b535f4857` | `BleComm.isSelfComm`, `BleNotifyChartComm.getServiceUuid` |
| Chart write characteristic (G2) | `494e5445-4c4c-495f-524f-434b535f2014` | `ChartPrepareInfoController.d/e`, `ChartTimeRangeController.d/e` |
| Chart history-data characteristic (H2) | `494e5445-4c4c-495f-524f-434b535f2015` | `BleComm.isChartData` (`str2 == H2`) |

`BleComm.q()` accepts service `...1910` **or** the Telink `...4857` service, so the same connection carries both the normal command channel (`...1910/2b11`) and the chart channel (`...4857/2014/2015`).

### 1.1 Frame format (single command, 20 bytes)

Built by `BleUtils.p(proType, commandType, ext)` / `generate20Bytes` (`base2kt/utils/BleUtils.java:1000`):

```
byte[0]  = proType   : 0x33 write/control, 0xAA read/query, 0x3A "secure write" (unused by H5086)
byte[1]  = commandType (opcode) — from controller.getCommandType()
byte[2..18] = ext payload (≤17 bytes, zero-padded)
byte[19] = BCC = XOR of bytes[0..18]   (BleUtils.v, base2kt/utils/BleUtils.java:1208)
```

`proType` is chosen by `AbsControllerNoEvent4Single.getProType()` (`base2light/ble/controller/AbsControllerNoEvent4Single.java:135`): write controllers → `0x33`, read controllers (`AbsMustController4Read`, write-flag false) → `0xAA`. **The per-feature opcode tables below list the `commandType` byte; the actual `byte[0]` is `0x33` for the write form and `0xAA` for the read form of the same opcode.**

### 1.2 Response / notify slicing

- **Read responses** (`0xAA` echo on `...2b11`): framework strips `byte[0..1]` and hands the controller callback the **17-byte payload = frame[2..18]** (`AbsSingleController.m`, `AbsControllerNoEvent4Single.g`). All `it2[n]` offsets in the controllers below are into this payload.
- **Notify frames**: begin `0xEE` (-18). `AbsNotify.parse` (`base2light/ble/comm/AbsNotify.java:31`) matches `frame[0]==0xEE`, then dispatches by `comType = frame[1]` to the `AbsNotifyParse` whose `c()` matches; `AbsNotifyParse.d` then copies `frame[2..18]` (17 bytes) to the parser's `e()`. So a notify is `[0xEE, comType, payload(17), XOR]` and the payload offsets equal the read-response offsets.

### 1.3 Integer / byte encodings (`BleUtils`, all big-endian when `z5=true`)

- `H(bytes, true)` = big-endian **unsigned** int (`:168`).
- `BleUtil.getSignedInt(bytes, true)` = big-endian **signed** int.
- `C(int, true)` = 2-byte big-endian (`:88`).
- `E(long, true)` / `getSignedBytesFor4(long, true)` = 4-byte big-endian (`:118`).
- Sentinel `0xFF…FF` (all bytes -1) = "unset / no value" (see RecentOneHour, Light, PowerWarning).

---

## 2. Opcode map (command channel `...1910 / 2b11`)

`commandType` is `byte[1]`. "Dir" = whether the app issues it as write (`0x33`) or read (`0xAA`), and/or whether the device emits it as a `0xEE` notify.

| Feature | commandType (hex) | Dir | Sub-byte (payload[0]) | Source |
|---------|------|-----|-----------------------|--------|
| Main switch | `0x01` | write `0x33` / read `0xAA` | — | `SwitchController` |
| Delay on/off | `0xB0` | write `0x33` / read `0xAA` | 0=off-timer, 1=on-timer | `DelayOnOffController` |
| Child lock | `0x1F` | write `0x33` / read `0xAA` | 2 (set sub-cmd) | `ChildLockController` |
| Indicator light (do-not-disturb sched) | `0x16` | write `0x33` / read `0xAA` | — | `LightController` |
| Instantaneous electric read | `0x19` | read `0xAA` + notify `0xEE 0x19` | — | `DeviceElectricController`, `DeviceStateNotifyParse` |
| Power warning (V1, combined) | `0x27` | write `0x33` / read `0xAA` | (write-off uses sub 2) | `PowerWarningController` |
| Power warning (V2) | `0x28` | write `0x33` | 1=warning, 2=auto-off | `PowerWarningControllerV2` |
| Device basic info (MAC + fw) | `0x07` | read `0xAA` | 0x10 | `DeviceBasicInfoController` |
| Wi-Fi module info | `0x07` | read `0xAA` | 0x11 | `WifiInfoController`; notify `0xEE 0x11` `WifiNotifyParse` |
| Exception / fault state | `0x17` | write `0x33`(query) / read `0xAA` | — | `ExceptionStateController` |
| Sync time | `0xB5` | write `0x33` | — | `SyncTimeController` |
| Recent-1-hour chart (10-min) | `0x01` + sub `0x0D` | read (single-send/multi-back) | 0x0D | `RecentOneHourChartController` |
| Timer read (4 slots) | `0x01` + sub `0x13` | read (single-send/multi-back) | 0x13 | `TimerReadController` |
| Timer write | `0xB4` | write `0x33` | — | `TimerWriteController` |
| Timer delete | `0x15` | write `0x33` | — | `TimerDeleteController` |
| Time-monitor session | `0x1A` | write `0x33` / read `0xAA` + notify `0xEE 0x1A` | — | `TimeMonitorController`, `TimeMonitorNotifyParse` |
| Secret key handshake (read) | `0xB1` | read | — | `SecretController` |
| Secret key handshake (write) | `0xB2` | write | — | `SecretController` |
| "Read-all" refresh trigger (notify) | `0xAA` | notify `0xEE 0xAA` | — | `ReadAllNotifyParse` |

`ControllerProtocol.java` collects the raw opcode constants (signed decimals): `b=7, c=2, d=3, e=6, f=16, g=17, h=6, i=20, j=32(0x20), k=33(0x21), l=-79(0xB1), m=-78(0xB2), n=-77(0xB3), o=1, p=-75(0xB5), q=-80(0xB0), r=-76(0xB4), s=19(0x13), t=21(0x15), u=31(0x1F), v=22(0x16), w=25(0x19), x=26(0x1A), y=-86(0xAA), z=23(0x17), A=39(0x27), B=40(0x28), C=13(0x0D)`.

---

## 3. Control commands (writes)

### 3.1 Main switch — `0x01`
`SwitchController.d(boolean on)` → payload `{on?1:0}`. Frame `33 01 [01|00] 00…  XOR`.
Read `SwitchController.b`: state = `it2[0] == 1`.

### 3.2 Delay on/off timer — `0xB0`
`DelayOnOffController` (`getCommandType` = `0xB0`):
- Write **on-timer**: `h(hour, min)` → payload `{1, hour, min}`.
- Write **off-timer**: `g(hour, min)` → payload `{0, hour, min}`.
- Read on-timer: `e(...)` sends payload `{1}`; read off-timer: `c(...)` sends `{0}`.
- Read parse (both): `hour = it2[1]`, `min = it2[2]`, `remainSeconds = getSignedInt(it2[3..5], BE)` (24-bit). i.e. response = `{selector(0/1), hour, min, sec_hi, sec_mid, sec_lo}`. `remainSeconds` is the live countdown.

### 3.3 Child lock — `0x1F`
`ChildLockController.d(boolean)` → payload `{2, locked?1:0}` (sub-cmd 2). Read `b`: locked = `it2[1] == 1`.

### 3.4 Indicator light schedule (do-not-disturb) — `0x16`
`LightController.d(NotDisturbInfo)` → payload `{isEnable, startHour, startMin, endHour, endMin, isForever}` (each a byte). `isEnable`/`isForever` are the raw `byte` values from `NotDisturbInfo`.
Read parse `LightController.e(payload)`:
- `enable = payload[0] == 1`, `forever = payload[5] == 1`.
- If `getSignedInt(payload[1..4]) == -1` (sentinel) → no window: start 00:00, end 23:59.
- Else `startHour=u8(payload[1])`, `startMin=u8(payload[2])`, `endHour=u8(payload[3])`, `endMin=u8(payload[4])`.
- `f(bytes20)` variant slices `bytes20[2..18]` first (parse straight from a raw 20-byte frame).

### 3.5 Sync time — `0xB5`
`SyncTimeController.a()` → payload `{ts[0..3] = unixSeconds BE, 1, tzOffsetHours, tzOffsetMinutes}`. `ts = E(System.currentTimeMillis()/1000, true)`; `tzOffsetHours = TimeZoneUtil.getTimeOffset()`, minute part `getTimeOffset4Minute()`. payload[4] constant = 1.

### 3.6 Exception state — `0x17`
`ExceptionStateController.d()` writes query payload `{1}`. Read `b`: exception/fault present = `it2[0] == 1`.

---

## 4. Energy monitoring

### 4.1 Instantaneous electric read — `0x19`  (`DeviceElectricController`)
Read (`0xAA 0x19`) and also pushed as notify `0xEE 0x19` (`DeviceStateNotifyParse`, `c()=25`). Both call `DeviceElectricController.d(payload)`. Layout (13 payload bytes, all big-endian signed via `getSignedInt(…, true)`):

| Payload bytes | Field | Decode | Unit |
|---------------|-------|--------|------|
| `[0..2]` (24-bit) | `runtime` | `getSignedInt / 60` | minutes (raw is seconds) |
| `[3..5]` (24-bit) | `electricUse` | `getSignedInt / 10000.0` | kWh (cumulative energy) |
| `[6..7]` (16-bit) | `volts` | `getSignedInt / 100.0` | V |
| `[8..9]` (16-bit) | `amps` | `getSignedInt / 100.0` | A |
| `[10..12]` (24-bit) | `activePower` | `getSignedInt / 100.0` | W |

Result object `ElectricData(runtime, electricUse, volts, amps, activePower)` (`network/entity/ElectricData.java`).
`DeviceElectricController.e(bytes20)` slices `[2..18]` then calls `d`. Notify path: `DeviceStateNotifyParse.e` → `DeviceStateCallbackManager.c(ElectricData)`.

### 4.2 Power-warning + auto-off thresholds

**V1 — `0x27` (`PowerWarningController`)**

Read `b` parses 8 payload bytes into `PowerWarningInfo(warningOpen, warningValue, warningIsSet, offOpen, offValue, offIsSet)`:

| Field | Source | Notes |
|-------|--------|-------|
| `warningOpen` | `it2[1] == 1` | over-power alert enabled |
| `warningValue` | `H(it2[2..3], BE)` | alert threshold, **watts** |
| `warningIsSet` | `it2[0] == 1` | threshold configured flag |
| `offOpen` | `it2[5] == 1` | auto-cut-off enabled |
| `offValue` | `H(it2[6..7], BE)` | auto-off threshold, watts |
| `offIsSet` | `it2[4] == 1` | auto-off configured flag |

Write forms:
- `d(Boolean warningOpen, Integer warningValue)` → payload `{flag, valHi, valLo}` where `flag = TRUE?1 : FALSE?0 : -1` and value = `C(value, BE)` or `{-1,-1}` when null. Sets the **warning** threshold.
- `e(boolean offOpen, Integer offValue)` → payload `{2, offOpen?1:0, valHi, valLo}` (sub-cmd 2). Sets the **auto-off** threshold.

**V2 — `0x28` (`PowerWarningControllerV2`)** (write-only; newer firmware, gated by `ReadInfoController` version ≥2 logic):
- `b(boolean on, Integer value)` → payload `{1, on?1:0, valHi, valLo}` — set **warning** (sub 1).
- `a(boolean on, Integer value)` → payload `{2, on?1:0, valHi, valLo}` — set **auto-off** (sub 2).
- value = `C(value, BE)` or `{-1,-1}` if null.

### 4.3 Time-monitor session — `0x1A`  (`TimeMonitorController`)
A user-started "measure usage over time" session. Write `d(boolean running, int hour, int min, long id)` → payload `{running?1:0, hour, min, id[0..3] BE}` (`id` is a session id / start-timestamp, 4-byte BE via `getSignedBytesFor4`).

Read/notify parse `e(payload)` → `TimeMonitorInfo(id, state, hour, minute, remainSeconds, electUse)`:

| Field | Payload | Decode |
|-------|---------|--------|
| `id` | `[0..3]` (32-bit) | `getSignedInt(BE)` |
| `state` | `[4]` | byte |
| `hour` | `[5]` | byte |
| `minute` | `[6]` | byte |
| `remainSeconds` | `[7..9]` (24-bit) | `getSignedInt(BE)` |
| `electUse` | `[10..12]` (24-bit) | `getSignedInt(BE)` |

Notify `0xEE 0x1A` (`TimeMonitorNotifyParse`, `c()=26`) → `DeviceStateCallbackManager.e(TimeMonitorInfo)`. (`electUse` scaling here is raw int; the UI/network layer applies kWh conversion. Flag: exact unit of `electUse` in this BLE struct not divided in `TimeMonitorController.e` — treat as raw, likely watt-hours or the same /10000 kWh applied downstream.)

---

## 5. Chart-history protocols

Two distinct history reads exist.

### 5.1 Recent 1 hour @ 10-min resolution — `0x01` sub `0x0D`  (`RecentOneHourChartController`)
`AbsController4BleSingleSendMultiBack`: one write request, multiple `0xAA` packets reassembled, then `f(validBytes)` parses the concatenated buffer:
- `validBytes[0..3]` = start timestamp, **seconds**, `H(BE)` unsigned. Rounded down to a 10-minute boundary (`c()`).
- Then entries of **3 bytes** starting at offset 4. Entry `i` (`g(start, entryBytes, i)`):
  - sample time = `startRounded + i*600` seconds (600 s = 10 min step).
  - if all 3 bytes == `0xFF` → empty slot (no data).
  - `value0 = H(entry[0], BE)` (1 byte) — stored as `ChartViewInfo` int field (instantaneous/avg power indicator).
  - `valueFloat = H(entry[1..2], BE) / 10000.0` — energy, **kWh** per 10-min bucket.
- Results merged into `LocalChartRepository.f()` (`ChartViewInfo`).

### 5.2 Bulk multi-hour history (charts screen) — Telink chart channel
Driven by `AbsBleWithChartDataComm` over the `...4857` service. Sequence:

1. **Prepare** — `ChartPrepareInfoController`: write `33 02` (commandType `0x02`, empty payload) on char **G2 = `…2014`**. Result callback `(success, commandType, proType)`.
2. **Time range** — `ChartTimeRangeController`: write `33 01` on char **G2** with 8-byte payload `q()` = `{start[0..3] BE, end[0..3] BE}` (both unix seconds, `getSignedBytesFor4`).
3. **Data packets** — device streams on char **H2 = `…2015`** (matched by `BleComm.isChartData`, `str2 == H2`). Each packet parsed by `AbsBleWithChartDataComm.K(now, startSec, endSec, bArr)`:
   - `packetIndex = H(bArr[0..1], BE)`.
   - 5 hourly entries, 3 bytes each, starting at offset 4 (`bArr[4 + i*3 .. +3]`, i = 0..4):
     - if all `0xFF` → skip.
     - sample time = `startSec + (packetIndex + i) * 3600` seconds (**3600 s = 1 hour step**).
     - `H5086ChartTable(time, sku, device, entry[0], H(entry[1..2], BE), 2)` — `entry[0]` = 1-byte value, `entry[1..2]` = 2-byte BE energy value. (Scaling to kWh applied downstream; raw stored.)
4. **Flow-control notifies** on the Telink chip service, marker `0xEE` (`ChartStateNotifyParser`, `BleNotifyChartComm`):
   - `payload[0] == 2` → "device querying / preparing data" → `ChartInfoStateCallbackManager.c()` (`onDataQuery`), app re-arms a 10 s watchdog.
   - `payload[0] == 1` → "read complete", `totalPackets = getSignedInt(payload[1..2], BE)` → `onDataOver(totalPackets)`.
   - (Note: chart-notify payload offsets are `frame[1]=status`, `frame[2..3]=count`, because `AbsNotifyParse.d` strips one leading byte from the `0xEE` frame.)

Watchdog: `f119014u0 = 1001` message, `f119013t0 = 10000` ms timeout (`AbsBleWithChartDataComm`). On timeout or `onDataOver`, a `FinishRunnable` calls `IChartFinishListener.onChartDataFinished`.

---

## 6. Device / Wi-Fi info reads (shared opcode `0x07`)

Both use commandType `0x07` (read `0xAA 07`), disambiguated by **payload[0] sub-byte**.

### 6.1 Device basic info — sub `0x10`  (`DeviceBasicInfoController`)
Constructed `super(new byte[]{16})` → request payload `{0x10}`. Response parse `d(validBytes)`:
- `validBytes[1..8]` (8 bytes) → BLE address via `BleUtil.toAddressBytes(…, false)`; a leading `00:00:` prefix is stripped.
- `validBytes[9..11]` → **soft (firmware) version** via `b(bArr)` = `"<bArr[0]>.<%02d bArr[1]>.<%02d bArr[2]>"`.
- `validBytes[12..14]` → **hard version** (same format).
- `validBytes[15]` → a 1-byte field (decompiled callback passes `Integer.valueOf(new byte[1][0])` — effectively 0; value semantics unclear, flagged).
- `e(bytes20)` variant slices `bytes20[2..18]` first.

### 6.2 Wi-Fi module info — sub `0x11`  (`WifiInfoController`)
Constructed `super(new byte[]{17})` → request payload `{0x11}`. Response parse `d(validBytes)`:
- `validBytes[1..6]` (6 bytes) → Wi-Fi MAC (`BleProtocolUtils.parseWifiMac`).
- `validBytes[7..9]` → Wi-Fi **soft version** (`major.minor.patch`).
- `validBytes[10..12]` → Wi-Fi **hard version**.

Wi-Fi connect notify `0xEE 0x11` (`WifiNotifyParse`, `c()=17`): `EventNotifyWifiConnect.sendEventWifiConnect(value[0] == 0)` — `value[0]==0` ⇒ connected.

---

## 7. Timers (4 slots)

### 7.1 Read — `0x01` sub `0x13`  (`TimerReadController`)
`AbsController4BleSingleSendMultiBack`, request payload `{0x13}`. Reassembled buffer split into **4-byte records** (`e`), record `i` = timer group `i`. `d(record, group)`:
- `record[0]`: bit `0x80` set ⇒ `enable`; low nibble (`&0x0F`) == 1 ⇒ `open` (on-action).
- `enableAndSwitch` recombined via `TimerInfo.Companion.f(enable, open)`.
- `record[1]` = hour (`u8`), `record[2]` = min (`u8`).
- `record[3]` = repeat bitmask (weekday bits).

### 7.2 Write — `0xB4`  (`TimerWriteController`)
`a(TimerInfo)` → payload `{group, enableAndSwitch, hour, min, repeat}`.

### 7.3 Delete — `0x15`  (`TimerDeleteController`)
`a(int group)` → payload `{group}`.

---

## 8. Secret-key handshake — `0xB1` / `0xB2`  (`SecretController`)

`getCommandType()` returns `0xB2` when writing, `0xB1` when reading (`return d() ? -78 : -79`).
- **Read** (`0xAA?`/`0xB1`): response `c(it2)` — if `it2[0]==1`, the 8 bytes `it2[1..8]` are the secret, base64-encoded for storage; else null.
- **Write** (`0xB2`): `d(String secretCodeBase64)` → payload = base64-decoded bytes (`Encode.decryByBase64`).

These are the SINGLE_READ_SECRET_KEY (`0xB1`) / SINGLE_CHECK_SECRET_KEY (`0xB2`) handshake opcodes (matches the global framework). Used during pairing (`SecretController` referenced from add/pair flow).

---

## 9. Composite read — `ReadInfoController`

`ReadInfoController(boolean full, int version, …)` chains many controllers into one read (`AbsComposeControllerWithOpResult`, `s(2)` retry). Issued order:

- If `full`: `SyncTime` (write), `DeviceBasicInfo`(0x07/0x10), `TimeMonitor`(0x1A), `TimerRead`(0x01/0x13), **if `version ≥ 2`** `RecentOneHourChart`(0x01/0x0D), `PowerWarning`(0x27).
- Always: `Switch`(0x01), `ExceptionState`(0x17), `DelayOnOff` on(0xB0/sub1) + off(0xB0/sub0), `ChildLock`(0x1F), `DeviceElectric`(0x19), `Light`(0x16).

On success returns `(ReadInfo, TimeMonitorInfo, List<TimerInfo>, List<ChartViewInfo>, exceptionFlag, PowerWarningInfo)`. The version-gate at `version ≥ 2` is the practical signal for which power-warning/chart variant the firmware supports.

`PairToDeviceInfoReadController` is a lighter composite used during pairing: `DeviceBasicInfo`(0x07/0x10) + `WifiInfo`(0x07/0x11) → soft/hard/wifi versions + wifi MAC + uuid.

---

## 10. Notify summary (frames begin `0xEE`)

| comType (frame[1]) | Meaning | Payload | Handler |
|--------------------|---------|---------|---------|
| `0x19` | Live electric push | V/A/W/kWh/runtime (see §4.1) | `DeviceStateNotifyParse` → `DeviceStateCallbackManager.c` |
| `0x1A` | Time-monitor update | TimeMonitorInfo (see §4.3) | `TimeMonitorNotifyParse` → `…e` |
| `0x11` | Wi-Fi connect state | `payload[0]==0` ⇒ connected | `WifiNotifyParse` |
| `0xAA` | "Read-all" refresh trigger | — | `ReadAllNotifyParse` → `DeviceStateCallbackManager.d()` |
| `0xEE`+status (Telink chart svc) | Chart flow-control | `[0]=1` done(+count), `[0]=2` querying | `ChartStateNotifyParser` |

Special early-return in `AbsBleWithChartDataComm.parse`: if `bytes[0]==0xAA && bytes[1]==0x01` the frame is swallowed (chart time-range read echo) and not re-dispatched.

---

## 11. Uncertainties / flags

- `DeviceBasicInfo` payload[15] is read but the decompiled callback passes a constant 0 (`new byte[1][0]`); real semantics unknown.
- Chart bulk-history energy value (`entry[1..2]`, §5.2) and `TimeMonitorInfo.electUse` (§4.3) are stored raw; the kWh scale factor (likely `/10000` as in §4.1) is applied in the DB/network layer, not in the BLE parse — not 100% confirmed from BLE code alone.
- `SyncTimeController` payload[4]=1 constant meaning (likely "12/24h" or "DST present") not decoded.
- `0x3A` "secure write" proType exists in the framework but no H5086 controller sets the secure flag, so all H5086 writes observed are plain `0x33`.
