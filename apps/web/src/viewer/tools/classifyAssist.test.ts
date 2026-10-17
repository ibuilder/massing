import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { ClassifyCoverage, ClassifyPlan, ClassifyProposals, ProposalRow }
  from "../../api/classificationRef";
import {
  REVIEW_ROW_CAP, coverageReading, coverageRows, planReading, proposalReading,
  renderClassifyCard, reviewRows, rowLabel, unmappedGuids,
} from "./classifyAssist";

/**
 * CLASSIFY-DARK, the screen half.
 *
 * The engine (`services/api/src/aec_api/classify_assist.py`) is careful: it returns `declared`,
 * `proposable` and `unmapped` separately, and `classified_pct` counts only the first. This file
 * asserts the CONSUMER — that the three are never collapsed into one backlog, that a page of rows
 * is never printed as a total, and that `apply_plan`'s `count` is never shown without `skipped`.
 */

const cov = (o: Partial<ClassifyCoverage> = {}): ClassifyCoverage => ({
  system: "masterformat",
  system_name: "CSI MasterFormat (US/CA)",
  default_bucket: { code: "01 00 00", title: "General Requirements" },
  declared_supplied: true,
  total: 100, declared: 4, classified_pct: 4,
  proposable: 60, unmapped: 36,
  by_basis: { declared: 4, keyword: 18, class_map: 42, unmapped: 36 },
  headline: "4.0% of 100 element(s) carry a masterformat code in the model",
  counts_only_declared: "classified_pct counts only codes the MODEL declares",
  unmapped_warning: "36 element(s) have no entry in the masterformat class map",
  ...o,
});

const row = (o: Partial<ProposalRow> = {}): ProposalRow => ({
  guid: o.guid ?? "g1", ifc_class: "IfcWall", name: "W-01", type_name: null,
  basis: "keyword", code: "09 20 00", title: "Plaster & Gypsum Board", confidence: "medium",
  evidence: "the element's own name/type matches /partition/",
  ...o,
});

const props = (o: Partial<ClassifyProposals> = {}): ClassifyProposals => ({
  ...cov(), rows: o.rows ?? [row()], returned: o.returned ?? 1, matching: o.matching ?? 1,
  truncated: o.truncated ?? false, truncation_note: o.truncation_note ?? null,
  ...o,
});

