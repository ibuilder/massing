<!-- FROZEN FIXTURE — the four stale gap records exactly as they shipped at 53cfa71a.
     `services/api/test_gap_records.py` replays its analyser against this file and must re-find
     every record here, and nothing else, before it may report on the live documents.

     It is a COPY rather than a `git show` of 53cfa71a, and that is the point: the first draft read
     the commit, which does not exist in CI's shallow clone, so the gate failed closed on every
     build. A proof-of-reach that depends on the depth of somebody's clone is not a proof, it is
     a dependency on an environment nobody here controls.

     Nothing in this file is live. Do not edit it to match a corrected document -- the whole
     value is that it still says what the tree said when the defect was present. -->

12. **G-10 (S) One JSON collection still loses a concurrent write** — `Scenario.shared_with` (a
   share grant). It reads a JSON collection and writes back what it derived, and that table carries
   no `modified_at`, so the compare-and-swap the record row uses does not exist for it; JSON
   equality is not a swap that behaves the same on SQLite and Postgres, which is why the same fix
   was not simply copied. `Project.dev_property` (the appraisal-override merge) was the second and
   is now **closed** under the per-project lock. It is
   listed in `services/api/test_rmw_sweep.py`'s `BAND_2` ledger, so the set is frozen and cannot
   grow silently — a new instance reds the build. Closing it means giving those tables a concurrency
   token, which is a migration (roadmap: RMW-TOKEN). Severity is small: the loss needs two grants or
   two appraisal saves inside one request window, and neither is a privilege boundary.

11. **G-12 (S) Three more read-modify-writes on tables with no concurrency token** —
   `drawingset.revise_sheet`, `proforma.sync_gmp_to_hard` and `proforma.sync_model_to_hard`.
   **The two `connections` entries were CLOSED on 2026-09-14 (RMW-TOKEN)**; they are described
   below because the reasoning is the interesting part. They were
   a **pair on one blob**: `put_mappings` merged `mappings` into `Connection.config` while
   `update_connection` merged the body's keys into the same column, keeping a stored secret where
   the form sent it blank. One admin saving connection settings while another saved field mappings
   lost a write. Both routes now take the **same** per-connection advisory lock —
   `pid_lock.mutating(_lock_key(cid))`, spanning each route's refresh, merge and commit — and the key
   is built by a shared helper rather than an f-string at each call site, because *a lock one side
   does not take protects nothing*, which is what the `dev_property` pair cost to learn. The lock
   rather than a compare-and-swap because the two edits are claims on **different keys** of one blob:
   serialising lets both survive, where a 409 would refuse an edit that conflicts with nothing.
   `test_connection_lock.py` asserts both survive, and that locking on two *different* keys reds it
   while leaving the static sweep green — *static analysis can see that a lock is present; only
   behaviour can see that it is the SAME lock.* (`proforma.put_property` was one of the original six and is now
   **closed** under the per-project lock — see the `dev_property` note in the concurrent-edit row
   above. `bim.promote_markup` was another and is **closed** too: it claimed the back-link with a
   plain assignment after a `topic_id` check, so two concurrent promotes minted two RFI Topics for
   one markup and orphaned the first, and it now uses the conditional UPDATE
   `modules.promote_comment` had been given one module over. *An already-solved defect living on
   elsewhere is the cheapest kind to close and the easiest to never look for.*) Each reads a column and writes back a value derived from it on a
   table that carries no `modified_at`, so the register row's compare-and-swap is unavailable
   exactly as in G-10. Surfaced by widening `services/api/test_rmw_sweep.py`'s ORM derivation to
   propagate taint through one local — before that, hoisting a read into a variable removed a site
   from the inventory. Frozen in that gate's ledger with a structured status, so a new instance reds
   the build. The three that remain are deliberately **not** ranked here. The first draft of this
   sentence ranked them and was wrong on the facts within a minute of being written — it called
   `drawingset.revise_sheet` a lost *sheet revision* with a single writer, when the read-modify-write
   is actually `m.data = d2` on each **markup** it tags `carried_from`, a blob the markup save and
   bulk-replace routes also write. *A priority claim is a factual claim about blast radius, and this
   file has now carried two wrong ones about this same list.* Rank them by reading the sites.

<!-- fixture ends -->
