"""DARK-RECIPES — a recipe the engine can run but no surface can invoke is not a capability.

`edit.RECIPES` is the authoring engine's registry. `authoring_matrix.py` publishes it as the
**authoring-coverage matrix**, and its docstring calls that "an honest, single-source answer to
'what can this tool actually author?' … Users read it to judge maturity; contributors read it to
pick work."

It is derived from the registry, so it cannot drift **from the engine**. But the question it answers
is about the **product**, and those are different questions the moment a recipe has no caller. Two
sentences in the published output asserted the stronger claim outright — *"the CAD command line + AI
command bar + panels all dispatch these"* — while `nlauthor.RECIPE_SPECS`, which is what constrains
the CAD line and the AI bar, is a CURATED subset naming 12 of the 96.

This gate derives the reachable set the same way a user reaches one — by finding something that
names the recipe — and pins the remainder. A recipe added without a caller now shows up here instead
of silently inflating a maturity claim.

## What counts as reachable, and why each is included

  * a **web** call site — the client can invoke any recipe by name through `editIfc`
  * an **API router** — a purpose-built endpoint wrapping the recipe
  * the **MCP server** — the agent surface
  * `nlauthor.RECIPE_SPECS` — the CAD command line and the AI planner both dispatch from it

## Two false positives this had to survive, both of which inverted the answer

  1. **`authoring_matrix.py` names every recipe**, being the catalog. Counting that as reachability
     reported 18 of the 18 candidates as reached — a clean bill of health for a check that was
     reading the registry back to itself. Catalogs are EXCLUDED below.
  2. **`RECIPE_SPECS` had to be measured, not assumed.** Had it been derived from `RECIPES` — which
     is exactly what a reader expects of a spec list, and what the matrix's own note implies — every
     recipe would be reachable by natural language and this file would be measuring nothing.

Run: PYTHONPATH=src ./.venv/bin/python test_recipe_reach.py
"""
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "services", "data", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from aec_api import authoring_matrix  # noqa: E402
from aec_data import edit, nlauthor  # noqa: E402

# Files that NAME every recipe by being a catalog, index or generated doc. Naming a recipe here is
# registration, not reachability — see false positive (1) in the docstring.
CATALOGS = (
    "authoring_matrix.py",           # the coverage matrix itself
    "__pycache__",
    "docs/authoring-matrix.md",      # generated FROM the matrix
    "services/data/src/aec_data/",   # the engine: the definition and its dispatch table
)

SEARCHED = (
    "apps/web/src",
    "services/api/src/aec_api",
    "services/api/mcp_server.py",
)


def _code(src: str) -> str:
    """Source with comments removed — `//`, `/* */` and `#`.

    **A mention in a comment is not a call**, and this gate learned that the same way the two
    false positives in the docstring were learned: a mutation that swapped a recipe out of its
    catalog entry left the name in the entry's own explanatory comment, and the check reported the
    recipe as still reachable. It would have passed on code that no longer invoked it.

    `apps/web/src/viewer/tools/accessorNotCollapsed.test.ts` states the general rule this is the
    third instance of: a gate that greps source must strip comments, or its own documentation
    becomes its evidence.
    """
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"^\s*#.*$", "", src, flags=re.M)          # python comment lines
    src = re.sub(r"(?<![:\w])//.*$", "", src, flags=re.M)    # js line comments, sparing https://
    return src


def callers(recipe: str) -> list[str]:
    """Files whose CODE names `recipe` — something that invokes it, not something describing it."""
    paths = [os.path.join(ROOT, p) for p in SEARCHED]
    paths = [p for p in paths if os.path.exists(p)]
    out = subprocess.run(["grep", "-rl", "-E", rf"\b{recipe}\b", *paths],
                         capture_output=True, text=True).stdout.split()
    hits = []
    word = re.compile(rf"\b{re.escape(recipe)}\b")
    for f in out:
        if any(c in f for c in CATALOGS) or "test" in os.path.basename(f):
            continue
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                if word.search(_code(fh.read())):
                    hits.append(f)
        except OSError:
            hits.append(f)          # unreadable: assume it counts rather than under-report
    return hits


