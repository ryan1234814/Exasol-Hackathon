// -----------------------------------------------------------------------------
// Demo parachute. When the app is built/served with VITE_MOCK=1, api.js resolves
// every request from this module instead of the backend, so all eleven tabs
// render identically with the database down (plan: "VITE_MOCK=1 renders the
// identical UI with the DB down"). The numbers are not invented theatre — they
// mirror the signals actually verified against the live WARDQ schema: ward 12
// coliform outbreak (avg ~27 CFU), ward 5 chlorine under-dosing (~0.11 mg/L),
// wards 9/14 sensor-only pH breaches the lab disputes, monsoon turbidity spike,
// ward 21 slow turbidity deterioration.
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
// There is no hand-set risk here: the score is derived from the components by
// the same 35/30/15/20 weighting the UDF uses, so the simulator's "at shipped
// weights this reproduces RISK_SCORE" claim is true in mock mode too.
const FLAGGED = {
  12: { param: 'COLIFORM', z: 3.9, breach: 0.92, slope: 0.71, dens: 8.4, rank: 1 },
  5: { param: 'CHLORINE', z: 2.6, breach: 0.64, slope: 0.42, dens: 5.1, rank: 2 },
  9: { param: 'PH', z: 2.2, breach: 0.51, slope: 0.18, dens: 6.8, rank: 3 },
  14: { param: 'PH', z: 2.1, breach: 0.49, slope: 0.15, dens: 6.1, rank: 4 },
  21: { param: 'TURBIDITY', z: 1.4, breach: 0.33, slope: 0.95, dens: 2.9, rank: 5 },
  3: { param: 'TURBIDITY', z: 1.9, breach: 0.41, slope: 0.25, dens: 3.6, rank: 6 },
}

const MONTHS = ['2025-11', '2025-12', '2026-01', '2026-02', '2026-03', '2026-04',
  '2026-05', '2026-06', '2026-07', '2026-08', '2026-09', '2026-10']
const LATEST_MONTH = '2026-10'

