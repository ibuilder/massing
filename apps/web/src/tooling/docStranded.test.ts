import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * DOC-STRAND — no doc comment in `apps/web/src` has lost the declaration it describes.
 *
 * ## The shape
 *
 * A `/** … *\/` block immediately followed by another one has no declaration of its own: whatever it
 * documented moved, was renamed, or had something inserted between them. The comment does not
 * disappear — it attaches itself visually to the *next* declaration down and is then read as
 * documenting that. **A comment about a declaration that is not there is not documentation; it is a
 * false statement positioned where the next reader will trust it.**
 *
 * `api/docComments.test.ts` has enforced exactly this since v0.3.1075, over `apps/web/src/api` only.
 * That scoping was deliberate and argued in writing: widening it "would need a rule that can tell a
 * header and a narrative from a leftover, and that rule does not exist yet". This is that widening,
 * and it is possible because **one of the two shapes the scoping rested on did not survive being
 * checked.**
 *
 * ## The two shapes, re-measured
 *
 * **A module header written below the import block is real — and it needs no exemption, because it
 * is structural.** `portal/panels/budget.ts` opens with five imports and then the file's own header,
 * followed by the first declaration's comment. Nothing but imports stands above it, and that is a
 * property this gate can compute (`isFileHeader`). It is the only site in the tree with that shape.
 *
 * **The "context block above the thing it motivates" did NOT survive.** That claim named
 * `viewer/app.ts` and `main.ts`. `main.ts` has no stranded comment at all. And the `viewer/app.ts`
 * block reads as deliberate narrative but is not: it documented `distributeToolGroups`, declared
 * **42 lines further down**, past `railGroup` and past `railGroup`'s own comment. It was residue of
 * exactly the kind this gate catches, classified as intentional prose by reading it rather than by
 * looking for its owner.
 *
 * *A gate's scope is part of its claim — and so is the reason given for not widening it.* That
 * reason was two examples: one stale, one a misreading. Neither was wrong when written in the sense
 * of careless; both were **assertions about the tree that nothing re-ran**, which is the same defect
 * one level out from the one this file gates.
 *
 * ## What the nine were, and why every one was a MOVE
 *
 * Nine sites, each with a verifiable owner, and not one a delete:
 *
 *     dev/liveAudit.ts        -> auditRooms            (NAV_SEL was inserted between them)
 *     drawings/drawings.ts    -> showMarkupGrid        (86 lines down)
 *     portal/portal.ts        -> renderBudget          (renderPortfolio sat between)
 *     portal/register/…       -> RegisterFilter        (53 lines down)
 *     portal/register/…       -> composeExhibit        (232 lines down)
 *     proforma/proforma.ts    -> renderBudget          (97 lines down)
 *     proforma/proforma.ts    -> refreshDealMemory     (refreshIncomeBasis sat between)
 *     ui/perfBeacon.ts        -> installClickEcho      (cappedSender sat between)
 *     viewer/app.ts           -> distributeToolGroups  (railGroup sat between)
 *
 * **That is the opposite of what the `api/` cleanup found**, where most stranded comments described
 * features with no method left in the file to own them and were deleted. The difference is not
 * chance: `api/client.ts` was the file the methods were moving *out of*, so its residue was
 * abandoned. These are feature modules that only ever had things inserted into them, so their
 * residue is *separated* — the owner is still a few dozen lines away, undocumented.
 *
 * Every one of the nine owners had **no doc comment of its own**, so nothing was a duplicate to
 * reconcile and nothing was lost. Nine functions that were silently undocumented got their
 * documentation back, and nine declarations stopped carrying a description of something else.
 *
 * ## Why this is the whole tree while `docComments.test.ts` stays inside `api/`
 *
 * The *stranded* rule needs no understanding of prose — it is a shape, and its one false-positive
 * shape is structural. The *pairing* rule next door (does this comment share a word with the method
 * below it?) is the half that cannot be widened, because outside `api/` a comment legitimately
 * describes a paragraph of behaviour rather than one method. **Two rules that shipped together do
 * not have to keep the same scope**, and assuming they did is what kept this half narrow for a
 * month after its blocker stopped being true.
 */

const ROOT = resolve(process.cwd(), "..", "..");

