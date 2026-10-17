import { describe, expect, it, vi } from "vitest";

import type { LayoutDeps, LayoutVerify } from "./layoutTool";
import {
  layoutButton, parseSetoutCsv, splitCsvLine, verifyReading, verifyRows,
} from "./layoutTool";

/**
 * LAYOUT-RENUMBER, the screen half — the field-layout panel promised an upload and had none.
 *
 * The engine half is `services/api/test_layout_renumber.py`, which replays the pre-fix matcher and
 * requires it to fabricate two grid-bay deviations before the gate may report. This file asserts the
 * client: that the parse counts what it could not read, that the Description column travels so the
 * server can match by GlobalId, and that `comparable === false` is answered before anything about
 * tolerance.
 */

/** The exporter's own output: `Point,Easting,Northing,Elevation,Description`, GlobalId after a `|`. */
const EXPORT = [
  "Point,Easting,Northing,Elevation,Description",
  "P1,100.0,200.0,0.0,COL-C-A|1aaaaaaaaaaaaaaaaaaaaa",
  "P2,106.0,200.0,0.0,COL-C-B|2bbbbbbbbbbbbbbbbbbbbb",
].join("\n");

describe("splitCsvLine", () => {
  it("keeps a comma inside a quoted Description, which an element name can carry", () => {
    expect(splitCsvLine('P1,1,2,3,"COL-Bay A, left|1aaaaaaaaaaaaaaaaaaaaa"'))
      .toEqual(["P1", "1", "2", "3", "COL-Bay A, left|1aaaaaaaaaaaaaaaaaaaaa"]);
  });

  it("unescapes a doubled quote rather than dropping it", () => {
    expect(splitCsvLine('A,"say ""hi""",B')).toEqual(["A", 'say "hi"', "B"]);
  });

  it("keeps an empty trailing cell, so column positions do not shift", () => {
    expect(splitCsvLine("P1,1,2,3,")).toHaveLength(5);
  });
});

describe("parseSetoutCsv", () => {
  it("reads the exporter's own file by header, and keeps the Description", () => {
    const p = parseSetoutCsv(EXPORT);
    expect(p.rows).toHaveLength(2);
    expect(p.basis).toBe("header");
    expect(p.hasDescription).toBe(true);
    expect(p.rows[0]).toEqual({ number: "P1", e: 100, n: 200, z: 0,
                                description: "COL-C-A|1aaaaaaaaaaaaaaaaaaaaa" });
    expect(p.skipped).toBe(0);
  });

  it("COUNTS a line it cannot read instead of dropping it", () => {
    // The defect one layer earlier than the server's: a survey file read halfway that then reports
    // no deviations is a clean as-built over a subset nobody declared.
    const p = parseSetoutCsv([
      "Point,Easting,Northing,Elevation,Description",
      "P1,100.0,200.0,0.0,COL-A|1aaaaaaaaaaaaaaaaaaaaa",
      "P2,bad,200.0,0.0,COL-B|2bbbbbbbbbbbbbbbbbbbbb",
      "P3,100.0,,0.0,COL-C|3cccccccccccccccccccccc",
    ].join("\n"));
    expect(p.rows).toHaveLength(1);
    expect(p.skipped).toBe(2);
    expect(p.skippedLines).toEqual([3, 4]);
  });

  it("does not count a blank line as a dropped shot", () => {
    expect(parseSetoutCsv(`${EXPORT}\n\n\n`).skipped).toBe(0);
  });

  it("reports that a headerless file's column order was ASSUMED", () => {
    const p = parseSetoutCsv("P1,100.0,200.0,0.0,COL-A|1aaaaaaaaaaaaaaaaaaaaa");
    expect(p.basis).toBe("assumed PENZD");
    expect(p.rows[0]!.e).toBe(100);
    // PENZD and PNEZD differ only in column 2 vs 3, so assuming wrong swaps every pair silently.
    const q = parseSetoutCsv("P1,100.0,200.0,0.0,COL-A|1aaaaaaaaaaaaaaaaaaaaa", "PNEZD");
    expect(q.basis).toBe("assumed PNEZD");
    expect(q.rows[0]!.e).toBe(200);
    expect(q.rows[0]!.n).toBe(100);
  });

  it("prefers the HEADER over the assumption when the file disagrees with it", () => {
    // A PNEZD export read with a PENZD assumption must still come out right, because the header says.
    const p = parseSetoutCsv([
      "Point,Northing,Easting,Elevation,Description",
      "P1,200.0,100.0,0.0,COL-A|1aaaaaaaaaaaaaaaaaaaaa",
    ].join("\n"), "PENZD");
    expect(p.basis).toBe("header");
    expect(p.rows[0]!.e).toBe(100);
    expect(p.rows[0]!.n).toBe(200);
  });

  it("does not mistake a headerless first row for a header", () => {
    // The sniff is "the coordinate columns are not numbers", not "the row mentions a column name" —
    // a description beginning with the word 'Point' would fool the latter and lose a shot.
    const p = parseSetoutCsv("Point-1,100.0,200.0,0.0,Easting pier|1aaaaaaaaaaaaaaaaaaaaa");
    expect(p.rows).toHaveLength(1);
    expect(p.basis).toBe("assumed PENZD");
  });

  it("handles a tab-delimited file, which the exporter also offers", () => {
    const p = parseSetoutCsv("Point\tEasting\tNorthing\tElevation\tDescription\n"
      + "P1\t100.0\t200.0\t0.0\tCOL-A|1aaaaaaaaaaaaaaaaaaaaa");
    expect(p.rows).toHaveLength(1);
    expect(p.rows[0]!.e).toBe(100);
  });

  it("accepts a shot keyed only by its Description, with no point number", () => {
    // The GlobalId is the stable key, so a file carrying only that is MORE reliable, not less.
    const p = parseSetoutCsv("Point,Easting,Northing,Elevation,Description\n"
      + ",100.0,200.0,0.0,COL-A|1aaaaaaaaaaaaaaaaaaaaa");
    expect(p.rows).toHaveLength(1);
    expect(p.rows[0]!.number).toBe("");
    expect(p.hasDescription).toBe(true);
  });

  it("omits `description` entirely when the column is absent, rather than sending an empty one", () => {
    const p = parseSetoutCsv("P1,100.0,200.0,0.0");
    expect(p.rows[0]).toEqual({ number: "P1", e: 100, n: 200, z: 0 });
    expect(p.hasDescription).toBe(false);
  });
});

