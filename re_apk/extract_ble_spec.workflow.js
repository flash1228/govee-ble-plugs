export const meta = {
  name: 'govee-ble-spec-extract',
  description: 'Reverse-engineer the Govee Home APK: extract the full BLE protocol spec across transport, crypto, broadcast, and per-device command sets',
  phases: [
    { title: 'Extract', detail: 'one agent per protocol dimension reads decompiled source, writes a spec section' },
    { title: 'Verify', detail: 'adversarial re-check of opcode/byte claims in the critical sections' },
    { title: 'Synthesize', detail: 'merge all sections + corrections into one master spec document' },
  ],
}

const BASE = '/home/evan/workspace/_hass/govee-ble-plugs/re_apk/decompiled/base/sources'
const PACT = '/home/evan/workspace/_hass/govee-ble-plugs/re_apk/decompiled' // pact_h7160/sources, pact_thnew/sources, etc.
const OUT = '/home/evan/workspace/_hass/govee-ble-plugs/re_apk/spec_sections'

// Verified ground truth handed to every agent so sections stay consistent and build on confirmed facts.
const GROUND_TRUTH = `
VERIFIED GROUND TRUTH (already confirmed by reading the source — build on this, do not contradict without strong evidence):

GATT (com/govee/ble + base2light): primary service UUID 00010203-0405-0607-0809-0a0b0c0d1910;
unified write+notify characteristic 00010203-0405-0607-0809-0a0b0c0d2b11 (modern); legacy split write 0a0b0c0d-...-1911 / notify ...-1912; CCCD 00002902-....
Alternate chip families also present in the app: Telink "INTELL_ROCKS" 494e5445-4c4c-495f-524f-434b535f**** (HW=4857, 2011..2015), HM-10 0000ffe0/0000ffe1, TI F000FFC0/FFC1/FFC2, 0000fd00/fd01/fd02, 02f00000-...-fe00/ff01.

FRAME FORMAT — single command, exactly 20 bytes:
  byte[0]  = command type: 0x33 (51) = SINGLE_WRITE/control, 0xAA (-86) = SINGLE_READ/query
  byte[1]  = opcode (per-feature, e.g. SINGLE_SWITCH/main switch, brightness, etc.)
  byte[2..18] = payload (zero-padded)
  byte[19] = BCC = XOR of bytes[0..18]
FRAME FORMAT — multi-packet (com/govee/ble/multi/MultiPackageManager, base2light BleUtil.a()):
  byte[0]  = 0xA1 (-95) multi-write / 0xA2 (-94) multi-read
  byte[1]  = comType, byte[2] = packet index/position, byte[3..18] = chunk, byte[19] = XOR
  Other multi opcodes: 0xA6 MTU_MULTIPLE_WRITE, 0xA3 MULTIPLE_WRITE_V1, 0xA4 V2, 0xAB/0xAC multi-read variants.
NOTIFY frames begin 0xEE (-18). Encryption handshake opcodes: 0xB1 (-79) SINGLE_READ_SECRET_KEY, 0xB2 (-78) SINGLE_CHECK_SECRET_KEY.

NOTE ON DECOMPILED BYTES: jadx prints signed decimals. Convert negatives to hex via (v & 0xFF): e.g. -86 -> 0xAA, -95 -> 0xA1, -18 -> 0xEE, -79 -> 0xB1, -78 -> 0xB2, -77 -> 0xB3, -76 -> 0xB4, -80 -> 0xB0, -75 -> 0xB5. Positive 51 -> 0x33, 48 -> 0x30, 1 -> 0x01.
`

const COMMON = `
You are reverse-engineering the decompiled Govee Home Android app (jadx output, partially obfuscated: classes/methods may be renamed a/b/c but byte constants, array writes, and many interface constant names are intact).

Decompiled base.apk Java root: ${BASE}
Split feature modules: ${PACT}/pact_h7160/sources, ${PACT}/pact_h7172/sources, ${PACT}/pact_bbqnew/sources, ${PACT}/pact_thnew/sources
Use Bash (grep/sed/find) and Read freely to explore your scope. Read the actual byte values in frame-building methods — do not guess.

${GROUND_TRUTH}

YOUR JOB: produce a precise, implementation-ready spec section for your assigned dimension. For every command/opcode give: human name, command-type byte (0x33/0xAA/0xA1...), opcode byte (hex), payload layout (byte offsets + meaning + units/encoding), direction (app->device write / device->app notify/read), and the source file:method you found it in. Include checksum/encoding details, value enumerations, and any state/notify parsing. Note multi-packet usage where relevant. Flag anything uncertain rather than inventing it.

OUTPUT: Write your full detailed section as GitHub-flavored markdown to the file path given below using the Write tool (create it). Use clear ## / ### headings and tables for opcode maps. Then RETURN the structured manifest (the StructuredOutput schema) summarizing what you wrote — the manifest's key_items should list the most important opcodes with their hex values and source files. Be exhaustive in the file; concise in the manifest.
`

