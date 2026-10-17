import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";

import type { CitedAnswer, CitedAnswerDeps } from "./citedAnswer";
import {
  citationReading, citeLabel, citedAnswerButton, claimRows, conflictLines, sampledClaims,
} from "./citedAnswer";

/**
 * CITED-ASK-DARK — the answer whose every claim traces to the GUIDs it came from, and nothing called
 * it.
 *
 * `/answer/cited-query` returns per-claim citations, a `coverage` fraction, `fully_cited`, the
 * INDICES of uncited claims, `matched`/`truncated`, and `conflicts` — two sources disagreeing about
 * one target, with both values and each one's provenance. Its client method was frozen as callerless.
 *
 * **The first framing of it here was wrong and that is worth keeping.** It read as the cited upgrade
 * to the shipped Project assistant; the route takes a SELECTOR, not a question, and 422s on anything
 * else. `askProject` is the natural-language door and degrades to a computed snapshot with no API
 * key. Merging them would have replaced a working NL box with a selector box. *A plausible framing
 * is the expensive kind of wrong, because nothing about it looks like a mistake.*
 */

const cite = (over: Partial<CitedAnswer["claims"][number]["citations"][number]> = {}) => ({
  source_type: "ifc" as const, document_id: null, revision: null, guid: "0aBcDeFgHiJkLmNoPqRsTu",
  sheet: null, page: null, bbox: null, record_ref: null, rule_id: null, span: null, ...over,
});

const claim = (text: string, citations: ReturnType<typeof cite>[], confidence = 0.9) =>
  ({ text, citations, confidence });

function ans(over: Partial<CitedAnswer> = {}): CitedAnswer {
  const claims = over.claims ?? [claim("40 element(s) match `IfcWall`.", [cite()])];
  const uncited = over.uncited_claims
    ?? claims.map((c, i) => (c.citations.length ? -1 : i)).filter((i) => i >= 0);
  return {
    answer: claims.map((c) => c.text).join(" "),
    claims, conflicts: [], coverage: claims.length ? (claims.length - uncited.length) / claims.length : 1,
    fully_cited: !uncited.length, uncited_claims: uncited,
    citation_count: claims.reduce((n, c) => n + c.citations.length, 0),
    source_types: { ifc: claims.reduce((n, c) => n + c.citations.length, 0) },
    note: "Every claim traces to its source", query: "IfcWall", matched: 1, truncated: false,
    ...over,
  };
}

