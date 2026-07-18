# UI at scale — information-architecture plan

> **Point-in-time audit (June 2026) — superseded.** Kept for the record; current state lives in
> [roadmap.md](roadmap.md) + [roadmap-completed.md](roadmap-completed.md) and the [changelog](../CHANGELOG.md).

The platform is closing in on 100 registers, ~17 first-class panels, and 10 finance tabs, with more
coming. This document records the evidence-backed plan for keeping the UI navigable as it grows, so
future features land inside the structure instead of expanding a flat list. Findings come from
primary sources (Nielsen Norman Group, GOV.UK Design System / GDS research, IBM Carbon, SAP Fiori,
Atlassian's 2024 navigation rebuild, Larson & Czerwinski CHI '98).

## What the evidence says

1. **Breadth beats depth, moderate wins overall** — deep hierarchies slow retrieval, but very broad
   flat lists blur categories; medium structures with strongly-labeled top levels perform best
   (Larson & Czerwinski, CHI 1998; NN/g, *Flat vs. Deep Website Hierarchies*).
2. **Progressive disclosure, max two levels** — 3+ disclosure levels lose users (NN/g, *Progressive
   Disclosure*, 2006).
3. **Journey/stage-based navigation measurably improves completion** — GOV.UK's step-by-step
   pattern (present the end-to-end journey as ordered steps) tested through 8 rounds and produced a
   significant increase in task completion (GDS, 2018). Task-based IA also beats audience-based and
   org-chart IA (NN/g, *Audience-Based Navigation*).
4. **Shell nav capacity is bounded** — usability drops fast as side-nav items grow; never put
   unbounded, growing content in the shell (IBM Carbon UI-shell guidance).
5. **Products at this scale converge on the same trio** — role-curated workspaces (SAP Fiori
   Spaces), Starred + Recent first with the tail behind "More" (Atlassian 2024 nav rebuild), and a
   searchable launcher for hundreds of objects (Salesforce App Launcher).
6. **Users don't customize** — ship strong system-side defaults; personalization by role, not by
   hoping users configure things (NN/g, *Customization vs. Personalization*).
7. **Forms**: one-thing-per-page / flexible wizards for occasional dependency-heavy flows; fast
   single-page forms for high-repetition expert entry — GOV.UK explicitly exempts expert repeat
   users (GDS *One thing per page*; NN/g *Wizards*).
8. **Dashboards**: summaries and exceptions ordered by importance, not every KPI (NN/g dashboards;
   Few, *Information Dashboard Design*).

## Shipped (v0.3.60)

- **Lifecycle-stage nav groups** — the portal's first-class destinations are grouped under stage
  headers instead of one flat list. Construction: *Plan & derisk* (Risk Review, Risk & Cost, IDS) →
  *Build* (Schedule, Budget, AI Assist) → *Turn over & operate* (Turnover, Operations, Energy).
  Developer: *Acquire* (Underwriting, Land Screening, Diligence & Entitlements) → *Design & build*
  (Project Lifecycle) → *Operate* (ESG & POE). Both end with *Across projects* (Portfolio,
  Benchmarks). Evidence: #1, #3.
- **🕘 Recent** — auto-populated last-opened registers at the top of the module list (below the
  opt-in ★ Favorites). Zero-effort, per #5/#6.
- **⌘K taught in context** — a persistent "Jump anywhere: Ctrl/⌘+K" hint at the bottom of the nav;
  the palette is the long-tail navigator for the ~100 registers, per #5.

## Rules going forward

- **No new top-level nav items.** A new feature lands inside an existing stage group, an existing
  panel as a tab/card, or the command palette — never as a new first-class destination (#4).
- **Two disclosure tiers max**: stage → destination; group → register (#2).
- **Persona curates, never gates**: personas pick which sections open by default; "Show all
  modules" stays one click away (#6 + the product's own everything-reachable principle).
- Keep single-page fast forms for repetitive field entry (daily reports, readings, punch items);
  reserve wizards for occasional dependency-heavy creates (#7).

## Backlog (structural, not yet scheduled)

- **Exception-first dashboard**: lead with what needs attention (overdue, over-budget, failing
  checks) above the KPI cards (#8).
- **Tree-test the group labels** (does "Risk Review" vs "Risk & Cost" pass?) and merge if not (#1).
- **Wizard for the heaviest creates** (change-order chain, turnover package) with a visible,
  jumpable step map (#7).
- **Command palette ranking**: recents first; include records and actions, not just destinations (#5).
