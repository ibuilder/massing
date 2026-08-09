"""Strong-copyleft is gated over WHAT SHIPS — the lock — not over whatever is in a dev venv.

WHY THIS EXISTS, MEASURED 2026-08-09
------------------------------------
`aec_api.supply_chain --gate` walks *installed distributions* (`importlib.metadata`). The production
image installs `services/api/requirements.lock` with `--require-hashes`. Those are different sets::

    in the LOCK (ships) ........ 107
    in the local VENV (gated) .. 144
    in venv but NOT shipped .... 52     <- noise the gate spends its attention on
    SHIPPED but not in venv .... 15     <- risk the gate has never once looked at

So the existing gate is structurally unable to fail on a package that ships, and a GPL dependency
entering the image is found — if ever — by a human audit months later. That is exactly how
`bcf-client` (GPLv3, transitive via `ifctester`) reached the production lock unnoticed.
[[derive-the-population-and-the-reach]]: the reach was right and the population was wrong.

THE POLICY THIS ENCODES
-----------------------
Strong copyleft (GPL/AGPL) is a hard exclusion for this product. But that was being applied by a
human to every hit, which turned each finding into a stop-work escalation. The rule is now tiered,
and only the first tier blocks:

  * **DECLARED in a requirements file, or IMPORTED by our source** -> BLOCK. We are choosing to
    depend on it, so it is a real violation and must be removed.
  * **transitive AND unimported** -> needs a dated exemption naming the parent and the evidence it
    is unused. Development continues; the fact is on the record rather than rediscovered.
  * **dual-licensed (permissive OR copyleft)** -> not an obligation at all; we take the permissive
    grant. Recorded so that a dropped grant upstream fails loudly instead of silently.

A finding should cost a line in a table, not a day.

WHAT THIS GATE CAN AND CANNOT SEE
---------------------------------
Licence metadata comes from the installed distribution, so coverage depends on where it runs. In CI
(`ci.yml` installs the lock itself) every entry resolves. On a dev machine some do not. **The gate
reports its own coverage and refuses to present a partial run as a complete one** — a clean result
over 92 of 107 packages is not a clean result. [[audit-must-state-its-configuration]]
"""
from __future__ import annotations

import importlib.metadata as im
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from aec_api.supply_chain import _license_of, is_dual_licensed, is_strong_copyleft  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]
_LOCK = _ROOT / "services" / "api" / "requirements.lock"
_REQ_FILES = ("services/api/requirements.in", "services/api/requirements-dev.txt",
              "services/data/requirements.txt")
_SRC_TREES = ("services/api/src", "services/data/src")

#: Packages offered under a permissive licence OR a copyleft one. We rely on the permissive grant, so
#: these are not an obligation — but `is_dual_licensed`'s own docstring names the hazard: *"if the
#: upstream ever drops the permissive option the answer changes silently."* Listing them means that
#: day reclassifies the package as strong-only and fails the tier-2 assertion, instead of passing.
_DUAL_LICENSED = {
    "odfpy": ("2026-08-09", "ifctester",
              "Apache-2.0 OR GPL OR LGPL — we rely on the Apache grant. Transitive via ifctester and "
              "not imported by our source."),
}

#: Transitive, unimported strong-copyleft packages ACCEPTED to remain in the image, each with the
#: evidence that made it acceptable. An entry is a dated decision, not a silencer — re-read it when
#: the parent dependency changes.  Format: name -> (date, parent, evidence)
_ACCEPTED_TRANSITIVE = {
    "bcf-client": (
        "2026-08-09", "ifctester",
        "GPLv3. NOT declared in any requirements file and ZERO import sites in our source — our BCF "
        "2.1/3.0 surface is our own implementation. Verified by blocking `bcf` at the import hook "
        "and running test_ids_authoring, test_stored_ids, test_openbim_quality, test_norm_valid, "
        "test_bcf_api and test_bcf3: all six pass, with the blocker itself proven to bite. Removal "
        "from the lock is therefore safe; whether it MUST be removed is a licence question referred "
        "to counsel, and this entry is the record that it is known and dated."),
}


def _lock_packages() -> set[str]:
    text = _LOCK.read_text(encoding="utf-8")
    return {m.group(1).lower() for m in re.finditer(r"^([A-Za-z0-9._-]+)==", text, re.M)}


def _declared() -> set[str]:
    out: set[str] = set()
    for rel in _REQ_FILES:
        p = _ROOT / rel
        if not p.exists():
            continue
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.split("#")[0].strip()
            if line and not line.startswith("-"):
                out.add(re.split(r"[<>=!~\[ ]", line)[0].strip().lower())
    return out


def _imported(pkg: str) -> bool:
    """Is any top-level module of `pkg` imported by our source? Name-normalised both ways."""
    candidates = {pkg.replace("-", "_"), pkg.replace("-", "")}
    try:
        files = im.distribution(pkg).files or []
        candidates |= {str(f).replace("\\", "/").split("/")[0] for f in files
                       if "dist-info" not in str(f) and not str(f).startswith("..")}
    except im.PackageNotFoundError:
        pass
    names = [re.escape(c) for c in candidates if c and c.isidentifier()]
    if not names:
        return False
    pat = re.compile(r"^\s*(?:from|import)\s+(" + "|".join(names) + r")\b", re.M)
    for tree in _SRC_TREES:
        for py in (_ROOT / tree).rglob("*.py"):
            try:
                if pat.search(py.read_text(encoding="utf-8")):
                    return True
            except OSError:
                continue
    return False