describe("citationReading — ordered by what changes the reader's action", () => {
  it("a CONFLICT outranks everything: two sources disagree about the building", () => {
    const a = ans({
      matched: 1,
      conflicts: [{ target: "Pset_WallCommon.FireRating", values: ["1HR", "2HR"],
                    claims: [{ text: "model says 1HR", value: "1HR", citations: [cite()] },
                             { text: "spec says 2HR", value: "2HR",
                               citations: [cite({ source_type: "doc", document_id: "A-101",
                                                  sheet: "A-101", page: 4, revision: "C" })] }] }],
    });
    const r = citationReading(a);
    expect(r.kind).toBe("conflict");
    expect(r.tone).toBe("bad");
    expect(r.detail).toContain("sources DISAGREE about Pset_WallCommon.FireRating");
    expect(r.detail).toContain("states one of them");
  });

  it("names WHICH claims rest on nothing, not just how many", () => {
    const a = ans({
      matched: 1,
      claims: [claim("40 element(s) match.", [cite()]), claim("All are load-bearing.", [])],
    });
    const r = citationReading(a);
    expect(r.kind).toBe("uncited");
    expect(r.tone).toBe("warn");
    expect(r.headline).toBe("1 of 2 claim(s) rest on nothing");
    expect(r.detail).toContain("Uncited: All are load-bearing.");
  });

  it("is the SAMPLED case: every claim cited, over evidence that is a page", () => {
    // `cited_query` takes `sample: int = 25` and the route never overrides it, so a claim about
    // 1,438 elements carries 25 citations.
    const a = ans({
      matched: 1438,
      claims: [claim("1438 element(s) match `IfcDuctSegment`.",
                     Array.from({ length: 25 }, (_, i) => cite({ guid: `G${i}` })))],
    });
    const r = citationReading(a);
    expect(r.kind).toBe("partial");
    expect(r.tone).toBe("warn");
    expect(r.detail).toContain("1 claim(s) cite fewer elements than they are about");
    expect(r.detail).toContain("(1438 matched)");
    expect(r.detail).toContain("a sample, not the set");
  });

  it("mentions the selector's OWN truncation when the server reports it", () => {
    const a = ans({ matched: 5000, truncated: true,
                    claims: [claim("5000 match.", [cite(), cite({ guid: "x" })])] });
    expect(citationReading(a).detail).toContain("selector's own result was truncated");
  });

  it("is `ok` only when nothing is uncited, nothing sampled and nobody disagrees", () => {
    const a = ans({ matched: 1, claims: [claim("1 element(s) match.", [cite()])] });
    const r = citationReading(a);
    expect(r.kind).toBe("cited");
    expect(r.tone).toBe("ok");
    expect(r.headline).toBe("Fully cited");
    expect(r.detail).toContain("covers the 1 element(s)");
  });

  it("REFUSES the server's 100% on an empty answer", () => {
    // `build()` computes `coverage = … if claims else 1.0` with `fully_cited = not uncited`, so zero
    // claims come back perfectly cited and the note says so. Not reachable through this route —
    // `cited_query` always emits the match claim — but `build` is the shared contract and
    // `rfi_qa.py` is already a second caller, so the consumer has to be right for every producer.
    const a = ans({ claims: [], coverage: 1.0, fully_cited: true, uncited_claims: [],
                    citation_count: 0, answer: "" });
    expect(a.fully_cited).toBe(true);           // what the server says
    const r = citationReading(a);
    expect(r.kind).toBe("none");                // what the screen says
    expect(r.tone).toBe("");
    expect(r.tone).not.toBe("ok");
    expect(r.detail).toContain("about an empty answer");
  });

  it("carries no markup — the render escapes it and these strings hold document titles", () => {
    for (const a of [ans(), ans({ claims: [] }),
                     ans({ claims: [claim("x", [])] })]) {
      const r = citationReading(a);
      expect(`${r.headline}${r.detail}`).not.toMatch(/[<>]/);
    }
  });
});

describe("sampledClaims — keyed on `matched`, never on the cap", () => {
  it("finds a claim citing fewer than it is about", () => {
    expect(sampledClaims(ans({ matched: 100, claims: [claim("100 match.", [cite()])] }))).toEqual([0]);
  });

  it("does NOT flag a claim whose citations cover the match", () => {
    expect(sampledClaims(ans({ matched: 2, claims: [claim("2 match.", [cite(), cite()])] }))).toEqual([]);
  });

  it("does not flag an UNCITED claim as merely sampled — they are different findings", () => {
    expect(sampledClaims(ans({ matched: 9, claims: [claim("x", [])] }))).toEqual([]);
  });

  it("is independent of the number 25, so passing `sample` cannot defeat it", () => {
    const fifty = Array.from({ length: 50 }, (_, i) => cite({ guid: `G${i}` }));
    expect(sampledClaims(ans({ matched: 1438, claims: [claim("x", fifty)] }))).toEqual([0]);
    expect(sampledClaims(ans({ matched: 50, claims: [claim("x", fifty)] }))).toEqual([]);
  });
});

