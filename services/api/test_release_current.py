"""The shipped version must actually have been RELEASED, not merely bumped.

Sibling of `test_changelog_current.py`, and written for the same reason one release later. That one
asserts the version in `apps/web/package.json` is NAMED in the changelog. This one asserts it has been
TAGGED — because on 2026-08-29 the changelog was perfectly current and nothing had shipped.

**The gap was thirty versions.** The newest tag was `v0.3.1090` (2026-08-25); `main` had reached
`v0.3.1120`. Thirty releases of merged, CI-green, container-published work that **no user could
install**, because the desktop auto-updater serves the latest *release* and there wasn't one. Every
step of the release flow was being taken except the last: changelog current, both manifests bumped,
CI green on every commit, images published to ghcr. Only `git tag` was missing.

Nothing noticed, and nothing could have. `test_changelog_current` was green — the entries were all
there. `versionConsistency` was green — the three version fields agreed. CI was green. The one
question nobody's instrument asked was *"did any of this reach a user?"*, and a release step that
depends on someone remembering is one that has now been forgotten twice in this repo — the changelog
stopped for fifty-two releases before this stopped for thirty.

**A LAG BOUND, not equality**, and the distinction is the whole design. At the moment a release commit
is prepared the version is bumped *before* the tag exists, so `version == newest_tag` is false on every
correctly-executed release and a gate asserting it would be switched off within a day. The bound is
deliberately loose for the reason `docsCurrent.test.ts` gives about its own: tighten it and it fails on
every release; drop it and it fails never, which is where this started. Ten would have fired twenty
releases before anyone noticed this one.

**The vacuity guard is not optional here.** `actions/checkout` does not fetch tags by default — it does
a shallow clone and `git tag -l` comes back EMPTY. A gate that read that as "no newest tag, nothing to
compare, pass" would be green forever while measuring nothing, which is the exact failure this file
exists to catch, one level up. So a missing tag list is a FAILURE that says why, and `ci.yml`'s
api-tests checkout carries `fetch-tags: true` to feed it. If that line is ever removed this goes red
rather than quiet.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

#: How far the shipped version may run ahead of the newest tag before this fails.
#: 1 is normal (the release commit itself); a sustained gap means releases stopped happening.
LAG = 10

FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + label + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


def _minor(v: str) -> int | None:
    m = re.fullmatch(r"0\.3\.(\d+)", v)
    return int(m.group(1)) if m else None


with open(os.path.join(ROOT, "apps", "web", "package.json"), encoding="utf-8") as fh:
    shipped = json.load(fh)["version"]

now = _minor(shipped)
check("the shipped version parses — otherwise every comparison below is meaningless",
      now is not None, f"apps/web/package.json says {shipped!r}")

tags: list[int] = []
try:
    out = subprocess.run(["git", "tag", "-l", "v0.3.*"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout
    tags = sorted(n for n in (_minor(t.strip()[1:]) for t in out.split("\n") if t.strip())
                  if n is not None)
except (subprocess.CalledProcessError, FileNotFoundError) as exc:
    check("git is available to list tags", False, str(exc))

# THE VACUITY GUARD. An empty tag list is the shallow-clone default, not a repo with no releases.
check("the tag list is non-empty — a shallow checkout without `fetch-tags: true` reads as zero tags "
      "and would make every assertion below vacuous",
      len(tags) > 10,
      f"{len(tags)} v0.3.* tags visible — if this is CI, restore `fetch-tags: true` on the "
      f"api-tests checkout in .github/workflows/ci.yml")

if now is not None and tags:
    newest = tags[-1]
    behind = now - newest
    print(f"  shipped v0.3.{now} · newest tag v0.3.{newest} · {behind} ahead (bound {LAG})")
    check(f"the shipped version is within {LAG} releases of the newest tag",
          behind <= LAG,
          f"v0.3.{now} is bumped but v0.3.{newest} is the newest TAG — {behind} versions have been "
          f"merged and never released. The auto-updater serves the latest release, so none of it "
          f"has reached a user. Tag the release rather than raising this bound")

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_release_current OK")
