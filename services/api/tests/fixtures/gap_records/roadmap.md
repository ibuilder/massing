<!-- FROZEN FIXTURE — the four stale gap records exactly as they shipped at 53cfa71a.
     `services/api/test_gap_records.py` replays its analyser against this file and must re-find
     every record here, and nothing else, before it may report on the live documents.

     It is a COPY rather than a `git show` of 53cfa71a, and that is the point: the first draft read
     the commit, which does not exist in CI's shallow clone, so the gate failed closed on every
     build. A proof-of-reach that depends on the depth of somebody's clone is not a proof, it is
     a dependency on an environment nobody here controls.

     Nothing in this file is live. Do not edit it to match a corrected document -- the whole
     value is that it still says what the tree said when the defect was present. -->

- 🟡 **RMW-LOCKGAP — the per-project edit lock is applied to six IFC-authoring routes and not to the
  other six** *(M — Lane G; **OPEN**, found 2026-09-14 by widening RMW-SWEEP's gate · gap G-11)*

  `bake_layers`, `import_families`, `import_family_pack`, `place_family`, `content_import` and
  `_restore_version` in `services/api/src/aec_api/routers/authoring.py` each read
  `Project.source_ifc`, derive a NEW IFC version from it, and write the pointer back — the textbook
  read-modify-write. `edit`, `edit_graph`, `edit_batch`, `macros_run`, `option_activate` and
  `mcp_tools._run_recipe` do exactly the same thing **inside `pid_lock.mutating(pid)`**, one of them
  carrying the comment *"same RMW race as /edit — serialize per project"*.

  **So the control exists, is named in the threat model, and covers half its population.** Two
  concurrent `place_family` calls lose one placement, both callers answered 200 — the same severity
  as the element-tag loss RMW-SWEEP fixed, on the model rather than the register.

  **Why it was not fixed in the PR that found it.** The fix is mechanical — the same three lines,
  six times, with a reentrant lock — but it wraps routes that do long IFC I/O and file writes, in a
  lane that pull request did not otherwise touch, and those paths are not exercised by the backend
  suite the way the register rows are. *One validated push beats three speculative ones*, and a
  sweep that half-rewrites a router is the shape CLAUDE.md warns gets abandoned. The set is frozen
  instead: `services/api/test_rmw_sweep.py` asserts the split in **both** directions, so a new
  unlocked writer reds the build and closing one of these six forces the ledger to be updated
  rather than leaving a gap recorded that no longer exists.

  Doing it: wrap from the `_project(db, pid)` read through `db.commit()`, re-reading under the lock
  (`db.refresh(p)`) exactly as `edit_graph` does; then move each entry in that gate's
  `IFC_PIPELINE` from OPEN to `"under pid_lock"` and watch the second assertion catch any you
  claimed but did not wrap.

- 🟡 **RMW-TOKEN — two JSON collections still lose a concurrent write, because their tables have no
  concurrency token** *(S — Lane G; **OPEN**, split out of RMW-SWEEP 2026-09-14 · gap G-10)*

  `routers/proforma.share_scenario` appends to `Scenario.shared_with` and
  `routers/realestate.save_appraisal` merges into `Project.dev_property`. Both read a JSON collection
  and write back a value derived from it, so a concurrent second grant or second appraisal save is
  silently dropped — and each caller's response echoes its own target either way, so neither can tell.

  **They were not fixed with the register row's fix, and the reason is the point of the item.**
  `modules._cas_row_edit` swaps on `modified_at`; `scenarios` and `projects` have no such column, and
  swapping on the JSON value itself is not a mechanism that behaves the same on SQLite and Postgres —
  *the identical trap `with_for_update()` is*, which Postgres honours and SQLite silently ignores. So
  closing this is a migration (add the column, backfill, route both writers through a CAS), not a
  copy of the existing fix.

  They are listed, with their reading, in `services/api/test_rmw_sweep.py`'s `BAND_2` ledger, and the
  gate reds the build on a **new** instance — so the gap is frozen rather than growing. Recorded here
  as well as there because *a sweep is bounded by the fix available to it*, and the seeding sweep lost
  four sites by leaving exactly this kind of remainder unmentioned.

<!-- fixture ends -->
