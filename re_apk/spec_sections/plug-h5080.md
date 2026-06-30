# Plug Protocol — H5080 / H5082 / H5083 / H5085 / H5089 / H5160 / H5161 (V1–V4)

Source root: `re_apk/decompiled/base/sources/com/govee/h5080/**`

This section covers the Govee smart-plug family handled by the `com.govee.h5080`
module: the single-outlet H5080-class plugs, the multi-outlet H5160/H5161 strips,
and the H5089 night-light plug. All BLE commands are built from the shared
controller classes in `com/govee/h5080/ble/controller/**` (and a few generic
`com.govee.base2light.ble.controller.*`). The same controllers are reused by the
IoT/cloud `pt`-passthrough path (`com.govee.h5080.iot.CmdPtReal`), so the wire
bytes below are identical whether sent over BLE or as an IoT `ptReal` payload.

---

## 1. Transport / GATT

Source: `ble/BleComm.java`, `ble/BleMultiComm.java`, `ble/BleNotifyComm.java`, `ble/Ble.java`

| Role | UUID |
|------|------|
| Primary service | `00010203-0405-0607-0809-0a0b0c0d1910` (`BleComm.P`) |
| Unified write + notify characteristic | `00010203-0405-0607-0809-0a0b0c0d2b11` (`BleComm.Q`) |
| Multi-packet comm | same service/char (`BleMultiComm.L`/`M`) |

`BleNotifyComm.getServiceUuid()` → `BleComm.P`. Notify parsers registered:
`WifiNotifyParse` and `h5089/Notify4NightLight` (see §9).

---

## 2. Frame format & checksum (verified)

Single-command frames are built by `BleUtils.generate20Bytes(...)` →
`base2kt/utils/BleUtils.java` methods `o()` (4-arg, opcode+sub-byte) and `p()`
(3-arg, opcode only). Layout for a 20-byte single command:

```
byte[0]  = proType   : 0x33 write/control, 0xAA read/query   (AbsSingleController.getProType())
byte[1]  = commandType (opcode)                              (controller.getCommandType())
byte[2..18] = payload, zero-padded
byte[19] = BCC = XOR of bytes[0..18]                          (BleUtils.v(packet,19))
```

`AbsSingleController.getProType()` returns `0x33` when `isWrite()` else `0xAA`
(`base2light/ble/controller/AbsSingleController.java`). Read requests use payload
from `p()`; writes use payload from `q()`. Checksum `v()` is a plain XOR fold of
bytes 0..18 into byte 19 (`BleUtils.java:1208`).

Notify frames from the device begin `0xEE` (global). Encryption handshake
opcodes `0xB1` (read secret key) / `0xB2` (check secret key) are issued via
`base2light…SecretKeyController` from each `BlePactV1`/`BleOpV2`/`BleOpV4`
(`secretKeyController(...)`).

---

## 3. SKU ↔ goodsType ↔ Frame mapping

Source: `adjust/AdjustAc.java:18-19`, `pact/Support.java` (`addSupportPact`,
`getPlugNum`, `getDefHeaderRes`), `add/BleBroadcastProcessor.java`, `pact/V{1..4}BleIotSkuItem.java`.

| goodsType (pactType) | Frame builder | Outlets (`getPlugNum`) | SKUs / product | Notes |
|----------------------|---------------|------------------------|----------------|-------|
| 43 | `adjust/v1/FrameV1` | 1 | H5080, H5082, H5083, H5085 | FrameV1 also mounts a secondary `adjust/v3/UiV3` |
| 50 | `adjust/v2/FrameV2` | 2 | dual-outlet plug (`plugv2_dual_name`) | per-outlet control |
| 90 | `adjust/v4_h5160/FrameV4` | 3 | H5160 (`plug_triple`), H5161 (`plug_triple_indoor`) | per-outlet control |
| 307 | `adjust/h5089/Frame4H5089` | 2 | H5089 night-light plug | adds night-light/child-lock/total-switch |

`AdjustAc.makeFrame()`:
`goodsType==43 → FrameV1; ==90 → FrameV4; ==307 → Frame4H5089; else → FrameV2`.

Pact protocol pairs accepted (`Support.addSupportPact`, `(pactType,pactCode)`):
43 → (1,1)(1,2)(2,1)(2,2); 50 → (1,1)(1,2)(2,1); 90 → (1,1)(2,1); 307 → (1,2)(2,2).

