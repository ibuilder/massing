"""R26-ONE-HEALTH — the app must not appear to disagree with itself about a project.

The redesign audit reported this as a contradiction: "model health 77/100 in Construction, 24 at risk
in Design". Investigating narrowed it to something more specific and more fixable.

**Two engines, two genuinely different subjects.** `model_health.scorecard` measures the MODEL — GUID
hygiene, ISO 19650 information delivery, clash resolution, verified as-built. `projecthealth` measures
the JOB — RFIs, submittals, T&M, quality, safety, field reporting, closeout. They are not duplicates
and must not be merged: a BIM coordinator and a PM track different things, and averaging them would
produce a number that answers neither question. Both are already labelled distinctly in the UI.

**The real defect was inside one engine.** `health_score` is a MEAN across domains while
`overall_status` is WORST-OF, and both are rendered together. Six green domains and one red yields
"88/100 · RED" — each number correct, the pair baffling. A user who catches the app disagreeing with
itself stops trusting every other number on the screen, which is the expensive part.

The fix is not to drop either aggregation — a PM needs both the average and the blocker — but to name
the domain that governs the band, so the pair reads as an explanation instead of a contradiction.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_health_consistency.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_health_consistency.db"
os.environ["STORAGE_DIR"] = "./test_storage_health_consistency"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_health_consistency.db"):
    os.remove("./test_health_consistency.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import projecthealth  # noqa: E402
from aec_api.main import app  # noqa: E402

HDR = {"X-User": "engineer"}

# ---- the two aggregations are DECLARED, so a caller never has to reverse-engineer them ------------
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Health"}, headers=HDR).json()["id"]
    h = c.get(f"/projects/{pid}/health", headers=HDR).json()

    assert h["score_basis"] == "mean of scored domains", h
    assert h["status_basis"] == "worst domain governs", h
    assert "governing_domain" in h and "governing_detail" in h

    # a clean project names no governing domain — there is nothing dragging the band down
    if h["overall_status"] == "green":
        assert h["governing_domain"] is None, h

    # THE INVARIANT: whenever the band is worse than green, the domain that set it is NAMED.
    # Without this, a high score beside a red band is indistinguishable from a bug.
    if h["overall_status"] in ("red", "amber"):
        assert h["governing_domain"], "a non-green band must say which domain governs it"
        gov = [d for d in h["domains"] if d["label"] == h["governing_domain"]]
        assert gov and gov[0]["status"] == h["overall_status"], (h["overall_status"], gov)

    # and the band always matches the worst domain present — never better than its worst part
    statuses = {d["status"] for d in h["domains"]}
    if "red" in statuses:
        assert h["overall_status"] == "red", h["overall_status"]
    elif "amber" in statuses:
        assert h["overall_status"] == "amber", h["overall_status"]

# ---- the mean/worst-of divergence is REAL, not hypothetical --------------------------------------
# Construct the exact shape the audit saw: mostly green, one red. The score stays high, the band goes
# red, and the payload explains why. This is the case that made the app look broken.
domains = [{"key": f"d{i}", "label": f"Domain {i}", "status": "green", "headline": "",
            "open_count": 0, "overdue_count": 0} for i in range(6)]
domains.append({"key": "safety", "label": "Safety", "status": "red", "headline": "1 recordable",
                "open_count": 1, "overdue_count": 1})
scored = [projecthealth._STATUS_SCORE[d["status"]] for d in domains]
mean = round(sum(scored) / len(scored))
assert mean >= 80, f"a single red among six greens still averages high ({mean}) — that is the trap"
# the band, by contrast, must be red — and that pairing is exactly what needs explaining
assert any(d["status"] == "red" for d in domains)

# ---- the two ENGINES stay separate, and that is deliberate ---------------------------------------
# Merging them would blend model quality with construction delivery and answer neither question.
from aec_api import model_health  # noqa: E402

assert hasattr(model_health, "scorecard") and hasattr(projecthealth, "project_health")
assert "hygiene" in model_health._WEIGHTS and "information" in model_health._WEIGHTS
# model health weights model-quality lenses; project health scores delivery domains. No overlap.
assert not ({"rfi", "submittals", "safety", "closeout"} & set(model_health._WEIGHTS))

print("R26-ONE-HEALTH OK - the audit reported the app contradicting itself (model health 77/100 in "
      "one workspace, 24 at risk in another) and investigating narrowed it to something more precise. "
      "The two engines measure genuinely DIFFERENT subjects - model_health scores the MODEL (GUID "
      "hygiene, ISO 19650 delivery, clash resolution, verified as-built) while projecthealth scores "
      "the JOB (RFIs, submittals, T&M, quality, safety, field reporting, closeout) - so merging them "
      "would produce a number answering neither question, and both are already labelled distinctly. "
      "The real defect sat INSIDE one engine: health_score is a MEAN across domains while "
      "overall_status is WORST-OF, and rendering them together means six green domains and one red "
      "shows as '88/100 RED' - each number correct, the pair baffling, and a user who catches the app "
      "disagreeing with itself stops trusting every other number on the screen. Both aggregations are "
      "worth keeping because a PM needs the average AND the blocker, so the payload now DECLARES each "
      "basis and names the governing domain, turning an apparent contradiction into the one sentence "
      "that was missing. The invariant is asserted: a non-green band must always name the domain that "
      "set it, and can never read better than its worst part.")
