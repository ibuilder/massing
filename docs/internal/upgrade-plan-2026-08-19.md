# Upgrade plan — 2026-08-19, at v0.3.986

**Grade: opinionated audit + decision brief. Nothing built from this file.** It is a reading of
the tree as it sits today, for the operator to pick from. It is **not** a work list and **not**
current after the next release. The live work list remains [`docs/roadmap.md`](../roadmap.md).
Security controls live in [`docs/security/threat-model.md`](../security/threat-model.md); the
security *queue* lives in [`security-roadmap.md`](security-roadmap.md).

**Method (so this is falsifiable).** Architecture docs and the standing roadmap; two code
walks of `services/api` + `services/data` and `apps/web`; measured line counts and lock pins on
this checkout; prior internal audits (tech-debt 2026-08-09, plan 2026-08-10, design audit).
CodeQL alerts were **not** re-queried — this environment's GitHub token returns 403 on the
code-scanning API. Do not treat "not queried" as "zero open."

---

## Verdict, first

Massing is already a **whole-lifecycle IFC platform** (authoring + 139 registers + proforma) with
the right architectural bets: GUID identity, server-side IFC write, Fragments in the browser,
rooms as the one shell. The binding constraint is **not missing capability**. It is the same
constraint the July design audit named: **adoption** — routing each person to the ten things they
touch today, making numbers traceable, and making authoring feel immediate.

Do **not** rewrite the stack, migrate the UI to another framework, or open a second "big ticket"
(CMMS, photo-pin, field-PWA) until the existing spine, element card, field mode, and authoring
round-trip are finished. Breadth is already the asset *and* the risk.

If you take only one engineering sequence after the decisions below, take this:

1. **Operator security posture** (branch protection + hosted defaults) — you decide; engineering
   cannot close it.
2. **User-visible reach** of things that already exist (element card on four more surfaces,
   readiness on every room home, runs history for clash/IDS).
3. **Authoring feel** — incremental model reload / optimistic geometry so Place does not wait on
   a full Fragments republish.
4. **Pay the god-file tax alongside features** (`client.ts`, `app.ts`, `register.ts`) — never as
   a standalone rewrite.
5. **MassingViewer swap** when packages are on npm — keep shipping here until then.

---

## What this product actually is

Four services on one IFC-keyed model:

```
IFC (source of truth)
  → converter (Node, IFC→.frag)
  → services/data (ifcopenshell: recipes, clash, QTO, drawings)
  → services/api (FastAPI: auth, 61 mounted routers, 139 module.json registers, jobs)
  → apps/web (Vite/TS: seven rooms + lazy 3D viewer)
```

**Users do not experience four services.** They experience seven rooms — Deal · Design · Planning
· Schedule · Cost · Work · Operate — plus a persona that *weights* which room opens first.
Design *is* the 3D viewer. Work is a ball-in-court queue. Everything else is a register or a
derived analysis.

Authoring is **not** an in-browser CAD kernel. Clicks arm a named recipe; Python writes IFC by
GlobalId; the converter republishes `.frag`; the viewer reloads. That is why the model stays
correct and why Place can feel slow. Treat that round-trip as the product's main performance
problem, not "the API is slow" in the abstract (request p95 is already budgeted at 100 ms in
`perf_budget.py`; click/panel budgets are still unmeasured).

---

## What is already good — do not redo

These were checked, not assumed:

| Area | Evidence on this checkout |
|---|---|
| Architecture | GUID + Fragments + API metadata split is encoded in tests (`ties.test.ts`, `test_reachable.py`, `test_module_rooms.py`). |
| Rooms | Seven-room shell is the only shell; `?shell=classic` is gone; parity/spine tests hold the catalog. |
| Authz | Route-table gates (`test_route_authz`, `test_global_mutating_authz`, dispatcher privilege coverage). Production boot refuses default secret / RBAC-off. |
| Supply chain | `pypdf==6.15.0` and `cryptography==50.0.0` are in `requirements.lock` (the 2026-08-09 tech-debt bumps **already landed**). `diskcache==5.6.3` remains the known no-fix pin. |
| Framework | React and Reflex were evaluated against this tree and rejected (`plan-2026-08-10.md`). `@massing/embed` has no React dependency. |
| Observability | Request IDs, optional Sentry, optional OTLP, Prometheus `/metrics`, error log table, client error reporter, job tray. |
| Onboarding | Welcome once, sample / generate / new project, ⌘K with verbs/records/elements, empty states distinguish none / filtered / failed. |

