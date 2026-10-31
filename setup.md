# Setup, run and deployment guide

Everything needed to go from a clean checkout to the dashboard on
<http://127.0.0.1:8000>. All paths are relative to the repository root
(`/Users/ryangeorge/exasol/` in this checkout).

Start the components in this order: **database → backend → frontend**.
The [README](README.md) explains the problem the app solves and what each tab
does; [docs/COVER.md](docs/COVER.md) is the one-page problem statement and
[pitch-deck/WARDQ-Pitch-Deck.pdf](pitch-deck/WARDQ-Pitch-Deck.pdf) is the deck.
This file is the operational manual.

---

## Overview

WARDQ is a read-only analytics surface over one Exasol schema (`WARDQ`): the
database computes the risk scores, forecasts and verdicts, and the FastAPI
process serves both the JSON API and the built React bundle on one origin. The
frontend build is a static folder (`frontend/dist`); there is no second server in
production.

| Component | Port | Started by |
|---|---|---|
| Exasol Personal | `127.0.0.1:8563` | `exasol start` |
| API + built UI | `127.0.0.1:8000` | `uvicorn backend.app:app` |
| Vite dev server (optional) | `5173` | `npm --prefix frontend run dev` |

---

## Prerequisites

- **Python 3.11** (not 3.14 — wheel availability for `pyexasol`).
- **Node 18+** and npm.
- **Exasol Personal** on `127.0.0.1:8563`, at least 4 GB reserved (this checkout
  runs at 6144 MB). The `exasol` CLI is provided by the Exasol starter kit.
- No internet is required at run time; the app never calls out.

---

## 1. Database

```bash
exasol status          # expect: Status: running
exasol start           # if stopped
exasol stop            # to shut it down
```

Then confirm it actually answers, not just that the process exists:

```bash
backend/.venv/bin/python scripts/run_sql.py db/70_verify.sql
```

### Load or reload the schema (first run, or after a rebuild)

The order matters — later steps read views and tables created by earlier ones:

```bash
for f in db/10_schema.sql db/20_seed_dims.sql db/30_generate_readings.sql \
         db/40_anomaly_window.sql db/45_forecast_view.sql \
         db/46_data_quality_view.sql db/50_udf_ward_risk.lua.sql \
         db/60_materialize.sql db/70_verify.sql; do
  backend/.venv/bin/python scripts/run_sql.py $f
done
```

- `45_forecast_view.sql` only needs `WARD_DAILY` and `V_WARD_PARAM_SLOPE`.
- `46_data_quality_view.sql` creates `V_DATA_QUALITY`; it writes no data and must
  run **after** `30_generate_readings.sql`.
- `61_materialize_no_udf.sql` is the drop-in replacement for `60_materialize.sql`
  if the Lua UDF is unavailable.
- Every step is idempotent; re-running the loop is the standard repair.

### If `status` says `database_connection_failed` (wedged launcher)

The launcher daemon can hold port 8563 while the VM guest is dead:

```bash
exasol stop                       # if it hangs, kill the daemon directly:
kill $(cat ~/.exasol/personal/deployments/default/local/runtime/vm.pid)
exasol start
```

If the status stays stale, run `exasol start` **from Terminal.app** — this has
restored the deployment with `data.img` intact when other shells did not.

> Never run `exasol repair-runtime` or `destroy` to "fix" a status: they discard
> data.

---

## 2. Backend

First-time setup only (the venv already exists in this checkout):

```bash
uv venv backend/.venv --python python3.11
backend/.venv/bin/pip install -r backend/requirements.txt
```

Run it — this single process serves the API **and** the built UI:

```bash
backend/.venv/bin/uvicorn backend.app:app --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/api/health     # database: up, mock: false
```

### Connection settings

Nothing is hardcoded in the repo:

| Variable | Purpose | Default |
|---|---|---|
| `EXAKIT_DSN` | Exasol DSN | `127.0.0.1:8563` |
| `EXAKIT_PASSWORD_FILE` | file containing the `sys` password | resolved from the local deployment |
| `EXASOL_DEPLOYMENT_DIR` | non-default Exasol deployment directory | kit default |

The password is read from a file at request time and never printed or logged.

### Tests

```bash
backend/.venv/bin/python -m pytest backend/tests -q       # 213 tests
```

Database-backed tests fail loudly when Exasol is down rather than skipping, so a
green run means the live queries really executed.

---

## 3. Frontend

### Production (what the demo runs)

No separate process — the backend above serves `frontend/dist`:

```bash
npm --prefix frontend install      # first time only
npm --prefix frontend run build    # after any frontend change
```

The production bundle registers the service worker in `frontend/public/sw.js`,
so once it is served from `http://127.0.0.1:8000` the dashboard is installable
(Chrome: **Install app**) and reloads with the network off. Service workers need
a secure context — `localhost` and `127.0.0.1` count; a plain-HTTP LAN address
does not, and there the app runs without the cache.

