# ADR-001: One sheet-composition model, or two?

**Status:** Proposed
**Date:** 2026-08-09 (at v0.3.913)
**Deciders:** repo owner
**Supersedes/relates:** the open question left by [`r36-viewer-subapp-design.md`](r36-viewer-subapp-design.md) §7

---

## Context

There are **two sheet composers**, in two modules, and they disagree about which view kinds exist.

| | `drawings.py::compose()` | `sheet_layout.py::compose_viewports()` |
|---|---|---|
| first commit | 2026-06-14 | 2026-07-18 (5 weeks later) |
| layout model | uniform fit-to-cell **grid** (`cols`) | **paper-space viewports**: `rect`, fixed `scale` 1:N, class freeze, geometric clipping |
| view dispatch | `_view_for_spec()` | `_view_polys()` → falls back to `_view_for_spec()` |
| supports `axon` | **no** | **yes** |
| shipping routes | **`sheet.svg`, `sheet.pdf`, `sheet.dxf`** (via `default_sheet`) | one: `analysis.py` sheet-regions, plus a presets endpoint |

`sheet_layout.py`'s own module docstring is explicit about the relationship:

> `drawings.compose()` lays views in a uniform fit-to-cell grid. **This is the mature endpoint of that
> idea** (the OCS layout model, server-side)…

So this is not two rival designs. It is **a succession that stalled**: the successor was built,
given one consumer, and the three user-facing sheet routes were never moved.

### The forces

**1. It is producing a wrong drawing today, not just duplication.** The `axon` branch lives in the
*wrapper* (`sheet_layout._view_polys`), and the shared helper `_view_for_spec` ends with an
unconditional fall-through to plan. So the legacy path, which calls the shared helper directly,
silently substitutes. Measured:

```
spec kind='plan'   -> label='PLAN'       sub='cut @ 1.20 m'
spec kind='axon'   -> label='ISO VIEW'   sub='cut @ 1.20 m'     <-- a PLAN, titled ISO VIEW
```

The title is the caller's, so the sheet **says ISO VIEW and draws a plan cut at 1.20 m**. On a
document an engineer may seal.

**2. The duplication is already drifting in a second way.** `_view_polys` re-implements plan and
section (to add the class freeze) and then delegates the rest. Two implementations of "what is a
plan" is how the first divergence happened; there is nothing stopping the second.

**3. A naming hazard is baked into the spec vocabulary.** `elevation` currently means three things:
a storey height (`{"kind":"plan","elevation":0.0}`), a view direction (`{"kind":"elevation"}`), and
a projection angle — which is why the axon spec had to call its angle `elevation_angle`. Meanwhile
the underlying function signature uses `elevation_deg`. Any decision here should settle whether the
spec keys and the function parameters are allowed to differ.

**4. R36-VIEWER-SUBAPP depends on the answer.** Its central promise is that 2D and 3D are peers on a
sheet. Which composer the sheet routes use decides whether that is one branch or a migration.

---

## Decision

**Move the `axon` branch down into the shared `_view_for_spec`, make an unknown kind an error rather
than a plan, and treat `compose_viewports` as the declared direction without migrating the routes
yet.** (Option A now, Option B as the stated destination, revisited when a second forcing function
arrives.)

---

## Options considered

### Option A — Backport `axon` into the shared helper; refuse unknown kinds

Move the axon branch from `sheet_layout._view_polys` into `drawings._view_for_spec`, and replace the
fall-through-to-plan with an explicit `plan` branch plus a raise.

| Dimension | Assessment |
|---|---|
| Complexity | **Low** — one branch moves down a level; one fall-through becomes a raise |
| Cost | Hours |
| Scalability | Neutral — same call graph |
| Team familiarity | High — the three sibling branches are right there |

**Pros**
- Fixes the wrong drawing immediately, for **both** composers at once.
- Removes the axon duplication rather than adding to it.
- Unblocks R36 slice 1 with no migration.
- A refusal is a contract improvement while there are still **no external callers** of the spec
  vocabulary — the cheapest moment it will ever be.

