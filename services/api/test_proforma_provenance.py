"""R24-TRACE-UI ② — the proforma reports which of its inputs were declared and which were defaulted.

The defect this closes is not a wrong number, it is an unanswerable question: an equity IRR looks the
same whether it rests on ten sponsor-supplied inputs or on three supplied and seven defaulted, and that
difference is what an IC memo exists to surface.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_proforma_provenance.py
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_proforma_provenance.db")
for _f in ("./test_proforma_provenance.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api.proforma import provenance as pv  # noqa: E402
from aec_api.proforma.solve import solve  # noqa: E402

# A deal with the required keys supplied and the optional ones deliberately ABSENT, so the
# declared/defaulted split below is a real distinction rather than an artefact of a fully-populated dict.
DEAL = {
    "timing": {"construction_months": 18, "hold_years": 5, "start_date": "2026-01-01"},
    "cost_lines": [{"category": "hard", "name": "Hard costs", "amount": 20_000_000,
                    "start_month": 0}],
    "debt": {"rate": 0.07, "ltc": 0.6, "max_ltv": 0.65},
    "equity": {"lp_pct": 0.9, "gp_pct": 0.1},
    "operations": {"potential_rent_annual": 4_000_000, "stabilized_occ": 0.93,
                   "opex_annual": 1_400_000},
    "exit": {"exit_cap": 0.055},
    "waterfall": {"pref_rate": 0.08, "tiers": [{"hurdle": 0.08, "lp": 0.8, "gp": 0.2}]},
}

# --- the load-bearing check: provenance must run on what the CALLER SENT, not the validated dump ----
# The routes call solve(a.model_dump()), by which point pydantic has substituted every default. Deriving
# from that dict reports EVERY input as declared — a record that is uniformly wrong and looks complete.
# Asserted against pydantic itself rather than against my own reading of it.
from aec_api.routers.proforma_schemas import Assumptions  # noqa: E402

model = Assumptions(**DEAL)
full = model.model_dump()
declared = pv.declared_from(model)
assert "credit_loss_pct" in full["operations"], "pydantic should have filled the default"
assert "credit_loss_pct" not in declared.get("operations", {}), \
    "exclude_unset must omit what the caller never sent — the whole feature rests on this"
# The trap this guards, stated as a measurable claim rather than an absolute. The validated dump does
# not lose ALL of the distinction: `min_dscr` / `min_debt_yield` are `float | None = None`, and a None
# optional genuinely means "the engine has no constraint here", so those read as defaulted either way.
# What it does lose is every default with a real value — which is most of them, and enough to make the
# record wrong. The assertion is that it UNDER-REPORTS, because that is the failure that matters.
naive = pv.derive(full, solve(full))
assert naive["defaulted_input_count"] < 4, naive["defaulted_inputs"]

solved = solve(full)
d = pv.derive(declared, solved)

# --- the map must COVER solve()'s output, or it silently stops describing the model ----------------
# This is the assertion that matters most. FIGURE_INPUTS is hand-maintained; without this, adding a
# figure to solve() leaves it underived and the trace quietly becomes a partial view that looks whole.
missing = []
for section in pv.HEADLINE_SECTIONS:
    for name in (solved.get(section) or {}):
        key = f"{section}.{name}"
        if key in pv.NOT_FIGURES or key in pv.FIGURE_INPUTS:
            continue
        missing.append(key)
assert not missing, f"headline figures with no derivation entry (add to FIGURE_INPUTS or NOT_FIGURES): {missing}"

# ...and the other direction: a map entry naming a figure solve() does not emit is equally rot.
emitted = {f"{s}.{n}" for s in pv.HEADLINE_SECTIONS for n in (solved.get(s) or {})}
stale = [k for k in pv.FIGURE_INPUTS if k not in emitted]
assert not stale, f"FIGURE_INPUTS names figures solve() no longer emits: {stale}"

# Guard against a vacuous pass — an empty map would satisfy both checks above.
assert len(pv.FIGURE_INPUTS) >= 15, len(pv.FIGURE_INPUTS)
assert d["figure_count"] == len(pv.FIGURE_INPUTS), (d["figure_count"], len(pv.FIGURE_INPUTS))

# --- declared vs defaulted is a REAL distinction, checked against the deal above --------------------
# `exit.exit_cap` was supplied.
cap = d["figures"]["returns.exit_cap"]
assert cap["basis"] == "declared", cap
assert cap["declared"][0]["value"] == 0.055, cap

# `discount_rate` was NOT supplied, so npv rests on the engine's default and must say so.
npv = d["figures"]["returns.npv"]
assert "discount_rate" in [x["path"] for x in npv["defaulted"]], npv
assert npv["basis"] in ("defaulted", "mixed"), npv

# NOI mixes supplied (rent, occ, opex) and defaulted (credit loss, other income, reserves).
noi = d["figures"]["operations.stabilized_noi_annual"]
assert noi["basis"] == "mixed", noi
assert noi["declared_count"] == 3 and noi["defaulted_count"] == 3, noi
assert {x["path"] for x in noi["defaulted"]} == {
    "operations.credit_loss_pct", "operations.other_income_annual",
    "operations.reserves_annual"}, noi["defaulted"]

# An explicit None counts as ABSENT — the engine substitutes, so the number is the engine's and
# crediting the caller with it would be a provenance lie.
d_none = pv.derive({**declared, "operations": {**declared["operations"], "reserves_annual": None}},
                   solved)
assert "operations.reserves_annual" in d_none["defaulted_inputs"], d_none["defaulted_inputs"]

# --- the trace NEVER invents an element terminus ---------------------------------------------------
# The tempting version of this feature emits a chain that looks like it reaches a GlobalId. The
# proforma holds none, so every figure must say so rather than assert one.
for key, f in d["figures"].items():
    assert f["element_link"] is None, (key, f["element_link"])
    assert "no element link" in f["element_link_reason"], key

# --- the reviewer's actual question: what did nobody supply? ---------------------------------------
assert d["defaulted_input_count"] > 0, d
assert d["defaulted_inputs"] == sorted(set(d["defaulted_inputs"])), "deduped and stable for diffing"
assert sum(d["by_basis"].values()) == d["figure_count"], d["by_basis"]

# A fully-specified deal must reduce the defaulted set — otherwise the classifier is not reading the
# assumptions at all, which a single-fixture test would never notice.
FULL = {**DEAL,
        "discount_rate": 0.09,
        "operations": {**DEAL["operations"], "credit_loss_pct": 0.02,
                       "other_income_annual": 100_000, "reserves_annual": 120_000},
        "exit": {**DEAL["exit"], "selling_cost_pct": 0.02},
        # `points`, not `origination_fee_pct` — solve() reads `debt.get("points", 0.0)`. The strict
        # `extra="forbid"` schema rejected the wrong key outright, which is exactly the behaviour that
        # commit was for: a typo'd money field is refused rather than silently defaulted.
        "debt": {**DEAL["debt"], "min_dscr": 1.25, "min_debt_yield": 0.09, "points": 0.01}}
m_full = Assumptions(**FULL)
d_full = pv.derive(pv.declared_from(m_full), solve(m_full.model_dump()))
assert d_full["defaulted_input_count"] < d["defaulted_input_count"], \
    (d_full["defaulted_input_count"], d["defaulted_input_count"])
assert d_full["figures"]["returns.npv"]["basis"] == "declared", d_full["figures"]["returns.npv"]

# --- reachable over HTTP: a route that is only defined is not a feature ----------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    r = c.post("/proforma/provenance", json=DEAL)
    assert r.status_code == 200, (r.status_code, r.text[:200])
    body = r.json()
    assert body["figure_count"] == len(pv.FIGURE_INPUTS), body["figure_count"]
    # The route must show DEFAULTS. If it derived from the validated dump this would collapse toward 0,
    # which is the single mistake this feature can make and still look finished.
    assert body["defaulted_input_count"] == d["defaulted_input_count"],         (body["defaulted_input_count"], d["defaulted_input_count"])
    assert body["figures"]["returns.npv"]["basis"] in ("defaulted", "mixed"), body["figures"]["returns.npv"]
    # and the solve route now carries it inline
    s = c.post("/proforma/solve", json=DEAL)
    assert s.status_code == 200, s.text[:200]
    assert s.json()["provenance"]["figure_count"] == len(pv.FIGURE_INPUTS), s.json()["provenance"]


print(f"PROFORMA PROVENANCE (R24-TRACE-UI (2)) OK - {d['figure_count']} headline figures each report "
      f"which assumptions were DECLARED by the caller and which the engine DEFAULTED; the sparse deal "
      f"leaves {d['defaulted_input_count']} inputs defaulted and the fully-specified one "
      f"{d_full['defaulted_input_count']}. NOI is correctly 'mixed' (3 declared / 3 defaulted) and an "
      f"explicit None counts as absent, since the engine substitutes. The map is completeness-checked "
      f"BOTH ways against solve()'s own output, so a new figure cannot go underived and a removed one "
      f"cannot linger. No figure carries an element link: the proforma holds no GlobalId, so a terminus "
      f"would be invented — every figure states that instead.")
