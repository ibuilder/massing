# Design audit & interface plan

> **Make the most powerful thing in AEC feel like the simplest.**

External design audit, 2026-07-25, read against the README, the CHANGELOG and the live demo shell.
18 findings · 5 principles · 6 interface moves · 4 phases. This file is the durable record; the
actionable engineering lands in [roadmap.md](../../roadmap.md) as the **R24 ring**.

## The thesis: adoption is the binding constraint, not capability

The platform spans acquisition → turnover on one IFC model. The interface is currently organised the
way the **engine** is built, rather than the way an architect, superintendent or developer actually
spends a Tuesday. That gap — not missing capability — is what decides whether any of it gets used.

| evidence | source |
|---|---|
| **47%** of contractors name *getting people to use new technology* their single biggest challenge — ahead of cost or integration | AGC, 2024 technology-adoption survey |
| **10h+ a week** spent chasing information across people and systems, for 53% of respondents; 22% spend 20h+ | Quickbase, 2023 gray-work report |
| **12%** of features drive 80% of daily usage; ~80% are rarely or never used | Pendo, 2019 Feature Adoption Report (615 subscriptions) |
| **30–50%** faster first-task completion when advanced features are *deferred, not deleted* | Nielsen Norman Group, progressive disclosure |

The consequence is specific. With ~130 modules shipped, the industry baseline says roughly **ten**
are what any one person touches on a given day — and *which* ten depends entirely on who they are.
A catalog with favourites and a filter treats that as a **browsing** problem. It is a **routing**
problem.

The upside is equally specific: because every record, geometry and cost line is keyed to the same IFC
GlobalId, the platform can answer *"where did this number come from"* in one hop. The interface does
not currently cash that in.

## Four people, four clocks

The app already knows these roles; it does not yet act on them.

| persona | the question | session | needs | kills adoption |
|---|---|---|---|---|
| **Developer** | "Does it pencil, by Friday?" | 20 min, 6× a day, laptop | one number, and its provenance | a 3D viewer they didn't ask for |
| **Architect / Engineer** | "Is the model clean and issued?" | 4+ hours, two monitors | density, keyboard, undo they trust | modal results with no history |
| **GC / Project Manager** | "What's in my court today?" | all day, constant switching | a queue, not a catalog | a wall of tiles on the home screen |
| **Superintendent / Sub** | "Log it before I forget it." | 40 s, one thumb, gloves, sun | 3 taps, offline, a visible queue | a desktop layout squeezed small |

## Five principles

1. **One model, one card.** A wall, an RFI and a cost code are the same object seen from three sides.
   One card component renders it everywhere, with the same lifecycle strip. Learn it once.
2. **The job, not the module.** Nobody opens "Submittal Register" — they answer a thing that is late.
   Navigation starts from a queue and a command bar; the module is where you *land*, not where you start.
3. **Never hide — explain.** A missing button is a support ticket; a disabled button that says
   *needs GC · Project Manager* is a lesson.
4. **Every number traces.** Any figure on screen is one click from its chain: IRR ← NOI ← rent roll ←
   area ← this slab's GlobalId. This is the entire reason to be IFC-keyed. Make it visible.
5. **Fast is a feature.** Budgets, not hopes: 100 ms for a click echo, 1 s for a panel; anything
   longer becomes a named job in a tray you can walk away from. Never a blocking spinner.

## Six interface moves

1. **One bar that does everything.** ⌘K searches records, jumps to modules, runs authoring verbs,
   finds an element by GlobalId — grouped by *verb / record / element / report*, never a flat list.
   The existing AI ask box becomes the fallback row rather than a separate feature to find.
2. **Replace the catalog with a spine.** A persona-scoped rail of ~seven destinations with live
   *ball-in-your-court* counts. Nothing is deleted — the rest stay one keystroke away.
3. **Home is a queue with a horizon.** Work queue left, project health right, one banded verdict on
   top. Rows actionable inline, without opening the module.
4. **The element card, everywhere.** Six lifecycle states — designed · checked · priced · scheduled ·
   installed · verified — rendered identically wherever the element is named.
