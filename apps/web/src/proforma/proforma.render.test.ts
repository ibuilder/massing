/**
 * Characterization tests for ProformaUI's massing + test-fit render paths — the safety net the
 * Repowise plan requires BEFORE the god-class split (health 1.65, top-1% change entropy, 4
 * bug-fixes in 180 d). These pin the two tabs that are about to be extracted along the LCOM4
 * seam, through the seam itself: the render methods, driven with a mocked ApiClient.
 *
 * What is pinned, deliberately: the form's field inventory and defaults (what `params()` derives),
 * the estimate flow's request payload and result summary, the no-project guard on generate, the
 * ESCAPED error path (the 2026-08-02 innerHTML XSS fix — a server error detail can quote the
 * caller's own input), and the unit-mix editor's default mix + localStorage round-trip. When the
 * extraction lands, these tests move with the code and must not change behavior.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ApiClient } from "../api/client";
import { ProformaUI } from "./proforma";

/** A ProformaUI whose root is a fresh container and whose api is a per-test mock. */
function mount(api: Partial<Record<string, unknown>>, pid: string | null = null) {
  const root = document.createElement("div");
  document.body.replaceChildren(root);
  const setStatus = vi.fn();
  const ui = new ProformaUI(root, api as unknown as ApiClient, setStatus, () => pid);
  // the private render methods ARE the seam the split will cut along — reach them deliberately
  return { root, ui: ui as unknown as { renderMassing(): void; renderTestFit(): void }, setStatus };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

const btn = (root: HTMLElement, text: string): HTMLButtonElement => {
  const b = [...root.querySelectorAll("button")].find((x) => x.textContent === text);
  if (!b) throw new Error(`no button ${text}`);
  return b;
};

/** The canned massing result the estimate/generate paths summarize. */
const RESULT = {
  metrics: {
    floors: 5, building_height_m: 17.5, buildable_gfa_sf: 64583, units: 64,
    footprint_m2: 1200, binding_constraint: "coverage", far_achieved: 3.0,
  },
  proforma: {
    assumptions: {},
    returns: { equity_irr: 0.182, equity_multiple: 2.1 },
    sources_uses: { total_uses: 20_000_000, equity: 7_000_000 },
  },
};

describe("renderMassing (characterization)", () => {
  beforeEach(() => localStorage.clear());

  it("builds the zoning form: use-type select, 14 numeric fields with the documented defaults, 6 toggles, parking, 2 actions", () => {
    const { root, ui } = mount({});
    ui.renderMassing();
    const host = root.querySelector("#pf-massing") as HTMLElement;
    expect(host).toBeTruthy();
    expect(host.querySelectorAll("select").length).toBe(1);
    const nums = [...host.querySelectorAll(".pf-form input[type=number]")] as HTMLInputElement[];
    expect(nums.length).toBe(14);
    expect(nums[0]?.value).toBe("50");                       // lot width (m)
    expect(nums.map((i) => i.value)).toContain("225");       // hard $/sf default
    expect(host.querySelectorAll("input[type=checkbox]").length).toBe(6); // dome/frame/units/envelope/core/corridor
    expect(btn(host, "Estimate yield")).toBeTruthy();
    expect(btn(host, "Generate IFC model + apply")).toBeTruthy();
  });

  it("estimate: sends params derived from the form (height_limit 0 → null) and summarizes the result", async () => {
    const previewMassing = vi.fn().mockResolvedValue(RESULT);
    const { root, ui } = mount({ previewMassing });
    ui.renderMassing();
    btn(root, "Estimate yield").click();
    await flush();
    expect(previewMassing).toHaveBeenCalledTimes(1);
    const sent = previewMassing.mock.calls[0]?.[0];
    expect(sent).toMatchObject({ use_type: "residential", lot_width: 50, lot_depth: 40, far: 3,
                                 height_limit: null, frame: false, units: false });
    expect(sent.parking).toBeUndefined();                    // 0 stalls → key omitted
    const out = root.querySelector("#pf-massing")?.textContent ?? "";
    expect(out).toContain("5 floors");
    expect(out).toContain("64,583 sf");
    expect(out).toContain("bound by coverage");
    expect(out).toContain("18.2%");                          // equity IRR formatted
  });

  it("generate without a project: guard message, api never called", async () => {
    const generateMassing = vi.fn();
    const { root, ui } = mount({ generateMassing }, null);
    ui.renderMassing();
    btn(root, "Generate IFC model + apply").click();
    await flush();
    expect(generateMassing).not.toHaveBeenCalled();
    expect(root.querySelector("#pf-massing")?.textContent).toContain("Open or create a project first");
  });

  it("an error detail is ESCAPED into the output, never parsed as markup (2026-08-02 XSS regression)", async () => {
    const previewMassing = vi.fn().mockRejectedValue(new Error('<img src=x onerror="window.__pwned=1">'));
    const { root, ui } = mount({ previewMassing });
    ui.renderMassing();
    btn(root, "Estimate yield").click();
    await flush();
    const host = root.querySelector("#pf-massing") as HTMLElement;
    expect(host.querySelector("img")).toBeNull();            // markup neutralized…
    expect(host.textContent).toContain("<img src=x");        // …but the message still shown verbatim
    expect((window as unknown as Record<string, unknown>).__pwned).toBeUndefined();
  });

  it("the generate error path escapes too (sink 2 of 4 from the same fix)", async () => {
    const generateMassing = vi.fn().mockRejectedValue(new Error("<b>422</b> detail quoting caller input"));
    const { root, ui } = mount({ generateMassing }, "p1");
    ui.renderMassing();
    btn(root, "Generate IFC model + apply").click();
    await flush();
    const host = root.querySelector("#pf-massing") as HTMLElement;
    expect(host.querySelector("b")).toBeNull();
    expect(host.textContent).toContain("<b>422</b>");
  });

  it("SOURCE PIN: every error-message innerHTML sink in proforma/ stays on the escaped path", async () => {
    // The four sinks fixed on 2026-08-02 took `(e as Error).message` into innerHTML unescaped.
    // Two are exercised above; the other two live in panels that need a deep api mock to drive,
    // so pin ALL of them at the source level, DERIVED not enumerated: an interpolation of an
    // error message into innerHTML must go through escapeHtml (textContent/setStatus are exempt —
    // they don't parse markup). Down-to-zero is the required state; any new unescaped sink fails.
    const { readFileSync, readdirSync } = await import("node:fs");
    const { join } = await import("node:path");
    const offenders: string[] = [];
    for (const f of readdirSync(__dirname).filter((n) => n.endsWith(".ts") && !n.endsWith(".test.ts"))) {
      const src = readFileSync(join(__dirname, f), "utf-8");
      for (const [i, line] of src.split("\n").entries()) {
        if (/innerHTML\s*[+]?=/.test(line) && /\((e|err) as Error\)\.message/.test(line)
            && !/escapeHtml\(\((e|err) as Error\)\.message\)/.test(line)) {
          offenders.push(`${f}:${i + 1}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe("renderTestFit (characterization)", () => {
  beforeEach(() => localStorage.clear());

  it("renders the plate form and the default Studio/1BR/2BR mix summing to 100%", () => {
    const { root, ui } = mount({});
    ui.renderTestFit();
    const host = root.querySelector("#pf-testfit") as HTMLElement;
    expect(host).toBeTruthy();
    const plates = [...host.querySelectorAll(".pf-form input[type=number]")] as HTMLInputElement[];
    expect(plates.map((i) => i.value)).toEqual(["40", "18", "6"]);   // width / depth / floors
    const names = [...host.querySelectorAll("input:not([type=number]):not([type=checkbox])")]
      .map((i) => (i as HTMLInputElement).value);
    expect(names).toEqual(["Studio", "1BR", "2BR"]);         // the default mix, one text input per row
    expect(host.textContent).toContain("mix Σ 100%");
  });

  it("the mix editor adds a unit type and Save persists it for the next mount", () => {
    const first = mount({});
    first.ui.renderTestFit();
    let host = first.root.querySelector("#pf-testfit") as HTMLElement;
    btn(host, "+ unit type").click();
    expect(host.textContent).toContain("mix Σ 110%");        // 100% + the new 10% row, flagged live
    btn(host, "Save mix").click();
    expect(first.setStatus).toHaveBeenCalledWith("unit mix saved");

    const second = mount({});
    second.ui.renderTestFit();
    host = second.root.querySelector("#pf-testfit") as HTMLElement;
    expect(host.textContent).toContain("mix Σ 110%");        // round-tripped through localStorage
  });
});

/**
 * RESERVE-SUGGESTION-UNVERIFIED — the banner must not present an unverified figure as a target.
 *
 * `reserve.py` solves the level contribution and then RE-RUNS it against the schedule to confirm it
 * clears; `suggestion_clears_horizon` is that second answer. This banner printed the number in bold
 * as a recommendation and never read the flag, so a figure that failed verification looked exactly
 * like one that passed — at the moment a user would act on it.
 *
 * Read as `=== false`. The field is optional, and an older server that omits it means "not checked",
 * which must not render as "does not work".
 */
const STUDY = {
  horizon: { from: 2026, to: 2051 }, components: 12, components_missing_data: 0,
  events: [], schedule: [], total_outflows: 900_000,
  first_underfunded_year: 2033, adequately_funded: false,
  suggested_level_contribution: 42_000, note: "",
};

describe("reserve study — an unverified suggestion says so", () => {
  const mountAsset = async (study: Record<string, unknown>) => {
    const { root, ui } = mount({ reserveStudy: vi.fn(async () => study) }, "P1");
    const host = document.createElement("div"); root.appendChild(host);
    await (ui as unknown as { renderAssetMgmt(h: HTMLElement): Promise<void> }).renderAssetMgmt(host);
    await flush(); await flush();
    return host;
  };

  it("warns when the solved figure did not clear the horizon", async () => {
    const host = await mountAsset({ ...STUDY, suggestion_clears_horizon: false });
    expect(host.textContent).toContain("did not clear the horizon when re-run");
    expect(host.textContent, "the figure is still shown — it is unreliable, not absent")
      .toContain("42,000");
  });

  it("stays silent when the figure verified — the paired control", async () => {
    // Without this the assertion above could pass with the warning rendered unconditionally.
    const host = await mountAsset({ ...STUDY, suggestion_clears_horizon: true });
    expect(host.textContent).toContain("42,000");
    expect(host.textContent).not.toContain("did not clear the horizon");
  });

  it("stays silent when the server did not answer — absent is not failed", async () => {
    // An older server omits the field. Inventing a warning from a missing value is its own wrong
    // answer, and one false alarm here costs trust in the figure every other time it is right.
    const host = await mountAsset(STUDY);
    expect(host.textContent).toContain("42,000");
    expect(host.textContent).not.toContain("did not clear the horizon");
  });

  it("says only what the flag licenses — no invented cause", async () => {
    // The first draft read "No flat contribution does; the shortfall needs a higher opening
    // balance...". That is FALSE: `need` is the exact closed-form minimum, so a failed verification
    // means the solved figure disagreed with the schedule, not that the horizon is unclearable.
    // Explaining a cause it cannot know is the same defect this banner exists to fix.
    const host = await mountAsset({ ...STUDY, suggestion_clears_horizon: false });
    expect(host.textContent).not.toContain("No flat contribution");
    expect(host.textContent).toContain("unreliable");
  });
});

/**
 * R35-DEAL-MEMORY — the $/SF strip must describe the hard cost that is on screen NOW.
 *
 * Review finding, 2026-08-27: the strip was painted once by `renderBudget()`, so editing
 * "Hard cost $" left a comparison for the PREVIOUS hard cost sitting beside the new number. That is
 * the defect class this whole release is about — a report that misdescribes what it reports on —
 * and it is worse on an underwriting screen than most places, because the two numbers are adjacent
 * and the stale one looks like it was computed from the fresh one.
 *
 * Driven through `refreshDealMemory`, the seam the fix created, rather than through a keystroke:
 * the debounce is `window.setTimeout` and pinning a timer would test the scheduler, not the sum.
 */
describe("the deal-memory strip follows the hard cost", () => {
  function mountBudget(pid: string | null = "P1") {
    const api = {
      dealMemoryBeside: vi.fn().mockResolvedValue({
        metric: "cost_per_sf", status: "insufficient_history", entered: null,
      }),
    };
    const root = document.createElement("div");
    document.body.replaceChildren(root);
    const ui = new ProformaUI(root, api as unknown as ApiClient, vi.fn(), () => pid);
    const priv = ui as unknown as {
      a: { cost_lines: { category: string; amount: number }[] };
      memoryEl?: HTMLElement;
      refreshDealMemory(): void;
    };
    // mount a connected element for the strip — `refreshDealMemory` refuses to paint a detached one
    const el = document.createElement("div"); root.appendChild(el); priv.memoryEl = el;
    return { api, priv };
  }

  it("sends the CURRENT hard-cost total, not the one from first render", () => {
    const { api, priv } = mountBudget();
    priv.refreshDealMemory();
    expect(api.dealMemoryBeside).toHaveBeenLastCalledWith("P1", 20_000_000);

    // the edit the reviewer described: change the hard line, refresh, expect the NEW total
    const hard = priv.a.cost_lines.find((c) => c.category === "hard")!;
    hard.amount = 26_500_000;
    priv.refreshDealMemory();
    expect(api.dealMemoryBeside).toHaveBeenLastCalledWith("P1", 26_500_000);
  });

  it("sums every hard line rather than reading cost_lines[1]", () => {
    // The default deal happens to put hard cost second. A budget synced from the GC's does not, and
    // an index would have compared the wrong line against the firm's own history — silently, since
    // any number looks plausible in a $/SF strip.
    const { api, priv } = mountBudget();
    priv.a.cost_lines.push({ category: "hard", amount: 1_000_000 } as never);
    priv.refreshDealMemory();
    expect(api.dealMemoryBeside).toHaveBeenLastCalledWith("P1", 21_000_000);
  });

  it("asks nothing when there is no project", () => {
    const { api, priv } = mountBudget(null);
    priv.refreshDealMemory();
    expect(api.dealMemoryBeside).not.toHaveBeenCalled();
  });
});