const EXTRACT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['section_id', 'title', 'output_file', 'summary', 'key_items', 'confidence', 'open_questions'],
  properties: {
    section_id: { type: 'string' },
    title: { type: 'string' },
    output_file: { type: 'string', description: 'absolute path of the markdown section you wrote' },
    summary: { type: 'string', description: '3-8 sentence overview of what this dimension covers' },
    key_items: {
      type: 'array',
      description: 'the most important commands/opcodes (10-40 items)',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['name', 'cmd_type', 'opcode_hex', 'direction', 'source'],
        properties: {
          name: { type: 'string' },
          cmd_type: { type: 'string', description: 'frame type byte e.g. 0x33, 0xAA, 0xA1, 0xEE, or n/a' },
          opcode_hex: { type: 'string', description: 'opcode byte in hex, e.g. 0x01' },
          direction: { type: 'string', description: 'write | read | notify | handshake' },
          payload: { type: 'string', description: 'short payload layout note' },
          source: { type: 'string', description: 'source file:method' },
        },
      },
    },
    crypto_notes: { type: 'string', description: 'any encryption/auth detail relevant to this section, or empty' },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    open_questions: { type: 'array', items: { type: 'string' } },
  },
}

const VERIFY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['section_id', 'items_checked', 'corrections', 'verdict', 'notes'],
  properties: {
    section_id: { type: 'string' },
    items_checked: { type: 'number' },
    corrections: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['item', 'claimed', 'actual', 'source'],
        properties: {
          item: { type: 'string' },
          claimed: { type: 'string' },
          actual: { type: 'string' },
          source: { type: 'string' },
        },
      },
    },
    verdict: { type: 'string', enum: ['confirmed', 'minor_issues', 'major_issues'] },
    notes: { type: 'string' },
  },
}

