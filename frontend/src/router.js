// Hash routing, hand-written. No router package: the whole surface is eleven
// tabs and one optional ward id, and a `hashchange` listener gives deep links
// (#/ward/12) that survive a reload for about forty lines.
//
// One invariant matters more than the rest: an *empty* hash means the landing
// page, and nothing else does. The landing page makes zero API calls, so it
// still renders with the database down — if routing ever mapped an unknown
// route to landing, a typo'd deep link would look like an outage.
import { useEffect, useState } from 'react'

export const TAB_IDS = [
  'dashboard', 'ward', 'trend', 'anomalies', 'disagreements', 'complaints',
  'leaderboard', 'simulator', 'brief', 'ingest', 'benchmark',
]

const KNOWN = new Set(TAB_IDS)
const FALLBACK = 'dashboard'

// '#/ward/12' -> {view:'app', tab:'ward', wardId:12}
// '#', ''     -> {view:'landing', tab:null, wardId:null}
// '#/nonsense'-> {view:'app', tab:'dashboard', wardId:null}
export function readRoute(hash) {
  const raw = hash === undefined ? window.location.hash : hash
  const path = String(raw || '').replace(/^#\/?/, '').trim()
  if (!path) return { view: 'landing', tab: null, wardId: null }

  const [tab, param] = path.split('/')
  const id = Number.parseInt(param, 10)
  return {
    view: 'app',
    tab: KNOWN.has(tab) ? tab : FALLBACK,
    wardId: Number.isFinite(id) && id > 0 ? id : null,
  }
}

export function routeHash(tab, wardId) {
  if (!tab) return '#/'
  return wardId ? `#/${tab}/${wardId}` : `#/${tab}`
}

export function navigate(tab, wardId) {
  const next = routeHash(tab, wardId)
  if (window.location.hash === next) return
  window.location.hash = next
}

// Back to the landing page. Setting the hash to '' leaves a bare '#' in some
// browsers and fires no event when it was already empty, so the route is
// re-read by hand in that case.
export function goHome() {
  const bare = window.location.hash.replace(/^#/, '')
  if (bare) {
    window.location.hash = ''
    return
  }
  window.dispatchEvent(new Event('hashchange'))
}

export function useRoute() {
  const [route, setRoute] = useState(() => readRoute())

  useEffect(() => {
    const sync = () => setRoute(readRoute())
    window.addEventListener('hashchange', sync)
    window.addEventListener('popstate', sync)
    return () => {
      window.removeEventListener('hashchange', sync)
      window.removeEventListener('popstate', sync)
    }
  }, [])

  return route
}
