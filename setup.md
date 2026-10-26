# Setup & Run Commands

All paths relative to `/Users/ryangeorge/exasol/`. Start the components in this
order: **database → backend → frontend**.

---

## 1. Exasol Database

```bash
# Check status
exasol status

# Start (if stopped)
exasol start

# Stop
exasol stop
```

Healthy output: `Status: running`. The database listens on `127.0.0.1:8563`.

### If `status` says `database_connection_failed` (wedged launcher)

The launcher daemon can hold port 8563 while the VM guest is dead. Repair:

```bash
exasol stop                       # if it hangs, kill the daemon directly:
kill $(cat ~/.exasol/personal/deployments/default/local/runtime/vm.pid)
exasol start
```

If the status stays stale, run `exasol start` **from Terminal.app** — this has
restored the deployment with `data.img` intact when other shells did not.

### Verify the database is actually answering

```bash
backend/.venv/bin/python scripts/run_sql.py db/70_verify.sql
```

### Rebuild the data pipeline (only if tables are missing)

```bash
for f in db/10_schema.sql db/20_seed_dims.sql db/30_generate_readings.sql \
         db/40_anomaly_window.sql db/45_forecast_view.sql \
         db/50_udf_ward_risk.lua.sql db/60_materialize.sql db/70_verify.sql; do
  backend/.venv/bin/python scripts/run_sql.py $f
done
```

---

## 2. Backend (FastAPI, port 8000)

```bash
backend/.venv/bin/uvicorn backend.app:app --port 8000
```

- Serves the API **and** the built frontend (`frontend/dist`) on one origin —
  open <http://127.0.0.1:8000> once it is up.
- Health check: `curl http://127.0.0.1:8000/api/health` should report
  `database: up, mock: false`.

First-time setup only (venv already exists in this checkout):

```bash
uv venv backend/.venv --python python3.11
backend/.venv/bin/pip install -r backend/requirements.txt
```

### Run tests

```bash
backend/.venv/bin/python -m pytest backend/tests -q
```

---

## 3. Frontend (React + Vite)

### Production mode (demo / normal use)

No separate process needed — the backend above serves `frontend/dist`.
To rebuild after changing frontend code:

```bash
npm --prefix frontend run build
```

### Development mode (hot reload, proxies `/api` to port 8000)

```bash
npm --prefix frontend run dev          # needs the backend running on :8000
npm --prefix frontend run dev:mock     # full UI with mock data, no DB needed
```

First-time setup only:

```bash
npm --prefix frontend install
```

---

## Quick reference

| Goal | Command |
|------|---------|
| Start database | `exasol start` |
| Stop database | `exasol stop` |
| Start backend + UI (one port) | `backend/.venv/bin/uvicorn backend.app:app --port 8000` |
| Rebuild frontend bundle | `npm --prefix frontend run build` |
| Dev server with hot reload | `npm --prefix frontend run dev` |
| UI with no database at all | `npm --prefix frontend run dev:mock` |
| Run any SQL file | `backend/.venv/bin/python scripts/run_sql.py db/NN_name.sql` |
| Run backend tests | `backend/.venv/bin/python -m pytest backend/tests -q` |
| Health check | `curl http://127.0.0.1:8000/api/health` |
