import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ClausePosition } from "../../api/creDeal";
import type { PanelContext } from "../panelContext";
import { coverage, renderClausePlaybook, rowGaps, seedFrom, typeNames } from "./clausePlaybook";

const row = (over: Partial<ClausePosition> = {}): ClausePosition => ({
  clause: "Indemnity", severity: "high", accept: "Mutual", negotiate: "", refuse: "One-way",
  fallback: "", ...over,
});

describe("rowGaps — the server's one hard rule, checked before the round trip", () => {
  it("names every clause with no red line", () => {
    expect(rowGaps([row(), row({ clause: "Retainage", refuse: "" })])).toEqual(["Retainage"]);
  });

  it("treats whitespace as absent, exactly as the server's .strip() does", () => {
    expect(rowGaps([row({ clause: "Payment terms", refuse: "   " })])).toEqual(["Payment terms"]);
  });

  it("labels an unnamed clause rather than reporting an empty string", () => {
    // A row the user has started and not named still has to be identifiable in the warning —
    // "⚠ 1 with NO red line" followed by nothing is a message that cannot be acted on.
    expect(rowGaps([row({ clause: "", refuse: "" })])).toEqual(["(unnamed)"]);
  });
});

describe("coverage — counted facts, deliberately not a verdict", () => {
  it("counts clauses, red lines, fallbacks and high severity", () => {
    const c = coverage([
      row(),
      row({ clause: "Retainage", severity: "medium", fallback: "Reduce at substantial" }),
      row({ clause: "Payment terms", severity: "medium", refuse: "" }),
    ]);
    expect(c).toEqual({ clauses: 3, red_lined: 2, with_fallback: 1, high: 1, gaps: 1 });
  });

  it("does not count a whitespace red line as present", () => {
    // The negative half. Without it `red_lined` could be `rows.length` and every assertion above
    // would still pass — which would make the coverage line confidently wrong rather than absent.
    expect(coverage([row({ refuse: " " })]).red_lined).toBe(0);
  });

  it("reports an empty standard as empty rather than as complete", () => {
    expect(coverage([])).toEqual({ clauses: 0, red_lined: 0, with_fallback: 0, high: 0, gaps: 0 });
  });
});

describe("seedFrom — non-destructive, and deduped the way the server dedupes", () => {
  const starter: ClausePosition[] = [
    { clause: "Indemnity", severity: "high", accept: "Mutual", refuse: "One-way" },
    { clause: "Retainage", severity: "medium", accept: "Reducing", refuse: "Held in full" },
  ];

  it("adds only the clauses this type does not already name", () => {
    expect(seedFrom(starter, [row({ clause: "Indemnity" })]).map((r) => r.clause))
      .toEqual(["Retainage"]);
  });

  it("matches case-insensitively, so seeding cannot create the duplicate it would be refused for", () => {
    // `validate()` dedupes on `name.lower() in seen` and raises "duplicate clause". A seed that
    // matched case-sensitively would hand the user a payload the server then rejects, with the
    // button that produced it labelled "seed".
    expect(seedFrom(starter, [row({ clause: "  indemnity  " })]).map((r) => r.clause))
      .toEqual(["Retainage"]);
  });

  it("returns copies — editing a seeded row must not reach the starter the server sent", () => {
    const added = seedFrom(starter, []);
    added[0]!.accept = "edited";
    expect(starter[0]!.accept).toBe("Mutual");
  });

  it("adds nothing when every starter clause is already named", () => {
    expect(seedFrom(starter, starter.map((r) => ({ ...r })))).toEqual([]);
  });
});

describe("typeNames", () => {
  it("sorts, matching the order the server's refusal lists available_types in", () => {
    expect(typeNames({ subcontract: [], "design services": [], prime: [] }))
      .toEqual(["design services", "prime", "subcontract"]);
  });

  it("tolerates no playbook at all", () => {
    expect(typeNames(undefined)).toEqual([]);
    expect(typeNames(null)).toEqual([]);
  });
});

describe("the server still enforces what these helpers assume", () => {
  // A CROSS-LANE TRIPWIRE, the same technique `reportMoments.test.ts` uses on the report catalog.
  // `rowGaps` exists because `validate()` requires a red line and `seedFrom` lowercases because
  // `validate()` dedupes that way. If either rule left the server, these helpers would be enforcing
  // a standard nobody holds — and every test above would still pass.
  const py = readFileSync(
    resolve(process.cwd(), "../../services/api/src/aec_api/clause_playbook.py"), "utf8");

  it("requires a 'refuse' position, in those words", () => {
    expect(py).toContain('if not str(c.get("refuse") or "").strip():');
    // Asserted as two fragments because the server wraps the sentence across two source lines —
    // the first draft of this check matched the whole sentence and failed on correct input, which
    // is the shape CR-REVIEW-8 recorded: a tripwire that reds on a tree that is right costs more
    // than one that stays silent, because the next person loosens it rather than reading it.
    expect(py).toContain("a 'refuse' position is required");
    expect(py).toContain("no red line is not a standard");
  });

  it("dedupes clause names case-insensitively", () => {
    expect(py).toContain("if name.lower() in seen:");
  });

  it("still refuses a contract type with no clauses, which is why empty types are dropped", () => {
    expect(py).toContain("needs at least one clause");
  });
});

// --- the editor ---------------------------------------------------------------------------------

const STARTER: ClausePosition[] = [
  { clause: "Standard of care", severity: "high", accept: "Ordinary", refuse: "Best-in-industry" },
  { clause: "Indemnity", severity: "high", accept: "Mutual", refuse: "One-way" },
];