describe("citeLabel — a GUID and a sheet are not interchangeable", () => {
  it("labels each source type in its own terms", () => {
    expect(citeLabel(cite())).toBe("IFC 0aBcDeFg");
    expect(citeLabel(cite({ revision: "v3" }))).toBe("IFC 0aBcDeFg @v3");
    expect(citeLabel(cite({ source_type: "doc", document_id: "A-101", sheet: "A-101", page: 4,
                            revision: "C" })))
      .toBe("doc A-101 sheet A-101 p.4 rev C");
    expect(citeLabel(cite({ source_type: "record", record_ref: "RFI-012" }))).toBe("record RFI-012");
    expect(citeLabel(cite({ source_type: "rule", rule_id: "R-7" }))).toBe("rule R-7");
  });

  it("a DOCUMENT citation keeps its revision — a spec without one cites nothing checkable", () => {
    expect(citeLabel(cite({ source_type: "doc", document_id: "S-201", revision: "B" })))
      .toContain("rev B");
  });
});

describe("claimRows and conflictLines", () => {
  it("marks an uncited claim rather than showing an empty citation list", () => {
    const rows = claimRows(ans({ matched: 1, claims: [claim("Unsupported.", [])] }));
    expect(rows[0]!.v).toBe("NO citation — this claim rests on nothing");
    expect(rows[0]!.strong).toBe(true);
  });

  it("caps the citation list in the cell and says how many more there are", () => {
    const six = Array.from({ length: 6 }, (_, i) => cite({ guid: `G${i}` }));
    const v = claimRows(ans({ matched: 6, claims: [claim("6 match.", six)] }))[0]!.v;
    expect(v).toContain("6 citation(s)");
    expect(v).toContain("+2 more");
  });

  it("says on the ROW when its provenance is a sample", () => {
    const v = claimRows(ans({ matched: 900, claims: [claim("900 match.", [cite()])] }))[0]!.v;
    expect(v).toContain("a SAMPLE of the 900 it is about");
  });

  it("renders a conflict with both values and where each came from", () => {
    const [line] = conflictLines(ans({
      conflicts: [{ target: "FireRating", values: ["1HR", "2HR"],
                    claims: [{ text: "m", value: "1HR", citations: [cite({ guid: "WALL1234" })] },
                             { text: "s", value: "2HR",
                               citations: [cite({ source_type: "doc", document_id: "A-101" })] }] }],
    }));
    expect(line).toContain("FireRating: 1HR vs 2HR");
    expect(line).toContain("1HR per IFC WALL1234");
    expect(line).toContain("2HR per doc A-101");
  });

  it("says a conflicting claim cites NOTHING rather than printing an empty source", () => {
    const [line] = conflictLines(ans({
      conflicts: [{ target: "T", values: ["a", "b"],
                    claims: [{ text: "x", value: "a", citations: [] },
                             { text: "y", value: "b", citations: [cite()] }] }],
    }));
    expect(line).toContain("a per nothing");
  });
});

/** **The engine side, read rather than assumed** — the two facts the reading rests on are in Python. */
describe("the contract this reading is about", () => {
  const SRC = readFileSync("../../services/api/src/aec_api/cited_answer.py", "utf8");

  it("scores an EMPTY claim list as perfectly cited — the branch the reading refuses", () => {
    expect(SRC).toContain("coverage = round(len(cited) / len(claims), 3) if claims else 1.0");
    expect(SRC).toContain('"fully_cited": not uncited,');
  });

  it("samples a claim's citations, so provenance and count are different sizes", () => {
    expect(SRC).toContain("sample: int = 25");
    expect(SRC).toContain("guids[:sample]");
  });

  it("surfaces a conflict when one target carries differing values", () => {
    expect(SRC).toContain("if len(values) > 1:");
    expect(SRC).toContain('"conflicts": conflicts,');
  });

  it("is a SHARED contract with a second producer, which is why the empty branch matters", () => {
    const RFI = readFileSync("../../services/api/src/aec_api/rfi_qa.py", "utf8");
    expect(RFI).toContain("ca.build(claims)");
  });
});

/** ---- the render, through the real button ----------------------------------------------------- */

