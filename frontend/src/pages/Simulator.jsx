import React, { useMemo, useState } from 'react'
import { useGet, fmt, riskColor } from './_shared'
import SqlDrawer from '../components/SqlDrawer'

// What-if simulator: move the four weights and watch the triage order change.
//
// The formula is the UDF's own, normalised so the score stays comparable 0..100
// when the weights no longer sum to 100:
//
//     score = 100 * Σ(wᵢ · cᵢ) / Σwᵢ        (RISK_SCORE is score·35+30+15+20)
//
// At the shipped weights (35/30/15/20) that is algebraically identical to
// WARDQ.RISK_SCORE, which is why the panel shows the stored score next to the
// simulated one for the top three: the simulator at rest is not an
// approximation, it is the same number.
const DEFAULT_WEIGHTS = { z: 35, breach: 30, slope: 15, complaint: 20 }

const FIELDS = [
  ['z', 'Anomaly (|z|)'],
  ['breach', 'Days in breach'],
  ['slope', '12-month slope'],
  ['complaint', 'Complaint density'],
]

function score(row, w) {
  const total = w.z + w.breach + w.slope + w.complaint
  if (!total) return null
  const sum = w.z * Number(row.Z_COMPONENT || 0)
    + w.breach * Number(row.BREACH_COMPONENT || 0)
    + w.slope * Number(row.SLOPE_COMPONENT || 0)
    + w.complaint * Number(row.COMPLAINT_COMP || 0)
  return (100 * sum) / total
}

export default function Simulator({ onOpenWard }) {
  const { data, loading, error } = useGet('/wards', [])
  const [weights, setWeights] = useState(DEFAULT_WEIGHTS)

  const rows = useMemo(() => data || [], [data])

  const baseline = useMemo(
    () => rows.slice().sort((a, b) => Number(b.RISK_SCORE) - Number(a.RISK_SCORE)),
    [rows],
  )

  const simulated = useMemo(() => {
    const scored = rows.map((row) => ({ row, sim: score(row, weights) }))
    scored.sort((a, b) => (b.sim ?? -1) - (a.sim ?? -1))
    return scored
  }, [rows, weights])

  const atDefaults = FIELDS.every(([key]) => weights[key] === DEFAULT_WEIGHTS[key])

  const drift = useMemo(() => {
    if (!rows.length) return null
    return rows.reduce((worst, row) => {
      const sim = score(row, DEFAULT_WEIGHTS)
      return Math.max(worst, Math.abs(sim - Number(row.RISK_SCORE || 0)))
    }, 0)
  }, [rows])

  const moved = useMemo(() => {
    const baseRank = new Map(baseline.map((row, i) => [row.WARD_ID, i]))
    return simulated.reduce((count, entry, i) => (baseRank.get(entry.row.WARD_ID) === i ? count : count + 1), 0)
  }, [baseline, simulated])

  if (error) return <div className="error">wards failed: {error}</div>
  if (loading) return <div className="loading">loading ward components…</div>

  const baseRank = new Map(baseline.map((row, i) => [row.WARD_ID, i]))

  return (
    <div>
      <div className="panel">
        <h2>What-if · risk weights</h2>
        <div className="legend-note">
          score = 100 · Σ(wᵢ · cᵢ) / Σwᵢ, the same four components the UDF consumes.
          At the shipped weights this reproduces RISK_SCORE exactly
          {drift != null && <> (largest difference across {rows.length} wards: {drift.toFixed(2)})</>}.
        </div>

        <div className="bars" style={{ marginTop: 14 }}>
          {FIELDS.map(([key, label]) => (
            <div className="bar-row" key={key} style={{ gridTemplateColumns: '132px 1fr 46px' }}>
              <span className="cap">{label}</span>
              <input
                type="range"
                min={0}
                max={60}
                step={1}
                value={weights[key]}
                aria-label={`${label} weight`}
                onChange={(e) => setWeights((w) => ({ ...w, [key]: Number(e.target.value) }))}
              />
              <span className="val">{weights[key]}</span>
            </div>
          ))}
        </div>

        <div className="controls">
          <button className="action" onClick={() => setWeights(DEFAULT_WEIGHTS)} disabled={atDefaults}>
            Reset to 35 / 30 / 15 / 20
          </button>
          <span className="legend-note" style={{ margin: 0 }}>
            {atDefaults ? 'shipped weights — identical to RISK_SCORE' : `${moved} ward${moved === 1 ? '' : 's'} changed position`}
          </span>
        </div>
      </div>

      <div className="panel">
        <h2>Re-ranked triage order</h2>
        <table>
          <thead>
            <tr>
              <th>#</th><th>Ward</th><th>Simulated</th><th>Stored RISK_SCORE</th>
              <th>Movement</th><th>Worst param</th><th />
            </tr>
          </thead>
          <tbody>
            {simulated.slice(0, 10).map((entry, i) => {
              const row = entry.row
              const before = baseRank.get(row.WARD_ID)
              const delta = before == null ? 0 : before - i
              return (
                <tr key={row.WARD_ID}>
                  <td className="mono">{i + 1}</td>
                  <td>#{row.WARD_ID} {row.WARD_NAME}</td>
                  <td className="mono" style={{ color: riskColor(entry.sim ?? 0), fontWeight: 700 }}>
                    {entry.sim == null ? '—' : fmt(entry.sim)}
                  </td>
                  <td className="mono">{i < 3 ? fmt(row.RISK_SCORE) : '·'}</td>
                  <td className="mono">
                    {delta === 0 ? '·' : delta > 0 ? `▲ ${delta}` : `▼ ${-delta}`}
                  </td>
                  <td>{row.WORST_PARAM}</td>
                  <td>
                    <button className="action" onClick={() => onOpenWard && onOpenWard(row.WARD_ID)}>
                      case file →
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <div className="legend-note">
          Top three rows show the stored value beside the simulated one: at shipped weights they agree,
          which is the point. Nothing here is written back — the simulator is browser state only.
        </div>
        <div style={{ marginTop: 10 }}>
          <SqlDrawer step="udf_risk" label="The UDF this reproduces" />
        </div>
      </div>
    </div>
  )
}