def _classify() -> tuple[dict[str, str], dict[str, str], set[str]]:
    """(strong-only, dual-licensed-with-copyleft, unresolved) — three outcomes, not two."""
    strong: dict[str, str] = {}
    dual: dict[str, str] = {}
    unresolved: set[str] = set()
    for pkg in sorted(_lock_packages()):
        try:
            dist = im.distribution(pkg)
        except im.PackageNotFoundError:
            unresolved.add(pkg)
            continue
        # `_license_of`, NOT a hand-rolled read of the metadata. It prefers the OSI classifiers and
        # deliberately SKIPS a `License:` field holding the full licence text — which is what numpy
        # and scipy carry, and reading it directly classified both BSD packages as GPL in the first
        # draft of this file. One classifier, in one place.
        text = _license_of(dist)
        if not is_strong_copyleft(text):
            continue
        (dual if is_dual_licensed(text) else strong)[pkg] = text[:80]
    return strong, dual, unresolved


def test_no_declared_or_imported_strong_copyleft() -> None:
    """Tier 1 — the blocking rule. Choosing to depend on GPL/AGPL is the violation."""
    strong, _dual, _unresolved = _classify()
    declared = _declared()
    violations = {
        p: ("declared in a requirements file" if p in declared else "imported by our source")
        for p in strong if p in declared or _imported(p)
    }
    assert not violations, (
        "strong copyleft (GPL/AGPL) that we CHOSE to depend on — a hard exclusion for this product:\n"
        + "\n".join(f"  {p}  ({why})  {strong[p]}" for p, why in sorted(violations.items()))
        + "\nRemove it, or replace it with a permissively-licensed equivalent."
    )
    print(f"PASS  nothing we declare or import is strong copyleft   "
          f"{len(strong)} strong-only in the lock, 0 of them ours by choice")


def test_transitive_strong_copyleft_is_accepted_on_the_record() -> None:
    """Tier 2 — does not block, but must be a DATED decision rather than a surprise."""
    strong, _dual, _unresolved = _classify()
    undocumented = sorted(p for p in strong if p not in _ACCEPTED_TRANSITIVE)
    assert not undocumented, (
        "strong copyleft reached the SHIPPED lock transitively with no recorded decision:\n"
        + "\n".join(f"  {p}  {strong[p]}" for p in undocumented)
        + "\nAdd an entry to _ACCEPTED_TRANSITIVE with the date, the parent that pulls it in, and "
          "the evidence it is unused — or remove it from the lock. An undocumented one is a surprise "
          "waiting for an audit; a documented one is a decision."
    )
    for p, (date, parent, why) in _ACCEPTED_TRANSITIVE.items():
        assert p in strong, (
            f"_ACCEPTED_TRANSITIVE names {p!r}, which is no longer strong-copyleft in the lock (or "
            f"has left it). Remove the entry — a stale exemption exempts nothing today and something "
            f"unknown tomorrow.")
        assert date and parent and len(why) > 60, (
            f"{p}: an exemption needs a date, a parent, and real evidence — not just a name")
    print(f"PASS  every transitive strong-copyleft package is a dated decision   "
          f"{len(_ACCEPTED_TRANSITIVE)} accepted: {', '.join(sorted(_ACCEPTED_TRANSITIVE))}")


def test_dual_licensed_copyleft_stays_on_the_record() -> None:
    """Tier 3 — fine today, one upstream decision from not being.

    Recorded rather than ignored so that if the permissive option is dropped the package
    reclassifies as strong-only and fails tier 2, instead of changing our position silently.
    """
    _strong, dual, _unresolved = _classify()
    unrecorded = sorted(p for p in dual if p not in _DUAL_LICENSED)
    assert not unrecorded, (
        "dual-licensed (permissive OR copyleft) packages in the shipped lock with no record:\n"
        + "\n".join(f"  {p}  {dual[p]}" for p in unrecorded)
        + "\nAdd them to _DUAL_LICENSED — we rely on the permissive grant, and that reliance should "
          "be written down."
    )
    stale = sorted(p for p in _DUAL_LICENSED if p not in dual)
    assert not stale, (
        f"_DUAL_LICENSED names {stale}, which are no longer dual-licensed in the lock. Either the "
        f"upstream dropped the permissive option — check urgently — or they left the lock.")
    print(f"PASS  dual-licensed packages are recorded, so a dropped grant fails loudly   "
          f"{len(_DUAL_LICENSED)} recorded: {', '.join(sorted(_DUAL_LICENSED))}")


def test_the_gate_states_its_own_coverage() -> None:
    """A clean result over part of the population is not a clean result."""
    lock = _lock_packages()
    _strong, _dual, unresolved = _classify()
    assert lock, "no packages parsed from requirements.lock — the gate is measuring an empty set"
    covered = len(lock) - len(unresolved)
    pct = 100.0 * covered / len(lock)
    assert pct >= 50.0, (
        f"only {covered}/{len(lock)} lock packages could be classified ({pct:.0f}%). This run cannot "
        f"support a clean verdict — install the lock (as CI does) before trusting it.")
    where = "TOTAL" if not unresolved else f"PARTIAL — {len(unresolved)} not installed here"
    print(f"PASS  the gate reports its coverage   {covered}/{len(lock)} lock packages "
          f"classified [{where}]")
    if unresolved:
        print(f"      not classified locally: {', '.join(sorted(unresolved)[:8])}"
              f"{' …' if len(unresolved) > 8 else ''}")


if __name__ == "__main__":
    test_no_declared_or_imported_strong_copyleft()
    test_transitive_strong_copyleft_is_accepted_on_the_record()
    test_dual_licensed_copyleft_stays_on_the_record()
    test_the_gate_states_its_own_coverage()
    print("test_license_lock_gate OK")
