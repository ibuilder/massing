"""R45-VENDOR-REACH — is the vendored engine *reached*, not just faithfully copied?

`test_massingplan_vendor.py` proves the copy is **faithful**: the digest matches, `core` imports the
standard library and nothing else, nobody forked a file. Every one of those checks passed on
2026-08-14 while the vendored tree grew by two modules and 880 lines that **nothing in the API could
call**. A re-sync can therefore double the engine and the whole gate stays green, because faithfulness
and usefulness are different claims and only one of them was being made.

That is the shape this repo keeps hitting: a check that measures the thing next to the thing you care
about. So this file makes the second claim explicitly — *how much of the vendored engine can the
application actually reach* — and ratchets it.

## Why the reachability is transitive, and why that is the whole point

The obvious implementation is a grep for `massingplan.core.<mod>` across `aec_api`. Run on the same
tree, it reports **12** unreached modules. Three of those — `cpm`, `progress_logic`, `units` — are
imported by `schedule.py`, which the API *does* import, so they run on every CPM calculation. A
grep-based gate would have told someone to "wire" three modules that were already load-bearing, and
`no_import_sites != not_load_bearing` is a lesson this project has already paid for once (it nearly
deleted networkx, which would have blanked every drawing silently).

Following the imports gives **9**, which is the honest number and the one below.

## The allowlist is a ratchet, and it can only shrink

`UNREACHED` is not permission — it is the recorded debt. The test fails if a module *leaves* the list
without the list being edited (good: someone wired it, update the list) **and** fails if a module is
added to the tree unreached and unlisted (good: a sync brought capability nobody can call). Both
directions are asserted, because a one-directional check here would let the number grow silently,
which is exactly the failure being fixed.
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
CORE = SRC / "massingplan" / "core"
APP = SRC / "aec_api"

#: Vendored core modules with no path from the API.
#:
#: Emptied on 2026-08-14 when R45 wired all 21 at the `d1e4bf16` sync — and **refilled the next day
#: by a re-sync**, which is the entire argument for this file. `a740241c` brought 2,873 lines of new
#: capability plus a rewritten MSPDI writer, and `test_massingplan_vendor` stayed green throughout
#: because the copy was faithful. Faithfulness and usefulness are different claims; only this one
#: notices that the engine grew and the application did not.
#:
#: Filed as **R46** in the roadmap. Unlike R45's list, none of these overlap anything we already
#: have — they are new methods, not duplicate ones:
#:
#:   * ~~`windows`~~  — SHIPPED v0.3.965 as `schedule_windows.py`.
#:   * ~~`modelled`~~ — SHIPPED v0.3.965 as `schedule_modelled.py`.
#:   * ~~`p6xml`~~   — SHIPPED v0.3.966. The PMXML branch of `schedule_import` used to return
#:                    ZERO activities with a warning; it now reads the format properly.
#:   * ~~`compression`~~ — SHIPPED v0.3.967 as `schedule_compression.py`.
#:   * ~~`earned`~~  — SHIPPED v0.3.966 as `schedule_earned.py`.
#:   * ~~`portfolio`~~ — SHIPPED v0.3.967 as `schedule_portfolio.py`.
#:   * ~~`weather`~~   — SHIPPED v0.3.967 as `schedule_weather.py`.
#:
#: **Empty again, and this time all 29.** R46 wired every module the a740241c sync brought.
#:
#: `xmlsafe` is NOT here: the same sync's parse-bomb and entity hardening reaches us transitively
#: through `mspdi` and `xer`, so the security fix was live the moment the files landed.
#:
#: **Remove names as they are wired; never add one without a roadmap entry saying why.**
UNREACHED: set[str] = set()

_FAILURES: list[str] = []


def check(name: str, ok: bool, why: str = "", note: str = "") -> None:
    tag = "PASS" if ok else "FAIL"
    print(f"{tag}  {name}   {note or why}")
    if not ok:
        _FAILURES.append(name)


def core_modules() -> set[str]:
    return {p.stem for p in CORE.glob("*.py") if p.stem != "__init__"}


def core_to_core_imports(mods: set[str]) -> dict[str, set[str]]:
    """Which core modules each core module imports. Relative and absolute spellings both count."""
    out: dict[str, set[str]] = {}
    for m in mods:
        text = (CORE / f"{m}.py").read_text(encoding="utf-8")
        deps = set()
        for other in mods:
            if other == m:
                continue
            if re.search(rf"from\s+\.{other}\b|from\s+massingplan\.core\.{other}\b"
                         rf"|from\s+\.\s+import\s+[^\n]*\b{other}\b", text):
                deps.add(other)
        out[m] = deps
    return out


def entry_points(mods: set[str]) -> set[str]:
    """Core modules the application layer names directly."""
    found: set[str] = set()
    for path in APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in mods:
            if re.search(rf"massingplan\.core\.{m}\b", text):
                found.add(m)
    return found


def reachable(mods: set[str]) -> set[str]:
    """Transitive closure from the application's entry points."""
    deps = core_to_core_imports(mods)
    seen: set[str] = set()
    stack = list(entry_points(mods))
    while stack:
        m = stack.pop()
        if m in seen:
            continue
        seen.add(m)
        stack.extend(deps.get(m, set()) - seen)
    return seen