const mk = (o: Partial<LayoutVerify> = {}): LayoutVerify => {
  const checked = o.checked ?? 2;
  const design = o.design_points ?? 2;
  return {
    tolerance_m: o.tolerance_m ?? 0.02, checked, in_tolerance: o.in_tolerance ?? checked,
    max_deviation_m: o.max_deviation_m ?? 0.0,
    out_of_tolerance: o.out_of_tolerance ?? [], deviations: o.deviations ?? [],
    design_points: design, shots_supplied: o.shots_supplied ?? checked,
    matched_on_guid: o.matched_on_guid ?? checked, matched_on_number: o.matched_on_number ?? 0,
    number_matched_points: o.number_matched_points ?? [],
    unshot: o.unshot ?? design - checked, unshot_numbers: o.unshot_numbers ?? [],
    unmatched_shots: o.unmatched_shots ?? 0, unmatched_numbers: o.unmatched_numbers ?? [],
    coverage_pct: o.coverage_pct ?? Math.round((1000 * checked) / (design || 1)) / 10,
    comparable: o.comparable ?? checked > 0, note: o.note ?? "",
  };
};

const OOT = [{ number: "P3", guid: "g3", ifc_class: "IfcFooting", deviation_m: 0.1 }];

describe("verifyReading — coverage before tolerance", () => {
  it("refuses to let an unmatched file read as a clean as-built", () => {
    const r = verifyReading(mk({ checked: 0, design_points: 400, shots_supplied: 120,
                                 comparable: false, coverage_pct: 0 }));
    expect(r.kind).toBe("unmatched");
    expect(r.tone).toBe("bad");
    expect(r.headline).toContain("NOTHING MATCHED");
    expect(r.headline).toContain("120 shot(s)");
    expect(r.headline).toContain("400 design point(s)");
    expect(r.detail).toContain("not a clean as-built");
  });

  it("names the missing Description column when that is why nothing matched", () => {
    const parsed = parseSetoutCsv("Q1,1,2,3");
    const r = verifyReading(mk({ checked: 0, comparable: false }), parsed);
    expect(r.detail).toContain("no Description column");
    // ...and does NOT say that when the file did carry one — the cause is then something else
    const r2 = verifyReading(mk({ checked: 0, comparable: false }), parseSetoutCsv(EXPORT));
    expect(r2.detail).not.toContain("no Description column");
  });

  it("says a tolerance verdict is about the points that were COMPARED", () => {
    const r = verifyReading(mk({ checked: 12, design_points: 400, unshot: 388, coverage_pct: 3 }));
    expect(r.kind).toBe("partial");
    expect(r.tone).toBe("warn");
    expect(r.headline).toContain("All 12 compared point(s)");
    expect(r.detail).toContain("12 of 400");
    expect(r.detail).toContain("388 never were");
    expect(r.detail).toContain("not about the setout");
  });

  it("calls out a positional match even when everything is in tolerance", () => {
    const r = verifyReading(mk({ matched_on_guid: 0, matched_on_number: 2 }));
    expect(r.kind).toBe("complete");
    expect(r.tone).toBe("ok");
    expect(r.detail).toContain("matched by point number only");
    expect(r.detail).toContain("position in one export");
  });

  it("a real finding outranks the coverage gap — a deviation is not a warning", () => {
    const r = verifyReading(mk({ checked: 12, design_points: 400, unshot: 388,
                                 in_tolerance: 11, out_of_tolerance: OOT, max_deviation_m: 0.1 }));
    expect(r.tone).toBe("bad");
    expect(r.headline).toContain("1 point(s) out of tolerance");
    expect(r.headline).toContain("100 mm");
    expect(r.headline).toContain("20 mm");
    expect(r.detail).toContain("12 of 400");         // the gap is still stated
  });

  it("counts supplied shots that matched nothing, not only unshot design points", () => {
    const r = verifyReading(mk({ checked: 2, design_points: 2, unmatched_shots: 7 }));
    expect(r.kind).toBe("partial");
    expect(r.detail).toContain("7 supplied shot(s) matched no design point");
  });

  it("is `complete` only when both sides of the join are exhausted", () => {
    expect(verifyReading(mk()).kind).toBe("complete");
    expect(verifyReading(mk({ unshot: 1 })).kind).toBe("partial");
    expect(verifyReading(mk({ unmatched_shots: 1 })).kind).toBe("partial");
  });
});

