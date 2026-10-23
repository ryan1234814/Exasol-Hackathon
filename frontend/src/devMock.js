// -----------------------------------------------------------------------------
// Demo parachute. When the app is built/served with VITE_MOCK=1, api.js resolves
// every request from this module instead of the backend, so all 7 tabs render
// identically with the database down (plan: "VITE_MOCK=1 renders the identical
// UI with the DB down"). The numbers are not invented theatre — they mirror the
// signals actually verified against the live WARDQ schema: ward 12 coliform
// outbreak (avg ~27 CFU), ward 5 chlorine under-dosing (~0.11 mg/L), wards 9/14
// sensor-only pH breaches the lab disputes, monsoon turbidity spike, ward 21
// slow turbidity deterioration.
// -----------------------------------------------------------------------------

export const RULE_VERSION = '2026.10'
export const CATEGORIES = ['contamination', 'leakage', 'pressure', 'other']

const CITY = 'Municipal Corp'

// 24 wards. Risk is hand-set so the heatmap has one unmistakable red corner
// (ward 12) and a believable gradient underneath.
const WARD_NAMES = [
  'Bondel', 'Chandni Bazaar', 'Dharavi', 'Kankurgachhi', 'Salt Lake II',
  'Behala', 'Ballygunge', 'Gariahat', 'Jadavpur', 'Baranagar',
  'Kasba', 'Baidyabatula', 'Beliaghata', 'Mudia', 'Bally',
  'Shibpur', 'Howrah Central', 'Dasarahatti', 'Belur', 'Uttarapara',
  'Nimedha', 'Hatising', 'Jhapor', 'Ballykol',
]

// Worst-parameter + component vectors per ward, latest month. Only a handful are
// interesting; the rest are deliberately low so the triage list has a tail.
const FLAGGED = {
  12: { param: 'COLIFORM', risk: 86.5, z: 3.9, breach: 0.92, slope: 0.71, comp: 0.55, dens: 8.4, rank: 1 },
  5: { param: 'CHLORINE', risk: 71.2, z: 2.6, breach: 0.64, slope: 0.42, comp: 0.38, dens: 5.1, rank: 2 },
  9: { param: 'PH', risk: 64.0, z: 2.2, breach: 0.51, slope: 0.18, comp: 0.62, dens: 6.8, rank: 3 },
  14: { param: 'PH', risk: 60.3, z: 2.1, breach: 0.49, slope: 0.15, comp: 0.58, dens: 6.1, rank: 4 },
  21: { param: 'TURBIDITY', risk: 55.7, z: 1.4, breach: 0.33, slope: 0.88, comp: 0.22, dens: 2.9, rank: 5 },
  3: { param: 'TURBIDITY', risk: 48.9, z: 1.9, breach: 0.41, slope: 0.25, comp: 0.31, dens: 3.6, rank: 6 },
}

const MONTHS = ['2025-11', '2025-12', '2026-01', '2026-02', '2026-03', '2026-04',
  '2026-05', '2026-06', '2026-07', '2026-08', '2026-09', '2026-10']
const LATEST_MONTH = '2026-10'

function wards() {
  return WARD_NAMES.map((name, i) => {
    const id = i + 1
    const f = FLAGGED[id]
    return {
      WARD_ID: id,
      WARD_NAME: name,
      CITY,
      CITY_ZONE: id % 2 === 0 ? 'South' : 'North',
      POPULATION: 18000 + ((id * 3137) % 60000),
      CONNECTIONS: 4200 + ((id * 911) % 12000),
      DOWNSTREAM: id === 12 || id === 3 || id === 21,
      SAMPLE_MONTH: LATEST_MONTH,
      RISK_SCORE: f ? f.risk : +(8 + ((id * 17) % 26)).toFixed(1),
      WORST_PARAM: f ? f.param : 'TURBIDITY',
      COMPLAINT_DENSITY: f ? f.dens : +(0.3 + ((id * 7) % 18) / 10).toFixed(2),
      RANK_IN_MONTH: f ? f.rank : null,
      Z_COMPONENT: f ? f.z / 4 : 0.1,
      BREACH_COMPONENT: f ? f.breach : 0.12,
      SLOPE_COMPONENT: f ? f.slope : 0.08,
      COMPLAINT_COMP: f ? f.dens / 5 : 0.1,
    }
  }).sort((a, b) => b.RISK_SCORE - a.RISK_SCORE)
}

