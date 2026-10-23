import React, { useEffect, useState } from 'react'
import { Line } from 'react-chartjs-2'
import { useGet, fmt } from './_shared'
import SqlDrawer from '../components/SqlDrawer'

const PARAMS = ['TURBIDITY', 'CHLORINE', 'COLIFORM', 'PH']

// Trend = one ward x one parameter, bucketed series. Chart.js is used ONLY here
// and on the leaderboard. Animation is off (see chartSetup) and the backend
// already caps points at MAX_TREND_POINTS, so the canvas stays cheap.
export default function Trend({ initialWard }) {
  const { data: wards } = useGet('/wards', [])
  const [wardId, setWardId] = useState(initialWard || 12)
  const [param, setParam] = useState('TURBIDITY')

  useEffect(() => { if (initialWard) setWardId(initialWard) }, [initialWard])

  const { data, loading, error } = useGet(`/wards/${wardId}/trend?param=${param}`, [wardId, param])

  const wardName = wards?.find((w) => w.WARD_ID === Number(wardId))?.WARD_NAME || `ward ${wardId}`
  const meta = data?.parameter || {}

  const chartData = data?.series?.length ? {
    labels: data.series.map((p) => p.BUCKET_START),
    datasets: [
      {
        label: `${meta.PARAM_NAME || param} (${meta.UNIT || ''})`,
        data: data.series.map((p) => p.DISPLAY_VALUE),
        borderColor: '#38bdf8',
        backgroundColor: 'rgba(56,189,248,0.12)',
        fill: true,
        tension: 0.25,
        pointRadius: 0,
      },
      {
        label: 'trailing avg',
        data: data.series.map((p) => p.TRAILING_AVG),
        borderColor: '#f59e0b',
        borderDash: [5, 4],
        pointRadius: 0,
        fill: false,
      },
    ],
  } : { labels: [], datasets: [] }

  const thresholdHi = meta.THRESHOLD_HI
  const options = {
    responsive: true,
    maintainAspectRatio: false,
    parsing: false,
    scales: {
      x: { ticks: { maxTicksLimit: 12, color: '#8ba0b3' }, grid: { color: '#26384a' } },
      y: { ticks: { color: '#8ba0b3' }, grid: { color: '#26384a' } },
    },
    plugins: {
      legend: { labels: { color: '#e6edf3' } },
      annotation: thresholdHi != null
        ? {} : {},
    },
  }

  return (
    <div className="panel">
      <h2>Trend · {wardName}</h2>
      <div className="controls">
        <label>
          Ward&nbsp;
          <select value={wardId} onChange={(e) => setWardId(Number(e.target.value))}>
            {(wards || []).map((w) => (
              <option key={w.WARD_ID} value={w.WARD_ID}>#{w.WARD_ID} {w.WARD_NAME}</option>
            ))}
          </select>
        </label>
        <div className="chips">
          {PARAMS.map((p) => (
            <span key={p} className={`chip${param === p ? ' active' : ''}`} onClick={() => setParam(p)}>{p}</span>
          ))}
        </div>
      </div>

      {error && <div className="error">trend failed: {error}</div>}
      {loading && <div className="loading">loading series…</div>}
      {data && (
        <>
          <div className="chart-wrap"><Line data={chartData} options={options} /></div>
          <div className="legend-note">
            {data.points} buckets × {data.bucket_days}d · query {data.query_ms} ms
            {thresholdHi != null && <> · breach threshold {meta.PARAM_NAME} {thresholdHi} {meta.UNIT}</>}
            {(meta.THRESHOLD_LO != null) && <> · min {meta.THRESHOLD_LO}</>}
          </div>
          {data.anomalies?.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <strong>Recent anomalies:</strong>
              <ul>
                {data.anomalies.map((a, i) => (
                  <li key={i}>
                    {a.PARAM_NAME}: z={fmt(a.Z_SCORE, 2)} · {a.BREACH_DAYS} breach days · run {a.CONSECUTIVE_RUN} · <span className={`sev-${a.SEVERITY}`}>{a.SEVERITY}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div style={{ marginTop: 10 }}>
            <SqlDrawer step="anomaly_window" />
          </div>
        </>
      )}
    </div>
  )
}
