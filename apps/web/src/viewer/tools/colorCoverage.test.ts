import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";

import type { ColorBy } from "./colorCoverage";
import { bucketRows, coverageReading } from "./colorCoverage";
import { type ModelStateDeps, openPhasingPanel } from "./modelStatePanels";

/**
 * COLOR-UNSET — a legend over the buckets alone, for a tool whose whole job is the elements that
 * have no bucket.
 *
 * `/elements/color-by` returns `total`, `colored` and `unset`; the shipped consumer read `buckets`
 * and nothing else. The branch that matters is `partial`, and the fixtures are the live caller's:
 * `modelStatePanels.ts` colours by `Massing_Phasing.Status`, which is unset on every element of a
 * model nobody has phased yet.
 *
 * **`colored === 0` and `total === 0` are different findings and are kept apart.** No model loaded
 * is an absence of input; a loaded model where nothing carries the property is the strongest result
 * the tool can produce, and collapsing them to one "nothing to show" line is the empty-versus-absent
 * confusion this branch has corrected repeatedly.
 */

const resp = (over: Partial<ColorBy> & { buckets: ColorBy["buckets"] }): ColorBy => {
  const colored = over.colored ?? over.buckets.reduce((n, b) => n + b.count, 0);
  const total = over.total ?? colored;
  return {
    prop: over.prop ?? "Massing_Phasing.Status",
    kind: over.kind ?? "categorical",
    total, colored, unset: over.unset ?? total - colored,
    buckets: over.buckets,
  };
};

const bk = (label: string, count: number): ColorBy["buckets"][number] =>
  ({ label, count, guids: Array.from({ length: count }, (_, i) => `${label}-${i}`) });

/** The defect's own shape: 40 phased elements in a 4,000-element model. */
const MOSTLY_UNPHASED = resp({
  total: 4000,
  buckets: [bk("new", 25), bk("existing", 10), bk("demolish", 4), bk("temporary", 1)],
});

describe("coverageReading — the uncoloured set is the finding, not the remainder", () => {
  it("is the SHIPPED SHAPE: 40 of 4,000 phased, and it says so in a warning tone", () => {
    const c = coverageReading(MOSTLY_UNPHASED);
    expect(c.kind).toBe("partial");
    expect(c.tone).toBe("warn");
    expect(c.text).toContain("40 of 4000");
    expect(c.text).toContain("1%");          // Math.round(40/4000*100)
    expect(c.text).toContain("other 3960");
  });

  it("calls a loaded model that carries NOTHING a finding, in a failing tone", () => {
    const c = coverageReading(resp({ total: 4000, colored: 0, unset: 4000, buckets: [] }));
    expect(c.kind).toBe("none");
    expect(c.tone).toBe("bad");
    expect(c.text).toContain("NOTHING carries Massing_Phasing.Status");
    expect(c.text).toContain("4000");
  });

  it("does NOT confuse that with an empty index — no model loaded is not a finding", () => {
    const c = coverageReading(resp({ total: 0, colored: 0, unset: 0, buckets: [] }));
    expect(c.kind).toBe("none");
    expect(c.tone).toBe("");                 // no tone: there is nothing to be alarmed about yet
    expect(c.text).toContain("load a model first");
    expect(c.text).not.toContain("NOTHING carries");
  });

  it("is `ok` only when every element carries the property", () => {
    const c = coverageReading(resp({ total: 30, buckets: [bk("new", 30)] }));
    expect(c.kind).toBe("full");
    expect(c.tone).toBe("ok");
    expect(c.text).toContain("All 30");
  });

  it("reports the engine's `unset`, never `total - colored`", () => {
    // A response whose three numbers disagree: the consumer must quote the field, because the day
    // they diverge the engine's answer is the one a bug report is about.
    const c = coverageReading(resp({ total: 100, colored: 10, unset: 7, buckets: [bk("new", 10)] }));
    expect(c.text).toContain("other 7");
    expect(c.text).not.toContain("other 90");
  });

  it("does not round a real gap away to 100%", () => {
    const c = coverageReading(resp({ total: 10000, colored: 9999, unset: 1,
                                     buckets: [bk("new", 9999)] }));
    expect(c.kind).toBe("partial");          // 100% to the nearest point, and still not `full`
    expect(c.tone).toBe("warn");
    expect(c.text).toContain("other 1");
  });
});

