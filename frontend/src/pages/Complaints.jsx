import React, { useState } from 'react'
import { useGet, fmt } from './_shared'
import SqlDrawer from '../components/SqlDrawer'

const CATS = ['', 'contamination', 'leakage', 'pressure', 'other']

export default function Complaints() {
  const [category, setCategory] = useState('')
  const [q, setQ] = useState('')
  const qs = `?limit=100${category ? `&category=${category}` : ''}${q ? `&q=${encodeURIComponent(q)}` : ''}`
  const { data, loading, error } = useGet(`/complaints${qs}`, [category, q])

  return (
    <div>
      <div className="panel">
        <h2>Complaint triage queue {data ? `· ${data.total}` : ''}</h2>
        <div className="controls">
          <input placeholder="search raw text…" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 240 }} />
          <div className="chips">
            {CATS.map((c) => (
              <span key={c || 'all'} className={`chip${category === c ? ' active' : ''}`} onClick={() => setCategory(c)}>{c || 'ALL'}</span>
            ))}
          </div>
        </div>

        {data?.category_mix?.length > 0 && (
          <div className="legend-note">
            mix: {data.category_mix.map((m) => `${m.CATEGORY} ${m.N} (${m.N_HIGH} high)`).join(' · ')}
          </div>
        )}
      </div>

      <div className="panel">
        {error && <div className="error">complaints failed: {error}</div>}
        {loading && <div className="loading">loading…</div>}
        {data && (
          <div className="scroll">
            <table>
              <thead>
                <tr><th>Sev</th><th>Ward</th><th>Category</th><th>Received</th><th>Raw text</th><th>Conf</th><th>Rule</th></tr>
              </thead>
              <tbody>
                {data.rows.map((r) => (
                  <tr key={r.COMPLAINT_ID}>
                    <td className={`sev-${r.SEVERITY}`}>{r.SEVERITY}</td>
                    <td>#{r.WARD_ID} {r.WARD_NAME}</td>
                    <td><span className="tag">{r.CATEGORY}</span></td>
                    <td className="mono">{r.RECEIVED_TS}</td>
                    <td>{r.RAW_TEXT}</td>
                    <td className="mono">{fmt(r.CONFIDENCE, 2)}</td>
                    <td className="mono">{r.RULE_VERSION}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div style={{ marginTop: 10 }}>
          <SqlDrawer step="complaint_category_mix" label="How categories were counted" />
        </div>
      </div>
    </div>
  )
}
