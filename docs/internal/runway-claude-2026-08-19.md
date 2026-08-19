# Runway for Claude Code — 2026-08-19, after v0.3.988 / open 987 PRs

**Grade: live handoff + decision brief.** Written so the next session (Claude Opus 5 / Claude Code)
picks up from measured state rather than from chat memory. It is **not** the work list —
[`docs/roadmap.md`](../roadmap.md) still is. Security *controls* live in
[`docs/security/threat-model.md`](../security/threat-model.md); the security *queue* is
[`security-roadmap.md`](security-roadmap.md). The 2026-08-19 upgrade audit on #292 remains useful
background; this file is what is true **after** the cloud-agent pass that produced PRs 292–296 and
the stacked 989 work in this PR.

**Method.** Read the standing directions, the open PR set, `requirements.lock` pins, CodeQL (token
403 — do not treat as zero alerts), Starlette/FastAPI/diskcache upstream, and the GET+commit
population in `aec_api` (now a gate).

---

## Land order — do this first, then write code

`origin/main` is still **v0.3.986** (`a67c4732`) until you merge. Three PRs all claim **v0.3.987**.
A fourth is **v0.3.988**. This runway is **v0.3.989**, stacked on 988.

| Order | PR | Branch | What |
|---:|---|---|---|
| 1 | [#294](https://github.com/ibuilder/massing/pull/294) | `cursor/lib-perf-sec-6e15` | Pin `pdfjs-dist` 6.2.108; `enableScripting: false` on both `getDocument` sites |
| 2 | [#292](https://github.com/ibuilder/massing/pull/292) | `cursor/upgrade-audit-plan-6e15` | CC0 in the written licence rule + upgrade brief |
| 3 | [#295](https://github.com/ibuilder/massing/pull/295) | `cursor/ux-debug-reach-6e15` | Honest empty canvas, Place `waitForPublish` ticks, Analyse destination names, element cards |
| 4 | [#296](https://github.com/ibuilder/massing/pull/296) | `cursor/readiness-diskcache-6e15` | Readiness strip on every home; bake-share `JSONDisk` |
| 5 | this PR | `cursor/runway-claude-6e15` | Server-side brief scope, cache dir 0700, GET+commit ratchet, this file |

After each merge: rebase the remainder, **keep the version the later PR already took** (987 then 988
then 989). Do not let three 987s collide. Do not tag onto a red or pending `main`
(`.claude/skills/ship-release`).

**Live pass still owed on #295.** Unit tests passed; the cloud image had no API venv. Drive: empty
canvas status (`NO_MODEL_STATUS` in `apps/web/src/viewer/loadProjectModel.ts`), Place convert ticks,
RFI / estimate / pay-app / asset cards. Geometry Place still needs a published model.

---

## What is already decided — do not re-open

- Binding constraint is **adoption / feel**, not missing modules. No second big-ticket (CMMS,
  photo-pin, field-PWA) until spine, element-card reach, field mode, and authoring round-trip move.
- No React, no Reflex (`docs/internal/plan-2026-08-10.md`).
- No new npm/PyPI packages without operator OK. Licence MIT/BSD/Apache/ISC/CC0. No GPL/AGPL.
- Python lock only via `.github/workflows/lockfile.yml` (`pip-compile` in python:3.12-slim). Never
  hand-edit hashes on a laptop.
- IFC GlobalId identity; Fragments in the browser; recipes on the server.
- Do **not** invent proforma GUID provenance in the client (`R24-TRACE-UI ②` is backend-first).
- Do **not** grow `apps/web/src/viewer/app.ts` or `apps/web/src/api/client.ts` without extracting
  first (`test_file_sizes.py` pins, often zero headroom).
- Do **not** turn `AEC_BAKE_SHARE_DIR` on by default. Do **not** add `mapped-diskcache`.
- MassingViewer swap waits on npm; keep shipping here behind existing seams.

**Operator still owns (engineering cannot close):** SEC-BRANCH (required checks / `enforce_admins`);
hosted vs on-prem defaults (`AEC_WEBHOOK_ALLOW_PRIVATE`, split `AEC_AUTH_SECRET`, compose memory
limits); seven-room vs workspace fossils; grey identity; element vs component and estimate vs budget
vs cost (`R24-TERMS`); zero vs one big-ticket.

CC0 is settled on #292. The 08-10 plan still lists it as open — ignore that bullet.

---

## What this cloud pass already shipped (do not redo)

1. **Licence writing matches the classifier** (#292) — CC0 was already accepted in Python on
   2026-08-10; the directions and the open-decision bullet had not followed.
2. **pdf.js** (#294) — 6.2.108 + scripting off. That is the XSS class for in-app PDFs.
3. **Reach, not new engines** (#295) — empty canvas tells the truth; Place shows convert ticks;
   Analyse labels say the job; element cards on four more surfaces.
4. **Readiness on every home** (#296) — `apps/web/src/portal/panels/readinessStrip.ts`. Fail-open.
   Pulse sits under the strip.
5. **Bake-share is JSON when on** (#296) — `diskcache.JSONDisk` in `services/data/src/aec_data/bake_shared.py`.
   Still off unless the env dir is set. Upstream still has **no published 5.6.4**; HMAC-pickle PRs
   exist (`grantjenks/python-diskcache` #361 / #364) and a mapped fork — we did not take the fork.
6. **This PR (989–991)** — scope maps; GET+commit ratchet; Starlette 1.6.0; Pulse GET; persona order.

---

## Libraries — current pins, what to bump, what not to

Checked 2026-08-19 against PyPI / advisories (not against a working CodeQL token).

| Package | Lock / pin | Take? |
|---|---|---|
| FastAPI | `0.141.1` | **No.** That is the current stable (2026-07-29). |
| Starlette | was 1.3.1; **1.6.0 in v0.3.990** | Taken. FileResponse Range + `max_body_size`. Recompile only via lockfile.yml if this lock is later edited. |
| pypdf / cryptography | 6.15.0 / 50.0.0 | Already the CVE floors. Leave. |
| diskcache | 5.6.3 | **No bump** (no fix on PyPI). JSONDisk + 0700 + off-by-default. Re-review if 5.6.4 publishes. |
| boto3 | lock 1.43.46; dependabot wants `>=1.43.68` (#288) | Routine lock regen. Not a feature. |
| numpy / trimesh | data `requirements.txt` vs lock | **Do not take trimesh 5** until booleans/sections are revalidated (`test_sections.py`). numpy 2.5.2 is a patch; lockfile workflow. |
| three / @thatopen | pinned pair | `ties.test.ts`. Never bump one without the other. |
| pdfjs-dist | 6.2.108 on #294 | After that lands, leave. |

`scripts/audit_lock_gate.py` already fails CI on **fixable** lock advisories. A green local machine
without `pip-audit` is not a green lock.

---

## More Python, less frontend — the next reversible slices

The 08-10 measurement still holds: ~13k LOC of portal/proforma is thin over JSON and is the
server-composed-HTML candidate. R43-CRUD-FRAGMENTS said converting one register converts all —
**do not** start with the generic renderer.

Take slices that already have a seam:

1. **Done in 989/991:** readiness scope and persona-weighted pill order (engineer on Design:
   design → regulatory → place) as a server `keys` list. The strip renders `brief.scope.keys`.
2. **Done in 991:** `GET /projects/{id}/pulse` returns `PulseInput`. Mapping is
   `project_pulse.py`; the shell only calls `projectPulse`. Fail-open stays. Do not put charts in HTML yet.
3. **Empty-register copy** — `empty.ts` already distinguishes none / filtered / failed. Curated
   hints can move to `module.json` / a server hint table so Lane B is not editing copy in TS.
4. **Do not** server-render the 3D viewer, Draft, or sheet canvas.

Authoring feel is still the expensive performance problem: every Place republishes the whole
`.frag`. Incremental reload is the right design and a large one — not a drive-by in this PR.

---

## Security leftovers that are real work

- **SEC-BRANCH** — operator. Required status checks on `main` would have caught the red-main + tag
  incidents. Do not fake this in code.
- **SEC-G1** — no secret scanning in CI. `test_no_secrets.py` is grep. Add gitleaks (or MIT
  equivalent) to `security.yml` when a licence-clean scanner is chosen.
- **GET + commit** — two sites, now ratcheted: OAuth callback (must stay GET) and CAM statement PDF
  (should become POST + blob download). SameSite=Lax does not protect top-level GET.
- **CodeQL alerts API** — 403 on the cloud token. Re-query from an account that can read
  code scanning after push. A green CodeQL *run* is not zero alerts.
- **Hosted overlay** — `AEC_WEBHOOK_ALLOW_PRIVATE=0` in any multi-tenant deploy; fail CI if that
  overlay is missing. Keep `1` for on-prem.

---

## Tests you should run, and the ones this image could not

From `services/api`:

```
python -m ruff check src/ ../data/src/
PYTHONPATH=src:../data/src python test_master_builder_scope.py
PYTHONPATH=src:../data/src python test_get_commits.py
PYTHONPATH=src:../data/src python test_bake_shared.py
PYTHONPATH=src:../data/src python test_claude_md_gates.py
```

`test_master_builder.py` needs FastAPI / the API venv (full brief + scoped route). This cloud image
did not have that venv.

Web (Node **24**, not whatever is first on PATH):

```
cd apps/web && npm run typecheck && npm run lint && npx vitest run src/portal/panels/readinessStrip.test.ts && npm run build
```

---

## UX recommendations (ranked, not a rewrite)

These are product calls with engineering already half-done. Prefer shipping reach over new chrome.

1. **One nav in the user's head.** Rooms only. **UX-DUP-DESTINATIONS shipped v0.3.994** — one Analyse
   home, three named tasks. Do not add a fourth engine. **Schedule room brief shipped v0.3.995**
   (R36-ROOM-BRIEFS, Schedule only).
2. **Close the first gap is now on every home.** A brief that 500s shows "Readiness unavailable"
   (**v0.3.991**) rather than a blank. Pulse's fail-open rule still holds for the rail.
3. **Authoring wait is the feel problem.** Optimistic local mesh + job-tray "saving…" until
   incremental fragments exist. Status bar is ~220 px — pair toast + request id.
4. **Print paper is a picker, default ARCH C (24×18 in)** (**v0.3.993**). Not an ISO A size.
   ARCH-D is full-size; ARCH-B half of D; ARCH-A the next step (often called quarter of D).
   Unknown `page` is refused. Live PDF still needs a source IFC.
5. **Density on registers** (`R24-DENSITY ②`), not only dashboards — where an 8-hour GC lives.
6. **Field mode as a mode**, not a breakpoint. Superintendent should not see the BIM rail.
7. **Catalog ★ keyboard focus** — cheapest a11y win still open.
8. **Do not** squeeze Design onto a phone. Field capture + PWA meta exist; the BIM shell is not a
   phone product.

---

## Explicitly out of scope for the next session unless the operator says otherwise

Starlette 1.6 lock regen is in scope (library hygiene). Routing clash/IDS through the job queue
(R24-RUNS-INBOX open half), growing `app.ts`, new UI frameworks, inventing IRR←GUID in the client,
and merging without rebase are not.