describe("coverageReading — three counts that only mean something together", () => {
  it("states the declared/proposable/unmapped SPLIT in every branch", () => {
    // A reader given only the percentage cannot recover the split, and the two halves of the
    // remainder are different instructions: one is reviewable, the other is not fixable here.
    // ...WHEREVER THERE IS A REMAINDER TO SPLIT. `full` is excluded on purpose rather than by
    // weakening the pattern: with `declared === total` both other counts are zero and there is no
    // split to state, so demanding the words there would only teach the next reader to loosen the
    // assertion. The `full` branch has its own test below.
    const split = [cov(), cov({ unmapped: 0, proposable: 96 }), cov({ declared_supplied: false })];
    expect(split.every((c) => c.declared < c.total)).toBe(true);
    for (const c of split) {
      const r = coverageReading(c);
      expect(`${r.headline} ${r.detail}`).toMatch(/\d+ declared/);
      expect(`${r.headline} ${r.detail}`).toMatch(/\d+ proposable/);
      expect(`${r.headline} ${r.detail}`).toMatch(/\d+ unmapped/);
    }
  });

  it("ranks a FLOOR above every other reading — 0% unread is not 0% classified", () => {
    // `declared_supplied: false` means the classification associations were never read. A 0% figure
    // then means "nobody looked", which is the opposite instruction to "nothing is classified".
    const r = coverageReading(cov({ declared_supplied: false, declared: 0, classified_pct: 0,
                                    unmapped: 36 }));
    expect(r.kind).toBe("floor");
    expect(r.headline).toContain("FLOOR");
    expect(r.tone).toBe("");          // neither a pass nor a finding
  });

  it("ranks UNMAPPED above proposable, and still states the proposable count", () => {
    const r = coverageReading(cov());
    expect(r.kind).toBe("unmapped");
    expect(r.tone).toBe("bad");
    expect(r.headline).toContain("36 ");
    expect(r.headline).toContain("cannot be proposed one at all");
    expect(r.detail).toContain("60 proposable");
  });

  it("names the DEFAULT BUCKET, which is the whole reason the engine exists", () => {
    // `classification.classify` returns it for an unmapped class and the return type cannot express
    // the difference — so an estimate prices them as General Requirements and reports complete.
    const r = coverageReading(cov());
    expect(r.detail).toContain("01 00 00");
    expect(r.detail).toContain("General Requirements");
  });

  it("is `proposable` with a warn tone when everything undeclared has a proposal", () => {
    const r = coverageReading(cov({ unmapped: 0, proposable: 96 }));
    expect(r.kind).toBe("proposable");
    expect(r.tone).toBe("warn");
    expect(r.headline).toContain("96 can be proposed one");
  });

  it("is `full` only when the MODEL declares every element", () => {
    const r = coverageReading(cov({ declared: 100, proposable: 0, unmapped: 0,
                                    classified_pct: 100, unmapped_warning: null }));
    expect(r.kind).toBe("full");
    expect(r.tone).toBe("ok");
    expect(r.detail).toContain("Nothing here is a guess");
  });

  it("says there is nothing to classify rather than reporting 0%", () => {
    const r = coverageReading(cov({ total: 0, declared: 0, proposable: 0, unmapped: 0,
                                    classified_pct: null, unmapped_warning: null }));
    expect(r.kind).toBe("empty");
    expect(r.headline).toContain("No elements to classify");
    expect(r.headline).not.toContain("0.0%");
  });
});

describe("coverageRows", () => {
  it("keeps the two KINDS of proposal apart — they are not equally trustworthy", () => {
    // A keyword hit is a claim about this element. A class-map hit is true of the CLASS, so every
    // element of it got the same code and they are right or wrong together.
    const rows = coverageRows(cov());
    const get = (k: string) => rows.find((x) => x.k.includes(k))?.v;
    expect(get("own name")).toBe("18");
    expect(get("IFC class")).toBe("42");
    expect(rows.map((x) => x.v)).not.toContain("60");   // never summed into one number
  });

  it("names the default bucket as a row of its own", () => {
    expect(coverageRows(cov()).find((x) => x.k.includes("Default bucket"))?.v)
      .toBe("01 00 00 General Requirements");
  });
});

describe("proposalReading — `rows` is a page, `matching` is the total", () => {
  it("reports the PAGE against the TOTAL, never the page as the total", () => {
    // TRUNC-COUNTED exactly: three screens printed the length of a page as if it were a total.
    const r = proposalReading(props({ rows: [row(), row({ guid: "g2" })], returned: 200,
                                      matching: 918, truncated: true,
                                      truncation_note: "718 further row(s) matched and are not shown" }),
                              "class_map");
    expect(r.kind).toBe("page");
    expect(r.tone).toBe("warn");
    expect(r.headline).toContain("200 of 918");
    expect(r.detail).toContain("718 further row(s)");
  });

  it("names the BASIS in its units, because `matching` counts what matched the filter", () => {
    // A bound reported in the wrong units is worse than no bound (NOTICE-CLOCK).
    expect(proposalReading(props({ matching: 36 }), "unmapped").headline)
      .toContain("with basis `unmapped`");
    expect(proposalReading(props({ matching: 18 }), "keyword").headline)
      .toContain("with basis `keyword`");
  });

  it("says the list is the whole set only when it is", () => {
    const r = proposalReading(props({ matching: 7, returned: 7 }), "keyword");
    expect(r.kind).toBe("all");
    expect(r.detail).toContain("whole set");
  });

  it("reports an empty FILTER result with the model's split, not as an empty model", () => {
    const r = proposalReading(props({ rows: [], returned: 0, matching: 0 }), "unmapped");
    expect(r.kind).toBe("none");
    expect(r.detail).toContain("4 declared");
    expect(r.detail).toContain("36 unmapped");
  });
});

