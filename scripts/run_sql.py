"""Execute the repository's .sql files against the local Exasol database.

Why this exists: the starter kit normally ships ``exapump`` as the SQL CLI, but it
is installed only after a successful first deployment, and this machine spent two
days without one. ``pyexasol`` is already a dependency, so the runner is ~80 lines.

The one genuinely tricky part is statement splitting, and it is not optional:

* ``COMMENT ON ... IS '…; …'`` puts a semicolon *inside* a string literal, so
  ``text.split(";")`` silently corrupts ``10_schema.sql`` into two broken halves.
* ``CREATE OR REPLACE LUA SCALAR SCRIPT`` bodies are terminated by a lone ``/``
  line, not ``;``, because Lua uses ``;`` freely.
* ``--`` line comments may sit after the terminator on the same line.

So splitting is a small state machine over quotes and line comments. It is pure
and unit-tested (``backend/tests/test_run_sql.py``) because a wrong split is the
kind of failure that surfaces as a syntax error halfway through a 289k-row insert.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# A "/" that terminates a Lua script body: alone on its line, possibly trailing WS.
LUA_TERMINATOR = re.compile(r"^[ \t]*/[ \t]*$")


def split_statements(text: str) -> list[str]:
    """Split SQL text into executable statements, quote- and comment-aware.

    Handles ``'…'`` literals (with ``''`` escapes), ``"…"`` quoted identifiers,
    ``--`` line comments, ``/* … */`` block comments, ``;`` terminators, and Lua
    ``/`` terminators. Returned statements have no trailing terminator and blank
    ones are dropped.
    """
    statements: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(text)
    in_single = in_double = in_block = False

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        # Line comment: consume to end of line, but never inside a literal.
        if not in_single and not in_double and not in_block and ch == "-" and nxt == "-":
            while i < n and text[i] != "\n":
                i += 1
            continue

        if in_block:
            if ch == "*" and nxt == "/":
                in_block = False
                i += 2
                continue
            i += 1
            continue

        if ch == "'" and not in_double:
            # '' inside a literal is an escaped quote, not a close+open pair.
            if in_single and nxt == "'":
                buf.append("''")
                i += 2
                continue
            in_single = not in_single
            buf.append(ch)
            i += 1
            continue

        if ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
            i += 1
            continue

        if not in_single and not in_double and ch == "/" and nxt == "*":
            in_block = True
            i += 2
            continue

        if not in_single and not in_double and ch == ";":
            statements.append("".join(buf).strip())
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return [s for s in statements if s]


def split_lua_file(text: str) -> list[str]:
    """Split a file whose CREATE … LUA SCALAR SCRIPT blocks end with a lone ``/``.

    Everything before the first bare ``/`` line is one statement; a trailing
    comment-only remainder is ignored.
    """
    statements: list[str] = []
    buf: list[str] = []
    for line in text.splitlines():
        if LUA_TERMINATOR.match(line):
            block = "\n".join(buf).strip()
            if block:
                statements.append(block)
            buf = []
            continue
        buf.append(line)
    remainder = "\n".join(buf).strip()
    if remainder and not _is_only_comments(remainder):
        statements.append(remainder)
    return statements


def _is_only_comments(text: str) -> bool:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            return False
    return True


def statements_for(path: Path) -> list[str]:
    """Pick the splitter by file shape, not by caller memory."""
    text = path.read_text(encoding="utf-8")
    if ".lua." in path.name or "LUA SCALAR SCRIPT" in text.upper():
        return split_lua_file(text)
    return split_statements(text)


def run_file(db, path: Path, *, echo: bool = True) -> tuple[int, float]:
    """Execute every statement in one file. Returns (statement_count, seconds)."""
    statements = statements_for(path)
    started = time.monotonic()
    for index, sql in enumerate(statements, start=1):
        db.execute(sql)
        if echo:
            first = sql.splitlines()[0][:78]
            print(f"    [{index:>2}/{len(statements)}] {first}")
    return len(statements), time.monotonic() - started


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run db/*.sql files in order.")
    parser.add_argument("files", nargs="+", type=Path,
                        help="paths relative to the repo root or absolute")
    parser.add_argument("--quiet", action="store_true", help="no per-statement echo")
    args = parser.parse_args(argv)

    from backend.db import DatabaseUnavailable, get_db  # after sys.path is set

    db = get_db()
    total_started = time.monotonic()
    for raw in args.files:
        path = raw if raw.is_absolute() else REPO_ROOT / raw
        if not path.is_file():
            print(f"missing file: {path}", file=sys.stderr)
            return 2
        print(f"== {path.relative_to(REPO_ROOT)}")
        try:
            count, elapsed = run_file(db, path, echo=not args.quiet)
        except DatabaseUnavailable as exc:
            print(f"FAILED {path.name}: {exc}", file=sys.stderr)
            return 1
        print(f"   {count} statements in {elapsed * 1000:.0f} ms")
    print(f"total {(time.monotonic() - total_started) * 1000:.0f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
