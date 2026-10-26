import React, { useMemo } from 'react'
import { useGet, fmt, riskColor } from './_shared'
import SqlDrawer from '../components/SqlDrawer'

// The ward case file. Everything on this page already existed as an endpoint —
// the dossier composes `/wards`, `/anomalies`, `/complaints`, `/heatmap` and
// `/wards/{id}/forecast` rather than hiding four independent failure states
// behind one mega-endpoint.
//
// Component bars carry the UDF's own weights (35/30/15/20) as labels, because
// the point of the page is that the number at the top is auditable.

const COMPONENTS = [
  ['Z_COMPONENT', 'Anomaly |z| / 4', 35],
  ['BREACH_COMPONENT', 'Days in breach', 30],
  ['SLOPE_COMPONENT', '12-month slope', 15],
  ['COMPLAINT_COMP', 'Complaint density / 5', 20],
]

const STATUS_LABEL = {
  over_limit: 'over limit',
  deteriorating: 'deteriorating',
  improving: 'improving',
  stable: 'stable',
  unknown: 'no data',
}

// A checklist in the same vocabulary, and therefore the same shape, as the
// brief's three actions: rank, crossing, instrument, complaints, or nothing.
function checklist(forecasts, complaints) {
  const items = []
  const over = forecasts.filter((f) => f.STATUS === 'over_limit')
  for (const f of over.slice(0, 2)) {
    items.push({
      kind: 'rank',
      text: `${f.PARAM_NAME} is already over the limit at ${fmt(f.CURRENT, 3)} ${f.UNIT || ''} `
        + `— treat it as an incident, not a forecast.`,
    })
  }
  const crossing = forecasts
    .filter((f) => f.STATUS === 'deteriorating' && f.DAYS_TO_BREACH != null)
    .sort((a, b) => a.DAYS_TO_BREACH - b.DAYS_TO_BREACH)[0]
  if (crossing) {
    items.push({
      kind: 'crossing',
      text: `Schedule a visit before ${crossing.BREACH_DATE || `~${Math.round(crossing.DAYS_TO_BREACH)} days`}: `
        + `${crossing.PARAM_NAME} is projected to cross its limit in about `
        + `${Math.round(crossing.DAYS_TO_BREACH)} days (${crossing.CONFIDENCE} confidence).`,
    })
  }
  const highSev = Number(complaints?.rows?.filter((r) => r.SEVERITY === 'high').length || 0)
  if (highSev > 0) {
    items.push({
      kind: 'complaints',
      text: `Clear the ${highSev} high-severity complaint${highSev === 1 ? '' : 's'} already in the queue `
        + 'before closing the ticket.',
    })
  }
  if (!items.length) {
    items.push({
      kind: 'none',
      text: 'No signal this month: no limit breach, no deteriorating parameter inside the horizon, '
        + 'and no high-severity complaint. That is a finding, not a missing feature.',
    })
  }
  return items
}

