import React, { useState } from 'react'
import { getJSON } from '../api'

// Shows the exact SQL that produced a number, straight from the repo file via
// GET /api/sql/{step}. Fetched on first open so the drawer never blocks render.
export default function SqlDrawer({ step, label = 'Show the SQL' }) {
  const [open, setOpen] = useState(false)
  const [sql, setSql] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  async function toggle() {
    const next = !open
    setOpen(next)
    if (next && sql === null && !busy) {
      setBusy(true)
      try {
        const d = await getJSON(`/sql/${step}`)
        setSql(d)
      } catch (e) {
        setErr(String(e.message || e))
      } finally {
        setBusy(false)
      }
    }
  }

  return (
    <div>
      <button className="action" onClick={toggle}>
        {open ? 'Hide' : label} · {step}
      </button>
      {open && (
        <div className="drawer">
          <div className="file">{sql?.file || `db/sql/${step}.sql`}</div>
          {busy && <div className="loading">loading…</div>}
          {err && <div className="error">{err}</div>}
          {sql && <pre>{sql.sql}</pre>}
        </div>
      )}
    </div>
  )
}
