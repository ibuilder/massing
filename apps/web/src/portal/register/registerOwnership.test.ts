import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * The register renderer lives here, and the shell reaches it through a named few doors.
 *
 * **What this protects, and why prose could not.** `docs/roadmap.md`'s lane table hands
 * `apps/web/src/portal/portal.ts` to Lane A · Shell & IA and `apps/web/src/portal/register/` to
 * Lane B · UI & panels. `shell/roadmapLanes.test.ts` proves those two paths are disjoint — but path
 * disjointness was never the problem. Until v0.3.850 both jobs sat in `portal.ts`, the paths were
 * perfectly disjoint, and *every* register item still had to edit a Lane A file to do Lane B work:
 * `R36-EMPTY-STATE` shipped that way and missed a collision by luck, `R24-MONO-DATA` gave up and
 * wrote the reason into `ui/monoData.test.ts`, `R24-DENSITY` is pointed at the same wall.
 *
 * So the lane check cannot be the gate here. It can only see where a file *is*; this sees what is
 * *in* it. If register rendering grows back into `portal.ts` the table goes on reading correct and
 * the collision returns — silently, and only for whoever is next to claim Lane B.
 *
 * **The population is the moved code, named.** These are the register renderer's own internals, not
 * its entry points: none of them is something the shell has any reason to mention. Their presence in
 * `portal.ts` therefore means the split is being undone, and their presence *here* is what stops
 * this file passing because it looked for names nobody uses any more (asserted below — a matcher
 * that finds nothing agrees with everything).
 */

// process.cwd() is apps/web under vitest — see the note in docs/roadmap-directions.md §5 about
// import.meta.url having no `file:` scheme in this environment.
const SRC = resolve(process.cwd(), "src");

/**
 * Comments stripped, because this asks what the code does and a comment is not code.
 *
 * Not a nicety — the first run of the door check below failed on the sentence four lines above the
 * doors explaining what a door is, which happened to contain `this.reg.x(...)`. A gate that forbids
 * *describing* the rule it enforces teaches people to stop writing the description, and this repo's
 * expensive lessons all live in comments. `//` is only treated as a comment when it does not follow
 * a `:`, so a `https://` in a link survives.
 */
const code = (src: string) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const SHELL = code(readFileSync(resolve(SRC, "portal/portal.ts"), "utf8"));
const REGISTER = readFileSync(resolve(SRC, "portal/register/register.ts"), "utf8");

/** Register-renderer internals. Entry points (`openModule`, `openRecord`, …) are deliberately absent
 *  — the shell calls those, so their name appearing in `portal.ts` is correct, not a regression. */
const INTERNALS = [
  "inlineCell", "inlineRefCell", "tableEditor", "filterRow", "filterableFields", "serverSortField",
  "refCell", "fmtCell", "assigneeCell", "statusCell", "ballCell", "ballInCourt", "columnPicker",
  "readColPrefs", "pasteRows", "renderImport", "renderForm", "renderBoard", "workflowMap",
  "contractActions", "composeExhibit", "signContract", "rfiTriage", "openPermitImport",
  "renderRelated", "renderAttachments", "queueUpload", "signaturePad",
  "REF_RESOLVE_LIMIT", "UUID_RE", "EDITABLE_FIELD_TYPES", "CONTRACT_DOCS",
];

/**
 * Every member of the register the shell is allowed to touch, with the reason it needs to.
 *
 * This is the half that rots quietly. A boundary holds for as long as crossing it stays annoying,
 * and `this.reg.` is not annoying at all — the next person who wants one more thing from in here
 * will simply take it, and the file split will still look intact. So the doors are enumerated: a
 * fifth one is a decision somebody has to write down, not a character somebody types.
 */
const DOORS = new Set([
  "openModule",    // a register link on the dashboard, and the command palette's openModuleByKey
  "openRecord",    // a record link on the dashboard (approvals, notifications, activity)
  "openByBrief",   // the same, by module key + id (the palette's openRecordByKey)
  "sort",          // a saved-view link sets the sort before opening the register
  "hookOnline",    // init() drains the offline upload queue…
  "flushUploads",  // …which belongs to the record attachment path, so it lives in the register
]);

describe("the register renderer is not in the portal shell", () => {
  it("the matcher looks for names that actually exist — else it agrees with everything", () => {
    // The vacuous-pass guard this repo keeps needing. If the register is refactored and these names
    // change, this fails HERE, pointing at the list, rather than passing an empty search below.
    const missing = INTERNALS.filter((n) => !REGISTER.includes(n));
    expect(missing, `named in this test but no longer in register.ts: ${missing.join(", ")}`).toEqual([]);
  });

  it("portal.ts mentions none of the register's internals", () => {
    const leaked = INTERNALS.filter((n) => new RegExp(`\\b${n}\\b`).test(SHELL));
    expect(leaked,
      `register-renderer internals are back in portal.ts: ${leaked.join(", ")}\n`
      + "portal.ts is Lane A · Shell & IA and portal/register/ is Lane B · UI & panels. Register "
      + "work in portal.ts puts two sessions in one file, which is what the v0.3.850 split removed.")
      .toEqual([]);
  });

  it("the shell reaches the register only through the enumerated doors", () => {
    const used = new Set([...SHELL.matchAll(/this\.reg\.(\w+)/g)].map((m) => m[1]!));
    expect(used.size, "portal.ts no longer talks to the register at all — this test is measuring nothing")
      .toBeGreaterThan(0);
    const extra = [...used].filter((m) => !DOORS.has(m));
    expect(extra,
      `the shell took a new door into the register: ${extra.join(", ")}\n`
      + "Widening this seam is how the two jobs grew together the first time. Either add it to DOORS "
      + "with the reason, or move the caller into portal/register/.")
      .toEqual([]);
  });
});
