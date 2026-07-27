# Core + plugins — a plan before any reorganisation

Drafted 2026-07-27 at v0.3.719. **Nothing here is built yet.** The goal is a free core that anyone can
download and sign into, plus installable capability plugins — some eventually paid — and an engine
third parties can build against (a precon plugin, an estimating/purchasing plugin, a developer plugin,
an architectural-studio plugin).

## The one fact that decides the shape

**We have two runtimes, and "plugin" means something different in each.**

* The adopted kernel's plugin host is **TypeScript** and environment-agnostic — it runs in a browser
  or in Node. That is what `massingifc`, `massing-pdf` and the vendored `core-kernel` are built on.
* Our capability lives in **~300 Python modules** behind 60 hand-written FastAPI routers. A
  TypeScript plugin host cannot load those.

So there is no single "make it plugins" move. There are two decisions, and conflating them is the
main way this goes wrong:

| | what a plugin is | difficulty | security surface |
|---|---|---|---|
| **Client-side** | a TS bundle registering capabilities, commands and UI against **generic** server APIs | moderate — the host already exists and is vendored | modest: it runs in the user's browser with their own permissions |
| **Server-side** | Python code loaded into the API process | **hard** — no host exists, and loading third-party code into the API is a different product | severe: arbitrary code beside the database |

**Recommendation: client-side plugins first, and possibly only.** Not as a compromise — because of
the next fact.

## What is already true, and is the real enabler

**132 of our modules are schema-driven** (`services/api/modules/*/module.json`): dynamic JSON-column
tables, generic CRUD, search, import/export, workflow states, reports. Adding one needs **no
migration and no new route**.

That means a plugin can already **bring its own data model** without server code. A precon plugin
ships `module.json` files plus a TS bundle that registers panels and commands against the generic
module API. The server never learns what "precon" is.

This is the single biggest asset in the plan and it was built for other reasons. The 60 hand-written
routers are the part that does *not* generalise — they are bespoke engines (clash, drawings, IFC
authoring, proforma maths) that a plugin should **call**, not contain.

So the architecture is:

```
free core            : viewer · IFC convert/load · projects & containers · auth/RBAC ·
                       module engine (the 132) · work queue · documents · markup basics
capability plugins   : TS bundle + module.json set + entitlement, talking to generic APIs
                       and to specific engines through capability tokens
premium engines      : stay server-side, gated by entitlement, exposed as capabilities
```

## Candidate plugins, from what we actually have

Grouped from the real destination catalog (46 destinations, see
[layout-parity.md](layout-parity.md)) and the backend module inventory. The kernel's own 16 capability
families are a strong independent prior and these largely agree with it — worth noting, since two
people arriving at the same seams is evidence the seams are real.

| plugin | what it takes with it | why it is a clean cut |
|---|---|---|
| **Precon / Estimating** | estimate · takeoff2d · cost_db · assemblies_cost · conceptual_estimate · est_bands/confidence · boe_ledger · sov_build · escalation · margin | Largest coherent block; a GC's estimator needs none of the deal side. Already has its own vocabulary (WBS/CBS, BOE). |
| **Purchasing / Procurement** | procurement · buyout_schedule · bid_leveling · itb · prequalification · supply_pipeline · comps | Distinct users (buyout desk), distinct records, and it consumes the estimate rather than producing it. |
| **Scheduling / 4D** | schedule_cpm · schedule_risk/options/status · takt · pull_plan · lean · resource_loading · prod_actuals | Self-contained maths over one record type; the 4D link to the model is a capability, not a coupling. |
| **CRE / Developer** | underwrite · proforma · distwaterfall · capital · rentroll · leasemgmt · absorption · t12 · hold_sell · covenants · market | The clearest commercial cut — a GC never opens it, a developer lives in it. Highest willingness to pay. |
| **Design & Drawings** | sheetgen · drawings_render · sections/keynotes/detail_refs · cover_sheet · view_templates | Studio-shaped. Heavy server engines, thin UI — a good test of "plugin calls engine". |
| **Field Ops** | dailylog · safety · quality · itp · cx · punchlist · verified_progress · progress_rollup | Mobile-shaped, mostly the generic module engine already. Could be the *first* plugin because it needs almost no bespoke engine. |
| **Facilities / Operations** | cmms · fca · reserve · asset_register · twin · energy_star | Post-turnover; a different buyer (owner/FM) from everyone above. |
| **Coordination / QA** | clash · IDS validation · model_qa · norm_valid · model_ci · revision_delta | Arguably **core** rather than plugin — see the open question below. |
| **PDF review** | already extracted → `MassingCloud/massing-pdf` | Proves the pattern; it is the reference implementation. |
| **Family content** | already extracted → `MassingCloud/massing-families` | Content, not code — a different plugin *kind*, and worth naming as such. |

