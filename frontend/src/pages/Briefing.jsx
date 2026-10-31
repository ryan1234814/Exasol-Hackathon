import React, { useState } from 'react'
import { useGet, fmt, download, toCsv } from './_shared'
import SqlDrawer from '../components/SqlDrawer'
import { LANGS, t } from '../i18n'

// The morning brief: three actions, each traceable to one saved query.
//
// The brief arrives as Markdown from `backend/brief.py`; Copy and Download use
// a client-side Blob so no file is ever written on the server (the whole build
// is SELECT-only). If the clipboard API is unavailable — plain http on a LAN
// address, which is exactly how this gets demoed — it falls back to a
// textarea + execCommand.
//
// The language chips do not translate anything locally: they re-request the
// brief with ?lang=, so the sentences come from the same templates the Atom
// feed uses and the two can never disagree. Only *chrome* (headings, buttons)
// is translated here, from i18n.js.
const ACTION_COLUMNS = ['N', 'KIND', 'WARD_ID', 'WARD_NAME', 'TITLE', 'DETAIL', 'SQL_STEP']

export default function Briefing({ onOpenWard, lang = 'en', onPickLang }) {
  const { data, loading, error } = useGet(`/brief?lang=${lang}`, [lang])
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

  function downloadCsv() {
    const body = toCsv(data?.ACTIONS || [], ACTION_COLUMNS)
    download(`morning-brief-${data?.MONTH || 'latest'}-${lang}.csv`, body, 'text/csv')
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
          <span className="legend-note" style={{ margin: 0 }}>{t(lang, 'brief.language')}</span>
          <div className="chips">
            {LANGS.map((option) => (
              <span
                key={option.id}
                role="button"
                tabIndex={0}
                className={`chip${lang === option.id ? ' active' : ''}`}
                onClick={() => onPickLang && onPickLang(option.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onPickLang && onPickLang(option.id) }
                }}
              >
                {option.label}
              </span>
            ))}
          </div>
        </div>

        <div className="controls">
          <button className="action" onClick={copyMarkdown}>{t(lang, 'brief.copy')}</button>
          <button
            className="action"
            onClick={() => download(`morning-brief-${data.MONTH}-${lang}.md`, data.MARKDOWN || '', 'text/markdown')}
          >
            {t(lang, 'brief.download')}
          </button>
          <button className="action" onClick={downloadCsv}>{t(lang, 'brief.downloadCsv')}</button>
          {copied && <span className="legend-note" style={{ margin: 0 }}>{copied}</span>}
        </div>

        <div className="legend-note">
          {data.NOTE}
          {data.DATA_AS_OF && <> · data as of {String(data.DATA_AS_OF).slice(0, 19)}</>}
          {data.query_ms != null && <> · {fmt(data.query_ms)} ms</>}
        </div>
      </div>

      <div className="panel">
        <h2>{data.HEADINGS?.ACTIONS || 'Do these three things today'}</h2>
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
          <h2>{data.HEADINGS?.WATCHLIST || 'Watchlist'}</h2>
          <table>
            <thead>
              <tr>
                <th>Rank</th>
                <th>Ward</th>
                <th>Risk</th>
                <th>Worst param</th>
                <th>High-severity complaints</th>
                <th />
              </tr>
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
          <summary>{data.HEADINGS?.MARKDOWN || 'The brief as markdown (what Copy and Download contain)'}</summary>
          <div className="drawer"><pre>{data.MARKDOWN}</pre></div>
        </details>
      </div>
    </div>
  )
}
