export const meta = {
  name: 'govee-all-devices-extract',
  description: 'Extract BLE protocol for ALL Govee device families in the Home app: full goodsType->family->SKU matrix + per-family command/mode byte layouts',
  phases: [
    { title: 'Matrix', detail: 'goodsType<->family<->SKU<->BLE-capability map' },
    { title: 'Families', detail: 'one agent per device-family cluster extracts device-specific opcodes + Mode/SubMode byte layouts' },
    { title: 'Synthesize', detail: 'assemble the companion device reference GOVEE_BLE_DEVICES.md' },
  ],
}

const BASE = '/home/evan/workspace/_hass/govee-ble-plugs/re_apk/decompiled/base/sources'
const PACT = '/home/evan/workspace/_hass/govee-ble-plugs/re_apk/decompiled'
const OUT = '/home/evan/workspace/_hass/govee-ble-plugs/re_apk/spec_sections'
const CATALOG = `${OUT}/_sku_catalog.md` // 617-SKU goodsType catalog already extracted

const GROUND = `
The core framing is ALREADY documented in re_apk/GOVEE_BLE_PROTOCOL.md (read it if useful). Recap:
20-byte frame [type][opcode][payload..][BCC=XOR(0..18)]; type 0x33=write 0xAA=read; mode cmd 0x05 with sub-mode selector at byte[2]; multi-packet 0xA1/0xA2; notify 0xEE. GATT service ...1910, unified char ...2b11. jadx prints signed bytes — convert via (v&0xFF).
Most Govee LIGHTS share the base2light common command set (on/off 0x01, brightness 0x04, mode 0x05, scenes/color/music/DIY as sub-modes). Per-family classes mainly (a) register which goodsTypes/SKUs they handle (Support*.java / pact/*) and (b) define the device-specific Mode/SubMode color/scene/music/DIY byte layouts.
The authoritative SKU->goodsType catalog (617 SKUs, 10 categories) is at ${CATALOG} — read it.
`

const COMMON = `
You are reverse-engineering the decompiled Govee Home Android app v7.5.20 (jadx; partially obfuscated, but byte constants, array writes, and Support/Mode/Controller class names are intact).
Base Java root: ${BASE}    Split modules: ${PACT}/pact_h7160/sources, ${PACT}/pact_h7172/sources, ${PACT}/pact_bbqnew/sources, ${PACT}/pact_thnew/sources
Use Bash (grep/sed/find) + Read freely. Read ACTUAL byte values in frame/mode builders — never guess.
${GROUND}
GOAL: for your assigned device family/cluster, document the BLE protocol so someone could control/monitor those devices: which goodsTypes/SKUs it covers, BLE-controllable vs broadcast-only, and the device-SPECIFIC frame/mode byte layouts BEYOND the common set (color RGB / color-temp / scene apply / DIY / music / segment, and any device-specific opcodes, status/notify parses, broadcast formats). Where a family just reuses the common set, say so and only document deviations. Give byte offsets + meaning + source file:method. Flag uncertainty rather than inventing.
OUTPUT: write your section as markdown (tables for opcode/mode maps) to the file path given, then RETURN the manifest. Be exhaustive in the file, concise in the manifest.
`

const EXTRACT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['section_id', 'output_file', 'summary', 'families_covered', 'confidence'],
  properties: {
    section_id: { type: 'string' },
    output_file: { type: 'string' },
    summary: { type: 'string' },
    families_covered: { type: 'array', items: { type: 'string' }, description: 'package/family names + representative SKUs covered' },
    ble_controllable: { type: 'string', description: 'which of these are BLE-controllable vs broadcast-only vs wifi/cloud-only' },
    key_items: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['name', 'detail'],
        properties: { name: { type: 'string' }, detail: { type: 'string', description: 'opcode/sub-mode + byte layout + source' } },
      },
    },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    open_questions: { type: 'array', items: { type: 'string' } },
  },
}

// ---- Phase 1: device matrix ----
phase('Matrix')
log('Building goodsType<->family<->SKU<->capability matrix across all device packages')

const matrix = await agent(
  `${COMMON}

=== ASSIGNMENT: master device matrix (section_id="matrix") ===
Build the authoritative mapping every integration needs: goodsType -> device family/package -> handled SKUs -> BLE capability -> which command-set/Mode classes apply.
Method:
- Read ${CATALOG} for the SKU->goodsType->category list.
- Find every family registration: grep the tree for Support classes and pact registries — e.g. 'find ${BASE}/com/govee -name "Support*.java"', 'addSupportPact', 'supportPact(', 'goodsType ==', 'registerProtocol', files named pact/Register*.java, pact/SubMaker.java, pact/Model*.java, pact/Support*.java. Each maps (goodsType[,pactType,pactCode]) -> a handler package.
- Determine BLE capability per family: presence of a ble/ package + controllers => BLE-controllable; broadcast-only (sensors) => monitor-only; wifi/iot-only => note as not-BLE.
Produce a big table: | goodsType | SKU(s) | category | family/package | BLE control? | command set (common / family-specific) | notes |. Cover as many of the 617 SKUs as can be mapped (group by goodsType where a family handles many). List any SKUs/goodsTypes you could NOT map.
Write to ${OUT}/matrix.md ; section_id="matrix".`,
  { label: 'matrix:devices', phase: 'Matrix', schema: EXTRACT_SCHEMA, effort: 'high' }
)