describe("reviewRows", () => {
  it("puts no-code rows first, then the class-wide guesses, then element-specific ones", () => {
    // THE FIXTURE IS DELIBERATELY NOT IN OUTPUT ORDER. A reorder is invisible to a fixture already
    // sorted — the blind spot `egressTravel.test.ts` and LAYOUT-RENUMBER each paid for once.
    const p = props({ rows: [row({ guid: "k", basis: "keyword" }),
                             row({ guid: "c", basis: "class_map" }),
                             row({ guid: "u", basis: "unmapped", code: null })] });
    expect(reviewRows(p).map((r) => r.guid)).toEqual(["u", "c", "k"]);
  });

  it("excludes DECLARED rows — they are not proposals and there is nothing to accept", () => {
    const p = props({ rows: [row({ guid: "d", basis: "declared" }), row({ guid: "k" })] });
    expect(reviewRows(p).map((r) => r.guid)).toEqual(["k"]);
  });
});

describe("unmappedGuids + rowLabel", () => {
  it("isolates only the elements nothing can price", () => {
    const p = props({ rows: [row({ guid: "a" }), row({ guid: "b", basis: "unmapped", code: null }),
                             row({ guid: "c", basis: "declared" })] });
    expect(unmappedGuids(p)).toEqual(["b"]);
  });

  it("shows the EVIDENCE, which is what makes a proposal reviewable rather than a guess", () => {
    const l = rowLabel(row({ confidence: "low", type_name: "WT-3" }));
    expect(l.detail).toContain("IfcWall");
    expect(l.detail).toContain("type WT-3");
    expect(l.detail).toContain("low confidence");
    expect(l.detail).toContain("matches /partition/");
  });

  it("falls back to the GUID when an element has no name, and says so when there is no code", () => {
    expect(rowLabel(row({ name: null, guid: "g9" })).label).toBe("g9");
    expect(rowLabel(row({ code: null, title: null })).code).toBe("— no code");
  });
});

const plan = (o: Partial<ClassifyPlan> = {}): ClassifyPlan => ({
  system: "masterformat", steps: o.steps ?? [], count: o.count ?? 0,
  skipped: o.skipped ?? [], note: "apply with POST /projects/{pid}/edit/batch",
  ...o,
});

describe("planReading — `count` is a verdict about a subset, and `skipped` is the rest", () => {
  it("states BOTH numbers on a partial plan, because the skipped would otherwise look done", () => {
    const r = planReading(plan({ count: 40, skipped: Array.from({ length: 20 }, (_, i) =>
      ({ guid: `g${i}`, reason: "already declared in the model" })) }), 60);
    expect(r.kind).toBe("partial");
    expect(r.tone).toBe("warn");
    expect(r.headline).toContain("40 step(s)");
    expect(r.headline).toContain("20 element(s) refused");
    expect(r.detail).toContain("40 of the 60");
  });

  it("collapses refusals BY REASON, commonest first", () => {
    const r = planReading(plan({ count: 1, skipped: [
      { guid: "a", reason: "already declared in the model" },
      { guid: "b", reason: "not in the proposal set" },
      { guid: "c", reason: "already declared in the model" },
    ] }), 4);
    expect(r.refusals).toEqual([
      { reason: "already declared in the model", count: 2 },
      { reason: "not in the proposal set", count: 1 },
    ]);
  });

  it("RANKS FIRST when the plan's own arithmetic does not add up", () => {
    // Every accepted GUID is a step or a refusal. If the two do not sum, the missing ones appear in
    // neither column — which reads as an ordinary partial plan, the one thing it must not be
    // mistaken for.
    const r = planReading(plan({ count: 40, skipped: [{ guid: "x", reason: "no code to apply" }] }), 60);
    expect(r.kind).toBe("unaccounted");
    expect(r.tone).toBe("bad");
    expect(r.headline).toContain("60 element(s) accepted but only 41 accounted for");
    expect(r.detail).toContain("Do not apply this plan");
  });

  it("does NOT report unaccounted when the caller deduped the way the server does", () => {
    // The route dedupes with `dict.fromkeys` before planning, so the accepted count handed here
    // must be the unique one or this check fires on a double-tick.
    const accept = [...new Set(["a", "b", "b"])];
    expect(planReading(plan({ count: 2, skipped: [] }), accept.length).kind).toBe("all");
  });

  it("refuses outright when nothing can be applied", () => {
    const r = planReading(plan({ count: 0, skipped: [{ guid: "a", reason: "no code to apply" }] }), 1);
    expect(r.kind).toBe("nothing");
    expect(r.tone).toBe("bad");
  });

  it("is `all` only when every accepted element became a step", () => {
    const r = planReading(plan({ count: 3, skipped: [] }), 3);
    expect(r.kind).toBe("all");
    expect(r.tone).toBe("ok");
    expect(r.detail).toContain("Nothing is applied until you say so");
  });
});