const TASKS = [
  {
    id: 'transport',
    critical: true,
    title: 'BLE transport, GATT & frame/checksum',
    scope: `Scope: ${BASE}/com/govee/ble/** (BleController, comm/BleCommImp, connect/BleConnectImp, scan/*, multi/MultiPackageManager, AbsBluetoothGattCallback, IRequestMtuSize*, IBleWriteCharacteristicResultCallback), and ${BASE}/com/govee/base2light/ble/BleUtil.java, ${BASE}/com/govee/base2light/ble/comm/** and base2light/ble/controller/BleProtocolConstants.java.
Extract: exact GATT service/characteristic/CCCD UUIDs and how the app picks among the chip families; connection lifecycle (scan->connect->discover->enable notify->MTU request->write); MTU sizes; how a single 20-byte frame is assembled (BleUtil/controllers) and the BCC/XOR checksum algorithm (prove it by reading the loop); how multi-packet write/read works (A1/A2/A6, indexing, reassembly, total-length, success byte); write-with-response vs write-no-response; notify dispatch. Produce the canonical frame diagrams.`,
  },
  {
    id: 'crypto',
    critical: true,
    title: 'Encryption & authentication (secret-key / session)',
    scope: `Scope: ${BASE}/com/govee/encryp/**, ${BASE}/com/govee/encryption/**, ${BASE}/com/govee/h5080/config/SecretKeyConfig.java, ${BASE}/com/govee/h5086/ble/controller/SecretController.java, ${BASE}/com/govee/base2light/ble/AbsConnectDialog4Secret.java, and grep across ${BASE}/com/govee for: SINGLE_READ_SECRET_KEY (0xB1/-79), SINGLE_CHECK_SECRET_KEY (0xB2/-78), "AES", "Cipher", "RSA", "ECB", "CBC", "secretKey", "sessionKey", "token", "aes/". The assets/api.key is an RSA public key.
Extract: the full encrypted/authenticated BLE session handshake (which devices use it, the 0xB1/0xB2 exchange, how the session/secret key is derived and where the RSA public key is used, AES mode/IV/key length, what gets encrypted — whole frame vs payload). This is the post-OTA H5080/H5086 protocol; be precise about the byte sequence and crypto primitives. Cross-reference how a normal control frame is wrapped once a session is established.`,
  },
  {
    id: 'broadcast',
    critical: true,
    title: 'BLE advertisement / broadcast parsing',
    scope: `Scope: ${BASE}/com/govee/ble/scan/**, ${BASE}/com/govee/h5080/add/BleBroadcastProcessor.java, ${BASE}/com/govee/h5086/add/BleBroadcastProcessor.java, and grep across ${BASE}/com/govee for getManufacturerSpecificData, getScanRecord, "0x8843"/34883, "manufacturer", broadcast parsers (BleBroadcastProcessor, *Broadcast*).
Extract: how the app identifies a Govee device from advertisement (manufacturer ID, SKU encoding, MAC), and how it decodes STATE from passive broadcasts — especially plug on/off state in the manufacturer data (the H5080 broadcasts plaintext on/off in the last byte; confirm exact byte offset and mapping). Document the manufacturer-data layout per device family you find, and the local-name / service-data conventions used during pairing.`,
  },
  {
    id: 'common-light',
    critical: false,
    title: 'Common light command set (base2light controllers)',
    scope: `Scope: ${BASE}/com/govee/base2light/ble/controller/** (every *Controller.java) plus base2light/ble/controller/BleProtocolConstants.java.
Extract: the shared 0x33 command set used across lights — main switch / light switch (SINGLE_MAIN_SWITCH, SINGLE_LIGHT_SWITCH 0x30), brightness (0x04), mode/scene (SINGLE_MODE 0x05, sub_mode_*), color sub-modes (sub_mode_color 0x15, color_temp), sync time (0x09), device info & version reads (soft/hard/MCU/wifi/UUID 0x06/0x07/...), factory reset, night/sleep/wake, gradual change, on/off memory, calibration. For each controller class give opcode + payload. Build the master 0x33/0xAA opcode table for lights.`,
  },
  {
    id: 'plug-h5080',
    critical: true,
    title: 'Plug protocol — H5080/H5081/H5082/H5083 (V1-V4)',
    scope: `Scope: ${BASE}/com/govee/h5080/ble/** (BleConstants, Ble, BleComm, BleNotifyComm, BleMultiComm, controller/** incl. SwitchControllerV2, NewTimerController*, HeartControllerV2, SpecController, SyncTimeController, TurnOnOffDelayController, TimerDeleteController, WifiNotifyParse, h5089/*), ${BASE}/com/govee/h5080/adjust/v1/Frame V1 + BleOpV1, adjust/v2/FrameV2+BleOpV2, adjust/v3, adjust/v4_h5160/FrameV4+BleOpV4, ${BASE}/com/govee/h5080/scenes/** and ${BASE}/com/govee/h5080/ConsV1.java.
Extract: the relay ON/OFF control frame for EACH plug generation V1/V2/V3/V4 (opcode + value bytes — note differences across generations and multi-outlet plugs like H5160), timer set/read/delete, delay-off, heartbeat, spec read, sync time, device id / hard+soft version, wifi status, battery, temp/hum. Map each FrameV* builder's exact bytes. Be explicit about which SKUs map to which version (H5080/81/82/83/85/89/H5160). This is the core deliverable — be exhaustive on the plug switch + timer + delay commands and their notify/status parses.`,
  },
  {
    id: 'plug-h5086',
    critical: true,
    title: 'Plug protocol — H5086 Smart Plug Pro (energy monitoring)',
    scope: `Scope: ${BASE}/com/govee/h5086/ble/** (BleComm, BleNotifyComm, BleMultiComm, AbsBleWithChartDataComm, controller/** = SwitchController, DelayOnOffController, ChildLockController, LightController, DeviceElectricController, PowerWarningController(+V2), DeviceBasicInfoController, ExceptionStateController, ReadInfoController, RecentOneHourChartController, TimeMonitorController, TimerRead/WriteController, SyncTimeController, WifiInfoController, SecretController, PairToDeviceInfoReadController, chartcontroller/*), ${BASE}/com/govee/h5086/ble/*NotifyParse.java, ${BASE}/com/govee/h5086/ble/ChartStateNotifyParser.java, ${BASE}/com/govee/h5086/H5086Constants.java.
Extract: switch, delay on/off, child lock, indicator light, sync time, timer; and the energy-monitoring specifics — instantaneous electric (voltage/current/power) read + units/scaling, power-warning thresholds, the multi-packet chart-data read protocol (time range, prepare, packetized history), time-monitor sessions, exception state. Document the notify parsers' byte layouts and scaling factors precisely.`,
  },
  {
    id: 'plug-h5089',
    critical: false,
    title: 'Plug H5089/H5085 variant — night light + multi-control',
    scope: `Scope: ${BASE}/com/govee/h5080/adjust/h5089/** (BleOp4H5089, Frame4H5089, CmdStatus4H5089, H5089OpManager, light/*) and ${BASE}/com/govee/h5080/ble/controller/h5089/** (Controller4TotalSwitch, Controller4ChildLock, Controller4NlSwitch, Controller4NlSleep, Controller4NlWakeUp, Controller4H5089TimerInfo, Notify4NightLight, Event4*), ${BASE}/com/govee/h5080/H5085MatterHelper.java.
Extract: total switch, child lock, the night-light sub-protocol (switch/color/diy/scene/sleep/wakeup) including its frame opcodes and color/scene payload encoding, H5089 timer info, and any Matter-related hints. Note how this layers on the H5080 frame format.`,
  },
  {
    id: 'rgbic',
    critical: false,
    title: 'RGB / RGBIC light protocol survey',
    scope: `Scope: ${BASE}/com/govee/rgblight/**, ${BASE}/com/govee/rgbiclight/**, ${BASE}/com/govee/dreamcolorlightv1/**, ${BASE}/com/govee/dreamcolorlightv2/**, ${BASE}/com/govee/stringlightv2/**, plus base2light scene/color/DIY controllers and the multi-packet scene/DIY opcodes in BleProtocolConstants (MULTI_* , sub_mode_*).
Extract: how RGB color, RGBIC segment color, color temperature, brightness, scene application (single + multi-packet scene/effect codes), DIY effects, and music/mic modes are sent. Provide representative frame layouts (segment color, whole-strip color, scene id apply). This is a survey — capture the patterns and the most common opcodes, not every effect.`,
  },
  {
    id: 'sensors',
    critical: false,
    title: 'Sensors & appliances survey (temp/hum, BBQ, kettles)',
    scope: `Scope: base.apk sensor/appliance device packages under ${BASE}/com/govee/ (h5042, h5043, h5051..h5055 if present, h7160, h7170/h7171, h7022, base2newth/bbq, base_h71xx) AND the split modules ${PACT}/pact_thnew/sources, ${PACT}/pact_h7160/sources, ${PACT}/pact_h7172/sources, ${PACT}/pact_bbqnew/sources. grep those trees for *Controller, *NotifyParse, Frame*, Broadcast*.
Extract: how thermo-hygrometers report temperature/humidity (via broadcast and/or connected reads — byte layout + scaling, signed temp), BBQ probe protocols (multi-probe temp, target/alarm), kettle/heater set-temperature + mode. A survey across these categories: capture representative read/notify frame layouts and broadcast formats with scaling factors.`,
  },
  {
    id: 'iot-map',
    critical: false,
    title: 'BLE<->IoT/cloud command cross-reference',
    scope: `Scope: ${BASE}/com/govee/h5080/iot/** (Cmd, CmdTurn, CmdStatus*, CmdPtReal, ResultPt), ${BASE}/com/govee/h5086/iot/**, and grep ${BASE}/com/govee/base2home and base2light for "ptReal", "pt/real", "multiSync", IoT passthrough command builders.
Extract: how the same on/off/timer commands are encoded for the cloud "pt" (passthrough) path as base64 of the same 20-byte BLE frames (confirm by reading CmdTurn/CmdPtReal), and the device "spec"/status JSON shape. This cross-references BLE opcodes with their cloud representation and helps validate the BLE frame bytes. Keep it focused on plugs.`,
  },
]

