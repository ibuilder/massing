"""GEN-SCORE — generative design-option scoring: massing variants ranked by cost · carbon · yield · code.

The frontier-bet payoff of the engines already built: `compute_massing` turns a zoning envelope into a
program, the conceptual estimator prices it, a whole-building carbon benchmark rates it, and the zoning
checks gate it — so N candidate options score in one deterministic pass and the developer sees WHICH
massing to take into design, with the trade-offs (cheapest vs greenest vs highest-yield) explicit rather
than argued from spreadsheets. Offline, deterministic, no LLM: the "generative" part is a systematic
variant grid around a base envelope, the scoring is the platform's own engines.

Scoring model (per option, normalized 0–100 across the option set, weighted composite):
  · cost      — conceptual $/SF (lower is better)
  · carbon    — embodied kgCO₂e/m² GFA benchmark by building type (lower is better)
  · yield     — net sellable/leasable area (higher is better)
  · compliance— zoning checks (FAR achieved ≤ allowed, height ≤ limit): a violation flags the option
                non-compliant, caps its composite, and excludes it from `recommended`.
"""
from __future__ import annotations

from typing import Any

from . import conceptual_estimate as ce
from .option_takeoff import OptionError

# The ONLY refusal that escapes score_options: every OptionError the takeoff raises is caught
# per-option below and turned into basis="none". Exported as a constant so the API layer can
# answer with it directly rather than stringifying a caught exception — the router cannot vouch
# for where a caught exception's text came from, which is exactly what the scanner objects to.
EMPTY_OPTIONS = "no options to score — pass at least one massing-params dict"

# Client-facing text for a takeoff refusal, keyed by OptionError.code. Literals, so the option a
# caller reads back is text this module wrote and not text an exception happened to carry.
TAKEOFF_REFUSALS = {
    "structure": "unknown structural system — no takeoff; carbon falls back to the benchmark",
    "wwr": "window-to-wall ratio out of range — no takeoff; carbon falls back to the benchmark",
    "invalid": "option rejected by the takeoff; carbon falls back to the benchmark",
}

# Whole-building embodied-carbon benchmarks, kgCO₂e/m² GFA (A1–A3 structure+envelope typicals from
# published whole-building LCA studies; editable defaults, same spirit as ce.COST_PER_SF). Types align
# with the conceptual estimator's catalog so one building_type drives both cost and carbon.
CARBON_KGCO2E_M2: dict[str, float] = {
    "office": 500.0, "office_highrise": 600.0, "multifamily": 400.0, "multifamily_highrise": 500.0,
    "retail": 350.0, "industrial": 320.0, "warehouse": 280.0, "hotel": 480.0, "hospital": 650.0,
    "school": 420.0, "parking_structure": 300.0, "mixed_use": 460.0, "data_center": 800.0,
    "senior_living": 430.0, "lab": 700.0,
}
_DEFAULT_CARBON = 450.0                      # unknown type → mid-range placeholder, flagged in the row
# Share of whole-building embodied carbon attributable to MEP + interior fit-out rather than to shell
# (structure + envelope). Whole-building LCA studies put shell at roughly two thirds; the rest is the
# part that varies with PROGRAMME, not geometry — a hospital's MEP against a warehouse's. Kept as one
# named constant so the split is a stated assumption rather than a number buried in a formula.
FITOUT_CARBON_SHARE = 0.35

DEFAULT_WEIGHTS = {"cost": 0.35, "carbon": 0.25, "yield": 0.25, "compliance": 0.15}
M2_TO_SF = 10.7639


def generate_options(base: dict, far_steps: list[float] | None = None,
                     types: list[str] | None = None) -> list[dict]:
    """The generative grid: massing variants around a `base` envelope (the compute_massing params).

    Varies FAR utilisation (default 60/80/100% of the base FAR) × building type (default: keep the
    base's). Deterministic — the same base always yields the same option set. Each option is a full
    params dict ready for `score_options`, labelled for the scoreboard."""
    far = float(base.get("far", 1.0))
    steps = far_steps or [0.6, 0.8, 1.0]
    tlist = types or [base.get("building_type") or "multifamily"]
    out: list[dict] = []
    for t in tlist:
        for s in steps:
            opt = dict(base)
            opt["far"] = round(far * s, 3)
            opt["building_type"] = t
            opt["label"] = f"{t} @ FAR {opt['far']:g}" + ("" if s == 1.0 else f" ({s:.0%} of max)")
            out.append(opt)
    return out


