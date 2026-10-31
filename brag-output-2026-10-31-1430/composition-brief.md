# Hyperframes Composition Brief: WARDQ — Ward-Level Water Quality & Complaint Triage

## Objective
An extended (2:55) launch-style product tour of WARDQ: the real dashboard, tab by
tab, with the numbers the running app returned.

## Output
- Composition directory: `brag-output-2026-10-31-1430/composition/`
- Rendered video: `brag-output-2026-10-31-1430/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 175 s, 17 scenes (three-minute ceiling; 10 scenes cut from the long cut)

## Source Material
- Project root: `/Users/ryangeorge/exasol`
- Primary files read: `README.md`, `frontend/src/App.jsx`, `frontend/src/tabs.js`,
  `frontend/src/pages/Landing.jsx`, `frontend/src/styles.css`,
  `frontend/src/pages/*.jsx`, `db/*.sql`, and the live API (`/api/summary`,
  `/api/wards`, `/api/heatmap`, `/api/anomalies`, `/api/disagreements`,
  `/api/complaints`, `/api/brief`, `/api/data-quality`, `/api/benchmark`,
  `/api/ingest/chat`).
- Product name: WARDQ
- Tagline / strongest claim: "Catch deteriorating water quality before the
  illness spike confirms it."
- Key UI or visual moment to recreate: the 24 × 13 ward × month risk heatmap,
  the KPI strip, the ward case file's four component bars, the SQL drawer.
- Copy that must appear verbatim:
  - "One page every morning. Every ward ranked. Every breach explained."
  - "All analytics run locally — nothing leaves this machine."
  - "But the lab says compliant"
  - "Can I trust this number?"
  - "Preview only: nothing was inserted, so this is safe to re-run."

## Creative Direction
- Tone preset: `polished`
- Creative direction: civic ops room, quietly confident
- Interpretation: long holds, one idea per scene, hard cuts between tabs like
  someone clicking through the real app. No jokes, no stock footage.
- Angle: the product's own inversion (data before illness) told as a tour.
- Hook: "The water gets worse first." / "The illness arrives weeks later."
- Outro / punchline: "Turn off the Wi-Fi. It still opens."
- Avoid: generic SaaS language, abstract filler, purple-gradient tech-bro look,
  invented numbers (every figure below is from the live API).

## Visual Identity
- Background: `#0f1720`; landing gradient `#081120 → #0f1720 → #0d1f33`
- Panel: `#17222e`; panel-2 `#1e2b3a`; border `#26384a`
- Text: `#e6edf3`; muted `#8ba0b3`
- Accent: `#38bdf8`; ok `#22c55e`; warn `#f59e0b`; bad `#ef4444`
- Display/body font: `system-ui` with `sans-serif` fallback (the app's stack)
- Visual references: KPI cards, tab strip, heatmap cells, 35/30/15/20 bars,
  verdict chips, SQL drawer, benchmark bars

## Storyboard
Use `brag-plan.md` as the creative contract. Scene summary:
1. The inversion — 7 s — two-line hook over a rising turbidity line
2. Title + promise — 10 s — badge, H1, subtitle, four stats
3. What is actually running — 11 s — stack + pipeline chips
4. Dashboard — 16 s — KPI strip + heatmap cascade + replay sweep
5. The case file — 13 s — 75.4, component bars, sparkline, forecast cards
6. Trend — 11 s — turbidity series, 5 NTU band, anomaly markers, projection
7. Anomalies → SQL drawer — 10 s — table, click, drawer with the saved query
8. Disagreements — 11 s — instrument_suspect / lab_confirmed / consistent
9. Complaints — 10 s — three real messages with rule evidence
10. Ingest — 9 s — parse report + category mix + "nothing was inserted"
11. Leaderboard + Simulator — 12 s — top 5 bars, sliders, re-rank, drift
12. Morning brief — 12 s — three actions, EN/हिं, .md/.csv/.ics/Atom
13. Trust — 11 s — 97.01 % complete, 28.02 ms, lineage table
14. Benchmark — 9 s — 15 ms vs 96 ms, 7 ms vs 19 ms, 16/13 cold-warm
15. Offline + free forever + wordmark — 12 s

## Audio
- Audio role: warm bed with sparse professional accents
- Audio arc: fade in under the hook, steady through the tour, out on the wordmark
- Music: `assets/music/happy-beats-business-moves-vol-1-by-ende-dot-app.mp3`
- Music treatment: two beds. vol-1 — volume lane 0 → 0.55 (0–1.6 s), hold,
  159.5 → 163.9 s to 0. vol-12 from 160.4 s — clip-relative 0 → 0.50 (0–2.0 s),
  hold, out over its last 2.4 s. The crossfade sits under the outro transition
- Music cue guidance: bundled preset, 120.19 BPM. Major locks: title at 7.0 s
  (nearest strong cue 8.02 s), case file at 40.0 s, wordmark at 163.0 s.
  Sequential reveals use the beat grid only where the text floor allows.
- Audio-reactive treatment: subtle — a slow glow behind the heatmap and the KPI
  strip; no waveform bars
- Audio-coupled moments: heatmap cascade, bar growth, SQL drawer open, slider
  ticks, final wordmark
- SFX selection guidance: `impactSoft_medium_00{1,4}`, `impactSoft_heavy_003`,
  `bong_001`, `ui/click2`, `interface/click_003` (all copied into `assets/sfx/`)
- Exact SFX timestamps: chosen after the animation exists, same frame as motion
- Audio files: copied into `composition/assets/`

## Hyperframes Instructions
- Standalone composition (no sub-compositions) so the timeline is one seekable
  GSAP timeline at `window.__timelines["main"]`.
- Vendor GSAP locally (`assets/gsap.min.js`) — no render-time network.
- Show real UI copy from the project; every on-screen number is an API value.
- Keep every line on screen long enough to read; cut copy rather than speed up.
- One `check` gate before render.
