#!/usr/bin/env python
"""PostToolUse hook — auto-run `ruff check --fix` on an edited Python file under services/, using the
CI config (services/api/ruff.toml, incl. isort/I001), so import-order and trivial fixes land before CI
instead of failing the API test gate. Self-authored, shells only to the project's own ruff, no network.
Best-effort: it never blocks or fails the edit (always exits 0).
"""
import json
import os
import subprocess
import sys


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
    venv_py = os.path.join(api, ".venv", "Scripts", "python.exe")
    base = [venv_py, "-m", "ruff"] if os.path.exists(venv_py) else ["ruff"]
    try:
        subprocess.run([*base, "check", "--fix", "--quiet", "--config", cfg, fp],
                       cwd=api, timeout=30, capture_output=True)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    finally:
        sys.exit(0)   # never block the edit
