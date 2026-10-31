// The tab list lives in exactly one place.
//
// It used to be duplicated: App.jsx held the components, router.js held the ids.
// Adding a tab to one and not the other does not crash — the hash silently falls
// back to the dashboard, which reads as a broken link rather than a bug. So the
// ids and the label keys are declared here, and both consumers import them.
//
// Order is the demo narrative: what is wrong today, which ward, why, what nobody
// has acted on, what to do, and finally why you can believe it.
export const TABS_META = [
  { id: 'dashboard', labelKey: 'tab.dashboard' },
  { id: 'ward', labelKey: 'tab.ward' },
  { id: 'trend', labelKey: 'tab.trend' },
  { id: 'anomalies', labelKey: 'tab.anomalies' },
  { id: 'disagreements', labelKey: 'tab.disagreements' },
  { id: 'complaints', labelKey: 'tab.complaints' },
  { id: 'leaderboard', labelKey: 'tab.leaderboard' },
  { id: 'simulator', labelKey: 'tab.simulator' },
  { id: 'brief', labelKey: 'tab.brief' },
  { id: 'trust', labelKey: 'tab.trust' },
  { id: 'ingest', labelKey: 'tab.ingest' },
  { id: 'benchmark', labelKey: 'tab.benchmark' },
]

export const TAB_IDS = TABS_META.map((tab) => tab.id)