function ctx(over: Record<string, unknown> = {}) {
  const api = {
    clausePlaybook: vi.fn().mockResolvedValue({ playbook: {}, starter: STARTER,
      positions: ["accept", "negotiate", "refuse", "absent"] }),
    saveClausePlaybook: vi.fn().mockImplementation(
      (_pid: string, pb: Record<string, ClausePosition[]>) =>
        Promise.resolve({ playbook: pb })),
    ...over,
  };
  const body = document.createElement("div");
  const c = {
    root: document.createElement("div"),
    host: { projectId: () => "p1", api } as unknown as PanelContext["host"],
  } as unknown as PanelContext;
  return { c, api, body };
}

const btn = (host: HTMLElement, text: string) =>
  Array.from(host.querySelectorAll("button")).find((b) => (b.textContent ?? "").includes(text))!;

describe("renderClausePlaybook", () => {
  beforeEach(() => vi.clearAllMocks());

  it("offers the starter standard on a project with no playbook, and says how many", async () => {
    const { c, body } = ctx();
    await renderClausePlaybook(c, body, "p1");
    expect(body.textContent).toContain("No clauses in this type yet");
    expect(btn(body, "Seed").textContent).toContain("Seed 2 from the starter standard");
  });

  it("seeds, then reports coverage as counted facts", async () => {
    const { c, body } = ctx();
    await renderClausePlaybook(c, body, "p1");
    btn(body, "Seed").click();
    expect(body.textContent).toContain("2 clauses");
    expect(body.textContent).toContain("2 with a red line");
    expect(body.textContent).toContain("2 high severity");
    // and no completeness claim anywhere — the thing this panel deliberately does not assert
    expect(body.textContent).not.toContain("complete");
  });

  it("warns, in the server's own words, about a clause with no red line", async () => {
    const { c, body } = ctx();
    await renderClausePlaybook(c, body, "p1");
    btn(body, "＋ clause").click();
    expect(body.textContent).toContain("1 with NO red line");
    expect(body.textContent).toContain("a clause with no red line is not a standard");
  });

  it("saves the draft under the type on screen, and drops a type nobody filled", async () => {
    const { c, api, body } = ctx();
    await renderClausePlaybook(c, body, "p1");
    btn(body, "Seed").click();
    // a second type, created and left empty: `validate()` refuses a type with no clauses, so
    // sending it would turn one person's stray click into a refusal of the whole save
    const nameInput = Array.from(body.querySelectorAll("input"))
      .find((i) => (i.placeholder ?? "").startsWith("new contract type"))!;
    nameInput.value = "design services";
    btn(body, "＋ type").click();
    btn(body, "Save playbook").click();
    await Promise.resolve(); await Promise.resolve();
    expect(api.saveClausePlaybook).toHaveBeenCalledTimes(1);
    const sent = api.saveClausePlaybook.mock.calls[0]![1] as Record<string, ClausePosition[]>;
    expect(Object.keys(sent)).toEqual(["subcontract"]);
    expect(sent.subcontract).toHaveLength(2);
  });

  it("shows the server's refusal verbatim, because it names the clause to fix", async () => {
    const { c, body } = ctx({
      saveClausePlaybook: vi.fn().mockRejectedValue(
        new Error("subcontract / Retainage: a 'refuse' position is required")),
    });
    await renderClausePlaybook(c, body, "p1");
    btn(body, "Seed").click();
    btn(body, "Save playbook").click();
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    expect(body.textContent).toContain("subcontract / Retainage");
  });

  it("never overwrites a position already written down", async () => {
    const { c, body } = ctx({
      clausePlaybook: vi.fn().mockResolvedValue({
        playbook: { subcontract: [{ clause: "Indemnity", severity: "low", accept: "ours",
                                    negotiate: "", refuse: "theirs", fallback: "" }] },
        starter: STARTER, positions: [] }),
    });
    await renderClausePlaybook(c, body, "p1");
    expect(btn(body, "Seed").textContent).toContain("Seed 1 from the starter standard");
    btn(body, "Seed").click();
    const names = Array.from(body.querySelectorAll("input"))
      .filter((i) => i.placeholder === "clause").map((i) => i.value);
    expect(names).toEqual(["Indemnity", "Standard of care"]);
    const accepts = Array.from(body.querySelectorAll("input"))
      .filter((i) => (i.placeholder ?? "").startsWith("the position we sign")).map((i) => i.value);
    expect(accepts[0]).toBe("ours");       // the firm's own wording survived the seed
  });

  it("shows each clause's STORED severity in its dropdown", async () => {
    // The assertion that was missing when this panel shipped. `option.selected` inside an append
    // loop lands one index early in happy-dom, so a severity dropdown built that way renders the
    // wrong value and every other test here still passes. *A property nothing asserts is a property
    // that ships broken.*
    const { c, body } = ctx({
      clausePlaybook: vi.fn().mockResolvedValue({
        playbook: { subcontract: [
          { clause: "Indemnity", severity: "high", accept: "", negotiate: "", refuse: "x", fallback: "" },
          { clause: "Retainage", severity: "low", accept: "", negotiate: "", refuse: "y", fallback: "" },
        ] },
        starter: STARTER, positions: [] }),
    });
    await renderClausePlaybook(c, body, "p1");
    const sels = Array.from(body.querySelectorAll("select"));
    // the first is the contract-type picker, then one per clause row
    expect(sels[0]!.value).toBe("subcontract");
    expect(sels.slice(1).map((s) => s.value)).toEqual(["high", "low"]);
  });

  it("reports a failed load as a reason, never as an empty standard", async () => {
    const { c, body } = ctx({
      clausePlaybook: vi.fn().mockRejectedValue(new Error("403 forbidden")),
    });
    await renderClausePlaybook(c, body, "p1");
    expect(body.textContent).toContain("Playbook unavailable: 403 forbidden");
    expect(body.textContent).not.toContain("No clauses in this type yet");
  });
});
