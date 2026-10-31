import { useEffect, useState } from 'react'
import { getJSON } from '../api'

// Tiny shared loader so every page gets the same loading/error discipline.
// An empty path means "not ready yet": the page has nothing to ask for until an
// id arrives, and skipping the fetch is better than requesting /api/wards/null.
export function useGet(path, deps = []) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!path) {
      setData(null)
      setError(null)
      setLoading(false)
      return undefined
    }
    let alive = true
    setLoading(true)
    setError(null)
    getJSON(path)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(String(e.message || e)))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return { data, loading, error }
}

export function fmt(n, digits = 1) {
  if (n === null || n === undefined || n === '') return '—'
  const num = Number(n)
  if (Number.isNaN(num)) return String(n)
  return num.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: digits })
}

// Risk 0..100 -> a heat colour. Kept here so Dashboard and Leaderboard agree.
export function riskColor(risk) {
  const r = Math.max(0, Math.min(100, Number(risk) || 0))
  // green -> amber -> red
  const stops = [
    [34, 197, 94],   // ok
    [245, 158, 11],  // warn
    [239, 68, 68],   // bad
  ]
  const t = r / 100
  const seg = t < 0.5 ? 0 : 1
  const local = seg === 0 ? t / 0.5 : (t - 0.5) / 0.5
  const a = stops[seg], b = stops[seg + 1]
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * local))
  return `rgb(${c[0]},${c[1]},${c[2]})`
}

// Downloads happen in the browser, never on the server: the whole build is
// SELECT-only, so there is no endpoint that writes a file, and the page already
// holds every row it is about to export.
export function download(filename, text, type) {
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

// RFC 4180: quote every field, double the quotes inside. `columns` entries are
// either a key string or {key, label}; the label only affects the header row.
// Quoting everything unconditionally sidesteps the comma/semicolon/newline
// argument entirely, at the cost of a slightly larger file.
export function toCsv(rows, columns) {
  const cols = (columns || []).map((c) => (typeof c === 'string' ? { key: c, label: c } : c))
  const quote = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const lines = [cols.map((c) => quote(c.label)).join(',')]
  for (const row of rows || []) {
    lines.push(cols.map((c) => quote(row[c.key])).join(','))
  }
  return `${lines.join('\n')}\n`
}
