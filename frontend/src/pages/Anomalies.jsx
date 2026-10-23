import React, { useState } from 'react'
import { useGet, fmt } from './_shared'
import SqlDrawer from '../components/SqlDrawer'

const PARAMS = ['', 'TURBIDITY', 'CHLORINE', 'COLIFORM', 'PH']

export default function Anomalies() {
  const [wardId, setWardId] = useState('')
  const [param, setParam] = useState('')
  const q = `?limit=200${wardId ? `&ward_id=${wardId}` : ''}${param ? `&param=${param}` : ''}`
  const { data, loading, error } = useGet(`/anomalies${q}`, [wardId, param])

  return (
    <div className="panel">
      <h2>Anomaly events {data ? `· ${data.count} in ${data.month}` : ''}</h2>
      <div className="controls">
        <input placeholder="ward id (blank = all)" value={wardId} onChange={(e) => setWardId(e.target.value.replace(/\D/g, ''))} style={{ width: 160 }} />
        <div className="chips">
          {PARAMS.map((p) => (
            <span key={p || 'all'} className={`chip${param === p ? ' active' : ''}`} onClick={() => setParam(p)}>{p || 'ALL'}</span>
          ))}
        </div>
      </div>

      {error && <div className="error">anomalies failed: {error}</div>}
      {loading && <div className="loading">loading…</div>}
      {data && (
        <>
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>Ward</th><th>Parameter</th><th>Z</th><th>Breach days</th>
                  <th>Consec. run</th><th>12m slope</th><th>Severity</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r, i) => (
                  <tr key={i}>
                    <td>#{r.WARD_ID} {r.WARD_NAME}{r.DOWNSTREAM ? ' ↓' : ''}</td>
                    <td>{r.PARAM_NAME}</td>
                    <td className="mono">{fmt(r.Z_SCORE, 2)}</td>
                    <td className="mono">{r.BREACH_DAYS}</td>
                    <td className="mono">{r.CONSECUTIVE_RUN}</td>
                    <td className="mono">{fmt(r.SLOPE_12M, 4)}</td>
                    <td className={`sev-${r.SEVERITY}`}>{r.SEVERITY}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="legend-note">↓ = downstream ward</div>
          <div style={{ marginTop: 10 }}>
            <SqlDrawer step={data.explanation_step || 'anomaly_window'} label="How this was computed" />
          </div>
        </>
      )}
    </div>
  )
}