**Stale claims in older audits (do not re-open as if current):** `apps/web/README.md` is still
Phase-0 shaped; `docs/reference/architecture.md` still says ~133 modules / 297 TS files; Node
notes in `CLAUDE.md` have been wrong twice — **measure `node -v`**. The 2026-08-09 axonometric→plan
composer defect has a later agreement gate (`test_view_kind_dispatch.py`); **re-measure before
re-fixing**.

---

## Architecture — upgrade, don't replace

The shape is right. The cost is **hub files and dual navigation fossils**.

Measured 2026-08-19:

| File | Lines | Pin in `test_file_sizes.py` |
|---|---:|---:|
| `apps/web/src/api/client.ts` | 3683 | 3683 (zero headroom) |
| `apps/web/src/viewer/app.ts` | 3032 | 3032 (zero headroom) |
| `apps/web/src/portal/register/register.ts` | 2546 | 2546 |
| `apps/web/src/main.ts` | 2102 | (shell hub) |
| `services/data/src/aec_data/drawings.py` | 2132 | (backend pressure) |

Zero headroom is the ratchet working: **every feature that touches those files pays an extraction
first.** That tax is already priced as SCALE-SEAM ⑧ (client mixins) and R39-DECOMP-VIEWER. Keep
paying it **one route group / one rail section per release**. A dedicated "split the god-files"
project will stall the product.

**Do not** convert the generic register (`register.ts`, one renderer for every `module.json`) into
server-composed HTML until someone names a **reversible slice**. R43-CRUD-FRAGMENTS already
recorded that there is no "one register" to A/B — converting one converts all. Leave it parked.

**Do not** block web work on MassingViewer. The extraction is ready on their side; packages are
not on npm. Prefer new behaviour behind existing seams (`kernel/`, tools sections) so the swap
is a dependency bump rather than a merge war.

**Dual IA is the real architecture smell the user feels.** Rooms are primary; workspaces
(Model / Drawings / Studio / Design / Construction / Developer / Finance) still exist as host
panes. Design-the-room is the viewer; Design-the-workspace is a third portal. `UX-DUP-DESTINATIONS`
is still open (Model Health / Model Analysis / BIM KPIs). That is confusion, not missing
features.

**Opinion:** freeze new workspace-level destinations. Finish `UX-DUP-DESTINATIONS` (one Analyse
home with three named jobs). Keep workspaces as implementation hosts, never as a second nav the
user must learn.

---

## Performance

The expensive work is already in the right layer (clash / QTO / drawings / convert on the server,
jobs for long runs, Fragments not IFC in the browser, pixel governor, lazy viewer ~6 MB).

What still hurts a human:

1. **Every authoring Place republishes and reloads the whole fragment set.** This is correctness
   first; it is also why Draft feels unlike desktop CAD. Highest-leverage product upgrade: after
   `apply_recipe`, stream a **delta** (or reload only dirty products) and keep the camera/selection.
   Until that exists, optimistic local mesh + "saving…" in the job tray is the honest UI.
2. **Clash, federated clash, sheet compose** — already job-shaped; make sure the UI never blocks
   on them (R24-RUNS-INBOX: history exists; routing clash/IDS/cost/energy *through* the queue is
   the open half).
3. **Large-model picking** — GUID selection + spatial re-click exist; do not add a new raycast
   library without a measured miss/hit split (`RT-BVH` is dependency-gated).
4. **Register tables at 500+ rows** — density was applied to dashboards, not registers
   (`R24-DENSITY ②`). That is where an 8-hour GC lives.

Server `AEC_GEOM_WORKERS` / PERF-WORKERS / PERF-THREADS are the right knobs for analysis
throughput. They will not make wall-drawing feel native.

---

## Security

Posture is strong for a public, self-hosted MIT app: RBAC, body cap on the ASGI receive path,
path-safe storage, defusedxml, AST sandboxes, SSRF guard with a test that enumerates `urlopen`,
HMAC webhooks, share-token curation. Standing queue: [`security-roadmap.md`](security-roadmap.md).

**You decide (engineering cannot):**

