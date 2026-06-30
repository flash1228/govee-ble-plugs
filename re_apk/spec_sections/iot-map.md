# BLE ⇆ IoT/Cloud Command Cross-Reference (plugs: H5080 / H5083 / H5086 / H5089)

This section maps the **same** on/off / timer / delay / status commands across two transports:

1. **BLE** — the 20-byte framed protocol (`0x33` write / `0xAA` read, `byte[1]` = opcode, `byte[19]` = XOR BCC).
2. **Cloud IoT (MQTT/AWS)** — JSON messages with a `cmd` string and a typed `data` payload.

The decisive finding: the cloud **`ptReal`** (passthrough-real) command transports the *exact same 20-byte BLE frames*, each Base64-encoded (`android.util.Base64`, flag `2` = `NO_WRAP`). So every BLE opcode reverse-engineered elsewhere is directly reusable over the cloud by Base64-wrapping it into a `ptReal` `command[]` array. The cloud also offers a few *native* (non-passthrough) commands (`turn`, `status`) whose byte encoding mirrors the corresponding BLE controller's payload byte-for-byte — these provide an independent cross-check on the BLE frame bytes.

---

## 1. Cloud message envelope

### Write (app → device), `AbsCmdWrite`
Source: `com/govee/base2home/iot/AbsCmdWrite.java`, `com/govee/base2home/iot/Write.java`

The published JSON is `{"msg": <AbsCmdWrite>}` serialized with `JsonUtil.toJsonWithDisableHtmlEscaping`:

```jsonc
{
  "msg": {
    "transaction": "<uuid/seq>",        // matched back in the V2 reply
    "accountTopic": "<account MQTT topic>",
    "data": { /* the AbsCmd subclass, serialized inline */ },
    "type": 1,                          // 1 = write, 0 = read  (AbsCmdWrite.type default = 1)
    "cmd": "<data.getCmd()>",           // e.g. "turn" / "ptReal" / "status"
    "cmdVersion": <data.getCmdVersion()> // usually 0
  }
}
```

`AbsCmdWrite(transaction, accountTopic, data)` copies `cmd = data.getCmd()` and `cmdVersion = data.getCmdVersion()` from the `AbsCmd`. The `data` object is whatever the per-feature `AbsCmd` subclass serializes to (see §2). `Write.getWriteMsg4Transaction(...)` auto-fills transaction (`IotTransactions.h(suffix)`) and account topic (`Iot.t()`).

### Read request
A status read is the same envelope with `type = 0` and `cmd = "status"`, `data = {}` (empty `CmdStatus`). Source: `com/govee/h5080/adjust/v1/IotOpV1.java` (`n()` returns `"status"`, `o()` returns `new CmdStatus()`).

### Reply (device → app)
Replies arrive as `IotMsgV2` events (`com/govee/base2home/iot/protype/v2/IotMsgV2.java`, dispatched via `IotMsgEventV2.sendIotMsgEventV2`). `IotMsgV2` carries `cmd`, `type` (`isRead()` = `type==0`), `transaction`, `sku`, `device`, `pactType`, `pactCode`, `proType`. The actual state lives in sibling JSON keys `state` / `op` / `online` of the raw reply string (see §3). The key to read for a given reply `cmd` is chosen by `Cmd.getCmdReadParseKey`:

| reply `cmd` | JSON key parsed | source |
|---|---|---|
| `pt`, `ptReal` | `op` | `base2home/iot/Cmd.java#getCmdReadParseKey`, `h5080/iot/Cmd.java#getCmdReadParseKey` |
| anything else (`status`, `turn`, …) | `state` | same |

### Protocol versions
`IotMsgProType` (used by scene builders, e.g. `IotSwitchCmdBuilderV1` returns `V2`): the plug switch scene command publishes as proType **V2**. Envelope variants: `IotMsg` (v0: flat `cmd/data/transaction/type/cmdVersion`), `IotMsgV1`, `IotMsgV2` (adds `pactType/pactCode/proType/sku/device/softVersion`).

### Cloud `cmd` string constants
Source: `com/govee/base2home/iot/Cmd.java`