/**
 * A NUMERIC response: binned ranges, ascending, and the largest bin in the middle.
 *
 * It exists because the first `bucketRows` sorted by count and no test could see it — the
 * categorical fixture above is already descending, so the reorder was a no-op on it. Here the
 * engine's order and a count order are different lists, so one of them is being asserted.
 */
const NUMERIC_BINS = resp({
  prop: "Qto_WallBaseQuantities.NetArea", kind: "numeric", total: 120,
  buckets: [bk("0 – 5", 4), bk("5 – 10", 60), bk("10 – 15", 11)],
});

describe("bucketRows", () => {
  it("keeps a numeric response's ASCENDING RANGES — a count sort would scramble the axis", () => {
    expect(bucketRows(NUMERIC_BINS).map((r) => r.k))
      .toEqual(["0 – 5", "5 – 10", "10 – 15"]);
  });

  it("keeps a categorical response's most-common order, with `Other` still last", () => {
    const r = resp({ total: 100, buckets: [bk("new", 30), bk("existing", 20), bk("Other", 25)] });
    expect(bucketRows(r).map((x) => x.k)).toEqual(["new", "existing", "Other"]);
  });

  it("states each share as a share of the COLOURED set, not of the model", () => {
    const rows = bucketRows(MOSTLY_UNPHASED);
    expect(rows[0]!.v).toBe("25 · 63% of the coloured");   // 25/40, not 25/4000
    expect(rows[0]!.v).toContain("of the coloured");
  });

  it("carries the guids through so the row can isolate them", () => {
    expect(bucketRows(MOSTLY_UNPHASED)[0]!.guids).toHaveLength(25);
  });

  it("drops the share rather than dividing by zero when nothing is coloured", () => {
    const rows = bucketRows(resp({ total: 5, colored: 0, unset: 5, buckets: [bk("new", 0)] }));
    expect(rows[0]!.v).toBe("0");
  });

  it("does not mutate the response it was handed", () => {
    const r = NUMERIC_BINS;
    bucketRows(r);
    expect(r.buckets.map((b) => b.label)).toEqual(["0 – 5", "5 – 10", "10 – 15"]);
  });
});

/** ---- the route these fixtures describe -------------------------------------------------------- */

describe("the engine", () => {
  const SRC = readFileSync("../../services/api/src/aec_api/routers/properties.py", "utf8");

  it("still returns the three coverage numbers this module reads", () => {
    expect(SRC).toContain('"total": len(idx), "colored": colored, "unset": len(idx) - colored');
  });

  it("counts `colored` from the buckets, which is why a bucket share is a share of it", () => {
    expect(SRC).toContain('colored = sum(len(b["guids"]) for b in buckets)');
  });

  it("emits numeric bins in ASCENDING range order, which `bucketRows` must not re-sort", () => {
    expect(SRC).toContain("for i in range(n):");
    expect(SRC).toContain('f"{lo + step * i:.3g} – {lo + step * (i + 1):.3g}"');
  });

  it("emits categorical buckets most-common first with `Other` APPENDED — likewise", () => {
    expect(SRC).toContain("Counter(str(v) for v in vals.values()).most_common(24)");
    expect(SRC).toContain('buckets.append({"label": "Other", "guids": other})');
  });

  it("omits an element with no value from every bucket — the unset set is not bucket 'Other'", () => {
    // `Other` holds values outside the top 24, not the absent ones: the filter is upstream of it.
    expect(SRC).toContain('if v not in (None, ""):');
  });
});

/** ---- the live consumer, driven through the real panel ----------------------------------------- */