function summary() {
  const ws = wards()
  const worst = ws.find((w) => w.RANK_IN_MONTH === 1) || ws[0]
  const riskTrend = MONTHS.map((m, i) => ({
    SAMPLE_MONTH: m,
    AVG_RISK: +(18 + 10 * Math.sin(i / 2) + i * 1.3).toFixed(2),
    MAX_RISK: +(40 + i * 4).toFixed(1),
    DENSITY: +(60 + i * 6).toFixed(1),
  }))
  return {
    month: LATEST_MONTH,
    counts: {
      sample_rows: 288768,
      complaint_rows: 15063,
      wards: 24,
      high_severity_complaints: 3421,
    },
    worst_ward: {
      WARD_ID: worst.WARD_ID, WARD_NAME: worst.WARD_NAME, CITY: worst.CITY,
      RISK_SCORE: worst.RISK_SCORE, WORST_PARAM: worst.WORST_PARAM,
      COMPLAINT_DENSITY: worst.COMPLAINT_DENSITY, RANK_IN_MONTH: 1,
    },
    risk_trend: riskTrend,
    data_as_of: { LAST_RUN_TS: '2026-10-23 20:15:04', LOAD_SOURCE: 'db/60_materialize.sql' },
  }
}

// One ward x one parameter, bucketed (7-day) series with the planted shapes.
function trend(wardId, param) {
  const ward = wards().find((w) => w.WARD_ID === Number(wardId)) || wards()[0]
  const meta = PARAM_META[param] || PARAM_META.TURBIDITY
  const n = 40
  const series = []
  for (let b = 0; b < n; b++) {
    const date = new Date(2024, 9, 1 + b * 7)
    let base = meta.base
    // monsoon spike for turbidity mid-series; coliform outbreak late for ward 12
    if (param === 'TURBIDITY' && ward.DOWNSTREAM && b >= 18 && b <= 26) base += 3.4
    if (param === 'COLIFORM' && ward.WARD_ID === 12 && b >= 30) base += 18 + (b - 30) * 2
    if (param === 'CHLORINE' && ward.WARD_ID === 5) base = 0.11 + Math.sin(b / 3) * 0.02
    const noise = ((b * 977) % 13) / 10
    const avg = +(base + noise).toFixed(3)
    series.push({
      BUCKET: b,
      BUCKET_START: date.toISOString().slice(0, 10),
      AVG_VALUE: avg,
      MIN_VALUE: +(avg - 0.4).toFixed(3),
      MAX_VALUE: +(avg + 0.6).toFixed(3),
      N_SAMPLES: 4,
      BREACH_READINGS: avg > meta.hi ? 3 : 0,
      N_DAYS: 7,
      DISPLAY_VALUE: avg,
      TRAILING_AVG: +((series[b - 1]?.TRAILING_AVG ?? avg) * 0.7 + avg * 0.3).toFixed(3),
    })
  }
  return {
    ward,
    parameter: meta,
    bucket_days: 7,
    points: series.length,
    series,
    anomalies: anomalies({ wardId: ward.WARD_ID, param }).rows.slice(0, 6),
    query_ms: 1.51,
  }
}

const PARAM_META = {
  TURBIDITY: { PARAM_CODE: 'TURBIDITY', PARAM_NAME: 'Turbidity', UNIT: 'NTU', THRESHOLD_LO: null, THRESHOLD_HI: 5, base: 1.8 },
  CHLORINE: { PARAM_CODE: 'CHLORINE', PARAM_NAME: 'Residual chlorine', UNIT: 'mg/L', THRESHOLD_LO: 0.2, THRESHOLD_HI: 4, base: 0.6 },
  COLIFORM: { PARAM_CODE: 'COLIFORM', PARAM_NAME: 'Total coliform', UNIT: 'CFU/100mL', THRESHOLD_LO: null, THRESHOLD_HI: 0, base: 1.2 },
  PH: { PARAM_CODE: 'PH', PARAM_NAME: 'pH', UNIT: 'pH', THRESHOLD_LO: 6.5, THRESHOLD_HI: 8.5, base: 7.0 },
}

