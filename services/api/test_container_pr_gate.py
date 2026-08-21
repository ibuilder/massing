"""R39-CONTAINER-PR — a container build must be exercisable BEFORE it lands on main.

`ci.yml`'s publish job (`containers`) is gated `github.event_name == 'push' && github.ref ==
'refs/heads/main'`. On a pull request it reports **`skipping`**, which renders green and means
nothing: it *structurally cannot* run on the event that would let a human see a break first. Both
Dockerfiles, `build-push-action` 6->7 (#276) and `setup-buildx-action` 3->4 (#279) merged all-green
under exactly that arrangement -- a 21-minute API gate, a web build, CodeQL -- and not one of those
greens had run a container build. **A skipped job is not a passed job.**

So there is a second job, `containers-pr`, that builds the same images on a PR and pushes nothing.
This file is the part that keeps it honest, and the assertions are ordered by what actually rots:

1.  **The two matrices stay equal.** This is the ratchet. A third image added to the publish matrix
    and not to the PR matrix would restore the original hole for that image alone, silently, and
    every other assertion here would still pass. Derived from both jobs, never listed here.
2.  **The PR job cannot push.** No `docker/login-action`, no write permission, no `docker push`,
    and every `build-push-action` step sets `push: false`. A build job that acquires registry
    credentials on a fork PR is a worse problem than the one this item fixes.
3.  **The path filter actually matches the matrix.** `docker-scope` decides whether to build from a
    regex over the PR's changed files. A regex and a matrix are two independent lists of the same
    thing, so the regex is extracted from the workflow and **run against each matrix `dockerfile`
    path** -- not eyeballed. Move a Dockerfile and this fails.
4.  **The publish job stays push-gated.** The cheap way to "fix" item 1 is to unpin `containers`'
    `if:` so it runs everywhere; that would push an image from a PR.

**Parsed as YAML, executed as text, deliberately mixed.** The job graph is structure and is read
with a parser (this repo has been bitten four times by a grep that could not tell code from a
comment). But the filter is a shell regex inside a `run:` block, where the text *is* the meaning --
so it is pulled out and run for real against real paths, which is the only way to know it matches.
Rule 3 carries its own twin: a filter that matched everything would satisfy every other assertion
here and quietly make the `touched=false` branch dead code, so decoy paths must NOT match.
"""
from __future__ import annotations

import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


doc = yaml.safe_load(CI.read_text(encoding="utf-8")) or {}
jobs = doc.get("jobs") or {}


def matrix_images(job: dict) -> dict[str, str]:
    """{image name: dockerfile path} from a job's `strategy.matrix.include`."""
    inc = (((job or {}).get("strategy") or {}).get("matrix") or {}).get("include") or []
    return {e["name"]: e["dockerfile"] for e in inc if isinstance(e, dict) and "dockerfile" in e}


def steps_of(job: dict) -> list[dict]:
    return [s for s in (job or {}).get("steps") or [] if isinstance(s, dict)]


PUBLISH = jobs.get("containers")
PR_BUILD = jobs.get("containers-pr")
SCOPE = jobs.get("docker-scope")

check("ci.yml declares a PR container build (`containers-pr`)", PR_BUILD is not None)
check("...and the publish job it mirrors (`containers`)", PUBLISH is not None)
check("...and the scope job that decides when to run it (`docker-scope`)", SCOPE is not None)

if PR_BUILD is None or PUBLISH is None or SCOPE is None:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)

# ---------------------------------------------------------------------------------------------- 1
pub_images = matrix_images(PUBLISH)
pr_images = matrix_images(PR_BUILD)
check("the publish matrix is non-empty -- otherwise every comparison below is vacuous",
      bool(pub_images), f"{len(pub_images)} image(s): {', '.join(sorted(pub_images))}")
check("every published image is also built on a PR",
      pub_images == pr_images,
      "matrices agree" if pub_images == pr_images
      else f"publish={sorted(pub_images.items())} pr={sorted(pr_images.items())}")
missing = sorted(p for p in pub_images.values() if not (ROOT / p).is_file())
check("every matrix Dockerfile exists on disk", not missing, ", ".join(missing) or "all present")