def board_pdf(project_name: str, scored: dict[str, Any]) -> bytes:
    """BOARDS — a styled one-page **design-option deck**: the scored option set as a client-facing
    artifact (title + recommendation, the comparison table, and score bars for the top options).
    Deterministic reportlab render over `score_options` output — a first-class deliverable, not a
    screenshot."""
    from io import BytesIO

    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    rows = scored.get("options") or []
    buf = BytesIO()
    W, H = landscape(letter)
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setFont("Helvetica-Bold", 24)
    c.drawString(18 * mm, H - 22 * mm, f"{project_name[:48]} — Design Options")
    c.setFont("Helvetica", 11)
    rec = scored.get("recommended")
    c.drawString(18 * mm, H - 30 * mm,
                 (f"Recommended: {rec}" if rec else "No compliant option to recommend") +
                 f"   ·   {len(rows)} option(s) scored")

    # comparison table
    cols = [("Option", 62), ("GFA m²", 22), ("Cost", 26), ("$/SF", 16), ("kgCO₂e/m²", 22),
            ("Sellable m²", 24), ("OK", 10), ("Score", 16)]
    x0, y = 18 * mm, H - 42 * mm
    c.setFont("Helvetica-Bold", 8.5)
    x = x0
    for name, wmm in cols:
        c.drawString(x, y, name)
        x += wmm * mm
    c.setLineWidth(0.5)
    c.line(x0, y - 2 * mm, x, y - 2 * mm)
    y -= 7 * mm
    c.setFont("Helvetica", 8.5)
    for r in rows[:12]:
        vals = [str(r.get("label", ""))[:44], f"{r.get('gfa_m2', 0):,.0f}",
                f"${r.get('cost_total', 0):,.0f}", f"{r.get('cost_per_sf') or 0:,.0f}",
                f"{r.get('carbon_intensity_kgco2e_m2', 0):,.0f}",
                f"{r.get('yield_net_sellable_m2', 0):,.0f}",
                "✓" if r.get("compliant") else "✗", f"{r.get('composite', 0):.0f}"]
        x = x0
        for (_name, wmm), v in zip(cols, vals):
            c.drawString(x, y, v)
            x += wmm * mm
        y -= 6 * mm
        if y < 40 * mm:
            break

    # score bars for the top 4 (composite out of 100)
    top = rows[:4]
    bx, bw = 18 * mm, W - 36 * mm
    y -= 4 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(bx, y, "Composite scores")
    y -= 6 * mm
    for r in top:
        c.setFont("Helvetica", 8.5)
        c.drawString(bx, y, str(r.get("label", ""))[:52])
        frac = max(0.0, min(1.0, float(r.get("composite", 0)) / 100.0))
        c.setFillColorRGB(0.29, 0.55, 1.0)
        c.rect(bx + 70 * mm, y - 1, (bw - 90 * mm) * frac, 3.4 * mm, fill=1, stroke=0)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(bx + 72 * mm + (bw - 90 * mm) * frac, y, f"{r.get('composite', 0):.0f}")
        y -= 6.5 * mm
    c.setFont("Helvetica-Oblique", 7.5)
    c.drawString(18 * mm, 14 * mm, (scored.get("note") or "")[:180])
    c.showPage()
    c.save()
    return buf.getvalue()


def _num(v: Any) -> float | None:
    """A real number, or None. Deliberately NOT `float(v or 0)`: on a lower-is-better axis 0 is the
    minimum, so coercing a missing value to zero awards the best possible score for having no data."""
    if v is None or isinstance(v, bool) or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f or f in (float("inf"), float("-inf")) else f


def _norm(vals: list[float], value: float, higher_better: bool) -> float:
    """Min-max normalize `value` against the option set → 0–100. A flat set (all equal) scores 100 —
    the criterion doesn't differentiate, so it shouldn't penalize anyone."""
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return 100.0
    x = (value - lo) / (hi - lo)
    return round((x if higher_better else 1.0 - x) * 100.0, 1)