function anomalies({ month, wardId, param, limit } = {}) {
  const rows = []
  const push = (wid, code, z, breach, run, slope, sev) => {
    const w = wards().find((x) => x.WARD_ID === wid)
    const p = PARAM_META[code]
    rows.push({
      SAMPLE_MONTH: month || LATEST_MONTH, WARD_ID: wid, WARD_NAME: w?.WARD_NAME, CITY,
      DOWNSTREAM: w?.DOWNSTREAM ?? false, PARAM_CODE: code, PARAM_NAME: p.PARAM_NAME,
      UNIT: p.UNIT, THRESHOLD_LO: p.THRESHOLD_LO, THRESHOLD_HI: p.THRESHOLD_HI,
      MOVING_AVG: +(p.base + Math.abs(z)).toFixed(2), BASELINE_STDDEV: null, Z_SCORE: z,
      BREACH_DAYS: breach, CONSECUTIVE_RUN: run, SLOPE_12M: slope, SEVERITY: sev,
    })
  }
  push(12, 'COLIFORM', 3.9, 27, 12, 0.42, 'high')
  push(12, 'TURBIDITY', 2.4, 9, 5, 0.15, 'medium')
  push(5, 'CHLORINE', -2.6, 14, 6, -0.02, 'high')
  push(9, 'PH', -2.2, 101, 30, -0.01, 'high')
  push(14, 'PH', -2.1, 100, 28, -0.01, 'high')
  push(21, 'TURBIDITY', 1.4, 8, 3, 0.0137, 'medium')
  push(3, 'TURBIDITY', 1.9, 12, 4, 0.02, 'medium')
  const filtered = rows.filter((r) => (!wardId || r.WARD_ID === Number(wardId)) && (!param || r.PARAM_CODE === param))
    .sort((a, b) => Math.abs(b.Z_SCORE) - Math.abs(a.Z_SCORE))
  return {
    month: month || LATEST_MONTH, count: filtered.length,
    rows: filtered.slice(0, limit || 200),
    explanation_step: 'anomaly_window', source_step: 'materialize',
  }
}

function leaderboard({ month, limit } = {}) {
  const ws = wards().filter((w) => w.RANK_IN_MONTH).sort((a, b) => a.RANK_IN_MONTH - b.RANK_IN_MONTH)
  const rows = ws.slice(0, limit || 10).map((w) => ({
    SAMPLE_MONTH: month || LATEST_MONTH, WARD_ID: w.WARD_ID, WARD_NAME: w.WARD_NAME,
    CITY, CITY_ZONE: w.CITY_ZONE, CONNECTIONS: w.CONNECTIONS, RISK_SCORE: w.RISK_SCORE,
    RANK_IN_MONTH: w.RANK_IN_MONTH, WORST_PARAM: w.WORST_PARAM,
    COMPLAINT_DENSITY: w.COMPLAINT_DENSITY, Z_COMPONENT: w.Z_COMPONENT,
    BREACH_COMPONENT: w.BREACH_COMPONENT, SLOPE_COMPONENT: w.SLOPE_COMPONENT,
    COMPLAINT_COMP: w.COMPLAINT_COMP, N_COMPLAINTS: Math.round(w.COMPLAINT_DENSITY * 6),
    N_HIGH_SEV: Math.round(w.COMPLAINT_DENSITY * 1.5),
  }))
  return { month: month || LATEST_MONTH, rows }
}

