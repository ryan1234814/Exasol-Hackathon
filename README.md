**Pitch deck:** [`pitch-deck/WARDQ-Pitch-Deck.pdf`](pitch-deck/WARDQ-Pitch-Deck.pdf) (16 slides, 4.3 MB) · **Demo video:** [`brag-output-2026-10-31-1430/brag.mp4`](brag-output-2026-10-31-1430/brag.mp4) (2:55, 1080p, 18 MB)

# WARDQ — Ward-Level Water Quality & Complaint Triage

**ExaThon India 2026 · Civic / Sustainability track**

One page every morning: every ward ranked, every breach explained, every number
traceable to the SQL that produced it — built to catch a water failure *before*
the illness spike confirms it.

`Exasol Personal` · `Python 3.11 / FastAPI` · `React 18 + Vite + Chart.js` ·
`24 wards` · `288,768 readings` · `15,063 complaints` · `213 tests` · `MIT`

Slide 2 of the deck is the problem statement; [docs/COVER.md](docs/COVER.md) is the
same argument written out in one page.

---

## The problem

### Who has it

Three people need the same answer, and today none of them gets it in time.

**1. The ward health officer.** She holds 15,063 citizen complaints but not the
instruments, so her morning list is ordered by who complained loudest — not by
which ward is actually deteriorating. There is no dated forecast to rank against.

**2. The water utility engineer.** Probe alarms and lab confirmations live in two
registers that never meet. In one ward that looks like 22 pH probe breaches and
**zero** lab confirmations: he cannot tell a fouled electrode from contaminated
water, so the safe habit becomes discounting every alarm — including the one that
matters.

**3. The resident.** 1,002,700 people across 24 wards, 224,230 connections, and
**9 of the 24 wards sit downstream of the intake** — they pay for contamination
they did not produce. Their first warning is usually the clinic queue.

### Why it matters

A water supply emits three signals on three clocks: the **probe** (hours), the
**lab** (7–14 days), and the **clinic** (weeks). Almost every municipal dashboard
reports the last one, because it is the only one with a number already attached.

That is the whole gap. By the time illness confirms the failure, the exposure
window has closed and the only remaining action is response, not prevention.

On this dataset, today:

| Measure | Value |
|---|---|
| Residents served by the 24 wards | **1,002,700** |
| Ward × parameter pairs already past their limit | **24 of 96** |
| Notice available before the next crossing (Ward 191, turbidity) | **26 days** |
| Crossings that appear in an illness report yet | **0** |
| Readings usable for a monthly mean | **97.01%** (253 of 8,448 cells have no result) |

Between the probe and the clinic there are roughly **three weeks** in which a
flushing order, a chlorine correction or a probe calibration still changes the
outcome. Nothing in the municipal stack is built to act inside that window.
That window is the product.

### What WARDQ does about it

It computes the risk from the instruments first, corroborates it with the
citizens second, and dates the forecast:

> `Ward 191 · Turbidity 4.695 NTU · +0.0118/day · crosses the 5 NTU limit in 26 days`

Every figure on every screen names the SQL file behind it, and the dashboard
publishes its own defect rate instead of hiding it.

---

## Overview

WARDQ is a read-only analytics surface over one Exasol schema (`WARDQ`). The
engine does the work — window functions, a Lua `RISK_SCORE` UDF, pre-aggregated
materialisations — and the application only ever reads answers.

| Layer | What it is |
|---|---|
| **Data** | 10 tables, 10 analytical views, 1 Lua UDF, 2 materialisations loading 288,768 readings and 15,063 classified complaints |
| **Analytics** | 30-day rolling z-scores, breach islands and runs, a 12-month deterioration slope, a 90-day breach forecast with a widening band, probe-vs-lab verdicts |
| **API** | 22 JSON endpoints (FastAPI, stdlib-only otherwise), plus `.ics`, Atom and SQL-source routes |
| **UI** | 12-tab PWA: heatmap replay, case file, trend, anomalies, disagreements, complaint triage, leaderboard, simulator, brief, trust, ingest, benchmark |
| **Output** | Morning brief as Markdown / CSV, breach calendar as `.ics`, brief as an Atom feed, offline cache |

### The twelve tabs

| Tab | Answers |
|---|---|
| **Dashboard** | Which ward is worst today — a 24 × 13 risk heatmap with a month replay |
| **Wards** | Why: four weighted components that multiply out to `RISK_SCORE`, plus the 13-month ribbon |
| **Trend** | What the series does, with a 90-day projection and breach ETA |
| **Anomalies** | Which ward × parameter was flagged, and the exact SQL that flagged it |
| **Disagreements** | Which alarms are instrument suspects, which are lab-confirmed |
| **Complaints** | What citizens reported, triaged by 169 explainable patterns |
| **Leaderboard** | Who is deteriorating fastest |
| **Simulator** | What happens if the weights change — reproduce the score without storing anything |
| **Briefing** | The three things to do today, in English or Hindi, downloadable |
| **Trust** | Can I believe this number — completeness, lineage, exports |
| **Ingest** | Drop a WhatsApp export or CSV, see the parse and the classification |
| **Benchmark** | Why Exasol: measured milliseconds against SQLite and Python |

