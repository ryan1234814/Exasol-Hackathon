import React, { useCallback, useEffect, useState } from 'react'
import { getJSON, IS_MOCK } from './api'
import { useRoute, navigate, goHome } from './router'
import { useTheme } from './theme'
import CommandPalette from './components/CommandPalette'
import Landing from './pages/Landing'
import Dashboard from './pages/Dashboard'
import WardDossier from './pages/WardDossier'
import Trend from './pages/Trend'
import Anomalies from './pages/Anomalies'
import Disagreements from './pages/Disagreements'
import Complaints from './pages/Complaints'
import Leaderboard from './pages/Leaderboard'
import Simulator from './pages/Simulator'
import Briefing from './pages/Briefing'
import Ingest from './pages/Ingest'
import BenchmarkPage from './pages/BenchmarkPage'

// Tab id, label, component. The ids are also the hash routes (#/ward/12), so
// they are part of the demo's URL surface — rename one and old links die.
const TABS = [
  ['dashboard', 'Dashboard', Dashboard],
  ['ward', 'Wards', WardDossier],
  ['trend', 'Trend', Trend],
  ['anomalies', 'Anomalies', Anomalies],
  ['disagreements', 'Disagreements', Disagreements],
  ['complaints', 'Complaints', Complaints],
  ['leaderboard', 'Leaderboard', Leaderboard],
  ['simulator', 'Simulator', Simulator],
  ['brief', 'Briefing', Briefing],
  ['ingest', 'Ingest', Ingest],
  ['benchmark', 'Benchmark', BenchmarkPage],
]

// Only the id and label travel to the palette; it must not need the components.
const PALETTE_TABS = TABS.map(([id, label]) => [id, label])

export default function App() {
  const route = useRoute()
  const [theme, toggleTheme] = useTheme()
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [summary, setSummary] = useState(null)
  const [health, setHealth] = useState(null)
  const [err, setErr] = useState(null)

  // Only hit the backend once the visitor has entered the app — the landing
  // page stays fully static so it renders even with the DB and API down.
  useEffect(() => {
    if (route.view !== 'app') return undefined
    let alive = true
    getJSON('/summary').then((s) => alive && setSummary(s)).catch((e) => alive && setErr(String(e.message || e)))
    getJSON('/health').then((h) => alive && setHealth(h)).catch(() => alive && setHealth({ database: 'down' }))
    return () => { alive = false }
  }, [route.view])

  useEffect(() => {
    function onKey(e) {
      if ((e.metaKey || e.ctrlKey) && String(e.key).toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const pick = useCallback((tab, wardId) => navigate(tab, wardId), [])
  const openWard = useCallback((id) => navigate('ward', id), [])
  const openTrend = useCallback((id) => navigate('trend', id), [])

  if (route.view === 'landing') {
    return <Landing onEnter={() => navigate('dashboard')} />
  }

  const Active = (TABS.find((t) => t[0] === route.tab) || TABS[0])[2]
  const common = {
    summary,
    wardId: route.wardId,
    onOpenWard: openWard,
    onOpenTrend: openTrend,
    onNavigate: pick,
  }

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Ward-Level Water Quality &amp; Complaint Triage</h1>
          <div className="sub">
            {summary ? `${summary.counts?.wards ?? 24} wards · month ${summary.month}` : 'loading…'}
            {summary?.data_as_of ? ` · as of ${summary.data_as_of.LAST_RUN_TS}` : ''}
          </div>
        </div>
        <div className="topbar__tools">
          <button className="action" onClick={goHome} title="Back to the landing page">← Home</button>
          <button
            className="action"
            onClick={() => setPaletteOpen(true)}
            title="Search everything (Ctrl/Cmd-K)"
          >
            Search <kbd>⌘K</kbd>
          </button>
          <button
            className="action"
            onClick={toggleTheme}
            title="Switch between the dark and light palettes"
          >
            {theme === 'dark' ? 'Light' : 'Dark'} theme
          </button>
          {IS_MOCK
            ? <span className="mock-badge" title="VITE_MOCK=1 — rendering from devMock, DB not required">mock data</span>
            : <span className="db-badge">db: {health?.database || '…'}</span>}
        </div>
      </header>

      {err && !IS_MOCK && <div className="error" style={{ margin: '10px 0' }}>backend unreachable: {err}</div>}

      <nav className="tabs">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            className={`tab${route.tab === id ? ' active' : ''}`}
            onClick={() => navigate(id)}
            aria-current={route.tab === id ? 'page' : undefined}
          >
            {label}
          </button>
        ))}
      </nav>

      <main>
        <Active {...common} />
      </main>

      <footer className="footer">
        Exasol Personal · WARDQ schema · rule engine · built for ExaThon India 2026.
      </footer>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onPick={pick}
        tabs={PALETTE_TABS}
      />
    </div>
  )
}
