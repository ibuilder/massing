"""The ENERGY STAR bridge refuses in both directions, and never invents a score.

## Why this file exists

`energy_star_bridge.sync_property` is a refusal stub: it raises, names exactly what a deployment must
wire, and never returns a fabricated 1–100 score. Its two siblings — `parcels_bridge.fetch_parcels`
and `payments_bridge.send_payment` — are the same design, and each already has a test exercising the
refusal (`test_parcels.py`, `test_payapp.py`). This one had **none**, and the gap surfaced sideways:

R37-TESTED-UNWIRED measured which public functions are referenced only by the test tree, and
`sync_property` came back referenced by **nothing at all** — not even a test. It had been made
invisible by its own `NotImplementedError` string naming it, until `test_dead_code_population.py`
stopped counting prose as a reference; then it was carried as a *deliberate exemption*.

**An exemption is what you write when there is nothing to assert.** Here there is something to
assert — that the stub refuses, and says what to wire — so the exemption was the wrong instrument and
this file replaces it. That matters beyond tidiness: an exemption entry freezes a missing test as a
decision somebody made on purpose, and reads that way to everyone afterwards.

## What is actually load-bearing

Not "it raises". **That no path returns a score.** The module's whole contract is that a benchmarking
number comes from EPA's web services or does not exist, because a plausible invented score is worse
than a missing one — it would be read as EPA's, quoted in a report, and never questioned. Both the
disabled and the enabled-but-unwired paths are checked, since a deployment that sets the env vars is
precisely the one that would believe a number it got back.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_energy_star_bridge.py
"""
from __future__ import annotations

import os
import sys

for _v in ("ENERGY_STAR_PROVIDER", "ENERGY_STAR_API_KEY"):
    os.environ.pop(_v, None)

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import energy_star_bridge as esb  # noqa: E402

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


def sync_raises() -> tuple[type[BaseException] | None, str]:
    """Call `sync_property` and report what came back — an exception type, or the RETURN value.

    Returning rather than asserting inline so the "it returned something" case is reportable: a stub
    that quietly starts returning a dict is the failure this file is about, and `pytest.raises`-style
    inline assertion would only say "did not raise" without showing what it produced instead.
    """
    try:
        out = esb.sync_property("P-1")
    except Exception as e:                      # noqa: BLE001 — the type IS the assertion
        return type(e), str(e)
    return None, f"RETURNED {out!r}"


# ---- disabled: the default posture ----------------------------------------------------------------
check("no provider configured by default", esb.is_enabled() is False, str(esb.provider()))
st = esb.status()
check("...and status says so rather than staying silent",
      st["enabled"] is False and st["provider"] is None, str(st))
check("...naming what is available WITHOUT the integration, so 'off' is not read as 'broken'",
      "computed locally" in st["message"], st["message"][:60])

kind, msg = sync_raises()
check("sync refuses when unconfigured", kind is RuntimeError, f"{kind} — {msg[:60]}")
check("...and the refusal names the two env vars to set, not just 'not configured'",
      "ENERGY_STAR_PROVIDER" in msg and "ENERGY_STAR_API_KEY" in msg, msg[:90])
check("...and says the local EUI path still works, which is the part a reader needs",
      "Local EUI" in msg or "remain available" in msg, msg[-60:])

# ---- flagged ON but unwired: the dangerous case ----------------------------------------------------
# A deployment that has set the env vars is exactly the one that would BELIEVE a number it got back.
# The refusal has to survive being switched on, and it has to name the function to implement.
os.environ["ENERGY_STAR_PROVIDER"] = "portfolio_manager"
os.environ["ENERGY_STAR_API_KEY"] = "not-a-real-key"
try:
    check("flagging it on really does flip is_enabled — else the case below is vacuous",
          esb.is_enabled() is True)
    kind, msg = sync_raises()
    check("an ENABLED but unwired provider still refuses", kind is NotImplementedError,
          f"{kind} — {msg[:60]}")
    check("...naming the function a deployment must implement",
          "sync_property" in msg, msg[:90])
    check("...and naming the provider it was asked for, so the message is about THIS config",
          "portfolio_manager" in msg, msg[:90])
finally:
    for _v in ("ENERGY_STAR_PROVIDER", "ENERGY_STAR_API_KEY"):
        os.environ.pop(_v, None)

# ---- the property that matters: no path returns a score -------------------------------------------
# Asserted over BOTH postures rather than argued. A fabricated 1-100 score is worse than a missing
# one: it would be read as EPA's, quoted in a report, and never questioned.
returned: list[str] = []
for label, env in (("disabled", {}),
                   ("enabled-but-unwired", {"ENERGY_STAR_PROVIDER": "portfolio_manager",
                                            "ENERGY_STAR_API_KEY": "k"})):
    os.environ.update(env)
    try:
        kind, msg = sync_raises()
        if kind is None:
            returned.append(f"{label}: {msg}")
    finally:
        for _v in ("ENERGY_STAR_PROVIDER", "ENERGY_STAR_API_KEY"):
            os.environ.pop(_v, None)
check("NO posture returns a score — the contract is 'never fabricate', not 'usually refuse'",
      not returned, "; ".join(returned))

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("ENERGY STAR BRIDGE OK - refuses unconfigured (naming both env vars and the local EUI path "
      "that still works) and refuses when flagged on but unwired (naming the provider and the "
      "function to implement). Neither posture returns a score, which is the contract: an invented "
      "1-100 would be read as EPA's and never questioned.")
