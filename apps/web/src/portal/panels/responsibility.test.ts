import { describe, expect, it, vi } from "vitest";

import type { PanelContext } from "../panelContext";
import { renderResponsibility } from "./responsibility";

/**
 * RESP-ORPHAN — the claim about the SCREEN, not about the rule.
 *
 * `raciValidation.test.ts` proves the verdict is computed over visible columns. That is a claim
 * about a FUNCTION. This is the claim about the PANEL: a validator that returns the right answer
 * into a banner still painting "✅ Every activity has exactly one Accountable" would satisfy the
 * first test completely and leave the user looking at the same lie.
 *
 * The distinction has bitten this repo before — a button built, returned, destructured and appended
 * to nothing typechecks perfectly — so these assertions drive the real DOM and read what is on it.
 */

// The clear path is behind a confirmation. jsdom never clicks it, so the real `confirmModal`
// leaves a promise pending forever and the test reads as "the button did nothing" — which is
// indistinguishable from the defect. Auto-confirm so the assertions are about the clear itself.
vi.mock("../../ui/modal", () => ({
  confirmModal: () => Promise.resolve(true),
  promptModal: () => Promise.resolve(null),
}));

const el = () => document.createElement("div");

const ORPHANED = {
  mode: "RACI", letters: ["R", "A", "C", "I"], doer: "R",
  roles: ["Client", "Task Team"],
  rows: [{ id: "1", ref: "RESP-001", activity: "Author models",
    phase: null, category: null, milestone: null, reference: null,
    assignments: { "Architect/EOR": "A", "GC / PM": "R" } }],
  count: 1,
  validation: { missing_accountable: [], no_responsible: [], unknown_role: [],
    accountable_load: {}, clean: true },
  summary: { activities: 1, clean: true, issues: 0 },
};

/**
 * The row satisfies the rule on its VISIBLE columns and still carries a letter on one that is gone.
 *
 * Added because the first draft of this file could not express it: `ORPHANED` has every letter
 * orphaned, so `clean` is already false and the early return is never reached — mutating the
 * banner's orphan guard away left all four tests green. A fixture that cannot reach the branch
 * reports the check as passing, which is the same shape as the defect under test.
 */
const CLEAN_BUT_ORPHANED = {
  ...ORPHANED,
  rows: [{ ...ORPHANED.rows[0]!,
    assignments: { Client: "A", "Task Team": "R", "Architect/EOR": "C" } }],
};

const CLEAN = {
  ...ORPHANED,
  roles: ["Client", "Task Team"],
  rows: [{ ...ORPHANED.rows[0]!, assignments: { Client: "A", "Task Team": "R" } }],
};

const flush = async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); };

/**
 * A FRESH clone on every read, because the panel mutates what it was handed.
 *
 * `mockResolvedValue(structuredClone(m))` captures ONE object and hands the same instance back to
 * every read. The clear handler assigns `r.assignments = keep` before awaiting, so a reload after a
 * failed PATCH re-read the row the client had already emptied — and a test asserting "the panel
 * shows what the server has" could not fail, because the mock had no server state distinct from the
 * client's. Raised in review. Cloning per call means client mutation can never leak back, and
 * `queue` lets a test state what the server holds on the NEXT read.
 */
function ctx(matrix: unknown, over: Record<string, unknown> = {}, queue: unknown[] = []) {
  const api = {
    responsibilityMatrix: vi.fn().mockImplementation(() =>
      Promise.resolve(structuredClone(queue.length ? queue.shift() : matrix))),
    responsibilityTemplates: vi.fn().mockResolvedValue({ templates: [] }),
    setResponsibilityConfig: vi.fn().mockResolvedValue({ roles: [], mode: "RACI" }),
    applyResponsibilityTemplate: vi.fn().mockResolvedValue({ created: 0 }),
    updateModuleRecord: vi.fn().mockResolvedValue({}),
    createModuleRecord: vi.fn().mockResolvedValue({ id: "x" }),
    deleteModuleRecord: vi.fn().mockResolvedValue({}),
    ...over,
  };
  const c: PanelContext = {
    root: el(),
    host: { projectId: () => "p1", api } as unknown as PanelContext["host"],
    mods: [], activeKey: "responsibility",
    bar: (title: string) => { const b = el(); b.textContent = title; return b; },
    buildNav: () => undefined, renderHome: async () => undefined, openModule: async () => undefined,
    navigate: () => undefined, hasDest: () => true,
  } as unknown as PanelContext;
  return { c, api };
}

