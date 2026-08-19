"""Protocol scoping lives in Python. The TS strip must not invent a second map.

Run: PYTHONPATH=src:../data/src python test_master_builder_scope.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, "src")

from aec_api.master_builder_scope import (  # noqa: E402
    STEPS_BY_PERSONA,
    STEPS_BY_WORKSPACE,
    apply_scope,
    scope_step_keys,
)

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


def _ts_object(name: str) -> dict[str, list[str]]:
    ts = Path(__file__).resolve().parents[2] / "apps" / "web" / "src" / "portal" / "panels" / "readinessStrip.ts"
    text = ts.read_text(encoding="utf-8")
    m = re.search(rf"export const {name}:[^{{]+{{(.*?)\n}};", text, re.S)
    if not m:
        raise AssertionError(f"{name} not found in {ts}")
    body = m.group(1)
    out: dict[str, list[str]] = {}
    for km in re.finditer(r"(\w+):\s*\[([^\]]+)\]", body):
        out[km.group(1)] = [x.strip().strip('"').strip("'") for x in km.group(2).split(",") if x.strip()]
    return out


check("design/all is place/program/design/regulatory",
      scope_step_keys("design", "all") == ["place", "program", "design", "regulatory"])
check("superintendent on construction drops feasibility",
      scope_step_keys("construction", "superintendent") == ["delivery", "risk", "handover"])
check("engineer on design uses persona order, not place-first workspace order",
      scope_step_keys("design", "engineer") == ["design", "regulatory", "place"])
check("superintendent on design falls back to the workspace set, not empty",
      scope_step_keys("design", "superintendent") == ["place", "program", "design", "regulatory"])
check("unknown workspace uses the builder set",
      scope_step_keys("nonsense", "all") == list(STEPS_BY_WORKSPACE["construction"]))

fake = {"readiness_pct": 40, "step_count": 8, "steps": [
    {"key": "place"}, {"key": "design"}, {"key": "delivery"},
]}
scoped = apply_scope(fake, "design", "all")
check("apply_scope keeps the overall score", scoped["readiness_pct"] == 40 and scoped["step_count"] == 8)
check("apply_scope drops construction-only pills",
      [s["key"] for s in scoped["steps"]] == ["place", "design"])
check("unscoped brief is unchanged", apply_scope(fake, None, None) is fake or apply_scope(fake, None, None)["steps"] == fake["steps"])

ts_ws = _ts_object("STEPS_BY_WORKSPACE")
ts_p = _ts_object("STEPS_BY_PERSONA")
check("TS workspace map matches Python",
      {k: list(v) for k, v in STEPS_BY_WORKSPACE.items()} == ts_ws, f"py={STEPS_BY_WORKSPACE} ts={ts_ws}")
check("TS persona map matches Python",
      {k: list(v) for k, v in STEPS_BY_PERSONA.items()} == ts_p, f"py={STEPS_BY_PERSONA} ts={ts_p}")

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_master_builder_scope OK")
