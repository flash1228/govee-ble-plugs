# Plug H5089 / H5085 — night-light + multi-outlet control

`section_id: plug-h5089`

This SKU family (H5089, related H5085) is a **multi-outlet smart plug with an integrated
RGB night-light**. It is built on the **H5080 BLE frame stack** (`com.govee.h5080.*`) and
reuses the standard 20-byte single-command frame plus the H5080 timer/delay controllers. On
top of that base it adds:

- a **total (master) switch** that drives all outlets at once,
- per-outlet switches (outlets indexed 0/1) via the shared H5080 `SwitchControllerV2`,
- **child lock**,
- a full **night-light sub-protocol** (on/off, brightness, color, color-temp, scene, DIY)
  layered through the shared `base_h71xx` "light71xx" mode protocol,
- night-light **sleep** and **wake-up** schedules (RGB/color-temp aware variants of the
  base sleep/wake controllers),
- H5089 timer enumeration/read (`Controller4H5089TimerInfo`),
- Matter onboarding hints (`H5085MatterHelper`).

## Frame format recap (how this layers on H5080)

All single commands are the canonical Govee 20-byte frame:

| offset | meaning |
|--------|---------|
| `[0]`  | proType: `0x33` write / `0xAA` read (default `AbsSingleController.getProType()`); the night-light **light-mode** controller overrides this — see note below |
| `[1]`  | commandType = the per-feature **opcode** (the value returned by each controller's `getCommandType()`) |
| `[2..18]` | payload from `p()` (read request) or `q()` (write), zero-padded |
| `[19]` | BCC = XOR of bytes `[0..18]` |

Confirmation that `[1]` is the opcode and `[0]` is `0x33/0xAA`: `CmdStatus4H5089.Companion.a()`
dispatches on `bArr[1]` against the controller `getCommandType()` values (18, 19, 31, 40, 41,
`0xB0`, 27, 22), and re-emits events with proType byte `(byte)51 = 0x33` for connection results
and `(byte)-18 = 0xEE` for notify-origin results.
Source: `com/govee/h5080/adjust/h5089/CmdStatus4H5089.java`.

NOTIFY frames arrive prefixed `0xEE` and are parsed by `Notify4NightLight` (opcode `0x1B`).

> **proType override for night-light mode:** `LightRgbController.getProType()` returns
> `BleProtocolConstants.v1()` on write (default **`0x3A` = 58**) and `O0()` on read (default
> **`0xAA` = -86**) instead of the usual `0x33/0xAA`. These come from runtime-configurable
> `BleProtocolConstants` fields, so a per-SKU init may reset them; treat `0x3A`(write)/`0xAA`(read)
> as the decompiled default and verify on-wire. Source:
> `com/govee/base_h71xx/light71xx/controller/LightRgbController.java:getProType`.

## Opcode map (byte `[1]`)

| Feature | opcode `[1]` (hex / dec) | cmd-type `[0]` | controller / source |
|---------|--------------------------|----------------|---------------------|
| Total (master) switch | `0x02` / 2 | `0x33`/`0xAA` | `Controller4TotalSwitch` |
| Per-outlet switch (idx 0/1) | shared H5080 `SwitchControllerV2` | `0x33`/`0xAA` | invoked in `BleOp4H5089.onEventSwitchV2` |
| Child lock | `0x1F` / 31 | `0x33`/`0xAA` | `Controller4ChildLock` |
| Night-light switch / brightness | `0x1B` / 27 (= `BleProtocolConstants.b0()`) | `0x33`/`0xAA` | `Controller4NlSwitch` |
| Night-light mode (color/scene/diy/default) | `0x1B` / 27 (= `b0()`) | `0x3A` wr / `0xAA` rd (see note) | `LightRgbController` (base_h71xx) |
| Night-light DIY upload (multi) | comType `0x04` inside `0xA3` multi-write-V1 | `0xA3` | `DiyMultipleControl` |
| Night-light notify | `0x1B` / 27 | `0xEE` | `Notify4NightLight` |
| Night-light sleep schedule | `0x28` / 40 | `0x33`/`0xAA` | `Controller4NlSleep` |
| Night-light wake-up schedule | `0x29` / 41 | `0x33`/`0xAA` | `Controller4NlWakeUp` |
| Timer count (per index) | `0x12` / 18 | `0x33`/`0xAA` | H5080 `NewTimerCountController` |
| Timer info (read, 4 groups/pkt) | `0x13` / 19 | `0xAA` | `Controller4H5089TimerInfo` |
| Turn-on/off delay | `0xB0` / -80 (176) | `0x33`/`0xAA` | H5080 `TurnOnOffDelayController` |
| Indicator/"do not disturb" light | `0x16` / 22 | `0x33`/`0xAA` | base_h71xx `NotDisturbController` |
| Sync time / versions / wifi-mac | (H5080 shared) | — | see `BleOp4H5089.V()` |

`BleProtocolConstants` resolved defaults (configurable static fields in
`com/govee/base_h71xx/sku_base/BleProtocolConstants.java`):
`b0()=27 (0x1B)`, `h()=1`, `i()=2`, `m()=1`, `g()=5`,
`j()=13 (0x0D)`, `n()=19 (0x13)`, `l()=10 (0x0A)`, `k()=252 (0xFC)`,
`v1()=58 (0x3A)`, `O0()=-86 (0xAA)`.

---

## Total (master) switch — opcode `0x02`

`Controller4TotalSwitch` (`com/govee/h5080/ble/controller/h5089/Controller4TotalSwitch.java`).

- `getCommandType()` = `2`.
- Write payload `q()` = `{ on ? 0x01 : 0x00 }` (single byte).
- Read/notify is not parsed here (`parseValidBytes` returns `true` unconditionally); state
  comes back via the heartbeat (`EventHeartV2`) and the per-outlet switch path.
- Write frame: `33 02 <on> 00..00 <BCC>`.

When a total-switch result arrives (`BleOp4H5089.onEvent4TotalSwitch`), the app sets BOTH
outlet `ExtV1.open` flags (`this.E.open`, `this.F.open`) to the same value, persists them in
`DeviceSwitchConfig` keyed `sku_device`, `sku_device_0`, `sku_device_1`, and — if turning ON —
re-applies the current night-light mode. So `0x02` is "all outlets together".

## Per-outlet switch (shared H5080 `SwitchControllerV2`)

Not in the h5089 package but driven from it. `BleOp4H5089.onEventSwitchV2` handles
`EventSwitchV2`: field `f118562i` is the outlet index (0 ⇒ `ExtV1 E`, 1 ⇒ `ExtV1 F`),
`f118560g` is the boolean state, and on a non-write (read) result `f118561h` is a
`List<Boolean>` of the two outlet states, with `info.open = list[0] | list[1]`.
Outlet count = `Support.getPlugNum(goodsType)` (`BleOp4H5089` field `H`).

## Child lock — opcode `0x1F` (31)

`Controller4ChildLock` (`…/h5089/Controller4ChildLock.java`).

- `getCommandType()` = `31` (`0x1F`).
- Read request payload `p()` = `{ 0x02 }`.
- Write payload `q()` = `{ 0x02, on ? 0x01 : 0x00 }`.
- Parse (`parseValidBytes`): require `validBytes[0] == 0x02`; locked = `validBytes[1] == 1`.
- Write frame: `33 1F 02 <on> … <BCC>`; read frame: `AA 1F 02 … <BCC>`.

`0x02` is a sub-selector inside the child-lock opcode. `CmdStatus4H5089` mirrors this: for
`bArr[1]==31`, valid `[0]==2` ⇒ `Event4ChildLock.b(..., locked = [1]==1)`.
Result surfaces in `H5089OpManager.onEvent4SwitchChildLock` → LiveData `L()`.

---

## Night-light sub-protocol (opcode `0x1B` = 27)

Everything that paints the night-light shares opcode `[1] = 0x1B` (`b0()`). The first payload
byte (`[2]`) is a **sub-opcode** that selects the function:

| sub-opcode `[2]` | value | function |
|------------------|-------|----------|
| `h()` | `0x01` | night-light on/off + brightness state |
| `g()` | `0x05` | light **mode** (color / color-temp / scene / diy / default) |

### Night-light on/off & brightness — sub-opcode `0x01`

`Controller4NlSwitch` (`…/h5089/Controller4NlSwitch.java`). Note the **write payload differs
from the read/notify payload**:

- Read request `p()` = `{ h()=0x01 }`.
- Write switch (`Controller4NlSwitch(boolean)`):
  `q()` = `{ h()=0x01, m()=0x01, on ? 1 : 0 }` → frame `33 1B 01 01 <on> …`
- Write brightness (`Controller4NlSwitch(int)`):
  `q()` = `{ h()=0x01, i()=0x02, <brightness 0..100> }` → frame `33 1B 01 02 <bri> …`
  (brightness is `Byte.parseByte(intString)`, base-10, i.e. raw 0–100.)
- Parse / notify (`parseValidBytes`, and `Notify4NightLight.e`): require `validBytes[0]==h()(1)`,
  then `on = validBytes[1]==1`, `brightness = validBytes[2]` (signed byte).
  So on the **return** path byte layout is `[01, on, brightness]`, whereas the **write** path
  inserts the `m()`/`i()` field-selector at `[1]`. Implementers must build writes with the
  selector and parse reads without it.

Result → `Event4NlSwitch` → `H5089OpManager.onEvent4SwitchNightLight` → LiveData `S()`
(`Pair<Pair<on,brightness>, isWrite>`).

### Night-light mode — sub-opcode `0x05`

`LightRgbController` (base_h71xx) carries a `LightModeInfo`. Opcode `[1]=b0()=0x1B`, proType
`[0]=0x3A` write / `0xAA` read (override noted above). Payload built by
`LightModeInfo.Companion.a()` (`com/govee/base_h71xx/light71xx/model/LightModeInfo.java`):

```
[ subCmd(=LightSubCmd.a()=g()=0x05),
  (optional deviceState byte, only if LightModeInfo.deviceState != null),
  subModeByte,
  ...modeData ]
```

`LightSubCmd` static init binds `a() = g() = 0x05` (mode) and `b() = h() = 0x01` (switch),
so the night-light mode sub-opcode `[2]` is `0x05`. Source:
`com/govee/base_h71xx/light71xx/model/LightSubCmd.java`.

**Sub-mode byte** (`LightSubMode.getByteValue()`):

| sub-mode | byte | const |
|----------|------|-------|
| COLOR   | `0x0D` (13)  | `j()` |
| SCENE   | `0x13` (19)  | `n()` |
| DIY     | `0x0A` (10)  | `l()` |
| DEFAULT | `0xFC` (252) | `k()` |

**Mode data** (`ModeColor` / `ModeScene` / `ModeDiy`):

- **COLOR** (`ModeColor.d()`): `getSignedBytesFor3(colorRgb)` ⇒ 3 bytes **R,G,B**, then
  `getSignedBytesFor2(kelvin)` ⇒ 2 bytes **kelvin** (big-endian, 0 when pure RGB).
  Full write frame: `3A 1B 05 0D <R> <G> <B> <Kh> <Kl> … <BCC>`.
  Parse (`ModeColor.Companion.a`, base index `i+1` after sub-mode byte): rgb =
  `getSignedInt({0xFF, b0, b1, b2})`, kelvin = `getSignedInt({b3, b4})`.
- **SCENE** (`ModeScene.c()`): 2 bytes `{ 0x00, sceneValue }`. Frame:
  `3A 1B 05 13 00 <scene> … <BCC>`. Parse reads scene at `i+1+1` (`Companion.a` reads
  `validBytes[i+1]`). Scene id default = 1.
- **DIY** (`ModeDiy.f96834e.b()`): a static DIY-reference byte block (the actual DIY frame
  bytes are uploaded separately via the multi-packet path below). Frame: `3A 1B 05 0A <diyRef…>`.
- **DEFAULT**: empty data ⇒ `3A 1B 05 FC … <BCC>`.

Color-temperature changes go through the same COLOR path: `H5089OpManager.D(kelvin)` builds a
`ModeColor(existingRgb, kelvin)` and writes it (`changeLightColorTem`). `changeLightRgb`
(`E()`) builds `ModeColor(rgb)` with optional deviceState byte.

Mode dispatch in `H5089OpManager.F()` (`changeMode`): COLOR/SCENE/DIY load last-used params
from `LightRgbRepository` and emit a `LightRgbController`. Notify/read of mode →
`LightModeEvent` → `H5089OpManager.onEvent4NightLightModel` (decompile elided but it updates
LiveData `Q()` of type `LightModeInfo`).

### Night-light DIY upload — multi-packet (`0xA3` MULTIPLE_WRITE_V1)

`DiyMultipleControl` (`com/govee/base_h71xx/light71xx/controller/DiyMultipleControl.java`)
extends `AbsMultipleControllerV1`, so it is fragmented via the V1 multi-write opcode
(`0xA3`). Inner `getCommandType()` = `4` (the comType carried in the multi frame, byte `[1]`).
Payload = `ModeDiy.h()` (the DIY pixel/segment program). `H5089OpManager.B(...)` assembles a
`ModeDiy(diyCode, speed, data)` and calls `H()` →
`BleOp4H5089.executeMultiOpV1(diyMultipleControl)` (BLE) or `IotOp4H5089` (IoT, wrapped in
`CmdMultiSync` with a trailing `LightRgbController` DIY-mode frame). After upload completes
(`EventMultipleDiy`), the app re-issues `changeMode(DIY)` to activate it.
Source: `H5089OpManager.I()` / `H5089OpManager.B()` / `H5089OpManager.H()`.

---

## Night-light sleep schedule — opcode `0x28` (40)

`Controller4NlSleep` (`…/h5089/Controller4NlSleep.java`) extends the base `SleepController` and
adds RGB / color-temp. `getCommandType()` = `40`.

Write payload `q()` (after opcode):

```
[ enable,            // [0]  base SleepController f57637f
  startBri,          // [1]  f57638g
  closeTime,         // [2]  f57639h (minutes, ≤240)
  curTime,           // [3]  f57640i (minutes, ≤240)
  defaultLight,      // [4]  f118591k (the "wakeMin"/default-light slot)
  rgb0, rgb1, rgb2,  // [5..7] getSignedBytesFor3(colorParam) — R,G,B
  ct0, ct1 ]         // [8..9] getSignedBytesFor2(kelvin) when Constant.isColorTemp(colorParam), else {0,0}
```

`f118590j` is the chosen color/color-temp value; if `Constant.isColorTemp(f118590j)` the last
two bytes carry `getColorTemKelvin(...)`.

Parse (`parseValidBytes` / `Companion.a`):
`enable=[0]`, `startBri=u8[1] (≤100)`, `closeTime=u8[2] (≤240)`, `curTime=u8[3] (≤240)`,
`defaultLight=u8[4]`, `rgb = Color.rgb(u8[5],u8[6],u8[7])`.
Maps to `base2light` `SleepInfo`. CmdStatus dispatches `bArr[1]==40` → `Controller4NlSleep.Companion.a`.
Result surfaces via `BleOp4H5089.onEvent4NlSleep` (`EventSleep`) into `ExtV1.sleepInfo` (the
night-light ext `G`) and `SleepSucEvent`.

## Night-light wake-up schedule — opcode `0x29` (41)

`Controller4NlWakeUp` (`…/h5089/Controller4NlWakeUp.java`) extends base `WakeUpController`.
`getCommandType()` = `41`.

Write payload `q()`:

```
[ enable,            // [0]  f57694f
  endBri,            // [1]  f57695g
  wakeHour,          // [2]  f57696h (0..23)
  wakeMin,           // [3]  f57697i (0..59)
  repeat,            // [4]  f57698j (bitmask of weekdays)
  wakeTime,          // [5]  f57699k (fade-in minutes)
  defaultLight,      // [6]  f118595l
  rgb0, rgb1, rgb2,  // [7..9] getSignedBytesFor3(colorParam)
  ct0, ct1 ]         // [10..11] getSignedBytesFor2(kelvin) when color-temp, else {0,0}
```

`f118596m` is the chosen color/color-temp value.

Parse (`parseValidBytes` / `Companion.c`):
`enable=[0]`, `endBri=u8[1]`, `wakeHour=clamp(u8[2],0..23)`, `wakeMin=clamp(u8[3],0..59)`,
`repeat=[4]`, `wakeTime=u8[5]`, `defaultLight=u8[6]`, `rgb = Color.rgb(u8[7],u8[8],u8[9])`.
Maps to `base2light` `WakeUpInfo`. CmdStatus dispatches `bArr[1]==41` →
`Controller4NlWakeUp.Companion.c`. Result via `BleOp4H5089.onEvent4NlWakeUp` (`EventWakeUp`)
into ext `G.wakeUpInfo` and `WakeupSucEvent`.

> Both sleep and wake-up controllers are also queued at connect-time in `BleOp4H5089.V()`
> (read pass) so the app pre-loads the night-light schedules.

---

## H5089 timer enumeration — opcodes `0x12` (count) / `0x13` (info)

The plug exposes **three timer scopes**, indexed 0, 1, 2: outlet-0, outlet-1, and the
**night-light** (index 2). `BleOp4H5089.V()`/`Y()` build, per outlet index `i`:
`NewTimerCountController(i)`, `TurnOnOffDelayController(i,0)`, `TurnOnOffDelayController(i,1)`,
and additionally `Controller4NlWakeUp`, `Controller4NlSleep`, and `NewTimerCountController(2)`
for the night-light scope.

`Controller4H5089TimerInfo` (`…/h5089/Controller4H5089TimerInfo.java`):

- `getCommandType()` = `19` (`0x13`).
- Read request payload `p()` = `{ (group<<4) | index }` — high nibble = packet/group number,
  low nibble = the timer scope index (0/1/2).
- Parse `parseOnePkgTimer(bArr)`: `parseOneByteBy4Bit(bArr[0])` splits the first byte into
  `[index, group]` nibbles; then 16 payload bytes are sliced into **four 4-byte timer records**
  decoded by `TimerInfo.parseBytes4List(group*4, …)` — i.e. 4 timer groups per 20-byte packet.

`NewTimerCountController` (opcode `0x12`/18) returns the count; `CmdStatus4H5089.Companion.c`
decodes `bArr[1]==18` as `[index, count]` and pre-sizes the timer list. `bArr[1]==19` →
`Companion.d` decodes one packet of timers. Index→ext mapping: 0⇒outlet0 (`b()`),
1⇒outlet1 (`c()`), else night-light (`a()`).

The flow: `onNewTimerCountController` (in `BleOp4H5089`) receives the count, allocates the list,
then issues `ceil(count/4)` `Controller4H5089TimerInfo(packet,index)` reads; for the
night-light scope (index 2) it also issues a `SwitchControllerV2` read. Night-light timer
results route to `NightLightUi`/`TimerResultEvent`.

`TurnOnOffDelayController` (opcode `0xB0`/-80) carries on/off **delay** info; `CmdStatus4H5089.b`
parses index + delay-type (0=sleep, 1=wake) and fills `ExtV1.sleepInfo`/`wakeUpInfo`.

---

## IoT / cloud JSON state mirror

`CmdStatus4H5089.Companion.a(json)` parses the cloud "state" + "op" mirror used when BLE is
unavailable (`IotOp4H5089`). `state.onOff` is a **bitmask of the two outlets**:
`outlet0 = (onOff & 1) != 0`, `outlet1 = (onOff & 2) != 0`. `state` also carries `brightness`
and `mode`. The `op.ptBytes` array is a list of raw 20-byte BLE frames, each dispatched by
`bArr[1]` exactly like the BLE notify path (18,19,40,41,`0xB0`,31,`b0()`=27,22).
Source: `com/govee/h5080/adjust/h5089/CmdStatus4H5089.java`, `IotOp4H5089.java`.

## Connect-time read burst

`H5089OpManager.C(true)` (on BLE connect) issues:
`SyncTimeController`, `NewTimerCountController(currentIndex)`, `Controller4ChildLock` (read),
`Controller4NlSwitch` (read), `LightRgbController(null)` (read mode), `NotDisturbController` (read).
This is the canonical "refresh everything" set. Source: `H5089OpManager.java:C`.

---

## Matter onboarding (`H5085MatterHelper`)

`com/govee/h5080/H5085MatterHelper.java` registers a `MatterInterceptor` during add-device:

- Applies to `goodsType == 43` or `goodsType == 307`.
- For goodsType 43 + sku `"H5085"`: Matter is offered only when BLE soft+hard versions are
  `>= WlanSupportVersion (3.01.00 floor)` **and** the exact strings `"3.01.00"` match the wifi
  soft/hard versions (`compareTo` gates on `WlanSupportVersion.f90971g`).
- For `Support.f118641c` sku (an H5080-family sku constant) or any goodsType 307: returns
  `true` (Matter eligible) unconditionally.

This only governs whether the Matter pairing path is shown; the BLE control protocol above is
unchanged. No Matter cluster/TLV detail is present in this class — it is purely an eligibility
gate.

---

## Uncertainties / flags

- **proType byte for night-light mode**: decompiled default `v1()=0x3A` (write) / `O0()=0xAA`
  (read). `BleProtocolConstants` is mutable (has setters), so a per-SKU initializer could
  override these to the usual `0x33/0xAA`. Verify on-wire before trusting `0x3A`.
- **All `BleProtocolConstants` opcode/sub values** (`b0/h/i/m/g/j/n/l/k`) are read from static
  defaults; confirm they aren't reconfigured for this SKU at runtime.
- `ModeDiy.f96834e.b()` static DIY-reference bytes were not expanded here (out of assigned
  scope — base_h71xx light model); the DIY pixel program is uploaded via the `0xA3` multi path.
- The night-light mode read/notify parser (`H5089OpManager.onEvent4NightLightModel`) was a
  jadx "method not decompiled" stub; its LiveData wiring is inferred from `Notify4NightLight`
  and `LightModeEvent`.
- Per-outlet `SwitchControllerV2` opcode byte was not read in this scope (lives in the shared
  H5080 package); only its event handling in `BleOp4H5089` was confirmed.
