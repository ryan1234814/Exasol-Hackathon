// Ctrl/Cmd-K palette. Hand-written for the same reason as the router: it is one
// modal, one filtered list and three keys, and a dependency would have to be
// added to the bundle and explained on stage.
//
// It lists the eleven tabs immediately and the wards as soon as `/wards`
// resolves, so the same keystroke gets you to "the trend chart" or to
// "ward 12" without hunting through the tab strip.
import React, { useEffect, useMemo, useRef, useState } from 'react'
import { getJSON } from '../api'

// Enough for all eleven tabs plus the first few matching wards. The list scrolls
// (`.palette__list` has a max-height), so this is a sanity cap, not a page size:
// at 9 the last two tabs were unreachable without typing, which is the one thing
// a command palette must never do.
const MAX_ITEMS = 14

export default function CommandPalette({ open, onClose, onPick, tabs }) {
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const [wards, setWards] = useState([])
  const inputRef = useRef(null)

  // Reset on open, and focus on the next tick so the overlay is painted first.
  useEffect(() => {
    if (!open) return undefined
    setQuery('')
    setCursor(0)
    const timer = setTimeout(() => inputRef.current?.focus(), 0)
    return () => clearTimeout(timer)
  }, [open])

  // One lazy fetch, cached for the session: the ward list never changes here.
  useEffect(() => {
    if (!open || wards.length) return undefined
    let alive = true
    getJSON('/wards')
      .then((rows) => { if (alive) setWards(rows || []) })
      .catch(() => { /* palette stays tab-only if the DB is down */ })
    return () => { alive = false }
  }, [open, wards.length])

  const items = useMemo(() => {
    const needle = query.trim().toLowerCase()
    const tabItems = tabs.map(([id, label]) => ({
      key: `tab:${id}`,
      label,
      hint: 'go to tab',
      run: () => onPick(id, null),
    }))
    const wardItems = wards.map((w) => ({
      key: `ward:${w.WARD_ID}`,
      label: `#${w.WARD_ID} ${w.WARD_NAME}`,
      hint: 'ward case file',
      run: () => onPick('ward', w.WARD_ID),
    }))
    const all = needle
      ? [...wardItems, ...tabItems].filter((i) => i.label.toLowerCase().includes(needle))
      : tabItems
    return all.slice(0, MAX_ITEMS)
  }, [query, tabs, wards, onPick])

  if (!open) return null

  function onKeyDown(e) {
    if (e.key === 'Escape') {
      e.preventDefault()
      onClose()
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setCursor((c) => (items.length ? (c + 1) % items.length : 0))
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      setCursor((c) => (items.length ? (c - 1 + items.length) % items.length : 0))
      return
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      const chosen = items[cursor] || items[0]
      if (chosen) {
        chosen.run()
        onClose()
      }
    }
  }

  return (
    <div className="palette-scrim" onMouseDown={onClose} role="presentation">
      <div
        className="palette"
        role="dialog"
        aria-label="Command palette"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          className="palette__input"
          placeholder="Jump to a tab, or type a ward name…"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setCursor(0) }}
          onKeyDown={onKeyDown}
          aria-label="Search tabs and wards"
        />
        <ul className="palette__list">
          {items.length === 0 && <li className="palette__empty">no match</li>}
          {items.map((item, i) => (
            <li key={item.key}>
              <button
                type="button"
                className={`palette__item${i === cursor ? ' active' : ''}`}
                onMouseEnter={() => setCursor(i)}
                onClick={() => { item.run(); onClose() }}
              >
                <span>{item.label}</span>
                <span className="palette__hint">{item.hint}</span>
              </button>
            </li>
          ))}
        </ul>
        <div className="palette__foot">↑↓ to move · enter to open · esc to close</div>
      </div>
    </div>
  )
}