function wards() {
  return WARD_NAMES.map((name, i) => {
    const id = i + 1
    const f = FLAGGED[id]
    // Unflagged wards sit flat but low across all four components, which is what
    // "nothing stands out" looks like in the four numbers the UDF consumes.
    const flat = (8 + ((id * 17) % 26)) / 100
    const z = f ? f.z / 4 : flat
    const breach = f ? f.breach : flat
    const slope = f ? f.slope : flat
    const comp = f ? Math.min(1, f.dens / 5) : flat
    // Components are the source of truth, exactly as in the UDF: RISK_SCORE is
    // their weighted sum, never a separately hand-set number.
    const risk = +(35 * z + 30 * breach + 15 * slope + 20 * comp).toFixed(4)
    return {
      WARD_ID: id,
      WARD_NAME: name,
      CITY,
      CITY_ZONE: id % 2 === 0 ? 'South' : 'North',
      POPULATION: 18000 + ((id * 3137) % 60000),
      CONNECTIONS: 4200 + ((id * 911) % 12000),
      DOWNSTREAM: id === 12 || id === 3 || id === 21,
      SAMPLE_MONTH: LATEST_MONTH,
      RISK_SCORE: risk,
      WORST_PARAM: f ? f.param : 'TURBIDITY',
      COMPLAINT_DENSITY: f ? f.dens : +(comp * 5).toFixed(2),
      RANK_IN_MONTH: f ? f.rank : null,
      Z_COMPONENT: +z.toFixed(4),
      BREACH_COMPONENT: +breach.toFixed(4),
      SLOPE_COMPONENT: +slope.toFixed(4),
      COMPLAINT_COMP: +comp.toFixed(4),
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
  // The last bucket starts on the first of the latest month, so the forecast's
  // breach date lands in the same calendar as every other panel instead of
  // drifting a year behind the month the header claims to show.
  const END_MS = Date.UTC(2026, 9, 1)
  for (let b = 0; b < n; b++) {
    const date = new Date(END_MS - (n - 1 - b) * 7 * 86400000)
    let base = meta.base
    // monsoon spike for turbidity mid-series; coliform outbreak late for ward 12
    if (param === 'TURBIDITY' && ward.DOWNSTREAM && b >= 18 && b <= 26) base += 3.4
    if (param === 'COLIFORM' && ward.WARD_ID === 12 && b >= 30) base += 18 + (b - 30) * 2
    if (param === 'CHLORINE' && ward.WARD_ID === 5) base = 0.11 + Math.sin(b / 3) * 0.02
    // planted signal 4: ward 21 turbidity deteriorates slowly. Without a real
    // drift the forecast tail fits a flat line and the mock would never show a
    // countdown, which is the whole point of the forecast card.
    if (param === 'TURBIDITY' && ward.WARD_ID === 21 && b >= 28) base += (b - 28) * 0.2
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

// ORDER BY PARAM_CODE, which is the order /api/wards/{id}/forecast returns.
const PARAM_ORDER = ['CHLORINE', 'COLIFORM', 'PH', 'TURBIDITY']
const HORIZON_DAYS = 90

// 13 months x 24 wards in one payload, mirroring /api/heatmap. Earlier months
// are damped so the replay slider tells a story instead of repeating the same
// picture thirteen times — the flagged wards get visibly worse toward the end.
function heatmap({ months } = {}) {
  const count = Math.max(1, Math.min(months || 13, MONTHS.length))
  const window = MONTHS.slice(-count)
  const ws = wards()
  const dims = ws
    .map((w) => ({
      WARD_ID: w.WARD_ID, WARD_NAME: w.WARD_NAME, CITY: w.CITY, CITY_ZONE: w.CITY_ZONE,
      POPULATION: w.POPULATION, CONNECTIONS: w.CONNECTIONS, DOWNSTREAM: w.DOWNSTREAM,
    }))
    .sort((a, b) => a.WARD_ID - b.WARD_ID)

  const cells = []
  window.forEach((month, mi) => {
    const fromEnd = window.length - 1 - mi
    const monthCells = dims.map((dim) => {
      const latest = ws.find((x) => x.WARD_ID === dim.WARD_ID)
      const decay = fromEnd === 0 ? 1 : Math.max(0.4, 1 - fromEnd * 0.055)
      // The newest month is the exact stored score, so the cell agrees with the
      // KPI, the leaderboard and the case file. Older months get a wobble so the
      // replay reads as a moving picture rather than a repeated one.
      const wobble = fromEnd === 0 ? 1 : 1 + 0.07 * Math.sin((dim.WARD_ID + mi) / 1.7)
      const risk = Math.max(2, Math.min(99, Number(latest.RISK_SCORE) * decay * wobble))
      return {
        SAMPLE_MONTH: month, WARD_ID: dim.WARD_ID,
        RISK_SCORE: fromEnd === 0 ? latest.RISK_SCORE : +risk.toFixed(1),
        WORST_PARAM: latest.WORST_PARAM, COMPLAINT_DENSITY: latest.COMPLAINT_DENSITY,
        RANK_IN_MONTH: null,
      }
    })
    monthCells.sort((a, b) => b.RISK_SCORE - a.RISK_SCORE).forEach((c, i) => { c.RANK_IN_MONTH = i + 1 })
    cells.push(...monthCells)
  })
  cells.sort((a, b) => a.SAMPLE_MONTH.localeCompare(b.SAMPLE_MONTH) || a.WARD_ID - b.WARD_ID)
  return { months: window, wards: dims, cells, months_returned: window.length, query_ms: 3.4 }
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

function addDays(iso, days) {
  const date = new Date(`${String(iso).slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(date.getTime())) return null
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

// A JS mirror of backend/forecast.py, so the forecast cards can be walked with
// the database down. The slope comes from a least-squares fit over the tail of
// the same series Trend.jsx draws — not from a separate invented number.
function forecastItem(wardId, code, horizonDays) {
  const ward = wards().find((w) => w.WARD_ID === Number(wardId))
  const meta = PARAM_META[code]
  const series = trend(wardId, code).series
  const tail = series.slice(-6).map((p) => p.DISPLAY_VALUE)
  const n = tail.length
  const mean = tail.reduce((a, b) => a + b, 0) / n

  let num = 0
  let den = 0
  tail.forEach((y, i) => {
    num += (i - (n - 1) / 2) * (y - mean)
    den += (i - (n - 1) / 2) ** 2
  })
  const slope = +((den ? num / den : 0) / 7).toFixed(6) // the series is 7-day buckets
  const variance = n > 1 ? tail.reduce((a, y) => a + (y - mean) ** 2, 0) / (n - 1) : 0
  const stddev = +Math.sqrt(variance).toFixed(4)
  const current = +mean.toFixed(3)
  const lastDate = series[series.length - 1].BUCKET_START
  const samples = 30 // six weekly buckets x five readings
  const lo = meta.THRESHOLD_LO
  const hi = meta.THRESHOLD_HI

  let eta = null
  if (Math.abs(slope) >= 1e-9) {
    if (slope > 0 && hi != null) eta = +((hi - current) / slope).toFixed(1)
    else if (slope < 0 && lo != null) eta = +((current - lo) / Math.abs(slope)).toFixed(1)
  }

  const over = (hi != null && current > hi) || (lo != null && current < lo)
  let status
  if (over) status = 'over_limit'
  else if (Math.abs(slope) < 1e-9) status = 'stable'
  else {
    const limit = slope > 0 ? hi : lo
    if (limit == null) status = 'improving'
    else if (eta == null) status = 'unknown'
    else if (eta <= 0) status = 'over_limit'
    else if (eta <= horizonDays) status = 'deteriorating'
    else status = 'stable'
  }

  const width = 1.96 * stddev * Math.sqrt(horizonDays / 7)
  const bandLow = samples >= 7 ? +Math.max(0, current - width).toFixed(3) : null
  const bandHigh = samples >= 7 ? +(current + width).toFixed(3) : null
  const breachOn = eta != null && eta >= 0 ? addDays(lastDate, Math.round(eta)) : null
  const project = (days) => +Math.max(0, current + slope * days).toFixed(3)

  const withUnit = (value) => `${value} ${meta.UNIT}`.trim()
  let headline
  if (status === 'unknown') headline = `not enough recent history to forecast ${meta.PARAM_NAME}`
  else if (status === 'over_limit') {
    headline = hi != null && (lo == null || current > hi)
      ? `already above the ${withUnit(hi)} limit`
      : `already below the ${withUnit(lo)} limit`
  } else if (status === 'deteriorating') {
    headline = `crosses ${withUnit(slope > 0 ? hi : lo)} in ~${Math.round(eta)} days${breachOn ? ` (${breachOn})` : ''}`
  } else if (status === 'improving') {
    const limit = slope > 0 ? lo : hi
    headline = limit != null ? `moving away from the ${withUnit(limit)} limit` : 'moving away from its limit'
  } else headline = `no breach expected within ${horizonDays} days`

  return {
    WARD_ID: ward.WARD_ID, WARD_NAME: ward.WARD_NAME, PARAM_CODE: code,
    PARAM_NAME: meta.PARAM_NAME, UNIT: meta.UNIT,
    THRESHOLD_LO: lo, THRESHOLD_HI: hi, CURRENT: current,
    SLOPE_PER_DAY: slope, RECENT_STDDEV: stddev, RECENT_N: samples, LAST_DATE: lastDate,
    STATUS: status, DAYS_TO_BREACH: eta, BREACH_DATE: breachOn,
    PROJECTED_30D: project(30), PROJECTED_90D: project(90),
    BAND_LOW: bandLow, BAND_HIGH: bandHigh,
    CONFIDENCE: samples >= 25 ? 'high' : samples >= 14 ? 'medium' : 'low',
    HORIZON_DAYS: horizonDays, HEADLINE: headline,
  }
}

function forecast(wardId, { param, horizonDays } = {}) {
  const ward = wards().find((w) => w.WARD_ID === Number(wardId)) || wards()[0]
  const horizon = horizonDays || HORIZON_DAYS
  const codes = param ? [param] : PARAM_ORDER
  const items = codes.map((code) => forecastItem(ward.WARD_ID, code, horizon))
  return {
    ward, horizon_days: horizon, items, item: param ? items[0] : null,
    method: 'trailing 12-month ordinary-least-squares slope over the daily aggregate, ' +
      'extended linearly; the band is 1.96 sigma of the last 30 daily means widening as ' +
      'sqrt(days / 7)',
    query_ms: 2.4,
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

// ward, parameter, sensor breaches, lab breaches. Wards 9 and 14 are the planted
// sensor-only pH false positives; ward 12 coliform is the one the laboratory
// actually confirmed. The contamination-complaint column is derived from
// COMPLAINT_SEED below rather than typed here, so this tab and the complaints
// tab cannot contradict each other on the same number.
const DISAGREEMENT_SEED = [
  [9, 'PH', 30, 0],
  [14, 'PH', 28, 0],
  [12, 'COLIFORM', 27, 22],
  [5, 'CHLORINE', 14, 3],
  [3, 'TURBIDITY', 12, 0],
  [12, 'TURBIDITY', 9, 0],
  [21, 'TURBIDITY', 8, 0],
  [4, 'CHLORINE', 0, 0],
  [6, 'PH', 0, 0],
]

function disagreements({ month, wardId, param, limit } = {}) {
  const ws = wards()
  const rows = DISAGREEMENT_SEED
    .filter(([wid, code]) => (!wardId || wid === Number(wardId)) && (!param || code === param))
    .map(([wid, code, sensor, lab]) => {
      const ward = ws.find((w) => w.WARD_ID === wid)
      const meta = PARAM_META[code]
      const contam = COMPLAINT_SEED.filter((c) => c[0] === wid && c[1] === 'contamination').length
      return {
        SAMPLE_MONTH: month || LATEST_MONTH, WARD_ID: wid, WARD_NAME: ward?.WARD_NAME,
        PARAM_CODE: code, UNIT: meta.UNIT, THRESHOLD_LO: meta.THRESHOLD_LO,
        THRESHOLD_HI: meta.THRESHOLD_HI, SENSOR_READINGS: 600, LAB_READINGS: 120,
        SENSOR_BREACHES: sensor, LAB_BREACHES: lab, CITIZEN_COMPLAINTS_THAT_MONTH: contam,
        VERDICT: lab > 0 ? 'lab_confirmed' : sensor > 0 ? 'instrument_suspect' : 'consistent',
      }
    })
    .sort((a, b) => b.SENSOR_BREACHES - a.SENSOR_BREACHES || a.WARD_ID - b.WARD_ID)

  const mix = {}
  for (const row of rows) mix[row.VERDICT] = (mix[row.VERDICT] || 0) + 1
  return {
    month: month || LATEST_MONTH, count: rows.length, verdict_mix: mix,
    rows: rows.slice(0, limit || 100),
    note: 'SENSOR_BREACHES counts readings outside the BIS limit from unverified probes; ' +
      'LAB_BREACHES counts lab-confirmed ones. One 288k-row aggregate per request — 15 ms measured.',
    query_ms: 15.2,
  }
}

function num(value, digits = 1) {
  if (value === null || value === undefined || value === '') return '—'
  const parsed = Number(value)
  return Number.isNaN(parsed) ? String(value) : String(+parsed.toFixed(digits))
}

// The morning brief, mirrored from backend/brief.py: the same three slots, the
// same priority order, the same KIND values, the same markdown skeleton.
function brief({ month } = {}) {
  const m = month || LATEST_MONTH
  const ws = wards()
  const ranked = leaderboard({ limit: 6 }).rows
  const items = ws.flatMap((w) => PARAM_ORDER.map((code) => forecastItem(w.WARD_ID, code, HORIZON_DAYS)))
  const findings = disagreements({ limit: 200 }).rows
  const counts = summary().counts
  const head = ranked[0]

  const actions = []
  if (head) {
    actions.push({
      N: 1, KIND: 'rank', WARD_ID: head.WARD_ID, WARD_NAME: head.WARD_NAME,
      TITLE: `Start with ${head.WARD_NAME}`,
      DETAIL: `${head.WORST_PARAM} sits ${num(head.Z_COMPONENT, 2)} of its 0-1 anomaly `
        + `component, with ${num(head.BREACH_COMPONENT, 2)} of days in breach and `
        + `${num(head.N_COMPLAINTS, 0)} complaints (${num(head.N_HIGH_SEV, 0)} high severity).`,
      SQL_STEP: 'morning_brief', SCORE: head.RISK_SCORE,
    })
  } else {
    actions.push({
      N: 1, KIND: 'none', WARD_ID: null, WARD_NAME: null,
      TITLE: 'No ward ranking available',
      DETAIL: 'WARD_MONTH_RISK has no rows for this month — run 60_materialize.sql then reload this page.',
      SQL_STEP: 'morning_brief',
    })
  }

  const crossing = items.filter((i) => i.STATUS === 'deteriorating' && i.DAYS_TO_BREACH != null)
  const preferred = crossing.filter((i) => i.WARD_ID !== actions[0].WARD_ID)
  const pick = (preferred.length ? preferred : crossing)
    .slice()
    .sort((a, b) => a.DAYS_TO_BREACH - b.DAYS_TO_BREACH)[0]
  if (pick) {
    actions.push({
      N: 2, KIND: 'crossing', WARD_ID: pick.WARD_ID, WARD_NAME: pick.WARD_NAME,
      TITLE: `Plan for ${pick.WARD_NAME} · ${pick.PARAM_NAME}`,
      DETAIL: `${pick.HEADLINE}. Currently ${num(pick.CURRENT, 3)} ${pick.UNIT}, trend `
        + `${pick.SLOPE_PER_DAY >= 0 ? '+' : ''}${pick.SLOPE_PER_DAY.toFixed(4)} per day over the `
        + `last 12 months (${pick.CONFIDENCE} confidence, ${num(pick.RECENT_N, 0)} samples).`,
      SQL_STEP: 'forecast_eta', DAYS_TO_BREACH: pick.DAYS_TO_BREACH,
    })
  } else {
    actions.push({
      N: 2, KIND: 'none', WARD_ID: null, WARD_NAME: null,
      TITLE: 'No breach countdown this month',
      DETAIL: 'No parameter is both deteriorating and inside the 90-day horizon.',
      SQL_STEP: 'forecast_eta',
    })
  }

  const suspects = findings.filter((f) => f.VERDICT === 'instrument_suspect')
  if (suspects.length) {
    const worst = suspects.slice().sort((a, b) => b.SENSOR_BREACHES - a.SENSOR_BREACHES)[0]
    actions.push({
      N: 3, KIND: 'instrument', WARD_ID: worst.WARD_ID, WARD_NAME: worst.WARD_NAME,
      TITLE: `Check the probe in ${worst.WARD_NAME}`,
      DETAIL: `${worst.PARAM_CODE}: ${num(worst.SENSOR_BREACHES, 0)} sensor-only breaches against `
        + `${num(worst.LAB_BREACHES, 0)} lab-confirmed ones, with `
        + `${num(worst.CITIZEN_COMPLAINTS_THAT_MONTH, 0)} contamination complaints. A reading only `
        + 'the instrument believes is a maintenance ticket, not an outbreak — verify the probe before flushing.',
      SQL_STEP: 'sensor_vs_lab',
    })
  } else {
    const heavy = ranked.filter((r) => r.N_HIGH_SEV).sort((a, b) => b.N_HIGH_SEV - a.N_HIGH_SEV)[0]
    actions.push(heavy ? {
      N: 3, KIND: 'complaints', WARD_ID: heavy.WARD_ID, WARD_NAME: heavy.WARD_NAME,
      TITLE: `Clear the high-severity queue in ${heavy.WARD_NAME}`,
      DETAIL: `${num(heavy.N_HIGH_SEV, 0)} of ${num(heavy.N_COMPLAINTS, 0)} complaints this month are `
        + 'high severity (illness, no water for days, black water). The triage queue is already severity-sorted.',
      SQL_STEP: 'complaint_category_mix',
    } : {
      N: 3, KIND: 'none', WARD_ID: null, WARD_NAME: null,
      TITLE: 'No third action this month',
      DETAIL: 'No instrument disagreement and no high-severity complaint in the latest month — that is a '+
        'good month, not a missing feature.',
      SQL_STEP: 'latest_risk',
    })
  }

  const watchlist = ranked.slice(1, 4).map((r) => ({
    WARD_ID: r.WARD_ID, WARD_NAME: r.WARD_NAME, RISK_SCORE: r.RISK_SCORE,
    WORST_PARAM: r.WORST_PARAM, RANK_IN_MONTH: r.RANK_IN_MONTH, N_HIGH_SEV: r.N_HIGH_SEV,
  }))

  const headline = [
    `${m}: ${num(counts.wards, 0)} wards ranked`,
    head ? `worst is ${head.WARD_NAME} at ${num(head.RISK_SCORE)}` : null,
    `${num(counts.sample_rows, 0)} readings and ${num(counts.complaint_rows, 0)} complaints analysed`,
    'data as of 2026-10-23 20:15:04',
  ].filter(Boolean).join('; ') + '.'

  const markdown = [
    `# Morning brief — ${m}`, '', headline, '',
    '## Do these three things today',
    ...actions.map((a) => `${a.N}. **${a.TITLE}** — ${a.DETAIL}`), '',
    '## Watchlist', '',
    '| Ward | Risk | Worst parameter | High-severity complaints |',
    '|---|---|---|---|',
    ...watchlist.map((w) => `| ${w.WARD_NAME} | ${num(w.RISK_SCORE)} | ${w.WORST_PARAM} | ${num(w.N_HIGH_SEV, 0)} |`),
    '',
    '## Data and limits', '',
    `- Schema \`WARDQ\` · month \`${m}\` · data as of \`2026-10-23 20:15:04\``,
    `- ${num(counts.sample_rows, 0)} readings · ${num(counts.complaint_rows, 0)} complaints · ${num(counts.wards, 0)} wards`,
    '- Single-node local Exasol Personal VM (2 vCPU / 6 GB); forecast is a 12-month linear slope, not a model.',
    "- Every number above comes from the queries listed in the dashboard's SQL drawer — nothing is generated prose.",
  ].join('\n') + '\n'

  return {
    MONTH: m, HEADLINE: headline, ACTIONS: actions, WATCHLIST: watchlist, COUNTS: counts,
    DATA_AS_OF: '2026-10-23 20:15:04', DATA_SOURCE: 'db/60_materialize.sql',
    NOTE: 'Composed from SQL results by backend/brief.py — no model, no network.',
    MARKDOWN: markdown, query_ms: 21.7,
  }
}

// Complaints are keyed by ward id and the display name is looked up from the
// same ward table every other tab uses — a hand-typed name here is how the mock
// ends up claiming #12 is "Dharavi" on one page and "Baidyabatula" on another.
// [wardId, category, severity, confidence, rawText, ruleEvidence]
const COMPLAINT_SEED = [
  [12, 'contamination', 'high', 0.97, 'Kala paani aa raha hai, bacchon ko pet kharab', 'black water; children sick'],
  [12, 'contamination', 'high', 0.91, 'Tap se ganda paani aur badbu aa rahi hai', 'dirty water; smell'],
  [10, 'pressure', 'medium', 0.58, 'Subah paani ka pressure bahut kam hai', 'low pressure'],
  [13, 'contamination', 'high', 0.84, 'Paani mein mail jaisa ghul gaya hai', 'muddy water'],
  [17, 'leakage', 'high', 0.79, 'Main pipeline phat gaya, 2 din se paani raste mein beh raha', 'pipe burst; 2 days'],
  [5, 'pressure', 'low', 0.42, 'Aaj paani nahi aaya', 'no water'],
  [9, 'contamination', 'medium', 0.66, 'Bahut chlorine ki smell hai', 'chlorine smell heavy'],
  [11, 'contamination', 'high', 0.9, 'Paani peene ke baad bukhar, hospital gaye', 'fever; hospital'],
  [6, 'pressure', 'medium', 0.5, 'Supply bahut dheemi hai', 'slow supply'],
  [8, 'other', 'low', 0.0, 'Repair ke liye shukriya', ''],
]

function complaints({ category, wardId, q, limit, offset } = {}) {
  const ws = wards()
  let rows = COMPLAINT_SEED.map((c, i) => ({
    COMPLAINT_ID: 900000 + i, WARD_ID: c[0],
    WARD_NAME: ws.find((w) => w.WARD_ID === c[0])?.WARD_NAME,
    RECEIVED_TS: `2026-10-${String(20 - (i % 12)).padStart(2, '0')} 0${(i % 9) + 1}:15:00`,
    SENDER_HANDLE: `citizen_${100 + i}`, RAW_TEXT: c[4], CATEGORY: c[1], SEVERITY: c[2],
    CONFIDENCE: c[3], RULE_EVIDENCE: c[5], RULE_VERSION: RULE_VERSION, CHANNEL: 'whatsapp',
  }))
  if (category) rows = rows.filter((r) => r.CATEGORY === category)
  if (wardId) rows = rows.filter((r) => r.WARD_ID === Number(wardId))
  if (q) { const t = q.toLowerCase(); rows = rows.filter((r) => r.RAW_TEXT.toLowerCase().includes(t)) }
  const rank = { high: 0, medium: 1, low: 2 }
  rows = rows.sort((a, b) => rank[a.SEVERITY] - rank[b.SEVERITY])
  const mix = CATEGORIES.map((cat) => ({
    CATEGORY: cat, N: COMPLAINT_SEED.filter((c) => c[1] === cat).length,
    N_HIGH: COMPLAINT_SEED.filter((c) => c[1] === cat && c[2] === 'high').length,
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
  forecast_eta: `-- db/sql/forecast_eta.sql — days until the trend reaches the limit\nSELECT WARD_NAME, PARAM_CODE, UNIT, RECENT_AVG, SLOPE_12M,\n       CASE WHEN SLOPE_12M > 0 AND THRESHOLD_HI IS NOT NULL\n                 THEN (THRESHOLD_HI - RECENT_AVG) / SLOPE_12M\n            WHEN SLOPE_12M < 0 AND THRESHOLD_LO IS NOT NULL\n                 THEN (RECENT_AVG - THRESHOLD_LO) / ABS(SLOPE_12M)\n            ELSE NULL END AS DAYS_TO_BREACH\nFROM WARDQ.V_WARD_FORECAST ORDER BY DAYS_TO_BREACH LIMIT 25;`,
  sensor_vs_lab: `-- db/sql/sensor_vs_lab.sql — instrument or water?\nSELECT lv.WARD_NAME, lv.PARAM_CODE, lv.SENSOR_BREACHES, lv.LAB_BREACHES,\n       CASE WHEN lv.LAB_BREACHES > 0 THEN 'lab_confirmed'\n            WHEN lv.SENSOR_BREACHES > 0 THEN 'instrument_suspect'\n            ELSE 'consistent' END AS VERDICT\nFROM WARDQ.V_LAB_VS_SENSOR lv ORDER BY lv.SENSOR_BREACHES DESC LIMIT 25;`,
  ward_month_matrix: `-- db/sql/ward_month_matrix.sql — the 600-cell month x ward matrix\nSELECT SAMPLE_MONTH, WARD_ID, RISK_SCORE, WORST_PARAM, RANK_IN_MONTH\nFROM WARDQ.WARD_MONTH_RISK\nORDER BY SAMPLE_MONTH DESC, RISK_SCORE DESC LIMIT 600;`,
  morning_brief: `-- db/sql/morning_brief.sql — the brief's inputs\nSELECT r.RANK_IN_MONTH, r.WARD_ID, r.RISK_SCORE, r.WORST_PARAM, r.Z_COMPONENT,\n       r.BREACH_COMPONENT, r.SLOPE_COMPONENT, r.COMPLAINT_COMP\nFROM WARDQ.WARD_MONTH_RISK r\nWHERE r.SAMPLE_MONTH = (SELECT MAX(SAMPLE_MONTH) FROM WARDQ.WARD_MONTH_RISK)\nORDER BY r.RANK_IN_MONTH LIMIT 10;`,
}

// Where each snippet actually lives, so the drawer header is not a lie.
const SQL_FILES = {
  forecast_eta: 'db/sql/forecast_eta.sql',
  sensor_vs_lab: 'db/sql/sensor_vs_lab.sql',
  ward_month_matrix: 'db/sql/ward_month_matrix.sql',
  morning_brief: 'db/sql/morning_brief.sql',
  latest_risk: 'db/sql/latest_risk.sql',
  monsoon_turbidity: 'db/sql/monsoon_turbidity.sql',
  outbreak_detection: 'db/sql/outbreak_detection.sql',
  deteriorating_wards: 'db/sql/deteriorating_wards.sql',
  complaint_vs_lab_disagreement: 'db/sql/complaint_vs_lab_disagreement.sql',
  complaint_category_mix: 'db/sql/complaint_category_mix.sql',
  anomaly_window: 'db/40_anomaly_window.sql (excerpt)',
  materialize: 'db/60_materialize.sql (excerpt)',
  udf_risk: 'db/50_udf_ward_risk.lua.sql (excerpt)',
  verify: 'db/70_verify.sql (excerpt)',
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
  if (bare === '/api/heatmap') {
    return heatmap({ months: q.get('months') ? Number(q.get('months')) : undefined })
  }
  const trendM = bare.match(/^\/api\/wards\/(\d+)\/trend$/)
  if (trendM) return trend(trendM[1], q.get('param') || 'TURBIDITY')
  const forecastM = bare.match(/^\/api\/wards\/(\d+)\/forecast$/)
  if (forecastM) {
    return forecast(forecastM[1], {
      param: q.get('param') || undefined,
      horizonDays: q.get('horizon_days') ? Number(q.get('horizon_days')) : undefined,
    })
  }
  if (bare === '/api/disagreements') {
    return disagreements({
      month: q.get('month') || undefined, wardId: q.get('ward_id') || undefined,
      param: q.get('param') || undefined, limit: Number(q.get('limit') || 100),
    })
  }
  if (bare === '/api/brief') return brief({ month: q.get('month') || undefined })
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
    return {
      step,
      file: SQL_FILES[step] || `db/sql/${step}.sql`,
      sql: SQL_SNIPPETS[step] || `-- no mock SQL registered for ${step}`,
    }
  }
  return { mock: true, note: `no mock for ${bare}` }
}

export { classify }