| ID | Choice | Recommendation |
|---|---|---|
| **SEC-BRANCH** | `enforce_admins` / required checks / ruleset bypass | Required status checks on `main` (reviews → 0 if agents must keep shipping). The two near-misses (red main + tagged release; tag racing later money commits) were process failures a required check would have caught. Full `enforce_admins` + 1 review makes *you* the bottleneck for every agent. |
| **SEC-OPS-1** | `AEC_WEBHOOK_ALLOW_PRIVATE` default | Keep `1` for on-prem/LAN; set `0` in any hosted/multi-tenant overlay and fail CI if that overlay is missing. |
| **SEC-OPS-2** | Split `AEC_AUTH_SECRET` into labeled subkeys | Yes, low drama, do with the next auth touch. |
| **SEC-OPS-3** | Uncomment container memory limits | Yes for prod compose; leave sandbox CPU-only if you want crash-over-OOM locally. |
| **SEC-G1** | Secret scanning in CI | Yes when a MIT-licensed scanner is available (`REL-6` / gitleaks). Until then the grep audits stay incomplete. |
| **diskcache** | Replace / accept / vendor | Accept with the existing pin + re-review date unless a fix appears; one import site (`bake_shared.py`). |
| **CC0-1.0** | Permit on the licence allowlist | Yes — you already ship CC0 family content; the written rule is narrower than reality. CC0 is more permissive than MIT. |

**Do not** treat a green CodeQL *run* as zero alerts. Re-query the alerts API from a token that
can read code scanning after the next push.

**Do not** add CSRF middleware as a fashion item without measuring: `SameSite=lax` is the entire
defence on cookie POSTs; state-changing **GET** routes are the actual sibling of that gap
(called out 2026-08-10). That is a targeted hunt, not a framework swap.

---

## Debug & operability

What exists: access log, `error_log`, Sentry (opt-in), OTel (opt-in, default sample 0.1),
`/metrics`, client `reportClientError` (deduped), load timings (fetch → parse → first frame),
job tray, toasts.

What operators and authors still cannot see quickly:

1. **Authoring pipeline as one trace** — click → recipe → IFC write → convert → frag fetch →
   first frame, with the same `request_id` / job id in the status line. Today each hop can
   succeed while the user stares at an empty canvas (metadata-only project, 404 `.frag`,
   collapsed pane = 0-hit picking).
2. **Status bar truncates (~220 px)** — errors become "something failed." Pair toast + job tray;
   put the request id on the toast action.
3. **Honest empty canvas** — "No geometry yet — Place a wall or Publish" vs a black void after
   New model. The code already knows the 404; the user does not.
4. **Perf budgets for click/panel** — `perf_budget.py` marks them unmeasured. Instrument one
   Place and one register open before claiming "fast."

---

## UI / UX / flow — the user-facing truth

The July design audit still names the product correctly: **defer, never delete.** Most of its
High findings shipped (spine, job tray, ⌘K verbs, empty states, tools/analyse split). What a
person still feels:

### Four clocks, still mixed in one chrome

| Persona | What they need on open | What they still get |
|---|---|---|
| Developer | One number + provenance, 20 min | Can land in Deal, but IRR chain to a slab GUID is not built (`R24-TRACE-UI` remaining). |
| Architect | Dense model, undo they trust | Draft works; every edit waits on publish/reload; inspector lifecycle strip exists, few call sites. |
| GC / PM | Work queue | Work room exists with a badge; catalog + "Show all modules" still compete. |
| Superintendent | 3 taps, outdoor, offline | `field/field.ts` is real (GPS + queue) **inside desktop IA** (`R24-FIELD-MODE` open). |

### Flows that work

- **First run:** welcome → sample (offline) or generate / new project (needs API) → persona.
- **Blank model → wall:** template → `createBlankModel` (storeys + datum) → Design room → Build
  rail → Draft → Place → server recipe → reload. CAD line and AI plan are alternatives.
- **Records:** room → register → GUID pin; ⌘K by name; Work queue for ball-in-court.

### Friction to spend on (ranked)

1. **Teach one nav.** Rooms only in the user's mind. Kill remaining duplicate destination names
   (`UX-DUP-DESTINATIONS`). Keep the `←` return on Drawings/Specs — those panes are still
   easy to trap in.
2. **Put the Master Builder readiness strip on every room home**, scoped by persona
   (`UX-READINESS-EVERYWHERE` / `R24-READINESS-HOME`). It already answers "what do I do next"
   and is buried in one Design destination.
3. **Element card on RFI, estimate line, pay app, COBie row** (`R24-ELEMENT-CARD ②`). Capability
   exists; reach does not. This is the IFC-keyed advantage made visible.
