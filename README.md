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
and is now `database_ready` on `127.0.0.1:8563`; `WARDQ` is loaded with 288,768
sample rows, all eight analytical window views, and the Lua `RISK_SCORE` UDF,
with every planted signal verified by live queries. The original blocker — an
orphan `launcher __daemon__` holding the port forwarder while `bridge100` pointed
at a dead VM address — is documented in risk R2 with the repair that worked.
Because `exapump` was never installed by a raw `exasol deploy`, SQL is run with
`scripts/run_sql.py` against the same `backend/db.py` seam the API uses.

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
| Language | Plain JS (no TypeScript), no router, no state lib | 2-day solo build |

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
                40_anomaly_window.sql  50_udf_ward_risk.lua.sql  60_materialize.sql
                70_verify.sql  sql/*.sql (6 saved demo queries)

data/           raw/whatsapp_ward_exports/*.txt  raw/sample_logs_demo.csv
                derived/*.csv (fallback snapshots)  generated/README.md

backend/        app.py  db.py  nlp_rules.py  ingest/whatsapp_parser.py
                ingest/tabular.py  benchmark.py  requirements.txt  tests/

frontend/       index.html  vite.config.js  src/{App.jsx,api.js,devMock.js,
                pages/*,components/*,styles.css}

Makefile  run_demo.sh  README.md  THIRD_PARTY_NOTICES.md  .gitignore
```

Makefile targets are the **only** entry points: `bootstrap` · `gen` · `load` · `refresh` · `api` · `web` · `build` · `bench` · `demo` · `reset`.

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

### `db/50_udf_ward_risk.lua.sql`

```sql
CREATE OR REPLACE LUA SCALAR SCRIPT WARDQ.RISK_SCORE(
  Z DOUBLE, BREACH_RATIO DOUBLE, SLOPE DOUBLE, COMPLAINT_DENSITY DOUBLE
) RETURNS DOUBLE
```

~40 lines, documented weights, clamped 0–100. Lua is on the critical path **only** for scoring; if it fails, the same expression is a `WITH` clause in `60_materialize.sql` and zero UI change results.

### `db/60_materialize.sql`

`TRUNCATE` + `INSERT … SELECT` from the views/UDF into `WARD_MONTH_RISK`, `ANOMALY_EVENT`, `COMPLAINT_SUMMARY`, stamping `GENERATED_AT`. `db/70_verify.sql` re-checks row counts from a fresh connection (the DB can ACK a DDL batch right after first boot without persisting it).

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

### Endpoints — reads hit materialized tables only (never the raw 300k, never a live UDF)

| Method · Path | Returns |
|---------------|---------|
| `GET /api/health` | DB reachability + `GENERATED_AT` |
| `GET /api/wards` | ward list + latest risk score |
| `GET /api/wards/{id}/trend?param=` | ≤500 points, server-side bucketed |
| `GET /api/anomalies?month=` | flagged ward×param rows |
| `GET /api/leaderboard` | deteriorating wards by risk |
| `GET /api/complaints?category=&ward=&q=` | triage queue, `LIMIT`-paged |
| `GET /api/summary` | header metrics + "data as of" |
| `POST /api/ingest/chat` | multipart `.txt` → parse + classify preview, does not write (safely re-runnable on stage) |
| `POST /api/ingest/logs` | CSV/XLSX → staging rows + validation report |
| `POST /api/classify` | one sentence → category + which rule fired |
| `GET /api/benchmark` | measured timings (below) |

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

Plus `chart.js`, `react-chartjs-2` only. `vite.config.js` dev proxy `/api` → `http://127.0.0.1:8000`. Plain JS, tab-switch state (no router).

| Tab | Component | Note |
|-----|-----------|------|
| Morning view | `Dashboard.jsx` | ward × month risk heatmap as a CSS grid of coloured cells — no chart lib, cannot break |
| Trend | `Trend.jsx` | line chart, one ward × 4 params, moving-average + breach band + anomaly markers |
| Anomalies | `Anomalies.jsx` | flagged table; click → the exact SQL that produced it (`SqlDrawer.jsx`) |
| Complaints | `Complaints.jsx` | triage queue, category chips, severity sort, "rule fired" tooltip, search |
| Leaderboard | `Leaderboard.jsx` | deteriorating wards bar |
| Ingest | `Ingest.jsx` | drop the WhatsApp file → parse stats → classified preview |
| Benchmark | `BenchmarkPage.jsx` | paired bars, "300,000 rows · N ms", replayable on stage |

### Chart.js discipline

Register only used controllers; `parsing:false`, `normalized:true`, `animation:false`, `decimation:{algorithm:'lttb',samples:300}` so payloads stay ≤50 KB and the UI stays smooth inside a 6 GB VM.

### Demo parachute

`scripts/snapshot_api.py` dumps every API response to `src/mock/*.json`; `VITE_MOCK=1` renders the identical UI with the DB down.

---

## Demo Script (5 min, `docs/demo-script.md`)

1. Heatmap with one red corner → click the ward
2. Trend chart showing the monsoon turbidity breach + z-score annotation
3. "But the lab says compliant"
4. Complaints tab shows 40 "kala paani / black water" messages
5. Paste `db/sql/complaint_vs_lab_disagreement.sql` live into `exakit sql` and get the same number (the kit's ask → inspect-SQL → run → validate → rerun loop)
6. Leaderboard
7. `/api/classify` on a judge-supplied sentence
8. Benchmark slide

### `run_demo.sh` — the stage artifact

Check `exakit status` → start if needed → build `dist` if missing → uvicorn on 8000 → print one URL. One command, one terminal, one port, nothing dependent on the internet.

---

## Day-by-Day Schedule (Oct 23 → 25)

### Oct 23 (today)

Phase 0 to green (2 h cap) → repo scaffold → `10_schema.sql` + `30_generate_readings.sql` loaded → install all deps today (network is ~350 KB/s; a re-install later is a schedule risk).

### Oct 24

`40_anomaly_window.sql` → Lua UDF (cut-line 18:00) → materialize → 5 read endpoints → heatmap + trend + triage queue → ingest endpoints → freeze data generation → write `docs/prd.md`.

### Oct 25

Leaderboard + benchmark pages → `run_demo.sh` → rehearse twice back-to-back → screenshots → submit.

### Minimum believable demo (if Oct 24 evening is missed)

DB green → data loaded → anomaly view + leaderboard → 5 read endpoints → heatmap + trend + triage queue. Ship read-only + one live SQL moment and describe ingest as roadmap — it still answers the brief.

### Explicit cut list

No auth, no multi-user, no real-time WhatsApp gateway, no LLM APIs, no maps/geo, no TypeScript, no router, no cloud deploy.

---

## Test Plan

- `backend/tests/test_rules.py` — every rule fires on a known sentence; unknown → `other`; severity ordering
- `backend/tests/test_parser.py` — both timestamp forms, `Media omitted`, multi-line, header/footer lines, non-English (Hinglish/romanised Marathi-Kannada) lines, the deliberately messy fixture
- `backend/tests/test_sql_snapshots.py` — each `db/sql/*.sql` runs against the live DB with a row-count assertion (proves the planted signals are actually detectable)
- `db/70_verify.sql` — `DESCRIBE` asserts every table + column name after load (catches the quoted-identifier trap)
- Manual: `make refresh` twice → identical results (determinism); `VITE_MOCK=1` renders all 7 tabs
- Each `db/sql/*.sql` is a single statement so it also runs through `exakit sql --file`

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
| R8 | Stale materialized tables → wrong numbers on stage | `make refresh` one command; `LOAD_RUN` shown as "data as of …" in the footer (turns the risk into an honest feature) |
| R9 | After-boot DDL ACK'd but not persisted | Idempotent `CREATE OR REPLACE`, re-verify from a fresh connection |
| R10 | `sys` is admin and unsandboxed — a demo bug could DROP | Read endpoints are SELECT-only; no "clear tables" button wired to the demo; writes only via `db/` scripts |
| R11 | Slow network blocks a late npm/uv install | Install Oct 23, commit `package-lock.json`, keep caches warm |
| R12 | Judges catch an inflated perf claim (single node) | Report `node_count`; every on-screen number from `BENCHMARK_RESULTS`; claim only columnar scan + pushdown + pre-aggregation + result cache. `DISTRIBUTED BY` is not even in the DDL, so it cannot be misclaimed |
| R13 | Licence wording | Personal = free, no artificial data cap, personal-use EULA; hackathon/demo use fine, no commercial-deployment claim (`THIRD_PARTY_NOTICES.md`) |

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