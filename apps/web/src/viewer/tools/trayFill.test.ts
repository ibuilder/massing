import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";

import type { MepDeps, TrayFill } from "./mepSection";
import { buildMepSection, trayFillHeadline, trayFillRows } from "./mepSection";

/**
 * TRAY-UNCOMPUTED — the tray-fill screen must not report a clearance over trays the engine could
 * not evaluate.
 *
 * `tray_fill` (`services/data/src/aec_data/mep_sizing.py`) returns a three-valued `status` per
 * tray, and **`info` means the tray was not evaluated**: no `IfcCableSegment` runs are authored on
 * its distribution system, so `fill_ratio` is `null`. `checked` counts every tray including those;
 * `failed` counts only the fails. The shipped render printed those two numbers and nothing else in
 * an `ok` tone, so **ten trays with no cables anywhere read as "10 tray(s) · 0 over fill", green**.
 *
 * It is another instance of one shape this branch has now fixed repeatedly — *an engine returns a
 * verdict beside a count of what it could not evaluate, and the consumer renders the verdict* — and
 * the narrowest of them: both immediate siblings in the same file already render their coverage
 * (`${mz.info} info`, `${tl.skipped_no_area} skipped (no area)`), one field away.
 *
 * **Why no audit here could see it.** `mepTrayFill` was typed `Record<string, unknown>`.
 * `deadFieldTyped.test.ts` and its siblings derive their population from the declarations in
 * `apps/web/src/api/`, so a response that declares no fields has nothing to check — the erasure
 * removes the subject, not just the type. `status` and `fill_ratio` were therefore fields no
 * derivation over declarations could reach, which is the same blindness
 * `noRespelledShapes.test.ts` sweeps for in its other form.
 *
 * Both layers are tested here: the decision (`trayFillHeadline`, mutated below) and the RENDER,
 * driven through the real `buildMepSection` into the DOM — because a source-level check cannot see
 * a render wrapped in `if (false)`, which is the limit `test_verdict_coverage.py` writes down for
 * itself.
 */

const tray = (status: "pass" | "fail" | "info", i = 0): TrayFill["trays"][number] =>
  status === "info"
    ? { guid: `TRAY${i}`, system: "PWR-1", width_in: 12, allowable_fill_in2: 14,
        citation: "NEC 392.22(A)", conductors: 0, fill_ratio: null, status: "info",
        note: "no cables authored on this tray's system" }
    : { guid: `TRAY${i}`, system: "PWR-1", width_in: 12, allowable_fill_in2: 14,
        citation: "NEC 392.22(A)", conductors: 3, fill_ratio: status === "fail" ? 1.4 : 0.42,
        used_fill_in2: status === "fail" ? 19.6 : 5.88, status,
        cables: [{ guid: "C1", diameter_in: 1.5, area_in2: 1.767 }] };

const DISCLAIMER = "Per-conductor NEC 392.22 fill screen from the authored cable diameters";

/** As the engine composes it: `checked` is every tray, `failed` only the fails. */
function resp(statuses: ("pass" | "fail" | "info")[]): TrayFill {
  const trays = statuses.map((s, i) => tray(s, i));
  return { checked: trays.length, failed: trays.filter((t) => t.status === "fail").length,
           trays, disclaimer: DISCLAIMER };
}