/** Minimal host: the readings above are pure, so only the DOM decisions need a stub. */
function deps(over: Record<string, unknown> = {}) {
  const calls: string[] = [];
  const body = document.createElement("div");
  return {
    calls, body,
    d: {
      showResult: (_t: string, render: (b: HTMLElement) => void) => { render(body); },
      resultNote: (html: string, kind = "") => {
        const n = document.createElement("div"); n.className = `note ${kind}`; n.innerHTML = html;
        return n;
      },
      kvTable: (rows: { k: string; v: string }[]) => {
        const t = document.createElement("div");
        t.textContent = rows.map((r) => `${r.k}=${r.v}`).join("|");
        return t;
      },
      toolBtn2: (label: string, onClick: () => void) => {
        const btn = document.createElement("button"); btn.textContent = label;
        btn.onclick = onClick; return btn;
      },
      esc: (v: unknown) => String(v).replace(/</g, "&lt;"),
      isolate: (g: string[]) => { calls.push(`isolate:${g.join(",")}`); },
      proposals: async () => props(),
      plan: async () => plan(),
      apply: async () => { calls.push("apply"); },
      reload: (s: string) => { calls.push(`reload:${s}`); },
      notify: (m: string) => { calls.push(`notify:${m}`); },
      ...over,
    },
  };
}

const labels = (host: HTMLElement) =>
  [...host.querySelectorAll("button")].map((b) => b.textContent ?? "");