describe("verifyRows", () => {
  it("reports both sides of the join and the two match keys separately", () => {
    const rows = verifyRows(mk({ checked: 3, design_points: 10, shots_supplied: 5,
                                 matched_on_guid: 2, matched_on_number: 1, unshot: 7,
                                 unmatched_shots: 2 }));
    const get = (k: string) => rows.find((r) => r.k === k)?.v;
    expect(get("Design setout points")).toBe("10");
    expect(get("Shots supplied")).toBe("5");
    expect(get("Matched by GlobalId")).toBe("2");
    expect(get("Matched by number only")).toBe("1");
    expect(get("Design points never shot")).toBe("7");
    expect(get("Shots matching no point")).toBe("2");
  });

  it("names where the columns came from, and the unreadable lines when there are any", () => {
    const parsed = parseSetoutCsv("Point,Easting,Northing,Elevation,Description\nP1,x,2,3,d");
    const rows = verifyRows(mk(), parsed);
    expect(rows.find((r) => r.k === "Columns read from")?.v).toBe("header");
    expect(rows.find((r) => r.k === "File lines unreadable")?.v).toContain("1");
  });

  it("omits the unreadable row when the file read cleanly", () => {
    const rows = verifyRows(mk(), parseSetoutCsv(EXPORT));
    expect(rows.some((r) => r.k === "File lines unreadable")).toBe(false);
  });
});

/** ---- the button, driven end to end ------------------------------------------------------------ */