def _evaluate(opt: dict) -> dict[str, Any]:
    """One option through the engines: massing → program, conceptual $/SF → cost, carbon benchmark,
    zoning checks. Raw (un-normalized) figures; `score_options` normalizes across the set."""
    from aec_data import massing as mg  # type: ignore  # deferred heavy import

    m = mg.compute_massing(opt)
    gfa_m2 = float(m.get("buildable_gfa_m2") or 0.0)
    gfa_sf = float(m.get("buildable_gfa_sf") or gfa_m2 * M2_TO_SF)
    btype = (opt.get("building_type") or "multifamily").lower()
    est = ce.estimate({"building_type": btype, "gfa_sf": gfa_sf, "region": opt.get("region"),
                       "year": opt.get("year"), "stories": m.get("floors"),
                       "units": m.get("units"), "soft_cost_pct": opt.get("soft_cost_pct")})
    carbon_int = CARBON_KGCO2E_M2.get(btype, _DEFAULT_CARBON)
    carbon_t = round(gfa_m2 * carbon_int / 1000.0, 1)          # tCO₂e total

    # zoning compliance off the massing result: FAR + height. compute_massing already binds the
    # program to the envelope, so violations here mean the INPUT asked past the envelope.
    violations: list[str] = []
    far_allowed = float(opt.get("far", 0) or 0)
    if far_allowed and float(m.get("far_achieved") or 0) > far_allowed + 1e-6:
        violations.append(f"FAR {m['far_achieved']} exceeds allowed {far_allowed}")
    hl = opt.get("height_limit")
    if hl is not None and float(m.get("building_height_m") or 0) > float(hl) + 1e-6:
        violations.append(f"height {m['building_height_m']}m exceeds limit {hl}m")

    # GEN-SCORE depth: an elemental takeoff behind the option, so carbon comes from QUANTITIES rather
    # than a typology benchmark. A benchmark gives two options the same intensity even when one is a
    # squat plate and the other a slender tower with twice the façade per m² — the exact trade-off
    # this scorer exists to expose. The benchmark stays the fallback, and `carbon_basis` says which
    # one you are reading.
    from . import option_takeoff
    try:
        to = option_takeoff.takeoff(m, structure=opt.get("structure"), wwr=opt.get("wwr"))
    except OptionError as e:
        # The note goes into the RESPONSE BODY, so it is selected from the literal table below by the
        # exception's `code` — never built from str(e). An exception's text is written for a
        # traceback and can carry detail from wherever it was raised; a response should not.
        to = {"basis": "none", "note": TAKEOFF_REFUSALS.get(e.code, TAKEOFF_REFUSALS["invalid"])}
    if to.get("basis") == "quantity" and to.get("carbon_intensity_kgco2e_m2"):
        # HYBRID, and it has to be. The takeoff sees only GEOMETRY — structure, envelope, partitions —
        # so on its own it gives a warehouse and a hospital with the same envelope identical carbon,
        # which is false: the difference between them lives in MEP and fit-out. Those are precisely
        # the elements the takeoff reports as uncovered (no EPD factor). So the geometry-driven part
        # comes from quantities and the type-driven remainder from the benchmark, and BOTH axes reach
        # the score. Using either alone loses one of them.
        shell = to["carbon_intensity_kgco2e_m2"]
        fitout = round(CARBON_KGCO2E_M2.get(btype, _DEFAULT_CARBON) * FITOUT_CARBON_SHARE, 1)
        carbon_int = round(shell + fitout, 1)
        carbon_t = round(gfa_m2 * carbon_int / 1000.0, 1)
        carbon_basis = "hybrid"
        to["carbon_split"] = {"shell_kgco2e_m2": shell, "fitout_kgco2e_m2": fitout,
                              "shell_pct": round(100.0 * shell / carbon_int, 1) if carbon_int else None,
                              "note": "shell from elemental quantities; fit-out (MEP + finishes) from "
                                      "the type benchmark, because no geometry at massing stage "
                                      "predicts it"}
    else:
        carbon_basis = "benchmark"

    return {
        "label": opt.get("label") or f"{btype} FAR {far_allowed:g}",
        "building_type": btype,
        "carbon_basis": carbon_basis,
        "takeoff": to,
        "massing": {k: m.get(k) for k in ("floors", "building_height_m", "buildable_gfa_m2",
                                          "buildable_gfa_sf", "net_sellable_m2", "units",
                                          "far_achieved", "binding_constraint")},
        "cost_total": est["total_cost"], "cost_per_sf": (est.get("metrics") or {}).get("cost_per_sf"),
        "carbon_intensity_kgco2e_m2": carbon_int, "carbon_total_tco2e": carbon_t,
        "carbon_benchmark_matched": btype in CARBON_KGCO2E_M2,
        "yield_net_sellable_m2": float(m.get("net_sellable_m2") or 0.0),
        "compliant": not violations, "violations": violations,
    }