// ---- Phase 2: per-family deep dives ----
phase('Families')

const FAMILIES = [
  { id: 'fam-rgbic', title: 'RGBIC lights (rgbiclight super-family)',
    scope: `${BASE}/com/govee/rgbiclight/** (incl. Support4*.java, SupportH6*.java, pact/**, ble/**, all Mode*/SubMode* classes). Representative SKUs: H6105/H6109/H6110/H6119/H6129/H6159/H6185/H61C5/H6184 + DreamColor/BareLight via this package. Extract RGBIC segment-color formats (whole-strip vs per-segment vs brightness-array), color-temp, scene apply, DIY, music/mic sub-modes and their byte layouts; note multi-packet color/scene comTypes.` },
  { id: 'fam-rgb', title: 'RGB (non-IC) lights (rgblight super-family)',
    scope: `${BASE}/com/govee/rgblight/** including subdirs h6113 h6160 h6179 h6181 h6182 h6188 h7308, all Mode*/SubMode*. Extract whole-light RGB + color-temp layout, scene/DIY/music sub-modes, any per-SKU deviations. Note which goodsTypes route here vs rgbiclight.` },
  { id: 'fam-dreamcolor', title: 'DreamColor v1/v2 strips',
    scope: `${BASE}/com/govee/dreamcolorlightv1/** and dreamcolorlightv2/** (+ pact). Extract segment color v1 (0x0B) vs v2 (0x15) formats, scene, DIY graffiti, music, IC-count config. These are the canonical RGBIC segment protocols.` },
  { id: 'fam-string', title: 'String / curtain / bulb-string lights',
    scope: `${BASE}/com/govee/stringlightv2/** (+pact), bulblightstringv1/** (+pact), and hollowlamp/** (+pact). Extract per-bulb/per-node color addressing, color-temp (SubModeColor4Ww 0x0D), scenes/DIY, and any node-count/layout config.` },
  { id: 'fam-tv-immersion', title: 'TV / immersion backlights + capture boxes',
    scope: `${BASE}/com/govee/tvlightv1/**, ${BASE}/com/govee/pact_tvlightv2/**, pact_tvlightv3/**, pact_tvlightv4/**, pickupbox/**, and home/main/device/moment/* if relevant. Extract video/camera color-region protocol, music feast, set-sub-device for movie/music feast (MULTI_SET_DEVICE_4_MOVIE_FEAST 0x50, sub-device 0x85), color-segment-from-screen layout.` },
  { id: 'fam-lamps-misc', title: 'Lamps & misc light forms',
    scope: `${BASE}/com/govee/tablelampv1/**, carlightv1/** (+pact), barelightv1/**, homelightv1/**, h1162/** (incl h1168), h6630/**, pickupbox if not covered. Extract device-specific modes (e.g. table-lamp scenes, car-light music/rhythm, net/curtain H1162 layouts) and deviations.` },
  { id: 'fam-bulbs-spots', title: 'Bulbs & spotlights (h61xx device packages)',
    scope: `${BASE}/com/govee/h6101/** h6102/** h6104/** h6105/** h6113/** h6114/** h6119/** h6127/** h6129/**. Extract per-device Mode/SubMode color/scene/music layouts and any device-specific opcodes (these are adjust/detail packages layered on common-light).` },
  { id: 'fam-panels-newgen', title: 'Panels & newer-gen families (h6159..h70bx, h604a, h705a, h7xxx lights)',
    scope: `${BASE}/com/govee/h6159/** h6160/** h6181/** h6182/** h6185/** h604a/** h705a/** (incl h3401) h70bx/** h70b1/** h70b2/** h6057/** h613839/** h612526/** h7004/** h7017/** h7014/** h6630/**. Extract device-specific mode/scene/segment layouts (hexa panels, glide, etc.) and newer-protocol deviations (e.g. proType overrides, base_h71xx server-driven opcodes).` },
  { id: 'fam-kitchen-air', title: 'Kitchen & Air Treatment appliances',
    scope: `${BASE}/com/govee/h7022/** (kettle/heater), h7017/**, and split modules ${PACT}/pact_h7160/sources (humidifier H7160) + ${PACT}/pact_h7172/sources (ice maker H7172/H7178), plus base_h71xx framework ${BASE}/com/govee/base_h71xx/**. Extract main switch, mode selection, target temp/level, ice-size, delay-start, fault/abnormal status, and broadcast state for kettles/heaters/humidifiers/purifiers/ice-makers/CO2 (H5140). Note base_h71xx runtime opcode reassignment.` },
  { id: 'fam-sensors-complete', title: 'Sensors complete matrix (TH / air / leak / BBQ / probe gateways)',
    scope: `${BASE}/com/govee/base2newth/** (+bbq), ${PACT}/pact_thnew/sources, ${PACT}/pact_bbqnew/sources (incl pact_h5199), ${BASE}/com/govee/h5042/** h5043/** h5151/** h5086(ref only), and base2home temp/hum broadcast utils (ThBroadcastUtil, BcDeviceInfoParseUtil). Produce a per-SKU sensor table: H5051/52/53/54/55, H5074/75, H5100/01/04/05/06/08/09/10/12/40, H5179, H5198/99, H5610, H5055 (BBQ), leak H5042/43/44, gateways H5151/H5112. For each: BLE broadcast byte layout (temp/hum/batt/pm/co2 scaling, signedness) AND connected-read opcodes where present. Complete what the earlier survey left open.` },
  { id: 'fam-controllers-gateways', title: 'Controllers, gateways, channel devices',
    scope: `${BASE}/com/govee/ctlchannel/** , h5151/**, h5042/** h5043/** (as gateways), and the 'Controller'(rootId 1192) + 'Gateway'(rootId 1193) category SKUs from ${CATALOG}. Extract relay/channel control, sub-device enumeration over multi-packet, and gateway-forwarded sub-device frames. Identify which controller SKUs are BLE-controllable.` },
]