def main() -> int:
    mods = core_modules()
    check("the vendored core is present and non-trivial",
          len(mods) > 10, note=f"{len(mods)} modules")

    entries = entry_points(mods)
    check("the application actually imports the engine — otherwise this gate is vacuous",
          len(entries) >= 5, note=f"{len(entries)} direct entry points: {', '.join(sorted(entries))}")

    reach = reachable(mods)
    unreached = mods - reach

    # The transitive claim, asserted rather than assumed. If `schedule.py` ever stopped importing
    # `cpm`, the closure would shrink and this would catch it before the allowlist did.
    check("reachability is TRANSITIVE, not direct — modules pulled in by another are counted",
          reach > entries,
          note=f"{len(entries)} direct -> {len(reach)} transitive "
               f"(+{len(reach - entries)}: {', '.join(sorted(reach - entries)) or 'none'})")

    newly_unreached = sorted(unreached - UNREACHED)
    check("no vendored module is unreachable without being recorded",
          not newly_unreached,
          note="add an adapter, or add it to UNREACHED with a roadmap entry saying why"
               if newly_unreached else f"{len(unreached)} unreached, all recorded")
    if newly_unreached:
        for m in newly_unreached:
            lines = len((CORE / f"{m}.py").read_text(encoding="utf-8").splitlines())
            print(f"        UNRECORDED: {m} ({lines} lines) has no path from aec_api")

    # The ratchet's other direction. Without this the list becomes a graveyard of names that were
    # wired years ago, and it stops describing anything.
    now_reached = sorted(UNREACHED & reach)
    check("the allowlist has no stale entries — a wired module must leave it",
          not now_reached,
          note=f"these are now reachable, delete them from UNREACHED: {', '.join(now_reached)}"
               if now_reached else "every recorded name is still genuinely unreached")

    # Vacuity twin, version 3, and version 2's failure is worth keeping.
    #
    # v1 was `reach != mods or not UNREACHED`. It worked while modules were being wired and then R45
    # emptied the list, at which point `not UNREACHED` is permanently true and the assertion can
    # never fail: a check whose failing branch is unreachable is not a check.
    #
    # v2 dropped the alphabetically-first entry point and required the closure to shrink. That held
    # until R46 wired `windows`, which imports `compare` — so removing `compare` as a DIRECT entry
    # point stopped shrinking anything, and a correct gate failed. The check was measuring an
    # accident of which name sorts first, not the property it meant.
    #
    # The property is that the closure is DERIVED from its entry points. Asserted two ways that do
    # not depend on any particular name: no entry points must give nothing, and any single one must
    # give strictly less than all of them. A `reachable()` degenerated into "return every module" —
    # the real hazard, since it would report full coverage forever — fails both.
    deps = core_to_core_imports(mods)

    def closure(seeds: set[str]) -> set[str]:
        seen: set[str] = set()
        stack = list(seeds)
        while stack:
            m = stack.pop()
            if m in seen:
                continue
            seen.add(m)
            stack.extend(deps.get(m, set()) - seen)
        return seen

    check("...and the closure is DERIVED — no entry points reaches nothing",
          closure(set()) == set(),
          note="an empty seed set that still returned modules would mean the walk invents them")

    smallest = min((closure({e}) for e in entries), key=len) if entries else set()
    check("...and one entry point reaches strictly less than all of them",
          bool(entries) and smallest < reach,
          note=f"the narrowest single entry point reaches {len(smallest)} of {len(reach)} — a "
               "closure that returns everything regardless would report full coverage forever")

    total = sum(len((CORE / f"{m}.py").read_text(encoding="utf-8").splitlines()) for m in unreached)
    print(f"\n  vendored engine: {len(reach)}/{len(mods)} modules reachable; "
          f"{len(unreached)} unreached ({total} lines) — see R45 in docs/roadmap.md")

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("test_vendor_reachable OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