> Newer H5083 / H5085 firmware is routed to a **different code path**:
> `pact/Model.java` jumps `H5083` to `adjust/newdetail/H5083NewDetailActivity`
> which uses the generic `com.govee.base_h71xx` SkuRepo rather than FrameV1 (see §8).
> `Support.getDefHeaderRes` returns `{0,0,0}` (no built-in header) for H5083/H5085
> under goodsType 43, consistent with that redirect.

---

## 4. Opcode map (from `ble/BleConstants.java`)

Decimal constants converted to hex (signed→`&0xFF`):

| Constant | Dec | Hex | Meaning |
|----------|----:|-----|---------|
| `SINGLE_WRITE` | 51 | 0x33 | command-type byte for writes |
| `SINGLE_READ` | -86 | 0xAA | command-type byte for reads |
| `MULTIPLE_WRITE` | -95 | 0xA1 | multi-packet write |
| `MULTIPLE_READ` | -94 | 0xA2 | multi-packet read |
| `NOTIFY` | -18 | 0xEE | device→app notify lead byte |
| `SINGLE_READ_SECRET_KEY` | -79 | 0xB1 | crypto handshake |
| `SINGLE_CHECK_SECRET_KEY` | -78 | 0xB2 | crypto handshake |
| `SINGLE_SPEC` | -77 | 0xB3 | spec read |
| `SINGLE_NEW_TIMER` | -76 | 0xB4 | legacy timer (V1) |
| `SINGLE_SYNC_TIME` | -75 | 0xB5 | sync time |
| `SINGLE_NEW_DELAY` | -80 | 0xB0 | delay on/off |
| `SINGLE_BATTERY` | 8 | 0x08 | battery read |
| `SINGLE_WIFI_STATUS` | 9 | 0x09 | wifi status read |
| `SINGLE_TEM_HUM` | 10 | 0x0A | temp/humidity read |
| `SINGLE_DEVICE_ID` | 12 | 0x0C | device id |
| `SINGLE_DEVICE_HARD_VERSION` | 13 | 0x0D | hardware version |
| `SINGLE_DEVICE_SOFT_VERSION` | 14 | 0x0E | software version |
| `SINGLE_LISTENER_PAIR` | 15 | 0x0F | pairing listener |
| `SINGLE_DATE_RESET` | 17 | 0x11 | date reset / wifi-connect notify type |
| `SINGLE_NEW_TIMER_COUNT` | 18 | 0x12 | timer count read |
| `SINGLE_NEW_TIMER_V2` | 19 | 0x13 | timer V2 (per-outlet) |
| `SINGLE_DELETE_TIMER` | 21 | 0x15 | delete timer |
| `SWITCH_OP_TYPE` | 31 | 0x1F | switch op-type / child-lock opcode (H5089) |
| `TOTAL_SWITCH_OP_TYPE` | 2 | 0x02 | H5089 master switch opcode |
| `SWITCH_OP_TYPE_4_CHILD_LOCK` | 2 | 0x02 | child-lock sub-byte |
| `SINGLE_WIFI_HARD` | 32 | 0x20 | wifi hardware version |
| `SINGLE_WIFI_SOFT` | 33 | 0x21 | wifi software version |
| `INDICATOR_LIGHT_OP_TYPE` | 22 | 0x16 | indicator light op-type |
| `LIGHT_TIMER_4_SLEEP` | 40 | 0x28 | night-light sleep (H5089) |
| `LIGHT_TIMER_4_WAKE_UP` | 41 | 0x29 | night-light wake (H5089) |
| `MULTIPLE_WIFI_SETTING` | 1 | 0x01 | multi-write wifi-setting sub-type |
| `MULTIPLE_SUC` | 0 | 0x00 | multi-write ack |

> **Note / discrepancy:** the modern init sequences (`BleOpV2`/`BleOpV4` line ~23-25)
> read versions with the *generic* `base2light` controllers, whose default opcodes
> are **soft=0x06, hard=0x07**, `WifiMac=0x14`, `WifiSoft=0x21`, `WifiHard=0x20`
> (`base2light/ble/controller/{Soft,Hard}VersionController`, `WifiMacController`).
> The `BleConstants` `0x0E`/`0x0D` device soft/hard opcodes are the older V1-firmware
> values. Treat 0x06/0x07 as the live read opcodes for current firmware and
> 0x0D/0x0E as legacy. Flagged — not resolved by reading alone.

