# Runway for Claude Code — 2026-08-19, after v0.3.1001

**Grade: live handoff.** Written so the next session picks up from measured state rather than chat
memory. It is **not** the work list — [`docs/roadmap.md`](../roadmap.md) still is. Security
*controls*: [`docs/security/threat-model.md`](../security/threat-model.md). Security *queue*:
[`security-roadmap.md`](security-roadmap.md).

---

## Land order — do this first, then write code

`origin/main` was **v0.3.986** when this stack started. Three PRs still claim **v0.3.987**. This
branch is **v0.3.988–1001**.

| Order | PR | Branch | What |
|---:|---|---|---|
| 1 | [#294](https://github.com/ibuilder/massing/pull/294) | `cursor/lib-perf-sec-6e15` | pdfjs 6.2.108; `enableScripting: false` |
| 2 | [#292](https://github.com/ibuilder/massing/pull/292) | `cursor/upgrade-audit-plan-6e15` | CC0 in the written licence rule |
| 3 | [#295](https://github.com/ibuilder/massing/pull/295) | `cursor/ux-debug-reach-6e15` | Empty canvas, Place ticks, Analyse names |
| 4 | close | [#296](https://github.com/ibuilder/massing/pull/296) | Superseded by this PR (readiness + JSONDisk) |
| 5 | this | `cursor/runway-claude-6e15` | **988–1001** (table below) |

After each merge: rebase the remainder, **keep the later version numbers**. Do not tag onto a red or
pending `main` (`.claude/skills/ship-release`). This agent cannot merge.

**Live pass still owed on #295** if it has not landed with a driven empty-canvas / Place tick check.

---

## What this PR already shipped — do not redo

| Ver | What |
|---|---|
| 988 | Readiness strip on every home; bake-share `JSONDisk` (off by default) |
| 989 | Brief scope server-side; cache dir 0700; GET+commit ratchet |
| 990 | Starlette 1.6.0 |
| 991 | `GET /projects/{id}/pulse`; persona pill order; "Readiness unavailable" |
| 992 | Issue / Sheet PDF sends `page=A1` |
| 993 | Paper picker. Default **ARCH C (24×18 in)**. Unknown `page` is 422 |
| 994 | One Analyse home, three named tasks. Not a fourth engine |
| 995 | Schedule room brief: lookahead, blockers, variance |
| 996 | Density Field 56 / Comfortable 36 / Compact 28 on registers; catalog ★ focus ring |
| 997 | CAM statement PDF is **POST** + blob download. OAuth callback is the only GET+commit |
| 998 | Deal room brief: returns vs band, open diligence, next protocol gate |
| 999 | Cost / Planning / Operate room briefs. Shared `roomBriefChrome.ts`. R36 complete except Design |
| 1000 | Element card on every tied register record (`tiedElements.ts`). R24-ELEMENT-CARD ② shipped |
| 1001 | R24-FIELD-MODE ① — mode flag, 56 px field chrome, always-visible sync strip, dictation |

---

## What is already decided — do not re-open

- Binding constraint is **adoption / feel**, not missing modules. No second big-ticket (CMMS,
  photo-pin, field-PWA) until field mode and authoring round-trip move. **Element-card reach shipped
  v0.3.1000.** Field-mode slice ① shipped **v0.3.1001**. Spine rooms already exist.
- No React, no Reflex. No new npm/PyPI packages without operator OK. Licence MIT/BSD/Apache/ISC/CC0.
- Python lock only via `.github/workflows/lockfile.yml`. Never hand-edit hashes.
- IFC GlobalId identity; Fragments in the browser; recipes on the server.
- Do **not** invent proforma GUID provenance in the client.
- Do **not** grow `apps/web/src/viewer/app.ts` or `apps/web/src/api/client.ts` without extracting
  first. `client.ts` pin is **3,672**. `register.ts` pin is **2,516** (`test_file_sizes.py`).
- Do **not** turn `AEC_BAKE_SHARE_DIR` on by default. Do **not** add `mapped-diskcache`. Do **not**
  take trimesh 5 until `test_sections.py` is revalidated.
- MassingViewer swap waits on npm; keep shipping here behind existing seams.
- Design room brief: **do not add one** while Design home is null (the viewer is the home).
- There is **no `pay_app` module** (emptyGuide already recorded this — it is `owner_invoice` / SOV).
  There is **no COBie worksheet UI** — Component.ExtIdentifier lives in the xlsx export; the in-app
  row is `asset_register`. Do not invent a cobie register to "finish" a shipped item.

**Operator still owns:** SEC-BRANCH; hosted vs on-prem defaults; seven-room vs workspace fossils;
grey identity; R24-TERMS; zero vs one big-ticket.

---

## Next slices that already have a seam (prefer these)

1. **R36 and R24-ELEMENT-CARD ② and FIELD-MODE ① are done.** Do not redo them.
2. **Empty-register copy** — `emptyGuide.ts` is still a TS table. Moving `what`/`from` onto
   `module.json` is Lane H + B together; do not start it as a drive-by in one lane.
3. **R24-FIELD-MODE remainder** — capture-first home. Not a second density control, not Lane J CSS.
4. **R24-CHARTS-GRAMMAR** series-colour (the rest of that item), not a new chart kind.
5. **Authoring wait** — optimistic local mesh + job-tray until incremental `.frag`. Large; not a
   drive-by.

---

## Security leftovers that are still real

- **SEC-BRANCH** — operator. Required status checks on `main`.
- **SEC-G1** — no secret scanning in CI. `test_no_secrets.py` is grep.
- **CodeQL alerts API** — 403 on the cloud token. A green CodeQL *run* is not zero alerts.
- **Hosted overlay** — `AEC_WEBHOOK_ALLOW_PRIVATE=0` in any multi-tenant deploy.

---

## Tests

From `services/api` (no pytest; `PYTHONPATH=src:../data/src`):

```
python3 test_file_sizes.py
python3 test_claude_md_gates.py
```

Web (Node **24**):

```
cd apps/web && npm run typecheck && npm run lint && npm run build
npx vitest run src/field/fieldMode.test.ts src/field/dictate.test.ts src/field/fieldQueue.test.ts \
  src/shell/roadmapLanes.test.ts src/shell/versionConsistency.test.ts
```

---

## Explicitly out of scope unless the operator says otherwise

Growing `app.ts` / `client.ts` / `register.ts`, merging without rebase, unifying Analyse dests (done),
enabling bake-share by default, a Design-room brief, a COBie worksheet UI, React/Reflex.
