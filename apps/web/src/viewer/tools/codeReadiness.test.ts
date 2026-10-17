import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";

import type { CodeReadiness, CodeReadinessDeps } from "./codeReadiness";
import {
  GUID_CAP, codeReadinessButton, isolateNote, readinessRows, readinessScope,
} from "./codeReadiness";

/**
 * CODE-READY-DARK — `/elements/code-check` had no client caller, and its summary leaves out the
 * rules it could not run.
 *
 * Six rules ship. A rule whose `applies` class is absent from the model is returned with
 * `status: "n/a"` and then **filtered out of the numbers**: `rules` is `len(checked_rules)`, and
 * `checked`, `passed` and `readiness_pct` sum over that filtered list. So a model with no
 * `IfcSpace` — the ordinary state of an early massing — reports a readiness percentage that omits
 * **both** occupant-load rules, the two a plan review actually turns on. `checks` carries all six;
 * the numbers describe four, and nothing in the response says so.
 *
 * It is this session's recurring shape with the coverage spread across the rows rather than counted
 * in a field: there is no `skipped` to read, so the consumer has to derive it. Derived from
 * `checks` here — the array the screen shows — and the server's own filter is pinned below, because
 * a change there leaves every fixture green.
 */

const rule = (over: Partial<CodeReadiness["checks"][number]> & { id: string }):
  CodeReadiness["checks"][number] => ({
  id: over.id, label: over.label ?? over.id, code: over.code ?? "IBC 1",
  note: over.note ?? "", applies: over.applies ?? "IfcWall",
  checked: over.checked ?? 0, passed: over.passed ?? 0, failed: over.failed ?? 0,
  below_min: over.below_min ?? 0, fail_guids: over.fail_guids ?? [],
  status: over.status ?? "pass",
});

/** Compose a response the way the route does: the summary sums only the non-`n/a` rules. */
function resp(checks: CodeReadiness["checks"][number][]): CodeReadiness {
  const ran = checks.filter((c) => c.status !== "n/a");
  const checked = ran.reduce((n, c) => n + c.checked, 0);
  const passed = ran.reduce((n, c) => n + c.passed, 0);
  return {
    code: "IBC (data-readiness)", rules: ran.length, checked, passed,
    readiness_pct: checked ? Math.round((1000 * passed) / checked) / 10 : 100.0,
    checks,
    fail_guids: [...new Set(checks.flatMap((c) => c.fail_guids))],
  };
}

/** The shipped shape on a model with walls and doors but **no spaces and no stairs**. */
const NO_SPACES = resp([
  rule({ id: "egress_door_width", label: "Egress door width recorded", applies: "IfcDoor",
         checked: 12, passed: 12, status: "pass" }),
  rule({ id: "fire_rating", label: "Fire rating on walls", applies: "IfcWall",
         checked: 40, passed: 40, status: "pass" }),
  rule({ id: "space_area", label: "Spaces carry floor area", applies: "IfcSpace", status: "n/a" }),
  rule({ id: "space_occupancy", label: "Spaces classify occupancy", applies: "IfcSpace",
         status: "n/a" }),
  rule({ id: "stair_present", label: "Egress stairs modelled", applies: "IfcStair", status: "n/a" }),
  rule({ id: "classification", label: "Elements typed/classified", applies: "*",
         checked: 52, passed: 52, status: "pass" }),
]);