`state`, `op`, `online`, `turn`, `brightness`, `status`, `color`, `colorTem`, **`pt`**, `mode`, `colorwc`, **`ptReal`**, **`multiSync`**, `ptUrl`.
H5080-scoped subset (`com/govee/h5080/iot/Cmd.java`): `state`, `op`, `online`, `turn`, `brightness`, `status`, `colorwc`, **`ptReal`**, **`ptIot`**.

---

## 2. Native cloud commands (typed `data`)

### `turn` — native on/off (`CmdTurn`)
Source: `com/govee/h5080/iot/CmdTurn.java`. Serializes to `data = {"val": <byte>}`.

`CmdTurn(boolean on, int order)` computes one byte from the socket **order** (0-based index of the socket on a multi-outlet plug) and the on/off boolean:

| `order` | base nibble (`i7`) | on-bit value (`r42` when on) | source line |
|---|---|---|---|
| 0 | `0x10` | `0x01` | CmdTurn.getCmd |
| 1 | `0x20` | `0x02` | |
| 2 | `0x40` | `0x04` | |
| else | `0xF0` | `0x0F` | |

`val = (byte)(onBit | base)`. Example: socket 0 ON = `0x11` (17); socket 0 OFF = `0x10` (16); socket 1 ON = `0x22`; "all" ON = `0xFF`.

**Cross-check vs BLE:** `com/govee/h5080/ble/controller/SwitchControllerV2.java` has `getCommandType() = 0x01` (BLE switch opcode) and payload method `q()` that builds `new byte[]{(byte)(r0 | i6)}` with the *identical* 16/32/64/-16 base + on-bit logic. So the cloud `turn.val` byte equals the BLE `0x33 0x01` frame's `byte[2]` payload byte. This confirms the BLE switch frame: `33 01 <val> 00…00 <bcc>`.

### `status` — native state read (`CmdStatus`)
Source: `com/govee/h5080/iot/CmdStatus.java`. `getCmd()` = `"status"`, empty `data`. Triggers a `state`+`op` reply (§3).

### `ptReal` — passthrough of raw BLE frames (`CmdPtReal`) ★ key
Source: `com/govee/h5080/iot/CmdPtReal.java` (and the richer light variant `com/govee/base2light/pact/iot/CmdPtReal.java`). Serializes to `data = {"command": ["<base64>", ...]}`.

Construction (h5080):
```java
new CmdPtReal(AbsSingleController c):  command.add( Encode.encryptByBase64( c.getValue() ) );      // single 20-byte frame
new CmdPtReal(List<byte[]> frames):    for each f: command.add( Encode.encryptByBase64(f) );        // multi-frame
```
`Encode.encryptByBase64(byte[])` = `Base64.encodeToString(bytes, 2)` → standard Base64, **NO_WRAP** (no newlines). `AbsSingleController.getValue()` returns the fully-built 20-byte BLE frame **including the XOR checksum byte[19]**. Therefore:

> **cloud `ptReal.command[i]` = Base64( exact 20-byte BLE frame, with BCC )**

Decode helper `getOpCommandByte()` Base64-decodes the last command, asserts `length == 20`, and returns `bytes[1]` (the opcode) — proving the cloud array elements are full BLE frames whose opcode is at offset 1. `getOpCommandBytes()` returns the whole 20-byte frame.

This means **any BLE opcode** (switch `0x01`, delay `0xB0`, timer `0xB4/0x12/0x13`, spec `0xB3`, sync-time, etc.) can be issued over the cloud by Base64-wrapping its 20-byte frame into `ptReal`.

The base2light `CmdPtReal` adds `opVersion` tags (DEF=0, DIY=1, SCENE=2, MUSIC=3, COLOR_MODE=4) and multi-packet helpers (`MultipleBleBytes.getMultipleWriteBytesV1/V2`) — for plugs only the DEF (single-frame / simple multi-frame) path is used.

---

## 3. Status reply parsing (`state` + `op`)

The plug status reply JSON contains:
- `state` → `{ "onOff": <int bitmask>, "brightness": <int>, "mode": <int> }` (only `onOff` is meaningful for plugs; `brightness`/`mode` are inherited template fields).
- `op`  → `{ "command": ["<base64 20-byte frame>", ...] }` (a `ResultPt`; same wire format as `ptReal`).
- `online` → presence flag.