const FILES = execFileSync("git", ["ls-files", "apps/web/src/**/*.ts", "apps/web/src/**/*.tsx"],
  { cwd: ROOT, encoding: "utf8" })
  .split("\n").map((s) => s.trim()).filter(Boolean)
  .filter((f) => !f.endsWith(".test.ts") && !f.endsWith(".d.ts"));

/**
 * Is this stranded block the FILE'S OWN header, written below the import block?
 *
 * True when nothing but imports and comments stands above it. Structural, so it costs no frozen
 * entry — an exemption list has to be maintained by hand and would admit a real residue the day
 * someone added one near the top of a file. By construction it cannot exempt a block that has a
 * declaration above it: `portal/register/register.ts` opens with fourteen imports and then two
 * documented constants, so its block stays flagged despite also sitting near line 30.
 */
function isFileHeader(lines: string[], start: number): boolean {
  for (let k = 0; k < start; k++) {
    const t = (lines[k] ?? "").trim();
    if (!t || t.startsWith("//") || t.startsWith("/*") || t.startsWith("*") || t.endsWith("*/")) continue;
    if (t.startsWith("import ") || t.startsWith("export type {") || t.startsWith("export {")) continue;
    return false;
  }
  return true;
}

/** Every `/** … *\/` block immediately followed by another, split by whether it is a file header. */
function scan(): { stranded: string[]; headers: string[] } {
  const stranded: string[] = [], headers: string[] = [];
  for (const f of FILES) {
    const lines = readFileSync(resolve(ROOT, f), "utf8").split("\n");
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i] ?? "";
      const closes = l.trimEnd().endsWith("*/") && (l.trim().startsWith("/**") || l.trim().startsWith("*"));
      if (!closes || !(lines[i + 1] ?? "").trim().startsWith("/**")) continue;
      let j = i;
      while (j > 0 && !(lines[j] ?? "").trim().startsWith("/**")) j--;
      const where = `${f}:${j + 1}  ${(lines[j] ?? "").trim().slice(0, 72)}`;
      (isFileHeader(lines, j) ? headers : stranded).push(where);
    }
  }
  return { stranded, headers };
}

const RESULT = scan();

describe("DOC-STRAND — no doc comment has lost its declaration", () => {
  it("scanned a plausible number of files — else every assertion below is vacuous", () => {
    expect(FILES.length, `only ${FILES.length} source files matched`).toBeGreaterThan(250);
  });

  it("no doc comment is stranded above another doc comment", () => {
    expect(RESULT.stranded,
      "a comment directly above another comment has lost its declaration, and it WILL be read as "
      + "documenting the next thing down. Find what it describes and move it there — all nine of the "
      + "originals had an owner a few dozen lines away with no comment of its own. Delete it only "
      + "once you have established the thing it describes has genuinely left the file.")
      .toEqual([]);
  });

  /**
   * The header exemption is a rule, so this is its positive control.
   *
   * `isFileHeader` returning true for everything would satisfy the assertion above while gating
   * nothing — the same failure as an allowlist quietly grown to cover the tree, and indistinguishable
   * from a correct rule if you only look at whether the suite is green. So it is pinned in both
   * directions: it must still match the one header shape that exists, and it must refuse a block
   * with a declaration above it.
   */
  it("the header rule matches file headers and nothing else", () => {
    expect(RESULT.headers.length,
      "0 means the rule matches nothing and is dead code; >1 means it has become over-broad and is "
      + "now hiding residue. Either way it has stopped being the thing asserted above.")
      .toBe(1);
    expect(RESULT.headers[0]).toContain("apps/web/src/portal/panels/budget.ts");

    const reg = readFileSync(resolve(ROOT, "apps/web/src/portal/register/register.ts"), "utf8").split("\n");
    const modFilter = reg.findIndex((l) => l.includes("MOD-FILTER — everything currently narrowing"));
    expect(modFilter, "MOD-FILTER's block is the fixture for this control").toBeGreaterThan(0);
    expect(isFileHeader(reg, modFilter - 1),
      "MOD-FILTER has two documented consts above it — a declaration, so never a file header")
      .toBe(false);
    expect(isFileHeader(reg, 0), "line 1 of any file trivially has nothing above it").toBe(true);
  });
});