**Cons**
- Leaves two composers standing. The architectural question is deferred, not answered.
- `_view_polys` still re-implements plan/section for the class freeze.

### Option B — Complete the succession: route all sheet endpoints through `compose_viewports`

| Dimension | Assessment |
|---|---|
| Complexity | **Medium-High** — the two layout models are not interchangeable |
| Cost | Days, plus regression risk on the main drawing output |
| Scalability | Better long-term: one model, paper-space semantics |
| Team familiarity | Medium — `compose_viewports` has one consumer today |

**Pros**
- One composition model. The drift class disappears.
- Every sheet gains true 1:N scale, class freeze and clipping — real requirements for an issued set.

**Cons**
- `default_sheet()` **chooses** views and lays them in a grid by count; `compose_viewports` requires
  explicit `rect` fractions per viewport. Migrating means inventing the grid→rect mapping, which is
  new logic on the path that produces the product's primary drawing output.
- Regression surface is the one thing users see most.
- Does **not** fix the silent substitution on its own — `_view_for_spec` is shared, and would still
  fall through for any caller that reaches it.

### Option C — Merge the two composers into one function

| Dimension | Assessment |
|---|---|
| Complexity | **High** |
| Cost | Days, and the result carries both layout models internally |
| Scalability | Poor — a function with a mode flag is two functions with worse names |

**Cons:** the grid model and the paper-space model differ in what a caller must supply. Merging
produces a signature where half the parameters are ignored depending on the other half. Rejected.

### Option D — Keep both deliberately, document the split, add a gate

**Pros:** zero risk today.
**Cons:** does nothing about the wrong drawing. A gate that asserts "these two dispatchers support
the same kinds" would at least make drift loud — but that is a *complement* to A, not a substitute.
Rejected as a standalone.

---

## Trade-off analysis

The decisive asymmetry: **Option A fixes a correctness defect and Option B does not.** B is the
better architecture and the worse next move, because the defect lives in the helper *both* paths
share — migrating the routes would leave the silent substitution intact for anything still calling
`_view_for_spec`.

The second consideration is sequencing risk. B touches the code path behind the product's primary
visible output (`sheet.pdf`) with no forcing function demanding it this week. A is a strictly smaller
change that makes B *easier* later, because after A there is exactly one place that knows what a view
kind is.

What would change the answer: if R36 slice 3 (a "place this view on a sheet" control) turns out to
need per-viewport `rect` and `scale` — which is what a user dragging viewports would want — then B
stops being optional and should be done then, with the UI as its test.

---

## Consequences

**Easier**
- Adding a fifth view kind: one branch, one place, both composers get it.
- R36 slice 1 becomes a few lines instead of a migration.
- A wrong `kind` fails loudly at the point of the mistake.

**Harder**
- Nothing immediately. The debt of two composers persists and is now written down rather than
  discovered.

**To revisit**
- When a second consumer of the spec vocabulary appears (the pyRevit bridge, or an interactive
  paper-space editor), re-open B — at that point the grid→rect mapping has a real requirement to
  satisfy instead of being invented.
- The `elevation` overload. If the spec vocabulary is ever public, three meanings for one key will
  cost more than renaming it now.

---

## Action items

1. [ ] Move the `axon` branch from `sheet_layout._view_polys` into `drawings._view_for_spec`;
       have `_view_polys` delegate for it as it does for the rest.
2. [ ] Replace `_view_for_spec`'s fall-through with an explicit `plan` branch and a raise on an
       unknown kind.
3. [ ] Test: a spec of `kind: "axon"` through **`sheet()`** returns an axonometric, not a plan —
       asserted through the shipping route path, not `compose_viewports`.
4. [ ] Test (the twin): an unknown kind raises rather than rendering anything. A refusal test with no
       twin passes on a function that refuses everything.
5. [ ] Gate: the two dispatchers support the same set of kinds — so if they diverge again it is loud.
6. [ ] Record in the roadmap that the R36 print slice is *smaller* than the entry assumes, and why.
7. [ ] **Do not** migrate the sheet routes to `compose_viewports` in this pass. Revisit per above.
