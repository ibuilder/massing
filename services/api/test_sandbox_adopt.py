"""SEC-PLUGIN-SANDBOX step two — the `bytes -> bytes` contract has an adopter, and the edit survives.

WHY THIS FILE EXISTS. Step one added `sandbox.execute_ifc_bytes` and **nothing called it**. A contract
with no adopter is not a migration, it is a second implementation sitting beside the first: the
isolation work would still have had to change `edit.py` later, which is the exact blocker step one was
written to remove. `test_sandbox_bytes.py` proves the function works; only this file proves the
product uses it.

THE FAILURE THIS IS SHAPED AGAINST, WHICH IS SILENT. Every other entry in `edit.RECIPES` mutates the
model in place, and both drivers rely on that: they call the recipe, then `model.write(out_path)` on
the object they already held. `execute_ifc_bytes` cannot work that way — it serialises, runs, and
returns a NEW model. Wire it in without teaching the driver to rebind and:

  * the recipe returns a healthy `changed` payload,
  * `apply_recipe` reports success,
  * the file on disk is the **pre-edit model**,
  * nothing raises, nothing logs, and the suite is green.

The user's edit is gone and every signal says it worked. So the assertions below deliberately do NOT
trust the return value. They re-open the written file and look for the change there. A test that
asserted `result["changed"]` would pass against the broken wiring — which is the whole point of
"ask what still passes if the function does nothing".

The batch case is worse and is asserted separately: in `apply_recipes` a missed rebind also strands
every LATER step on an orphaned model, so a three-step batch silently keeps only the steps that ran
before the sandbox one.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_sandbox_adopt.py
"""
import os
import sys
import tempfile

os.environ["AEC_ALLOW_IFC_CODE"] = "1"      # the recipe is off by default; this suite is about wiring

import ifcopenshell  # noqa: E402

from aec_data import edit  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


TMP = tempfile.mkdtemp(prefix="sandbox_adopt_")


def fresh(name: str = "in.ifc") -> str:
    """A minimal but real IFC on disk. `edit.open_model` is the same reader the drivers use."""
    m = ifcopenshell.file(schema="IFC4")
    m.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name="Adopt")
    p = os.path.join(TMP, name)
    m.write(p)
    return p


# The snippet renames the project. Chosen because it is observable in the SERIALISED file by reading
# an attribute, needs no geometry, and cannot be confused with anything the fixture already contains.
RENAME = "model.by_type('IfcProject')[0].Name = 'TOUCHED'"


def project_name(path: str) -> str | None:
    return (ifcopenshell.open(path).by_type("IfcProject") or [None])[0].Name


# --- 1. the wiring is real -----------------------------------------------------------------------
check("the recipe is declared model-REPLACING",
      "execute_ifc_code" in edit.REPLACING_RECIPES,
      "the drivers will not rebind, so the edit will be written nowhere")

# Behavioural, not source-reading: the helper must hand back a DIFFERENT object from the one passed
# in. That is the observable signature of the bytes contract — the live-model call mutates and returns
# a count, so if this ever starts returning the same object the migration has been quietly reverted.
_probe = ifcopenshell.open(fresh("probe.ifc"))
_new, _res = edit._sandbox_replace(_probe, RENAME)
check("the helper returns a NEW model, which is what the bytes contract means",
      _new is not _probe, "same object back — this is the in-place call wearing a new name")
check("...and the ORIGINAL is not mutated, because the snippet ran on a serialised copy",
      (_probe.by_type("IfcProject") or [None])[0].Name == "Adopt",
      "the caller's model changed under it — the copy semantics are not holding")
check("...while the returned model carries the edit",
      (_new.by_type("IfcProject") or [None])[0].Name == "TOUCHED", f"got {_res!r}")


# --- 2. single apply: the change is in the FILE, not just the return value -----------------------
out = os.path.join(TMP, "out_single.ifc")
res = edit.apply_recipe(fresh(), "execute_ifc_code", {"code": RENAME}, out)
check("apply_recipe writes the sandbox's edit to the output file",
      project_name(out) == "TOUCHED",
      f"file says {project_name(out)!r} — the driver saved the pre-edit model and reported "
      f"{res.get('changed')!r}")

# The source model must be untouched: `execute_ifc_bytes` works on a serialised copy, and a recipe
# that edited the input in place would defeat the whole point of the contract.
check("the INPUT file is left alone — the snippet ran against a copy",
      project_name(res_src := fresh("check_src.ifc")) == "Adopt", f"got {project_name(res_src)!r}")


# --- 3. batch apply: rebinding must survive to later steps AND to the file -----------------------
# `add_storey` after the sandbox step is the discriminator. If the driver failed to rebind, this
# storey lands on the orphaned model and the written file has neither the rename nor the storey.
out_b = os.path.join(TMP, "out_batch.ifc")
edit.apply_recipes(fresh("in_b.ifc"), [
    {"recipe": "execute_ifc_code", "params": {"code": RENAME}},
    {"recipe": "add_storey", "params": {"name": "L99", "elevation": 9.0}},
], out_b)
after = ifcopenshell.open(out_b)
check("a batch keeps the sandbox step's edit",
      (after.by_type("IfcProject") or [None])[0].Name == "TOUCHED",
      "the rename was written to an object the driver then discarded")
check("...and a step AFTER it lands on the same model the file is written from",
      any(s.Name == "L99" for s in after.by_type("IfcBuildingStorey")),
      "the later step mutated an orphan — this is the failure a missed rebind causes in a batch")


# --- 4. the gate still holds through the new path ------------------------------------------------
os.environ["AEC_ALLOW_IFC_CODE"] = "0"
try:
    edit.apply_recipe(fresh("in_off.ifc"), "execute_ifc_code", {"code": RENAME},
                      os.path.join(TMP, "out_off.ifc"))
    check("the recipe still refuses when AEC_ALLOW_IFC_CODE is off", False,
          "adoption widened the reach of a gated escape hatch")
except PermissionError:
    check("the recipe still refuses when AEC_ALLOW_IFC_CODE is off", True)
except Exception as e:  # noqa: BLE001
    check("the recipe still refuses when AEC_ALLOW_IFC_CODE is off", False,
          f"refused with {type(e).__name__}, not PermissionError: {e}")
finally:
    os.environ["AEC_ALLOW_IFC_CODE"] = "1"

print(f"\ntest_sandbox_adopt {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