describe("readinessScope — the percentage is about the rules that RAN", () => {
  it("is the SHIPPED SHAPE: 100% readiness over four of six rules", () => {
    // What a first consumer would have printed: `readiness_pct` and nothing else. It is 100, and
    // the two occupant-load rules were never asked.
    expect(NO_SPACES.readiness_pct).toBe(100);
    expect(NO_SPACES.rules).toBe(3);
    const s = readinessScope(NO_SPACES);
    expect(s.ran).toBe(3);
    expect(s.skipped).toBe(3);
    expect(s.total).toBe(6);
    expect(s.tone).not.toBe("ok");
    expect(s.tone).toBe("warn");
    expect(s.headline).toContain("3 of 6 rules checked");
    expect(s.detail).toContain("NOT checked");
    expect(s.detail).toContain("IfcSpace");
    expect(s.detail).toContain("Spaces classify occupancy");
    expect(s.detail).toContain("excludes them entirely");
  });

  it("is `ok` only when every rule ran AND nothing failed", () => {
    const all = resp([
      rule({ id: "a", checked: 3, passed: 3, status: "pass" }),
      rule({ id: "b", checked: 2, passed: 2, status: "pass" }),
    ]);
    const s = readinessScope(all);
    expect(s.tone).toBe("ok");
    expect(s.skipped).toBe(0);
    expect(s.headline).toContain("All 2 rules checked");
    expect(s.detail).not.toContain("NOT checked");
  });

  it("a real failure outranks the coverage gap — a finding is not a warning", () => {
    const mixed = resp([
      rule({ id: "a", checked: 4, passed: 1, failed: 3, fail_guids: ["x", "y", "z"],
             status: "fail" }),
      rule({ id: "b", applies: "IfcStair", status: "n/a" }),
    ]);
    const s = readinessScope(mixed);
    expect(s.tone).toBe("bad");
    expect(s.failedRules).toBe(1);
    expect(s.detail).toContain("NOT checked");      // still stated, not swallowed by the failure
  });

  it("nothing ran is ABSENT, not a clean pass — and the server would say 100%", () => {
    const none = resp([
      rule({ id: "a", applies: "IfcDoor", status: "n/a" }),
      rule({ id: "b", applies: "IfcSpace", status: "n/a" }),
    ]);
    expect(none.readiness_pct).toBe(100);           // the server's own `else 100.0`
    const s = readinessScope(none);
    expect(s.tone).toBe("");
    expect(s.headline).toBe("No rule could be checked");
    expect(s.detail).toContain("about nothing");
  });

  it("derives the skipped count from `checks`, NOT from the server's `rules`", () => {
    // The two can only disagree if the filter changes, and `checks` is what the screen shows. A
    // consumer reading `rules` would report a coverage that does not match its own table.
    const lying = { ...NO_SPACES, rules: 6 };
    expect(readinessScope(lying).skipped).toBe(3);
    expect(readinessScope(lying).ran).toBe(3);
  });
});

describe("readinessRows — a rule that did not run still gets a row", () => {
  it("says why rather than showing 0/0", () => {
    const rows = readinessRows(NO_SPACES);
    expect(rows).toHaveLength(6);
    const space = rows.find((r) => r.k.startsWith("Spaces carry floor area"))!;
    expect(space.v).toBe("not checked — no IfcSpace in this model");
    expect(space.v).not.toContain("0/0");
    expect(space.strong).toBe(false);
  });

  it("reports the missing and the below-minimum counts separately", () => {
    const r = resp([rule({ id: "d", label: "Egress door width recorded", applies: "IfcDoor",
                           checked: 10, passed: 6, failed: 4, below_min: 3,
                           fail_guids: ["a", "b", "c", "d"], status: "fail" })]);
    const row = readinessRows(r)[0]!;
    expect(row.v).toContain("6/10 carry it");
    expect(row.v).toContain("4 missing");
    expect(row.v).toContain("3 below the minimum");
    expect(row.strong).toBe(true);
  });
});

describe("isolateNote — the isolate set is a page and the count is a total", () => {
  it("names the shortfall when the guid list is capped", () => {
    const n = isolateNote({ label: "Fire rating on walls", failed: 7200,
                            fail_guids: Array.from({ length: GUID_CAP }, (_, i) => `g${i}`) })!;
    expect(n).toContain(`the first ${GUID_CAP} of 7200`);
    expect(n).toContain("a page, not the finding");
  });

  it("is null when the list is the whole set", () => {
    expect(isolateNote({ label: "x", failed: 3, fail_guids: ["a", "b", "c"] })).toBeNull();
    expect(isolateNote({ label: "x", failed: 0, fail_guids: [] })).toBeNull();
  });
});

/**
 * **The two facts this module rests on live in Python**, so they are read rather than assumed: the
 * summary filters `n/a` out, and a guid list is capped. A change to either leaves every fixture
 * above green — CLASH-TRUNC's lesson, where the guard was sound and the evidence handed to it
 * was not.
 */