5. **Numbers that show their work.** Every figure expands into the chain that produced it, tagged
   model-derived / overridden / market assumption, ending in a clickable element.
6. **A field mode, not a small desktop.** 56 px targets, 17 px body, 7:1 contrast, capture-first home,
   permanently visible sync queue. A separate mode with its own rules, not a responsive breakpoint.

**Density scale** — Field (56 px / 17 px / 7:1) · Default (36 px / 14 px / 4.5:1) · Compact
(28 px / 13 px). One switch, per user, persisted. A superintendent and a scheduler should not be given
the same row height.

## The visual system

- **Colour, restrained on purpose.** Blue = interactive & model-derived. Green = solved, healthy.
  Amber = your attention. Red = blocking. Nothing else is coloured, ever.
- **Two faces, no exceptions.** A sans for language; a **mono** for anything a machine produced — IDs,
  GlobalIds, quantities, currency, dates, statuses. The split is the fastest signal for
  *"this is data, not prose."*
- **The grid is the brand.** A 24 px minor / 192 px major grid behind every workspace at 5–7% opacity —
  the drawing sheet, the site plan and the spreadsheet at once. Borders, not elevation.

## The 18 findings

| # | sev | area | finding |
|---|---|---|---|
| 01 | **crit** | Navigation · portal | The module catalog is the best asset and the worst front door — routing, not browsing |
| 02 | **crit** | Navigation · pillars | Model / Construction / Finance is a mode switch, not a workflow |
| 03 | high | Identity · roles | Two role dimensions gate the UI invisibly |
| 04 | high | Feedback · long jobs | Convert / reindex / republish are background work with foreground UI |
| 05 | high | Results · analysis | Clash, IDS, cost and energy results are modals — so they have no history |
| 06 | high | Object model | The single-GUID advantage is real in the backend and invisible in the UI |
| 07 | high | Onboarding | The first-run tour teaches the chrome instead of the payoff |
| 08 | med | Persona | The persona picker only relabels; it should change the shape of the product |
| 09 | med | Tools panel | The accordion mixes verbs (instant) with reports (produce an artifact after a wait) |
| 10 | med | Finance | Great numbers with no provenance |
| 11 | med | Density | Default web spacing in a tool people use for eight hours |
| 12 | med | Mobile | Field capture is a bottom sheet inside a desktop information architecture |
| 13 | med | Search | Cross-module search exists but is scoped to modules |
| 14 | low | Empty states | Blank projects were hardened for robustness, not for guidance |
| 15 | low | Charts | A dependency-free SVG kit that has not been given a grammar |
| 16 | low | Reports | The Report Center is a list of nouns |
| 17 | low | Terminology | Three vocabularies (BIM, GC, real-estate) collide in one shell |
| 18 | low | Marketing → app | The site promises a lifecycle; the app opens on a shell |

## What was already true before the audit landed

Two findings were partly addressed in **v0.3.677** by an independent live audit — worth recording so
the ring is not re-litigated:

- **Nav density (#01/#02, partial).** The `Build` stage held 13 entries of which 7 were project
  accounting, and `Model & standards` held 14. Split into Build / Money and Model & standards /
  Analyse & check; largest group **14 → 7**, nothing removed. That is the *shape* the spine wants,
  applied to the existing rail rather than replacing it.
- **Controls are labelled.** 170 visible controls, **0** unlabelled, 0 console errors — so finding #03
  is about *permission legibility*, not about missing labels.

And one finding the live audit independently reached from the other direction:

- **#07 onboarding / #18 marketing → app.** The Master Builder panel is already a live 8-step
  readiness synthesis that names exactly what is missing and links to the tool that fixes it. It is
  reachable from **one** destination in **one** workspace. Promoting it is the cheapest available
  progress on both findings.

---

*Sources: AGC 2024 technology-adoption survey · Quickbase 2023 gray-work report · Pendo 2019 Feature
Adoption Report (615 subscriptions) · Standish Group CHAOS 2002 · Nielsen Norman Group, progressive
disclosure · CII IR-153 rework causation.*
