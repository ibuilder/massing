"""MOD-SWEEP — the field-level invariants a register needs to read as a tool rather than a form.

The R30 sweep asked a different question from `test_module_config` (is this module *well-formed*?) and
from `test_module_rooms` (is it in the right *room*?). This one asks whether each field carries enough
declared meaning to be rendered, filtered and trusted. The audit that produced these rules found, over
133 modules and 1171 fields, that the entire field vocabulary in use was:

    name · label · type · fieldset · options · required · module · source_module · source_field · op · help

Eleven attributes, all structural or presentational. Nothing said what a number *measures*, nothing
distinguished a percentage from a count, and half the concepts that already had their own register were
stored as loose strings. Those are the three things asserted here.

Every rule below is a ratchet: it encodes a state already reached, so it cannot be satisfied by
weakening it, only by fixing the module. Counts are floors, not equalities — adding a module should
never require editing this file, but removing the work should fail it.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_module_fields.py
"""
import json
import os

MODULES_DIR = os.path.join(os.path.dirname(__file__), "modules")

mods = {}
for name in sorted(os.listdir(MODULES_DIR)):
    p = os.path.join(MODULES_DIR, name, "module.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            mods[name] = json.load(fh)

assert len(mods) >= 130, f"expected the full module set, read {len(mods)}"
keys = set(mods)
NUMERIC = {"number", "currency", "percent"}

# ---- 1. a percentage is typed as one -------------------------------------------------------------
# 20 fields named `*_pct` were typed `number`, which renders 7.5% and 7.5 identically in a table and
# formats with thousands separators. `percent` appears anywhere in the name, not just as a suffix —
# `evm_snapshot.percent_complete` is the one a suffix-only rule missed.
bad_pct = [f"{k}.{f['name']}" for k, m in mods.items() for f in m.get("fields", [])
           if f["type"] == "number" and ("pct" in f["name"] or "percent" in f["name"])]
assert not bad_pct, f"percentage-named fields typed 'number': {bad_pct}"

# ---- 2. a unit belongs to a magnitude, and only to a magnitude -----------------------------------
united = [(k, f) for k, m in mods.items() for f in m.get("fields", []) if f.get("unit")]
for k, f in united:
    assert f["type"] in NUMERIC, f"{k}.{f['name']}: unit {f['unit']!r} on a {f['type']} field"
assert len(united) >= 60, (
    f"only {len(united)} fields declare a unit; the sweep moved 67 units out of field NAMES "
    "(elevation_ft, expected_life_years) and into the schema, where they can be rendered beside an "
    "input and appended to a cell. A unit in a name is readable only by a human."
)
# A calendar year is a point in time, not a duration — the suffix rule could not tell them apart and
# labelled three of them 'yr'. Named so the distinction cannot be re-lost by a future bulk pass.
for k, fname in (("capital_plan", "planned_year"), ("fca_element", "recommended_year"),
                 ("market_assumption", "construction_start_year")):
    f = next(x for x in mods[k]["fields"] if x["name"] == fname)
    assert "unit" not in f, f"{k}.{fname} is a calendar year, not a duration — it takes no unit"

# ---- 3. the table a user first sees shows enough to decide whether to open a row ------------------
thin = sorted(k for k, m in mods.items() if len(m.get("list_columns") or []) < 3)
assert len(thin) <= 17, (
    f"{len(thin)} registers show fewer than 3 columns: {thin}. 15 had none at all and 40 had two, so "
    "the table was a title and a status chip — a list you must open every row of is not a register."
)
# columns must name real fields (test_module_config checks this too; kept so this file stands alone)
for k, m in mods.items():
    names = {f["name"] for f in m.get("fields", [])}
    for c in m.get("list_columns") or []:
        assert c in names, f"{k}: list_column {c!r} is not a field"

# A reference is the most useful column in a register — *who* it is with — and it appeared in only 2
# of 133 registers' columns while 98 reference fields existed. The tool had the relationship and the
# table did not show it.
with_ref = [k for k, m in mods.items()
            if any(f["type"] == "reference" for f in m.get("fields", [])
                   if f["name"] in (m.get("list_columns") or []))]
assert len(with_ref) >= 30, f"only {len(with_ref)} registers surface a reference as a column"

# ---- 4. relationships: the additive text+reference pattern ----------------------------------------
# 74 text fields named a concept that already had its own register. They are NOT converted in place:
# a reference stores a uuid, and a converted field's legacy string used to render as a link labelled
# with its first 8 characters — a control that looked resolved and opened nothing. The codebase already
# had the safe pattern in three places (investor+investor_company, lease+tenant_company,
# subcontract+vendor_company): add the reference BESIDE the text, backfill, retire the text later.
pairs = []
for k, m in mods.items():
    by = {f["name"]: f for f in m.get("fields", [])}
    for n, f in by.items():
        if f["type"] != "reference":
            continue
        for suf in ("_company", "_loc", "_spec", "_system", "_contact", "_package", "_ref", "_id"):
            stem = n[: -len(suf)] if n.endswith(suf) else None
            if stem and stem in by and by[stem]["type"] in ("text", "textarea"):
                pairs.append((k, stem, n))
                # the pair must be ADJACENT, or the form renders them in different places and nobody
                # sees that one is the link for the other (same rule as fieldset contiguity)
                fl = [x["name"] for x in m["fields"]]
                assert abs(fl.index(stem) - fl.index(n)) == 1, \
                    f"{k}: {stem!r} and its reference {n!r} are not adjacent"
                assert by[stem].get("fieldset") == f.get("fieldset"), \
                    f"{k}: {stem!r} and {n!r} are in different fieldsets"
assert len(pairs) >= 50, f"only {len(pairs)} additive text+reference pairs; the sweep created 54"

# every reference points at a module that exists (config test covers it; asserted here for the pairs)
for k, m in mods.items():
    for f in m.get("fields", []):
        if f["type"] == "reference":
            assert f.get("module") in keys, f"{k}.{f['name']}: bad reference target {f.get('module')!r}"

refs = sum(1 for m in mods.values() for f in m.get("fields", []) if f["type"] == "reference")
islands = [k for k, m in mods.items()
           if not any(f["type"] == "reference" for f in m.get("fields", []))]
assert refs >= 176, (
    f"only {refs} reference fields; the sweep took it from 98 to 152, TRANSMIT-REFS to 173 and "
    "PERMIT-AUTHORITY to 178"
)
assert len(islands) <= 44, (
    f"{len(islands)} modules have no reference at all (was 69, then 49). A record that points at "
    "nothing cannot take part in a chain, which is most of what separates a register from a "
    "spreadsheet. TRANSMIT-REFS took three more off the list — `transmittal` itself, which could not "
    "name the company it was addressed to, and `document` and `drawing_set`, which had no reference "
    "of any kind and so could not be put in a package. PERMIT-AUTHORITY took two more — `permit` "
    "and `entitlement`, the two ends of the approval chain, neither of which could point at the "
    "authority it was applying to."
)


# ---- 5. TRANSMIT-REFS: a package must be able to CARRY what it is sent to carry ------------------
#
# R22-ENTITLEMENT's remaining item is the outbound submittal package, and its stated blocker was that
# `transmittal.items` is a textarea. **That was the wrong blocker.** `submittal.transmittal` was
# already a reference, so submittals resolved into a package the whole time — the entry's own ④ note
# had verified exactly that against `…/related`, and its Remaining paragraph contradicted it.
#
# What was actually missing is asserted here. A transmittal carries drawings, sets and documents at
# least as often as submittals, and NONE of those three could name one: `document` and `drawing_set`
# had no reference field of any kind. A package whose contents cannot point at it is prose.
#
# The set is NAMED rather than derived, because "what a transmittal carries" is a judgement about the
# business, not a fact about the schema — and a derived rule would either miss registers or drag in
# every module that happens to sit in the Drawings section. Naming it means adding a register here is
# a deliberate act with a reason, which is the same discipline `NOT_OFFERED` uses in test_routines.py.
TRANSMITTED = {
    "submittal": "the original case; its reference predates this rule",
    "drawing": "a transmittal issues sheets",
    "drawing_set": "and more often issues the whole set, which is the usual unit of issue",
    "document": "reports, specs and letters go out under a transmittal too",
}
for _k, _why in TRANSMITTED.items():
    _m = mods[_k]
    assert any(f["type"] == "reference" and f.get("module") == "transmittal"
               for f in _m.get("fields", [])), \
        (f"{_k} cannot name the transmittal that issued it ({_why}), so it can never appear in a "
         "package: a transmittal's contents ARE the records pointing at it, via REVERSE_REFS.")

# The recipient half. A transmittal addressed to a typed company name cannot be resolved, reused or
# reported on, and `company` is a register. Kept as the additive pair the sweep established rather
# than a conversion — rule 4 above asserts the pair is adjacent and shares a fieldset.
assert any(f["type"] == "reference" and f.get("module") == "company"
           for f in mods["transmittal"].get("fields", [])), \
    "a transmittal cannot name the company it is addressed to"


# ---- 6. PERMIT-AUTHORITY: the permitting chain must be able to NAME the body it is applying to ----
#
# #448 closed half of one sentence. The roadmap said a transmittal's recipient "cannot be the agency
# an `entitlement` names, since that field is free text too" — TRANSMIT-REFS gave the transmittal its
# `company` reference and left the agency half exactly as it found it.
#
# The whole permitting chain named its counterparty in prose: `entitlement.agency`,
# `permit.authority`, `review_cycle.agency` and `inspection.agency` were four text fields for one
# concept, and `company` already models it — `company.type` has offered an 'Authority' option all
# along, so the register was waiting and nothing pointed at it. The cost is not cosmetic: an authority
# typed four ways is four authorities, so "how long does this jurisdiction take" and "what else is
# open with them" are unanswerable, and `entitlement` and `permit` were islands — a permit could not
# be tied to anything at all.
#
# NAMED, not derived, for the reason TRANSMITTED gives above: which registers apply to an authority is
# a judgement about permitting, and a derived rule keyed on the field NAME would sweep in
# `project_charter.budget_authority`, which is an internal spend limit and not an agency at all.
AUTHORITY_NAMED = {
    "entitlement": ("agency_company", "the jurisdiction an application is made to"),
    "permit": ("authority_company", "the AHJ that issues it, and the one that can revoke it"),
    "review_cycle": ("agency_company", "a round is with an agency; that is what makes it a round"),
    "inspection": ("agency_company", "the authority whose inspector signs the result"),
}
for _k, (_ref, _why) in AUTHORITY_NAMED.items():
    _by = {f["name"]: f for f in mods[_k]["fields"]}
    _f = _by.get(_ref)
    assert _f is not None and _f["type"] == "reference" and _f.get("module") == "company", (
        f"{_k} cannot name its authority as a record ({_why}). It is {_ref!r} -> company; without it "
        "the same jurisdiction typed two ways is two jurisdictions, and nothing about an agency can "
        "be totalled, filtered or reported on."
    )

# The person, not the body. `inspection` already paired inspector/inspector_contact; `review_cycle`
# named the plan reviewer in text beside it, which is the same fact about the same kind of person on
# the other side of the same counter.
for _k, _ref in (("inspection", "inspector_contact"), ("review_cycle", "reviewer_contact")):
    assert any(f["name"] == _ref and f["type"] == "reference" and f.get("module") == "contact"
               for f in mods[_k]["fields"]), f"{_k}.{_ref} must link the reviewing person to `contact`"


# ---- 7. a workflow gate must not demand the half of a pair the user was told not to fill ---------
#
# Found by review on PR #449, and the review found ONE of the two. Rule 4's additive pattern adds a
# reference BESIDE its text field so the text can be retired later — but `entitlement.submit`
# declared `requires: ["agency"]`, so the moment `agency_company` arrived carrying help text telling
# the user to pick a company INSTEAD of typing the name, a linked-only entitlement could never be
# submitted. **The pull request that added the control created the trap.**
#
# Sweeping all 139 modules found a second, already on main and nothing to do with that PR:
# `compliance_evidence.sign_off` requires `responsible`, which has had `responsible_contact` beside
# it. So this is the additive pattern's general collision with the workflow gate, not a bad manifest
# — which is why the rule below is DERIVED from the pairs rather than naming the two known cases.
# A pair added next year is covered the day it is added; a named list would not be.
#
# The fix is alternation: `requires: ["agency|agency_company"]`, satisfied when EITHER is filled
# (`modules.py`, and `requiresGate.ts` on the UI side so the button agrees with the server).
gated = []
for k, m in mods.items():
    by = {f["name"]: f for f in m.get("fields", [])}
    # NOT `pairs` — rule 4 above builds a module-level list of that name and the summary line prints
    # its length. Shadowing it here reported "0 additive pairs" while 65 were sitting in the file,
    # which is the summary lying about the check directly above it.
    pair_map = {}
    for n, f in by.items():
        if f["type"] != "reference":
            continue
        for suf in ("_company", "_loc", "_spec", "_system", "_contact", "_package", "_ref", "_id"):
            stem = n[: -len(suf)] if n.endswith(suf) else None
            if stem and stem in by and by[stem]["type"] in ("text", "textarea"):
                pair_map[stem] = n
    for t in (m.get("workflow") or {}).get("transitions", []):
        for entry in t.get("requires") or []:
            alts = entry.split("|")
            for one in alts:
                assert one in by, f"{k}: transition {t.get('action')!r} requires unknown field {one!r}"
            for one in alts:
                if one in pair_map and pair_map[one] not in alts:
                    gated.append(f"{k}.{t.get('action')}: requires {entry!r} but {one!r} has the "
                                 f"reference {pair_map[one]!r} beside it")
assert not gated, (
    "a transition gate names the TEXT half of an additive pair without accepting its reference: "
    + "; ".join(gated) + ". The additive pattern tells the user to fill the reference instead, so a "
    "gate demanding the text makes the new control a trap — write it as `text|reference`, which is "
    "met by EITHER half."
)
alternated = sorted(f"{k}.{t.get('action')}"
                    for k, m in mods.items()
                    for t in (m.get("workflow") or {}).get("transitions", [])
                    for e in (t.get("requires") or []) if "|" in e)
assert len(alternated) >= 2, f"expected the two known alternation gates, found {alternated}"

print(f"MOD-SWEEP OK - {len(mods)} modules, {refs} reference fields ({len(islands)} still islands), "
      f"{len(united)} fields carry a declared unit, {len(pairs)} additive text+reference pairs are "
      f"adjacent and share a fieldset, {len(with_ref)} registers surface a reference as a column, and "
      "no percentage-named field is typed 'number'. " + f"{len(alternated)} transition gates accept "
      "either half of an additive pair. Each bound is a FLOOR recording work already done, "
      "so the file needs no edit when a module is added and fails if the work is undone. The three "
      "calendar-year fields are asserted to carry NO unit: a suffix rule cannot tell 2027 from "
      "5 years, and it labelled all three 'yr' before a human read the list.")