### `state.onOff` decoding (per-socket bitmask)
| variant | source | decode |
|---|---|---|
| V0 | `CmdStatusV0.parseJson` | `socket0_on = (onOff & 1) != 0`; `socket1_on = (onOff & 2) != 0`; overall = `(onOff & 1) > 0` |
| V3 | `CmdStatusV3.parseJson` | same as V0 |
| V4 | `CmdStatusV4.parseJson` | loops `list` of `ExtV3`: `extV3[i].on = (onOff & (1<<i)) != 0` for each socket i; overall = OR of all |

### `op.command[]` (`ResultPt`) parsing — dispatch on BLE opcode `bArr[1]`
Source: `com/govee/h5080/iot/ResultPt.java` (`getPtBytes()` Base64-decodes each into a `byte[]`), then `CmdStatusV0/V3/V4.parseJson` switch on `bArr[1]` (each frame asserted `length == 20`):

| `bArr[1]` (signed) | hex opcode | meaning | parser | present in |
|---|---|---|---|---|
| `-80` | **0xB0** | turn-on/off **delay** (sleep/wake) | `parsePtDelay` → `TurnOnOffDelayController.parseIndex/parseDelayType/parse2Sleep/parse2WakeUp` | V0, V3, V4 |
| `-76` | **0xB4** | **timer** (4× Timer structs) | `parsePtTimer` (legacy 4-byte Timer blocks) | V0 only |
| `18` | **0x12** | timer **count** | `parsePtTimerCount` (`bArr[0]`=index, `bArr[1]`=count) | V0, V3, V4 |
| `19` | **0x13** | **timer V2** | `parsePtTimer` → `NewTimerControllerV2.parseOnePkgTimer` | V0(`parsePtTimerV2`), V3, V4 |

Notes on the delay frame (`TurnOnOffDelayController`): BLE `getCommandType() = 0xB0`; write payload `q()` = `{index, delayType, min/60, min%60}` (HH,MM split), read parses a 3-byte signed-int duration. `parseIndex(bArr)`/`parseDelayType(bArr)` extract socket index and sleep(0)/wake(1) type from the returned frame.

Timer V2 frames use 4-bit packing: `BleUtil.parseOneByteBy4Bit(validBleBytes[0])[0]` = socket index; `NewTimerControllerV2.parseOnePkgTimer` yields `TimerInfo` objects tagged with `group`. `parseValidBleBytes(bArr)` strips frame type/opcode/BCC to the payload.

---

## 4. BLE opcode ⇄ cloud cross-reference table (plugs)

All BLE frames are 20 bytes: `[type][opcode][payload…][bcc]`. "Cloud form" = how the same action travels over IoT.

| Action | BLE type | BLE opcode | BLE source | Cloud form | Cloud source |
|---|---|---|---|---|---|
| Main switch (per socket) | `0x33` write / `0xAA` read | **0x01** | `SwitchControllerV2.getCommandType()` (=1), `q()` payload | native `turn` `{val}` **or** `ptReal` Base64(frame) | `h5080/iot/CmdTurn.java`, `CmdPtReal.java` |
| Turn-on/off delay (sleep/wake) | `0x33`/`0xAA` | **0xB0** | `TurnOnOffDelayController.getCommandType()` (=-80) | `ptReal`; reply parsed in `op` | `CmdStatusV0/V3/V4.parsePtDelay` |
| Timer (legacy) | `0x33`/`0xAA` | **0xB4** | (V0 reply) | `ptReal`; reply `op` | `CmdStatusV0.parsePtTimer` |
| Timer count | `0x33`/`0xAA` | **0x12** | `NewTimerCountController` | `ptReal`; reply `op` | `CmdStatusV*.parsePtTimerCount` |
| Timer V2 | `0x33`/`0xAA` | **0x13** | `NewTimerControllerV2` | `ptReal`; reply `op` | `CmdStatusV*.parsePtTimer` |
| Device spec/version read | `0xAA` read | **0xB3** | `SpecController.getCommandType()` (=-77), `AbsOnlyReadSingleController` | `ptReal` (read) / device meta | `h5080/ble/controller/SpecController.java` |
| Heartbeat | `0x33`/`0xAA` | (see HeartControllerV2) | `HeartControllerV2` | n/a (BLE link only) | `h5080/ble/controller/HeartControllerV2.java` |
| Sync time | `0x33` write | (see SyncTimeController) | `SyncTimeController` | `ptReal` | `h5080/ble/controller/SyncTimeController.java` |
| Full status snapshot | n/a | n/a | n/a | native `status` → `state`+`op` reply | `CmdStatus.java`, `IotOpV1.java` |

