import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import {
  actionsFrom, governanceReading, IMMUTABLE_STATES, renderGovernanceCard, returnsReading,
  REVIEW_TRANSITIONS, revisionName, type ScenarioRow,
} from "./scenarioGovernance";

const FIN_GOV = readFileSync(
  resolve(__dirname, "../../../../services/api/src/aec_api/fin_gov.py"), "utf8");
const PF = readFileSync(resolve(__dirname, "./proforma.ts"), "utf8");

const row = (p: Partial<ScenarioRow> = {}): ScenarioRow => ({
  id: "s1", name: "Base case", review_status: "draft", returns: { equity_irr: 0.18 }, ...p });

describe("the transition table agrees with the server's", () => {
  /** `REVIEW_ACTIONS` out of `fin_gov.py`, as `action → [from, to]`. */
  function serverTransitions(): Record<string, [string, string]> {
    const start = FIN_GOV.indexOf("REVIEW_ACTIONS");
    expect(start, "REVIEW_ACTIONS not found — has fin_gov.py been reorganised?").toBeGreaterThan(-1);
    const body = FIN_GOV.slice(start, FIN_GOV.indexOf("\n}", start));
    const out: Record<string, [string, string]> = {};
    for (const m of body.matchAll(/"(\w+)":\s*\("(\w+)",\s*"(\w+)"\)/g)) {
      out[m[1] as string] = [m[2] as string, m[3] as string];
    }
    return out;
  }

  it("parsed the server's table — a parse that matches nothing agrees with everything", () => {
    expect(Object.keys(serverTransitions()).length).toBeGreaterThanOrEqual(5);
  });

  it("matches it exactly, in BOTH directions", () => {
    // A transition on the server and not here is a button nobody can reach; one here and not there
    // is a button that 404s. Only comparing the whole mapping catches both.
    expect(serverTransitions()).toEqual(REVIEW_TRANSITIONS);
  });

  it("mirrors IMMUTABLE_STATES too — that is what decides whether Edit or Revise is the move", () => {
    const m = FIN_GOV.match(/IMMUTABLE_STATES\s*=\s*\(([^)]*)\)/);
    expect(m, "IMMUTABLE_STATES not found").toBeTruthy();
    const server = [...m![1]!.matchAll(/"(\w+)"/g)].map((x) => x[1]);
    expect(server).toEqual([...IMMUTABLE_STATES]);
  });

  it("derives the legal actions per state from the table, not a second list", () => {
    expect(actionsFrom("draft")).toEqual(["submit"]);
    expect(actionsFrom("in_review").sort()).toEqual(["approve", "reject"]);
    expect(actionsFrom("approved").sort()).toEqual(["publish", "reopen"]);
    // published is TERMINAL — the whole reason a clone is the only forward move from it
    expect(actionsFrom("published")).toEqual([]);
  });
});

describe("the Overview tab actually mounts it", () => {
  // Source-level, the bargain `clientCallers.test.ts` and `test_route_reachability` make: this
  // cannot see a mount disabled at runtime, and the card's own DOM behaviour is asserted below.
  // It exists because the DEFECT this module closes was three routes nothing called — a card whose
  // mount is deleted in a refactor is the same defect returning, and the pure functions would all
  // still pass.
  it("renders the card from renderOverview, with the project id", () => {
    const fn = PF.slice(PF.indexOf("private renderOverview("));
    const body = fn.slice(0, fn.indexOf("\n  }\n"));
    expect(body).toContain("renderScenarioGovernance(gov, pid)");
  });

  it("drives all three routes — review, clone and the edit", () => {
    const fn = PF.slice(PF.indexOf("private async renderScenarioGovernance("));
    const body = fn.slice(0, fn.indexOf("\n  }\n"));
    for (const call of ["api.listScenarios(", "api.reviewScenario(", "api.cloneScenario(",
                        "api.updateScenario("]) {
      expect(body, call).toContain(call);
    }
    expect(body).toContain("renderGovernanceCard(");
  });

  it("reports the clone's `resolved` rather than asserting the re-solve happened", () => {
    // The server states whether it computed this revision's result. A caller that prints returns
    // without reading that flag is the defect half of FIN-GOV-DARK wearing a client hat.
    const fn = PF.slice(PF.indexOf("private async renderScenarioGovernance("));
    expect(fn.slice(0, fn.indexOf("\n  }\n"))).toContain("c.resolved");
  });
});