---

## Setup

Prerequisites: Python 3.11, Node 18+, and a running Exasol Personal instance on
`127.0.0.1:8563` (the starter kit installs it). Full detail and repair paths are
in [setup.md](setup.md); the short version:

```bash
# 0. database
exasol status                 # expect: Status: running
exasol start                  # if stopped

# 1. backend (venv already present in this checkout)
uv venv backend/.venv --python python3.11
backend/.venv/bin/pip install -r backend/requirements.txt

# 2. frontend
npm --prefix frontend install
npm --prefix frontend run build

# 3. load the schema once (pipeline order matters)
for f in db/10_schema.sql db/20_seed_dims.sql db/30_generate_readings.sql \
         db/40_anomaly_window.sql db/45_forecast_view.sql \
         db/46_data_quality_view.sql db/50_udf_ward_risk.lua.sql \
         db/60_materialize.sql db/70_verify.sql; do
  backend/.venv/bin/python scripts/run_sql.py $f
done
```

The database connection is read from the environment, never from the repo:

| Variable | Purpose |
|---|---|
| `EXAKIT_DSN` | DSN, default `127.0.0.1:8563` |
| `EXAKIT_PASSWORD_FILE` | file holding the `sys` password (default: resolved from the local deployment) |
| `EXASOL_DEPLOYMENT_DIR` | non-default Exasol deployment directory |

No credential is committed, and `.env`, `secrets.json` and `credentials/` are
gitignored.

---

## Run guide

**Production / demo — one process, one origin, port 8000:**

```bash
backend/.venv/bin/uvicorn backend.app:app --port 8000
# open http://127.0.0.1:8000
```

`backend/app.py` serves `frontend/dist` at `/`, so there is no second server and
no CORS. Health check:

```bash
curl http://127.0.0.1:8000/api/health     # database: up, mock: false
```

**Development (hot reload, `/api` proxied to :8000):**

```bash
backend/.venv/bin/uvicorn backend.app:app --port 8000   # terminal 1
npm --prefix frontend run dev                           # terminal 2
```

**No database at all** (identical UI on mock data — the stage parachute):

```bash
npm --prefix frontend run dev:mock        # dev server
npm --prefix frontend run build:mock      # static bundle for a no-DB fallback
```

**Rebuild the UI** after frontend changes, then reload:

```bash
npm --prefix frontend run build
```

### Useful routes once it is up

| Thing | Where |
|---|---|
| Landing page | <http://127.0.0.1:8000> |
| Dashboard | <http://127.0.0.1:8000/#/dashboard> |
| A ward case file | <http://127.0.0.1:8000/#/ward/24> |
| Morning brief (JSON) | <http://127.0.0.1:8000/api/brief> |
| Hindi brief | <http://127.0.0.1:8000/api/brief?lang=hi> |
| Breach calendar | `curl -OJ http://127.0.0.1:8000/api/forecast.ics` |
| Brief as Atom | <http://127.0.0.1:8000/feed/brief.xml> |
| Data quality | <http://127.0.0.1:8000/api/data-quality> |
| Lineage registry | <http://127.0.0.1:8000/api/lineage> |

Five-minute walkthrough: press **Replay** on the dashboard, open Ward 205,
compare it with **Disagreements**, read the **Briefing**, then open **Trust** and
click a lineage row to see the SQL behind the number.

---

## Deployment

The app is one long-lived `uvicorn` process serving both the API and a static
bundle, plus a reachable Exasol instance. That is the whole topology.

### Local production (what the demo runs)

```bash
npm --prefix frontend run build
backend/.venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

### On a server

1. Clone the repository and create the venv (see [Setup](#setup)).
2. Build the frontend **on the machine that will serve it** — `frontend/dist` is
   gitignored, so a fresh clone has no bundle until `npm run build` runs.
3. Export the connection settings, then start the process:

   ```bash
   export EXAKIT_DSN="<host>:8563"
   export EXAKIT_PASSWORD_FILE="/etc/wardq/exasol.pass"   # root-readable only
   backend/.venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port 8000 --workers 1
   ```

4. Put a TLS reverse proxy in front of port 8000. The app speaks plain HTTP and
   expects to be the only origin:

   ```nginx
   location / {
     proxy_pass http://127.0.0.1:8000;
     proxy_set_header Host $host;
     proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
   }
   ```

   Service workers (offline cache, installable PWA) need a secure context —
   `https://` in a deployment, `localhost`/`127.0.0.1` locally.