Two plugin **kinds** fall out of that last row, and the distinction matters for packaging:

* **capability plugins** — code: commands, panels, engines behind tokens.
* **content packs** — data: family libraries, cost databases, code rule sets, titleblock templates,
  spec templates. No code, no security surface, trivially versionable, and a natural paid item.

## Sequence

1. **Prove the seam with one plugin that needs no server change.** Field Ops is the candidate: it is
   almost entirely the generic module engine already. If it cannot be a plugin, none of the others
   can, and we learn that for the price of one.
2. **Entitlement before the second plugin.** `licensing.py`/`license_cloud.py` exist but are
   per-install, not per-capability. A plugin the user has not paid for must be *absent*, not merely
   hidden — a disabled button that still calls the API is not entitlement.
3. **Extract the PDF plugin as the first external consumer.** `massing-pdf` already exists; making
   this repo consume it proves the third-party path with a repo we control.
4. **Then the commercial cuts**, largest first: CRE/Developer, then Precon.
5. **Content packs last** — easy, and better designed once real plugins exist to consume them.

## The hard parts, named now

* **Entitlement is the actual product.** The plugin host is the easy half. Deciding what a free core
  can do, how a licence is checked offline (this product runs offline by design), and what happens
  when a licence lapses with data already in the project — that is the work.
* **A plugin that owns records must not be able to strand them.** If someone uninstalls Precon, the
  estimate rows still exist. The container format already carries records generically, so the data
  survives; what needs deciding is whether it stays *visible*. Orphaned-but-listed beats vanished.
* **Cross-plugin dependencies are real and must be explicit.** Purchasing consumes the estimate;
  4D consumes the schedule *and* the model. The kernel's capability tokens with version ranges handle
  this, and `require()` already distinguishes "absent" from "present but incompatible" — which is
  exactly the distinction a missing-plugin message needs.
* **The 60 bespoke routers are the ceiling.** Anything a plugin needs from them stays server-side and
  gated. Do not try to move IFC authoring or clash detection into a browser plugin.

## Open questions — yours, not mine

1. **Is Coordination/QA core or paid?** Clash and IDS validation are what makes this an openBIM tool
   rather than a viewer. My instinct is core, because it is the reason someone chooses the product,
   but it is also the most obviously valuable thing to charge for.
2. **Does a free core include authoring, or only viewing?** The 2026-07 direction was that in-browser
   authoring is a first-class goal. If authoring is free, the plugins are all workflow; if authoring
   is paid, the split is quite different.
3. **Server-side plugins ever?** My recommendation is no — third-party Python beside the database is
   a different risk posture and would need a sandbox we do not have. Third parties get the client-side
   host, the module schema, and documented APIs.

## Tracking across the four repos

Work now spans `ibuilder/massing` (product) plus `massingifc` (kernel), `massing-pdf` (review engine),
`massing-families` (content). Issues raised against a satellite from integration work should live in
that satellite — the `massingifc` PR (#5) is the template: found downstream, fixed upstream, and the
downstream copy re-synced with the local patches dropped.

The one durable rule from that exercise: **when two repos must agree, write the assertion, not the
sentence.** Every shared assumption recorded in prose had drifted by the time anyone checked; the
container-extension mismatch was only caught because it had been pinned as a test designed to fail
when it was fixed. See [`executable-architecture-checks`](../CLAUDE.md).
