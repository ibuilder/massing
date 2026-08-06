"""R41-CLASH-TRIAGE — the reduction is real at scale, or the ratio we quote is a fixture artefact.

**The entry's premise is already built, and that is the finding.** R41-CLASH-TRIAGE asks for grouping
by similarity, dropping duplicates, filtering grazing false positives, and ranking survivors by
construction consequence. All four exist: `clash_intel.analyze` groups by greedy set-cover on the
dominant element and scores by discipline pair x penetration volume x group size, and
`aec_data.clash.detect` takes `min_volume=1e-3` (drops slivers) and a `tolerance` that shrinks the
boxes so merely-touching elements never register. `clash_intel` even adds a stable `group_hash` that
survives re-runs, which the entry does not ask for.

**What was NOT verified is the only number the entry is actually about.** The competitor headline is
22,843 raw clashes reduced to 103 groups — roughly 222:1. `test_clash_intel.py` asserts
`reduction == 2.0` on a **four-clash** fixture. Four rows cannot demonstrate an order of magnitude,
and greedy set-cover is exactly the kind of algorithm whose ratio is a function of topology: it can
look fine on a toy and collapse to ~1:1 on a real federation where every clash pair is distinct.
A small fixture manufacturing a confident number is a mistake this repo has made before, at 6.44%
versus an at-scale 0.92%.

So this measures the reduction on clash sets shaped like real ones, and asserts the property that
matters — **reduction must scale with clash density, not stay flat** — plus the two ways a grouper
can cheat:

1. **it must not reduce by losing clashes.** Every raw clash has to be inside exactly one group; a
   grouper that drops rows shows a magnificent ratio and silently discards work;
2. **it must not group things a coordinator would have to split again.** Distinct problems that share
   no element must stay distinct, or "one issue" stops meaning one real-world problem — which is the
   whole premise of the layer.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_clash_reduction_scale.py
"""
import sys

sys.path.insert(0, "src")

from aec_api.clash_intel import analyze  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def duct_through_joists(n_ducts: int, joists_per_duct: int, storeys: int = 1) -> list[dict]:
    """The shape the grouping exists for: one duct crossing many joists is ONE problem.

    This is the real topology, not a convenient one — a run of MEP crossing a structural bay produces
    exactly this fan-out, and it is what makes an order-of-magnitude reduction possible at all.
    """
    out = []
    for s in range(storeys):
        for d in range(n_ducts):
            duct = f"duct-{s}-{d}"
            for j in range(joists_per_duct):
                out.append({
                    "a_guid": duct, "a_class": "IfcDuctSegment", "a_model": "MEP",
                    "b_guid": f"joist-{s}-{d}-{j}", "b_class": "IfcBeam", "b_model": "STRUCT",
                    "volume": 0.02, "point": {"x": d * 1.0, "y": j * 0.5, "z": s * 3.0},
                })
    return out


# --- 1. THE HEADLINE NUMBER, at a scale that can actually show one -------------------------------
big = duct_through_joists(n_ducts=40, joists_per_duct=18, storeys=8)   # 5,760 raw clashes
res = analyze(big)
check("a realistic federation produces thousands of raw clashes, not four",
      res["clash_count"] == 5_760, res["clash_count"])
check("THE REDUCTION IS ORDER-OF-MAGNITUDE, not the 2:1 a toy fixture shows",
      res["reduction"] >= 10.0, res["reduction"])
check("  which is the entry's whole claim — thousands of clashes become a readable list",
      res["group_count"] <= 400, res["group_count"])
print(f"      [measured] {res['clash_count']} raw -> {res['group_count']} groups "
      f"({res['reduction']}:1)")

# --- 2. IT MUST NOT REDUCE BY LOSING CLASHES ------------------------------------------------------
# A grouper that silently drops rows posts a spectacular ratio. Count membership, not groups.
# `count` and `other_guids` are the engine's real keys — read off analyze() output, not guessed.
# My first draft invented `clash_count`/`clashes` and `score`, which is the same key-name seam this
# session has now hit four times: a name that sounds right is not a name that exists.
grouped = sum(g["count"] for g in res["groups"])
check("EVERY raw clash is accounted for inside a group — reduction is not deletion",
      grouped == res["clash_count"], (grouped, res["clash_count"]))

# --- 3. REDUCTION MUST SCALE WITH DENSITY, NOT SIT AT A CONSTANT ----------------------------------
# The property that separates real grouping from a fixed-size bucketing scheme.
sparse = analyze(duct_through_joists(n_ducts=40, joists_per_duct=2, storeys=8))
dense = analyze(duct_through_joists(n_ducts=40, joists_per_duct=30, storeys=8))
check("a denser fan-out reduces HARDER — the ratio tracks topology, it is not a constant",
      dense["reduction"] > sparse["reduction"] * 2, (sparse["reduction"], dense["reduction"]))
print(f"      [measured] sparse {sparse['reduction']}:1   dense {dense['reduction']}:1")

# --- 4. IT MUST NOT MERGE PROBLEMS A COORDINATOR WOULD HAVE TO SPLIT ------------------------------
# Distinct pairs sharing no element are distinct problems. If these collapse, "one issue" is a lie.
distinct = [{"a_guid": f"pipe-{i}", "a_class": "IfcPipeSegment", "a_model": "MEP",
             "b_guid": f"wall-{i}", "b_class": "IfcWall", "b_model": "ARCH",
             "volume": 0.05, "point": {"x": i, "y": 0, "z": 0}} for i in range(60)]
d = analyze(distinct)
check("60 unrelated clashes stay 60 issues — no element shared, nothing to merge",
      d["group_count"] == 60, d["group_count"])
check("  so the reduction ratio is honestly 1.0 when there is nothing to reduce",
      d["reduction"] == 1.0, d["reduction"])

# A mixed set: the fan-out collapses, the unrelated ones do not.
mixed = analyze(duct_through_joists(n_ducts=2, joists_per_duct=20) + distinct)
check("in a mixed set only the genuine fan-out collapses",
      mixed["group_count"] == 62, mixed["group_count"])

# --- 5. the ranking survives the reduction --------------------------------------------------------
check("groups are ranked, so the survivors are readable in consequence order",
      [g["severity_score"] for g in res["groups"]]
      == sorted((g["severity_score"] for g in res["groups"]), reverse=True),
      [g["severity_score"] for g in res["groups"][:5]])
check("  and a structural pair is not filed as Low",
      res["groups"][0]["severity_label"] in ("Medium", "High", "Critical"),
      res["groups"][0]["severity_label"])

print()
if FAILED:
    print(f"clash_reduction_scale: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("clash_reduction_scale: all checks passed")