---

## 5. Relay ON/OFF — the core command (all generations)

All generations build the switch frame from **`ble/controller/SwitchControllerV2`**
(opcode **0x01**). The IoT mirror is `iot/CmdTurn` (identical byte math) and the
scene mirror is `scenes/BleSwitchCmdBuilder` (which literally calls
`SwitchControllerV2(open, order).getValue()`).

Frame: `33 01 <value> 00…00 <bcc>` (write) / read state with `AA 01 …`.

### Value byte encoding (`SwitchControllerV2.q()`, mirrored in `CmdTurn.getCmd()`)

The single payload byte packs an **outlet-select mask in the high nibble** and the
**desired states in the low nibble**:

| Outlet arg (`f118577g`) | High-nibble mask | Low-nibble (when ON) | value ON | value OFF |
|-------------------------|------------------|----------------------|----------|-----------|
| 0 | 0x10 | bit0 = 1 | 0x11 | 0x10 |
| 1 | 0x20 | bit1 → 0x02 | 0x22 | 0x20 |
| 2 | 0x40 | bit2 → 0x04 | 0x44 | 0x40 |
| else (= "all", arg 15) | 0xF0 | 0x0F | 0xFF | 0xF0 |

So: the high nibble says *which outlets this command addresses*; the low nibble
gives their new on/off bits. "All outlets" is the `else` branch → mask `0xF0`,
value `0xFF` (all on) or `0xF0` (all off).

### Per-generation call sites

| Gen | Whole-plug toggle | Per-outlet toggle |
|-----|-------------------|-------------------|
| V1 (gt 43) | `UiV1:674` `SwitchControllerV2(!open, 15)` → 0xFF/0xF0 | n/a (single) |
| V3 sub-UI (gt 43) | `UiV3:620` `SwitchControllerV2(!open, 15)` | n/a |
| V2 (gt 50) | `UiV2:730` `(!open,15)` | `UiV2:743` `SwitchControllerV2(on, outletIdx)` |
| V4 (gt 90) | `UiV4:639` `(!open,15)` | `UiV4:651` `SwitchControllerV2(on, outletIdx)` |

### Read / heartbeat parse (`SwitchControllerV2.parseValidBytes`, `HeartControllerV2`)

Read uses the no-arg `SwitchControllerV2()` (proType 0xAA, opcode 0x01) or the
heartbeat path. The response `byte[0]` is a bitfield: **bit i (0..7) = outlet i
on/off**. `parseValidBytes` builds a `List<Boolean>` of 8 flags → `EventSwitchV2`.
`HeartControllerV2` (`base2light HeartController`, opcode **0x01**) parses the same
8-bit field and emits `EventHeartV2`. `EventSwitchV2.h()` reconciles a pending
write by applying `(f118562i >> (i+4)) & 1` (the high-nibble mask) to know which
outlets the write actually changed.

---

## 6. Timers

### 6.1 Legacy timer — opcode 0xB4 (`NewTimerController`)
Used by V1/V3/V4 (`NewTimerController(group, outletIndex, Timer)`).

- **Write** `q()`: `[ group | (outletIndex!=0 ? 0x10 : 0), enableAndType, hour, minute, repeat ]`
  - byte0 low nibble = timer group (0..n); bit4 (0x10) = outlet index flag.
- **Read** `p()`: `[ (readType==1 ? 1 : 0), 0xFF ]` — `0xFF` requests **all groups**.
- **Parse** `parseValidBytes`: if requested group == 255 (0xFF), reads **4 timers**
  back-to-back, each 4 bytes `[enableAndType, hour, minute, repeat]` starting at
  offset 1; otherwise one timer. Static helpers: `parseGroup = bytes[0] & 0x0F`,
  `parseIndex = (bytes[0] & 0x10) >> 4`, `parseTimer` (offset 1, 4 bytes).
- `Timer.enableAndType` packs enable bit + on/off type; `repeat` = weekday bitmask.

### 6.2 Timer V2 (per-outlet) — opcode 0x13 (`NewTimerControllerV2`)
Used by V1/V2/V4 multi-outlet and H5089.

