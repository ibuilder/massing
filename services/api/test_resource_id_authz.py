"""SEC-RESOURCE-ID — a project-scoped resource reachable by its OWN id must still authorise.

`test_route_authz` walks `/projects/{pid}/...` routes and requires each to carry a
`rbac.require_role(...)` dependency. **A route with no `{pid}` in the PATH is outside its remit
entirely** — that sentence appears, in almost those words, in the docstrings of
`test_global_authz`, `test_body_pid_authz` and `test_protected_prefix_coverage`. Each of those
closed one way the project id can arrive by some route other than the path:

    test_global_authz             a GLOBAL mutating route with no authorising dependency
    test_global_mutating_authz    ...and that it actually refuses anonymity, rather than being frozen
    test_body_pid_authz           a `pid` in the request BODY, unreachable to `require_role`
    test_protected_prefix_coverage a NEW top-level prefix silently outside `_PROTECTED_PREFIXES`

**This file closes the remaining one: the id in the path is not the project's, it is the
RESOURCE's.** `GET /attachments/{aid}/download` names an attachment; the attachment names a
project. `PUT /proforma/scenarios/{sid}` names a scenario; the scenario names a project. Nothing
in either path is a `{pid}`, so `require_role` cannot be applied and `test_route_authz` never
looks. The route is correct only if the handler fetches the row and checks membership **itself**.

## This is not hypothetical, and it is not old

It is the shape of the two most recent authorisation defects in this repo:

  * **`/proforma/scenarios/{sid}`** — `_scenario_for`'s own docstring records it: `_can_read`
    "was called by **2 of the 8** `{sid}` routes... The other six — share, update, clone, review,
    forecast, draw-package — **fetched by id and acted, with no ownership check at all**."
    `/proforma` *is* in `_PROTECTED_PREFIXES`, so anonymous callers were refused and every route
    *looked* guarded. What was missing was authorisation, not authentication.
  * **the massing.cloud sign-in door** — `AEC_OAUTH_ALLOWED_DOMAINS` was enforced in the direct-IdP
    callback and nowhere else, so a restriction held on four doors and was bypassed by the fifth.

Both were found by a person reading, and both were fixed by hand at the call site. `_scenario_for`
even says why it was written as a helper: *"so that a ninth route cannot be added without answering
the question."* **That is a convention, and a convention is what this file exists to replace** — a
ninth route can be added without calling it, and nothing goes red.

## What it checks, and the honest limits

Swept 2026-08-25: **43 routes** are outside `test_route_authz`'s remit (no `{pid}`, a path
parameter, no role gate). **Every one of them is correctly protected today** — this file fixes no
live defect and must not be read as though it did. It freezes *how* each is protected, in four
buckets, so a forty-fourth cannot join the population silently:

  ADMIN     a real authorisation dependency (`require_admin_user` / `require_platform_admin` /
            `require_scim`). Not enumerated: the dependency IS the check, and it is visible to
            anything that walks the dependant tree. New routes may join freely.
  IDENTITY  `require_identified` — identity, **not** authorisation, and enumerated for exactly that
            reason. Each of these four was a deliberate decision (see the notes beside them); a
            fifth needs the same decision made, not inherited.
  IN_HANDLER the ones that matter: no dependency any gate can see, correct only because the handler
            body authorises. Each is pinned to the helper it calls, and the call must still be
            there.
  PUBLIC    intentionally unauthenticated, each with the reason it is safe.

**What this cannot check** is whether the helper is the *right* one — `_can_read` where `_can_write`
was needed would pass here. `_can_write`'s own docstring is about precisely that confusion
("Read permission is not write permission"), so the distinction is real and is left to review. A
gate that claimed to settle it would be worse than one that names its limit.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_resource_id_authz.py
"""
from __future__ import annotations

import inspect
import os
import re
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./_resource_id_authz.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_resource_id_authz")
os.environ.pop("AEC_RBAC", None)

from fastapi import APIRouter  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402

import aec_api.main as M  # noqa: E402  (importing main registers + includes every router)

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


