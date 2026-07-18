# Workflow — author the model safely with recipes

Goal: add or edit real geometry/data in the IFC through GUID-stable recipes, without ever hand-writing IFC
or fabricating a GUID. Every edit is validated, audited, and undoable.

1. **Discover.** `list_recipes` → the authoring-coverage matrix: every recipe you can drive, grouped by
   category (walls, columns, beams, slabs, levels, spaces, families, MEP, structural connections,
   properties, groups, phasing…) with the IFC class each emits. Pick the recipe whose `produces` matches
   the intent.
2. **Know the params.** Each recipe takes a small param object (e.g. `add_wall` →
   `{start, end, height, thickness, level}`; `set_pset` → `{guids, pset, props}`). If unsure of the shape,
   read the recipe's entry in `docs/authoring-matrix.md` or place one element and inspect the result.
3. **Ground the coordinates.** Author in the model's plan plane. When adding to an existing model, read the
   relevant elements first (`list_records`, `openbim_quality`) so new geometry lands on the right level and
   snaps to existing datums — the CAD command line and snap engine exist precisely so humans do this; as an
   agent, compute the coordinates deliberately.
4. **Apply.** `run_recipe` with `{project_id, recipe, params}`. This is a **write** tool: under RBAC you
   need editor role. It validates params against the authoring guardrails (a zero-length wall or missing
   host is rejected with a clear error, not a broken model), saves a **new audited IFC version**, and
   records it in the edit history so it can be undone.
5. **Publish.** `run_recipe` deliberately does **not** reconvert. After your batch of edits, tell the user
   the model needs a **publish** (the normal reconvert flow) so the viewer and the property index pick up
   the changes. Until then the new version is saved but not yet streamed.
6. **Verify.** After publish, re-read (`openbim_quality`, `drawing_qa`, or the relevant analysis) to confirm
   the edit did what was intended, and report the before/after.

Never bypass the recipe surface. If something you need isn't a recipe yet, say so — a new recipe is a
server change, and it will then appear in `list_recipes` automatically.