- **Write** `q()`: `[ subIndex(outlet), group, enableAndSwitch, hour, min, repeat ]`
  (fields from `base_h71xx…TimerInfo`).
- **Read** `p()`: `[ subIndex(outlet), group ]`.
- **Parse** `parseOnePkgTimer(bytes)`: `byte[0]` split via `parseOneByteBy4Bit` →
  `[groupHigh, outlet]`; then 16 bytes (offset 1) = **4 timers × 4 bytes**, decoded
  by `TimerInfo.parseBytes4List(outlet*4, …)`. `parseGroup = byte0 & 0x0F`,
  `parseIndex = (byte0 & 0x10) >> 4`.

### 6.3 Timer V2 (H5089 variant) — opcode 0x13 (`h5089/Controller4H5089TimerInfo`)
- **Read** `p()`: `[ (group << 4) | outlet ]` (single packed byte).
- Same 4-timers-per-packet parse as 6.2.

### 6.4 Timer count — opcode 0x12 (`NewTimerCountController`, read-only)
- **Read** `p()`: `[ outlet/group ]`.
- **Parse**: emits `EventNewTimerCount.sendSuc(count = byte[1], group = byte[0])`.

### 6.5 Delete timer — opcode 0x15 (`TimerDeleteController`, write-only)
- **Write** `q()`: `[ outletIndex, timerGroup ]`
  (1-arg ctor sets outlet=0; 2-arg `(group, outlet)`).

---

## 7. Delay, sync-time, spec, wifi/version reads

### 7.1 Delay on/off — opcode 0xB0 (`TurnOnOffDelayController`)
- **Write** `q()`: `[ outletIndex, delayType, minutes/60, minutes%60 ]`
  (i.e. byte2 = hours, byte3 = remaining minutes of the total delay duration).
  Ctor `(outlet, type, minutes)`; `f118583g = minutes*60`.
- **Read** `p()`: `[ outletIndex, delayType ]`.
- **delayType** (from `BleOpV2:32-33`, `BleOpV4:25-26`): **0 = off/sleep delay,
  1 = on/wake delay**.
- **Parse** `parseValidBytes`: `outlet=bytes[0]`, `type=bytes[1]`,
  `minutesConfigured = bytes[2]*60 + bytes[3]`, `remaining` = signed int from
  bytes[4..6] (`BleUtil.getSignedInt(.., true)`). Static `parse2Sleep`/`parse2WakeUp`
  reuse this; when `bytes[0]==0x33` (echoed write) they recompute remaining =
  configured*60. `parseDelayType = bytes[1]`, `parseIndex = bytes[0]`.

### 7.2 Sync time — opcode 0xB5 (`SyncTimeController`, write-only)
- **Write** `q()` (7 bytes): `[ ts31..ts0 (4-byte signed BE, epoch seconds),
  0x01, hourOffset, minuteOffset ]`. Timestamp = `System.currentTimeMillis()/1000`
  via `BleUtil.getSignedBytesFor4(ts, true)`; offsets from `TimeZoneUtil`.

### 7.3 Spec read — opcode 0xB3 (`SpecController`, read-only)
- **Read**: no payload; **parse** emits `EventSpec.sendSuc(spec = byte[0])`.

### 7.4 Device / version / wifi reads (generic `base2light` controllers)
Issued in `BleOpV2`/`BleOpV4` init and `getBle().j(...)`:

| Controller | Opcode (default) | Direction | Parse |
|------------|------------------|-----------|-------|
| `SoftVersionController` | 0x06 | read | ASCII string `getStrData` |
| `HardVersionController` | 0x07 | read | ASCII string |
| `WifiSoftVersionController` | 0x21 | read | ASCII string |
| `WifiHardVersionController` | 0x20 | read | ASCII string |
| `WifiMacController` | 0x14 | read | MAC bytes → address |

(See §4 note re: 0x06/0x07 vs `BleConstants` 0x0E/0x0D.) Battery 0x08, wifi-status
0x09, temp/hum 0x0A, device-id 0x0C are declared in `BleConstants` but are not
wired by the V2/V4 controllers in this module (likely advert/legacy-firmware reads).

---

## 8. H5083 / H5085 "newdetail" path (generic base_h71xx)

Source: `adjust/newdetail/H5083NewDetailRepository.java:302-315`.