function DossierBody({ id, ward, forecast, anomalies, complaints, spark }) {
  const rows = forecast?.items || []
  const items = checklist(rows, complaints)
  const anomaliesRows = anomalies?.rows || []

  return (
    <>
      <div className="panel">
        <div className="controls" style={{ justifyContent: 'space-between' }}>
          <div>
            <h2 style={{ marginBottom: 2 }}>Ward {id} · {ward?.WARD_NAME}</h2>
            <div className="legend-note" style={{ margin: 0 }}>
              {ward?.CITY} · zone {ward?.CITY_ZONE} · population {fmt(ward?.POPULATION, 0)}
              {' '}· {fmt(ward?.CONNECTIONS, 0)} connections
              {ward?.DOWNSTREAM ? ' · downstream of the plant' : ' · upstream of the plant'}
            </div>
          </div>
          <div className="controls" style={{ margin: 0 }}>
            <button className="action" onClick={() => window.print()}>Print report</button>
            <span className="tag mono">#/ward/{id}</span>
          </div>
        </div>

        <div className="bars" style={{ marginTop: 14 }}>
          {COMPONENTS.map(([key, label, weight]) => {
            const value = Math.max(0, Math.min(1, Number(ward?.[key] || 0)))
            return (
              <div className="bar-row" key={key}>
                <span className="cap">{label} × {weight}%</span>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${value * 100}%`, background: riskColor(value * 100) }} />
                </div>
                <span className="val">{fmt(ward?.[key], 2)}</span>
              </div>
            )
          })}
        </div>
        <div className="legend-note">
          RISK_SCORE {fmt(ward?.RISK_SCORE)} · rank {ward?.RANK_IN_MONTH ?? '—'} of the month · worst parameter{' '}
          {ward?.WORST_PARAM || '—'}. Weights are the UDF's, so the bars multiply out to the score.
        </div>
      </div>

      <div className="panel">
        <h2>Risk, last {spark.length} months</h2>
        {spark.length === 0 && <div className="loading">no monthly history for this ward</div>}
        {spark.length > 0 && (
          <>
            <div className="spark" role="img" aria-label="Monthly risk score for this ward">
              {spark.map((point) => (
                <div
                  key={point.SAMPLE_MONTH}
                  style={{ height: `${Math.max(3, Number(point.RISK_SCORE) || 0)}%`, background: riskColor(point.RISK_SCORE) }}
                  title={`${point.SAMPLE_MONTH}: ${fmt(point.RISK_SCORE)}`}
                />
              ))}
            </div>
            <div className="spark-axis">
              <span>{spark[0].SAMPLE_MONTH}</span>
              <span>{spark[spark.length - 1].SAMPLE_MONTH}</span>
            </div>
          </>
        )}
      </div>

      <div className="panel">
        <h2>Breach forecast</h2>
        <div className="cards">
          {rows.map((f) => (
            <div className="card" key={f.PARAM_CODE}>
              <div className="controls" style={{ marginBottom: 6 }}>
                <span className={`pill ${f.STATUS}`}>{STATUS_LABEL[f.STATUS] || f.STATUS}</span>
                <span className="legend-note" style={{ margin: 0 }}>{f.CONFIDENCE} confidence</span>
              </div>
              <h3>{f.PARAM_NAME} ({f.UNIT})</h3>
              <div className="big">{fmt(f.CURRENT, 3)}</div>
              <div className="meta">
                trend {f.SLOPE_PER_DAY == null ? '—' : `${f.SLOPE_PER_DAY > 0 ? '+' : ''}${f.SLOPE_PER_DAY.toFixed(4)}`}/day
                <br />
                {f.DAYS_TO_BREACH == null
                  ? 'no limit in the direction of travel'
                  : f.DAYS_TO_BREACH < 0
                    ? 'already past the limit'
                    : f.DAYS_TO_BREACH > (f.HORIZON_DAYS || 90)
                      ? `outside the ${f.HORIZON_DAYS || 90}-day horizon (slope reaches it in ~${Math.round(f.DAYS_TO_BREACH)} days)`
                      : `crosses in ~${Math.round(f.DAYS_TO_BREACH)} days (${f.BREACH_DATE})`}
                <br />
                {f.BAND_LOW == null
                  ? 'band unavailable — too few samples this month'
                  : `±${fmt((f.BAND_HIGH - f.CURRENT) / 2, 3)} at 90 days (${fmt(f.BAND_LOW, 3)}–${fmt(f.BAND_HIGH, 3)})`}
              </div>
              <div className="meta" style={{ marginTop: 6 }}>{f.HEADLINE}</div>
            </div>
          ))}
        </div>
        {rows.length === 0 && <div className="loading">no forecast rows — run db/45_forecast_view.sql</div>}
        <div className="legend-note">{forecast?.method}</div>
        <div style={{ marginTop: 10 }}>
          <SqlDrawer step="forecast_eta" label="The ETA arithmetic" />
        </div>
      </div>

      <div className="grid-2">
        <div className="panel">
          <h2>Current anomalies</h2>
          {anomaliesRows.length === 0 && <div className="loading">no anomaly events this month</div>}
          {anomaliesRows.length > 0 && (
            <table>
              <thead>
                <tr><th>Param</th><th>z</th><th>Breach days</th><th>Run</th><th>Slope</th><th>Severity</th></tr>
              </thead>
              <tbody>
                {anomaliesRows.map((a, i) => (
                  <tr key={`${a.PARAM_CODE}-${i}`}>
                    <td>{a.PARAM_CODE}</td>
                    <td className="mono">{fmt(a.Z_SCORE, 2)}</td>
                    <td className="mono">{a.BREACH_DAYS}</td>
                    <td className="mono">{a.CONSECUTIVE_RUN}</td>
                    <td className="mono">{fmt(a.SLOPE_12M, 4)}</td>
                    <td className={`sev-${a.SEVERITY}`}>{a.SEVERITY}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="panel">
          <h2>Recent complaints</h2>
          {(complaints?.rows || []).length === 0 && <div className="loading">no complaints on record</div>}
          {(complaints?.rows || []).map((c) => (
            <div key={c.COMPLAINT_ID} style={{ padding: '6px 0', borderBottom: '1px solid var(--line)' }}>
              <div>
                <span className={`sev-${c.SEVERITY}`}>{c.SEVERITY}</span>
                {' '}<span className="tag">{c.CATEGORY}</span>
                {' '}<span className="legend-note" style={{ margin: 0 }}>{c.RECEIVED_TS}</span>
              </div>
              <div style={{ marginTop: 2 }}>{c.RAW_TEXT}</div>
              {c.RULE_EVIDENCE && (
                <div className="legend-note" style={{ margin: 0 }}>rule evidence: {c.RULE_EVIDENCE}</div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <h2>Do next</h2>
        <ol style={{ margin: 0, paddingLeft: 20 }}>
          {items.map((item, i) => (
            <li key={i} style={{ marginBottom: 6 }}>
              <span className={`pill ${item.kind}`}>{item.kind === 'none' ? 'no signal' : item.kind}</span>{' '}
              {item.text}
            </li>
          ))}
        </ol>
      </div>
    </>
  )
}

export default function WardDossier({ wardId, onOpenWard, onOpenTrend, summary }) {
  const { data: wards, loading: wardsLoading, error: wardsError } = useGet('/wards', [])
  const { data: heat } = useGet('/heatmap?months=13', [])

  // No id in the hash means "worst ward", which is what the dashboard's first
  // tile is pointing at anyway — and `/wards` is already risk-ordered.
  const id = wardId || (wards && wards.length ? wards[0].WARD_ID : null)
  const ward = useMemo(
    () => (wards || []).find((w) => w.WARD_ID === Number(id)) || null,
    [wards, id],
  )

  // These three only mount once the id is known, so no page ever fetches
  // /wards/null/forecast while the ward list is still in flight.
  const ready = id != null
  const forecast = useGet(ready ? `/wards/${id}/forecast` : '', [id])
  const anomalies = useGet(ready ? `/anomalies?ward_id=${id}&limit=20` : '', [id])
  const complaints = useGet(ready ? `/complaints?ward_id=${id}&limit=5` : '', [id])

  const spark = useMemo(() => {
    const cells = (heat?.cells || []).filter((c) => c.WARD_ID === Number(id))
    return cells.slice().sort((a, b) => String(a.SAMPLE_MONTH).localeCompare(String(b.SAMPLE_MONTH)))
  }, [heat, id])

  if (wardsError) return <div className="error">wards failed: {wardsError}</div>
  if (wardsLoading || !wards) return <div className="loading">loading ward list…</div>

  return (
    <div>
      <div className="panel">
        <div className="controls">
          <label>
            Ward&nbsp;
            <select value={id ?? ''} onChange={(e) => onOpenWard && onOpenWard(Number(e.target.value))}>
              {wards.map((w) => (
                <option key={w.WARD_ID} value={w.WARD_ID}>
                  #{w.WARD_ID} {w.WARD_NAME} · {fmt(w.RISK_SCORE)}
                </option>
              ))}
            </select>
          </label>
          <button className="action" onClick={() => onOpenTrend && onOpenTrend(id)}>
            open the trend chart →
          </button>
          {summary?.month && <span className="legend-note" style={{ margin: 0 }}>month {summary.month}</span>}
        </div>
      </div>

      {!ready && <div className="loading">no wards to show</div>}
      {ready && (
        <DossierBody
          id={id}
          ward={ward}
          forecast={forecast.data}
          anomalies={anomalies.data}
          complaints={complaints.data}
          spark={spark}
        />
      )}
    </div>
  )
}
