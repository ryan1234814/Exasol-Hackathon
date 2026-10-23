"""The one place that talks to Exasol.

Kept deliberately small (~150 lines, no ORM, no connection pool) because every
"it won't connect" failure on stage funnels through this module, and because it
is also the single place the docker-db fallback is absorbed.

Three details that are easy to get wrong and are therefore pinned here:

* **DSN** is ``127.0.0.1:8563`` — the starter kit's port forwarder, not the VM's
  own address.
* **TLS** — the local database uses a *self-signed* certificate, so
  ``websocket_sslopt={"cert_reqs": 0}`` is required or every connection fails
  with a certificate error that looks like a network problem.
* **The password is never a literal and is never logged.** It is read at connect
  time from whichever of the known locations actually exists — the starter kit's
  credentials file, or the launcher's per-deployment ``secrets.json`` (which is
  JSON, ``{"dbPassword": "…"}``, not a bare string).
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
import threading
import time
from decimal import Decimal
from pathlib import Path

log = logging.getLogger("wq.db")

DEFAULT_DSN = "127.0.0.1:8563"
DEFAULT_USER = "sys"
CREDENTIALS_DIR = Path.home() / ".exasol-starter-kit" / "credentials"
# The launcher writes the admin password here per deployment. It matters because
# `exasol deploy` provisions a working database *without* the starter kit having
# recorded a runtime, so the kit's credentials directory can legitimately not
# exist yet while the database is perfectly reachable.
DEPLOYMENTS_ROOT = Path.home() / ".exasol" / "personal" / "deployments"
PASSWORD_KEYS = ("dbPassword", "db_password", "password")


class DatabaseUnavailable(RuntimeError):
    """Raised when the local database cannot be reached or queried."""


def _extract_password(raw: str) -> str:
    """Pull the secret out of a file that may be JSON or a bare string.

    ``secrets.json`` is ``{"dbPassword": "…"}``; the kit's credential file is a
    raw string. Accepting both means one code path works whether the database was
    brought up by the kit or straight by the launcher.
    """
    text = raw.strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DatabaseUnavailable(f"password file is not valid JSON: {exc}") from exc
        for key in PASSWORD_KEYS:
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
        raise DatabaseUnavailable(
            f"password JSON has none of {PASSWORD_KEYS}")
    if not text:
        raise DatabaseUnavailable("password file is empty")
    return text


def _deployment_secrets_file() -> Path | None:
    """Newest launcher ``secrets.json`` under the deployments root.

    Newest rather than alphabetically first: recreating a deployment under the
    same name is the normal repair path, and the fresh secret is the live one.
    """
    explicit = os.environ.get("EXASOL_DEPLOYMENT_DIR")
    if explicit:
        candidate = Path(explicit).expanduser() / "secrets.json"
        if candidate.is_file():
            return candidate
    if not DEPLOYMENTS_ROOT.is_dir():
        return None
    files = sorted(
        (p for p in DEPLOYMENTS_ROOT.glob("*/secrets.json") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def resolve_password() -> str:
    """Locate and read the admin password.

    Order: ``EXAKIT_PASSWORD_FILE``, then ``exakit info --json`` (authoritative
    when the kit recorded a runtime), then the newest file in the kit's
    credentials directory, then the launcher's per-deployment ``secrets.json``.
    Never guesses a filename, never prints the value.
    """
    explicit = os.environ.get("EXAKIT_PASSWORD_FILE")
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return _extract_password(path.read_text(encoding="utf-8"))
        raise DatabaseUnavailable(f"EXAKIT_PASSWORD_FILE points at nothing: {path}")

    candidate: str | None = None
    try:
        out = subprocess.run(
            ["exakit", "info", "--json"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            info = json.loads(out.stdout)
            candidate = (info.get("runtime") or {}).get("password_file")
    except (FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError):
        pass  # exakit absent or unhelpful; fall through to the directory scan

    if candidate and Path(candidate).is_file():
        return _extract_password(Path(candidate).read_text(encoding="utf-8"))

    if CREDENTIALS_DIR.is_dir():
        files = sorted(
            (p for p in CREDENTIALS_DIR.iterdir() if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if files:
            return _extract_password(files[0].read_text(encoding="utf-8"))

    secrets = _deployment_secrets_file()
    if secrets:
        return _extract_password(secrets.read_text(encoding="utf-8"))

    raise DatabaseUnavailable(
        "Could not locate the Exasol admin password. Set EXAKIT_PASSWORD_FILE to "
        "the path reported by `exakit info`, or EXASOL_DEPLOYMENT_DIR to the "
        "directory holding `secrets.json` (see `exasol status`)."
    )


def _bindable(value):
    """Coerce one Python value into something pyexasol 3.x will actually send.

    pyexasol 3.0.1 serialises query parameters as JSON over the WebSocket, and
    ``datetime`` / ``date`` are not JSON types — binding one fails with
    ``Object of type datetime is not JSON serializable``. Exasol accepts the
    canonical ISO text, which is what ``isoformat(sep=' ')`` produces for a
    timestamp, so conversion is lossless for the DATE/TIMESTAMP columns here.
    """
    if value is None or isinstance(value, (int, float, str, bytes)):
        return value
    if hasattr(value, "isoformat"):
        sep = " " if hasattr(value, "hour") else "-"
        return value.isoformat(sep)
    return str(value)


def _conversion(value) -> str:
    """Choose a pyexasol ``{name!x}`` conversion so the value binds correctly.

    pyexasol 3.x has no ``?`` positional binding at all: ``execute(sql, params)``
    runs ``str.format`` with a *dict*, and the default conversion quotes every
    value as a string. That breaks ``LIMIT ?`` (it becomes ``LIMIT '3'``) and
    would turn a numeric ``WARD_ID = ?`` into a string compare. Choosing the
    conversion by Python type keeps numbers bare (``!d`` integer, ``!f`` float,
    both validated by ``ExaFormatter``) and quotes everything else.
    """
    if isinstance(value, bool):  # bool is an int subclass; no bools are bound today
        return "!d"
    if isinstance(value, int):
        return "!d"
    if isinstance(value, (float, Decimal)):
        return "!f"
    return ""  # default conversion -> quote(), which renders NULL for None


def _bind(sql: str, params) -> tuple[str, dict | None]:
    """Translate ``?``-positional SQL (what the whole backend is written in) into
    pyexasol 3.x ``{pN!c}`` named parameters.

    Replacement is quote-aware so a literal ``?`` inside a string can never be
    mistaken for a placeholder, and the placeholder count is validated against
    the parameter count — a mismatch is a programming error and must fail loudly
    rather than send a truncated query.
    """
    if params is None:
        return sql, None
    if isinstance(params, dict):  # caller already used named form
        return sql, {k: _bindable(v) for k, v in params.items()}
    params = list(params)
    named: dict[str, object] = {}
    out: list[str] = []
    i = 0
    slot = 0
    in_single = in_double = False
    n = len(sql)
    while i < n:
        ch = sql[i]
        if ch == "'" and not in_double:
            if in_single and i + 1 < n and sql[i + 1] == "'":
                out.append("''")
                i += 2
                continue
            in_single = not in_single
            out.append(ch)
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
            i += 1
            continue
        if ch == "?" and not in_single and not in_double:
            if slot >= len(params):
                raise DatabaseUnavailable(
                    f"more ? placeholders than parameters in: {sql[:80]}")
            value = params[slot]
            named[f"p{slot}"] = _bindable(value)
            out.append("{p%d%s}" % (slot, _conversion(value)))
            slot += 1
            i += 1
            continue
        out.append(ch)
        i += 1
    if slot != len(params):
        raise DatabaseUnavailable(
            f"{len(params)} parameters but {slot} ? placeholders in: {sql[:80]}")
    return "".join(out), named


class ExasolDB:
    """Lazy, reconnecting wrapper around a single pyexasol connection.

    A single connection is intentional: the local VM has 2 vCPU, so a pool would
    only buy concurrent query storms that make the demo slower.
    """

    def __init__(self, dsn: str | None = None, user: str = DEFAULT_USER):
        self.dsn = dsn or os.environ.get("EXAKIT_DSN", DEFAULT_DSN)
        self.user = user
        self._conn = None
        self._lock = threading.Lock()
        self.last_query_ms: float | None = None
        self.last_sql: str | None = None

    # -- lifecycle ---------------------------------------------------------
    def _connect(self):
        try:
            import pyexasol
        except ImportError as exc:  # pragma: no cover - depends on the venv
            raise DatabaseUnavailable(
                "pyexasol is not installed in this interpreter. Use "
                "backend/.venv (see Makefile bootstrap)."
            ) from exc

        password = resolve_password()
        try:
            return pyexasol.connect(
                dsn=self.dsn,
                user=self.user,
                password=password,
                websocket_sslopt={"cert_reqs": 0},  # local self-signed cert
                socket_timeout=30,
                query_timeout=300,
                compression=False,
            )
        except Exception as exc:  # noqa: BLE001 - surface as a domain error
            # The single most common cause is a stopped database, and the
            # message below is the remedy the kit's own skill documents.
            raise DatabaseUnavailable(
                f"Cannot connect to Exasol at {self.dsn}: {exc}. "
                "If this is 'Connection refused', the database is not running: "
                "`exakit start`, then `exakit status`."
            ) from exc

    def _ensure(self):
        if self._conn is None:
            self._conn = self._connect()
        return self._conn

    def _reset(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001 - closing a dead socket is noise
                pass
        self._conn = None

    def close(self) -> None:
        with self._lock:
            self._reset()

    # -- queries -----------------------------------------------------------
    def query(self, sql: str, params=None) -> list[dict]:
        """Run a SELECT and return a list of dicts keyed by column name.

        Retries exactly once, because a stale keep-alive socket after the VM was
        restarted is the common transient and it should not need a human.
        """
        with self._lock:
            started = time.monotonic()
            for attempt in (1, 2):
                try:
                    conn = self._ensure()
                    # pyexasol 3.x has no ? positional binding; translate.
                    named_sql, named_params = _bind(sql, params)
                    cur = (conn.execute(named_sql, named_params)
                           if named_params else conn.execute(named_sql))
                    # pyexasol 3.x exposes ``column_names()`` as a method; the
                    # DB-API-style ``.description`` attribute does not exist on
                    # ExaStatement, and relying on it fails on the first live query.
                    columns = list(cur.column_names())
                    rows = [dict(zip(columns, r)) for r in cur.fetchall()]
                    self.last_query_ms = round((time.monotonic() - started) * 1000, 2)
                    self.last_sql = sql
                    return rows
                except DatabaseUnavailable:
                    raise
                except Exception as exc:  # noqa: BLE001
                    if attempt == 2:
                        self._reset()
                        raise DatabaseUnavailable(f"Query failed: {exc}") from exc
                    self._reset()  # discard the stale socket and reconnect

        return []  # unreachable; keeps type checkers honest

    def iter_query(self, sql: str, batch_size: int = 20_000):
        """Stream a large result in batches instead of building a list of dicts.

        The benchmark mirrors all ~289k sample rows into SQLite; holding that as
        Python dicts would cost hundreds of MB on a host that is also paying the
        VM its whole reservation, which is precisely the OOM risk the plan calls
        out (R5).

        Holds the connection lock for the whole iteration, so it is for the
        single-threaded benchmark CLI and never for a request path.

        Streams with ``fetchmany`` because pyexasol 3.x has no ``fetchiter``, and
        stops at the first empty batch rather than trusting a row count.
        """
        with self._lock:
            started = time.monotonic()
            conn = self._ensure()
            try:
                cur = conn.execute(sql)
                columns = list(cur.column_names())
                while True:
                    batch = cur.fetchmany(batch_size)
                    if not batch:
                        break
                    for row in batch:
                        yield dict(zip(columns, row))
            except Exception as exc:  # noqa: BLE001
                self._reset()
                raise DatabaseUnavailable(f"Stream failed: {exc}") from exc
            finally:
                self.last_query_ms = round((time.monotonic() - started) * 1000, 2)
                self.last_sql = sql

    def execute(self, sql: str, params=None) -> None:
        with self._lock:
            started = time.monotonic()
            conn = self._ensure()
            named_sql, named_params = _bind(sql, params)
            try:
                (conn.execute(named_sql, named_params)
                 if named_params else conn.execute(named_sql))
            except Exception as exc:  # noqa: BLE001
                self._reset()
                raise DatabaseUnavailable(f"Statement failed: {exc}") from exc
            self.last_query_ms = round((time.monotonic() - started) * 1000, 2)
            self.last_sql = sql

    def insert_many(self, statement: str, rows: list[tuple], batch_size: int = 5_000) -> int:
        """Bulk-insert with pyexasol's fast path, returning the row count.

        ``statement`` is e.g. ``"WARDQ.COMPLAINT (A, B, C)"`` with no trailing
        semicolon, and ``rows`` are tuples in that column order. One INSERT per
        row would take minutes for 15k complaints; ``ext.insert_multi`` is the
        documented bulk route and needs no intermediate CSV file.

        pyexasol 3.x changed the call shape to ``insert_multi(table_name, data,
        columns)`` and dropped ``batch_size`` entirely (and this build has no
        ``import_from_iterable`` to fall back on), so the table and column list
        are parsed out of ``statement`` and batching is done here, under the
        connection lock, in ``batch_size`` slices.
        """
        if not rows:
            return 0
        table, columns = _parse_insert_shape(statement)
        with self._lock:
            started = time.monotonic()
            conn = self._ensure()
            try:
                for offset in range(0, len(rows), batch_size):
                    conn.ext.insert_multi(
                        table,
                        [tuple(_bindable(v) for v in row) for row in
                         rows[offset:offset + batch_size]],
                        columns)
            except Exception as exc:  # noqa: BLE001
                self._reset()
                raise DatabaseUnavailable(f"Bulk insert failed: {exc}") from exc
            self.last_query_ms = round((time.monotonic() - started) * 1000, 2)
            self.last_sql = statement
        return len(rows)

    def scalar(self, sql: str, params=None):
        rows = self.query(sql, params)
        if not rows:
            return None
        return next(iter(rows[0].values()), None)

    def health(self) -> dict:
        """Cheap reachability probe used by GET /api/health."""
        try:
            ts = self.scalar("SELECT CURRENT_TIMESTAMP AS TS")
            return {"database": "up", "dsn": self.dsn, "server_time": str(ts)}
        except DatabaseUnavailable as exc:
            return {"database": "down", "dsn": self.dsn, "error": str(exc)}


_singleton: ExasolDB | None = None
_singleton_lock = threading.Lock()


def get_db() -> ExasolDB:
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = ExasolDB()
        return _singleton


def _parse_insert_shape(statement: str) -> tuple[tuple[str, str], list[str]]:
    """Split ``"WARDQ.COMPLAINT (A, B, C)"`` into ``(("WARDQ","COMPLAINT"), ["A","B","C"])``.

    ``load.py`` builds one INSERT shape once and hands it here; pyexasol 3.x
    wants the table and the column order as separate arguments, and it refuses a
    dotted table name as an untrusted string — the schema-qualified name must be
    passed as a ``('SCHEMA', 'TABLE')`` tuple.
    """
    text = statement.rstrip().rstrip(";")
    table, _, rest = text.partition("(")
    columns = [c.strip() for c in rest.rstrip(")").split(",") if c.strip()]
    if not columns:
        raise DatabaseUnavailable(f"cannot read column list from: {statement}")
    parts = [p.strip() for p in table.split(".") if p.strip()]
    if len(parts) == 1:
        return (parts[0],), columns
    return (parts[-2], parts[-1]), columns


def quote(value: str) -> str:
    """Escape a literal for interpolation into a saved .sql demo query.

    Used only where a query is shown to a human and re-run via ``exakit sql``,
    where bound parameters are not available. API paths use ``params`` instead.
    """
    return shlex.quote(str(value).replace("'", "''"))
