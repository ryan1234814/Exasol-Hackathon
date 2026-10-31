import React, { useState } from 'react'
import { download, toCsv } from '../pages/_shared'
import { t } from '../i18n'

// One button for every table, so "export" behaves identically on all of them.
//
// This lives in a .jsx file on purpose: the project has no JSX loader for plain
// .js modules, so the two helpers it needs (`download`, `toCsv`) stay in
// _shared.js and only the component is here.
//
// Returns early with a disabled button when there is nothing to export — an
// export that silently writes an empty file reads as a bug.
export default function ExportCsvButton({ filename, rows, columns, lang = 'en', label }) {
  const [note, setNote] = useState('')
  const count = (rows || []).length

  function handleClick() {
    if (!count) return
    download(filename, toCsv(rows, columns), 'text/csv;charset=utf-8')
    setNote(`${count} rows`)
    // Clear the confirmation so the next click reads as a fresh action.
    setTimeout(() => setNote(''), 2500)
  }

  return (
    <span className="controls" style={{ display: 'inline-flex', gap: 8 }}>
      <button className="action" onClick={handleClick} disabled={!count}>
        {label || t(lang, 'export.csv')}
      </button>
      {!count && <span className="legend-note" style={{ margin: 0 }}>{t(lang, 'export.empty')}</span>}
      {note && <span className="legend-note" style={{ margin: 0 }}>{note}</span>}
    </span>
  )
}
