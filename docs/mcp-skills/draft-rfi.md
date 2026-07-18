# Workflow — draft an RFI grounded in the model

Goal: turn a coordination question ("is there a clash between the beam and the duct on level 3?") into a
well-formed RFI that references the project's real state, not a guess.

1. **Orient.** `project_snapshot` → note the open-RFI count and the risk headline so you don't duplicate an
   existing question and you know the project's discipline mix.
2. **Ground the question.** Pull the relevant facts:
   - `list_records` with `module: "clash"` (or `rfi`, `submittal`) to see what's already logged;
   - `openbim_quality` or `standards_check` if the question is about model/standard conformance;
   - `drawing_qa` if it's about a sheet (it cites findings to sheet numbers you can quote).
3. **Write it tightly.** Compose a `subject` (one line) and a `question` that states the observed condition,
   the affected elements/sheets, and the decision you need — in the words a PM would use.
4. **Create it.** `create_rfi` with `{project_id, subject, question, discipline}`. This is a **write** tool:
   under RBAC you must hold at least editor on the project. Confirm the returned `ref` back to the user.
5. **Close the loop.** Report the new RFI's ref and one-line summary; if the snapshot showed a related open
   item, mention it so the team can link them.

Keep the RFI specific and answerable — a good RFI names the elements, cites the sheet or spec section, and
asks exactly one decision.