recipes = sorted(edit.RECIPES)
assert len(recipes) >= 90, f"only {len(recipes)} recipes — the registry did not import"

# `RECIPE_SPECS` is what the CAD command line and the AI planner dispatch from. Asserted to be a
# STRICT subset rather than assumed equal, because the whole finding turns on it.
specs = set(nlauthor.RECIPE_SPECS)
assert specs < set(recipes), "RECIPE_SPECS should be a subset of RECIPES"
assert len(specs) < len(recipes), (
    "RECIPE_SPECS now covers every recipe. If that is deliberate, every recipe is reachable by "
    "natural language and this gate's premise is void — rewrite it rather than deleting it."
)

uncalled = sorted(r for r in recipes if r not in specs and not callers(r))

# ---- the pinned sets -----------------------------------------------------------------------------
# The uncalled set splits in two, and the split is the point. `UNREACHED` is a capability no user can
# reach — a defect, listed deliberately rather than fixed. `SUPERSEDED` is a duplicate spelling of a
# capability users already have through another recipe — not a defect, and wiring it would ship a
# second control for the same outcome.
#
# **The two must be disjoint and must together cover the tree**, so neither can absorb the other
# quietly. Adding a recipe with no caller fails this until it is wired, listed as a gap, or shown to
# be a duplicate — and the last of those is not a free escape, because the equivalence is asserted
# below against what the two recipes actually author.
superseded = authoring_matrix.SUPERSEDED
assert not (set(superseded) & set(authoring_matrix.UNREACHED)), (
    f"a recipe is in both UNREACHED and SUPERSEDED: {sorted(set(superseded) & set(authoring_matrix.UNREACHED))}"
)
assert uncalled == sorted(set(authoring_matrix.UNREACHED) | set(superseded)), (
    "the matrix's UNREACHED + SUPERSEDED sets disagree with the tree.\n"
    f"  uncalled, derived from the tree : {uncalled}\n"
    f"  UNREACHED named in the matrix   : {sorted(authoring_matrix.UNREACHED)}\n"
    f"  SUPERSEDED named in the matrix  : {sorted(superseded)}\n"
    "A recipe that gained a caller must come OFF both; one added without a caller must go ON one of "
    "them (or be wired). The matrix is published as a maturity claim — it may not count what no user "
    "can invoke, and it may not report a duplicate as a gap."
)

# ---- the supersession claim, checked against what the recipes AUTHOR -----------------------------
# `SUPERSEDED` asserts that a reachable recipe produces the identical result. That is a claim about
# behaviour, so it is checked by running both and comparing products — not by reading the two lambdas
# and finding them similar. If `add_fire_equipment` ever stopped resolving "sprinkler" to the same
# class, predefined type, system and discipline, `add_sprinkler` would silently become a real gap
# while still sitting in the set that says it is not one.
#
# The comparison covers every attribute that distinguishes one MEP terminal from another: without the
# system and discipline it would pass on two elements that land on different systems, which is most of
# what these recipes are for.
if superseded:
    import tempfile

    import ifcopenshell

    from aec_data import massing  # type: ignore

    _tmp = os.path.join(tempfile.mkdtemp(prefix="supersede_"), "m.ifc")
    massing.generate_blank_ifc(_tmp, name="Supersession", storeys=1, storey_height=4.0, ground_size=40.0)
    _model = ifcopenshell.open(_tmp)

    def _fingerprint(guid: str) -> tuple:
        """(IFC class, PredefinedType, system name, system PredefinedType) for an authored element."""
        el = next((e for e in _model.by_type("IfcProduct") if e.GlobalId == guid), None)
        assert el is not None, f"no element with GUID {guid!r}"
        sys_name = sys_type = None
        for rel in (getattr(el, "HasAssignments", None) or []):
            grp = getattr(rel, "RelatingGroup", None)
            if grp is not None and grp.is_a("IfcDistributionSystem"):
                sys_name, sys_type = grp.Name, getattr(grp, "PredefinedType", None)
        return el.is_a(), getattr(el, "PredefinedType", None), sys_name, sys_type

    def _guid_of(result) -> str:
        return result if isinstance(result, str) else result["guid"]

    for dup, live in sorted(superseded.items()):
        assert dup in edit.RECIPES and live in edit.RECIPES, (dup, live)
        a = _fingerprint(_guid_of(edit.RECIPES[dup](_model, {"point": [2.0, 2.0]})))
        # The live recipe is invoked the way the product invokes it — `add_fire_equipment` takes the
        # kind as a parameter, and "sprinkler" is what the 🧯 button defaults to and sends.
        b = _fingerprint(_guid_of(edit.RECIPES[live](_model, {"kind": "sprinkler", "point": [4.0, 2.0]})))
        assert a == b, (
            f"{dup!r} is listed as superseded by {live!r}, but they author different elements:\n"
            f"  {dup:<20} -> {a}\n  {live:<20} -> {b}\n"
            "(class, PredefinedType, system name, system PredefinedType). If this is a deliberate "
            f"divergence then {dup!r} is a real capability again — move it to UNREACHED, or wire it."
        )

