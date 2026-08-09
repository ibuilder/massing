# Massing documentation

Everything written down about Massing, and which of it to read. Start here rather than in the file
list — the useful path through these documents is not alphabetical.

| I want to… | Read |
| --- | --- |
| **Run it for the first time** | [Getting started](getting-started.md) |
| **Learn to use it** | [User guide](user-guide/) — start with [the seven rooms](user-guide/rooms.md) |
| **See it demoed** | [Walkthrough](walkthrough.md) — a 3-minute script, or a written click-through |
| **Deploy it for real** | [Deployment](deploy.md) → [go-live checklist](PRODUCTION_CHECKLIST.md) → [operator runbook](operations.md) |
| **Call the API** | [API reference](reference/api.md), or `/docs` on any running instance |
| **Understand how it is built** | [Architecture](reference/architecture.md) · [client vs server](client-vs-server.md) · [drawings & sheets](drawings.md) |
| **Add a record type** | [Authoring a module](authoring-modules.md) — no code required |
| **Know what it can do** | [capabilities.html](https://massing.build/capabilities.html) · [roadmap](roadmap.md) |

> **A note on trust.** Documentation in this repo has been wrong in ways that cost readers real time —
> a flag that had not existed for fifty releases, a sample deleted twelve releases earlier, a room count
> that said six when there were seven. The fix was not more careful writing; it was
> [`docsCurrent.test.ts`](../apps/web/src/shell/docsCurrent.test.ts) and
> [`docsPublished.test.ts`](../apps/web/src/shell/docsPublished.test.ts), which read these files from
> disk and fail CI when they disagree with the code. Where you see a claim about the product below, a
> test is usually holding it in place. Where a document is a plan or a snapshot, it says so at the top.

## Using Massing

| Document | What it covers |
| --- | --- |
| [getting-started.md](getting-started.md) | Docker, desktop, or dev install; your first project; where to go next. |
| [user-guide/](user-guide/) | The detailed guide — rooms, authoring, drawings, records, files, troubleshooting. |
| [walkthrough.md](walkthrough.md) | The demo script, scene by scene, with timings. Also a written tour. |
| [authoring-modules.md](authoring-modules.md) | Define a new record type as JSON — form, list, workflow. No code. |
| [families.md](families.md) | The type library: how Massing places IFC **types**, not meshes, and how to add content. |
| [mobile.md](mobile.md) | The separate mobile app. **Plan** — no native build in CI yet. |

## Reference

| Document | What it covers |
| --- | --- |
| [reference/api.md](reference/api.md) | Every significant endpoint, grouped. The live truth is `/docs` on a running API. |
| [reference/architecture.md](reference/architecture.md) | How the four services fit together, and the repo layout. |
| [client-vs-server.md](client-vs-server.md) | Which work runs in the browser and which in Python — and why the line sits there. |
| [drawings.md](drawings.md) | How a model becomes a drawing set: bake → view → sheet → SVG/DXF/PDF, the view-spec vocabulary, and the two composers. |
| [mass-format.md](mass-format.md) | The `.mass` project container. A plain ZIP; one project per file. |
| [authoring-matrix.md](authoring-matrix.md) | Coverage matrix of every authoring recipe. **Generated — do not hand-edit.** |
| [roles-views.md](roles-views.md) | Which role owns which room, and the rule used to place a new tool. |
| [mcp.md](mcp.md) | Driving the model from an AI agent over MCP. |
| [mcp-skills/](mcp-skills/) | Drop-in Claude skill pack — draft an RFI, run a takeoff, drive a recipe. |
| [engineering/](engineering/) | Internal standards: [backend](engineering/backend-standards.md) · [web](engineering/web-standards.md) · [calculation precision](engineering/calculation-precision.md) |
| [adr/](adr/) | Architecture decision records. |

## Running it in production

| Document | What it covers |
| --- | --- |
| [deploy.md](deploy.md) | The full stack: compose services, storage, auth model, hardening. |
| [PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md) | Copy-paste gate to run before exposing a deployment. |
| [operations.md](operations.md) | Day-2 operator runbook: health, flags, common incidents. |
| [ops-dr.md](ops-dr.md) | Backup, restore, disaster recovery — and how a restore is *proven*. |
| [ops/runbooks.md](ops/runbooks.md) | Incident runbooks. |
| [security/threat-model.md](security/threat-model.md) | Trust boundaries and threats. Posture lives in [SECURITY.md](../SECURITY.md). |
| [compliance/soc2-readiness.md](compliance/soc2-readiness.md) | Control mapping and gaps. |

## Integrations and bridges

Each of these documents an **optional** seam. All are off by default; none is required to run Massing.

| Document | Status |
| --- | --- |
| [massing-cloud-bridge.md](massing-cloud-bridge.md) | Optional online licence validation. Off by default; offline-first. |
| [cv-bridge.md](cv-bridge.md) | Site-progress % from photos. Massing does **not** ship the vision model. |
| [render-bridge.md](render-bridge.md) | AI concept renders. External image model; not bundled. |
| [esign-options.md](esign-options.md) | E-signature approach for contracts and change orders. |
| [realestate-marketing.md](realestate-marketing.md) | Disposition and appraisal — plan + decisions. |

## Project state

| Document | What it is |
| --- | --- |
| [roadmap.md](roadmap.md) | **What is open.** The live plan, by ring. |
| [roadmap-completed.md](roadmap-completed.md) | What is closed. Large (264 KB) — search it, don't read it. |
| [../CHANGELOG.md](../CHANGELOG.md) | Every release. The authoritative history. |
| [history/platform-history.md](history/platform-history.md) | Narrative summary of how the platform filled out, by release band. |
| [credits.md](credits.md) · [ATTRIBUTIONS.md](ATTRIBUTIONS.md) | Open-source credit. Attribution removed from screen is owed here. |

## Not documentation

[internal/](internal/) holds working notes — superseded audits and unbuilt plans. It is **excluded from
the published site** and should not be cited as current; see [internal/README.md](internal/README.md).

The public site sources `index.html`, `guide.html`, `status.html` and `capabilities.html` from this
directory. Anything you add under `docs/` is published unless it goes in `internal/`.
