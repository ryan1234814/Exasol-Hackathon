import React, { useState } from 'react'
import { useGet, fmt } from './_shared'
import SqlDrawer from '../components/SqlDrawer'

// The morning brief: three actions, each traceable to one saved query.
//
// The brief arrives as Markdown from `backend/brief.py`; Copy and Download use
// a client-side Blob so no file is ever written on the server (the whole build
// is SELECT-only). If the clipboard API is unavailable — plain http on a LAN
// address, which is exactly how this gets demoed — it falls back to a
// textarea + execCommand.
export default function Briefing({ onOpenWard }) {
  const { data, loading, error } = useGet('/brief', [])
  const [copied, setCopied] = useState('')

  async function copyMarkdown() {
    const text = data?.MARKDOWN || ''
    try {
      if (!navigator.clipboard?.writeText) throw new Error('no clipboard api')
      await navigator.clipboard.writeText(text)
      setCopied('copied to clipboard')
      return
    } catch {
      const area = document.createElement('textarea')
      area.value = text
      area.setAttribute('readonly', '')
      area.style.position = 'fixed'
      area.style.opacity = '0'
      document.body.appendChild(area)
      area.select()
      let ok = false
      try { ok = document.execCommand('copy') } catch { ok = false }
      area.remove()
      setCopied(ok ? 'copied to clipboard' : 'copy blocked — open the markdown below')
    }
  }

  function download(filename, text, type) {
    const blob = new Blob([text], { type })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    // Revoking immediately cancels the download in some browsers.
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  function downloadCsv() {
    const head = ['N', 'KIND', 'WARD_ID', 'WARD_NAME', 'TITLE', 'DETAIL', 'SQL_STEP']
    const quote = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`
    const lines = [head.join(',')]
    for (const a of data?.ACTIONS || []) {
      lines.push(head.map((key) => quote(a[key])).join(','))
    }
    download(`morning-brief-${data?.MONTH || 'latest'}.csv`, `${lines.join('\n')}\n`, 'text/csv')
  }

  if (error) return <div className="error">brief failed: {error}</div>
  if (loading) return <div className="loading">composing the brief…</div>
  if (!data) return <div className="loading">no brief</div>

  return (
    <div>
      <div className="panel">
        <h2>Morning brief · {data.MONTH}</h2>
        <p style={{ marginTop: 0 }}>{data.HEADLINE}</p>

        <div className="controls">
          <button className="action" onClick={copyMarkdown}>Copy markdown</button>
          <button
            className="action"
            onClick={() => download(`morning-brief-${data.MONTH}.md`, data.MARKDOWN || '', 'text/markdown')}
          >
            Download .md
          </button>
          <button className="action" onClick={downloadCsv}>Download .csv (actions)</button>
          {copied && <span className="legend-note" style={{ margin: 0 }}>{copied}</span>}
        </div>

        <div className="legend-note">
          {data.NOTE}
          {data.DATA_AS_OF && <> · data as of {String(data.DATA_AS_OF).slice(0, 19)}</>}
          {data.query_ms != null && <> · {fmt(data.query_ms)} ms</>}
        </div>
      </div>

      <div className="panel">
        <h2>Do these three things today</h2>
        <div className="cards">
          {(data.ACTIONS || []).map((action) => (
            <div className="card" key={action.N}>
              <div className="controls" style={{ marginBottom: 6 }}>
                <span className={`pill ${action.KIND}`}>{action.KIND === 'none' ? 'no action' : action.KIND}</span>
                <span className="legend-note" style={{ margin: 0 }}>#{action.N}</span>
              </div>
              <h3>{action.TITLE}</h3>
              <div className="meta">{action.DETAIL}</div>
              {action.WARD_ID && onOpenWard && (
                <button
                  className="action"
                  style={{ marginTop: 8 }}
                  onClick={() => onOpenWard(action.WARD_ID)}
                >
                  case file →
                </button>
              )}
              <div style={{ marginTop: 8 }}>
                <SqlDrawer step={action.SQL_STEP} label="Why this" />
              </div>
            </div>
          ))}
        </div>
      </div>

      {(data.WATCHLIST || []).length > 0 && (
        <div className="panel">
          <h2>Watchlist</h2>
          <table>
            <thead>
              <tr><th>Rank</th><th>Ward</th><th>Risk</th><th>Worst param</th><th>High-severity complaints</th><th /></tr>
            </thead>
            <tbody>
              {data.WATCHLIST.map((row) => (
                <tr key={row.WARD_ID}>
                  <td className="mono">{row.RANK_IN_MONTH}</td>
                  <td>#{row.WARD_ID} {row.WARD_NAME}</td>
                  <td className="mono">{fmt(row.RISK_SCORE)}</td>
                  <td>{row.WORST_PARAM}</td>
                  <td className="mono sev-high">{fmt(row.N_HIGH_SEV, 0)}</td>
                  <td>
                    <button className="action" onClick={() => onOpenWard && onOpenWard(row.WARD_ID)}>
                      case file →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="panel">
        <details>
          <summary>The brief as markdown (what Copy and Download contain)</summary>
          <div className="drawer"><pre>{data.MARKDOWN}</pre></div>
        </details>
      </div>
    </div>
  )
}
