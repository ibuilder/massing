import { describe, expect, it, vi } from "vitest";

import { type RepairDeps, wallJoinsButton } from "./repairPanel";

/**
 * The wall-joins panel, driven through the DOM it actually builds.
 *
 * **What this exists for.** A reviewer found that the repair re-read the tolerance input at the
 * moment the button was pressed, rather than using the tolerance the list on screen was measured at.
 * Scan at 0.05, see three joins, nudge the input to 0.5, press butt-join — and the server resolves at
 * 0.5, trimming walls that were never displayed. *The list is the user's consent, and it is specific
 * to the number it was measured at.*
 *
 * It is the same shape as the defect the whole PR is about — what is SHOWN and what is ACTED ON
 * coming apart — which is why it gets a behavioural test rather than a careful comment: the comment
 * is what the original had.
 */
function harness(joins = 2) {
  const calls: { scanned: number[]; repaired: unknown[] } = { scanned: [], repaired: [] };
  const deps: RepairDeps = {
    pid: "p1",
    api: {
      wallJoins: async (_pid: string, tol?: number) => {
        calls.scanned.push(tol as number);
        return {
          wall_count: 3, counts: { L: joins, T: 0 },
          joins: Array.from({ length: joins }, (_, i) => ({
            kind: "L" as const, corner: [i, 0], through: `T${i}`, stub: `S${i}`,
            walls: [`T${i}`, `S${i}`],
          })),
        };
      },
    } as unknown as RepairDeps["api"],
    toolBtn2: (label, onClick) => {
      const b = document.createElement("button");
      b.textContent = label; b.onclick = onClick; return b;
    },
    notify: vi.fn(),
    selectMap: vi.fn(async () => undefined),
    sets: { fromGuids: vi.fn(async (g: string[]) => g as never) } as unknown as RepairDeps["sets"],
    authorAndReload: vi.fn(async (_r, params) => {
      calls.repaired.push(params);
      return { applied: true, refused: false };
    }),
  };
  return { deps, calls };
}

const flush = () => new Promise((r) => setTimeout(r, 0));
const pick = <T extends Element>(sel: string) => document.querySelector(sel) as T;
const btn = (text: string) =>
  [...document.querySelectorAll("button")].find((b) => b.textContent?.includes(text))!;

async function openPanel(deps: RepairDeps) {
  document.body.replaceChildren();
  const opener = wallJoinsButton(deps);
  document.body.appendChild(opener);
  opener.click();
  await flush();
}

describe("wall joins: the repair uses the tolerance the LIST was measured at", () => {
  it("scans at the input's value and repairs at that same value", async () => {
    const { deps, calls } = harness();
    await openPanel(deps);
    expect(calls.scanned, "the panel scans once on open").toEqual([0.05]);

    btn("Butt-join").click();
    await flush();
    expect(calls.repaired, "repairs at the tolerance that produced the list").toEqual([{ tol: 0.05 }]);
  });

  it("REFUSES to repair at a tolerance the user never saw a list for", async () => {
    // The regression. Without the fix this repairs at 0.5 while the visible list is the 0.05 one,
    // trimming walls that were never displayed.
    //
    // **The two properties are asserted separately, and the first draft of this test conflated
    // them.** It disabled the button, clicked it, and concluded from an empty `repaired` that the
    // press-time guard had refused. It had not: *a disabled button's `.click()` does not fire its
    // handler at all*, so the assertion passed on the affordance alone and would have passed with
    // the guard deleted. Caught in review — and it is this PR's own subject a fourth time, a claim
    // in a comment that the check does not back. The handler is now forced to run.
    const { deps, calls } = harness();
    await openPanel(deps);
    expect(calls.scanned).toEqual([0.05]);

    const tolI = pick<HTMLInputElement>("input[type=number]");
    tolI.value = "0.5";
    tolI.dispatchEvent(new Event("input"));

    const fix = btn("Butt-join");
    expect(fix.disabled, "① the affordance: editing the tolerance invalidates the list on screen").toBe(true);

    fix.disabled = false;              // ② the guard, exercised for real: re-enable so the handler RUNS
    fix.click();
    await flush();
    expect(calls.repaired, "the handler itself must refuse a list the user never saw").toEqual([]);
    expect(fix.disabled, "and it must put the control back where it found it").toBe(true);
  });

  it("repairs at the NEW tolerance once the user has actually re-scanned at it", async () => {
    // The complement: the guard must not make the control unusable after a legitimate change.
    const { deps, calls } = harness();
    await openPanel(deps);

    const tolI = pick<HTMLInputElement>("input[type=number]");
    tolI.value = "0.5";
    tolI.dispatchEvent(new Event("input"));
    btn("Scan").click();
    await flush();
    expect(calls.scanned).toEqual([0.05, 0.5]);

    btn("Butt-join").click();
    await flush();
    expect(calls.repaired).toEqual([{ tol: 0.5 }]);
  });

  it("leaves the repair unavailable when the scan found nothing to repair", async () => {
    const { deps, calls } = harness(0);
    await openPanel(deps);
    expect(btn("Butt-join").disabled, "nothing found — nothing to butt-join").toBe(true);
    expect(calls.repaired).toEqual([]);
  });
});