describe("trayFillHeadline — the verdict may not outrun the coverage", () => {
  it("is the SHIPPED DEFECT: ten trays, no cables, nothing computed", () => {
    const h = trayFillHeadline(resp(Array.from({ length: 10 }, () => "info" as const)));
    // What shipped: "10 tray(s) · 0 over fill" in `ok`. Both halves are wrong — the tone claims a
    // clearance, and the number counts trays nobody measured as if they had passed.
    expect(h.total).toBe(10);
    expect(h.uncomputed).toBe(10);
    expect(h.computed).toBe(0);
    expect(h.kind).not.toBe("ok");
    expect(h.kind).toBe("warn");
    expect(h.html).toContain("none computed");
    expect(h.html).toMatch(/add ifccablesegment/i);
    // and it must never read as a count of trays that passed
    expect(h.html).not.toMatch(/10 tray\(s\) · <b>0 over fill/);
  });

  it("names the uncomputed remainder when SOME trays were computed", () => {
    const h = trayFillHeadline(resp(["pass", "pass", "info", "info", "info"]));
    expect(h.computed).toBe(2);
    expect(h.uncomputed).toBe(3);
    expect(h.kind).toBe("warn");
    expect(h.html).toContain("2 of 5 tray(s) computed");
    expect(h.html).toContain("3 NOT computed");
  });

  it("is `ok` ONLY with full coverage and no failures", () => {
    const h = trayFillHeadline(resp(["pass", "pass"]));
    expect(h.kind).toBe("ok");
    expect(h.uncomputed).toBe(0);
    expect(h.html).toContain("2 of 2 tray(s) computed");
    expect(h.html).not.toContain("NOT computed");
  });

  it("a real failure outranks the coverage gap — a finding is not a warning", () => {
    const h = trayFillHeadline(resp(["fail", "info"]));
    expect(h.failed).toBe(1);
    expect(h.uncomputed).toBe(1);
    expect(h.kind).toBe("bad");
    expect(h.html).toContain("1 NOT computed");      // still stated, not swallowed by the fail
  });

  it("zero trays is ABSENT, not clean — the sibling defect", () => {
    const h = trayFillHeadline(resp([]));
    expect(h.kind).toBe("");                          // not `ok`: there is nothing to clear
    expect(h.html).toContain("no cable trays");
    expect(h.html).toMatch(/author/i);
  });

  it("does NOT key the uncomputed set on `conductors` — the supplied-ratio branch has none", () => {
    // `tray_fill`'s middle branch: no cables authored, but a `FillRatio` property supplied, so the
    // tray IS evaluated (pass or fail) with `conductors: 0`. Counting conductors would warn about a
    // tray that has an answer, and `status` is the only field that distinguishes the two.
    const supplied: TrayFill["trays"][number] = {
      guid: "TRAY9", system: "PWR-2", width_in: 24, allowable_fill_in2: 28,
      citation: "NEC 392.22(A)", conductors: 0, fill_ratio: 0.3, status: "pass",
      note: "supplied fill ratio (no cables authored on this system)",
    };
    const h = trayFillHeadline({ checked: 1, failed: 0, trays: [supplied], disclaimer: DISCLAIMER });
    expect(h.uncomputed).toBe(0);
    expect(h.computed).toBe(1);
    expect(h.kind).toBe("ok");
  });
});

describe("trayFillRows", () => {
  it("says 'not computed' in words rather than a dash in a percentage column", () => {
    const rows = trayFillRows(resp(["info"]));
    expect(rows).toHaveLength(1);
    expect(rows[0]!.v).toContain("not computed");
    expect(rows[0]!.v).not.toContain("0%");
  });

  it("reports the computed ones as a percentage of the allowable area", () => {
    const rows = trayFillRows(resp(["fail"]));
    expect(rows[0]!.v).toContain("140% of 14 in²");
    expect(rows[0]!.v).toContain("3 conductor(s)");
  });

  it("caps the table, as every sibling table here does", () => {
    expect(trayFillRows(resp(Array.from({ length: 30 }, () => "pass" as const)))).toHaveLength(12);
  });
});

/**
 * **The precondition the coverage count rests on**: `trays` is the WHOLE list.
 *
 * `cables` inside each tray is capped at 20 by the engine; `trays` is not. If a later change paged
 * it, `uncomputed` would become a count over a page while `checked` stayed a total — which is
 * CLASH-TRUNC exactly, one directory over, and the reason that gate exists is that the guard was
 * sound and its evidence was not. Asserted against the engine's own source, because the defect
 * would be introduced there and would leave every test above green.
 */