`SwitchControllerV2.getCommandType()` returning `0x01` is the per-feature **opcode** (it becomes `byte[1]` of a `0x33`/`0xAA` frame via the base `AbsSingleController.getValue()` framing). The `turn`/`switch` *frame type* is the usual `0x33` (write) / `0xAA` (read).

---

## 5. H5086 (energy-monitoring plug) — distinct status path

Source: `com/govee/h5086/iot/State.java`, `com/govee/h5086/iot/CmdStatus.java`

- **`State`** (Kotlin data class): just `{ onOff: Int }` — single field, same bitmask idea.
- **`CmdStatus`** reassembles **multi-packet** passthrough replies. Its `g()` (chart) and `h()` (timer) iterate `List<byte[]>` and select frames whose `bArr[0] == -84` (**0xAC**, a multi-read response frame type) and dispatch on a *sub-opcode at `bArr[6]`*:
  - `bArr[6] == 13` (**0x0D**) → recent-hour energy chart, reassembled via `RecentOneHourChartController.f(...)`.
  - `bArr[6] == 19` (**0x13**) → timer list, via `TimerReadController.e(...)`.
  - Reassembly: first packet (`bArr[1]==0`) carries a count (`getSignedIntV2(bArr[2..3])`) and per-packet length `bArr[4]`, copying `bArr[7..]`; continuation packets copy `bArr[2..]` (17 bytes mid, remainder last).
- `c(bArr, fn)` decodes an on/off-remaining-time triple from `bArr[3]` (hour), `bArr[4]` (minute), `bArr[5..7]` (signed remaining seconds) into `ReadInfo` (`setHourOn/Off`, `setMinuteOn/Off`, `setRemainSecOn/Off`).

The 0xAC frame type here corresponds to the BLE multi-read response family (cf. `0xA2/0xAB/0xAC` multi-read opcodes in the ground-truth multi-packet spec). H5086 thus uses **multi-packet passthrough** for bulk reads (energy history, timer lists), unlike the single-frame `ptReal` used by H5080's switch/delay/timer.

---

## 6. Practical takeaways for an independent (non-app) implementation

1. To control a plug over the cloud the simplest, fully-general route is **`ptReal`**: build the normal 20-byte BLE frame (correct opcode + XOR BCC), Base64-encode it (`NO_WRAP`), and send `{"msg":{"cmd":"ptReal","type":1,"data":{"command":["<b64>"]},"transaction":"…","accountTopic":"…"}}`.
2. For plain on/off you may instead use native **`turn`** with `data={"val": <byte>}`, where `val` follows the order/on-bit table in §2. This is a useful independent confirmation that the BLE switch frame's payload byte uses base nibble `0x10/0x20/0x40/0xF0` + on-bits `0x01/0x02/0x04/0x0F`.
3. Reading state: send native **`status`**; parse the reply's `state.onOff` bitmask (bit *i* = socket *i*) and decode any `op.command[]` Base64 frames by their `byte[1]` opcode (`0xB0` delay, `0xB4/0x12/0x13` timers).
4. Base64 here is **standard alphabet, no padding-wrap** (`NO_WRAP`); frames are always exactly 20 bytes after decode (the code asserts this).

### Uncertain / not fully traced
- The exact JSON field name of the serialized `CmdTurn` is inferred as `"val"` from the field `int val;` (Gson default field-name serialization); not seen as a literal string constant. **Flag: verify against a captured packet.**
- `multiSync` and `ptUrl` cloud cmds exist (`base2home/iot/Cmd.java`) but no plug-specific builder was found in scope; likely used by lights/group sync, not plugs.
- `ptIot` (h5080 `Cmd.java`) appears alongside `ptReal` but its plug builder wasn't located in the iot/ package — possibly the OTA/auto path (`base2light/ble/ota/auto/CmdPtIot.java`).
- H5086 multi-packet sub-opcodes beyond `0x0D`/`0x13` (e.g. power-warning, time-monitor) are assembled inside the un-decompiled `CmdStatus.d(...)` (method dump skipped by jadx) — not fully enumerated.