phase('Extract')
log(`Extracting ${TASKS.length} protocol dimensions in parallel from decompiled Govee Home APK`)

const extracted = await parallel(
  TASKS.map((t) => () =>
    agent(
      `${COMMON}\n\n=== YOUR ASSIGNMENT: ${t.title} (section_id="${t.id}") ===\n${t.scope}\n\nWrite your section to: ${OUT}/${t.id}.md\nSet output_file to that exact path. section_id must be "${t.id}".`,
      { label: `extract:${t.id}`, phase: 'Extract', schema: EXTRACT_SCHEMA, effort: 'high' }
    )
  )
).then((r) => r.filter(Boolean))

log(`Extraction complete: ${extracted.length}/${TASKS.length} sections written`)

// Adversarial verification of the critical sections: re-read the cited sources and confirm the opcode bytes.
phase('Verify')
const criticalIds = new Set(TASKS.filter((t) => t.critical).map((t) => t.id))
const toVerify = extracted.filter((s) => s && criticalIds.has(s.section_id))
log(`Adversarially verifying ${toVerify.length} critical sections (opcode/byte accuracy)`)

const verifications = await parallel(
  toVerify.map((s) => () => {
    const itemList = (s.key_items || [])
      .map((k) => `- ${k.name}: cmd_type=${k.cmd_type} opcode=${k.opcode_hex} dir=${k.direction} [${k.source}]`)
      .join('\n')
    return agent(
      `You are a skeptical reverse-engineering verifier. Decompiled base.apk Java root: ${BASE}.
${GROUND_TRUTH}
A prior agent produced the spec section "${s.section_id}" (${s.title}). Independently RE-READ the cited source files (Bash grep/sed + Read) and check that each claimed opcode/byte is ACTUALLY what the source contains. Watch for: sign/hex conversion errors (jadx prints signed decimals), opcode confused with payload, wrong source file, command-type byte wrong, hallucinated commands not present in code. Default to skepticism — if you cannot find a claim in the source, report it as a correction with actual="NOT FOUND".
Claimed key items:\n${itemList}\n
Also spot-check the section file at ${OUT}/${s.section_id}.md if useful. Return the verdict and a list of concrete corrections (only real discrepancies; empty if all confirmed).`,
      { label: `verify:${s.section_id}`, phase: 'Verify', schema: VERIFY_SCHEMA, effort: 'high' }
    )
  })
).then((r) => r.filter(Boolean))