describe("the engine hands over every tray, not a page", () => {
  const ENGINE = readFileSync("../../services/data/src/aec_data/mep_sizing.py", "utf8");

  it("returns `trays` whole and `checked` as its length", () => {
    expect(ENGINE).toContain('"checked": len(trays), "failed": sum(1 for t in trays if t["status"] == "fail"),');
    expect(ENGINE).toContain('"trays": trays,');
    expect(ENGINE).not.toMatch(/"trays": trays\[/);
  });

  it("still emits the three statuses this screen reads, `info` among them", () => {
    expect(ENGINE).toContain('"status": "info"');
    expect(ENGINE).toContain('"cables": cables[:20]');       // the cap that `conductors` corrects for
  });
});

/** ---- the render, driven through the real panel ---------------------------------------------- */

function harness(tf: TrayFill) {
  const isolated: string[][] = [];
  const api = {
    mepSummary: vi.fn(async () => ({
      total_systems: 1, unassigned: { segments: 0, fittings: 0 },
      systems: [{ guid: "S1", name: "PWR-1", members: 2, segments: 1, fittings: 1, terminals: 0,
                  other: 0, elements_with_open_ports: 0 }],
    })),
    mepConnectivity: vi.fn(async () => ({
      elements: 2, ports_total: 4, ports_connected: 4, ports_open: 0, connections: 2,
      dangling_count: 0, connected_pct: 100, dangling: [],
    })),
    mepTrayFill: vi.fn(async () => tf),
  };
  const deps = {
    toolBtn2: (label: string, onClick: () => void) => {
      const b = document.createElement("button");
      b.textContent = label;
      b.onclick = onClick;
      return b;
    },
    api: api as unknown as MepDeps["api"],
    pid: "p1",
    projectId: "p1",
    notify: vi.fn(),
    container: document.createElement("div"),
    lastPoint: () => null,
    selectedGuid: () => null,
    layerMgr: { isolateGuids: (g: string[]) => { isolated.push(g); return Promise.resolve(); } } as
      unknown as MepDeps["layerMgr"],
    loadProjectModel: vi.fn(async () => true),
    reloadModelPins: vi.fn(async () => undefined),
    waitForPublish: vi.fn(async () => undefined),
    authorAndReload: vi.fn(async () => ({ applied: true, refused: false })),
  } satisfies MepDeps;
  return { deps, isolated };
}

const flush = () => new Promise((r) => setTimeout(r, 0));
const btn = (text: string) =>
  [...document.querySelectorAll("button")].find((b) => b.textContent?.includes(text));
const notes = () =>
  [...document.querySelectorAll(".result-note")].map((n) => ({
    text: n.textContent ?? "", cls: n.className,
  }));

const tables = () => document.querySelectorAll(".result-table").length;

async function openTrayFill(tf: TrayFill) {
  document.body.replaceChildren();
  const { deps, isolated } = harness(tf);
  const buttons = buildMepSection(deps);
  buttons.mepSysBtn.click();
  await flush();
  // The panel renders its own system table before any of these buttons is pressed, so "did the
  // tray result add a table" is a DELTA. Counting all of them measured the panel, not this tool —
  // it reported one table for a response with no trays at all.
  const before = tables();
  btn("Tray fill")!.click();
  await flush();
  return { isolated, tablesAdded: tables() - before };
}

describe("the rendered tray-fill result", () => {
  it("renders the coverage, and NOT in a passing tone", async () => {
    await openTrayFill(resp(["info", "info", "info"]));
    const headline = notes().find((n) => n.text.includes("Tray fill"))!;
    expect(headline.text).toContain("none computed");
    expect(headline.cls).toContain("warn");
    expect(headline.cls).not.toContain("ok");
    // the engine's disclaimer still reaches the screen
    expect(notes().some((n) => n.text.includes("NEC 392.22 fill screen"))).toBe(true);
  });

  it("offers the two different pieces of work the two sets ask for", async () => {
    const { isolated } = await openTrayFill(resp(["fail", "info"]));
    btn("Isolate over-fill trays")!.click();
    btn("Isolate trays with no cables authored")!.click();
    expect(isolated).toEqual([["TRAY0"], ["TRAY1"]]);
  });

  it("offers neither button when there is nothing in either set", async () => {
    await openTrayFill(resp(["pass"]));
    expect(btn("Isolate over-fill trays")).toBeUndefined();
    expect(btn("Isolate trays with no cables")).toBeUndefined();
    expect(notes().find((n) => n.text.includes("Tray fill"))!.cls).toContain("ok");
  });

  it("DOES add the per-tray table when there are trays — the other half of the delta", async () => {
    const { tablesAdded } = await openTrayFill(resp(["pass", "info"]));
    expect(tablesAdded).toBe(1);
  });

  it("renders no table when there are no trays, rather than an empty one", async () => {
    const { tablesAdded } = await openTrayFill(resp([]));
    expect(tablesAdded).toBe(0);
    expect(notes().find((n) => n.text.includes("Tray fill"))!.text).toContain("no cable trays");
  });
});