### Operational notes

- **Read-only by construction.** Every request path issues `SELECT`s; the only
  writes are the `db/*.sql` pipeline scripts, run deliberately.
- **One worker.** The app holds a single lazily-created pyexasol connection with
  one reconnect attempt; `--workers 1` keeps that honest.
- **Database down is a degraded state, not a crash.** `/api/health` reports
  `database: down` and the UI says so; the landing page renders with zero API calls.
- **Rebuilding data** is idempotent: re-run `db/30_generate_readings.sql` →
  `db/60_materialize.sql` → `db/70_verify.sql`.
- **PWA cache.** If a bundle looks stale after a deploy, bump `CACHE_VERSION` in
  `frontend/public/sw.js` and rebuild, or use **Trust → Clear cached data**.
- No container image, IaC or CI pipeline is included; there is nothing hidden to
  reproduce.

---

## Data honesty & limits

Stated here rather than discovered by a judge:

- **The readings are generated.** 288,768 samples and 15,063 complaints are
  synthesised in SQL, with monsoon intrusions, a chronic under-dosing ward, a
  coliform cluster and probe drift planted on purpose. The pipeline, the SQL and
  the detectors are real; the water is not.
- **3% of readings are unusable** (253 of 8,448 cells). They are excluded from
  means, counted in completeness, and shown on the **Trust** tab.
- **One node, no replication.** Exasol Personal, 2 vCPU / 6 GB, no
  `DISTRIBUTED BY` anywhere in the DDL, and no distributed claim in the UI.
- **The forecast is an OLS line over a trailing 12 months** with a band that
  widens as `sqrt(days / 7)` — a triage instrument, not a hydrology model.
- **Benchmarks are single-laptop measurements**, re-runnable from the
  **Benchmark** tab: 15 ms vs 96 ms on the same 288k-row scan, 7 ms vs 19 ms for
  ward z-scores, 11,231 bytes on the wire.

---

## Data sources, licences & third-party tools

### Where the data comes from

Every row in this repository is either generated in SQL or Python, or written by
hand for this project. Nothing is scraped, licensed in, or redistributed from a
third party.

| Source | What it is | Lives in | Terms |
|---|---|---|---|
| **Sample logs** | 288,768 readings generated in SQL: 24 wards × 4 parameters × 752 days × 4 stations, 2024-10-01 → 2026-10-21, with seeded signals (monsoon turbidity, chlorine under-dosing, a coliform cluster, probe drift) | `db/30_generate_readings.sql` | Generated by this project — MIT |
| **WhatsApp export fixtures** | Three hand-written ward exports in the messy shape a real group chat has: emoji, Hinglish, forwarded chains, missing timestamps | `data/raw/whatsapp_ward_exports/*.txt` | Written for this repo — MIT |
| **Complaint corpus** | The fixtures, parsed and then scaled on top of a **fixed random seed** so 15,063 complaints rerun identically | `backend/ingest/load_complaints.py` | Generated by this project — MIT |
| **Ward dimension** | 24 ward names drawn from real Mumbai and Bengaluru municipal wards, with **illustrative** population and connection figures, not an official census extract | `db/20_seed_dims.sql` | Written for this repo — MIT |
| **Thresholds** | Per-parameter limits aligned to **BIS 10500:2012** acceptability ranges, stored as data so they can be edited without a redeploy | `db/20_seed_dims.sql` | Reference to a public standard; no BIS content is copied |
| **Demo upload** | An 18-line CSV and the ingestion path it exercises (`openpyxl` for `.xlsx`) | `data/raw/sample_logs_demo.csv` | Written for this repo — MIT |
| **Benchmark artefacts** | The SQLite mirror and measured results the Benchmark tab quotes | `data/derived/` | Generated by this project — MIT |

Because none of it is third-party data, the repository needs no data licence
agreement, attribution notice or redistribution clause. If you replace the
generator with a real ULB feed, that feed's terms are yours to satisfy — the
README and the Trust tab both name the generator as the provenance boundary.

### APIs

