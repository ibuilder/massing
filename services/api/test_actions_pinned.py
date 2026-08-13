"""HIGH-7 — every THIRD-PARTY GitHub Action is pinned to a commit SHA.

A workflow step runs arbitrary code from another repository with access to this one. A tag or branch
ref is *mutable*: whoever controls the upstream repo can repoint `v2` or `stable` at new code, and
the next CI run executes it. A 40-hex commit SHA cannot be repointed.

The worst case here was `dtolnay/rust-toolchain@stable` — not even a tag, a **branch**, used three
times. A branch ref moves on every upstream push by design.

**Scope, stated rather than assumed.** This gate requires SHA pins for third-party actions only.
`actions/*` and `github/codeql-action/*` are published by GitHub itself, from the same trust root
that runs the workflow — pinning them is defence in depth against a GitHub-org compromise that would
already own the runner. Pinning all 33 first-party references would triple the bump burden for
approximately no threat-model gain, and a gate whose upkeep outweighs its value gets switched off.
That trade-off is the claim; if it is ever wrong, change `FIRST_PARTY` and the gate follows.

**Why this parses YAML instead of grepping.** The first enumeration of this problem was a grep, and
it reported 46 references including `actions/setup-example@v1` — a **commented-out line** in
CodeQL's starter template. There is no such action. This repo has now been bitten four separate
times by a source-scanning check that could not tell code from prose, and the fix each time was the
same: read the structure, not the text. A YAML parser cannot see a comment at all.

**On `yaml` itself:** PyYAML is not declared in any requirements file — it arrives transitively via
`bandit` and `pyHanko`, and `test_worker_split.py` already imports it bare. If that transitive path
ever disappears this test raises ImportError, which fails loudly. That is an acceptable failure mode
(a gate that dies noisily is not a gate that lies), but it is a real fragility and it is written down
here rather than discovered later.
"""
from __future__ import annotations

import pathlib
import re
import sys

import yaml

WF = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows"

#: Publishers whose refs may stay on a version tag. See the scope note above.
FIRST_PARTY = ("actions/", "github/codeql-action")

SHA = re.compile(r"^[0-9a-f]{40}$")

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


def uses_refs() -> list[tuple[str, str, str]]:
    """(workflow file, job, uses-value) for every real step, comments structurally excluded."""
    out: list[tuple[str, str, str]] = []
    for f in sorted(WF.glob("*.yml")) + sorted(WF.glob("*.yaml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        for jname, job in (doc.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            for st in (job.get("steps") or []):
                if isinstance(st, dict) and st.get("uses"):
                    out.append((f.name, jname, st["uses"]))
            if isinstance(job.get("uses"), str):      # reusable-workflow call
                out.append((f.name, jname, job["uses"]))
    return out


refs = uses_refs()

# Silence is not a signal. If the glob or the parse stops finding steps, every assertion below
# passes on an empty list and the gate reports success while checking nothing.
check("the scan found workflow steps at all", len(refs) >= 30,
      f"{len(refs)} `uses:` references across {len(list(WF.glob('*.yml')))} workflow files")

third = [(f, j, u) for f, j, u in refs if not u.startswith(FIRST_PARTY)]
first = [(f, j, u) for f, j, u in refs if u.startswith(FIRST_PARTY)]

# Vacuity guard on the SPLIT itself, in both directions. If everything landed in `first`, the real
# assertion below iterates an empty list and cannot fail; if nothing did, the scope note is fiction.
check("the third-party set is non-empty — the rule below has something to check", bool(third),
      f"{len(third)} third-party references")
check("the first-party set is non-empty — the documented exemption is real, not theoretical",
      bool(first), f"{len(first)} first-party references")


def ref_of(u: str) -> str:
    return u.split("@", 1)[1].strip() if "@" in u else ""


unpinned = [f"{f}:{j} -> {u}" for f, j, u in third if not SHA.match(ref_of(u))]
check("every third-party action is pinned to a 40-hex commit SHA", not unpinned,
      "; ".join(unpinned) or f"all {len(third)} pinned")

# A tag or branch is mutable; that is the entire point. Called out separately because a BRANCH ref
# is strictly worse than a tag — a tag is at least conventionally stable, a branch moves by design.
branchy = [f"{f}:{j} -> {u}" for f, j, u in third
           if ref_of(u) and not SHA.match(ref_of(u)) and not ref_of(u).startswith("v")]
check("...and none rides a branch ref, which moves on every upstream push", not branchy,
      "; ".join(branchy) or "none")

# The twin. Everything above is a refusal test: it asserts that nothing bad is present, which is
# exactly what a predicate that answers "pinned" to every input would also satisfy. This proves the
# predicate can say NO, using the real shapes that were actually in this repo before the fix.
for bad in ("dtolnay/rust-toolchain@stable", "anchore/sbom-action@v0", "swatinem/rust-cache@v2"):
    rejected = not SHA.match(ref_of(bad))
    check(f"...and the check REJECTS an unpinned ref ({bad.split('@')[1]})", rejected,
          f"{bad} correctly rejected" if rejected else f"{bad} WRONGLY ACCEPTED")
# ...and accepts a real one, so it is not simply refusing everything.
check("...while accepting a genuine 40-hex SHA",
      bool(SHA.match(ref_of("dtolnay/rust-toolchain@4360b52568e2003a75bf9bc1d59f33a8e3fc893c"))))

# Pins are unreadable without the version they came from. Not security, but a pin nobody can
# interpret is a pin nobody will ever bump, which becomes a security problem on a slower clock.
uncommented = []
for f in sorted(WF.glob("*.yml")):
    for line in f.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("#") or "uses:" not in s:
            continue
        val = s.split("uses:", 1)[1].strip()
        repo_ref = val.split("#")[0].strip()
        if "@" in repo_ref and SHA.match(repo_ref.split("@", 1)[1]) and "#" not in val:
            uncommented.append(f"{f.name}: {repo_ref[:50]}")
check("every SHA pin carries a trailing comment naming the version it pins",
      not uncommented, "; ".join(uncommented) or "all annotated")

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(f"test_actions_pinned OK  ({len(third)} third-party pinned, {len(first)} first-party by policy)")