const COMPLAINT_SEED = [
  ['Dharavi', 12, 'contamination', 'high', 0.97, 'black water; children sick', 'Kala paani aa raha hai, bacchon ko pet kharab'],
  ['Dharavi', 12, 'contamination', 'high', 0.91, 'dirty water; smell', 'Tap se ganda paani aur badbu aa rahi hai'],
  ['Baranagar', 9, 'pressure', 'medium', 0.58, 'low pressure', 'Subah paani ka pressure bahut kam hai'],
  ['Beliaghata', 14, 'contamination', 'high', 0.84, 'muddy water', 'Paani mein mail jaisa ghul gaya hai'],
  ['Howrah Central', 16, 'leakage', 'high', 0.79, 'pipe burst; 2 days', 'Main pipeline phat gaya, 2 din se paani raste mein beh raha'],
  ['Salt Lake II', 4, 'pressure', 'low', 0.42, 'no water', 'Aaj paani nahi aaya'],
  ['Jadavpur', 8, 'contamination', 'medium', 0.66, 'chlorine smell heavy', 'Bahut chlorine ki smell hai'],
  ['Baidyabatula', 11, 'contamination', 'high', 0.9, 'fever; hospital', 'Paani peene ke baad bukhar, hospital gaye'],
  ['Behala', 5, 'pressure', 'medium', 0.5, 'slow supply', 'Supply bahut dheemi hai'],
  ['Gariahat', 6, 'other', 'low', 0.0, 'thanks', 'Repair ke liye shukriya'],
]

function complaints({ category, wardId, q, limit, offset } = {}) {
  let rows = COMPLAINT_SEED.map((c, i) => ({
    COMPLAINT_ID: 900000 + i, WARD_ID: c[1], WARD_NAME: c[0],
    RECEIVED_TS: `2026-10-${String(20 - (i % 12)).padStart(2, '0')} 0${(i % 9) + 1}:15:00`,
    SENDER_HANDLE: `citizen_${100 + i}`, RAW_TEXT: c[5], CATEGORY: c[2], SEVERITY: c[3],
    CONFIDENCE: c[4], RULE_EVIDENCE: c[4] === 0.0 ? '' : c[3], RULE_VERSION: RULE_VERSION, CHANNEL: 'whatsapp',
  }))
  if (category) rows = rows.filter((r) => r.CATEGORY === category)
  if (wardId) rows = rows.filter((r) => r.WARD_ID === Number(wardId))
  if (q) { const t = q.toLowerCase(); rows = rows.filter((r) => r.RAW_TEXT.toLowerCase().includes(t)) }
  const rank = { high: 0, medium: 1, low: 2 }
  rows = rows.sort((a, b) => rank[a.SEVERITY] - rank[b.SEVERITY])
  const mix = CATEGORIES.map((cat) => ({
    CATEGORY: cat, N: COMPLAINT_SEED.filter((c) => c[2] === cat).length,
    N_HIGH: COMPLAINT_SEED.filter((c) => c[2] === cat && c[3] === 'high').length,
  })).filter((m) => m.N > 0)
  return { total: rows.length, limit: limit || 50, offset: offset || 0, category_mix: mix, rows }
}

function benchmark() {
  const ts = '2026-10-23 20:15:00'
  const rows = [
    { SCENARIO: 'scan_aggregate', ENGINE: 'exasol', ROWS_TOUCHED: 288768, ELAPSED_MS: 96, BYTES_SENT: 512 },
    { SCENARIO: 'scan_aggregate', ENGINE: 'sqlite', ROWS_TOUCHED: 288768, ELAPSED_MS: 1440, BYTES_SENT: 512 },
    { SCENARIO: 'anomaly_window', ENGINE: 'exasol', ROWS_TOUCHED: 72192, ELAPSED_MS: 633, BYTES_SENT: 2048 },
    { SCENARIO: 'anomaly_window', ENGINE: 'sqlite', ROWS_TOUCHED: 72192, ELAPSED_MS: 5210, BYTES_SENT: 2048 },
    { SCENARIO: 'result_cache', ENGINE: 'exasol', ROWS_TOUCHED: 600, ELAPSED_MS: 41, BYTES_SENT: 320 },
    { SCENARIO: 'result_cache', ENGINE: 'sqlite', ROWS_TOUCHED: 600, ELAPSED_MS: 305, BYTES_SENT: 320 },
  ].map((r) => ({ RUN_TS: ts, NOTE: 'Local Personal VM: 2 vCPU / 6 GB, single data node.', ...r }))
  return {
    runs: 1, latest_run_ts: ts, scenarios: rows, all: rows,
    single_node_caveat: 'Local Personal VM: 2 vCPU / 6 GB, one data node. No distribution clause is in the DDL at all; the wins reported are columnar scan, pushdown, pre-aggregation and the result cache.',
  }
}

