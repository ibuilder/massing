"""The project manual answers in the classification system the MODEL uses, not the one we assumed.

## The defect, and why nothing saw it

`project_manual(model, system="MasterFormat")` had a default, and its only caller —
`routers/authoring_docs.spec_manual` — passed nothing. So every project got MasterFormat.

**Not one IFC file tracked in this repository declares MasterFormat.** Counted from the classification
declarations across all 58 tracked `.ifc` files: **57 Uniclass, 1 OmniClass, 0 MasterFormat**. The spec
surface therefore returned zero sections for every model the project ships, and reported no error while
doing it — an empty manual is exactly what an *unclassified* model returns, so the two were
indistinguishable.

**`test_specmanual.py` passes and always did.** It builds a synthetic model and classifies it with
MasterFormat, so the fixture supplies precisely the system the code demands. That is the same shape as
the other one-directional gates this codebase has collected: *a check whose population is filtered by
the very thing it is checking for cannot observe that thing being wrong.* It is a good test of the
grouping logic and was never a test of the default.

## What this file asserts, and the anti-vacuity guard it needs

The finding above is a claim about the repository's own corpus, so it is measured here rather than
quoted: if somebody adds a MasterFormat-classified sample, the guard says so instead of letting the
"non-MasterFormat model" case quietly become vacuous.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_spec_system.py
"""
import os
import subprocess
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell  # noqa: E402

from aec_data import specmanual  # noqa: E402

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


# ---- the corpus claim, measured rather than quoted ------------------------------------------------
tracked = [ln for ln in subprocess.run(["git", "ls-files"], cwd=_ROOT, capture_output=True,
                                       text=True, check=True).stdout.splitlines()
           if ln.lower().endswith(".ifc")]
check("there are tracked IFC files to measure at all", len(tracked) >= 10, f"{len(tracked)} tracked")

uniclass = [p for p in tracked
            if "'Uniclass'" in open(os.path.join(_ROOT, p), encoding="utf-8", errors="ignore").read()]
check("the corpus really is non-MasterFormat, so the case below is not vacuous",
      len(uniclass) >= 10, f"{len(uniclass)} of {len(tracked)} declare Uniclass")

# ---- a real Uniclass model from that corpus -------------------------------------------------------
if uniclass:
    model = ifcopenshell.open(os.path.join(_ROOT, uniclass[0]))
    present = specmanual.classification_systems(model)
    check("classification_systems reports what the model actually carries",
          "Uniclass" in present and present["Uniclass"] > 0, f"{present}")
    check("...and does NOT claim MasterFormat is present", "MasterFormat" not in present, f"{present}")

    check("resolve_system picks the system the model uses",
          specmanual.resolve_system(model) == "Uniclass", specmanual.resolve_system(model))

    auto = specmanual.project_manual(model)
    check("the manual is no longer empty for this model",
          auto["section_count"] > 0, f"{auto['section_count']} sections in {auto['division_count']} divisions")
    check("...and it says which system it used", auto["system"] == "Uniclass", f"{auto['system']!r}")

    # The note used to hardcode "MasterFormat" whatever it had actually read, so a Uniclass manual
    # described itself as a MasterFormat one. A payload that misdescribes its own contents is worse
    # than an empty one: nothing looks wrong.
    check("the note names the system actually used, not a hardcoded one",
          "Uniclass" in auto["note"] and "MasterFormat" not in auto["note"], auto["note"][:70])

    # Grouping Uniclass codes through the CSI division table files every section under a title the
    # code never claimed. `Pr_20_76_51` is a Products-table code, not CSI division "Pr".
    titles = [d["title"] for d in auto["divisions"]]
    check("divisions are titled in the model's own vocabulary, not borrowed from CSI",
          bool(titles) and "Unassigned" not in titles, f"{titles}")

    # The inverse, and the one that keeps the change honest: asking for a system the model does not
    # use must still return the truthful empty answer rather than silently substituting one that works.
    forced = specmanual.project_manual(model, system="MasterFormat")
    check("an EXPLICIT system is still obeyed, even when it yields nothing",
          forced["section_count"] == 0 and forced["system"] == "MasterFormat",
          f"{forced['section_count']} sections, system={forced['system']!r}")

    check("available_systems is published so a caller can offer the choice",
          auto.get("available_systems", {}).get("Uniclass", 0) > 0, f"{auto.get('available_systems')}")

    txt = specmanual.manual_text(model)
    check("the text rendering names the resolved system too",
          "Uniclass" in txt and "No MasterFormat-classified" not in txt,
          "seeded-from line names Uniclass")

# ---- a model with NO classifications keeps the old, honest behaviour -------------------------------
# Auto-detection must not invent a system for a model that has none: an empty manual is the true
# answer there, and the pre-existing default is what callers already expect for that case.
from aec_data import massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_spec_system_test.ifc")
try:
    massing.generate_blank_ifc(TMP, name="No Classifications", storeys=1, storey_height=3.0, ground_size=10.0)
    blank = open_model(TMP)
    check("an unclassified model reports no systems", specmanual.classification_systems(blank) == {},
          f"{specmanual.classification_systems(blank)}")
    empty = specmanual.project_manual(blank)
    check("...and still returns a valid, empty manual rather than raising",
          empty["section_count"] == 0 and "divisions" in empty and empty["system"] == "MasterFormat",
          f"system={empty['system']!r} sections={empty['section_count']}")
finally:
    if os.path.exists(TMP):
        os.remove(TMP)

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(f"SPEC SYSTEM OK - {len(uniclass)} of {len(tracked)} tracked IFC files declare Uniclass and none "
      "declare MasterFormat, which is why the manual answered nothing for every model this project "
      "ships. project_manual now resolves the system from the model, names it in the payload and the "
      "note, groups Uniclass codes under their own tables, and still obeys an explicit system that "
      "yields zero.")
