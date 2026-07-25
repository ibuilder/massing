"""R26-INSPECTOR — the six-state lifecycle strip: designed · checked · priced · scheduled · installed · verified.

The redesign's sharpest observation about this product: every one of those six facts is already held
against the **same GlobalId** — the model, the QA lenses, the 5D cost binding, the schedule, the field
record, the LOD-500 stamp — and they live in six different panels in different workspaces. The one
genuinely unusual thing here, that all of it shares one key, is invisible in the interface.

Three rules decide whether the strip is worth having, and all three are tested below.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_lifecycle_strip.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_lifecycle_strip.db"
os.environ["STORAGE_DIR"] = "./test_storage_lifecycle_strip"
if os.path.exists("./test_lifecycle_strip.db"):
    os.remove("./test_lifecycle_strip.db")

from aec_api import lifecycle_strip as ls  # noqa: E402

EL = {"guid": "1kP9x7Qa", "ifc_class": "IfcSlab", "name": "L04 slab"}

# ---- the strip reads left to right, always, in one order ------------------------------------------
assert ls.STATE_KEYS == ["designed", "checked", "priced", "scheduled", "installed", "verified"]
for s in ls.STATES:
    assert len(s["means"]) > 25 and len(s["advance"]) > 10, s

# ---- RULE 1: unknown is NOT "no" -------------------------------------------------------------------
# An element nobody priced and an element priced at zero are different facts. Colouring the first as a
# failure is how a strip becomes something people learn to ignore.
bare = ls.strip(EL)
assert bare["states"][0]["status"] == "done", bare["states"][0]        # it IS in the model
assert [s["status"] for s in bare["states"][1:]] == ["unknown"] * 5, bare
assert bare["unknown_count"] == 5
assert bare["reached"] == "designed"

# consulted-and-negative is a DIFFERENT answer from not-consulted
told_no = ls.strip(EL, checked=False, priced={}, scheduled={}, installed={}, verified={})
assert [s["status"] for s in told_no["states"][1:]] == ["none"] * 5, told_no
assert told_no["unknown_count"] == 0
assert told_no["states"][2]["detail"] == "no cost rule matched"

# ---- RULE 2: `reached` is the furthest CONTIGUOUS state -------------------------------------------
# A later state must never flatter an incomplete earlier one — "verified" with nothing checked is not
# progress, it is a contradiction.
full = ls.strip(EL, checked=True,
                priced={"code": "03 30 00", "amount": 9420.0},
                scheduled={"activity": "A-1042"},
                installed={"installed": True, "date": "2026-06-11"},
                verified={"verified": True, "deviation_m": 0.008})
assert full["reached"] == "verified" and full["done_count"] == 6, full
assert full["next"] is None, "a complete element has no next step"
assert "03 30 00" in full["states"][2]["detail"]
assert "0.008" in full["states"][5]["detail"], "a verification states its ACCURACY, not just a tick"

gap = ls.strip(EL, checked=True, priced={}, scheduled={"activity": "A-9"},
               installed={"installed": True}, verified={"verified": True, "deviation_m": 0.01})
assert gap["reached"] == "checked", "priced is missing, so nothing past it may be claimed as reached"
assert gap["done_count"] == 5, "the later states are still individually true"

# ---- RULE 3: an out-of-order strip REPORTS the inconsistency rather than smoothing it -------------
# "verified but never installed" is a real data defect; hiding it loses the only signal that says so.
assert gap["inconsistencies"], gap
assert any("Priced" in m for m in gap["inconsistencies"]), gap["inconsistencies"]
assert not full["inconsistencies"], full["inconsistencies"]
assert not bare["inconsistencies"], "unknown is not a contradiction — only done-after-none is"

# ---- every incomplete state names what would advance it -------------------------------------------
# A strip showing six greys and no next step is a diagnosis with no prescription.
for s in bare["states"]:
    if s["status"] != "done":
        assert s["advance"], s
    else:
        assert s["advance"] is None, "telling someone how to finish what they finished is noise"
assert bare["next"]["key"] == "checked", bare["next"]
assert "Model Health" in bare["next"]["advance"]

# ---- degenerate inputs ------------------------------------------------------------------------------
empty = ls.strip(None)
assert empty["states"][0]["status"] == "none" and empty["reached"] is None
assert empty["next"]["key"] == "designed"
assert ls.strip({"guid": "x"})["states"][0]["status"] == "none", "no class = not in the model"
assert ls.strip(EL)["guid"] == "1kP9x7Qa"
# a priced amount of ZERO is still priced — free is a price, and conflating it with unpriced is the
# same error as treating unknown as no
zero = ls.strip(EL, priced={"code": "01", "amount": 0})
assert zero["states"][2]["status"] == "done", zero["states"][2]

print("R26-INSPECTOR OK - the six-state lifecycle strip (designed, checked, priced, scheduled, "
      "installed, verified) composes facts the platform ALREADY holds against the same GlobalId - the "
      "model, the QA lenses, the 5D cost binding, the schedule, the field record and the LOD-500 stamp "
      "- which until now lived in six panels across different workspaces, leaving the one genuinely "
      "unusual thing about this product invisible. Three rules make it trustworthy. UNKNOWN IS NOT NO: "
      "an element nobody priced and one priced at zero are different facts, and a strip that colours "
      "the unexamined as failed is one people learn to ignore - so a state not consulted reads "
      "unknown, and an amount of zero still counts as priced because free is a price. REACHED IS "
      "CONTIGUOUS: a later state can never flatter an incomplete earlier one, so an element verified "
      "but never priced reports as reaching only 'checked'. And an out-of-order strip REPORTS the "
      "inconsistency rather than smoothing it, because 'verified but not installed' is a real data "
      "defect and hiding it destroys the only signal that says so. Every incomplete state names what "
      "would advance it; every complete one stays quiet.")