# ---- the population -----------------------------------------------------------------------------
# Same `_role_gate` probe `test_route_authz` uses, deliberately: if that marker ever changes, both
# files must move together, and sharing the predicate is what makes that true.
def _has_role_gate(dependant) -> bool:
    if getattr(getattr(dependant, "call", None), "_role_gate", None) is not None:
        return True
    return any(_has_role_gate(sub) for sub in getattr(dependant, "dependencies", []))


def _dep_names(dependant, out: set[str] | None = None) -> set[str]:
    out = out if out is not None else set()
    call = getattr(dependant, "call", None)
    if call is not None:
        out.add(getattr(call, "__name__", str(call)))
    for sub in getattr(dependant, "dependencies", []):
        _dep_names(sub, out)
    return out


_PARAM = re.compile(r"\{([a-z_]+)\}")
_ADMIN = {"require_platform_admin", "require_admin_user", "require_scim"}
_IDENTITY = {"require_identified"}

Route = tuple[str, str]          # (METHOD, path)
population: dict[Route, set[str]] = {}       # route -> dependency names
sources: dict[Route, str] = {}               # route -> handler source

_routers = {n: getattr(M, n) for n in dir(M)
            if isinstance(getattr(getattr(M, n, None), "router", None), APIRouter)}
for _name, _mod in _routers.items():
    for r in _mod.router.routes:
        if not isinstance(r, APIRoute):
            continue
        methods = (r.methods or set()) & {"GET", "POST", "PUT", "PATCH", "DELETE"}
        # Outside this file's remit, in order: no verb; `{pid}` in the path (test_route_authz owns
        # it); a role gate already present; no path parameter at all (nothing to dereference).
        if not methods or "{pid}" in r.path or _has_role_gate(r.dependant):
            continue
        if not _PARAM.findall(r.path):
            continue
        try:
            src = inspect.getsource(r.endpoint)
        except (OSError, TypeError):        # pragma: no cover - handler without readable source
            src = ""
        for m in sorted(methods):
            population[(m, r.path)] = _dep_names(r.dependant)
            sources[(m, r.path)] = src

# Anti-vacuity FIRST. Every assertion below is a statement about this set, and an empty set
# satisfies all of them — the failure mode `roadmapLanes.test.ts` calls "a green check over an
# empty set" and that this repo has shipped four times. If the route table or the `_role_gate`
# marker moves, this is the line that says so instead of four silent OKs.
check("the no-{pid} route population parses", len(population) >= 35,
      f"{len(population)} routes with a path id, no {{pid}}, and no role gate")


# ---- IDENTITY: enumerated because identity is NOT authorisation ----------------------------------
# `require_identified` proves who is calling and nothing else. These four are deliberate: a sample
# open and a cloud-library read are the caller's own business, and `/templates/{tid}` was a
# considered decision recorded in `test_global_mutating_authz` (it had NO identity dependency at
# all before that pass). A fifth route wanting this bar needs the argument made again.
IDENTITY_ONLY: dict[Route, str] = {
    ("GET", "/cloud/library/models/{model_id}"): "the caller's own cloud library",
    ("GET", "/cloud/library/projects/{project_id}"): "the caller's own cloud library",
    ("POST", "/samples/{sample_id}/open"): "creates a NEW project from a shipped sample; the actor is recorded",
    ("DELETE", "/templates/{tid}"): "shared template state; identity was the bar agreed in test_global_mutating_authz",
}

# ---- PUBLIC: intentionally unauthenticated, each with its reason ---------------------------------
PUBLIC: dict[Route, str] = {
    ("GET", "/auth/oauth/{provider}/login"): "starts the IdP redirect; there is no caller to authorise yet",
    ("GET", "/auth/oauth/{provider}/callback"): "the IdP's redirect back; the CODE is the credential",
    ("GET", "/families/{key}/types"): "the shared family catalog — global content, no project data",
    ("GET", "/shared/{token}"): "client-portal capability URL: the unguessable token IS the credential",
    ("POST", "/shared/{token}/comment"): "client-portal capability URL",
    ("POST", "/shared/{token}/decision"): "client-portal capability URL",
    ("GET", "/shared/{token}/digest"): "client-portal capability URL",
    ("GET", "/shared/{token}/model.frag"): "client-portal capability URL",
}

