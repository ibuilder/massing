"""R37-CONTRACT — the two contract findings from the tested-but-unwired audit, pinned.

Both are the same defect wearing different clothes: **a contract documented in prose and enforced
nowhere**, so the thing that was supposed to be evidence could be supplied by anyone for free.

① `cited_answer` documents four citation kinds and `Assumptions.sources` is typed `dict[str, list[dict]]`
   with a comment saying those dicts are `cite_doc`/`cite_record`/`cite_rule`/`cite_ifc`. Nothing
   checked. Measured before the fix, against the real functions:

       {}                        -> 100% provenance coverage, status "cited", confidence 0.6
       {"source_type": "ifc"}    -> confidence 0.733  (a complete cite_record scored 0.667)

   An EMPTY DICT was full provenance, and asserting the strongest kind while naming no source
   out-scored a real weaker citation — because rank was read off a self-declared string. On a module
   whose stated thesis is "an uncited assumption is uncited, never assumed sound".

② `licensing.TIER_FEATURES` has marked `sso` Enterprise-only since the tiers were written and the
   Settings panel renders that table, but no code consulted it: any tier that configured a SAML IdP
   got SSO. Meanwhile upgrade messaging came from a hand-kept second copy of the matrix that listed
   only the openBIM formats, so every Home-tier export refusal read "requires the Massing a higher
   plan (or higher)".

The recurring lesson, for the third time this phase: **a duplicated derivation is where the
unmaintained half hides**, and a check whose population accepts anything counts noise as evidence.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from aec_api import assumption_provenance as ap  # noqa: E402
from aec_api import cited_answer as ca  # noqa: E402
from aec_api import licensing, saml  # noqa: E402

checks = 0


def check(cond, msg):
    """Assert `cond`, counting it, so the summary line reports how much was actually verified."""
    global checks
    assert cond, msg
    checks += 1


# --- ① is_citation: the contract's own rule ----------------------------------
GUID = "3vB2$aB1n0kQm8XzRt7Wq2"
for good in (ca.cite_ifc(GUID), ca.cite_record("rfi", 12), ca.cite_rule("readiness/spec"),
             ca.cite_doc("doc-7", page=3)):
    check(ca.is_citation(good), f"constructor output must be a citation: {good}")

# Every kind the rank table scores must be constructible AND recognised — otherwise a kind can carry
# provenance weight that no producer can legitimately earn.
check(set(ca._RANK) == set(ca._IDENTIFIES), "every ranked source_type needs an identifying field")

for bad, why in [
    ({}, "an empty dict is not a citation"),
    ({"foo": "bar"}, "an arbitrary dict is not a citation"),
    ({"source_type": "vibes", "guid": GUID}, "an unknown source_type is not a citation"),
    ({"source_type": "ifc"}, "ifc without a guid identifies nothing"),
    ({"source_type": "ifc", "guid": ""}, "an empty guid identifies nothing"),
    ({"source_type": "ifc", "guid": "   "}, "a whitespace guid identifies nothing"),
    ({"source_type": "record"}, "record without a record_ref identifies nothing"),
    ({"source_type": "rule"}, "rule without a rule_id identifies nothing"),
    ({"source_type": "doc"}, "doc without a document_id identifies nothing"),
    ({"source_type": "ifc", "guid": 123}, "a non-string identifier is not an identifier"),
    (None, "None is not a citation"),
    ("cite", "a string is not a citation"),
    ([], "a list is not a citation"),
]:
    check(not ca.is_citation(bad), why)

# --- ① the exact numbers from the docstring, now refuted ---------------------
check(ca.provenance_confidence([{}]) == 0.0, "an empty dict must carry no confidence")
check(ca.provenance_confidence([{"source_type": "ifc"}]) == 0.0,
      "a kind claim with no source must carry no confidence")
check(ca.provenance_confidence([{"source_type": "ifc"}]) < ca.provenance_confidence([ca.cite_record("rfi", 1)]),
      "an unidentified strong-kind claim must never out-score a complete citation")
check(ca.provenance_confidence([ca.cite_ifc(GUID)]) > 0, "a real citation still scores")
# a real citation is not diluted by junk sitting beside it
check(ca.provenance_confidence([ca.cite_ifc(GUID), {}]) == ca.provenance_confidence([ca.cite_ifc(GUID)]),
      "junk must not change a real citation's score in either direction")

# --- ① build(): coverage counts real citations, and junk no longer crashes ---
junk_only = ca.build([ca.claim("unbacked", [{"source_type": "ifc"}])])
check(junk_only["coverage"] == 0.0 and not junk_only["fully_cited"],
      f"a claim cited only by junk is uncited: {junk_only['coverage']}")
check(junk_only["uncited_claims"] == [0], junk_only["uncited_claims"])
check(junk_only["citation_count"] == 0, "junk must not be counted as a citation")
# source_types indexed cit["source_type"] directly — one dict without the key took down the answer
check(ca.build([ca.claim("x", [{"no": "type"}])])["source_types"] == {},
      "a dict with no source_type must not raise")
real = ca.build([ca.claim("backed", [ca.cite_ifc(GUID)])])
check(real["coverage"] == 1.0 and real["fully_cited"] and real["citation_count"] == 1, real)
check(real["source_types"] == {"ifc": 1}, real["source_types"])

# --- ① assumption_provenance: the consumer that receives caller dicts --------
def prov(sources):
    """Run `assumption_provenance` over one material assumption carrying `sources`."""
    return ap.provenance({"exit": {"exit_cap": 0.055}, "sources": {"exit.exit_cap": sources}})


for junk, why in [([{}], "empty dict"), ([{"foo": "bar"}], "arbitrary dict"),
                  ([{"source_type": "ifc"}], "kind with no source"),
                  ([{"source_type": "vibes"}], "unknown kind")]:
    r = prov(junk)
    check(r["coverage_pct"] == 0.0, f"{why} must not be provenance coverage: {r['coverage_pct']}")
    check(r["assumptions"][0]["status"] == ap.STATUS_UNCITED, f"{why} must read as uncited")
    # counted and NAMED, not dropped silently — the caller believes this assumption is sourced
    check(r["malformed_citation_count"] == 1, f"{why} must be counted: {r['malformed_citation_count']}")
    check(r["malformed_citation_paths"] == ["exit.exit_cap"], f"{why} must be named")
    check("exit.exit_cap" in r["uncited"], f"{why} must appear in the uncited list")

# A NON-DICT recorded value is malformed too, not silence. The first version of the fix filtered
# `isinstance(c, dict)` while building the list and counted after the discard, so a plain string —
# the most natural way to get this field wrong — reported 0 malformed and read as plainly uncited.
# Caught by CodeRabbit on #372; it is the same defect as ①, one layer down.
for junk, why in [(["Appraisal p.12"], "a plain string in the list"),
                  ("Appraisal p.12", "a bare string instead of a list"),
                  ([0.055], "a number"),
                  ([None], "a None entry")]:
    r = prov(junk)
    check(r["malformed_citation_count"] == 1, f"{why} must be counted: {r['malformed_citation_count']}")
    check(r["malformed_citation_paths"] == ["exit.exit_cap"], f"{why} must be named")
    check(r["coverage_pct"] == 0.0, f"{why} is not coverage")

# ...but an ABSENT or EMPTY value is silence, not a malformed record — nothing was claimed.
for quiet, why in [(None, "nothing recorded"), ([], "an empty list"), ({}, "an empty mapping")]:
    r = prov(quiet)
    check(r["malformed_citation_count"] == 0, f"{why} must not be reported as malformed")
    check(r["malformed_citation_paths"] == [], f"{why} must name no path")

# a real citation beside an unreadable one: cited, and the unreadable one still reported
half = prov([ca.cite_ifc(GUID), "p.12"])
check(half["coverage_pct"] == 100.0 and half["malformed_citation_count"] == 1, half)

ok = prov([ca.cite_record("rfi", 12)])
check(ok["coverage_pct"] == 100.0 and ok["malformed_citation_count"] == 0, ok)
check(ok["assumptions"][0]["status"] == ap.STATUS_CITED, ok)
# a real citation beside a junk one: still cited, and the junk is still reported
mixed = prov([ca.cite_ifc(GUID), {}])
check(mixed["coverage_pct"] == 100.0 and mixed["malformed_citation_count"] == 1, mixed)
check("malformed_citations" not in ok["assumptions"][0], "a clean row carries no malformed key")
# the status wording must say what a malformed entry counts as, or the number is unexplained
check("malformed_citation_paths" in ap._WHY[ap.STATUS_UNCITED], ap._WHY[ap.STATUS_UNCITED])

# --- ② licensing: upgrade messaging derived from the matrix ------------------
check(not hasattr(licensing, "_MIN_TIER") and not hasattr(licensing, "_EXPORT_MIN_TIER"),
      "the hand-kept min-tier dicts must be gone, not shadowed by the derivation")
check(not hasattr(licensing, "tier_at_least"),
      "tier_at_least had no caller and was replaced by the derivations that do")
check(licensing.min_tier_for_export("png") == "Home", licensing.min_tier_for_export("png"))
check(licensing.min_tier_for_export("ifcx") == "Commercial", "ifcx is openBIM data-out")
# `nwd` was delisted in v0.3.1119 (a closed Autodesk binary nothing here can write), so it is now
# an example of the OTHER branch: a format that names no upgrade because no plan grants it.
check(licensing.min_tier_for_export("nwd") is None, "nwd was delisted and names no plan")
check(licensing.min_tier_for_export("step") is None and licensing.min_tier_for("bogus") is None,
      "an ungranted capability names no upgrade")

# the 402 body itself — the defect was visible only in the rendered string
_enf, _cur = licensing.enforcement_enabled, licensing.current_tier
licensing.enforcement_enabled, licensing.current_tier = (lambda: True), (lambda: "free")
try:
    from fastapi import HTTPException
    for fmt, want in [("png", "Massing Home plan"), ("ifc", "Massing Commercial plan"),
                      ("ifcx", "Massing Commercial plan")]:
        try:
            licensing.require_export(fmt)
            raise AssertionError(f"{fmt} must be refused on free with enforcement on")
        except HTTPException as e:
            check(e.status_code == 402 and want in e.detail, f"{fmt}: {e.detail}")

    # The population is EVERY declared format and EVERY declared boolean entitlement, and the property
    # is the RENDERED refusal — not that the derivation agrees with the list it reads, which it cannot
    # fail to do. Asserting the message is what catches the original defect: the old dict listed only
    # the openBIM formats and the other six rendered "the Massing a higher plan (or higher)".
    every_fmt = {f for feats in licensing.TIER_FEATURES.values() for f in feats["exports"]}
    # Anti-vacuity: the loop below proves nothing over an empty set. **Not a fixed floor** — that is
    # what this was, and it moved twice in two releases (9 → 8 → 7) as `nwd`, `obj` and `rvt` were
    # each delisted for cause. A number that has to be edited every time the thing it measures changes
    # legitimately is measuring the wrong thing: the property is "there is a population", not "the
    # population is this big". The delistings themselves are pinned by name in
    # `services/api/test_export_promises.py`, which is where that belongs.
    check(every_fmt, "the tier table must sell some exports, or the loop below asserts nothing")
    for fmt in sorted(every_fmt):
        try:
            licensing.require_export(fmt)
            raise AssertionError(f"{fmt} must be refused on free with enforcement on")
        except HTTPException as e:
            check("a higher plan (or higher)" not in e.detail, f"{fmt} names no plan: {e.detail}")
            check(any(f"Massing {lab} plan" in e.detail for lab in licensing.TIER_LABEL.values()),
                  f"{fmt} must name a real plan: {e.detail}")
    every_feat = {k for feats in licensing.TIER_FEATURES.values()
                  for k, on in feats.items() if k != "exports" and on}
    for feat in sorted(every_feat):
        try:
            licensing.require(feat)
            raise AssertionError(f"{feat} must be refused on free with enforcement on")
        except HTTPException as e:
            check(any(f"Massing {lab} plan" in e.detail for lab in licensing.TIER_LABEL.values()),
                  f"{feat} must name a real plan: {e.detail}")
    try:
        licensing.require_export("step")
        raise AssertionError("step must be refused")
    except HTTPException as e:
        check("not included on any Massing plan" in e.detail, e.detail)
    try:
        licensing.require("sso", "SAML single sign-on")
        raise AssertionError("sso must be refused on free")
    except HTTPException as e:
        check("SAML single sign-on requires the Massing Enterprise plan" in e.detail, e.detail)
finally:
    licensing.enforcement_enabled, licensing.current_tier = _enf, _cur

# --- ② the sso entitlement is actually consulted -----------------------------
check(hasattr(saml, "is_available"), "SSO entitlement needs a predicate the advertisement can share")
_ise, _allows = saml.is_enabled, licensing.allows
try:
    saml.is_enabled = lambda: True
    licensing.allows = lambda f, tier=None: f != "sso"
    check(not saml.is_available(), "a configured IdP without the sso entitlement is not available")
    licensing.allows = lambda f, tier=None: True
    check(saml.is_available(), "configured + entitled is available")
    saml.is_enabled = lambda: False
    check(not saml.is_available(), "entitled but unconfigured is not available")
finally:
    saml.is_enabled, licensing.allows = _ise, _allows

# Both the routes and the advertisement must go through the entitlement — gating only the routes
# leaves the sign-in page rendering an SSO button that 402s on click (the symmetric-path defect
# this phase hit four separate times).
# Asserted over the AST, not over source substrings: `def _require_saml()` contains the text
# `_require_saml()`, so a naive count reads 4 for 3 call sites — the same substring trap that made
# the previous item's first test pass on its own docstring.
import ast  # noqa: E402

router_src = (Path(__file__).parent / "src/aec_api/routers/saml.py").read_text()
tree = ast.parse(router_src)
routes = [n for n in tree.body
          if isinstance(n, ast.FunctionDef) and any(
              isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
              and isinstance(d.func.value, ast.Name) and d.func.value.id == "router"
              for d in n.decorator_list)]
check(len(routes) == 3, f"expected 3 SAML routes, found {[r.name for r in routes]}")
for fn in routes:
    called = {c.func.id for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    check("_require_saml" in called, f"{fn.name} must go through the entitlement guard")
    # a route that re-checks configuration itself would 404 before reaching the entitlement
    attrs = {f"{c.func.value.id}.{c.func.attr}" for c in ast.walk(fn)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
             and isinstance(c.func.value, ast.Name)}
    check("saml.is_enabled" not in attrs, f"{fn.name} must not re-check configuration and skip the gate")

guard = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_require_saml")
guard_attrs = {f"{c.func.value.id}.{c.func.attr}" for c in ast.walk(guard)
               if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
               and isinstance(c.func.value, ast.Name)}
check({"saml.is_enabled", "licensing.require"} <= guard_attrs,
      f"the guard must check both configuration and entitlement: {guard_attrs}")

auth_tree = ast.parse((Path(__file__).parent / "src/aec_api/routers/auth.py").read_text())
providers = next(n for n in ast.walk(auth_tree)
                 if isinstance(n, ast.FunctionDef) and n.name == "auth_providers")
adv = {f"{c.func.value.id}.{c.func.attr}" for c in ast.walk(providers)
       if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
       and isinstance(c.func.value, ast.Name)}
check("saml.is_available" in adv and "saml.is_enabled" not in adv,
      f"/auth/providers must advertise availability, not mere configuration: {adv}")

print(f"R37-CONTRACT OK — {checks} checks. An empty dict no longer scores 100% provenance coverage; "
      "a source_type with no source no longer out-ranks a complete citation; malformed citations are "
      "counted and named rather than silently credited. Upgrade messaging is derived from "
      "TIER_FEATURES, so no export refusal reads 'the Massing a higher plan (or higher)'; the sso "
      "entitlement gates the SAML routes AND the button that advertises them.")
