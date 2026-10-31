# Ward-Level Water Quality & Complaint Triage

**ExaThon India 2026 · Civic/Sustainability track · Oct 23 → 25**

A municipal ward officer opens one page each morning and immediately sees which ward is deteriorating this month, why (turbidity / residual chlorine / coliform / pH breach trends), and what citizens are complaining about — before an illness spike confirms it. All analytics run inside a local Exasol Personal database; nothing leaves the laptop, and every tool is free forever.

---

## Table of Contents

- [Summary](#summary)
- [Locked Decisions](#locked-decisions)
- [Memory And Footprint](#memory-and-footprint-measured-not-estimated)
- [Phase 0 — Repair the Database](#phase-0--repair-the-database)
- [Repository Layout](#repository-layout)
- [Database Design](#database-design)
- [Backend](#backend)
- [Frontend](#frontend)
- [Demo Script](#demo-script)
- [Day-by-Day Schedule](#day-by-day-schedule)
- [Test Plan](#test-plan)
- [Risks & Mitigations](#risks--mitigations)
- [Rejected Alternatives](#rejected-alternatives)
- [Free-Forever Proof](#free-forever-proof)

---

## Summary

**Status as of Oct 23:** Phase 0 is green. The database that never came up was
redeployed at 6 GB (see [Memory And Footprint](#memory-and-footprint-measured-not-estimated))
and is at that point `database_ready` on `127.0.0.1:8563`; `WARDQ` is loaded with
288,768 sample rows, eight analytical window views plus the forecast view
(`V_WARD_FORECAST`, added later by `db/45_forecast_view.sql`), and the Lua
`RISK_SCORE` UDF, with every planted signal verified by live queries. The
original blocker — an orphan `launcher __daemon__` holding the port forwarder
while `bridge100` pointed at a dead VM address — is documented in risk R2 with the
repair that worked.
Because `exapump` was never installed by a raw `exasol deploy`, SQL is run with
`scripts/run_sql.py` against the same `backend/db.py` seam the API uses.

> **Status as of Oct 25:** the database is `database_ready` again on
> `127.0.0.1:8563`. A `start` issued on Oct 24 died in the macOS Local Network
> block (guest booted, host got `no route to host`), leaving a wedged `launcher
> __daemon__` holding the forwarder while the CLI reported `stopped`. Restarting
> that daemon **from Terminal.app** restored it with `data.img` intact, so every
> table and both materializations survived. All 170 backend tests pass, including
> the DB-backed ones that used to skip, and `/api/health` reports
> `database: up, mock: false`. `db/45_forecast_view.sql` now applies cleanly and
> `V_WARD_FORECAST` exists (96 rows).
>
> Two dialect fixes came out of executing that file for the first time: this
> build rejects a standalone `COMMENT ON VIEW` with `0A000 Feature not
> supported` (the comment must ride on `CREATE VIEW … COMMENT IS`), and `CURRENT`
> is a reserved word, so `db/sql/forecast_eta.sql` had to quote it as `"CURRENT"`.
> Note that `exakit status` still says "not installed": the runtime was brought up
> by a raw `exasol deploy`, so the kit has no record of it. Use `exasol status`
> as the source of truth for this deployment.

### What is new in v1.1 — Trust & Reach

Six additions, all of them free forever: stdlib only on the backend, hand-written
JS on the frontend, no accounts, no API keys, no new npm or uv packages, and the
build is still SELECT-only, one origin, one port.

| # | Feature | Why it is on stage |
|---|---------|--------------------|
| 1 | `V_DATA_QUALITY` + **Trust** tab | "3% of readings are unusable — here is the number, not a promise" |
| 2 | SQL lineage registry + Trust tab | every figure on screen traces to a file you can run in `exakit sql` |
| 3 | **Export CSV** on six tables | judges walk away with the data in a spreadsheet |
| 4 | Installable PWA + offline cache | turn off Wi-Fi; the dashboard still opens, with a badge saying so |
| 5 | Hindi UI chrome + Hindi brief | the brief a ward officer would actually read |
| 6 | `.ics` breach calendar + Atom feed | a 90-day breach ETA lands in the officer's calendar with a 7-day alarm |

Nothing new is licensed, and item 6 is the free equivalent of email/WhatsApp
delivery: pull, not push. The four rejected shortcuts (a `vite-plugin-pwa`
dependency, a server-side `/api/export/*.csv`, a fifth materialized table, and a
full 11-page Hindi translation) are recorded in
[Rejected Alternatives](#rejected-alternatives).

---

## Locked Decisions

| Concern | Decision | Why |
|---------|----------|-----|
| In-DB UDF language | Lua only | Lua is integrated into the Exasol engine; Python/Java UDFs need the script-languages container, which is absent from Personal local |
| Primary anomaly path | SQL window functions materialized into tables | Decouples the entire UI from UDF success |
| Data volume | ~289k sample rows + ~15k complaints, generated in pure SQL | Big enough to sell columnar speed, small enough to reload in seconds on a 2 vCPU / 6 GB VM |
| Perf claims | Only from measured numbers; no `DISTRIBUTED BY`/`PARTITION BY` in the DDL at all | Single data node, and the Personal build does not parse those clauses (measured) |
| Serving | FastAPI serves `frontend/dist` on one origin, one port (8000) | Deletes CORS as a failure mode entirely |
| NLP | Pure-stdlib regex rule table (data, not code) | No spaCy/transformer downloads on a ~350 KB/s link; explainable on stage |
| Language | Plain JS (no TypeScript), hand-written hash router, no state lib | 2-day solo build; a router dependency buys nothing that ~40 lines of `hashchange` does not |

---

## Memory And Footprint (measured, not estimated)

The local Exasol VM reserves RAM for the whole machine, so its `memory-mb` is the
single biggest number in this project. It was cut from the 8192 MB default toward
the enforced floor to bring the entire stack inside a 7-8 GB budget on a 16 GB
host — and the exact value was chosen by measurement, not guesswork.

| Component | Default | Now | How to re-measure |
|---|---|---|---|
| Exasol VM RAM reservation | 8192 MB | **6144 MB** | `exasol config get` |
| Launcher/forwarder process | 17 MB | 17 MB | `ps -axo pid,rss,comm \| grep launcher` |
| Backend + frontend dev servers | ~150 MB | ~150 MB | Activity Monitor |
| **RAM total** | ~8.6 GB | **~6.3 GB** | — |
| Repo working tree | 99 MB | 99 MB | `du -sh .` |
| Deployment dir (VM + data images) | 1.8 GB | 1.8 GB | `du -sh ~/.exasol/personal/deployments/default` |
| Starter kit + launcher cache | 270 MB | 270 MB | `du -sh ~/.exasol-starter-kit ~/Library/Caches/.exasol` |
| **Disk total** | 2.2 GB | 2.2 GB | `du -sh -c` over those four paths |

**Why 6144 MB and not the 4096 MB floor.** `exasol init local --memory-mb=N` was
probed in a throwaway deployment directory: `1`, `1024`, `2048` and `3072` are all
rejected with `local memory-mb must be at least 4096 MB`, while `4096` and `6144`
are accepted (the clamp is compiled into the launcher binary, which reads
`hw.memsize` via `detectLocalHostMemoryMB`). `4096` was set first and ran the whole
pipeline correctly for ~30 minutes, then the guest dropped to a bare Alpine shell
under a modest query burst — an out-of-memory crash at the floor. `6144` keeps the
total stack at ~6.3 GB, comfortably inside the 7-8 GB target, with the headroom
that makes the demo reliable.

**Why the workload still fits easily.** The fact table is 288,768 rows across four
DOUBLE/DATE/VARCHAR columns — roughly 13 MB uncompressed — and the API only ever
reads pre-aggregated tables (`WARD_DAILY` = 72,192 rows, `ANOMALY_EVENT`,
`WARD_MONTH_RISK`), all of which stay resident with gigabytes of headroom. Measured:
schema + seed + 289k-row generation + all eight window views + the Lua UDF + the
materialize pass + 15,063 complaints reload in a few seconds end to end.

To reproduce the change (config cannot be edited while resources exist, so the
order is fixed):

```bash
exasol destroy --auto-approve
exasol config set --memory-mb=6144 --auto-approve
exasol deploy --auto-approve          # then re-run the starter-kit installer
```

If `destroy` fails with `failed to remove Nano container exasol-db-<id>`, an
orphaned `launcher __daemon__` (PPID 1) is wedged on the dead VM address — see
risk R2 for the proven repair. `data-size-gb` was deliberately left at 100: the
100 GB value is a sparse image that currently occupies 864 MB, so shrinking it
saves nothing today.

---

## Phase 0 — Repair the Database

> **Gate: nothing downstream is trusted until this is green.**
> Budget: 2 hours. Decision gate at 20:00 today, Oct 23.

### Read-only diagnostics first

```bash
exakit status --json; echo "exit=$?"      # 0 running · 3 stopped/interrupted · 4 not installed
exakit preflight
ps -p 42445 -o pid,rss,comm
netstat -rn | grep 192.168.64              # expect bridge100, not utun
```

### The ladder — stop at first success

1. **Free the port + clear the route conflict.**
   `exakit stop`; if it refuses, `kill 42445` (the PID from `~/.exasol/personal/deployments/default/local/runtime/vm.pid`). Quit OrbStack and any VPN/remote tool that may own `192.168.64.0/24`-adjacent routes. macOS application firewall is already disabled (verified), so it is not the cause.

2. **Re-run the resumable installer** — this installs the currently-missing exapump, pyexasol-venv, and credentials:
   ```bash
   curl -fsSL https://www.exasol.com/install/starter-kit.sh | sh
   ```
   The 620 s launcher download is skipped (already present).

3. `exakit start`, then poll `exakit status` until exit 0.

### Fallback B (if vmnet still unreachable by the gate)

OrbStack `exasol/docker-db` on 8563 — docker CLI is installed at `/usr/local/bin/docker` (daemon currently off; start OrbStack). The kit adopts it with `EXAKIT_REUSE_DB=1`. All `db/*.sql`, `backend/`, and `frontend/` code is identical — only the DSN/password source changes. Disclose the runtime deviation in `docs/prd.md` limitations.

### Safety rule

> **Never run `exakit repair-runtime` without explicit user consent** — it destroys data. (State is `deploymentFailed`, not `interrupted`, so it isn't needed; and `data.loaded: false` means there is nothing to lose anyway.)

### Gate to proceed

`exakit sql 'SELECT CURRENT_TIMESTAMP'` returns a row, **and** a throwaway:

```sql
CREATE OR REPLACE LUA SCALAR SCRIPT WQ_PROBE(X DOUBLE) AS RETURNS DOUBLE + SELECT WQ_PROBE(2)
```

executes. If the Lua probe fails, drop the UDF from the critical path (Phase 2 already provides the pure-SQL equivalent) and continue.

### Also verify

- `exakit info --json` → note `runtime.password_file` path only (never print the value)
- `exapump --version`
- `~/.exapump/config.toml` has the starter-kit profile

---

## Repository Layout

All paths relative to `/Users/ryangeorge/exasol/` (verified empty — safe to build in place).

```
docs/           prd.md  decisions.md  data-dictionary.md  demo-script.md

db/             10_schema.sql  20_seed_dims.sql  30_generate_readings.sql
                40_anomaly_window.sql  45_forecast_view.sql  46_data_quality_view.sql
                50_udf_ward_risk.lua.sql  60_materialize.sql
                61_materialize_no_udf.sql  70_verify.sql
                sql/*.sql (11 saved demo queries)

data/           raw/whatsapp_ward_exports/*.txt  raw/sample_logs_demo.csv
                derived/*.csv (fallback snapshots)  generated/README.md

backend/        app.py  db.py  nlp_rules.py  forecast.py  brief.py
                quality.py  calendar_feed.py  atom_feed.py
                ingest/whatsapp_parser.py  ingest/tabular.py
                benchmark.py  requirements.txt  tests/

frontend/       index.html  vite.config.js  public/(manifest.webmanifest, sw.js,
                icon.svg, icon-192.png, icon-512.png)
                src/{App.jsx,api.js,devMock.js,router.js,tabs.js,i18n.js,
                theme.js,chartSetup.js,
                pages/{Landing,Dashboard,WardDossier,Trend,Anomalies,
                Disagreements,Complaints,Leaderboard,Simulator,
                Briefing,Trust,Ingest,BenchmarkPage}.jsx,
                components/*,styles.css}

scripts/        run_sql.py
README.md  THIRD_PARTY_NOTICES.md  .gitignore
```

There is **no `Makefile` and no `run_demo.sh`** in this checkout. The three entry
points are the ones the code actually has:

| Task | Command |
|------|---------|
| Pipeline (any `db/NN_*.sql`) | `backend/.venv/bin/python scripts/run_sql.py db/NN_name.sql` |
| API + built UI, one origin | `backend/.venv/bin/uvicorn backend.app:app --port 8000` |
| UI against mock data, no DB | `npm --prefix frontend run dev:mock` |

---

## Database Design (Exasol, schema `WARDQ`)

### Identifier rule (bites silently)

Every column is `UPPER_SNAKE`, and DDL is pre-created before any CSV load — file-loaded tables otherwise keep the header case as quoted identifiers, so `SELECT SUM(VISITS)` fails. Paging uses `LIMIT n` only (no `FETCH FIRST` / `TOP`).

### `db/10_schema.sql`

| Table | Grain | Key columns |
|-------|-------|-------------|
| `WARD` | 1 row/ward | `WARD_ID, WARD_NAME, CITY, CITY_ZONE, POPULATION, CONNECTIONS` — 24 wards, real-ish names (Ward 12 – Andheri East, Mumbai; Ward 44 – Koramangala, Bengaluru). `CITY_ZONE`, not `ZONE`: `ZONE` is a reserved token in the Exasol parser. |
| `PARAMETER_LIMITS` | 1 row/param | `PARAM_CODE, PARAM_NAME, UNIT, THRESHOLD_LO, THRESHOLD_HI` — TURBIDITY (NTU, hi 5), CHLORINE (mg/L, lo 0.2 hi 1.0), COLIFORM (CFU/100ml, hi 0), PH (lo 5.5 hi 8.5) — BIS 10500-aligned. Named `PARAMETER_LIMITS` because bare `PARAMETER` is a reserved word and Exasol refuses it as a table name |
| `SAMPLE_LOG` | 1 row/sample | `SAMPLE_ID, WARD_ID, PARAM_CODE, SAMPLE_DATE, SAMPLE_TS, VALUE_DOUBLE, SOURCE_STATION, LAB_VERIFIED` — ~289k rows. No `DISTRIBUTED BY`/`PARTITION BY`: unsupported by the Personal build |
| `COMPLAINT` | 1 row/message | `COMPLAINT_ID, WARD_ID, RECEIVED_TS, SENDER_HANDLE, RAW_TEXT, CATEGORY, SEVERITY, CONFIDENCE, RULE_VERSION, CHANNEL` |
| `WARD_DAILY` | ward × day | aggregates + `GENERATED_AT` |
| `ANOMALY_EVENT` | ward × param × month | `Z_SCORE, MOVING_AVG, BREACH_DAYS, CONSECUTIVE_RUN, FIRST_BREACH_FLAG, SLOPE_12M` |
| `WARD_MONTH_RISK` | ward × month | `RISK_SCORE, RANK, COMPLAINT_DENSITY` — the table the API reads |
| `COMPLAINT_SUMMARY` | ward × category × month | counts + representative quote |
| `LOAD_RUN` | 1 row/load | `RUN_TS, ROWS_LOADED, ELAPSED_MS, SOURCE` — powers the honest "data as of …" footer |

No foreign keys (Exasol doesn't enforce them); `COMMENT ON` every table/column.

### `db/30_generate_readings.sql` — deterministic, no CSV pipeline

Copy the pattern from the kit's own `~/.exasol-starter-kit/kit/data/datasets/energy/02_load_data.sql`: a 4-way digit cross-join CTE generating an hours/days spine, joined to dimensions, `TRUNCATE`-first so a re-run can't double-insert. Baseline = sine seasonal curve + per-ward offset + deterministic jitter `MOD(ward*7919 + day*104729, 100)`.

**Planted signals — the demo depends on these existing:**

- Monsoon turbidity spike (Jul–Sep) in 4 downstream wards
- One chronic chlorine-under-dosing ward
- A one-off coliform event cluster (the "outbreak" story)
- A slowly deteriorating ward (trend, not spike — proves the slope metric)
- Sensor-drift pH in 2 wards (false-positive story: lab vs sensor)
- ~3 % missing values + a few unit typos, so the parser's error report has something to catch

**Fallback:** if SQL generation is awkward for a column type, commit generated CSVs to `data/raw/` and load with:

```bash
EXAKIT_DATA_FILE=… EXAKIT_DATA_TABLE=WARDQ.SAMPLE_LOG EXAKIT_ON_EXISTING=replace exakit data-load
```

(zero loader code).

### `db/40_anomaly_window.sql` — the analytical core (primary path, not the UDF)

```sql
AVG(VALUE_DOUBLE) OVER (PARTITION BY WARD_ID, PARAM_CODE
                        ORDER BY SAMPLE_DATE
                        ROWS BETWEEN 29 PRECEDING AND 1 PRECEDING)   -- moving avg
STDDEV(...) OVER (same window)                                        -- → Z_SCORE
LAG(BREACH_FLAG) OVER (PARTITION BY WARD_ID, PARAM_CODE ORDER BY SAMPLE_DATE)
```

Plus breach-day counts vs the `PARAMETER_LIMITS` thresholds, consecutive-breach runs, and a 12-month deterioration slope (`REGR_SLOPE`, or manual covariance if unsupported — probe, don't assume). Window functions run on the daily aggregate, not the raw 289k, which is what keeps the UI sub-second on 2 vCPU.

### `db/45_forecast_view.sql` — inputs for the breach forecast

One `CREATE OR REPLACE VIEW`, no data written. `V_WARD_FORECAST` joins the last
30 days of `WARD_DAILY` (mean, `STDDEV`, sample count) to the newest
`V_WARD_PARAM_SLOPE` row and the `PARAMETER_LIMITS` thresholds — 96 rows
(24 wards × 4 parameters), one row per ward × parameter.

It deliberately returns **raw inputs only**: no ETA arithmetic in SQL. Every
branch (rising vs falling, which bound is in play, a zero slope, coliform's
limit of 0) lives in `backend/forecast.py`, which is unit-tested with no
database. `db/sql/forecast_eta.sql` shows the same arithmetic as a single
`SELECT` for the on-stage "show me the SQL" moment.

### `db/50_udf_ward_risk.lua.sql`

```sql
CREATE OR REPLACE LUA SCALAR SCRIPT WARDQ.RISK_SCORE(
  Z DOUBLE, BREACH_RATIO DOUBLE, SLOPE DOUBLE, COMPLAINT_DENSITY DOUBLE
) RETURNS DOUBLE
```

~40 lines, documented weights, clamped 0–100. Lua is on the critical path **only** for scoring; if it fails, the same expression is a `WITH` clause in `60_materialize.sql` and zero UI change results.

### `db/60_materialize.sql`

`TRUNCATE` + `INSERT … SELECT` from the views/UDF into `WARD_MONTH_RISK`, `ANOMALY_EVENT`, `COMPLAINT_SUMMARY`, stamping `GENERATED_AT`. `db/70_verify.sql` re-checks row counts from a fresh connection (the DB can ACK a DDL batch right after first boot without persisting it).

### Pipeline order

```
10_schema → 20_seed_dims → 30_generate_readings → 40_anomaly_window
  → 45_forecast_view → 46_data_quality_view → 50_udf_ward_risk
  → 60_materialize → 70_verify
```

`45_forecast_view.sql` depends only on `WARD_DAILY` and `V_WARD_PARAM_SLOPE`, so
it can run before or after the UDF. `61_materialize_no_udf.sql` is the drop-in
replacement for `60` when the Lua UDF is unavailable; `70_verify.sql` is re-run
last either way. Each step is one file, so the whole pipeline is
`for f in db/NN_*.sql; do backend/.venv/bin/python scripts/run_sql.py $f; done`.

### `db/46_data_quality_view.sql` — the Trust scorecard's inputs

`CREATE VIEW WARDQ.V_DATA_QUALITY`: one row per ward × parameter × month (~1,152
rows) carrying `N_READINGS`, `N_MISSING`, `N_LAB_VERIFIED`, `N_SENSOR_ONLY`,
`N_IMPLAUSIBLE` and the first/last sample date. It reads only `SAMPLE_LOG`,
`PARAMETER_LIMITS` and `WARD`, and writes nothing.

The **grading is deliberately not in SQL**: bands, findings and the sentences
around them live in `backend/quality.py`, because they are a policy opinion that
will be argued about and must be testable without a VM. This is the second
documented exception to "reads touch the materialized layer" (see the endpoint
section) and it reports its own `query_ms`.

`N_IMPLAUSIBLE` is legitimately `0` — that is a finding, not a bug. The generator
plants NULL results and sensor drift, not unit typos, and the view proves it
rather than asserting it.

---

## Backend (FastAPI + pyexasol)

### `backend/requirements.txt`

Exactly: `fastapi`, `uvicorn[standard]`, `pyexasol`, `python-multipart`, `openpyxl`.

Venv via `uv venv backend/.venv --python python3.11` (not 3.14 — wheel availability), and deliberately separate from the kit's pyexasol venv so a kit update/repair can't wipe app deps. No ORM, no pandas in the request path.

### `backend/db.py` — the single seam to the DB (~50 lines)

```python
pyexasol.connect(dsn="127.0.0.1:8563", user="sys",
                 password=open(PASSWORD_FILE).read().strip(),   # path from `exakit info --json`
                 websocket_sslopt={"cert_reqs": 0})              # local self-signed cert
```

Lazy connection + one reconnect-on-stale attempt; per-query `time.monotonic()` timing. Password file path from env `EXAKIT_PASSWORD_FILE`; never hardcoded, never printed, gitignored. Fallback if pyexasol is unavailable: subprocess → `exakit sql --json` (same response shape, no TLS config).

### Endpoints — reads hit materialized tables or pre-aggregated views (never the raw 289k, never a live UDF)

| Method · Path | Returns |
|---------------|---------|
| `GET /api/health` | DB reachability + `GENERATED_AT` |
| `GET /api/wards` | ward list + latest risk score |
| `GET /api/wards/{id}/trend?param=` | ≤500 points, server-side bucketed |
| `GET /api/wards/{id}/forecast?param=&horizon_days=90` | breach ETA, ±band and confidence per parameter (all four when `param` is omitted) |
| `GET /api/anomalies?month=` | flagged ward×param rows |
| `GET /api/leaderboard` | deteriorating wards by risk |
| `GET /api/heatmap?months=13` | ward × month risk matrix in one payload (≤600 cells) for the replay slider |
| `GET /api/disagreements?month=&ward_id=&param=&limit=` | sensor-vs-lab agreement per ward × parameter, with a derived `VERDICT` |
| `GET /api/brief?month=&lang=en\|hi` | the three-action morning brief plus its Markdown rendering, in English or Hindi (`backend/brief.py`) |
| `GET /api/data-quality?month=` | completeness and lab coverage per ward × parameter, already graded into bands and findings |
| `GET /api/lineage` | one row per read endpoint: the SQL step, the tables it reads, and the file that reproduces it |
| `GET /api/forecast.ics?horizon_days=90&alarm_days=7` | the breach forecast as an importable `.ics` calendar (one all-day event per projected crossing, 7-day alarm) |
| `GET /feed/brief.xml?month=&lang=` | the same brief as an Atom 1.0 feed, built from the same payload so feed and page cannot drift |
| `GET /api/complaints?category=&ward_id=&q=&since=` | triage queue, `LIMIT`-paged |
| `GET /api/summary` | header metrics + "data as of" |
| `GET /api/sql/{step}` | the exact `db/sql/*.sql` source behind a number, whitelisted by step name |
| `GET /api/rules` | the NLP rule table as data |
| `POST /api/ingest/chat` | multipart `.txt` → parse + classify preview, does not write (safely re-runnable on stage) |
| `POST /api/ingest/logs` | CSV/XLSX → staging rows + validation report |
| `POST /api/classify` | one sentence → category + which rule fired |
| `GET /api/benchmark` | measured timings (below) |

**One documented exception** to "reads touch materialized tables only":
`/api/disagreements` reads the pre-aggregated view `V_LAB_VS_SENSOR` directly.
That is one 288,768-row aggregate, measured at **15 ms** on this VM
(`data/derived/benchmark_results.csv`, `S1_scan_aggregate`/`exasol`), which is
cheaper than maintaining a fourth summary table for a view the pipeline already
computes. Every other endpoint reads `WARD_MONTH_RISK`, `ANOMALY_EVENT`,
`COMPLAINT_SUMMARY`, `LOAD_RUN` or `BENCHMARK_RESULTS`.

**The second documented exception** is `/api/data-quality`, which reads
`V_DATA_QUALITY` (the same 289k rows, counted once per request). It cannot be
materialized into the risk tables without pretending that a gap in the readings
is a property of the score rather than of the samples — so instead of hiding the
cost it returns `query_ms` and the Trust page prints it. If that measurement ever
exceeds ~150 ms, the documented fallback is a `60_materialize.sql`-style table.

All new read endpoints add `query_ms` (the `time.monotonic()` measurement
`backend/db.py` already records) so the UI can show the cost of the number it is
displaying.

```python
app.mount("/", StaticFiles(directory="frontend/dist", html=True))
```

→ one port, one origin, no CORS. `uvicorn --workers 1`.

### NLP (`backend/nlp_rules.py`)

One data structure:

```python
RULES = [{category, patterns[], weight, evidence}]
```

Over `contamination | leakage | pressure | other`, severity from cue words ("black water", "fever", "bachche" → high; "slow", "low pressure" → medium), confidence = normalized matched weight, `RULE_VERSION` stored per row so "show me the rule that fired" is a queryable column, not a black box. Optionally mirrored as a Lua keyword UDF (`51_udf_classify.lua.sql`) as the "15k complaints categorised in-database in N ms" line — explicitly off the critical path.

### WhatsApp parser (`ingest/whatsapp_parser.py`)

- Regex tolerant of both `[DD/MM/YYYY, HH:MM:SS]` and `DD/MM/YYYY, HH:MM:SS`
- Strips the `-- ... --` export header, `Media omitted`, `<attached: …>`, `Calls missed`, `— message deleted`
- Merges multi-line messages by sender
- Infers ward from keyword map with an explicit `--ward` override
- Returns rows plus a parse report (lines read / parsed / skipped) surfaced in the UI
- Tested against two committed fixtures, one deliberately messy, plus the kit's `test_data/employees_edgecases.csv` / `_malformed.csv` mindset

### Benchmark (`backend/benchmark.py`)

Writes `WARDQ.BENCHMARK_RESULTS` + a mirrored SQLite file so the comparison is same-laptop and reproducible:

| Scenario | Description |
|----------|-------------|
| S1 | Aggregate scan over 300k (Exasol vs SQLite) |
| S2 | Ward z-score computed in-DB vs pulled into Python (isolates transfer cost — the most persuasive, overhead-agnostic pair) |
| S3 | Same query twice → cold vs result-cache warm |

Discloses the 2 vCPU / 6 GB VM sizing in `docs/` so no claim is unfair.

---

## Frontend (React + Vite + Chart.js)

```bash
npm create vite@latest frontend -- --template react
```

Plus `chart.js`, `react-chartjs-2` only — no router package, no state library, no vitest. `vite.config.js` dev proxy `/api` → `http://127.0.0.1:8000`. Plain JS.

### Routing (`src/router.js`, ~60 lines)

The URL is the state: `#/dashboard`, `#/trend`, `#/ward/12` … An empty hash means
the landing page, which is how the "landing renders with the DB down" invariant
survives — it still makes zero API calls. Unknown tab → `dashboard`. Unknown ward
id → the ward selector on the case file. `readRoute()` / `routeHash()` / `navigate()`
plus one `hashchange` listener is the whole router; nothing new is downloaded and
the back button works.

`src/theme.js` toggles `:root[data-theme]`, persisting to `localStorage` inside a
`try/catch` so private-mode browsers still render. `Ctrl/Cmd-K` opens
`components/CommandPalette.jsx`: 12 tabs plus a lazily-fetched ward list, arrow
keys and Enter, no dependency.

### One tab registry (`src/tabs.js`)

The tab list used to be duplicated — `App.jsx` held the components, `router.js`
held the ids. Adding a tab to one and not the other does not crash; the hash
silently falls back to the dashboard, so it reads as a broken link rather than a
bug. `TABS_META` (id + i18n label key) is now the single definition: `router.js`
imports `TAB_IDS` from it and `App.jsx` builds its `COMPONENTS` map against the
same ids. A tab that exists in one place and not the other is now a build-time
reference error, not a silent fallback.

### Bilingual chrome (`src/i18n.js`)

`LANGS = [EN, हिं]`, one `STRINGS` table per language, and `t(lang, key, vars)`
which never returns a raw key: an unknown language or key falls back to English,
so a missing string degrades instead of showing `tab.trust`. `useLang()` persists
to `localStorage` (`wardq.lang`) inside `try/catch`, exactly like `theme.js`.

**The scope is explicit and stated on the page**: navigation chrome, the Trust
page and the morning brief. The brief's *sentences* are not translated here at
all — the chips re-request `/api/brief?lang=hi`, so the Hindi text comes from the
same `backend/brief.py` templates the Atom feed uses. Deep data prose on the
other nine tabs stays English, because a half-translated dashboard reads as a bug
and a clearly scoped bilingual shell does not.

### Landing page (`Landing.jsx`)

The first screen a judge sees. Pure CSS animations, zero API calls, zero chart dependencies:

- **Hero** — project title, one-line value proposition, and a prominent **"Open Dashboard →"** button
- **Stats bar** — 24 wards · 300k+ samples · 15k+ complaints · <1s load
- **Feature cards** — Anomaly Detection, Complaint Triage, In-DB Analytics, Free Forever
- **Description section** — what the system does, how it inverts the illness-spike timeline, and why every number is traceable to a SQL statement
- **Footer CTA** — second "Enter Dashboard" button

Clicking either button navigates to `#/dashboard`, revealing the tab bar + Dashboard. The `← Home` button in the header returns to the landing page through the same route table.

### Dashboard tabs

The tab order is the demo narrative: what is wrong today → which ward → why → what
nobody has acted on → what to do about it.

| Tab | Component | Note |
|-----|-----------|------|
| Dashboard | `Dashboard.jsx` | ward × month risk heatmap as a CSS grid of coloured cells — no chart lib, cannot break. Month slider + `▶ Replay` animates 12 months from one prefetched `/heatmap` payload (900 ms per tick, stops at the newest month, `live` badge when there); cells are `role="button"` and open the case file |
| Wards | `WardDossier.jsx` | the case file, also `#/ward/12`: four weighted component bars labelled with the UDF's own 35/30/15/20, 12-month risk sparkline, four breach-forecast cards, current anomalies, recent complaints with `RULE_EVIDENCE`, a "Do next" checklist, and **Print report** |
| Trend | `Trend.jsx` | line chart, one ward × 4 params, moving-average + breach band + anomaly markers; forecast row (status, ETA capped at the horizon, ±band, confidence) and an optional dashed 90-day projection |
| Anomalies | `Anomalies.jsx` | flagged table; click → the exact SQL that produced it (`SqlDrawer.jsx`) |
| Disagreements | `Disagreements.jsx` | "but the lab says compliant": probe breaches vs lab-confirmed breaches per ward × param, a verdict chip (`instrument_suspect` / `lab_confirmed` / `consistent`), and the ticket-worthy suspects called out above the table |
| Complaints | `Complaints.jsx` | triage queue, category chips, severity sort, "rule fired" tooltip, search |
| Leaderboard | `Leaderboard.jsx` | deteriorating wards bar |
| Simulator | `Simulator.jsx` | four weight sliders (default 35/30/15/20). `100·Σ(wᵢcᵢ)/Σwᵢ` reproduces `RISK_SCORE` exactly at shipped weights — the page prints the measured drift, and the top three keep the stored score beside the simulated one as proof |
| Briefing | `Briefing.jsx` | the three things to do today, chosen by `backend/brief.py` in a fixed priority order (rank → soonest crossing → instrument/complaints); watchlist, language chips (`EN` / `हिं` → `/api/brief?lang=`), copy-Markdown, download `.md` / `.csv` — all client-side `Blob`s, no write endpoint |
| Trust | `Trust.jsx` | "can I trust this number?": completeness, lab coverage and unusable-reading counts from `V_DATA_QUALITY` with the bands and findings decided in `backend/quality.py`; a lineage table (endpoint → SQL step → tables → the exact file, openable in place, with a copyable `run_sql.py` command); and an export panel (CSV, `.ics`, Atom URL, clear cached data). The measured `query_ms` is printed on the page |
| Ingest | `Ingest.jsx` | drop the WhatsApp file → parse stats → classified preview |
| Benchmark | `BenchmarkPage.jsx` | paired bars, "289k rows · N ms", replayable on stage |

### Chart.js discipline

Register only used controllers (`Line`, `Bar`, `Category`, `Linear` and
`Logarithmic` scales — the benchmark page plots milliseconds on a log axis, and a
scale that is not registered throws instead of degrading) plus
`normalized:true`, `animation:false`, `decimation:{algorithm:'lttb',samples:300}`
so payloads stay ≤50 KB and the UI stays smooth inside a 6 GB VM.

**`parsing` stays at its default.** Every dataset here is a primitive number array
with a separate `labels` array, and `parsing:false` makes Chart.js treat each number
as a pre-parsed `{x, y}` point — the axis then collapses to `NaN`. Both new charts
(Trend projection, benchmark log axis) were checked against that failure mode.

### Demo parachute

`VITE_MOCK=1` renders the identical UI with the DB down. `src/devMock.js`
answers every endpoint — including the four newer ones (`/heatmap`,
`/disagreements`, `/wards/{id}/forecast`, `/brief`) and the four new SQL
snippets — with the same UPPER_SNAKE keys the components already read, so no
component branches on `IS_MOCK`. Three rules keep the parachute honest:

- the mock derives `RISK_SCORE` from the same four components through the same
  weights, so the Simulator's "reproduces `RISK_SCORE` exactly" claim holds in
  mock mode too (measured drift `3.55e-15`);
- ward names are looked up from the one ward table rather than typed per tab;
- the newest heatmap month is the stored score, so the tile, the KPI and the case
  file cannot disagree.

`npm run dev:mock` starts Vite in that mode; `npm run build:mock` produces the
same static bundle for a no-DB stage fallback. The production build tree-shakes
the whole mock module because `IS_MOCK` is a compile-time `false`, so the real
bundle pays nothing for it.

`devMock.js` also answers the two newer JSON paths (`/api/data-quality`,
`/api/lineage`) and the `?lang=hi` brief, so the Trust page and the Hindi brief
render in mock mode too. Only the `.ics` and Atom links are marked "server-only"
there: they are file responses, not JSON, and faking them would be a lie.

### Export (`components/ExportCsvButton.jsx`)

One button, used on Leaderboard, Anomalies, Disagreements, Complaints, Briefing
and Trust. `download()` and `toCsv()` live in `pages/_shared.js` (plain JS, so no
JSX in a `.js` file); `toCsv` quotes every field and doubles embedded quotes per
RFC 4180. It is entirely client-side, so it works in `VITE_MOCK=1`, needs no
endpoint, and adds nothing to the SQL whitelist.

### Installable and offline (`public/sw.js`)

A hand-written service worker (~100 lines) rather than `vite-plugin-pwa` or
Workbox, because the project's rule is no new dependencies and the policy is one
sentence: **network first for navigation and `/api`, stale-while-revalidate for
assets**.

- `install` precaches `/`, `/index.html`, the manifest and the two icons —
  deliberately *not* the hashed bundle, so a rebuild cannot leave a precache entry
  pointing at a deleted file;
- `activate` deletes every cache whose name does not start with the current
  version, which is also the repair path for a worker that got stuck;
- non-`GET` requests pass straight through, so `/api/ingest/*` and `/api/classify`
  are never cached and no write is ever faked;
- a failed `/api` read falls back to the last successful response, and the topbar
  shows an **offline badge** so a stale cached view does not look like a hang;
- registration is `import.meta.env.PROD` only and sits outside React (StrictMode
  double-invokes effects), and it is fire-and-forget — a browser that refuses the
  worker still gets the app.

The demo: turn off Wi-Fi, reload, and the landing page, the dashboard and the last
Trust numbers still render with the badge on. If a bundle ever looks stale mid-demo,
**Trust → Clear cached data** empties `caches.keys()` and reloads — no DevTools.

---

## Demo Script (5 min, `docs/demo-script.md`)

1. Heatmap with one red corner → press `▶ Replay` (twelve months in ten seconds) → click the ward
2. Ward case file: four component bars that multiply out to the score, then **Print report**
3. Trend chart showing the monsoon turbidity breach + z-score annotation + the breach-ETA card
4. "But the lab says compliant" → Disagreements tab → the pH probe nobody has verified
5. Complaints tab shows the "kala paani / black water" messages
6. Paste `db/sql/sensor_vs_lab.sql` live into `exakit sql` and get the same number (the kit's ask → inspect-SQL → run → validate → rerun loop)
7. Briefing tab → three actions, copy the Markdown, switch to `हिं` and copy it again
8. Simulator → drag a weight, watch the ranking move, reset
9. Leaderboard → **Export CSV** and hand the judge the file
10. `/api/classify` on a judge-supplied sentence
11. Benchmark slide
12. **Trust tab** → "can I trust this number?": the completeness percentage, the findings the bands produce, and the lineage row that opens the exact SQL. Then **Breach calendar (.ics)** → open it in Calendar, and Trust → **Clear cached data** to show the offline cache is real and removable

### `scripts/run_demo.sh` — the stage artifact (not yet written)

When it exists it will: check `exakit status` → start if needed → build `dist` if
missing → uvicorn on 8000 → print one URL. One command, one terminal, one port,
nothing dependent on the internet. Today the same three steps are the three
commands in [Repository Layout](#repository-layout).

---

## Day-by-Day Schedule (Oct 23 → 25)

### Oct 23 (today)

Phase 0 to green (2 h cap) → repo scaffold → `10_schema.sql` + `30_generate_readings.sql` loaded → install all deps today (network is ~350 KB/s; a re-install later is a schedule risk).

### Oct 24

`40_anomaly_window.sql` → Lua UDF (cut-line 18:00) → materialize → 5 read endpoints → heatmap + trend + triage queue → ingest endpoints → freeze data generation → write `docs/prd.md`.

### Oct 25

Leaderboard + benchmark pages → `scripts/run_demo.sh` → rehearse twice back-to-back → screenshots → submit.

### Minimum believable demo (if Oct 24 evening is missed)

DB green → data loaded → anomaly view + leaderboard → 5 read endpoints → heatmap + trend + triage queue. Ship read-only + one live SQL moment and describe ingest as roadmap — it still answers the brief.

### Explicit cut list

No auth, no multi-user, no real-time WhatsApp gateway, no LLM APIs, no maps/geo, no TypeScript, no router *dependency* (a hand-written `hashchange` router is in), no cloud deploy, no persisted what-if scenarios or triage acknowledgements (the SELECT-only rule is worth more than the feature).

---

## Test Plan

```bash
backend/.venv/bin/python -m pytest backend/tests -q
# 199 passed, 17 skipped — the skips are the @requires_db live assertions,
# because the local Exasol database is not installed on this machine.
```

| File | Covers | DB needed |
|------|--------|-----------|
| `test_rules.py` | every rule fires on a known sentence; unknown → `other`; severity ordering | no |
| `test_parser.py` | both timestamp forms, `Media omitted`, multi-line, header/footer lines, non-English (Hinglish/romanised Marathi-Kannada) lines, the deliberately messy fixture | no |
| `test_forecast.py` | upward drift with an upper limit and downward drift with a lower limit (chlorine); zero/`None` slope; already-over-limit; horizon overflow; band widens monotonically and is `None` below 7 samples; confidence tiers; `breach_date` arithmetic | no |
| `test_brief.py` | exactly three actions; priority order; instrument-suspect beats complaints; every number in the text appears in the inputs; empty inputs produce the "no signal" line rather than a fabricated ward; markdown contains all three titles; **`lang="hi"` still returns three actions and keeps every input number; an unknown `lang` falls back to English; `lang="en"` is byte-identical to before** | no |
| `test_quality.py` | completeness/lab-coverage arithmetic; band boundaries at 0.98 / 0.95; empty input yields the `no data` finding and no fabricated grade; every finding's `DETAIL` quotes a number that exists in the inputs | no |
| `test_calendar_feed.py` | `\r\n` everywhere and no bare `\n`; every physical line ≤ 75 **octets** after folding; one `VEVENT` per deteriorating item only; UID stable across two builds; `STATUS:CONFIRMED`; comma/semicolon escaping in `SUMMARY`; zero items still yields a valid `VCALENDAR` | no |
| `test_atom_feed.py` | parses with `xml.etree.ElementTree`; three entries; ids stable across builds; `&`/`<` in a ward name are escaped; `updated` falls back when `DATA_AS_OF` is `None` | no |
| `test_lineage.py` | every `LINEAGE[i]["SQL_STEP"]` is a key of `SQL_WHITELIST`; every whitelisted step resolves to a file that exists on disk; no duplicate `ENDPOINT`; ≥12 endpoints | no |
| `test_sql_snapshots.py` | the 11 `db/sql/*.sql` files exist and obey the single-statement contract (`SELECT`, no `;`, a literal `LIMIT`), the 10 ODS files are present in pipeline order (including `46_data_quality_view.sql`), and — with a DB — each demo query returns rows, `V_WARD_FORECAST` has 96 rows, and the SQL countdown agrees with `backend/forecast.py` within a day | partly |

Manual checks:

- `db/70_verify.sql` — `DESCRIBE` asserts every table and column name after load (catches the quoted-identifier trap), and checks 16–17 assert `V_DATA_QUALITY` has ≥1000 rows with a non-zero `N_MISSING` (a view that returns zeros would be the bug)
- Run the pipeline twice → identical results (determinism)
- `npm --prefix frontend run build` **and** `npm --prefix frontend run build:mock`, then walk all **12** tabs in each; reload `#/ward/12` directly; print → PDF from the case file
- Trust tab → **Export CSV** opens in a spreadsheet; **Breach calendar (.ics)** opens in Calendar with a 7-day alarm; the Atom URL parses in a reader
- DevTools → Application → Service Workers → **offline** → reload: the landing page and dashboard still render and the topbar shows the offline badge. Trust → **Clear cached data** → reload recovers
- Each `db/sql/*.sql` is a single statement, so it also runs through `exakit sql --file`

---

## Risks & Mitigations

| # | Risk | Mitigation |
|---|------|------------|
| R1 | DB never comes up (vmnet no route to host, undocumented in kit docs) — highest-probability project-killer | 2 h cap; kill orphan PID 42445 + clear 192.168.64.0/24 conflicts first; resumable installer; Fallback B = OrbStack docker-db on 8563 with identical SQL; decide by 20:00 today |
| R2 | Orphan launcher daemon holds 127.0.0.1:8563 and wedges on `no route to host`, so `stop` and `destroy` both fail with "failed to remove Nano container" | Kill the daemon (`kill $(cat …/vm.pid)`, escalate to -KILL), which also clears the stale `bridge100`; `exasol destroy` then succeeds. Verified twice on this machine (PIDs 42445, 89468) |
| R3 | Python UDF attempted → fails (needs script-languages container) | Lua is the only UDF on the critical path; SQL WITH-clause drop-in keeps the same API shape |
| R4 | Lua UDF blocked on privileges/memory | Cut-line Oct 24 18:00; `40_anomaly_window.sql` already produces the same columns |
| R5 | 16 GB host − VM reservation = OOM with VM + Vite + uvicorn + Chrome + OrbStack | VM cut to the enforced 4096 MB floor; serve static dist (kills the Vite process); close OrbStack/Electron apps; `--workers 1`; rehearse the exact process set |
| R6 | Self-signed TLS breaks pyexasol | `websocket_sslopt={"cert_reqs": 0}`; smoke-test `db.py` before the UI exists; `exakit sql --json` fallback needs no TLS config |
| R7 | CORS blank dashboard | Single-origin static mount; Vite proxy in dev only |
| R8 | Stale materialized tables → wrong numbers on stage | Re-running `db/40_anomaly_window.sql` → `db/50_udf_ward_risk.lua.sql` → `db/60_materialize.sql` is three commands via `scripts/run_sql.py`; `LOAD_RUN` shown as "data as of …" in the footer (turns the risk into an honest feature) |
| R9 | After-boot DDL ACK'd but not persisted | Idempotent `CREATE OR REPLACE`, re-verify from a fresh connection |
| R10 | `sys` is admin and unsandboxed — a demo bug could DROP | Read endpoints are SELECT-only; no "clear tables" button wired to the demo; writes only via `db/` scripts |
| R11 | Slow network blocks a late npm/uv install | Install Oct 23, commit `package-lock.json`, keep caches warm |
| R12 | Judges catch an inflated perf claim (single node) | Report `node_count`; every on-screen number from `BENCHMARK_RESULTS`; claim only columnar scan + pushdown + pre-aggregation + result cache. `DISTRIBUTED BY` is not even in the DDL, so it cannot be misclaimed |
| R13 | Licence wording | Personal = free, no artificial data cap, personal-use EULA; hackathon/demo use fine, no commercial-deployment claim (`THIRD_PARTY_NOTICES.md`) |
| R14 | Service worker serves a stale bundle mid-demo | network-first for navigation and `/api`; version const bumped per release; **Clear cached data** button on Trust; registered only in `PROD`; no blind precache of hashed assets |
| R15 | The 289k-row quality view breaks the sub-second claim | the endpoint returns `query_ms` and the page prints it; documented fallback is a materialized table if it ever exceeds ~150 ms |
| R16 | Exasol dialect traps in the new view (`COMMENT ON VIEW`, `DATE_TRUNC`, `DISTRIBUTED BY`) | `COMMENT IS` on the `CREATE VIEW`, month via `SUBSTR(CAST(…))`, no distribution clauses — all three are already-burned rules in this repo |
| R17 | `.ics` rejected by Calendar | tests pin CRLF, octet folding and property escaping; dates come from `LAST_DATE`, not wall-clock, so the file is reproducible |
| R18 | Hindi strings drift from the English payload | `test_brief.py` asserts three actions and every input number survive in both languages; `t()` falls back to English, never to a raw key |

---

## Rejected Alternatives

| Alternative | Why rejected |
|-------------|--------------|
| Python UDF for anomaly/classification | Requires the `exasol/script-languages-release` container, absent from Exasol Personal local — would be load-bearing on an unverified capability. Lua is in-engine with the lowest documented overhead |
| 1M+ row dataset with sharded numpy CSV generation (Plan B) | Adds a Python generator + shard-loading pipeline for no demo benefit on a 2 vCPU / 6 GB single-node VM; 289k already sells "in-memory" honestly and reloads in seconds |
| Native materialized views | `CREATE MATERIALIZED VIEW` / `create_aggregate_view` unconfirmed (doc 404s on 7.1 and latest) — physical summary tables + `INSERT … SELECT` achieve the same latency with zero risk |
| Claiming `DISTRIBUTED BY` speedups | Wrong twice over: a single data node makes it meaningless, and the Personal build rejects the clause as a syntax error. Removed from the DDL entirely |
| Streamlit / dash-server add-on instead of React | User explicitly chose React + Vite + Chart.js. Marketplace dash-server noted only as an emergency fallback |
| CSV-snapshot backend with no DB (Plan C fallback level C) | Removes the entire Exasol premise of the hackathon entry — kept only as an absolute last resort, and it would require user sign-off |
| `exakit repair-runtime` to clear the bad state | Destroys data and is unnecessary — state is `deploymentFailed`, not `interrupted`. Requires explicit user consent regardless |
| Vite dev server during the demo | Extra Node process on a host also paying the VM its whole reservation, plus a CORS surface; static build served by FastAPI is faster and simpler |
| spaCy / transformers for complaint NLP | Multi-hundred-MB model downloads on a ~350 KB/s link, and unexplainable on stage. Stdlib regex rule table is free forever and queryable |
| Real WhatsApp Business API ingestion | Paid/credentialed (violates free-forever) and unnecessary — the brief's pain is exported chat logs, which a parser handles offline |

---

## Free-Forever Proof

| Component | Licence |
|-----------|---------|
| pyexasol | MIT |
| FastAPI | MIT |
| Vite | MIT |
| Chart.js | MIT |
| React | MIT |
| Exasol Personal | Free with no artificial data cap (personal-use EULA) |

No API keys, no credits, no cloud.

---

## `docs/prd.md` — generated from artifacts, never invented

Written last (Oct 24), derived from real sources so PRD and code cannot drift:

| PRD section | Source of truth |
|-------------|-----------------|
| Problem, users, why it matters, tracks | The chosen brief (Jal Board / ward officers, contamination clusters found after illness spikes) |
| Architecture & Environment | `exakit info --json` / `exakit status --json` — runtime 2.3.0, DSN 127.0.0.1:8563, credential file path only, never the secret |
| Data model & volumes | `db/10_schema.sql` + live `SYS.EXA_ALL_TABLES` row counts |
| Features | The tab list in `frontend/src/App.jsx` + the `@app.get` decorators in `backend/app/main.py` |
| Anomaly logic | `db/40_anomaly_window.sql` + the Lua UDF source |
| NLP rules | Table dumped from `nlp_rules.py` |
| Acceptance criteria | The pytest names + `db/sql/*.sql` |
| Free-forever proof | Licence table above |
| Performance | Measured ms from `/api/benchmark` on this laptop |
| Risks & limitations | This plan's risk table + honest disclosure of the single-node and Lua-only constraints |

Plus user stories, functional/non-functional requirements, out-of-scope list, and a "reproduce me" command block.