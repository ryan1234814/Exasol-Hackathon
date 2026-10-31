# Brag Plan: WARDQ — Ward-Level Water Quality & Complaint Triage

## What is this app?

A municipal ward officer's morning dashboard: 24 wards, 288,768 water samples and
15,063 WhatsApp complaints analysed inside a local Exasol Personal database, so
deteriorating water quality is caught before the illness spike confirms it.

## The angle

The product's own inversion is the story: **"Catch deteriorating water quality
*before* the illness spike confirms it."** The video runs that inversion as a
tour of the actual dashboard — every claim on screen is a number the running app
returned, not a slide. This is the **2:55 cut**: the same film trimmed to the
three-minute ceiling, keeping the scenes whose visuals carry a claim and dropping
the ones that only restate it.

## Hook (first 2-3 seconds)

Black frame, one amber line: **"The water gets worse first."** Beat. **"The
illness arrives weeks later."** A thin turbidity line spikes behind it.

## Key moments (the middle)

- The 24 × 13 heatmap as a wall of risk cells, with `▶ Replay` sweeping 13 months
- Ward 205 - Peenya at risk **75.4**, worst param COLIFORM, four component bars
  labelled with the UDF's own **35 / 30 / 15 / 20**
- Every flagged row opens the SQL that produced it
- "But the lab says compliant" — `instrument_suspect` vs `lab_confirmed`
- A real complaint: *"Water from Vile Parle East tap is black colour…"* with the
  rule evidence that fired
- Simulator at **100·Σ(wᵢcᵢ)/Σwᵢ**, measured drift **3.55e-15**
- Trust: **97.01 %** complete, **2.99 %** unusable, **28.02 ms**, lineage table
- Benchmark: **15 ms** Exasol vs **96 ms** SQLite on 288,768 rows
- Monsoon: **5.75 NTU** downstream vs **2.15 NTU** upstream, same city, same months
- The caveat wall: a single node, a straight-line forecast, a nine-day-old file

## Outro / punchline

"Turn off the Wi-Fi. It still opens." → free-forever stack line → WARDQ wordmark
and the event line.

## User flow worth showing

Entry: landing → **Open Dashboard**. Key action: heatmap → click ward → case
file → breach forecast. Result: the three-action morning brief (and the same
brief as `.ics` / Atom / CSV leaving the laptop).

## Tone

- Preset: `polished`
- Creative direction: "civic ops room, quietly confident — the dashboard is the
  hero, the numbers do the bragging"
- Interpretation: long holds, restrained motion, one idea per scene, hard cuts
  between tabs like a real operative clicking through. No jokes.

## Format: landscape — 1920x1080
## Duration: 175 s (2:55) — 17 scenes, trimmed to the three-minute ceiling

## Visual identity (from the project)

- Background: `#0f1720` (page), `#081120` → `#0d1f33` (landing gradient)
- Panel: `#17222e`, panel-2 `#1e2b3a`, border `#26384a`
- Text: `#e6edf3`, muted `#8ba0b3`
- Accent: `#38bdf8`; ok `#22c55e`; warn `#f59e0b`; bad `#ef4444`
- Display/body font: the app's own system stack (`system-ui, sans-serif`)
- Strongest visual element: the ward × month risk heatmap grid and the KPI strip

## Share copy (draft)

WARDQ: 24 wards, 288,768 water samples, 15,063 complaints, one local Exasol
database — and every number traceable to the SQL that produced it.

## Audio direction

- Role: warm, steady corporate-electronic bed; restrained accents
- Music: two beds — `…vol-1…mp3` (163.96 s, 120.19 BPM) carries the whole body,
  `…vol-12…mp3` (117.36 s, 109.96 BPM) takes the last 14.6 s from 160.4 s
- Music treatment: vol-1 fades in 0–1.6 s to 0.55, holds to 156 s, out by 163.9 s;
  vol-12 fades in 0–2.0 s (clip-relative) to 0.50, holds, out over its last 2.4 s.
  The crossfade sits under the outro transition, so the seam is never audible
- Music cue guidance: bundled preset `cues/…vol-1….music-cues.json`; strong cues
  at 16.02 / 17.02 / 18.02 / 19.02 s, then every ~4 s. Lock 16.02 (title lands),
  40.0 (ward case file), 163.0 (wordmark)
- Audio-reactive treatment: subtle — the heatmap cells and the KPI strip carry a
  faint background glow that breathes with the bed
- SFX posture: sparse; one soft impact per chapter change, clicks for the SQL
  drawer and the simulator sliders
- Audio-coupled moments: heatmap cascade, component bars growing, SQL drawer
  opening, simulator sliders, final wordmark
- Restraint rule: no whooshes on every cut, no typed-text clatter over the tour

## Storyboard

### Scene 1 — The inversion (hook) — 0:00–0:06
Near-black frame. "The water gets worse first." lands, holds; "The illness
arrives weeks later." arrives in amber with a rising turbidity sparkline behind.