function harness(c: ColorBy) {
  const isolated: string[][] = [];
  const api = {
    phasing: vi.fn(async () => ({
      total: c.total, phased: c.colored, prop: c.prop,
      counts: { NEW: 0, EXISTING: 0, DEMOLISH: 0, TEMPORARY: 0, UNSET: c.unset },
    })),
    colorBy: vi.fn(async () => c),
  };
  const deps = {
    toolBtn2: (label: string, onClick: () => void) => {
      const b = document.createElement("button");
      b.textContent = label;
      b.onclick = onClick;
      return b;
    },
    api: api as unknown as ModelStateDeps["api"],
    pid: "p1",
    projectId: "p1",
    notify: vi.fn(),
    selectedGuid: () => null,
    layerMgr: { isolateGuids: (g: string[]) => { isolated.push(g); return Promise.resolve(); } } as
      unknown as ModelStateDeps["layerMgr"],
    container: document.createElement("div"),
    authorAndReload: vi.fn(async () => ({ applied: true, refused: false })),
    waitForPublish: vi.fn(async () => "done"),
    loadProjectModel: vi.fn(async () => true),
    reloadModelPins: vi.fn(async () => undefined),
  } satisfies ModelStateDeps;
  return { deps, isolated, api };
}

const flush = () => new Promise((res) => setTimeout(res, 0));
const notes = () => [...document.querySelectorAll(".result-note")].map((n) => ({
  text: n.textContent ?? "", cls: n.className,
}));
const btn = (text: string) =>
  [...document.querySelectorAll("button")].find((b) => b.textContent?.includes(text));

/** Open the phasing panel, then the "Isolate a phase in 3D" sub-panel it builds. */
async function openIsolate(c: ColorBy) {
  document.body.replaceChildren();
  const h = harness(c);
  await openPhasingPanel(h.deps);
  btn("Isolate a phase in 3D")!.click();
  await flush();
  return h;
}

describe("openPhasingPanel — the isolate sub-panel", () => {
  it("states the unphased share on screen, which is the whole of COLOR-UNSET", async () => {
    await openIsolate(MOSTLY_UNPHASED);
    const cov = notes().find((n) => n.text.includes("of 4000"));
    expect(cov).toBeDefined();
    expect(cov!.text).toContain("other 3960");
    expect(cov!.cls).toContain("warn");
  });

  it("still offers a row per phase, largest first, and isolates that bucket's guids", async () => {
    const h = await openIsolate(MOSTLY_UNPHASED);
    const labels = [...document.querySelectorAll("button")]
      .map((b) => b.textContent ?? "").filter((t) => t.startsWith("◎ "));
    expect(labels[0]).toContain("new · 25");
    expect(labels).toHaveLength(4);
    btn("◎ new ·")!.click();
    expect(h.isolated[0]).toHaveLength(25);
  });

  it("says nothing is phased AND why the list is empty — two different sentences", async () => {
    await openIsolate(resp({ total: 4000, colored: 0, unset: 4000, buckets: [] }));
    const texts = notes().map((n) => n.text);
    expect(texts.some((t) => t.includes("NOTHING carries"))).toBe(true);
    expect(texts.some((t) => t.includes("tag phases above"))).toBe(true);
  });

  it("reports the coverage in a passing tone only when the model is fully phased", async () => {
    await openIsolate(resp({ total: 30, buckets: [bk("new", 20), bk("existing", 10)] }));
    const cov = notes().find((n) => n.text.includes("All 30"))!;
    expect(cov.cls).toContain("ok");
    expect(cov.cls).not.toContain("warn");
  });

  it("escapes the property name — `prop` reaches innerHTML through the note", async () => {
    await openIsolate(resp({ prop: "<img src=x onerror=1>", total: 9, colored: 0, unset: 9,
                             buckets: [] }));
    expect(document.querySelector(".result-note")!.innerHTML).not.toContain("<img");
    expect(document.body.querySelector("img")).toBeNull();
  });
});
