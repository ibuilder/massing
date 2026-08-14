"""The weekly upstream-drift check answers three things, not two.

`vendor_drift` is the half of R43-PLAN-DRIFT that needs the network, so it is scheduled rather than
run per-commit and it **notifies instead of failing a build**. Both of those are deliberate and both
are easy to break by accident, so they are asserted here.

**The assertion that matters most is UNKNOWN.** If the upstream query fails — offline, rate-limited,
a renamed branch, a token without access — the honest answer is *"could not tell"*. Reporting CLEAN
would mean a check that has quietly stopped working keeps producing good news every week, which is
precisely the failure mode this repo keeps re-learning under a different name each time. A
two-valued verdict cannot express it, so the verdict is three-valued and this file proves the third
value is reachable.

Offline by construction: `upstream_head` is monkeypatched. A test that needed the network to check
the offline branch would be the same mistake one level up.
"""
from __future__ import annotations

import pathlib
import sys
import tempfile

import vendor_drift
from vendor_drift import check_drift, read_digest, read_pin

FAILED: list[str] = []


def check(name: str, ok: bool, why: str = "", note: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ((f"   {note}" if note else "") if ok
                                                   else (f"   {why}" if why else "")))
    if not ok:
        FAILED.append(name)


PIN = "b703dca49b6a8f88b26fe114d2716989de4dbf5c"
DOC = f"""# Vendored: massingplan core
| | |
|---|---|
| Commit | `{PIN}` |
| Content digest | `d7d2ac5e71b0ac7e` |
"""


def doc_at(text: str) -> pathlib.Path:
    p = pathlib.Path(tempfile.mkdtemp()) / "VENDOR.md"
    p.write_text(text, encoding="utf-8")
    return p


# --- the parse, which two callers share -----------------------------------------------------------
check("read_pin finds the 40-hex commit", read_pin(DOC) == PIN, note=PIN[:12] + "…")
check("read_digest finds the content digest", read_digest(DOC) == "d7d2ac5e71b0ac7e")
# The twin: it must be able to say "absent" rather than returning something plausible.
check("...and both return None when the row is missing",
      read_pin("# no table here") is None and read_digest("# no table here") is None,
      "a parse that always answers cannot report a malformed VENDOR.md")
# A SHORT pin must not satisfy it. VENDOR.md's own history includes a short `155640a7`, and a short
# sha cannot identify a commit unambiguously.
check("...and a short pin is refused, not truncated into an answer",
      read_pin("| Commit | `155640a7` |") is None)

_orig = vendor_drift.upstream_head
try:
    # --- clean: upstream head equals the pin --------------------------------------------------------
    vendor_drift.upstream_head = lambda *a, **k: (PIN, "ok")            # type: ignore[assignment]
    d = check_drift(doc_at(DOC))
    check("upstream at the pin reports CLEAN", d.verdict == "clean", f"got {d.verdict}")

    # --- drifted: upstream moved --------------------------------------------------------------------
    moved = "a" * 40
    vendor_drift.upstream_head = lambda *a, **k: (moved, "ok")          # type: ignore[assignment]
    d = check_drift(doc_at(DOC))
    check("upstream ahead of the pin reports DRIFTED", d.verdict == "drifted", f"got {d.verdict}")
    check("...and carries both shas so the issue can name them",
          d.pinned == PIN and d.upstream == moved, f"pinned={d.pinned} upstream={d.upstream}")

    # --- unknown: the query failed. THE POINT OF THIS FILE. -----------------------------------------
    vendor_drift.upstream_head = lambda *a, **k: (None, "gh exit 1: could not resolve host")
    d = check_drift(doc_at(DOC))
    check("a FAILED upstream query reports UNKNOWN, never CLEAN", d.verdict == "unknown",
          f"got {d.verdict!r} — a check that cannot reach upstream knows nothing about upstream, "
          f"and reporting clean would let a silently-broken job produce good news every week")
    check("...and says why, so the issue is actionable rather than mysterious",
          "could not resolve host" in d.detail, f"detail={d.detail!r}")

    # A malformed VENDOR.md is also UNKNOWN — not clean, and not a crash.
    vendor_drift.upstream_head = lambda *a, **k: (PIN, "ok")            # type: ignore[assignment]
    d = check_drift(doc_at("# no pin row"))
    check("a VENDOR.md with no pin reports UNKNOWN", d.verdict == "unknown", f"got {d.verdict}")
    d = check_drift(pathlib.Path(tempfile.mkdtemp()) / "absent.md")
    check("a missing VENDOR.md reports UNKNOWN", d.verdict == "unknown", f"got {d.verdict}")

    # --- all three verdicts are reachable -----------------------------------------------------------
    # Vacuity guard on the whole set: if the function could only ever answer one thing, every
    # assertion above would still pass on the case that matched it.
    seen = set()
    for head in ((PIN, "ok"), ("b" * 40, "ok"), (None, "boom")):
        vendor_drift.upstream_head = lambda *a, _h=head, **k: _h        # type: ignore[assignment]
        seen.add(check_drift(doc_at(DOC)).verdict)
    check("all three verdicts are reachable", seen == {"clean", "drifted", "unknown"},
          f"only saw {sorted(seen)}")
finally:
    vendor_drift.upstream_head = _orig                                   # type: ignore[assignment]

# --- the exit code is not the signal ---------------------------------------------------------------
# Asserted because "make it fail the build" is the obvious-looking hardening, and it is wrong here:
# upstream moving is not a defect in OUR tree, and a red nobody can fix by editing our code teaches
# people to ignore red. The local-fork gate blocks; this one notifies.
vendor_drift.upstream_head = lambda *a, **k: ("c" * 40, "ok")            # type: ignore[assignment]
try:
    check("main() exits 0 even when drifted — it notifies, it does not block",
          vendor_drift.main([]) == 0)
finally:
    vendor_drift.upstream_head = _orig                                   # type: ignore[assignment]

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_vendor_drift OK  (clean / drifted / unknown all reachable; notifies rather than blocks)")