describe("`returns: null` is not a return of zero", () => {
  it("separates never-solved from solved-with-nothing", () => {
    expect(returnsReading(row({ returns: null })).kind).toBe("unsolved");
    expect(returnsReading(row({ returns: {} })).kind).toBe("no_returns");
    expect(returnsReading(row({ returns: { equity_irr: null, npv: null } })).kind).toBe("no_returns");
    expect(returnsReading(row()).kind).toBe("solved");
  });

  it("says which it is in words a developer can act on", () => {
    expect(returnsReading(row({ returns: null })).text).toContain("not solved yet");
    expect(returnsReading(row({ returns: {} })).text).toContain("returns nothing");
    expect(returnsReading(row({ returns: { equity_irr: 0.182, equity_multiple: 2.1 } })).text)
      .toBe("18.2% equity IRR · 2.10× equity");
  });
});

describe("the committed verdict carries its coverage", () => {
  it("is NULL on an empty register, not false — those are different facts", () => {
    const r = governanceReading([]);
    expect(r.committed).toBeNull();
    expect(r.summary).toContain("No scenarios saved yet");
  });

  it("is false with scenarios and nothing published", () => {
    const r = governanceReading([row(), row({ id: "s2", review_status: "in_review" })]);
    expect(r.committed).toBe(false);
    expect(r.summary).toContain("Not committed");
    expect(r.summary).toContain("1 in review");
  });

  it("is true with a published one, and names it", () => {
    const r = governanceReading([row(), row({ id: "s2", name: "IC case", review_status: "published" })]);
    expect(r.committed).toBe(true);
    expect(r.published?.id).toBe("s2");
    expect(r.summary).toContain("IC case");
  });

  it("counts the unsolved rows rather than folding them into the verdict", () => {
    const r = governanceReading([row({ returns: null }), row({ id: "s2", returns: null }), row({ id: "s3" })]);
    expect(r.unsolved).toBe(2);
  });

  it("refuses to pick silently when several rows are published", () => {
    const r = governanceReading([row({ id: "a", review_status: "published" }),
                                 row({ id: "b", name: "Later", review_status: "published" })]);
    expect(r.multiple_published).toBe(2);
    expect(r.published?.id).toBe("b");       // newest, since the list is oldest→newest
  });
});

describe("revisionName", () => {
  it("counts up from the parent's base name", () => {
    expect(revisionName("Base case", ["Base case"])).toBe("Base case rev 2");
    expect(revisionName("Base case rev 2", ["Base case", "Base case rev 2"])).toBe("Base case rev 3");
    expect(revisionName("Base case", ["Base case", "Base case rev 2", "Base case rev 3"]))
      .toBe("Base case rev 4");
  });
});