`necessaryMessages()` sends, on connect:
- `base_h71xx…SyncTimeController` + `base2light…SwitchController` (opcode **0x01**,
  value = single on/off byte `{open}` — *not* the nibble-mask form; single outlet).
- `H()` opcode with `{0,0}` then `{0,1}` (read two delay/timer groups — `H()` is a
  device-configured opcode from `BleProtocolConstants`).
- If `supportLockAndLightIndicator` (H5083 fw≥10003 & wifi≥40100):
  `D()` opcode `{2}` (child-lock query) + single-read `J0()`.
- If `isOldH5080` (sku H5080 & soft ver ≤ 10008): legacy timer read
  `0xB4` with `{0, 0xFF}` (all groups, see 6.1).
- else single-read `j1()`.

The exact byte values of `H()/D()/J0()/j1()` are **dynamic** (set per-SKU via the
server-driven `BleProtocolConstants` table), so they cannot be pinned from static
constants. Flagged.

---

## 9. H5089 night-light plug extras

Source: `ble/controller/h5089/*`, `adjust/h5089/*`. Opcodes use `0x33`/`0xAA`.

| Function | Opcode | Write payload `q()` | Read payload `p()` / parse |
|----------|--------|---------------------|----------------------------|
| Master / total switch (`Controller4TotalSwitch`) | **0x02** | `[ on?1:0 ]` (empty if null) | parse → `Event4TotalSwitch` |
| Child lock (`Controller4ChildLock`) | **0x1F** | `[ 0x02, on?1:0 ]` | read `p()=[0x02]`; parse `validBytes[1]==1` |
| Night-light switch (`Controller4NlSwitch`) | `b0()` (dynamic) | `[ h(), m(), on?1:0 ]` | read `p()=[h()]`; parse `[1]`=on, `[2]`=mode |
| Night-light sleep (`Controller4NlSleep`) | **0x28** | `[hour,min,closeTime,curTime,defLight, bri(3B signed), rgbWord(2B)]` (10B) | `EventSleep` (V2) |
| Night-light wake (`Controller4NlWakeUp`) | **0x29** | 12-byte: `[hour,min,…,bri(3B),rgb(2B)]` | `EventWakeUp` (V2) |

`Controller4NlSleep` decode (`parseValidBytes`): bytes → start-bri, close/cur time,
RGB = `Color.rgb(b5,b6,b7)`. `Controller4NlWakeUp` decode: RGB = `Color.rgb(b7,b8,b9)`.
The `h()`/`m()`/`b0()` values come from the per-SKU `BleProtocolConstants` table
(dynamic) — flagged.

H5089 read-back of night-light state is handled by `h5089/Notify4NightLight`
(an `AbsNotifyParse`, lead byte `0xEE`).

---

## 10. Notify parsing

| Parser | Notify type byte | Payload | Meaning |
|--------|------------------|---------|---------|
| `ble/WifiNotifyParse` | `c()` = 0x11 | `byte[0]==0` ⇒ connected | `EventNotifyWifiConnect.sendEventWifiConnect(byte0==0)` |
| `h5089/Notify4NightLight` | (h5089 NL) | night-light state | updates NL UI |

All notify frames are `0xEE`-led; the matcher in `AbsController.bleMsg` requires
`bArr[0]/bArr[1]` to equal the controller's `proType`/`commandType`
(`isSameController`).

---

## 11. Multi-packet usage

The plug module declares the standard multi opcodes (`0xA1` write / `0xA2` read,
`MULTIPLE_WIFI_SETTING=0x01`, `MULTIPLE_SUC=0x00`) via `BleMultiComm`, used for
the Wi-Fi provisioning blob during pairing (`add/*`). All of the relay/timer/delay
control commands above are **single 20-byte frames** — including the "read all 4
timers" responses, which pack 4 timers into one frame rather than multi-packeting.

---

## 12. IoT / cloud mirror

`iot/CmdTurn(boolean,int)` reproduces the exact §5 nibble-mask math and is sent as
the `"turn"` command. `iot/CmdPtReal` wraps any `AbsSingleController` so its 20-byte
BLE frame is forwarded verbatim through the cloud (`writeCmd(new CmdPtReal(controller))`
appears throughout `UiV1/UiV2/UiV3/UiV4`). Net effect: **the BLE byte layouts in
this section are also the canonical IoT passthrough payloads.**
