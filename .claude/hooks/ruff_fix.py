#!/usr/bin/env python
"""PostToolUse hook — auto-run `ruff check --fix` on an edited Python file under services/, using the
CI config (services/api/ruff.toml, incl. isort/I001), so import-order and trivial fixes land before CI
instead of failing the API test gate. Self-authored, shells only to the project's own ruff, no network.
Best-effort: it never blocks or fails the edit (always exits 0).

**It also refuses to run below the project's declared ruff floor, and that guard is the point of the
2026-08-29 revision.** This hook WRITES to source files. Doing that with a different rule engine than
the one that judges them is worse than not running at all: the bad case is silent, because the run is
`capture_output=True` and the exit is always 0. On a Linux cloud clone it was measured doing exactly
that — the venv probe below looked only for `.venv/Scripts/python.exe`, a **Windows** path, so every
POSIX checkout fell through to bare `ruff`, which resolved to **0.15.8** against a
`requirements-dev.txt` floor of **>=0.16.3** and a CI gate running **0.16.5**. Two minors of
`--fix` behaviour drift (I001 grouping is the likeliest) applied by a tool nobody could see fail.

Both halves are fixed: the probe now knows the POSIX layout, and the floor is READ FROM
`requirements-dev.txt` rather than copied here — a hardcoded floor is the same drift one level up,
and this repository has a long record of exactly that. When no interpreter satisfies the floor the
hook does nothing, which is the safe direction: CI still runs the real ruff.
"""
import json
import os
import re
import subprocess
import sys


def _floor(api: str):
    """The declared minimum ruff, read from requirements-dev.txt. None if it cannot be read."""
    try:
        with open(os.path.join(api, "requirements-dev.txt"), encoding="utf-8") as fh:
            m = re.search(r"^ruff\s*>=\s*([0-9]+(?:\.[0-9]+)*)", fh.read(), re.M)
        return tuple(int(p) for p in m.group(1).split(".")) if m else None
    except Exception:
        return None


def _version(base):
    """The version `base` actually runs, or None if it will not run at all."""
    try:
        out = subprocess.run([*base, "--version"], capture_output=True, text=True, timeout=15)
        m = re.search(r"([0-9]+(?:\.[0-9]+)*)", out.stdout or "")
        return tuple(int(p) for p in m.group(1).split(".")) if m else None
    except Exception:
        return None


def _candidates(api: str):
    """Interpreters that might carry ruff, project venv first — Windows and POSIX layouts both."""
    for rel in (("Scripts", "python.exe"), ("bin", "python")):
        py = os.path.join(api, ".venv", *rel)
        if os.path.exists(py):
            yield [py, "-m", "ruff"]
    yield ["ruff"]                       # whatever is on PATH
    yield [sys.executable, "-m", "ruff"]  # the interpreter running this hook


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    fp = ((data.get("tool_input") or {}).get("file_path") or "").replace("\\", "/")
    if not fp.endswith(".py"):
        return
    if "/services/api/" not in fp and "/services/data/" not in fp:
        return
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # .claude/hooks → repo
    api = os.path.join(repo, "services", "api")
    cfg = os.path.join(api, "ruff.toml")
    if not os.path.exists(cfg) or not os.path.exists(fp):
        return
    # Take the first candidate that both RUNS and meets the declared floor. An unreadable floor is
    # treated as "no floor" rather than as zero: this hook is a convenience, and refusing to run
    # because a requirements file moved would be a worse failure than the one being prevented.
    floor = _floor(api)
    for base in _candidates(api):
        got = _version(base)
        if got is None or (floor is not None and got < floor):
            continue
        try:
            subprocess.run([*base, "check", "--fix", "--quiet", "--config", cfg, fp],
                           cwd=api, timeout=30, capture_output=True)
        except Exception:
            pass
        return


if __name__ == "__main__":
    try:
        main()
    finally:
        sys.exit(0)   # never block the edit