function harness(points: { count: number; by_class: Record<string, number> }, v: LayoutVerify | Error) {
  document.body.replaceChildren();
  const sent: unknown[] = [];
  const api = {
    layoutPoints: vi.fn(async () => points),
    layoutVerify: vi.fn(async (_pid: string, measured: unknown) => {
      sent.push(measured);
      if (v instanceof Error) throw v;
      return v;
    }),
    layoutCsvUrl: () => "#csv",
    layoutDxfUrl: () => "#dxf",
  };
  const outText: string[] = [];
  const deps = {
    api: api as unknown as LayoutDeps["api"],
    pid: "p1",
    container: document.createElement("div"),
    toolBtn2: (label: string, onClick: () => void) => {
      const b = document.createElement("button"); b.textContent = label; b.onclick = onClick; return b;
    },
    withLoading: (async <T,>(_h: HTMLElement, _l: string, fn: () => Promise<T>) => fn()) as
      LayoutDeps["withLoading"],
    toast: vi.fn(),
    showResult: (_t: string, render: (b: HTMLElement) => void) => {
      const b = document.createElement("div"); b.className = "result-body";
      document.body.appendChild(b); render(b);
    },
    resultNote: (html: string, kind?: string) => {
      const d = document.createElement("div");
      d.className = `result-note ${kind ?? ""}`; d.innerHTML = html; return d;
    },
    kvTable: (rows: { k: string; v: string }[]) => {
      const t = document.createElement("table"); t.className = "result-table";
      t.innerHTML = rows.map((r) => `<tr><th>${r.k}</th><td>${r.v}</td></tr>`).join(""); return t;
    },
    setOut: (t: string) => outText.push(t),
  } satisfies LayoutDeps;
  return { deps, api, sent, outText };
}

const flush = () => new Promise((res) => setTimeout(res, 0));
const text = () => document.body.textContent ?? "";
const POINTS = { count: 65, by_class: { IfcColumn: 64, IfcWall: 1 } };

async function open(v: LayoutVerify | Error) {
  const h = harness(POINTS, v);
  const b = layoutButton(h.deps);
  document.body.appendChild(b);
  b.click();
  await flush();
  return h;
}

/** Drive the file input the way the browser does — the handler reads `file.text()`. */
async function upload(csv: string) {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
  Object.defineProperty(input, "files", {
    value: [{ name: "survey.csv", text: async () => csv }], configurable: true,
  });
  input.onchange!(new Event("change"));
  await flush();
  return input;
}

describe("layoutButton", () => {
  it("still exports the setout — the half that already worked", async () => {
    await open(mk());
    expect(text()).toContain("65");
    expect(document.querySelectorAll("a.file-btn")).toHaveLength(3);
    expect(text()).toContain("Keep the Description column");
  });

  it("OFFERS THE UPLOAD the panel's copy had always promised", async () => {
    await open(mk());
    expect(document.querySelector('input[type="file"]')).not.toBeNull();
  });

  it("sends the Description column through, so the server can match by GlobalId", async () => {
    const h = await open(mk());
    await upload(EXPORT);
    const sent = h.sent[0] as { description?: string }[];
    expect(sent).toHaveLength(2);
    expect(sent[0]!.description).toContain("|1aaaaaaaaaaaaaaaaaaaaa");
  });

  it("renders the coverage and the counts, not just the tolerance verdict", async () => {
    await open(mk({ checked: 12, design_points: 400, unshot: 388, coverage_pct: 3 }));
    await upload(EXPORT);
    expect(text()).toContain("12 of 400");
    expect(text()).toContain("Design points never shot");
    expect(text()).toContain("Matched by GlobalId");
  });

  it("shows an unmatched file as a failure, never as a pass", async () => {
    await open(mk({ checked: 0, comparable: false, design_points: 400,
                              shots_supplied: 9, coverage_pct: 0 }));
    await upload(EXPORT);
    expect(text()).toContain("NOTHING MATCHED");
    const note = [...document.querySelectorAll(".result-note")]
      .find((n) => n.textContent?.includes("NOTHING MATCHED"))!;
    expect(note.className).toContain("bad");
    expect(note.className).not.toContain("ok");
  });

  it("refuses an unreadable file before calling the server at all", async () => {
    const h = await open(mk());
    await upload("garbage\nmore garbage");
    expect(h.api.layoutVerify).not.toHaveBeenCalled();
    expect(text()).toContain("Could not read a single shot");
  });

  it("reports a server refusal in the panel rather than silently doing nothing", async () => {
    await open(new Error("no source IFC"));
    await upload(EXPORT);
    expect(text()).toContain("no source IFC");
  });

  it("escapes the file name, which is user-supplied text in innerHTML", async () => {
    await open(mk());
    const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
    Object.defineProperty(input, "files", {
      value: [{ name: "<img src=x onerror=1>.csv", text: async () => "garbage" }],
      configurable: true,
    });
    input.onchange!(new Event("change"));
    await flush();
    expect(document.body.querySelector("img")).toBeNull();
  });
});
