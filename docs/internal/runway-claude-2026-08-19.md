# Runway for Claude Code — 2026-08-19, after v0.3.1010

**Grade: live handoff.** Written so the next session picks up from measured state rather than chat
memory. It is **not** the work list — [`docs/roadmap.md`](../roadmap.md) still is. Security
*controls*: [`docs/security/threat-model.md`](../security/threat-model.md). Security *queue*:
[`security-roadmap.md`](security-roadmap.md).

---

## Land order — do this first, then write code

`origin/main` was **v0.3.986** when this stack started. Three PRs still claim **v0.3.987**. Then:

| Order | PR | Branch | What |
|---:|---|---|---|
| 1 | [#294](https://github.com/ibuilder/massing/pull/294) | `cursor/lib-perf-sec-6e15` | pdfjs 6.2.108; `enableScripting: false` |
| 2 | [#292](https://github.com/ibuilder/massing/pull/292) | `cursor/upgrade-audit-plan-6e15` | CC0 in the written licence rule |
| 3 | [#295](https://github.com/ibuilder/massing/pull/295) | `cursor/ux-debug-reach-6e15` | Empty canvas, Place ticks, Analyse names |
| 4 | close | [#296](https://github.com/ibuilder/massing/pull/296) | Superseded |
| 5 | [#297](https://github.com/ibuilder/massing/pull/297) | `cursor/runway-claude-6e15` | **988–1001** vs `main` |
| 6 | [#298](https://github.com/ibuilder/massing/pull/298) | `cursor/charts-series-colour-6e15` | **1002** vs #297 |
| 7 | [#299](https://github.com/ibuilder/massing/pull/299) | `cursor/mono-data-token-6e15` | **1003** vs #298 |
| 8 | [#300](https://github.com/ibuilder/massing/pull/300) | `cursor/field-mode-chrome-6e15` | **1004** vs #299 |
| 9 | [#301](https://github.com/ibuilder/massing/pull/301) | `cursor/cite-highlight-6e15` | **1005** vs #300 |
| 10 | [#302](https://github.com/ibuilder/massing/pull/302) | `cursor/field-capture-home-6e15` | **1006** vs #301 |
| 11 | [#303](https://github.com/ibuilder/massing/pull/303) | `cursor/a11y-journeys-6e15` | **1007** vs #302 |
| 12 | [#304](https://github.com/ibuilder/massing/pull/304) | `cursor/field-hide-spine-6e15` | **1008** vs #303 |
| 13 | [#305](https://github.com/ibuilder/massing/pull/305) | `cursor/weekly-gantt-6e15` | **1009** vs #304 |
| 14 | this | `cursor/symbol-count-6e15` | **1010** vs #305 |

After each merge: rebase the remainder, **keep the later version numbers**. Do not tag onto a red or
pending `main`. This agent cannot merge.

**Live pass still owed on #295** if it has not landed with a driven empty-canvas / Place tick check.

---

## What already shipped on this stack — do not redo

| Ver | What |
|---|---|
| 988–1000 | Readiness, pulse, paper, Analyse, room briefs, element-card reach (see #297) |
| 1001 | R24-FIELD-MODE ① — mode, strip, dictation (inline FAB still 52 px; strip could sit under it) |
| 1002 | R24-CHARTS-GRAMMAR closed — series vs status |
| 1003 | R24-MONO-DATA closed — paste textarea uses `var(--mono)`; allowance 0 |
| 1004 | R24-FIELD-MODE ② — field CSS beats FAB inline size/position; strip `aria-live` |
| 1005 | R31-CITE-HIGHLIGHT closed — in-app viewer + PageWords box |
| 1006 | R24-FIELD-MODE ③ — capture sheet lands when field mode + project |
| 1007 | R39-A11Y-JOURNEYS ② closed — Tab to `[data-room-primary]` (Design tab for Design) |
| 1008 | R24-FIELD-MODE ④ — hide `#workspaces` while field mode is on |
| 1009 | UX-GANTT closed — weekly hybrid on the Schedule room |
| 1010 | R23-SYMBOL-COUNT ① — NCC + NMS matcher (`ui/symbolCount.ts`); takeoff wiring open |

---

## What is already decided — do not re-open

- Binding constraint is **adoption / feel**, not missing modules. No second big-ticket.
- No React, no Reflex. No new npm/PyPI packages without operator OK. Licence MIT/BSD/Apache/ISC/CC0.
- Do **not** grow `apps/web/src/viewer/app.ts` or `apps/web/src/api/client.ts` without extracting
  first. Pins: `client.ts` **3,672**, `app.ts` **3,032**, `register.ts` **2,516**.
- Do **not** turn `AEC_BAKE_SHARE_DIR` on by default. Do **not** add `mapped-diskcache`.
- Design room brief: **do not add one** (`ROOM_HOME.design` is null).
- There is **no `pay_app` module** and **no COBie worksheet UI**.
- Empty-register copy (`emptyGuide.ts` → `module.json`) is Lane H + B together.

**Operator still owns:** SEC-BRANCH; hosted vs on-prem defaults; R24-TERMS remaining pairs;
PERSONA-SHAPE; IDENTITY.

---

## Next slices

1. **R24-FIELD-MODE remainder** — replacing the portal home (Lane A). ④ only hides the room tabs.
2. **R24-REPORTS-BY-MOMENT** scheduling (needs a job kind + delivery; larger).
3. Lane B still open: `R24-TERMS` (user decision), `R22-REPORT-BUILDER` (aggregation/share is backend),
   `R23-SYMBOL-COUNT` takeoff wiring, `R38-SHEET-MARKUP ③` (generated sheets + GUID pins).

---

## Security leftovers that are still real

- **SEC-BRANCH** — operator. Required status checks on `main`.
- **SEC-G1** — no secret scanning in CI. `test_no_secrets.py` is grep.
- **CodeQL alerts API** — 403 on the cloud token. A green CodeQL *run* is not zero alerts.
- **Hosted overlay** — `AEC_WEBHOOK_ALLOW_PRIVATE=0` in any multi-tenant deploy.

---

## Tests

```
cd apps/web && npm run typecheck && npm run lint
npx vitest run src/ui/a11yJourney.test.ts src/portal/panels/planningBrief.test.ts \
  src/portal/panels/costBrief.test.ts src/portal/panels/scheduleBrief.test.ts \
  src/portal/panels/dealBrief.test.ts src/portal/panels/operateBrief.test.ts \
  src/shell/roadmapLanes.test.ts src/shell/versionConsistency.test.ts
cd ../services/api && PYTHONPATH=src:../data/src python3 test_file_sizes.py && python3 test_claude_md_gates.py
```

---

## Explicitly out of scope unless the operator says otherwise

Growing `app.ts` / `client.ts` / `register.ts`, merging without rebase, enabling bake-share by
default, a Design-room brief, a COBie worksheet UI, React/Reflex.