4. **Density on registers** (Field / Default / Compact), not only dashboards.
5. **Field mode as a mode**, not a breakpoint. Superintendent should never see the BIM rail.
6. **Catalog ★ keyboard focus** (known Low). Cheap a11y.
7. **Settle vocabulary** — storey/floor is gated; **element vs component** and
   **estimate vs budget vs cost** need your call (`R24-TERMS`).

Mobile: field capture + PWA meta exist; the BIM shell is not a phone product. Capacitor native
builds are gated on macOS/Xcode. Do not squeeze the Design room onto a phone.

---

## Decisions that are yours (parked on purpose)

Answer these before agents pick them up. A wrong call here is expensive; a delay is cheap.

| Decision | Options | Opinion |
|---|---|---|
| **R24-PERSONA-SHAPE** | Identical seven rooms for everyone vs persona-scoped fewer rooms | **Keep seven rooms identical.** Superintendents skip Deal via home + field mode; hiding rooms recreates the four taxonomies you just killed. Weight, don't hide. |
| **R24-IDENTITY** | Visual identity pass vs keep grey | **Keep grey until `R24-BASELINE` has numbers.** Colour without a measurement becomes a rewrite of `style.css` with no adoption signal. |
| **QUALITY-ROOM** | Move inspections/ITP to Work | **Leave the register in Design;** the *task* already hits the Work queue. Revisit only after watching a GC use it. |
| **R32-TAXONOMY-LIFECYCLE** | Derive document taxonomy from rooms | Yes in principle; do not invent a fourth tree. |
| **CC0 allowlist** | Widen vs remove shipped CC0 content | Widen. |
| **massingviser vs this repo as "the" platform** | Pick one federation manager | **This repo stays the product.** Sibling cores vendor in; do not grow a second shell. |
| **Open one BIG-TICKET** | FIELD-PWA / PHOTO-PIN / CMMS-OPS / A2 RAG | **None until field-mode + element-card reach ship.** Then FIELD-PWA if the superintendent is the next customer; CMMS if operate-phase is. Not both. |
| **Hosted vs on-prem defaults** | Permissive LAN vs locked cloud | Ship **two overlays**. Do not change the on-prem default to punish self-hosters. |

---

## Recommended sequence (if you take the opinion)

Slices, not a calendar. Each should be one release-sized change in an existing lane.

**A — You, this week**
1. SEC-BRANCH choice (required checks vs review bottleneck).
2. CC0 allowlist yes/no.
3. Persona-shape: confirm "weight, don't hide."
4. Pick **zero or one** big-ticket for the next quarter.

**B — Highest user-visible return (Lane A/B)**
1. `UX-DUP-DESTINATIONS` (Analyse home).
2. Readiness strip on every room home.
3. Element card on the four unwired surfaces.
4. Runs inbox: put clash/IDS on the job/history path.

**C — Authoring feel (Lane E + D, after B or in parallel if two agents)**
1. Honest empty-canvas + Place pipeline status (debug that is also UX).
2. Incremental or optimistic geometry after recipe (the actual CAD-feel upgrade).
3. Continue R39-DECOMP-VIEWER only as the tax on those changes.

**D — Hygiene alongside, never instead**
1. SCALE-SEAM ⑧ next mixin out of `client.ts` when an endpoint would grow it.
2. Secret-scan CI when a permitted scanner exists.
3. Auth subkeys + prod memory limits when you next touch compose/auth.
4. Re-query CodeQL **alerts** after pushes.

**E — Explicitly later / gated**
- MassingViewer npm swap.
- Register HTML fragments (needs a reversible slice first).
- React/Reflex (closed: no).
- Native mobile shell, EnergyPlus binaries, licensed code prose, paid APS depth.

---

## What I would refuse if asked to "just upgrade"

- A framework migration.
- A new module pack while Work / Deal still hide the next action.
- Splitting `register.ts` "because it is 2,546 lines" with no behaviour change.
- Viewer work that couples into `app.ts` instead of a tools/kernel seam.
- Treating archived UX audits (`ux-findings.md`, June 2026) as a backlog.

---

## How to use this file

Tick the decision table. File the chosen B/C items as the next NOW picks **in the roadmap**,
not by extending this document. When a row here is done, the proof is a changelog line and a
test, not an edit to this audit.

Checked on this tree: version `0.3.986` in `apps/web/package.json`; lock pins above; line
counts via `wc -l` on the five hub files. Not checked: live demo click-through, CodeQL alert
count, production overlay env.