describe("the RACI banner answers for assignments the grid cannot show", () => {
  it("does NOT claim the matrix is complete when every letter is on a removed column", async () => {
    // This is the defect verbatim: `apply_template` swapped the columns under an existing row, so
    // the row rendered blank and the banner called it complete.
    const { c } = ctx(ORPHANED);
    await renderResponsibility(c); await flush();
    const text = c.root.textContent ?? "";
    expect(text, "the banner asserted completeness over an unshowable row")
      .not.toContain("✅ Every activity has exactly one Accountable");
    expect(text).toContain("Architect/EOR");
    expect(text).toContain("GC / PM");
    expect(text).toMatch(/no longer has/);
  });

  it("does NOT claim completeness when the rule passes but an orphan remains", async () => {
    // The narrow branch: `clean` is true and there is still a letter the grid cannot draw. The
    // ✅ has to answer for it, or the panel is silently dropping a "C" the user assigned.
    const { c } = ctx(CLEAN_BUT_ORPHANED);
    await renderResponsibility(c); await flush();
    const text = c.root.textContent ?? "";
    expect(text, "the ✅ was painted over an assignment the grid cannot show")
      .not.toContain("✅ Every activity has exactly one Accountable");
    expect(text).toContain("Architect/EOR");
  });

  it("still shows the ✅ when the matrix really is clean", async () => {
    // Without this the test above passes for the wrong reason — a banner that never says ✅ at all
    // would satisfy it, and that is a different defect rather than a fix.
    const { c } = ctx(CLEAN);
    await renderResponsibility(c); await flush();
    expect(c.root.textContent ?? "").toContain("✅ Every activity has exactly one Accountable");
  });

  it("offers to restore the missing columns, and asks for exactly them", async () => {
    const { c, api } = ctx(ORPHANED);
    await renderResponsibility(c); await flush();
    const restore = [...c.root.querySelectorAll("button")]
      .find((b) => (b.textContent ?? "").includes("Restore"));
    expect(restore, "no restore control was rendered").toBeTruthy();
    restore!.click(); await flush();
    expect(api.setResponsibilityConfig).toHaveBeenCalledTimes(1);
    const [, roles] = api.setResponsibilityConfig.mock.calls[0]!;
    // the existing columns are kept and the orphans are appended — restoring must not drop columns
    expect(roles).toEqual(["Client", "Task Team", "Architect/EOR", "GC / PM"]);
  });

  it("refuses a Restore that would overflow the column cap, rather than truncating", async () => {
    // Raised in review, and it is this item's own defect through its own repair button: set_config
    // TRUNCATES a longer list and returns 200 with the visible roles first, so the orphans fall off
    // the tail and the banner reloads clean over assignments that are still stranded.
    const WIDE = {
      ...ORPHANED,
      roles: Array.from({ length: 16 }, (_, i) => `Role ${i}`),   // exactly at the cap
    };
    const { c, api } = ctx(WIDE);
    await renderResponsibility(c); await flush();
    const restore = [...c.root.querySelectorAll("button")]
      .find((b) => (b.textContent ?? "").includes("Restore")) as HTMLButtonElement | undefined;
    expect(restore, "the restore control should still be shown, explaining why it cannot run")
      .toBeTruthy();
    expect(restore!.disabled, "restore must not be armed when it cannot fit").toBe(true);
    expect(restore!.title).toMatch(/16-column limit/);
    restore!.click(); await flush();
    expect(api.setResponsibilityConfig, "an over-long restore must not reach the server")
      .not.toHaveBeenCalled();
  });

  it("re-reads after a partial clear instead of showing state the server refused", async () => {
    // Each row is its own PATCH. On a mid-loop failure the panel must not keep rendering the
    // in-memory assignments it optimistically emptied. Raised in review.
    const TWO_ROWS = {
      ...ORPHANED,
      rows: [
        { ...ORPHANED.rows[0]!, id: "1", ref: "RESP-001" },
        { ...ORPHANED.rows[0]!, id: "2", ref: "RESP-002" },
      ],
      count: 2,
    };
    // What the SERVER holds after the first PATCH commits and the second is rejected: row 1 cleared,
    // row 2 still carrying its orphaned letters. Queued as a distinct response, because asserting
    // only that a re-read happened proves nothing about what the re-read showed — raised in review.
    const AFTER_PARTIAL = {
      ...TWO_ROWS,
      rows: [
        { ...TWO_ROWS.rows[0]!, assignments: {} },
        { ...TWO_ROWS.rows[1]! },
      ],
    };
    let calls = 0;
    const { c, api } = ctx(TWO_ROWS, {
      updateModuleRecord: vi.fn().mockImplementation(() => {
        calls += 1;
        return calls === 1 ? Promise.resolve({}) : Promise.reject(new Error("500"));
      }),
    }, [TWO_ROWS, AFTER_PARTIAL]);
    await renderResponsibility(c); await flush();
    const reads = api.responsibilityMatrix.mock.calls.length;
    const clear = [...c.root.querySelectorAll("button")]
      .find((b) => (b.textContent ?? "").includes("Clear them")) as HTMLButtonElement | undefined;
    expect(clear).toBeTruthy();
    clear!.click(); await flush(); await flush();
    expect(api.responsibilityMatrix.mock.calls.length,
      "a partial failure must re-read, not leave the panel ahead of the server")
      .toBeGreaterThan(reads);
    // ...and the re-read must be what is RENDERED: the row the server still holds is still reported.
    const text = c.root.textContent ?? "";
    expect(text, "the banner must still report the orphan the server did not clear")
      .toMatch(/no longer has/);
    expect(text).toContain("Architect/EOR");
    expect(text, "a partial clear is not a clean matrix")
      .not.toContain("✅ Every activity has exactly one Accountable");
  });

  it("does not offer a repair when there is nothing to repair", async () => {
    const { c } = ctx(CLEAN);
    await renderResponsibility(c); await flush();
    const buttons = [...c.root.querySelectorAll("button")].map((b) => b.textContent ?? "");
    expect(buttons.some((t) => t.includes("Restore"))).toBe(false);
    expect(buttons.some((t) => t.includes("Clear them"))).toBe(false);
  });
});
