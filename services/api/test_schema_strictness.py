"""Unknown fields on a request model must be REFUSED, not silently dropped.

Pydantic's default for an unrecognised key is `extra="ignore"`: it drops the value and returns 200.
For a money contract that is the worst available behaviour, and it was demonstrated rather than
theorised before this file existed:

    Waterfall(pref_rat=0.10, clawbck=True)  ->  accepted, HTTP 200
                                                pref_rate = 0.08   (the default)
                                                clawback  = False  (the default)

The caller asked for a 10% preferred return with clawback ON; the engine priced an 8% pref with
clawback OFF and said nothing. A typo in a client, a field renamed on one side of a deploy, or a
hand-written request is enough to trigger it. **A rejected request is visible and gets fixed in
minutes; a silently-defaulted one is priced, exported into an investment memo, and never questioned.**

The same defect class was found independently in `Assumptions`, where a whole `sources` block vanished
before storage and the endpoint returned 200 — provenance that the caller believed was recorded.

## Why this is a RATCHET and not a blanket rule

A repo-wide "every model must declare a policy" assertion would fail on 53 models today, and a gate
that cannot go green is a gate people delete. So this pins two things instead:

1. the **money** models are strict, by name, and are checked by behaviour rather than by config; and
2. the number of models with no declared policy **may not grow**.

Tightening is one deliberate edit to `MAX_UNDECLARED`, and it only ever moves down.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil
import warnings

warnings.filterwarnings("ignore")

from pydantic import BaseModel, ValidationError  # noqa: E402

import aec_api  # noqa: E402
from aec_api.routers import proforma_schemas as PS  # noqa: E402

#: Every model in the proforma input contract. These decide money, so they are strict by name — a new
#: sibling added without strictness fails `test_every_money_model_is_strict` below.
MONEY_MODELS = ["Timing", "CostLine", "Debt", "Equity", "Ops", "Exit", "Tier", "Waterfall", "Tax",
                "Assumptions"]

#: Models with no declared `extra` policy, measured 2026-07-31. **This number may only go down.**
#: It is deliberately the live count rather than a comfortable ceiling: a threshold set above the
#: truth measures the threshold, not the code.
MAX_UNDECLARED = 43


def _all_models() -> dict[str, type[BaseModel]]:
    out: dict[str, type[BaseModel]] = {}
    for m in pkgutil.walk_packages(aec_api.__path__, "aec_api."):
        try:
            mod = importlib.import_module(m.name)
        except Exception:  # noqa: BLE001 — an unimportable module is not this gate's business
            continue
        for obj in vars(mod).values():
            if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj is not BaseModel:
                out[f"{obj.__module__}.{obj.__name__}"] = obj
    return out


def test_the_scan_finds_models_at_all():
    # Without this the assertions below pass vacuously if the walk ever stops importing anything —
    # the exact can't-fail shape this repo keeps re-learning.
    assert len(_all_models()) >= 40, len(_all_models())


def test_every_money_model_is_strict():
    """Checked by BEHAVIOUR, not by reading `model_config`.

    Asserting the config would pass if a future refactor kept `extra="forbid"` while some wrapper
    re-validated leniently. Feeding each model an unknown key and requiring it to raise is the
    property that actually matters.
    """
    for name in MONEY_MODELS:
        model = getattr(PS, name)
        assert model.model_config.get("extra") == "forbid", f"{name} declares no forbid policy"
        try:
            model.model_validate({"totally_not_a_field_xyz": 1})
        except ValidationError as e:
            assert any("totally_not_a_field_xyz" in str(err.get("loc", "")) for err in e.errors()), \
                f"{name} rejected the payload but not for the unknown key"
        else:
            raise AssertionError(f"{name} ACCEPTED an unknown field — it will silently default")


def test_a_typo_in_a_money_field_is_refused_not_defaulted():
    """The concrete case, pinned so the regression is legible rather than abstract."""
    good = PS.Waterfall.model_validate(
        {"tiers": [{"hurdle": 0.08, "lp": 0.9, "gp": 0.1}], "pref_rate": 0.10, "clawback": True})
    assert good.pref_rate == 0.10 and good.clawback is True

    try:
        PS.Waterfall.model_validate(
            {"tiers": [{"hurdle": 0.08, "lp": 0.9, "gp": 0.1}], "pref_rat": 0.10, "clawbck": True})
    except ValidationError as e:
        bad_keys = {str(err["loc"][0]) for err in e.errors()}
        assert {"pref_rat", "clawbck"} <= bad_keys, bad_keys
    else:
        raise AssertionError("a 10% pref with clawback ON was silently priced at 8% with clawback OFF")


def test_undeclared_policy_count_does_not_grow():
    """The ratchet. New request models should declare a policy; existing ones are grandfathered."""
    undeclared = [k for k, m in _all_models().items() if (m.model_config or {}).get("extra") is None]
    assert len(undeclared) <= MAX_UNDECLARED, (
        f"{len(undeclared)} models declare no `extra` policy, up from {MAX_UNDECLARED}. "
        f"A model with no policy SILENTLY DROPS unknown fields and returns 200. "
        f"Set `model_config = ConfigDict(extra='forbid')` on the new one, or lower the baseline. "
        f"New since baseline: {sorted(undeclared)[:6]}")


if __name__ == "__main__":
    import sys
    fails = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"  ok   {name}")
        except Exception as e:  # noqa: BLE001 — a harness reports, it does not re-raise
            fails += 1
            print(f"  FAIL {name}: {type(e).__name__}: {e}")
    n = len([k for k, m in _all_models().items() if (m.model_config or {}).get("extra") is None])
    print(f"SCHEMA STRICTNESS {'FAILED' if fails else 'OK'} - the 10 proforma money models refuse an "
          f"unknown field (a typo'd `pref_rat` used to be accepted and priced at the 8% default with "
          f"clawback off, HTTP 200); {n} models repo-wide still declare no policy, ratcheted at "
          f"{MAX_UNDECLARED}.")
    sys.exit(1 if fails else 0)
