# UX / UI findings — app-wide heuristic review

A lightweight pass across the four workspaces (Model / Drawings / Construction / Finance) and the
shared chrome, capturing issues by severity with a recommended order. Seeded from the 2026-06
tools-panel redesign; the rest is a backlog to work through, not yet implemented.

Severity: **High** (hurts daily use / blocks discovery) · **Med** (friction) · **Low** (polish).

## Done — tools & analysis surface (2026-06)
- ✅ **Two confusing tool surfaces.** Rule established: the floating viewer toolbar = *interact with
  the model*; the ⚙ Tools rail = *produce outputs / run analysis / batch edits*. Removed the
  duplicate rail "Measure" section (moved "clear" to the toolbar).
- ✅ **Everything always shown.** Tools rail is now a collapsible accordion with per-section
  preconditions; unmet → one muted "needs a project / source IFC" line + auto-collapse (no more
  repeated dead rows). Open/closed state persists.
- ✅ **Cramped results.** Cost / Energy / MEP / IDS / clash now open a readable result modal
  (`ui/result.ts`) with tables/metric grids; a one-line status stays in the rail.
- ✅ **Not role-aware.** Tools panel now persona-ordered (`TOOLS_BY_PERSONA`): a persona's primary
  tools sit on top, the rest fold under "More tools". Mirrors the existing workspace/rail filtering.

## Backlog

### High
- **Construction portal scales poorly (68 modules).** A flat module list is overwhelming. Needs
  grouping (by discipline/phase), search, favorites/pins, and **persona filtering** (a GC, architect,
  and owner's-rep should not see the same 68 entries). Extend the `TOOLS_BY_PERSONA` idea to modules.
- **Workspace ↔ tool overlap.** Exports, Cost/Pay Apps, and Schedule live in the viewer's ⚙ Tools
  rail *and* conceptually belong to the Construction/Finance workspaces. Decide one home per
  capability (or make the rail a quick-access shortcut that deep-links into the workspace) so users
  aren't unsure where the "real" one is.

### Med
- **Icon-only floating toolbar (~20 glyphs).** Discoverability relies entirely on hover titles
  (`↔ ▱ ✂ ⊙ ◐ ⊞ ⌫ 👥 ⤴ ⬚ ☰ ▭ ▮ ▬ ❏ ␡ ◧ ◨ ✥ ⟲ ✎ ⧉`). Group by function with dividers, consider an
  overflow menu for the long tail, and/or a one-time labelled "what's this" affordance.
- **Empty-state consistency.** Different panels phrase "no project / no model / no source IFC"
  differently. Standardize copy and styling (the tools accordion's muted-reason pattern is a good
  template to reuse in the portal and drawings).
- **Result/feedback reuse.** The new `toast` + `showResult` modal pattern should be the standard for
  long-running portal actions (sync, exports, bulk ops) instead of inline text.

### Low
- **Theme/contrast audit** in light mode (the dark theme is the primary; verify the result modal,
  accordion chevrons, and disabled-state contrast in light mode).
- **Keyboard & a11y.** Accordion headers are real `<button>`s with focus (good); audit tab order and
  ensure the result modal traps/returns focus and the toolbar buttons keep their `aria-label`s.
- **Responsive / mobile** layout was not reviewed; the rail + floating toolbar likely need a
  narrow-viewport treatment.

## Not yet reviewed
- **Finance / Proforma** workspace (scenarios, sensitivity, portfolio roll-up) — needs its own pass.
- **Drawings set** workspace beyond the earlier layout fix — the sheet register / markup flow looks
  solid but deserves a task-flow review (create → markup → promote-to-RFI).
