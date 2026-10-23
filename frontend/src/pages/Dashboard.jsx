import React from 'react'
import { useGet, fmt, riskColor } from './_shared'

// Dashboard = KPI strip + ward risk heatmap. The heatmap is a plain CSS grid of
// coloured cells (no chart lib) so it cannot crash on the small VM and needs no
// decimation. Clicking a cell hands the ward id up so App opens its Trend tab.
export default function Dashboard({ summary, onOpenTrend }) {
  const { data: wards, loading, error } = useGet('/wards', [])

  if (error) return <div className="error">wards failed: {error}</div>
  if (!summary) return <div className="loading">loading summary…</div>

  const c = summary.counts || {}
  const worst = summary.worst_ward || {}

  return (
    <div>
      <div className="kpis">
        <div className="kpi"><div className="n">{fmt(c.sample_rows, 0)}</div><div className="l">lab/sensor readings</div></div>
        <div className="kpi"><div className="n">{fmt(c.complaint_rows, 0)}</div><div className="l">complaints triaged</div></div>
        <div className="kpi"><div className="n">{fmt(c.wards, 0)}</div><div className="l">wards monitored</div></div>
        <div className="kpi"><div className="n">{fmt(c.high_severity_complaints, 0)}</div><div className="l">high-severity complaints</div></div>
        <div className="kpi worst">
          <div className="n">{fmt(worst.RISK_SCORE)}</div>
          <div className="l">worst ward: {worst.WARD_NAME} · {worst.WORST_PARAM}</div>
        </div>
      </div>

      <div className="panel">
        <h2>Ward risk heatmap — latest month ({summary.month})</h2>
        <div className="legend-note">Colour = RISK_SCORE (z-score · breach · slope · complaint density). Click a ward to open its trend.</div>
        {loading ? <div className="loading">loading wards…</div> : (
          <div className="heatmap">
            {(wards || []).map((w) => (
              <div
                key={w.WARD_ID}
                className="cell"
                style={{ background: riskColor(w.RISK_SCORE) }}
                onClick={() => onOpenTrend && onOpenTrend(w.WARD_ID)}
                title={`${w.WARD_NAME} — click for trend`}
              >
                <div className="id">#{w.WARD_ID}</div>
                <div className="name">{w.WARD_NAME}</div>
                <div className="risk">{fmt(w.RISK_SCORE)}</div>
                <div className="param">{w.WORST_PARAM}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
