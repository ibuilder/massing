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
// `prompted` is what the next promptModal resolves to; the rename tests set it. A constant `null`
// would make every rename assertion pass by never starting a rename at all.
const prompted: { value: unknown } = { value: null };
vi.mock("../../ui/modal", () => ({
  confirmModal: () => Promise.resolve(true),
  promptModal: () => Promise.resolve(prompted.value),
}));

// The failure paths toast rather than throw, and "did it warn?" is half the claim: a silent no-op
// and a reported refusal look identical in the DOM.
const toasts: string[] = [];
vi.mock("../../ui/feedback", async (orig) => ({
  ...(await orig<typeof import("../../ui/feedback")>()),
  toast: (msg: string) => { toasts.push(msg); },
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

  it("clears a removed column in ONE call, and writes nothing when it fails", async () => {
    // BULK-PATCH. This used to be a PATCH per row, and the test that stood here asserted the panel
    // RE-READ after a mid-loop failure — the best available answer when half the rows were already
    // committed. There is no half now: `drop` moves the cells inside the same transaction as the
    // config write, so the claim is stronger and different. Kept as one test because the old one
    // would now pass VACUOUSLY: with the loop gone, `updateModuleRecord` is never called and every
    // assertion about a partial failure holds for a reason that no longer exists.
    const { c, api } = ctx(ORPHANED, {
      setResponsibilityConfig: vi.fn().mockRejectedValue(new Error("500 from the server")),
    });
    await renderResponsibility(c); await flush();
    const before = c.root.textContent ?? "";
    toasts.length = 0;
    const clear = [...c.root.querySelectorAll("button")]
      .find((b) => (b.textContent ?? "").includes("Clear them")) as HTMLButtonElement | undefined;
    expect(clear).toBeTruthy();
    clear!.click(); await flush(); await flush();

    expect(api.setResponsibilityConfig, "the clear must be one call, not one per row")
      .toHaveBeenCalledTimes(1);
    const [, roles, mode, opts] = api.setResponsibilityConfig.mock.calls[0]!;
    expect(roles, "clearing orphans must not change the columns").toEqual(["Client", "Task Team"]);
    expect(mode).toBe("RACI");
    expect(opts).toEqual({ drop: ["Architect/EOR", "GC / PM"] });
    expect(api.updateModuleRecord, "no row may be PATCHed directly any more")
      .not.toHaveBeenCalled();
    expect(toasts.join(" "), "a refused clear must say so").toMatch(/Couldn't clear/);
    expect(c.root.textContent ?? "", "nothing was written, so nothing may change on screen")
      .toBe(before);
    expect(clear!.disabled, "the button must be re-armed so the user can retry").toBe(false);
  });

  it("renames a column and its cells in ONE call, never row by row", async () => {
    // The dangerous one. Per-row PATCHes left the rows that had already moved carrying a name that
    // was no longer a column — indistinguishable from an orphan, and a re-run could not find them
    // because the name it was renaming was gone from the rows that mattered. The new column list
    // and the cell remap now travel together, so there is no state in between.
    prompted.value = { role: "Owner" };
    const { c, api } = ctx(CLEAN);
    await renderResponsibility(c); await flush();
    const head = [...c.root.querySelectorAll("th span")]
      .find((sp) => sp.textContent === "Client") as HTMLElement | undefined;
    expect(head, "the 'Client' column header was not rendered").toBeTruthy();
    head!.click(); await flush(); await flush();

    expect(api.setResponsibilityConfig).toHaveBeenCalledTimes(1);
    const [, roles, mode, opts] = api.setResponsibilityConfig.mock.calls[0]!;
    expect(roles, "the renamed column replaces the old one in place")
      .toEqual(["Owner", "Task Team"]);
    expect(mode).toBe("RACI");
    expect(opts, "the cell remap must ride WITH the column list")
      .toEqual({ rename: { Client: "Owner" } });
    expect(api.updateModuleRecord).not.toHaveBeenCalled();
    prompted.value = null;
  });

  it("leaves every row on the original name when the rename is refused", async () => {
    // The half-applied rename, stated as the panel can state it: one call, so a refusal means the
    // whole thing did not happen. Asserting the DOM as well as the mock, because "the request was
    // rejected" and "the screen still shows the old name" are different claims.
    prompted.value = { role: "Owner" };
    const { c, api } = ctx(CLEAN, {
      setResponsibilityConfig: vi.fn().mockRejectedValue(new Error("row 3 refused")),
    });
    await renderResponsibility(c); await flush();
    toasts.length = 0;
    const head = [...c.root.querySelectorAll("th span")]
      .find((sp) => sp.textContent === "Client") as HTMLElement | undefined;
    head!.click(); await flush(); await flush();

    expect(api.updateModuleRecord).not.toHaveBeenCalled();
    const headers = [...c.root.querySelectorAll("th span")].map((sp) => sp.textContent);
    expect(headers, "a refused rename must leave the columns exactly as they were")
      .toContain("Client");
    expect(headers).not.toContain("Owner");
    expect(toasts.join(" ")).toMatch(/Couldn't rename Client/);
    prompted.value = null;
  });

  it("removes a column by naming it in `drop`, and switches mode without touching rows", async () => {
    // Two handlers, one claim: the cells that a column edit moves are the SERVER's to move. The
    // mode toggle is here because `matrix()` hides any letter invalid in the current mode, so a row
    // left on the old doer renders empty rather than wrong — the failure nobody would report.
    const { c, api } = ctx(CLEAN);
    await renderResponsibility(c); await flush();
    const x = [...c.root.querySelectorAll("th span")]
      .find((sp) => (sp.textContent ?? "").includes("✕")) as HTMLElement | undefined;
    expect(x, "no remove control on the first column").toBeTruthy();
    x!.click(); await flush(); await flush();
    const [, roles, , opts] = api.setResponsibilityConfig.mock.calls[0]!;
    expect(roles).toEqual(["Task Team"]);
    expect(opts).toEqual({ drop: ["Client"] });

    const mode = [...c.root.querySelectorAll("button")]
      .find((b) => (b.textContent ?? "").includes("Switch to DACI")) as HTMLButtonElement;
    expect(mode).toBeTruthy();
    mode.click(); await flush(); await flush();
    const [, mRoles, mMode, mOpts] = api.setResponsibilityConfig.mock.calls[1]!;
    expect(mRoles, "switching mode must not change the columns").toEqual(["Client", "Task Team"]);
    expect(mMode).toBe("DACI");
    expect(mOpts, "the R→D remap is the server's, so no rename/drop is sent").toBeUndefined();
    expect(api.updateModuleRecord, "no handler may PATCH a row to change a column or the mode")
      .not.toHaveBeenCalled();
  });

  it("does not offer a repair when there is nothing to repair", async () => {
    const { c } = ctx(CLEAN);
    await renderResponsibility(c); await flush();
    const buttons = [...c.root.querySelectorAll("button")].map((b) => b.textContent ?? "");
    expect(buttons.some((t) => t.includes("Restore"))).toBe(false);
    expect(buttons.some((t) => t.includes("Clear them"))).toBe(false);
  });
});