const totalCorrections = verifications.reduce((n, v) => n + (v.corrections ? v.corrections.length : 0), 0)
log(`Verification done: ${verifications.length} sections checked, ${totalCorrections} corrections found`)

// Synthesis: one agent merges all section files + applies verification corrections into the master spec.
phase('Synthesize')
const manifest = extracted.map((s) => ({
  section_id: s.section_id,
  title: s.title,
  file: s.output_file,
  confidence: s.confidence,
  open_questions: s.open_questions,
}))
const correctionsBlock = verifications
  .map((v) => `Section ${v.section_id} [${v.verdict}], ${v.corrections.length} corrections:\n` +
    v.corrections.map((c) => `   * ${c.item}: claimed ${c.claimed} -> ACTUAL ${c.actual} (${c.source})`).join('\n'))
  .join('\n')

const masterPath = '/home/evan/workspace/_hass/govee-ble-plugs/re_apk/GOVEE_BLE_PROTOCOL.md'
const synth = await agent(
  `You are assembling the definitive Govee BLE protocol reference from per-dimension spec sections that other agents wrote to disk.
${GROUND_TRUTH}
Section files (read each with Read; they contain the full detail):
${manifest.map((m) => `- ${m.section_id} (${m.title}) [confidence ${m.confidence}] -> ${m.file}`).join('\n')}

Verification corrections to APPLY while merging (fix the corresponding facts; if a correction says NOT FOUND, drop or clearly flag that claim):
${correctionsBlock || '(none)'}

TASK: Write a single, coherent, implementation-ready master document to ${masterPath} using the Write tool. Structure:
1. Overview & scope (app version 7.5.20, what devices covered).
2. BLE transport: GATT UUIDs (table of chip families), connection lifecycle, MTU, write/notify.
3. Frame format: single 20-byte frame diagram + BCC/XOR checksum (with worked example), multi-packet framing, notify (0xEE) frames.
4. Encryption/authentication session (0xB1/0xB2, AES/RSA details).
5. Broadcast/advertisement parsing (device id + plug on/off state from manufacturer data).
6. Command reference by category: Common light opcodes; Plugs H5080 V1-V4 (relay/timer/delay/heartbeat/spec); H5086 Smart Plug Pro (energy + chart); H5089 night light; RGB/RGBIC survey; Sensors/BBQ survey.
7. BLE<->cloud passthrough cross-reference.
8. Open questions / lower-confidence items, and a per-section confidence summary.
Use tables for every opcode map (columns: Name | cmd byte | opcode | payload | dir | source). Preserve concrete byte values and source file:method citations. Merge faithfully — do not invent opcodes beyond what the sections contain. Keep the corrected values. Aim for a thorough, single-source-of-truth document.
Return a short summary: master file path, total opcodes documented, sections with low confidence, and the top open questions.`,
  { label: 'synthesize:master', phase: 'Synthesize', effort: 'high' }
)

return {
  master: masterPath,
  sections: manifest,
  verification: verifications.map((v) => ({ id: v.section_id, verdict: v.verdict, corrections: v.corrections.length })),
  synthesis_summary: synth,
}
