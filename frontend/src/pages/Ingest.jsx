import React, { useRef, useState } from 'react'
import { classify, postForm, IS_MOCK } from '../api'
import { fmt } from './_shared'

// Ingest = paste/classify a single complaint (works in mock mode via the JS
// mirror) + drop a chat export for bulk preview (needs the live backend).
export default function Ingest() {
  const [text, setText] = useState('')
  const [out, setOut] = useState(null)
  const [busy, setBusy] = useState(false)
  const [upload, setUpload] = useState(null)
  const [over, setOver] = useState(false)
  const fileRef = useRef(null)

  async function run() {
    if (!text.trim()) return
    setBusy(true)
    try { setOut(await classify(text)) } catch (e) { setOut({ error: String(e.message || e) }) }
    finally { setBusy(false) }
  }

  async function sendFiles(files) {
    if (!files?.length) return
    if (IS_MOCK) { setUpload({ note: 'bulk upload needs the live backend (mock mode classifies single text only)' }); return }
    const fd = new FormData()
    for (const f of files) fd.append('file', f)
    setBusy(true)
    try { const r = await postForm('/ingest/chat', fd); setUpload(r) }
    catch (e) { setUpload({ error: String(e.message || e) }) }
    finally { setBusy(false) }
  }

  return (
    <div>
      <div className="panel">
        <h2>Classify a complaint</h2>
        <div className="controls" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
          <textarea
            rows={3}
            placeholder="e.g. Tap se ganda paani aur badbu aa rahi hai, bacchon ko pet kharab"
            value={text}
            onChange={(e) => setText(e.target.value)}
            style={{ width: '100%', background: 'var(--panel-2)', color: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 8, padding: 8 }}
          />
          <div><button className="action" onClick={run} disabled={busy}>{busy ? '…' : 'Classify'}</button></div>
        </div>
        {out && (
          <div className="classify-out">
            {out.error ? <span className="error">{out.error}</span> : (
              <>
                <span className="tag">{out.category}</span>{' '}
                <span className={`sev-${out.severity}`}>{out.severity}</span>{' '}
                confidence <span className="mono">{fmt(out.confidence, 2)}</span> · rule <span className="mono">{out.rule_version}</span>
                {out.evidence && <div className="legend-note">evidence: {out.evidence}</div>}
              </>
            )}
          </div>
        )}
      </div>

      <div className="panel">
        <h2>Bulk upload (WhatsApp / CSV export)</h2>
        <div
          className={`drop${over ? ' over' : ''}`}
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setOver(true) }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); sendFiles(e.dataTransfer.files) }}
        >
          {IS_MOCK ? 'mock mode — drop disabled (single classify still works above)' : 'drop a .csv / .txt here, or click to choose'}
          <input ref={fileRef} type="file" multiple hidden onChange={(e) => sendFiles(e.target.files)} />
        </div>
        {upload && (
          <div className="classify-out">
            {upload.error ? <span className="error">{upload.error}</span>
              : upload.note ? <span className="legend-note">{upload.note}</span>
              : <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{JSON.stringify(upload, null, 2)}</pre>}
          </div>
        )}
      </div>
    </div>
  )
}