function harness(a: CitedAnswer | Error) {
  const calls: unknown[] = [];
  const api = {
    citedQuery: vi.fn(async (_pid: string, q: string, prop?: string) => {
      calls.push({ q, prop });
      if (a instanceof Error) throw a;
      return a;
    }),
  };
  const notify = vi.fn();
  const deps = {
    toolBtn2: (label: string, onClick: () => void) => {
      const b = document.createElement("button");
      b.textContent = label; b.onclick = onClick;
      return b;
    },
    api: api as unknown as CitedAnswerDeps["api"],
    pid: "p1",
    container: document.createElement("div"),
    notify,
  } satisfies CitedAnswerDeps;
  return { deps, calls, notify };
}

const flush = () => new Promise((r) => setTimeout(r, 0));
const notes = () => [...document.querySelectorAll(".result-note")].map((n) => ({
  text: n.textContent ?? "", cls: n.className,
}));
const inputs = () => [...document.querySelectorAll<HTMLInputElement>("input.portal-filter")];
const askBtn = () =>
  [...document.querySelectorAll("button")].find((b) => b.textContent === "Ask")!;

async function open(a: CitedAnswer | Error, sel?: string, prop?: string) {
  document.body.replaceChildren();
  const h = harness(a);
  const b = citedAnswerButton(h.deps);
  document.body.appendChild(b);
  b.click();
  await flush();
  if (sel !== undefined) inputs()[0]!.value = sel;
  if (prop !== undefined) inputs()[1]!.value = prop;
  askBtn().click();
  await flush();
  return h;
}

describe("the rendered cited answer", () => {
  it("renders the answer, then the verdict beside it", async () => {
    await open(ans({ matched: 1, claims: [claim("1 element(s) match `IfcWall`.", [cite()])] }));
    const texts = notes().map((n) => n.text);
    expect(texts.some((t) => t.includes("1 element(s) match"))).toBe(true);
    const verdict = notes().find((n) => n.text.includes("Fully cited"))!;
    expect(verdict.cls).toContain("ok");
  });

  it("renders a conflict as its OWN note, in a bad tone", async () => {
    await open(ans({
      matched: 1,
      conflicts: [{ target: "FireRating", values: ["1HR", "2HR"],
                    claims: [{ text: "m", value: "1HR", citations: [cite({ guid: "WALL1234" })] },
                             { text: "s", value: "2HR",
                               citations: [cite({ source_type: "doc", document_id: "A-101" })] }] }],
    }));
    const c = notes().find((n) => n.text.includes("FireRating: 1HR vs 2HR"))!;
    expect(c).toBeDefined();
    expect(c.cls).toContain("bad");
  });

  it("sends the selector AND the optional property, and nothing when the selector is blank", async () => {
    const h = await open(ans(), "IfcDuctSegment & storey=L2", "Pset_DuctSegmentTypeCommon.Shape");
    expect(h.calls).toEqual([{ q: "IfcDuctSegment & storey=L2",
                               prop: "Pset_DuctSegmentTypeCommon.Shape" }]);
    const h2 = await open(ans(), "   ");
    expect(h2.calls).toEqual([]);
    expect(h2.notify).toHaveBeenCalledWith("enter a selector first", "info");
  });

  it("omits the property rather than sending an empty string", async () => {
    const h = await open(ans(), "IfcWall", "");
    expect(h.calls).toEqual([{ q: "IfcWall", prop: undefined }]);
  });

  it("shows a 422 selector error in place of an answer", async () => {
    await open(new Error("unknown operator '=='"));
    const e = notes().find((n) => n.text.includes("unknown operator"))!;
    expect(e.cls).toContain("bad");
    expect(notes().some((n) => n.text.includes("Fully cited"))).toBe(false);
  });

  it("escapes a document id — a citation label is server text in innerHTML", async () => {
    await open(ans({
      matched: 1,
      claims: [claim("x", [cite({ source_type: "doc", document_id: "<img src=x onerror=1>" })])],
    }));
    expect(document.body.querySelector("img")).toBeNull();
  });
});