# The matrix must SAY so, not merely hold the sets.
m = authoring_matrix.matrix()
unreached = sorted(authoring_matrix.UNREACHED)
assert m["unreached_count"] == len(unreached), (m["unreached_count"], len(unreached))
assert m["superseded_count"] == len(superseded), (m["superseded_count"], len(superseded))
assert m["superseded"] == dict(sorted(superseded.items())), m["superseded"]
by_recipe = {r["recipe"]: r for cat in m["by_category"].values() for r in cat["recipes"]}
for r in unreached:
    assert by_recipe[r]["reach"] == "none", (r, by_recipe[r])
for r, live in superseded.items():
    assert by_recipe[r]["reach"] == "superseded", (r, by_recipe[r])
    assert by_recipe[r].get("superseded_by") == live, (r, by_recipe[r])
for r in sorted(specs):
    assert by_recipe[r]["reach"] == "cad+ai", (r, by_recipe[r])

# The two sentences that carried the false claim, pinned VERBATIM as negatives so they cannot return.
# Matched exactly rather than by keyword: the corrected text legitimately says both "every recipe is a
# GUID-stable server-side pass" (true — it is a statement about the ENGINE) and "dispatchable from the
# CAD command line and the AI planner" (true — of the 12 it names). A keyword pin flagged the fix as
# the defect, which is the failure mode of asserting on vocabulary instead of on the claim.
FALSE_CLAIMS = (
    "the CAD command line + AI command bar + panels all dispatch these",
    "dispatchable from the CAD command line, the "
    "AI command bar, the node canvas, or the tool panels",
)
for text in (m["note"], authoring_matrix.to_markdown()):
    for claim in FALSE_CLAIMS:
        assert claim not in text, (
            f"the published matrix claims {claim!r} of every recipe. RECIPE_SPECS — what the CAD line "
            f"and the planner actually dispatch from — names {len(specs)} of {len(recipes)}, and "
            f"{len(uncalled)} have no caller at all."
        )

print(f"RECIPE-REACH OK - {len(recipes)} recipes; {len(specs)} dispatchable from the CAD line and AI "
      f"planner (RECIPE_SPECS is CURATED, not derived); {len(uncalled)} with no caller, split into "
      f"{len(unreached)} reachable from no surface and named in authoring_matrix.UNREACHED "
      f"({', '.join(unreached) or '(none)'}) and {len(superseded)} SUPERSEDED — uncalled because a "
      "reachable recipe authors the identical element, asserted by running both and comparing what "
      f"they produce ({', '.join(f'{k} -> {v}' for k, v in sorted(superseded.items())) or '(none)'}). "
      "Reachability is derived by finding a CALLER outside the catalogs and the engine, because a "
      "recipe listed in the coverage matrix is registered, not reachable — counting the matrix as a "
      "caller reported every candidate as reached, which is this check measuring the registry against "
      "itself.")
