"""GET handlers that Session.commit() are CSRF-shaped: SameSite=Lax sends the cookie
on a top-level GET from another origin.

The population is derived from the tree, not recalled. Each hit needs an allowlist
reason. oauth_callback must stay GET (the provider redirects). CAM statement PDF is POST.

Run: PYTHONPATH=src python test_get_commits.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

FAILED = []

ROOT = Path(__file__).resolve().parent / "src" / "aec_api"

# Name the reason. An exemption with no argument is a suppression.
ALLOWED = {
    "routers/auth.py::oauth_callback":
        "OAuth providers redirect the browser with GET; the commit writes the session",
}


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


def _is_get(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for d in fn.decorator_list:
        call = d if isinstance(d, ast.Call) else None
        if call is None:
            continue
        f = call.func
        if isinstance(f, ast.Attribute) and f.attr == "get":
            return True
    return False


def _commits(fn: ast.AST) -> bool:
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "commit":
            return True
    return False


found: dict[str, int] = {}
for path in sorted(ROOT.rglob("*.py")):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rel = path.relative_to(ROOT).as_posix()
    for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        if _is_get(fn) and _commits(fn):
            found[f"{rel}::{fn.name}"] = fn.lineno

extra = sorted(k for k in found if k not in ALLOWED)
missing = sorted(k for k in ALLOWED if k not in found)

check("every GET+commit is named in ALLOWED", not extra,
      "; ".join(f"{k}:{found[k]}" for k in extra) or "none extra")
check("ALLOWED entries still exist (no stale exemption)", not missing,
      ", ".join(missing) or "all live")
check("the scan found oauth_callback, so it is measuring something",
      "routers/auth.py::oauth_callback" in found,
      str(sorted(found)))

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_get_commits OK")