# ---------------------------------------------------------------------------------------------- 2
pr_uses = [str(s.get("uses", "")) for s in steps_of(PR_BUILD)]
has_login = any("login-action" in u for u in pr_uses)
check("the PR build never logs in to a registry", not has_login,
      "login-action present" if has_login else "no login step")
perms = set((PR_BUILD.get("permissions") or {}).items())
check("the PR build asks for no write permission", perms <= {("contents", "read")},
      str(PR_BUILD.get("permissions")))
runs = " ".join(str(s.get("run", "")) for s in steps_of(PR_BUILD))
check("the PR build runs no `docker push`", "docker push" not in runs)
build_steps = [s for s in steps_of(PR_BUILD) if "build-push-action" in str(s.get("uses", ""))]
check("the PR build uses build-push-action at all", bool(build_steps), f"{len(build_steps)} step(s)")
pushes = [s.get("name") for s in build_steps if (s.get("with") or {}).get("push") is not False]
check("...and every build step sets `push: false` explicitly",
      not pushes, "; ".join(map(str, pushes)) or "all explicit")

# ---------------------------------------------------------------------------------------------- 3
# The filter lives inside a `run:` block as an ERE handed to `grep -qE '...'`. Pull the pattern out
# and run it, because "the regex looks right" is the assertion this file exists to replace.
scope_run = "\n".join(str(s.get("run", "")) for s in steps_of(SCOPE))
pat = re.search(r"grep -qE '([^']+)'", scope_run)
check("docker-scope's path filter is extractable", pat is not None,
      pat.group(1) if pat else "no `grep -qE '...'` found in the run block")
if pat:
    # POSIX ERE and Python's re agree on everything this pattern uses (alternation, anchors,
    # groups, escaped dots). If that stops being true these go red, which is the right direction:
    # a filter nobody can evaluate is a filter nobody can trust.
    rx = re.compile(pat.group(1))
    unmatched = sorted(p for p in pub_images.values() if not rx.search(p))
    check("...and it matches every Dockerfile in the build matrix",
          not unmatched, ", ".join(unmatched) or f"all {len(pub_images)} matched")
    check("...and it matches ci.yml itself, so an action bump triggers a build",
          bool(rx.search(".github/workflows/ci.yml")))
    decoys = ["README.md", "docs/roadmap.md", "apps/web/src/viewer/app.ts",
              ".github/workflows/codeql.yml"]
    wrong = sorted(d for d in decoys if rx.search(d))
    check("...while NOT matching an unrelated file -- the filter can still say no",
          not wrong, ", ".join(wrong) or "none of the four decoys matched")

# The error branch, read as text: the body between a failed enumeration and its closing `fi` must
# set touched=true. Gating the build off because an API call failed is the same silence this item
# exists to remove.
#
# The closing `fi` is matched as a WHOLE LINE, and that is not fussiness: the first spelling of this
# split on the bare string "fi", which occurs four characters into `files=` on the very line the
# branch opens with. It cut the body to nothing and reported the fail-safe missing while it was
# sitting right there -- a check failing for a reason that has nothing to do with its subject.
err_branch = ""
if "if ! files=" in scope_run:
    tail = scope_run.split("if ! files=", 1)[1]
    err_branch = re.split(r"^\s*fi\s*$", tail, maxsplit=1, flags=re.M)[0]
check("docker-scope fails SAFE: a PR whose files cannot be listed still builds",
      "touched=true" in err_branch, "the error branch sets touched=true"
      if "touched=true" in err_branch else "error branch does not force a build")

# ---------------------------------------------------------------------------------------------- 4
pub_if = str(PUBLISH.get("if", ""))
check("the publish job is still gated to pushes on main -- a PR must never push an image",
      "push" in pub_if and "refs/heads/main" in pub_if, pub_if or "no `if:` at all")
check("the PR build is gated on the scope job rather than running on every PR",
      PR_BUILD.get("needs") == "docker-scope" and "docker-scope.outputs" in str(PR_BUILD.get("if")),
      f"needs={PR_BUILD.get('needs')} if={PR_BUILD.get('if')}")
check("docker-scope only runs on pull requests", "pull_request" in str(SCOPE.get("if", "")))

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(f"test_container_pr_gate OK  ({len(pub_images)} images built on both events)")