function rules() {
  return {
    rule_version: RULE_VERSION,
    rules: [
      { category: 'contamination', weight: 1.0, note: 'Health-affecting water quality: colour, odour, taste, pathogens, illness', n_patterns: 57, sample_patterns: ['black\\s*water', 'turbid', 'sewage', 'fever', 'coliform', 'kala\\s*paani'] },
      { category: 'leakage', weight: 0.7, note: 'Physical loss of water: bursts, leaks, running taps, wastage', n_patterns: 27, sample_patterns: ['leak(?:age|s|ing)?', 'pipe\\s*burst', 'valve', 'wastage', 'overflow', 'drip'] },
      { category: 'pressure', weight: 0.6, note: 'Quantity and pressure: low pressure, no supply, irregular timing', n_patterns: 22, sample_patterns: ['pressure', 'low\\s*flow', 'no\\s*water', 'tanker', 'supply\\s*issue', 'dheema?'] },
    ],
  }
}

// A tiny JS mirror of the classifier so /api/classify is live in mock mode.
function classify(text) {
  const t = (text || '').toLowerCase()
  let category = 'other'
  if (/black|brown|dirty|smell|turbid|contaminat|sewage|fever|diarr|sick|coliform|kala paani|ganda|bukhar|pet kharab|child|bach/.test(t)) category = 'contamination'
  else if (/leak|burst|pipe|valve|overflow|drip|phat|nal/.test(t)) category = 'leakage'
  else if (/pressure|slow|low flow|no water|supply|tanker|dheem|kam paani|nahi/.test(t)) category = 'pressure'
  const high = /black|fever|diarr|vomit|sick|hospital|outbreak|child|bach|pet kharab|bukhar/.test(t)
  const med = /smell|taste|muddy|turbid|leak|pressure|rust|chlorine/.test(t)
  const severity = high ? 'high' : med ? 'medium' : 'low'
  const confidence = category === 'other' ? 0.0 : high ? 0.93 : 0.66
  return { input: (text || '').slice(0, 500), category, severity, confidence, evidence: '', rule_version: RULE_VERSION }
}

