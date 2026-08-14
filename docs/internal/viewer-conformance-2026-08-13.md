# R43-VIEWER-CONFORMANCE — MassingViewer's `RemoteKernel` against our live API

**Run 2026-08-13 against a live `:8093` with a real project.** This is the run the roadmap asked for
and the one MassingViewer's own docs name as outstanding. Result reported RAW, refusals included.

## What was actually stood up

Not a stub and not the demo snapshot:

| | |
|---|---|
| API | `uvicorn aec_api.main:app` on `127.0.0.1:8093`, fresh SQLite, fresh storage dir |
| Health | `GET /health` → `200 {"status":"ok"}` — checked *before* use, because a stale server also answers 200 |
| Project | `315dba91-…` from `POST /projects` |
| Model | `samples/school_str.ifc`, **8,593,426 bytes**, uploaded via `POST /projects/{pid}/source-ifc` |
| Converted | `model_kind: "frag"`, `has_source_ifc: true` |
| Queryable | `GET /projects/{pid}/elements` → **500 elements**, real `IfcBeam` rows with GUIDs, psets, storeys, disciplines |

## The correction that matters before reading the table

**The roadmap said their suite "has only ever passed against a stub its own author wrote, so it is a
green check with no subject." That is unfair, and the file says so itself.**
`packages/kernel-remote/src/conformance.test.ts` states in its own header that it runs against
cassettes and that what it proves is *"that the adapter satisfies the contract given the protocol as
documented, not that massing's service actually speaks it — those are different claims and conflating
them would be the whole value of this file thrown away."* `docs/kernels/authoring.md` records the live
run as outstanding.

So it is a correctly-scoped adapter test that names its own gap. **The missing piece was ours to
supply, and this is it.**

## The result — 1 of 7 works as-is

Probed against the live API, then resolved against the OpenAPI route table (904 paths) so that
"absent" and "present but different" are not conflated.

| `RemoteKernel` calls | Live | Verdict |
|---|---|---|
| `GET /reference/authoring-matrix` | `200` — 96 recipes, 15 categories | ✅ **speaks it, unchanged** |
| `POST /projects/{pid}/edit` | `422` — `body.recipe Field required` | ⚠️ **route exists, body differs** — kernel sends `{op, params}`, we want `recipe` |
| `GET /projects/{pid}/export.ifc` | route is `/projects/{pid}/model/export.ifc` | ⚠️ **path differs** — extra `/model/` segment |
| `GET /jobs/{jobId}` | route is `/projects/{pid}/jobs/{job_id}` | ⚠️ **scoping differs** — ours is project-scoped, theirs is global |
| `GET /projects/{pid}/geometry` | route is `/projects/{pid}/rules/geometry/run` `[POST]` | ⚠️ **different resource** — ours is a rules runner, not a geometry fetch |
| `GET /projects/{pid}/spatial-tree` | no such route | ❌ **absent** |
| `GET /projects/{pid}/elements/properties` | no such route | ❌ **absent** |

### One refusal that reads as a match and is not

`/projects/{pid}/elements/properties` answered **`404 {"detail":"element not found"}`** — a *domain*
message, which normally means a route matched and rejected the input. It did not. There is no such
route; `/projects/{pid}/elements/{guid}` matched with `guid = "properties"`. Read from the status line
alone this looks like a contract mismatch to negotiate; it is an absent endpoint. **The OpenAPI table
is what separates them, and probing alone would have got this one wrong.**

## What this means for adoption

The gap is **narrow and mechanical**, not architectural:

- **Two endpoints to add** — `spatial-tree` and `elements/properties`.
- **Three renames/rescopes** — `export.ifc`, `jobs/{id}`, `geometry`. Cheap on either side; worth
  agreeing which side moves rather than both adding aliases.
- **One body-shape decision** — `/edit` taking `{op, params}` vs `recipe`. This is the only one with
  real design content, because `recipe` is our GUID-stable edit vocabulary and `op` is theirs.

None of it is blocked on them. Every remaining item is a change we can make or a name we can agree.

## Reproducing

```bash
# from services/api, with the venv
DATABASE_URL=sqlite:///.../conf_api.db STORAGE_DIR=.../conf_storage AEC_TRUST_XUSER=1 \
PYTHONPATH="C:\Server\modelmaker\services\api\src;C:\Server\modelmaker\services\data\src" \
  ./.venv/Scripts/python.exe -m uvicorn aec_api.main:app --host 127.0.0.1 --port 8093
```

Then create a project, `POST /projects/{pid}/source-ifc` with `samples/school_str.ifc`, and probe the
seven paths above. **Check `/health` first** — and confirm the element count, because a project that
exists is not the same as a project with a model in it.

## Two traps hit while doing this, both mine

1. **An em dash in a `curl -d` JSON payload** mangled the request and the project came back without an
   `id`. The failure looked like a schema problem and was an encoding one — the same cp1252 theme as
   `test_output_encoding.py`.
2. **`/tmp` in bash is not `/tmp` to the Windows Python interpreter.** A file `ls` could see, Python
   reported as missing. Use an explicit Windows path across that boundary.