### Scene 2 — Title + promise — 0:06–0:15
Badge "ExaThon India 2026 · Civic / Sustainability track", H1 "Ward-Level Water
Quality & Complaint Triage", then four stats: 24 wards monitored · 288,768
lab/sensor readings · 15,063 complaints triaged · db: up.

### Scene 3 — What is actually running — 0:15–0:24
Two columns: the stack (Exasol Personal / WARDQ schema, FastAPI + pyexasol,
React + Vite + Chart.js, one origin) and the pipeline chips 10_schema → 70_verify.

### Scene 4 — Dashboard: what is wrong today — 0:24–0:40
KPI strip (288,768 readings · 15,063 complaints · 24 wards · 7,805 high severity ·
worst Ward 205 - Peenya 75.4 COLIFORM). The 24 × 13 heatmap wall fills right and
`▶ Replay` sweeps 2025-10 → 2026-10, month label following the playhead.

### Scene 5 — The case file — 0:40–0:53
Ward 24 · Ward 205 - Peenya, rank #1, risk 75.4. Four component bars with the
UDF's weights 35/30/15/20, a 13-month risk sparkline, four breach-forecast cards
and the "Do next" checklist + Print report.

### Scene 6 — Trend: the why — 0:53–1:03
Ward 24 turbidity, 26 real monthly buckets (0.92 → 5.49 NTU), breach band at
5 NTU, z-score markers, dashed 90-day projection. Side notes: bucketed
server-side · 30-day z window · 12-month slope.

### Scene 7 — Anomalies → the SQL behind it — 1:03–1:13
Flagged table (Ward / Parameter / Z / Breach days / Consec. run / 12m slope /
Severity) with the month's real rows. A pointer clicks Ward 5 - Govandi and the
drawer slides in with the saved query and the copyable `run_sql.py` command.

### Scene 8 — "But the lab says compliant" — 1:13–1:24
Three verdict cards with the month's real mix (instrument_suspect 2,
lab_confirmed 2, consistent 2) and rows: Ward 51 - Indiranagar PH 22 probe
breaches vs 0 lab, COLIFORM 12 vs 41.

### Scene 9 — What people are saying — 1:24–1:33
Three real complaints as message cards with category chip, severity, confidence
and RULE_EVIDENCE. Footer: regex rule table, not a neural network · 2026.10.

### Scene 10 — Ingest — 1:33–1:41
`ward_4_dharavi_export.txt`: 33 lines read, 31 parsed, 2 system, 30 messages,
ward inferred 30/30; category mix (contamination 12, other 12, leakage 4,
pressure 2). Stamp: "Preview only — nothing was inserted."

### Scene 11 — Leaderboard + Simulator — 1:41–1:53
Top-5 leaderboard bars (75.4, 73.5, 70.3, 69.6, 68.4) and the simulator with four
weight sliders at 35/30/15/20, formula `100·Σ(wᵢcᵢ)/Σwᵢ`, drift 3.55e-15.

### Scene 12 — The morning brief — 1:53–2:05
Three prioritised actions, verbatim titles, the language panel (EN / हिं), the
reach row (`.md`, `.csv`, `.ics`, Atom feed) and the Markdown preview underneath.

### Scene 13 — Trust: can I trust this number? — 2:05–2:16
Four KPIs: 97.01 % complete · 2.99 % unusable · 97.91 % lab-verified · 28.02 ms
measured. Lineage table (endpoint → SQL step → tables → file), freshness strip,
footnote: N_IMPLAUSIBLE = 0 is a finding, not a bug.

### Scene 14 — Benchmark: measured on this laptop — 2:16–2:24
Paired bars: S1 scan 288,768 rows 15 ms Exasol vs 96 ms SQLite; S2 z-score 7 ms
in-DB vs 19 ms in Python; S3 cold 16 ms vs warm 13 ms. Caveat: 2 vCPU / 6 GB.

### Scene 15 — Monsoon: downstream vs upstream — 2:24–2:34
Downstream 5.41 / 5.54 / 5.75 NTU with 891 / 1,040 / 1,049 breach days, 100 % of
ward-days in breach; upstream 1.84 / 1.95 / 2.15 NTU, 0 breach days.

### Scene 16 — What it refuses to claim — 2:34–2:43
Six caveats in one grid: one data node · a straight line is not a model · the data
lags nine days · 104 regex patterns · generated, not measured · one machine, one
process. Footer: every caveat is printed inside the product, not in a slide.

### Scene 17 — Offline, free, and done — 2:43–2:55
"Turn off the Wi-Fi. It still opens." with the `served from cache` badge; the
free-forever stack line; final WARDQ wordmark, subtitle, "ExaThon India 2026".

**Music mood for this video:** upbeat-but-serious corporate electronic — one bed
for the body, a second for the last fifteen seconds.
**Audio summary:** two beds with a short crossfade under the outro, sparse
impacts at chapter changes, one accent at the wordmark, then a clean fade.