describe("the card", () => {
  let host: HTMLElement;
  beforeEach(() => { host = document.createElement("div"); document.body.appendChild(host); });

  const ctx = () => {
    const calls: string[] = [];
    return { calls, ctx: { review: (s: string, a: string) => { calls.push(`review:${s}:${a}`); },
                           clone: (s: string, n: string) => { calls.push(`clone:${s}:${n}`); },
                           updateFromCurrent: (s: string, n: string) => { calls.push(`update:${s}:${n}`); },
                           askName: async (s: string) => s } };
  };

  it("offers exactly the legal actions for each row's state, plus Revise", () => {
    const rows = [row({ id: "d", review_status: "draft" }),
                  row({ id: "p", review_status: "published" })];
    renderGovernanceCard(host, governanceReading(rows), ctx().ctx);
    const acts = (sid: string) => [...host.querySelectorAll(`[data-scenario="${sid}"] [data-action]`)]
      .map((b) => (b as HTMLElement).dataset.action);
    expect(acts("d")).toEqual(["submit", "update", "clone"]);
    // published is terminal AND immutable, so Revise is the ONLY control — no review action to take
    // and no edit permitted. That is the governance design's point, and the reason the clone route
    // being dark meant a published scenario was a dead end in the app.
    expect(acts("p")).toEqual(["clone"]);
    // approved: review actions remain (publish/reopen) but the EDIT does not
    renderGovernanceCard(host, governanceReading([row({ id: "a", review_status: "approved" })]), ctx().ctx);
    expect(acts("a")).toEqual(["publish", "reopen", "clone"]);
  });

  it("RENDERS the coverage line, not just computes it", () => {
    // The consumer's half of VERDICT-COVERAGE: a reading that carries the count proves nothing if
    // the screen drops it. Mutating the `unsolved > 0` branch away reds here.
    renderGovernanceCard(host, governanceReading([row({ returns: null }), row({ id: "s2" })]), ctx().ctx);
    expect(host.textContent).toContain("1 of 2 scenario(s) have no solved result");
    expect(host.textContent).toContain("unknown, not zero");
  });

  it("says nothing about coverage when everything is solved", () => {
    renderGovernanceCard(host, governanceReading([row()]), ctx().ctx);
    expect(host.textContent).not.toContain("no solved result");
  });

  it("explains that a committed row cannot be edited in place, on the button itself", () => {
    renderGovernanceCard(host, governanceReading([row({ review_status: "approved" })]), ctx().ctx);
    const rev = host.querySelector('[data-action="clone"]') as HTMLElement;
    expect(rev.title).toContain("cannot be edited in place");
    renderGovernanceCard(host, governanceReading([row({ review_status: "draft" })]), ctx().ctx);
    expect((host.querySelector('[data-action="clone"]') as HTMLElement).title)
      .not.toContain("cannot be edited");
  });

  it("offers the edit only where the state machine permits it", () => {
    for (const st of ["draft", "in_review"] as const) {
      renderGovernanceCard(host, governanceReading([row({ review_status: st })]), ctx().ctx);
      expect(host.querySelector('[data-action="update"]'), st).toBeTruthy();
    }
    for (const st of ["approved", "published"] as const) {
      renderGovernanceCard(host, governanceReading([row({ review_status: st })]), ctx().ctx);
      expect(host.querySelector('[data-action="update"]'), st).toBeNull();
    }
  });

  it("wires the handlers", async () => {
    const c = ctx();
    renderGovernanceCard(host, governanceReading([row({ id: "x", review_status: "in_review" })]), c.ctx);
    (host.querySelector('[data-action="approve"]') as HTMLButtonElement).click();
    expect(c.calls).toEqual(["review:x:approve"]);
    (host.querySelector('[data-action="clone"]') as HTMLButtonElement).click();
    await Promise.resolve(); await Promise.resolve();
    expect(c.calls).toContain("clone:x:Base case rev 2");
    (host.querySelector('[data-action="update"]') as HTMLButtonElement).click();
    expect(c.calls).toContain("update:x:Base case");
  });

  it("escapes a scenario name — it is user text in innerHTML", () => {
    renderGovernanceCard(host, governanceReading([row({ name: "<img src=x onerror=1>" })]), ctx().ctx);
    expect(host.querySelector("img")).toBeNull();
    expect(host.textContent).toContain("<img src=x onerror=1>");
  });

  it("survives a review_status this build has never heard of", () => {
    // A declared union is a claim about the server, not a guarantee from it. Before `statusLabel`
    // the title line did `STATUS_LABEL[s].toLowerCase()` and the WHOLE CARD threw on one such row.
    const rows = [row({ review_status: "escrowed" as never })];
    expect(() => renderGovernanceCard(host, governanceReading(rows), ctx().ctx)).not.toThrow();
    expect(host.textContent).toContain("escrowed");
    // No review action, because the table knows no transition from there. The EDIT is still
    // offered, and that is a decision rather than an oversight: the 409 from `update_scenario` is
    // the authority on whether a row may change — this render cannot be, since another person can
    // approve it between the fetch and the click — and a refusal that explains itself teaches more
    // than a hidden button. Failing closed here would also forbid editing a new state that is
    // legitimately editable, on no evidence either way.
    expect([...host.querySelectorAll("[data-action]")].map((b) => (b as HTMLElement).dataset.action))
      .toEqual(["update", "clone"]);
  });

  it("renders the empty register without rows, and says so", () => {
    renderGovernanceCard(host, governanceReading([]), ctx().ctx);
    expect(host.querySelectorAll("[data-scenario]")).toHaveLength(0);
    expect(host.textContent).toContain("No scenarios saved yet");
  });
});
