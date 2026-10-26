import React, { useMemo, useState } from 'react'
import { useGet, fmt } from './_shared'
import SqlDrawer from '../components/SqlDrawer'

const VERDICTS = ['', 'instrument_suspect', 'lab_confirmed', 'consistent']

const VERDICT_NOTE = {
  instrument_suspect: 'the probe breached, the laboratory did not — check the instrument',
  lab_confirmed: 'the laboratory confirmed the breach — this is the water',
  consistent: 'sensor and lab agreed this month',
}

// "But the lab says compliant." This page exists because that sentence is the
// one that wastes a field visit, and the data to answer it was already in
// V_LAB_VS_SENSOR.
//
// One aggregate per page open over 288k rows, measured at 15 ms on this VM —
// that is why this reads the view directly instead of a materialized table.
export default function Disagreements({ wardId, onOpenWard }) {
  const [verdict, setVerdict] = useState('')
  const params = wardId ? `?ward_id=${wardId}&limit=200` : '?limit=200'
  const { data, loading, error } = useGet(`/disagreements${params}`, [wardId])

  const rows = useMemo(() => data?.rows || [], [data])
  const shown = verdict ? rows.filter((r) => r.VERDICT === verdict) : rows
  const suspects = rows.filter((r) => r.VERDICT === 'instrument_suspect')

  return (
    <div>
      <div className="panel">
        <h2>Sensor vs laboratory {data ? `· ${data.month}` : ''}</h2>
        <div className="legend-note">
          A sensor breach with no lab breach is an instrument problem, not a water problem.
          {' '}Verdicts are computed from the two breach counts, never from prose.
        </div>

        {suspects.length > 0 && (
          <div className="cards" style={{ marginTop: 12 }}>
            {suspects.slice(0, 4).map((r) => (
              <div className="card" key={`${r.WARD_ID}-${r.PARAM_CODE}`}>
                <h3>#{r.WARD_ID} {r.WARD_NAME} · {r.PARAM_CODE}</h3>
                <div className="big">{fmt(r.SENSOR_BREACHES, 0)}</div>
                <div className="meta">
                  probe breaches, {fmt(r.LAB_BREACHES, 0)} lab-confirmed
                  <br />
                  {fmt(r.CITIZEN_COMPLAINTS_THAT_MONTH, 0)} contamination complaints that month
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="controls" style={{ marginTop: 12 }}>
          <div className="chips">
            {VERDICTS.map((v) => (
              <span
                key={v || 'all'}
                role="button"
                tabIndex={0}
                className={`chip${verdict === v ? ' active' : ''}`}
                onClick={() => setVerdict(v)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setVerdict(v) }
                }}
              >
                {v ? v.replace('_', ' ') : 'ALL'}
              </span>
            ))}
          </div>
          {verdict && <span className="legend-note" style={{ margin: 0 }}>{VERDICT_NOTE[verdict]}</span>}
        </div>
      </div>

      <div className="panel">
        {error && <div className="error">disagreements failed: {error}</div>}
        {loading && <div className="loading">loading disagreements…</div>}
        {data && (
          <>
            <div className="scroll">
              <table>
                <thead>
                  <tr>
                    <th>Month</th><th>Ward</th><th>Param</th><th>Probe breaches</th>
                    <th>Lab breaches</th><th>Complaints</th><th>Verdict</th><th />
                  </tr>
                </thead>
                <tbody>
                  {shown.map((r) => (
                    <tr key={`${r.SAMPLE_MONTH}-${r.WARD_ID}-${r.PARAM_CODE}`}>
                      <td className="mono">{r.SAMPLE_MONTH}</td>
                      <td>#{r.WARD_ID} {r.WARD_NAME}</td>
                      <td>{r.PARAM_CODE}</td>
                      <td className="mono">{fmt(r.SENSOR_BREACHES, 0)}</td>
                      <td className="mono">{fmt(r.LAB_BREACHES, 0)}</td>
                      <td className="mono">{fmt(r.CITIZEN_COMPLAINTS_THAT_MONTH, 0)}</td>
                      <td><span className={`pill ${r.VERDICT}`}>{r.VERDICT.replace('_', ' ')}</span></td>
                      <td>
                        <button className="action" onClick={() => onOpenWard && onOpenWard(r.WARD_ID)}>
                          case file →
                        </button>
                      </td>
                    </tr>
                  ))}
                  {shown.length === 0 && (
                    <tr><td colSpan={8} className="loading">no rows with this verdict this month</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="legend-note">
              {shown.length} of {data.count} rows · {fmt(data.query_ms)} ms — one 288k-row aggregate per page open,
              measured on this VM
            </div>
            <div style={{ marginTop: 10 }}>
              <SqlDrawer step="sensor_vs_lab" label="How the verdict is computed" />
            </div>
          </>
        )}
      </div>
    </div>
  )
}
