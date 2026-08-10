# Dependency advisories carried knowingly

Internal. The repo is public; this file records reasoning, not exposure detail.

Every advisory in `services/api/requirements.lock` that has a **published fix** is blocked in CI by
`scripts/audit_lock_gate.py` and must be answered with a version floor. This file is only for the
other kind: an advisory with **no fix available**, where a version bump is not an option and the
decision is to carry it, replace the package, or vendor around it.

An entry here is a decision with a re-review date, not a dismissal.

---

## `diskcache` 5.6.3 — CVE-2025-69872 / PYSEC-2026-2447 — MODERATE — **carried**

*Recorded 2026-08-09. Re-review 2026-11-09, or immediately if a fixed release appears.*

**The advisory.** diskcache deserializes cached values with `pickle`. Anything that can write into
the cache directory can therefore run code in the process that next reads it. No fix is published;
the behaviour is intrinsic to the design rather than a bug with a patch waiting.

**Why it is carried rather than removed.** The threat it describes is *write access to our own cache
directory*. An attacker who has that already has filesystem write access as the service user inside
the container, which is a strictly larger capability than the one this advisory grants — they could
replace the application code. The advisory raises no privilege we do not already lose in the state it
presumes. Its own CVSS vector agrees: local, low privileges required, and **user interaction
required**.

There is a stronger fact than that argument, and it is the one that actually settles it: **the shared
cache is off unless an operator turns it on.** `bake_shared.enabled()` is `bool(os.environ.get(
"AEC_BAKE_SHARE_DIR"))`, and `_store()` returns `None` when that variable is unset — so in a default
deployment `diskcache.Cache` is never constructed and nothing is ever unpickled. The directory, when
it exists, comes from that environment variable alone; no request, header, or stored record
influences it, and an environment variable is operator-supplied by definition.

Two corrections to what a first pass wanted to write here, both worth keeping as a warning about
which facts get assumed:

- *"the cache lives under a read-only container's writable tmp mount"* — **not in evidence.** No
  tracked deploy file (`docker-compose.yml`, `docker-compose.prod.yml`, either `Dockerfile`) sets
  `read_only`, `tmpfs`, or `readOnlyRootFilesystem`. The claim came from a remembered practice, not
  from this repo, and it was checked only because a doc citation next to it turned out not to exist.
  A container hardening pass is worth doing; it is not something to cite as though already done.
- the CVSS vector's "user interaction required" reads as a mitigation and is not one worth leaning
  on — reading a cache entry *is* the interaction, and the service does that on its own.

**Why not just drop it.** It is the cross-process geometry cache. Under gunicorn with N workers, a
plain in-process dict tessellates the same model N times; diskcache is a lock-correct SQLite-backed
store, and the locking is the part that is genuinely hard to write correctly. Replacing it means
either writing that lock or adding a service dependency (Redis) to a path that must work offline —
the viewer running fully offline is a non-negotiable.

**What would change the decision.** A published fix (take it immediately — the gate will start
demanding it on its own, which is the intended behaviour). Or any change that lets the cache
directory be influenced by a request rather than by the environment, which would move this from
"presumes a larger compromise" to "is the compromise". Or the shared cache becoming on-by-default,
which would remove the fact this entry mostly rests on.

**Follow-up worth doing separately:** run the containers with a read-only root filesystem and an
explicit writable mount. Not a response to this advisory — it is ordinary hardening that nothing in
this repo currently does, discovered while checking a claim made about it.

---

## Adding an entry

State: the advisory and its severity, why no version answers it, what makes the exposure smaller than
it reads (with the assumptions named separately, so they can be re-checked rather than trusted), what
replacing the dependency would cost, and what evidence would reverse the call. A date and a
re-review date, always.

If the advisory *does* have a fix and you are reaching for this file, you are in the wrong place —
raise the floor in `services/api/requirements.in` and regenerate the lock. `EXEMPT` in the gate
handles the narrow case where a fix exists but taking it is a major migration, and every entry there
expires.
