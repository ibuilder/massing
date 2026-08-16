# The seven rooms

Massing's primary navigation is seven rooms, and they are **the same seven for everyone**. A quantity
surveyor, a superintendent and a developer see the same structure in the same order; what changes is
which room opens first.

> **Deal · Design · Planning · Schedule · Cost · Work · Operate**

## Why a fixed structure

This replaced four different left-rail taxonomies. Seven workspaces had each grown their own, so
nothing a user learned in one transferred to the next, and some modules appeared in more than one of
them. The rooms are one structure that does not change per role.

Three properties matter more than the layout:

1. **The rooms come from the API.** `GET /rooms` derives the allocation from a single section→room
   table. The shell does not invent a taxonomy — a module with no room is **reported**, never filed
   somewhere plausible. Guessing is how four taxonomies came to exist.
2. **Nothing is hidden.** All 138 modules stay reachable four ways: from their room, from the element
   they are anchored to, from the work queue when it is your turn, and from **⌘K** by name. The
   design rule is *defer, never delete*.
3. **A workspace weights the spine, it never replaces it.** Opening Construction promotes Schedule to
   the front; it does not remove Deal. A room that disappears is a room you have to relearn where to
   find.

## What each room is for

| Room | Its job | Opens on |
| --- | --- | --- |
| **Deal** | Underwrite it, fund it, lease it and dispose of it | Portfolio |
| **Design** | Model it, draw it, specify it — the architect's and engineer's room | The 3D model itself |
| **Planning** | Take it off, estimate it, bid it, buy it out, contract it and get it approved | Benchmarks |
| **Schedule** | Sequence it, run the field, and track what got built | Schedule |
| **Cost** | Budget it, change it, bill it and account for it | Budget |
| **Work** | Whatever is in your court right now | Work queue |
| **Operate** | Hand it over, maintain it, meter it and plan its renewal | Operations |

The order is deliberate: **the deal comes first because it authorizes everything after it, and the
finished asset comes last because operating it is the longest and final phase.**

Design is the one room whose content is not a panel — the 3D viewer *is* that room.

### Deal
The asset as an investment. Underwriting, land and site search, massing optimisation, due diligence,
market data, whole-life lifecycle cost, portfolio rollup, ESG. This is where a project exists before
there is a building to model.

### Design
The building and everything that describes it: the model, the drawing set, specifications,
standards and materials, model QA and analysis, BIM KPIs, space utilisation, MEP fittings, the space
program, concept renders, documents, energy analysis, and the issue/topic board.

Energy analysis and the issue board live here rather than under Schedule or Deal because an energy
model is an engineering analysis run off the geometry, and an issue board records clashes and
coordination questions raised *against* the model. Neither describes a deal or a sequence.

### Planning
Everything between "we have a design" and "we are building it": takeoff, estimating, benchmarks,
selections, bidding, buyout, contracts, approvals. It also holds **preconstruction intelligence** —
risk review (reading an incoming contract for risky clauses), scope-gap detection, bid levelling and
AI assist.

Planning split from Cost so that taking off and buying out stopped sharing a room with the general
ledger. They are different jobs done by different people at different times.

### Schedule
Time, and the field that consumes it. CPM schedule, resource loading, equipment, daily reports,
turnover. If you are asking *when*, you are in Schedule.

### Cost
Money against the building: budget, margin, earned value, WIP, the ledger, cost traceability, risk
cost. If you are asking *how much, and against which line*, you are in Cost.

### Work
Whatever is in your court right now — a single queue across every module, with a live count on the
tab. It is deliberately **only** a queue. Tools that were once filed here (risk review, AI assist)
moved to Planning, because a queue with tools in it stops reading as a list of things you owe someone.

The badge counts **ball-in-your-court** items, not totals. A badge you cannot act on is noise.

### Operate
The asset in service: CMMS work orders and preventive maintenance, facility condition assessment
(UNIFORMAT II → Facility Condition Index), the asset register, utility meters → EUI, reserve study and
capital plan, CAM reconciliation, ESG rollup, post-occupancy evaluation.

The asset register lives here with the work orders rather than under Deal — it is the handover artifact
the CMMS reads, and separating the two is what severs the COBie chain.

## The vitals strip

Along the bottom of every room: **LOD · area · $/ft² · float · IRR · health**. All six are computed
from the one model, which is the point — no two rooms can quote different figures, because there is
only one source for them.

A value it cannot compute renders as **`—` with its reason**, never as `0`. On a structural-only
model, Area reads `—` because the model has no spaces, and the strip says so. This matters: a zero
looks like an answer.

## Getting anywhere fast

- **⌘K** — command palette. Every module by name, wherever it lives.
- **Room tabs** — the seven above.
- **From an element** — select something; the records anchored to it are listed with it.
- **Work queue** — what is waiting on you, across every module.
- **NEXT BEST ACTION** — names one thing to do, and renders nothing when there is nothing. It does
  not manufacture a suggestion to fill space.

## Related

- [roles-views.md](../roles-views.md) — which role owns which room, and the rule for placing a new tool.
- [modules.md](modules.md) — what the 138 registers are and how records work.
- The allocation itself is enforced by `services/api/test_module_rooms.py`; the rail's reachability by
  `apps/web/src/shell/parity.test.ts`. Neither the room list nor its coverage is maintained by hand.
