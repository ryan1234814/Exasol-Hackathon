import React, { useEffect, useState } from 'react'
import { getJSON, IS_MOCK } from './api'
import Dashboard from './pages/Dashboard'
import Trend from './pages/Trend'
import Anomalies from './pages/Anomalies'
import Complaints from './pages/Complaints'
import Leaderboard from './pages/Leaderboard'
import Ingest from './pages/Ingest'
import BenchmarkPage from './pages/BenchmarkPage'

const TABS = [
  ['dashboard', 'Dashboard', Dashboard],
  ['trend', 'Trend', Trend],
  ['anomalies', 'Anomalies', Anomalies],
  ['complaints', 'Complaints', Complaints],
  ['leaderboard', 'Leaderboard', Leaderboard],
  ['ingest', 'Ingest', Ingest],
  ['benchmark', 'Benchmark', BenchmarkPage],
]

export default function App() {
  const [tab, setTab] = useState('dashboard')
  const [ward, setWard] = useState(null) // ward id handed from Dashboard -> Trend
  const [summary, setSummary] = useState(null)
  const [health, setHealth] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    let alive = true
    getJSON('/summary').then((s) => alive && setSummary(s)).catch((e) => alive && setErr(String(e.message || e)))
    getJSON('/health').then((h) => alive && setHealth(h)).catch(() => alive && setHealth({ database: 'down' }))
    return () => { alive = false }
  }, [])

  // open a ward's trend from the heatmap without a router
  function openTrend(wardId) {
    setWard(wardId)
    setTab('trend')
  }

  const Active = TABS.find((t) => t[0] === tab)[2]
  const common = { summary, onOpenTrend: openTrend, initialWard: ward }

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Ward-Level Water Quality &amp; Complaint Triage</h1>
          <div className="sub">
            {summary ? `${summary.counts?.wards ?? 24} wards · month ${summary.month}` : 'loading…'}
            {health?.data_as_of ? ` · as of ${summary?.data_as_of?.LAST_RUN_TS}` : ''}
          </div>
        </div>
        <div>
          {IS_MOCK
            ? <span className="mock-badge" title="VITE_MOCK=1 — rendering from devMock, DB not required">mock data</span>
            : <span className="db-badge">db: {health?.database || '…'}</span>}
        </div>
      </header>

      {err && !IS_MOCK && <div className="error" style={{ margin: '10px 0' }}>backend unreachable: {err}</div>}

      <nav className="tabs">
        {TABS.map(([id, label]) => (
          <button key={id} className={`tab${tab === id ? ' active' : ''}`} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </nav>

      <main>
        <Active {...common} />
      </main>

      <footer className="footer">
        Exasol Personal · WARDQ schema · rule engine {summary?.data_as_of ? '' : ''}built for ExaThon India 2026.
      </footer>
    </div>
  )
}
