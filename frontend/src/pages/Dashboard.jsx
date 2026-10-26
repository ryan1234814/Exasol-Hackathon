import React, { useEffect, useMemo, useState } from 'react'
import { useGet, fmt, riskColor } from './_shared'

const REPLAY_MS = 900

// Dashboard = KPI strip + ward risk heatmap + the month replay.
//
// The heatmap is a plain CSS grid of coloured cells (no chart lib) so it cannot
// crash on the small VM. The whole 13-month matrix arrives in one payload, so
// the replay slider animates with *no network at all* — re-fetching per tick
// would put 13 round trips on a single-lock database connection.
//
// Clicking a cell opens that ward's case file; the case file links onward to
// the trend chart, so the drill-down is two deliberate steps rather than one
// ambiguous one.
export default function Dashboard({ summary, onOpenWard }) {
  const { data, loading, error } = useGet('/heatmap?months=13', [])
  const months = useMemo(() => data?.months || [], [data])
  const [idx, setIdx] = useState(null) // null until the payload lands
  const [playing, setPlaying] = useState(false)

  // Start on the newest month, which is what the demo claims to show.
  useEffect(() => {
    if (idx === null && months.length) setIdx(months.length - 1)
  }, [idx, months.length])

  // Replay: a 900 ms timer re-armed on each step. A timeout chain (rather than
  // setInterval) means unmount and pause both cancel it with one line, and the
  // slider cannot drift past the newest month.
  useEffect(() => {
    if (!playing || idx === null) return undefined
    if (idx >= months.length - 1) { setPlaying(false); return undefined }
    const timer = setTimeout(() => setIdx((i) => (i === null ? 0 : i + 1)), REPLAY_MS)
    return () => clearTimeout(timer)
  }, [playing, idx, months.length])

  const wardsById = useMemo(() => {
    const map = new Map()
    for (const w of data?.wards || []) map.set(w.WARD_ID, w)
    return map
  }, [data])

  const cellsByMonth = useMemo(() => {
    const map = new Map()
    for (const c of data?.cells || []) {
      if (!map.has(c.SAMPLE_MONTH)) map.set(c.SAMPLE_MONTH, [])
      map.get(c.SAMPLE_MONTH).push(c)
    }
    return map
  }, [data])

  if (error) return <div className="error">heatmap failed: {error}</div>
  if (!summary) return <div className="loading">loading summary…</div>

  const c = summary.counts || {}
  const worst = summary.worst_ward || {}
  const current = idx === null ? null : months[idx]
  const isLive = current != null && current === months[months.length - 1]
  const cells = (cellsByMonth.get(current) || [])
    .slice()
    .sort((a, b) => Number(b.RISK_SCORE) - Number(a.RISK_SCORE))

  function togglePlay() {
    if (!months.length) return
    if (playing) { setPlaying(false); return }
    if (idx === null || idx >= months.length - 1) setIdx(0)
    setPlaying(true)
  }

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
        <h2>
          Ward risk heatmap · {current || '…'}
          {isLive && <> <span className="live-badge">live</span></>}
        </h2>

        <div className="replay" style={{ marginBottom: 12 }}>
          <button className="action" onClick={togglePlay} disabled={!months.length}>
            {playing ? '⏸ Pause' : '▶ Replay'}
          </button>
          <input
            type="range"
            min={0}
            max={Math.max(0, months.length - 1)}
            step={1}
            value={idx ?? 0}
            onChange={(e) => { setPlaying(false); setIdx(Number(e.target.value)) }}
            aria-label="Month to display"
            disabled={!months.length}
          />
          <span className="month">{current || '—'}</span>
          <span className="legend-note" style={{ margin: 0 }}>
            {idx === null ? '' : `${idx + 1} / ${months.length} months`}
          </span>
        </div>

        <div className="legend-note">
          Colour = RISK_SCORE (z-score · breach · slope · complaint density). Click a ward to open its case file.
        </div>

        {loading && <div className="loading">loading heatmap…</div>}
        {data && (
          <div className="heatmap">
            {cells.map((cell) => {
              const ward = wardsById.get(cell.WARD_ID) || {}
              return (
                <div
                  key={cell.WARD_ID}
                  className="cell"
                  role="button"
                  tabIndex={0}
                  style={{ background: riskColor(cell.RISK_SCORE) }}
                  onClick={() => onOpenWard && onOpenWard(cell.WARD_ID)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      onOpenWard && onOpenWard(cell.WARD_ID)
                    }
                  }}
                  title={`${ward.WARD_NAME || `ward ${cell.WARD_ID}`} — open the case file`}
                >
                  <div className="id">#{cell.WARD_ID}</div>
                  <div className="name">{ward.WARD_NAME || `Ward ${cell.WARD_ID}`}</div>
                  <div className="risk">{fmt(cell.RISK_SCORE)}</div>
                  <div className="param">{cell.WORST_PARAM}</div>
                </div>
              )
            })}
          </div>
        )}

        {data && (
          <div className="legend-note">
            {data.cells?.length ?? 0} cells across {data.months_returned ?? months.length} months in one prefetched
            payload · query {data.query_ms} ms
          </div>
        )}
      </div>
    </div>
  )
}
