# emanager → Massing gap analysis (what we adopted)

[emanager](https://github.com/) is a WordPress construction-management platform (the GC-portal sibling
of Massing). Its module set mirrors Massing's GC portal almost 1:1, so the value wasn't new
modules — it was the **cross-cutting engine features** matured in emanager's own improvement plan, and
validated against Procore / Autodesk Build best practice.

## Already in Massing (no work needed)

emanager "learnings" that Massing had already built independently: auto-numbering (`_next_ref`),
related-records (reference fields + reverse index), real attachments (MinIO), in-app + email
notifications, ball-in-court (`my_work`), global cross-module search, bulk actions, **saved views**
(`SavedViewDef` + `/modules/{key}/views`), and a test suite + CI. Massing is also **ahead** on
mobile/offline (IndexedDB upload queue) — a 2026 must-have the research flags.

## Adopted (the real gaps)

1. **Transition field-gating** — a workflow transition can declare `requires: [field, …]` that must be
   filled before it fires (RFI can't be *Answered* without an answer). Generalizes the existing
   attachment evidence-gate; `available_actions()` advertises the requirement so the UI disables the
   button and explains why. Engine-wide — any `module.json` transition can use it. (Procore shows the
   same "required fields missing" banner on approval steps.)
2. **Company / Contact directory + first-class lookups** — `company` + `contact` config modules (a
   project directory). Lookups are the existing `reference` field type pointing at the directory
   (`contact.company`, `subcontract.vendor_company`), so they get the picker, resolution, and reverse
   links for free. (Procore's flagship Directory tool.)
3. **Due dates / SLA + overdue feed** — `GET /projects/{pid}/due-feed` buckets open records (not in a
   terminal state) past or near their due date across the 11 modules that carry a due field; a
   "⏰ Deadlines" widget on the portal home surfaces overdue / due-this-week.
4. **In-app workflow map** — the record view renders a compact state diagram (states left→right,
   current highlighted, reachable next-states emphasized).

## Why these were small to add

Massing's modules engine is **config-driven**, so each change is one engine/manifest edit that
lights up across all ~75 modules at once — the same leverage that made the emanager build pay off.

Tests: `test_workflow_gate.py`, `test_due_feed.py`, `test_directory.py`.
