"""R27-FIRM-MEMORY: firm-level standards a project inherits and may override, visibly.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_firm_standards.py"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./_firmstd_test.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_firmstd")
if os.path.exists("./_firmstd_test.db"):
    os.remove("./_firmstd_test.db")

from aec_api import firm_standards as fs  # noqa: E402
from aec_api import rule_library  # noqa: E402

PID = "11111111-2222-3333-4444-555555555555"
ok = 0


def check(cond, label, detail=""):
    global ok
    assert cond, f"FAIL  {label}  {detail}"
    ok += 1
    print(f"PASS  {label}" + (f"   {detail}" if detail else ""))


# start clean — these are storage blobs, not DB rows
fs.save_rules([])
rule_library.save(PID, [])

# ---- inheriting costs nothing when there is no firm library ---------------------------------------
rule_library.save(PID, [{"id": "own1", "name": "Project only", "scope": "IfcDoor",
                         "require": "Pset_DoorCommon.FireRating=90", "severity": "high"}])
eff = fs.effective_rules(PID)
check(eff["count"] == 1 and eff["firm_count"] == 0,
      "with no firm rules, a project sees exactly its own", f"{eff['count']} rule(s)")
check(eff["rules"][0]["source"] == "project", "...sourced as project")

# ---- a project inherits firm rules ----------------------------------------------------------------
fs.save_rules([
    {"id": "fire90", "name": "L1 doors are fire-rated", "scope": "IfcDoor",
     "require": "Pset_DoorCommon.FireRating=90", "severity": "high"},
    {"id": "loadbear", "name": "Fire walls are load-bearing", "scope": "IfcWall",
     "require": "Pset_WallCommon.LoadBearing=true", "severity": "medium"},
])
eff = fs.effective_rules(PID)
check(eff["inherited_count"] == 2, "both firm rules are inherited", f"got {eff['inherited_count']}")
check(eff["count"] == 3, "...alongside the project's own", f"{eff['count']} effective")
check({r["source"] for r in eff["rules"]} == {"firm", "project"}, "every rule states where it came from")

# ---- an override is VISIBLE as an override --------------------------------------------------------
rule_library.save(PID, [
    {"id": "own1", "name": "Project only", "scope": "IfcDoor",
     "require": "Pset_DoorCommon.FireRating=90", "severity": "high"},
    # same id as the firm rule → this job's client wants 60, not 90
    {"id": "fire90", "name": "L1 doors are fire-rated (client: 60)", "scope": "IfcDoor",
     "require": "Pset_DoorCommon.FireRating=60", "severity": "high"},
])
eff = fs.effective_rules(PID)
check(eff["overridden_count"] == 1, "the displaced firm rule is counted", f"got {eff['overridden_count']}")
check(eff["count"] == 3, "...and does NOT also appear as inherited",
      "a rule applying twice under one id is worse than either version alone")
ov = eff["overridden"][0]
check(ov["firm_require"] == "Pset_DoorCommon.FireRating=90"
      and ov["project_require"] == "Pset_DoorCommon.FireRating=60",
      "both sides of the override are reported", f"{ov['firm_require']} -> {ov['project_require']}")
winner = next(r for r in eff["rules"] if r["id"] == "fire90")
check(winner["source"] == "project" and winner["require"] == "Pset_DoorCommon.FireRating=60",
      "the project's version is the one that applies")
check(winner["overrides"] and winner["overrides"]["require"] == "Pset_DoorCommon.FireRating=90",
      "...carrying the firm version it replaced",
      "a firm standard silently replaced is how standards stop being standards")
check(eff["project_only_count"] == 1, "a project rule that overrides nothing is not counted as one")

# ---- the firm library is validated like any other --------------------------------------------------
# An EMPTY selector, which QUERY-DSL genuinely rejects. (The first version of this check used
# "IfcDoor &&& broken" and passed nothing: the DSL accepts it — `&` is a separator, so that parses to
# the predicates it can find. Asserting on a string I *assumed* was malformed would have tested my
# guess about the grammar rather than the validator.)
try:
    fs.save_rules([{"id": "bad", "name": "Nonsense", "scope": "", "require": "x", "severity": "high"}])
    raised = False
except Exception:
    raised = True
check(raised, "a malformed firm rule is rejected",
      "a rule invalid on a project must not be accepted because it was authored at the firm level")
check(len(fs.load_rules()) == 2, "...and nothing was written", "save is atomic, at both tiers")

# ---- firm scope cannot be a project ---------------------------------------------------------------
check(fs.FIRM_SCOPE == "_firm" and "-" not in fs.FIRM_SCOPE,
      "the firm scope key cannot collide with a project id", "project ids are UUIDs")

print(f"\ntest_firm_standards OK  ({ok} checks)")
print("R27-FIRM-MEMORY: a firm's standards are exactly the thing that does NOT change per project, yet "
      "rule_library, design_standards and standards_expert are all per-project - so the standard gets "
      "re-authored per job and becomes forty slightly different rule sets with no way to say which one "
      "is the standard. Firm rules now live under a reserved storage scope, reusing rule_library's own "
      "blob path and validator so there is one persistence path and one definition of a valid rule. A "
      "project layers over them by rule ID, not by name - matching on name would make a rename look "
      "like a new rule and silently reinstate the firm's version alongside the project's. The override "
      "is the point: it is legitimate (a client standard differing from the firm's is normal) but it "
      "must be VISIBLE, because the failure here is not a wrong answer, it is a firm discovering its "
      "standards were quietly optional. This codebase has no Organization entity - what tenant scoping "
      "means here is RBAC over project membership - so 'firm' means the deployment, stated rather than "
      "hidden; if organisations arrive, FIRM_SCOPE becomes an org id and the inheritance is unchanged.")
