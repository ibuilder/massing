# Layout parity — the old rail vs the five rooms

**Verdict: nothing was lost, and every workspace gained.** Written 2026-07-27 at v0.3.719, after the
spine became the default at v0.3.715.

The claim being checked is one written in a comment in `portal.ts`: *"Both read the SAME destination
catalog, so the two shells cannot drift on what exists."* That is exactly the kind of statement this
codebase has repeatedly found to be prose rather than fact, so it is now asserted by
`src/shell/parity.test.ts` — 14 cases, proven to fail when a destination is orphaned.

## What was measured

Two rails slice the same catalog differently:

* the **old lifecycle-stage rail** shows `stagesFor(workspace)` — that workspace's slice, grouped by
  project phase (Plan & derisk → Build → Operate, and so on per persona);
* the **five-room spine** shows `[...that slice, ...ALL_DESTS]` — deliberately *everything*, so a
  destination only the Developer rail used to surface is filed in a room rather than lost.

So the room rail should be a **strict superset**, and the interesting question is not "are the numbers
equal" but "is anything reachable in the old rail reachable in no room at all".

## Results

| check | result |
|---|---|
| destinations in the catalog | **46** |
| destinations with a room | **46** |
| unroomed (reachable in the old rail, in no room) | **0** |
| stale room mappings (a room promising something that no longer exists) | **0** |
| workspaces where the room rail loses something | **0 of 5** |
| workspaces where the room rail reaches the *whole* catalog | **5 of 5** |
| empty rooms (a heading with nothing under it) | **0** |

The last row matters as much as the first. An empty room is worse than a missing one — it reads as
"there is nothing here" rather than "this lives elsewhere", and the user stops looking.

## What each room holds, and where it came from

The right-hand column is provenance: which stage of the **old** rail each destination appeared under.
A destination listed under several stages was reachable from several personas.

### Work — *Whatever is in your court right now* (3)

| destination | was in old stage(s) |
|---|---|
| AI Assist | Build |
| My Work | Plan & derisk · Brief & program · Acquire |
| Risk Review | Plan & derisk |

### Model — *Author, coordinate and document the building* (17)

| destination | was in old stage(s) |
|---|---|
| BIM KPIs | Analyse & check |
| CDE / Standards | Model & standards |
| Climate Resilience | Build · Analyse & check · Operate |
| Concept Renders | Brief & program |
| Design Metrics | Analyse & check |
| Discipline Spine | Model & standards |
| Documents | Documents · Model & standards · Documents & model |
| IDS Requirements | Model & standards |
| Master Builder | Brief & program |
| Materials | Model & standards |
| MEP Fittings | Analyse & check |
| Model Analysis | Analyse & check · Documents & model |
| Model Health | Analyse & check |
| Module Relations | Model & standards |
| Responsibility | Plan & derisk · Model & standards |
| Space Program | Brief & program |
| Space Utilization | Analyse & check |

### Cost — *Price it, buy it out, change it and pay for it* (9)

| destination | was in old stage(s) |
|---|---|
| Benchmarks | Across projects |
| Budget | Money |
| Cost Traceability | Money |
| Cost-code Margin | Money |
| Earned Value | Money |
| General Ledger | Money |
| Risk & Cost | Plan & derisk |
| Selections | Money |
| WIP Schedule | Money |

### Schedule — *Sequence it, run the field, and track what got built* (5)

| destination | was in old stage(s) |
|---|---|
| Equipment | Build |
| Issue Board | Build |
| Resource Loading | Build |
| Schedule | Build |
| Turnover | Turn over & operate |

### Deal — *Underwrite it, fund it, lease it and dispose of it* (12)

| destination | was in old stage(s) |
|---|---|
| Asset Register | Turn over & operate |
| Diligence & Entitlements | Acquire |
| Energy | Turn over & operate |
| ESG & POE | Operate |
| Facility Condition | Turn over & operate · Operate |
| Land Screening | Acquire |
| Market Intelligence | Acquire |
| Massing Optioneer | Acquire |
| Operations | Turn over & operate |
| Portfolio | Across projects |
| Project Lifecycle | Brief & program · Design & build |
| Underwriting | Acquire |


## What this does NOT claim

* **Not a claim that the new grouping is better.** It measures reachability, not comprehension.
  Whether "Cost" is a more natural home for *Selections* than "Build" was is a judgement about how
  people actually look for things, and the honest instrument for that is `R26-V-TIMING` — first-task
  completion per persona — which needs real users and is deliberately still open.
* **Not a claim about the viewer's own tool rail.** This covers the portal's destination navigation.
  The 3D toolbar was reorganised separately (R26-TOOLBAR) with its own gate, `toolbarLayout.test`,
  which asserts every registered tool is either laid out or reported under "Unlisted".
* **Not a claim that every destination is populated.** Reachable is not the same as useful.
  `liveAudit.ts` measures what actually renders, and records that a room can be reached and still
  show only an empty-state placeholder.

## Follow-ups this produced

1. **`work` holds only 3 destinations** against `model`'s 17. Defensible — Work is the
   ball-in-your-court queue, not a category — but it is where most workspaces land by default, and
   three entries is a thin first impression. Review once V-TIMING can say whether people leave it
   immediately.
2. **`schedule` holds 5**, two of which (*Equipment*, *Resource loading*) are arguably cost-side.
   No action; recorded so the next person does not rediscover it as a bug.
3. **The provenance column is generated** and will drift once the classic shell is retired. When that
   happens, delete that column rather than let it describe a rail that no longer exists.