describe("the card — the DOM decisions the pure readings cannot assert", () => {
  it("offers ONE review per basis and no unfiltered one — the page would drop the reviewable", () => {
    // `propose()` sorts `declared` first and the route pages the sorted list, so an unfiltered
    // request returns the declared rows and truncates away exactly the ones a reviewer can act on.
    const h = deps();
    renderClassifyCard(cov(), h.d as never);
    const all = labels(h.body);
    expect(all).toEqual([
      "🏷 18 named by the element's own name",
      "🧱 42 class-wide guesses",
      "⚠ 36 with no code at all",
    ]);
  });

  it("never asks for an unfiltered page — every fetch carries a basis", () => {
    const seen: (string | undefined)[] = [];
    const h = deps({ proposals: async (_s: string, b: string) => { seen.push(b); return props(); } });
    renderClassifyCard(cov(), h.d as never);
    h.body.querySelectorAll("button").forEach((b) => { b.click(); });
    expect(seen).toEqual(["keyword", "class_map", "unmapped"]);
    expect(seen.every((b) => b !== undefined)).toBe(true);
  });

  it("omits a basis the model has none of, rather than offering an empty review", () => {
    const h = deps();
    renderClassifyCard(cov({ by_basis: { declared: 4, keyword: 0, class_map: 42, unmapped: 0 },
                             proposable: 42, unmapped: 0, unmapped_warning: null }), h.d as never);
    expect(labels(h.body)).toEqual(["🧱 42 class-wide guesses"]);
  });

  it("offers no review buttons when the model is fully classified", () => {
    const h = deps();
    renderClassifyCard(cov({ declared: 100, proposable: 0, unmapped: 0, classified_pct: 100,
                             by_basis: { declared: 100, keyword: 0, class_map: 0, unmapped: 0 } }),
                       h.d as never);
    expect(labels(h.body)).toEqual([]);
  });

  it("re-reads coverage when the system changes — the SPLIT changes with the class map", () => {
    const h = deps();
    renderClassifyCard(cov(), h.d as never);
    const sel = h.body.querySelector("select")!;
    expect(sel.value).toBe("masterformat");
    sel.value = "nrm1";
    sel.dispatchEvent(new Event("change"));
    expect(h.calls).toContain("reload:nrm1");
  });

  it("WITHHOLDS the apply button when the plan does not account for what was ticked", async () => {
    // The one behavioural consequence of the `unaccounted` reading, and the only assertion here
    // that `planReading` alone cannot make.
    const h = deps({
      proposals: async () => props({ rows: [row({ guid: "a" }), row({ guid: "b" })],
                                     returned: 2, matching: 2 }),
      plan: async () => plan({ count: 1, steps: [{ recipe: "set_classification", params: {} }],
                               skipped: [] }),
    });
    renderClassifyCard(cov(), h.d as never);
    labels(h.body).forEach(() => undefined);
    h.body.querySelectorAll("button").forEach((b) => {
      if (b.textContent?.includes("named by the element")) b.click();
    });
    await Promise.resolve(); await Promise.resolve();
    h.body.querySelectorAll("input[type=checkbox]").forEach((el) => {
      const box = el as HTMLInputElement;
      box.checked = true; box.dispatchEvent(new Event("change"));
    });
    h.body.querySelectorAll("button").forEach((b) => {
      if (b.textContent?.includes("Prepare a plan")) b.click();
    });
    await Promise.resolve(); await Promise.resolve();
    // The review DID render (the row's own label is on screen) and the apply button is absent.
    // Asserting on "Isolate" instead would have been asserting the wrong thing: these two fixture
    // rows are `keyword`, so there is correctly no no-code set to isolate.
    expect(h.body.textContent).toContain("W-01");
    expect(h.body.querySelectorAll("input[type=checkbox]").length).toBe(2);
    expect(labels(h.body).join(" ")).not.toContain("Apply");
    expect(h.body.textContent).toContain("accepted but only 1 accounted for");
  });

  it("disables ticking a row with no code — there is nothing to accept", async () => {
    const h = deps({
      proposals: async () => props({ rows: [row({ guid: "u", basis: "unmapped", code: null,
                                                  title: null })], returned: 1, matching: 1 }),
    });
    renderClassifyCard(cov(), h.d as never);
    h.body.querySelectorAll("button").forEach((b) => {
      if (b.textContent?.includes("named by the element")) b.click();
    });
    await Promise.resolve(); await Promise.resolve();
    const box = h.body.querySelector("input[type=checkbox]") as HTMLInputElement;
    expect(box.disabled).toBe(true);
  });
});