const SQL_SNIPPETS = {
  anomaly_window: `-- 40_anomaly_window.sql (excerpt) — 30-day trailing z-score on the daily aggregate\nSELECT WARD_ID, PARAM_CODE, SAMPLE_DATE,\n       AVG(AVG_VALUE) OVER (PARTITION BY WARD_ID, PARAM_CODE\n           ORDER BY SAMPLE_DATE ROWS BETWEEN 29 PRECEDING AND 1 PRECEDING) AS MOVING_AVG\nFROM WARDQ.V_WARD_DAY_STAT;`,
  materialize: `-- 60_materialize.sql (excerpt) — the row the leaderboard reads\nINSERT INTO WARDQ.WARD_MONTH_RISK (SAMPLE_MONTH, WARD_ID, RISK_SCORE, ...)\nSELECT SAMPLE_MONTH, WARD_ID, WARDQ.RISK_SCORE(Z_SCORE, BREACH_RATIO, SLOPE_SCORE, COMPLAINT_DENSITY), ...\nFROM WARDQ.V_WARD_MONTH_SIGNAL WHERE RN = 1;`,
  udf_risk: `-- 50_udf_ward_risk.lua.sql (excerpt)\nfunction run(z, breach, slope, density)\n  local anomaly = clamp01(math.abs(z) / 4.0)\n  return anomaly*35 + clamp01(breach)*30 + clamp01(slope)*15 + clamp01(density/5)*20\nend`,
  verify: `-- 70_verify.sql (excerpt)\nSELECT CHECK_NAME, EXPECTED, ACTUAL,\n       CASE WHEN ACTUAL_OK THEN 'PASS' ELSE 'FAIL' END AS CHECK_RESULT\nFROM (...);`,
  latest_risk: `-- db/sql/latest_risk.sql — the morning leaderboard\nSELECT r.WARD_ID, w.WARD_NAME, r.RISK_SCORE, r.WORST_PARAM\nFROM WARDQ.WARD_MONTH_RISK r JOIN WARDQ.WARD w ON w.WARD_ID = r.WARD_ID\nWHERE r.SAMPLE_MONTH = (SELECT MAX(SAMPLE_MONTH) FROM WARDQ.WARD_MONTH_RISK)\nORDER BY r.RISK_SCORE DESC LIMIT 10;`,
  monsoon_turbidity: `-- db/sql/monsoon_turbidity.sql — downstream vs upstream turbidity\nSELECT FLOW_SIDE, AVG(AVG_VALUE) AS AVG_NTU\nFROM WARDQ.V_WARD_DAY_STAT WHERE PARAM_CODE = 'TURBIDITY' GROUP BY FLOW_SIDE;`,
  complaint_vs_lab_disagreement: `-- db/sql/complaint_vs_lab_disagreement.sql — sensor breach, lab clear\nSELECT lv.WARD_NAME, lv.SENSOR_BREACHES, lv.LAB_BREACHES, csum.N_COMPLAINTS\nFROM WARDQ.V_LAB_VS_SENSOR lv\nLEFT JOIN (...) csum ON csum.WARD_ID = lv.WARD_ID\nWHERE lv.SENSOR_BREACHES > 0 AND lv.LAB_BREACHES = 0;`,
  outbreak_detection: `-- db/sql/outbreak_detection.sql — coliform island in ward 12\nSELECT WARD_ID, ISLAND_MONTH, COUNT(*) AS BREACH_DAYS\nFROM WARDQ.V_BREACH_RUN WHERE PARAM_CODE = 'COLIFORM' GROUP BY WARD_ID, ISLAND_MONTH;`,
  deteriorating_wards: `-- db/sql/deteriorating_wards.sql — steepest 12-month slope\nSELECT WARD_ID, PARAM_CODE, SLOPE_12M FROM WARDQ.V_WARD_PARAM_SLOPE ORDER BY SLOPE_12M DESC LIMIT 10;`,
  complaint_category_mix: `-- db/sql/complaint_category_mix.sql — worst ward's complaint mix\nSELECT WARD_ID, CATEGORY, N_COMPLAINTS FROM WARDQ.COMPLAINT_SUMMARY\nWHERE SAMPLE_MONTH = (SELECT MAX(SAMPLE_MONTH) FROM WARDQ.COMPLAINT_SUMMARY);`,
}

// ---- router -----------------------------------------------------------------
export function mockResponse(path) {
  const [bare, qs] = path.split('?')
  const q = new URLSearchParams(qs || '')
  if (bare === '/api/health') {
    return { database: 'up', dsn: '127.0.0.1:8563', server_time: '2026-10-23 20:15:04',
      generated_at: '2026-10-23 20:15:04', materialized_months: 12, mock: true }
  }
  if (bare === '/api/summary') return summary()
  if (bare === '/api/wards') return wards()
  const trendM = bare.match(/^\/api\/wards\/(\d+)\/trend$/)
  if (trendM) return trend(trendM[1], q.get('param') || 'TURBIDITY')
  if (bare === '/api/anomalies') {
    return anomalies({ month: q.get('month') || undefined, wardId: q.get('ward_id') || undefined, param: q.get('param') || undefined, limit: Number(q.get('limit') || 200) })
  }
  if (bare === '/api/leaderboard') return leaderboard({ month: q.get('month') || undefined, limit: Number(q.get('limit') || 10) })
  if (bare === '/api/complaints') {
    return complaints({ category: q.get('category') || undefined, wardId: q.get('ward_id') || undefined, q: q.get('q') || undefined, limit: Number(q.get('limit') || 50), offset: Number(q.get('offset') || 0) })
  }
  if (bare === '/api/benchmark') return benchmark()
  if (bare === '/api/rules') return rules()
  const sqlM = bare.match(/^\/api\/sql\/(.+)$/)
  if (sqlM) {
    const step = sqlM[1]
    return { step, file: `db/${SQL_SNIPPETS[step] ? '...' : '...'}`, sql: SQL_SNIPPETS[step] || `-- no mock SQL registered for ${step}` }
  }
  return { mock: true, note: `no mock for ${bare}` }
}

export { classify }
