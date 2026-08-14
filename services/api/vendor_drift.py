"""R43-PLAN-DRIFT — has the vendored engine's upstream moved since we pinned it?

The companion to `test_massingplan_vendor.py`, and deliberately the opposite kind of check.

| | `test_massingplan_vendor.py` | this |
|---|---|---|
| Question | did *we* edit the copy? | did *upstream* move? |
| Answer source | the tree, offline | the network |
| When it runs | every CI run | a weekly schedule |
| On a bad answer | **fails the build** | **opens an issue** |

**Why this one must not fail a build.** Upstream moving is not a defect in our tree. A red build
caused by someone else's commit cannot be fixed by editing our code, and a red nobody can act on is
the fastest way to teach people that red means nothing. The local-fork check blocks because that
*is* our defect; this one notifies.

**Why UNKNOWN is a distinct answer.** If the upstream query fails — network, rate limit, a private
repo, a renamed branch — the honest report is "could not tell", not "no drift". Collapsing those two
is how a check that has quietly stopped working keeps reporting good news, which is the failure this
repo has hit more than any other. `check_drift` therefore returns a three-valued verdict and the
caller is expected to render UNKNOWN differently from CLEAN.

Run manually:

    python vendor_drift.py                 # human-readable
    python vendor_drift.py --json          # machine-readable, for the workflow
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
from typing import Literal, NamedTuple

VENDOR_DOC = pathlib.Path(__file__).parent / "src" / "massingplan" / "VENDOR.md"
UPSTREAM = "MassingCloud/massingplan"

Verdict = Literal["clean", "drifted", "unknown"]


class Drift(NamedTuple):
    verdict: Verdict
    pinned: str | None
    upstream: str | None
    detail: str


def read_pin(doc: str) -> str | None:
    """The 40-hex commit VENDOR.md records.

    **The single source for this parse.** `test_massingplan_vendor.py` imports this function rather
    than carrying its own regex, so the gate and the drift check cannot disagree about which pin the
    document names — a disagreement neither would notice, because each would be self-consistent.
    """
    m = re.search(r"Commit\s*\|\s*`([0-9a-f]{40})`", doc)
    return m.group(1) if m else None


def read_digest(doc: str) -> str | None:
    """The recorded content digest, same single-source reasoning as `read_pin`."""
    m = re.search(r"Content digest\s*\|\s*`([0-9a-f]{8,})`", doc)
    return m.group(1) if m else None


def upstream_head(repo: str = UPSTREAM, branch: str = "main") -> tuple[str | None, str]:
    """(sha, detail) for upstream's branch head, or (None, why) if it could not be determined.

    Uses `gh` because the workflow already has an authenticated one and it keeps a token out of this
    file. Any failure returns None — never a guess, and never a fallback to "assume unchanged".
    """
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{repo}/commits/{branch}", "--jq", ".sha"],
            capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"could not run gh: {type(exc).__name__}"
    sha = (out.stdout or "").strip()
    if out.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", sha):
        why = (out.stderr or out.stdout or "no output").strip().splitlines()
        return None, f"gh exit {out.returncode}: {why[0][:160] if why else 'no output'}"
    return sha, "ok"


def check_drift(doc_path: pathlib.Path = VENDOR_DOC) -> Drift:
    if not doc_path.is_file():
        return Drift("unknown", None, None, f"{doc_path} not found")
    pinned = read_pin(doc_path.read_text(encoding="utf-8"))
    if not pinned:
        return Drift("unknown", None, None, "VENDOR.md records no 40-hex commit pin")
    head, detail = upstream_head()
    if head is None:
        # NOT "clean". A query that failed knows nothing about upstream.
        return Drift("unknown", pinned, None, detail)
    if head == pinned:
        return Drift("clean", pinned, head, "pin matches upstream head")
    return Drift("drifted", pinned, head, "upstream has moved since the pin")


def main(argv: list[str]) -> int:
    d = check_drift()
    if "--json" in argv:
        print(json.dumps(d._asdict()))
    else:
        print(f"verdict : {d.verdict.upper()}")
        print(f"pinned  : {d.pinned or '-'}")
        print(f"upstream: {d.upstream or '-'}")
        print(f"detail  : {d.detail}")
    # Always 0. The exit code is not the signal — the verdict is. See the module docstring: a weekly
    # schedule that reddens the branch for an upstream commit trains people to ignore red.
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