**Inbound, owned by this app.** One process on port 8000 exposes 22 JSON
routes, plus an `.ics` calendar, an Atom feed and a SQL-source route, all
documented in the [run guide](#useful-routes-once-it-is-up). There is no
authentication layer because there is no second tenant: the app is designed to
run on one municipal host behind a reverse proxy.

**Outbound: none.** At run time the app calls no third-party API. No telemetry,
no analytics, no CDN, no web fonts, no map tiles, no email gateway, no cloud
storage — the frontend ships system fonts and hand-written JS, and the only
network peer is the Exasol instance on `127.0.0.1:8563`. File ingestion is a
local upload (`python-multipart`, `openpyxl`), not a cloud round-trip. Uploads
and exports are also why **no API key, token or account is needed anywhere in the
product**.

**Consumed, not depended on at run time:** the `exasol` CLI from the starter kit
starts and stops the database. If it is absent, a running instance is still
enough.

### Third-party tools and their licences

Direct dependencies, with the versions resolved in this checkout and the licence
each one declares. Runtime pins live in `backend/requirements.txt` and
`frontend/package.json`; the lockfile is `frontend/package-lock.json`.

| Component | Version | Licence | Used for |
|---|---|---|---|
| **Exasol Personal** | local deployment | Exasol personal-use EULA | The engine: window functions, the Lua UDF, materialisations |
| `pyexasol` | 3.0.1 | MIT | The only database driver; one connection, one reconnect |
| `fastapi` | 0.161.1 | MIT | The 22 JSON routes |
| `starlette` | 1.9.0 | BSD-3-Clause | ASGI toolkit underneath FastAPI (transitive) |
| `pydantic` | 2.14.1 | MIT | Request/response models (transitive) |
| `uvicorn` | 0.54.0 | BSD-3-Clause | Serving the API and the static bundle |
| `python-multipart` | 0.0.32 | Apache-2.0 | Multipart file uploads on the ingest tab |
| `openpyxl` | 3.1.5 | MIT | Reading `.xlsx` sample logs |
| `react`, `react-dom` | 18.3.1 | MIT | The 12-tab UI |
| `chart.js` | 4.6.1 | MIT | Trend, forecast and benchmark charts |
| `react-chartjs-2` | 5.3.1 | MIT | React binding for Chart.js |
| `vite`, `@vitejs/plugin-react` | 5.4.21 / 4.7.0 | MIT | Build and dev server only — not shipped |
| `pytest` | 9.1.1 | MIT | The 213-test suite (in the venv, not a runtime pin) |
| Google Chrome (headless) | build-time only | Proprietary, used as installed | Prints `pitch-deck/WARDQ-Pitch-Deck.pdf`; not a runtime dependency |

Three notes a reviewer will ask about:

- **Versions move.** `package.json` uses caret ranges, so a fresh `npm install`
  may resolve newer patch releases; the licence column follows the package
  metadata, not a guess.
- **Nothing copyleft, nothing viral.** The direct set is MIT, BSD-3-Clause and
  Apache-2.0 only, so redistribution of this repository's code carries no
  source-disclosure obligation and needs no `NOTICE` file. Every transitive
  package ships its own licence text inside `node_modules/` or the virtualenv.
- **Exasol Personal is not redistributed.** The engine is installed locally by
  the starter kit and runs under its personal-use EULA; this repository contains
  only SQL, Python, JavaScript and documentation.

---

## Testing

```bash
backend/.venv/bin/python -m pytest backend/tests -q     # 213 tests
```

The suite mixes pure-Python units (rules, parser, forecast, brief, quality,
`.ics`, Atom) with SQL snapshot tests that execute against the live database.
Database-backed tests **fail loudly** when Exasol is unreachable rather than
silently skipping; `scripts/run_sql.py db/70_verify.sql` re-checks row counts
from a fresh connection.

---

## Project structure

```
backend/     app.py (22 endpoints)  db.py (the only DB seam)  nlp_rules.py
             forecast.py  brief.py  quality.py  calendar_feed.py  atom_feed.py
             benchmark.py  ingest/  tests/ (213 tests)
db/          10_schema → 70_verify (pipeline)  sql/ (11 saved demo queries)
frontend/    src/pages (12 tabs)  src/components  public/ (PWA)  vite.config.js
data/        raw/ (WhatsApp exports, sample logs)  derived/ (benchmark mirror)
scripts/     run_sql.py
pitch-deck/  WARDQ-Pitch-Deck.pdf + deck.html + captured screenshots
docs/        COVER.md (the problem statement) · ENGINEERING.md (the build record)
setup.md     install, run and repair commands
LICENSE      MIT
```

The long-form engineering record — locked decisions, measured memory footprint,
risk table, rejected alternatives — lives in
[docs/ENGINEERING.md](docs/ENGINEERING.md).

---

## Licence

Released under the [MIT Licence](LICENSE).

Third-party components are permissively licensed — MIT, BSD-3-Clause and
Apache-2.0 — and listed with versions in
[Data sources, licences & third-party tools](#data-sources-licences--third-party-tools).
Exasol Personal is free to use under its personal-use EULA. Nothing here needs
an API key, a credit card or a cloud account.