describe("the panel is WIRED — source-level, and the limit is stated", () => {
  // A render inside `if (false)` would pass this. The complement is the DOM block above.
  const HERE = dirname(fileURLToPath(import.meta.url));
  const SRC = readFileSync(resolve(HERE, "analyseSection.ts"), "utf-8");

  it("calls all THREE routes, which is what made this one capability and not three", () => {
    expect(SRC).toContain("api.classifyCoverage(pid, system)");
    expect(SRC).toContain("api.classifyProposals(pid, sys, { basis })");
    expect(SRC).toContain("api.classifyPlan(pid, accept, sys)");
  });

  it("applies the plan as ONE batch, so the model is never left half-classified", () => {
    // BATCH-DARK: a loop of single edits leaves the model in a state nobody asked for.
    expect(SRC).toContain("api.editBatch(pid, steps)");
  });

  it("keeps the card BODY out of the eager chunk, which is what the budget refuses", () => {
    expect(SRC).toContain('await import("./classifyAssist")');
    expect(SRC).not.toContain("coverageRows(");
    expect(SRC).not.toContain("proposalReading(");
    expect(SRC).not.toContain("planReading(");
  });

  it("DECLARES the response shapes, or no derivation over declarations can see them", () => {
    // CLASH-TRUNC: a re-spelled shape is a field no audit over declarations reaches, which is how
    // `truncated` went unread for months. `noRespelledShapes.test.ts` pins this tree-wide.
    const api = readFileSync(resolve(HERE, "../../api/classificationRef.ts"), "utf-8");
    expect(api).toContain("export interface ClassifyCoverage");
    expect(api).toContain("export interface ClassifyProposals extends ClassifyCoverage");
    expect(api).toContain("export interface ClassifyPlan");
    expect(api).toContain("declared_supplied: boolean");
    expect(api).toContain("matching: number");
    expect(api).toContain("skipped: { guid: string; reason: string }[]");
  });

  it("offers EXACTLY the systems the server will propose for — derived, not asserted", () => {
    // A hardcoded list of someone else's enum drifts the moment a fourth system is added: it would
    // be served and proposable and have no way to be chosen, with nothing going red. The engine
    // refuses Uniclass and OmniClass by name and `systems()` is `sorted(CLASSIFICATIONS)`, so the
    // server's own keys are the population — read here rather than restated.
    const SRV = resolve(HERE, "../../../../../services/api/src/aec_api");
    const py = readFileSync(resolve(SRV, "classification.py"), "utf-8");
    const block = py.slice(py.indexOf("CLASSIFICATIONS"), py.indexOf("def classify"));
    const catalog = [...block.matchAll(/^ {4}"([a-z0-9]+)": \{$/gm)].map((m) => m[1]!);
    // MINUS `REFUSED`, which is the proposable set rather than the catalog. Asserting against the
    // catalog alone would contradict itself the day a refused system gains a published class map:
    // it would demand the client offer a system every request for it refuses. `classify_assist`
    // had exactly that bug, found while writing this picker.
    const asst = readFileSync(resolve(SRV, "classify_assist.py"), "utf-8");
    const refBlock = asst.slice(asst.indexOf("REFUSED: dict[str, str]"), asst.indexOf("class ClassifyError"));
    const refused = [...refBlock.matchAll(/^ {4}"([a-z0-9]+)":/gm)].map((m) => m[1]!);
    expect(catalog.length, "the catalog parse found nothing — this check would pass vacuously")
      .toBeGreaterThan(0);
    // Checked for CONTENT, not for an exact list: a third refusal is a legitimate addition and a
    // reorder is none of this gate's business, but an empty or broken parse would make the
    // subtraction a silent no-op and this check vacuous.
    expect(refused, "the REFUSED parse found nothing, so the subtraction would be a no-op")
      .toEqual(expect.arrayContaining(["uniclass", "omniclass"]));
    const served = catalog.filter((k) => !refused.includes(k)).sort();
    const mod = readFileSync(resolve(HERE, "classifyAssist.ts"), "utf-8");
    const offered = [...mod.matchAll(/\["([a-z0-9]+)", "[^"]+"\]/g)].map((m) => m[1]!).sort();
    expect(offered).toEqual(served);
  });

  it("caps the tick list at a number DIFFERENT from the route's page size", () => {
    // Two bounds that cannot be mistaken for one another, and neither for the total.
    expect(REVIEW_ROW_CAP).toBe(150);
  });
});
