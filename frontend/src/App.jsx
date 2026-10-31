import React, { useCallback, useEffect, useState } from 'react'
import { getJSON, IS_MOCK } from './api'
import { useRoute, navigate, goHome } from './router'
import { useTheme } from './theme'
import { LANGS, t, useLang } from './i18n'
import { TABS_META } from './tabs'
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
import Trust from './pages/Trust'
import Ingest from './pages/Ingest'
import BenchmarkPage from './pages/BenchmarkPage'

// The ids and the order come from tabs.js, which router.js also reads — one
// registry, so a new tab cannot be added to only half the app. This map holds
// only the components, keyed by the same ids.
const COMPONENTS = {
  dashboard: Dashboard,
  ward: WardDossier,
  trend: Trend,
  anomalies: Anomalies,
  disagreements: Disagreements,
  complaints: Complaints,
  leaderboard: Leaderboard,
  simulator: Simulator,
  brief: Briefing,
  trust: Trust,
  ingest: Ingest,
  benchmark: BenchmarkPage,
}

// Offline is worth a badge rather than silence: a stale cached view and a hung
// request look identical to someone standing in front of the screen.
function useOnline() {
  const [online, setOnline] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine))
  useEffect(() => {
    const up = () => setOnline(true)
    const down = () => setOnline(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    return () => {
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
    }
  }, [])
  return online
}

export default function App() {
  const route = useRoute()
  const [theme, toggleTheme] = useTheme()
  const [lang, pickLang] = useLang()
  const online = useOnline()
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

  // Labels are resolved once per language change, so the palette and the tab
  // strip cannot disagree.
  const tabs = TABS_META.map((meta) => ({ ...meta, label: t(lang, meta.labelKey) }))

  if (route.view === 'landing') {
    return <Landing onEnter={() => navigate('dashboard')} />
  }

  const Active = COMPONENTS[route.tab] || COMPONENTS.dashboard
  const common = {
    summary,
    lang,
    onPickLang: pickLang,
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
          <button className="action" onClick={goHome} title={t(lang, 'topbar.homeTitle')}>
            {t(lang, 'topbar.home')}
          </button>
          <button
            className="action"
            onClick={() => setPaletteOpen(true)}
            title={t(lang, 'topbar.searchTitle')}
          >
            {t(lang, 'topbar.search')} <kbd>⌘K</kbd>
          </button>
          <button
            className="action"
            onClick={toggleTheme}
            title={t(lang, 'topbar.themeTitle')}
          >
            {theme === 'dark' ? 'Light' : 'Dark'} {t(lang, 'topbar.theme')}
          </button>
          <div className="chips" title={t(lang, 'topbar.language')}>
            {LANGS.map((option) => (
              <span
                key={option.id}
                role="button"
                tabIndex={0}
                className={`chip${lang === option.id ? ' active' : ''}`}
                onClick={() => pickLang(option.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pickLang(option.id) }
                }}
              >
                {option.label}
              </span>
            ))}
          </div>
          {!online && (
            <span className="mock-badge" title="Serving the last cached API responses from the service worker">
              {t(lang, 'offline.badge')}
            </span>
          )}
          {IS_MOCK
            ? <span className="mock-badge" title="VITE_MOCK=1 — rendering from devMock, DB not required">mock data</span>
            : <span className="db-badge">db: {health?.database || '…'}</span>}
        </div>
      </header>

      {err && !IS_MOCK && <div className="error" style={{ margin: '10px 0' }}>backend unreachable: {err}</div>}

      <nav className="tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`tab${route.tab === tab.id ? ' active' : ''}`}
            onClick={() => navigate(tab.id)}
            aria-current={route.tab === tab.id ? 'page' : undefined}
          >
            {tab.label}
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
        tabs={tabs.map((tab) => [tab.id, tab.label])}
      />
    </div>
  )
}
