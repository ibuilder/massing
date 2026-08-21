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

## CLOSED 2026-08-21 — and this report was wrong twice

Both absent endpoints are built and tested (`services/api/test_spatial_tree.py`). Before writing
them, the seven rows above were re-derived from `kernel.ts` itself rather than trusted, and that
turned up two errors in this document. Both are the same mistake: **a table is a sample of a
population somebody has to count.**

### 1. `elements/properties` is a POST, and this said GET

The row reads `GET /projects/{pid}/elements/properties` → **absent**. The absence was real. The
method was not: the adapter sends `{guids: [...]}` in a **POST** body, and its own comment says why
— "one POST rather than a GET per element", because a property panel over a multi-selection is
where per-element round-trips bite.

This is the *same* mis-read the section above congratulates itself for catching. Probing with GET hit
`/elements/{guid}` with `guid="properties"`; the OpenAPI table correctly said there was no such GET
route, and the conclusion drawn — "an absent GET" — quietly kept the wrong method. Resolving the
status line against the route table fixed *which question* was being asked and not *what the client
actually sends*. **The answer to "does our service speak it" is in the client's source, not in a
probe of ours.** A GET-shaped endpoint would have satisfied every check in this file and been
unreachable from the adapter forever.

### 2. The population was NINE calls, not seven

Listing every `transport.*` call in `kernel.ts` gives nine, not seven. Two are missing from the
table entirely:

| Missing from the table above | Ours |
|---|---|
| `GET /projects/{pid}/snap?x=&z=&r=` (`snapCandidates`) | not checked — no such route found |
| `GET /projects/{pid}/drawings/{kind}.svg?cut=&storey=&axis=&offset=` (`drawing`) | not checked |

So "1 of 7 works as-is" was measuring against a denominator nobody derived. It is **1 of 9** on the
same evidence, and the two new rows are unassessed rather than failing — they are not fixed here,
because each is its own question. Recorded so the next reader inherits the real size of the gap
instead of a number that was only ever a count of the rows somebody wrote down.

### 3. Their cassette and their published type disagree

`conformance.test.ts` stubs `spatial-tree` as `{kind, name, children}`. `provider.ts` documents
`SpatialNode` as `{ref, ifcClass, name, elevation?, children}`. The cassette is cast through
`as HttpOutcome<T>`, so TypeScript never compares them. **We implemented the published interface**,
which is the contract; the cassette is a fixture with a hole in its type checking. Worth telling
them, and worth noting here because "their tests pass" is not evidence about which of the two
shapes is meant.

### What shipped

* `GET /projects/{pid}/spatial-tree` — the real `IfcRelAggregates` chain (Project ▸ Site ▸ Building
  ▸ Storey ▸ Space), every node carrying its GlobalId. Built at index time in
  `services/data/src/aec_data/properties_index.py`; **never** grouped from the `storey` name string,
  which has no GUIDs in it and merges two buildings that each have a "Level 2".
* `POST /projects/{pid}/elements/properties` — `{guids: [...]}` → one row per hit. A guid we have no
  element for is **absent** from the array, preserving the adapter's documented distinction between
  "no properties" and "not found".
* An index written before `index_schema: 2` is **refused (422, `code: "refused"`) with the remedy in
  the sentence**, not answered with a null tree. A v2 index whose model genuinely has no `IfcProject`
  is a 404. Those are different answers and the version number is the only thing that separates them.
* Our own model browser gained "By spatial structure", which is the first grouping in it keyed on a
  GlobalId rather than a name.

Still open on the original list: the three renames/rescopes (`export.ifc`, `jobs/{id}`, `geometry`)
and the `/edit` body shape, all of which need a *decision* about which side moves rather than code.

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