log(`Deep-diving ${FAMILIES.length} device-family clusters in parallel`)
const fams = await parallel(
  FAMILIES.map((f) => () =>
    agent(
      `${COMMON}\n\n=== ASSIGNMENT: ${f.title} (section_id="${f.id}") ===\n${f.scope}\n\nWrite to ${OUT}/${f.id}.md ; section_id="${f.id}".`,
      { label: f.id, phase: 'Families', schema: EXTRACT_SCHEMA, effort: 'high' }
    )
  )
).then((r) => r.filter(Boolean))

log(`Family extraction complete: ${fams.length}/${FAMILIES.length}`)

// ---- Phase 3: synthesize companion device reference ----
phase('Synthesize')
const all = [matrix, ...fams].filter(Boolean)
const devicesPath = '/home/evan/workspace/_hass/govee-ble-plugs/re_apk/GOVEE_BLE_DEVICES.md'
const synth = await agent(
  `You are assembling the companion device reference to re_apk/GOVEE_BLE_PROTOCOL.md (which documents the core framing/crypto/plug protocol). Do NOT duplicate the core framing — reference it.
${GROUND}
Section files written by extraction agents (Read each — full detail is in them):
${all.map((s) => `- ${s.section_id}: ${s.output_file} [${s.confidence}] — ${(s.families_covered||[]).slice(0,6).join(', ')}`).join('\n')}

TASK: write ${devicesPath} (Write tool) — the all-device companion. Structure:
1. Intro: scope (all families in app v7.5.20), and the key insight (most lights share the common command set; per-family = mode/color/scene byte layouts). Cross-link GOVEE_BLE_PROTOCOL.md for framing/crypto/plugs.
2. **Device matrix** (from matrix.md): the goodsType -> family -> SKUs -> BLE-control? -> command-set table. This is the centerpiece. Keep it complete; note unmapped SKUs.
3. **Per-family protocol** sections (lights: rgbic, rgb, dreamcolor, string, tv/immersion, lamps/misc, bulbs/spots, panels/newgen): for each, the device-specific color/color-temp/scene/DIY/music/segment frame layouts with byte offsets + source citations. Use tables.
4. **Appliances** (kitchen/air): switch/mode/target/status/broadcast per device type.
5. **Sensors** (complete per-SKU table): broadcast + connected-read byte layouts with scaling/signedness.
6. **Controllers & gateways**.
7. BLE-controllability summary: a concise list of which families are fully controllable / broadcast-monitor-only / not-BLE — the actionable input for an integration.
8. Open questions & per-section confidence.
Merge faithfully; keep concrete byte values + source file:method; do not invent. Aim for the definitive all-device reference.
Return: file path, families documented, count of BLE-controllable families, and the top open questions / unmapped SKUs.`,
  { label: 'synthesize:devices', phase: 'Synthesize', effort: 'high' }
)

return { devices: devicesPath, matrix_file: matrix && matrix.output_file, families: fams.map((f) => f.section_id), synthesis_summary: synth }