def score_options(options: list[dict], weights: dict[str, float] | None = None) -> dict[str, Any]:
    """Score N candidate options and rank them. Composite = Σ(weightᵢ × normalized criterionᵢ); a
    non-compliant option's composite is capped at 49 (never above any compliant one's floor) and it is
    excluded from `recommended`. Raises ValueError on an empty set."""
    if not options:
        raise OptionError(EMPTY_OPTIONS)
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    rows = [_evaluate(o) for o in options]

    # R22-OPTION-OBJECT: a MISSING criterion is not a good score. `cost_per_sf` is
    # `(est.get("metrics") or {}).get("cost_per_sf")` — it can be None — and the previous
    # `float(x or 0.0)` turned that into 0.0. On a lower-is-better axis 0 is the minimum, so an
    # option with NO cost data normalized to 100: the best possible cost score, awarded FOR LACKING
    # DATA, ranking it above every option that had a real number. Same shape as the mixed-carbon-
    # basis problem below, and handled the same way: exclude it, then say so.
    def _vals(key: str) -> list[float]:
        return [float(r[key]) for r in rows if _num(r.get(key)) is not None]

    psf, cint, sell = _vals("cost_per_sf"), _vals("carbon_intensity_kgco2e_m2"), \
        _vals("yield_net_sellable_m2")
    CRIT = (("cost", "cost_per_sf", psf, False), ("carbon", "carbon_intensity_kgco2e_m2", cint, False),
            ("yield", "yield_net_sellable_m2", sell, True))
    for r in rows:
        scores: dict[str, float | None] = {"compliance": 100.0 if r["compliant"] else 0.0}
        missing: list[str] = []
        for name, key, pool, higher in CRIT:
            v = _num(r.get(key))
            if v is None or not pool:
                scores[name] = None                    # scored on fewer dimensions — never on 100
                missing.append(name)
            else:
                scores[name] = _norm(pool, v, higher_better=higher)
        # Composite over the criteria this option ACTUALLY has, with the weights renormalized over
        # them. Averaging a missing criterion in as any number — 0 or 100 — states something about
        # the option that nobody measured.
        present_w = sum(w[k] for k in scores if scores[k] is not None) or 1.0
        composite = round(sum(w[k] * v for k, v in scores.items() if v is not None) / present_w, 1)
        if not r["compliant"]:
            composite = min(composite, 49.0)           # a violating option never outranks a compliant one
        r["scores"] = scores
        r["composite"] = composite
        r["missing_criteria"] = missing
        r["fully_scored"] = not missing
    rows.sort(key=lambda r: -r["composite"])
    # Recommending an option that was scored on FEWER dimensions than its rivals is exactly the
    # failure this ring is named for — a massing evaluated without its returns. It stays in the
    # ranking (a reader may still want to see it) but it cannot be the recommendation.
    compliant = [r for r in rows if r["compliant"] and r["fully_scored"]]
    partial = [r["label"] for r in rows if not r["fully_scored"]]

    # A quantity-derived carbon figure and a typology benchmark are different claims about the world.
    # Ranking options whose carbon came from different bases is comparing unlike things, and the
    # carbon weight is doing work it hasn't earned — so say so rather than averaging over it.
    bases = {r.get("carbon_basis") for r in rows}
    mixed = len(bases) > 1
    carbon_note = ""
    if mixed:
        n_q = sum(1 for r in rows if r.get("carbon_basis") in ("quantity", "hybrid"))
        carbon_note = (f" ⚠ CARBON BASES ARE MIXED: {n_q} of {len(rows)} option(s) are quantity-derived, "
                       f"the rest are typology benchmarks. Those are different claims — the carbon "
                       f"ranking across this set is not like-for-like.")
    elif bases <= {"quantity", "hybrid"}:
        carbon_note = (" Carbon is quantity-derived for every option (elemental takeoff → EPD factors), "
                       "so the carbon ranking IS like-for-like.")

    return {
        "options": rows, "weights": w,
        "recommended": (compliant[0]["label"] if compliant else None),
        "carbon_basis": sorted(b for b in bases if b),
        "partially_scored": partial,
        "partially_scored_note": (
            f"{len(partial)} option(s) are missing at least one criterion and were scored on the "
            "criteria they have, with the weights renormalized over those. They are RANKED but "
            "cannot be recommended: a missing criterion is not a good score, and recommending an "
            "option measured on fewer dimensions than its rivals is the failure this guards."
            if partial else ""),
        "carbon_basis_mixed": mixed,
        "note": ("Deterministic scoring through the platform's own engines: conceptual $/SF (cost), "
                 "embodied carbon (carbon), net sellable area (yield), and zoning FAR/height checks "
                 "(compliance). Normalized within THIS option set — scores compare options to each "
                 "other, not to an absolute standard. Editable defaults; refine with a detailed "
                 "takeoff + EPDs as the design develops.") + carbon_note,
    }
