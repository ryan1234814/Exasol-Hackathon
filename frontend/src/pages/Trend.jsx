import React, { useEffect, useState } from 'react'
import { Line } from 'react-chartjs-2'
import { useGet, fmt } from './_shared'
import SqlDrawer from '../components/SqlDrawer'

const PARAMS = ['TURBIDITY', 'CHLORINE', 'COLIFORM', 'PH']

const STATUS_LABEL = {
  over_limit: 'over limit',
  deteriorating: 'deteriorating',
  improving: 'improving',
  stable: 'stable',
  unknown: 'no data',
}

function addDays(iso, days) {
  const date = new Date(`${iso}T00:00:00Z`)
  if (Number.isNaN(date.getTime())) return iso
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

// Trend = one ward x one parameter, bucketed series, plus the breach forecast.
//
// Chart.js is used ONLY here and on the leaderboard. Animation is off (see
// chartSetup) and the backend already caps points at MAX_TREND_POINTS.
//
// The 90-day projection is three appended points with the history padded by
// nulls and spanGaps:false, so the dashed line starts exactly where the solid
// one ends. `parsing` stays at its default: the datasets are primitive number
// arrays with a separate `labels` array, and parsing:false would resolve every
// point to NaN and collapse the axis.
export default function Trend({ wardId: routedWard, onOpenWard }) {
  const { data: wards } = useGet('/wards', [])
  const [wardId, setWardId] = useState(routedWard || 12)
  const [param, setParam] = useState('TURBIDITY')
  const [showProjection, setShowProjection] = useState(false)

  useEffect(() => { if (routedWard) setWardId(routedWard) }, [routedWard])

  const { data, loading, error } = useGet(`/wards/${wardId}/trend?param=${param}`, [wardId, param])
  const { data: forecast } = useGet(`/wards/${wardId}/forecast?param=${param}`, [wardId, param])

  const wardName = wards?.find((w) => w.WARD_ID === Number(wardId))?.WARD_NAME || `ward ${wardId}`
  const meta = data?.parameter || {}
  const item = forecast?.item || null

  const series = data?.series || []
  const projection = showProjection && item && item.CURRENT != null
    ? [30, 60, 90].map((days) => ({
      date: addDays(item.LAST_DATE || new Date().toISOString().slice(0, 10), days),
      value: days === 30 ? item.PROJECTED_30D
        : days === 90 ? item.PROJECTED_90D
          : (Number(item.PROJECTED_30D) + Number(item.PROJECTED_90D)) / 2,
    }))
    : []

  const chartData = series.length ? {
    labels: [...series.map((p) => p.BUCKET_START), ...projection.map((p) => p.date)],
    datasets: [
      {
        label: `${meta.PARAM_NAME || param} (${meta.UNIT || ''})`,
        data: [...series.map((p) => p.DISPLAY_VALUE), ...projection.map(() => null)],
        borderColor: '#38bdf8',
        backgroundColor: 'rgba(56,189,248,0.12)',
        fill: true,
        tension: 0.25,
        pointRadius: 0,
        spanGaps: false,
      },
      {
        label: 'trailing avg',
        data: [...series.map((p) => p.TRAILING_AVG), ...projection.map(() => null)],
        borderColor: '#f59e0b',
        borderDash: [5, 4],
        pointRadius: 0,
        fill: false,
        spanGaps: false,
      },
      ...(projection.length ? [{
        label: '90-day projection',
        data: [
          ...series.map((p, i) => (i === series.length - 1 ? p.DISPLAY_VALUE : null)),
          ...projection.map((p) => p.value),
        ],
        borderColor: '#a78bfa',
        borderDash: [2, 4],
        pointRadius: 2,
        pointBackgroundColor: '#a78bfa',
        fill: false,
        spanGaps: false,
      }] : []),
    ],
  } : { labels: [], datasets: [] }

  const thresholdHi = meta.THRESHOLD_HI
  // No `parsing: false` here: the datasets are primitive number arrays with a
  // separate `labels` array, which is exactly the shape Chart.js must parse.
  // Skipping parsing makes it treat each number as a pre-parsed {x,y} point, so
  // every value resolves to NaN and the axis silently collapses to 0..1.
  const options = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: { ticks: { maxTicksLimit: 12, color: '#8ba0b3' }, grid: { color: '#26384a' } },
      y: { ticks: { color: '#8ba0b3' }, grid: { color: '#26384a' } },
    },
    plugins: {
      legend: { labels: { color: '#e6edf3' } },
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
        <label style={{ marginLeft: 'auto' }}>
          <input
            type="checkbox"
            checked={showProjection}
            onChange={(e) => setShowProjection(e.target.checked)}
            disabled={!item || item.CURRENT == null}
          />
          {' '}show 90-day projection
        </label>
        {onOpenWard && (
          <button className="action" onClick={() => onOpenWard(wardId)}>case file →</button>
        )}
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

          {item && (
            <div className="cards" style={{ marginTop: 12 }}>
              <div className="card">
                <div className="controls" style={{ marginBottom: 6 }}>
                  <span className={`pill ${item.STATUS}`}>{STATUS_LABEL[item.STATUS] || item.STATUS}</span>
                </div>
                <h3>Status</h3>
                <div className="meta">{item.HEADLINE}</div>
              </div>
              <div className="card">
                <h3>Breach ETA</h3>
                <div className="big">
                  {/* The exact ETA is in the payload; past the horizon we print a
                      bound instead of a 1,400-day number nobody can act on. */}
                  {item.DAYS_TO_BREACH == null
                    ? '—'
                    : item.DAYS_TO_BREACH > (item.HORIZON_DAYS || 90)
                      ? `>${item.HORIZON_DAYS || 90}d`
                      : `${Math.round(item.DAYS_TO_BREACH)}d`}
                </div>
                <div className="meta">
                  {item.DAYS_TO_BREACH == null
                    ? 'no limit in the direction of travel'
                    : item.DAYS_TO_BREACH < 0
                      ? 'already past the limit'
                      : item.DAYS_TO_BREACH > (item.HORIZON_DAYS || 90)
                        ? `outside the ${item.HORIZON_DAYS || 90}-day horizon — the slope would reach it in ~${Math.round(item.DAYS_TO_BREACH)} days`
                        : `projected ${item.BREACH_DATE}`}
                </div>
              </div>
              <div className="card">
                <h3>90-day band</h3>
                <div className="big">
                  {item.BAND_LOW == null ? '—' : `${fmt(item.BAND_LOW, 2)}–${fmt(item.BAND_HIGH, 2)}`}
                </div>
                <div className="meta">
                  {item.BAND_LOW == null
                    ? `band needs 7 daily samples this month (have ${fmt(item.RECENT_N, 0)})`
                    : `±1.96σ of the last 30 daily means, widening as √(days/7)`}
                </div>
              </div>
              <div className="card">
                <h3>Confidence</h3>
                <div className="big">{item.CONFIDENCE}</div>
                <div className="meta">
                  {fmt(item.RECENT_N, 0)} samples · slope{' '}
                  {item.SLOPE_PER_DAY == null ? '—' : `${item.SLOPE_PER_DAY > 0 ? '+' : ''}${item.SLOPE_PER_DAY.toFixed(4)}`}/day
                  over 12 months
                </div>
              </div>
            </div>
          )}

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
            <SqlDrawer step="forecast_eta" label="How the ETA is derived" />
            {' '}
            <SqlDrawer step="anomaly_window" />
          </div>
        </>
      )}
    </div>
  )
}