describe("the route these fixtures describe", () => {
  const SRC = readFileSync("../../services/api/src/aec_api/routers/properties.py", "utf8");

  it("filters the `n/a` rules out of the summary — the defect this module corrects", () => {
    expect(SRC).toContain('checked_rules = [c for c in checks if c["status"] != "n/a"]');
    expect(SRC).toContain('"rules": len(checked_rules),');
    expect(SRC).toContain('tot_checked = sum(c["checked"] for c in checked_rules)');
  });

  it("returns all six rules in `checks`, which is what the coverage is derived from", () => {
    const rules = SRC.slice(SRC.indexOf("_CODE_RULES = ["), SRC.indexOf("def _first_value"));
    expect([...rules.matchAll(/\{"id": "/g)]).toHaveLength(6);
    expect(rules).toContain('"applies": "IfcSpace"');
    expect(SRC).toContain('"checks": checks,');
  });

  it("caps a returned guid list at the number `isolateNote` quotes", () => {
    expect(SRC).toContain('"fail_guids": fails[:5000]');
    expect(SRC).toContain("list(all_fail)[:5000]");
    expect(GUID_CAP).toBe(5000);
  });
});

/** ---- the render, through the real button ----------------------------------------------------- */

function harness(r: CodeReadiness | Error) {
  const isolated: string[][] = [];
  const api = {
    codeCheck: vi.fn(async () => { if (r instanceof Error) throw r; return r; }),
  };
  const toast = vi.fn();
  const deps = {
    toolBtn2: (label: string, onClick: () => void) => {
      const b = document.createElement("button");
      b.textContent = label;
      b.onclick = onClick;
      return b;
    },
    api: api as unknown as CodeReadinessDeps["api"],
    pid: "p1",
    container: document.createElement("div"),
    layerMgr: { isolateGuids: (g: string[]) => { isolated.push(g); return Promise.resolve(); } } as
      unknown as CodeReadinessDeps["layerMgr"],
    toast,
  } satisfies CodeReadinessDeps;
  return { deps, isolated, toast };
}

const flush = () => new Promise((res) => setTimeout(res, 0));
const notes = () => [...document.querySelectorAll(".result-note")].map((n) => ({
  text: n.textContent ?? "", cls: n.className,
}));
const btn = (text: string) =>
  [...document.querySelectorAll("button")].find((b) => b.textContent?.includes(text));

async function open(r: CodeReadiness | Error) {
  document.body.replaceChildren();
  const h = harness(r);
  const b = codeReadinessButton(h.deps);
  document.body.appendChild(b);
  b.click();
  await flush();
  return h;
}

describe("the rendered result", () => {
  it("renders the coverage, and NOT in a passing tone", async () => {
    await open(NO_SPACES);
    const head = notes().find((n) => n.text.includes("rules checked"))!;
    expect(head.text).toContain("3 of 6 rules checked");
    expect(head.text).toContain("NOT checked");
    expect(head.cls).toContain("warn");
    expect(head.cls).not.toContain("ok");
    // every rule has a row, including the three that did not run
    expect(document.querySelectorAll(".result-table tr")).toHaveLength(6);
    // and the result says what it is NOT
    expect(notes().some((n) => n.text.includes("not a code finding"))).toBe(true);
  });

  it("offers the isolate button for a failing rule, and names it", async () => {
    const h = await open(resp([
      rule({ id: "d", label: "Egress door width recorded", applies: "IfcDoor", checked: 5,
             passed: 3, failed: 2, fail_guids: ["D1", "D2"], status: "fail" }),
    ]));
    btn("Isolate 2 element(s) missing Egress door width")!.click();
    expect(h.isolated).toEqual([["D1", "D2"]]);
  });

  it("warns, on screen, when that isolate set is a capped page", async () => {
    await open(resp([
      rule({ id: "w", label: "Fire rating on walls", checked: 9000, passed: 1800, failed: 7200,
             fail_guids: Array.from({ length: GUID_CAP }, (_, i) => `g${i}`), status: "fail" }),
    ]));
    expect(notes().some((n) => n.text.includes(`the first ${GUID_CAP} of 7200`))).toBe(true);
    // ...and the BUTTON says what it will select, not what the rule found. Labelling it `failed`
    // survived the note being present — the warning and the control are two claims, and only one
    // was asserted.
    expect(btn(`Isolate ${GUID_CAP} element(s) missing Fire rating`)).toBeDefined();
    expect(btn("Isolate 7200 element(s)")).toBeUndefined();
  });

  it("offers no isolate button when a rule passes", async () => {
    await open(resp([rule({ id: "a", checked: 3, passed: 3, status: "pass" })]));
    expect(btn("Isolate")).toBeUndefined();
  });

  it("reports a refusal through the toast rather than an empty modal", async () => {
    const h = await open(new Error("no properties index for project"));
    expect(h.toast).toHaveBeenCalledWith(
      expect.stringContaining("no properties index for project"), "error");
    expect(document.querySelectorAll(".result-overlay")).toHaveLength(0);
  });

  it("escapes a rule label — `applies` and `label` are server text in innerHTML", async () => {
    await open(resp([rule({ id: "x", label: "<img src=x onerror=1>", applies: "IfcSpace",
                            status: "n/a" }),
                     rule({ id: "y", checked: 1, passed: 1, status: "pass" })]));
    expect(document.body.querySelector("img")).toBeNull();
  });
});