# ---- IN_HANDLER: correct only because the body authorises ----------------------------------------
# route -> the authorising call its handler must still contain. Pinned to the SPECIFIC helper, not
# to "some check": the point of failure this catches is a refactor that drops the call while the
# route keeps working for the person testing it, who is a member of the project.
IN_HANDLER: dict[Route, str] = {
    ("GET", "/attachments/{aid}/download"): "_download_allowed",
    ("GET", "/attachments/{aid}/signed-url"): "role_for",
    ("GET", "/module-attachments/{att_id}/download"): "_download_allowed",
    ("GET", "/proforma/scenarios/{sid}"): "_can_read",
    ("PUT", "/proforma/scenarios/{sid}"): "_scenario_for",
    ("POST", "/proforma/scenarios/{sid}/clone"): "_scenario_for",
    ("POST", "/proforma/scenarios/{sid}/draw-package"): "_scenario_for",
    ("POST", "/proforma/scenarios/{sid}/forecast"): "_scenario_for",
    ("GET", "/proforma/scenarios/{sid}/provenance"): "_can_read",
    ("POST", "/proforma/scenarios/{sid}/review"): "_scenario_for",
    ("POST", "/proforma/scenarios/{sid}/share"): "_scenario_for",
}

# ---- 1. every route in the population is accounted for -------------------------------------------
admin = {rt for rt, deps in population.items() if deps & _ADMIN}
declared = set(IDENTITY_ONLY) | set(PUBLIC) | set(IN_HANDLER)
unaccounted = sorted(rt for rt in population if rt not in admin and rt not in declared)
check("every no-{pid} route is admin-gated or declared", not unaccounted,
      "" if not unaccounted else
      f"{len(unaccounted)} unaccounted: {unaccounted[:4]}. A route addressing a resource by its own "
      "id cannot use require_role — there is no {pid} for it to read. Either authorise in the "
      "handler and add it to IN_HANDLER with the helper it calls, or add it to PUBLIC/IDENTITY_ONLY "
      "with the reason it is safe. Do not add it to PUBLIC to make this pass.")

# ---- 2. the in-handler checks are still there ----------------------------------------------------
missing = sorted(f"{m} {p} (expected {helper!r})"
                 for (m, p), helper in IN_HANDLER.items()
                 if (m, p) in sources and helper not in sources[(m, p)])
check("every IN_HANDLER route still calls its authorising helper", not missing,
      "" if not missing else f"{len(missing)}: {missing[:3]}")

# ---- 3. the reverse: a declared entry must still BE a route --------------------------------------
# Without this the three lists rot exactly as `clearCache.ts`'s KEEP_KEYS did — naming routes that
# no longer exist, while reading as though they were still covered. Same two-directional shape as
# `test_env_documented`, and for the same reason.
stale = sorted(f"{m} {p}" for (m, p) in declared if (m, p) not in population)
check("no declared route has left the app (or gained a role gate)", not stale,
      "" if not stale else
      f"{len(stale)} listed but not in the population: {stale[:4]}. If the route was deleted or has "
      "since gained a require_role gate, drop it from the list here rather than leaving it.")

# ---- 4. anti-vacuity on the buckets that carry the argument ---------------------------------------
# ADMIN is not asserted: it may legitimately be any size, and its members are checked by the
# dependency tree rather than by this list. The other three are the claim.
check("the IN_HANDLER bucket is non-empty", len(IN_HANDLER) >= 8, f"{len(IN_HANDLER)} routes")
check("admin-gated routes are found at all", len(admin) >= 15, f"{len(admin)} routes")

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(
    f"RESOURCE-ID AUTHZ OK - {len(population)} routes reach a resource by its own id with no "
    f"{{pid}} in the path, so require_role cannot apply and test_route_authz cannot see them: "
    f"{len(admin)} carry a real admin/scim dependency, {len(IN_HANDLER)} authorise inside the "
    f"handler (each pinned to the helper it calls), {len(IDENTITY_ONLY)} take identity only by a "
    f"recorded decision, and {len(PUBLIC)} are deliberately public. A new route in this shape fails "
    "until someone says which it is."
)