If a cached bundle looks stale, use **Trust → Clear cached data**, or bump
`CACHE_VERSION` in `frontend/public/sw.js` and rebuild.

### Development (hot reload, `/api` proxied to port 8000)

```bash
npm --prefix frontend run dev        # needs the backend running on :8000
npm --prefix frontend run dev:mock   # full UI on mock data, no database needed
```

`dev:mock` is the stage parachute: identical UI, identical payload shapes, no
database. `npm run build:mock` produces the same fallback as a static bundle.

---

## Run guide

| Goal | Command |
|---|---|
| Full stack (demo) | `exasol start` → `backend/.venv/bin/uvicorn backend.app:app --port 8000` |
| Open the app | <http://127.0.0.1:8000> |
| Dashboard | <http://127.0.0.1:8000/#/dashboard> |
| A ward case file | <http://127.0.0.1:8000/#/ward/24> |
| Hot-reload UI | `npm --prefix frontend run dev` |
| UI with no database | `npm --prefix frontend run dev:mock` |
| Rebuild the bundle | `npm --prefix frontend run build` |
| Run any SQL file | `backend/.venv/bin/python scripts/run_sql.py db/NN_name.sql` |
| Download the breach calendar | `curl -OJ http://127.0.0.1:8000/api/forecast.ics` |
| Subscribe to the brief | open <http://127.0.0.1:8000/feed/brief.xml> in a feed reader |
| Hindi briefing | `curl 'http://127.0.0.1:8000/api/brief?lang=hi'` |
| Data-quality JSON | `curl http://127.0.0.1:8000/api/data-quality` |
| Provenance registry | `curl http://127.0.0.1:8000/api/lineage` |
| Backend tests | `backend/.venv/bin/python -m pytest backend/tests -q` |

### Five-minute walkthrough

1. **Dashboard** — press `▶ Replay` to sweep 13 months; the newest month is `live`.
2. Click **Ward 205 – Peenya** — the four weighted bars multiply out to 75.4.
3. **Trend** — enable *show 90-day projection*; the breach ETA is dated, not vague.
4. **Disagreements** — 22 pH probe breaches with 0 lab confirmations is an
   instrument problem, not a water problem.
5. **Briefing** — three ranked actions; download the `.md` and the actions `.csv`;
   switch to `हिं`.
6. **Trust** — completeness, the defect rate, and a lineage row that opens the
   exact SQL. Export the `.ics` and open it in Calendar.
7. **Benchmark** — replayable timings against SQLite on the same laptop.

---

## Deployment

The topology is one `uvicorn` process serving the API and the static bundle, plus
a reachable Exasol instance. Nothing else is required.

### Local production (the demo)

```bash
npm --prefix frontend run build
backend/.venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

### On a server

1. Clone the repository and create the venv (see [Backend](#2-backend)).
2. Build the frontend **on the serving machine** — `frontend/dist` is gitignored,
   so a fresh clone has no bundle until `npm run build` runs.
3. Export the connection settings and start the process:

   ```bash
   export EXAKIT_DSN="<host>:8563"
   export EXAKIT_PASSWORD_FILE="/etc/wardq/exasol.pass"
   backend/.venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port 8000 --workers 1
   ```

4. Front it with a TLS reverse proxy (the PWA needs `https://` off-localhost):

   ```nginx
   location / {
     proxy_pass http://127.0.0.1:8000;
     proxy_set_header Host $host;
     proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
   }
   ```

### Deployment checklist

- [ ] `exasol status` is `running` and `db/70_verify.sql` passes.
- [ ] `frontend/dist` exists and is newer than the last source change.
- [ ] `curl /api/health` reports `database: up, mock: false`.
- [ ] Port 8000 is bound to loopback only when a proxy is in front.
- [ ] No credential, `.env` or `secrets.json` is present in the tree.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `database_connection_failed`, port 8563 held | orphan launcher daemon | kill `…/runtime/vm.pid`, `exasol start` (from Terminal.app if needed) |
| `database: down` in `/api/health` | database stopped | `exasol start`, then reload |
| Dashboard renders but every panel is empty | stale materialisations | re-run `db/40_anomaly_window.sql` → `db/60_materialize.sql` → `db/70_verify.sql` |
| `object WARDQ.V_DATA_QUALITY not found` | quality view never built | `run_sql.py db/46_data_quality_view.sql` |
| UI shows an old build after deploy | service worker cache | bump `CACHE_VERSION` in `frontend/public/sw.js` and rebuild, or **Trust → Clear cached data** |
| Blank page, no network calls | `frontend/dist` missing | `npm --prefix frontend run build` |
| Dev server `/api` 404s | backend not on :8000 | start uvicorn first; the Vite proxy targets port 8000 |
| Lua UDF unavailable | Personal build without script languages | run `db/61_materialize_no_udf.sql` instead of `60_materialize.sql` |
