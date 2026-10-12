import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { CoordStale } from "./coordFreshness";
import { freshnessReading, freshnessRows, recheckPrompt } from "./coordFreshness";

/**
 * COORD-UNANCHORED, the screen half.
 *
 * The engine half is `services/api/test_coord_unanchored.py`, which replays the pre-fix scan and
 * requires it to report an unanchored topic as one of the open issues that did NOT go stale before
 * the gate may report. This file asserts the client: that `clean` is reachable only when the
 * comparison was possible AND everything was assessed, that the two reasons for an incomparable
 * result give different advice, and that the write is offered only for what it would actually touch.
 */

const mk = (o: Partial<CoordStale> = {}): CoordStale => {
  const stale = o.stale ?? [];
  const unanchored = o.unanchored ?? (o.unanchored_topics ?? []).length;
  const assessable = o.assessable ?? 1;
  return {
    from: o.from ?? 1, to: o.to ?? 2,
    changed_elements: o.changed_elements ?? 3,
    open_coordination_issues: o.open_coordination_issues ?? assessable + unanchored,
    assessable, unanchored, unanchored_topics: o.unanchored_topics ?? [],
    stale, stale_count: o.stale_count ?? stale.length,
    comparable: o.comparable ?? ((o.changed_elements ?? 3) > 0 && assessable > 0),
    note: o.note ?? "",
  };
};

const topic = (title: string, n = 1, flagged = false) => ({
  id: title, guid: `g-${title}`, title,
  changed_guids: Array.from({ length: n }, (_, i) => `e${i}`), already_flagged: flagged,
});
const bare = (title: string) => ({ id: title, guid: `g-${title}`, title });

describe("freshnessReading — can this be ruled on, before what it ruled", () => {
  it("is the SHIPPED DEFECT's shape: unanchored topics are not called fresh", () => {
    const r = freshnessReading(mk({ assessable: 38, unanchored_topics: [bare("From a PDF"),
                                                                       bare("Sheet A-201")] }));
    expect(r.kind).toBe("partial");
    expect(r.tone).toBe("warn");
    expect(r.headline).toContain("Nothing stale among the 38 issue(s) that could be assessed");
    expect(r.headline).toContain("2 could not be");
    expect(r.detail).toContain("not reported as still valid");
  });

  it("reports `clean` only when everything was assessed AND the comparison was possible", () => {
    expect(freshnessReading(mk({ assessable: 40 })).kind).toBe("clean");
    // one unanchored topic is enough to stop it being a clean bill
    expect(freshnessReading(mk({ assessable: 39, unanchored_topics: [bare("x")] })).kind)
      .toBe("partial");
    // ...and so is an incomparable diff
    expect(freshnessReading(mk({ assessable: 40, changed_elements: 0, comparable: false })).kind)
      .toBe("incomparable");
  });

  it("gives DIFFERENT advice for the two reasons a comparison is impossible", () => {
    const noChange = freshnessReading(mk({ changed_elements: 0, comparable: false }));
    expect(noChange.headline).toContain("no element changed");
    expect(noChange.detail).toContain("Pick two versions that differ");
    expect(noChange.detail).not.toContain("Anchor these issues");

    const noAnchors = freshnessReading(mk({
      assessable: 0, changed_elements: 5, comparable: false,
      unanchored_topics: [bare("a"), bare("b")], open_coordination_issues: 2,
    }));
    expect(noAnchors.headline).toContain("none of the 2 open issue(s) carries an element GlobalId");
    expect(noAnchors.detail).toContain("Anchor these issues");
    expect(noAnchors.detail).toContain("not a statement that they are still valid");
    expect(noAnchors.detail).not.toContain("Pick two versions");
  });

  it("neither incomparable state is toned as a pass or a failure", () => {
    expect(freshnessReading(mk({ changed_elements: 0, comparable: false })).tone).toBe("");
    expect(freshnessReading(mk({ assessable: 0, comparable: false })).tone).toBe("");
  });

  it("a real finding outranks the coverage gap, and still states it", () => {
    const r = freshnessReading(mk({ assessable: 38, stale: [topic("Duct vs beam")],
                                    unanchored_topics: [bare("x"), bare("y")] }));
    expect(r.kind).toBe("stale");
    expect(r.tone).toBe("bad");
    expect(r.headline).toContain("1 open issue(s) touch an element that changed");
    expect(r.detail).toContain("2 further issue(s) have no anchors");
    expect(r.detail).toContain("can be worse");
  });

  it("omits the unanchored clause when there is nothing unanchored", () => {
    const r = freshnessReading(mk({ assessable: 40, stale: [topic("Duct vs beam")] }));
    expect(r.kind).toBe("stale");
    expect(r.detail).not.toContain("further issue(s) have no anchors");
  });

  it("names the versions it compared, in every branch", () => {
    for (const r of [
      freshnessReading(mk({ assessable: 40 })),
      freshnessReading(mk({ assessable: 38, unanchored_topics: [bare("x")] })),
      freshnessReading(mk({ stale: [topic("a")] })),
      freshnessReading(mk({ changed_elements: 0, comparable: false })),
    ]) expect(`${r.headline} ${r.detail}`).toContain("v1 → v2");
  });
});

describe("freshnessRows", () => {
  it("shows both halves of the population, not just the total", () => {
    const rows = freshnessRows(mk({ assessable: 38, open_coordination_issues: 40,
                                    unanchored_topics: [bare("x"), bare("y")],
                                    stale: [topic("a"), topic("b", 1, true)] }));
    const get = (k: string) => rows.find((r) => r.k === k)?.v;
    expect(get("Open coordination issues")).toBe("40");
    expect(get("…assessable (anchored)")).toBe("38");
    expect(get("…unanchored (not ruled on)")).toBe("2");
    expect(get("Stale (element changed)")).toBe("2");
    expect(get("Already flagged")).toBe("1");
  });
});

describe("recheckPrompt — the write is offered for what it would actually touch", () => {
  it("counts only the topics NOT already flagged, because the route is idempotent", () => {
    const p = recheckPrompt(mk({ stale: [topic("a"), topic("b", 1, true), topic("c")] }))!;
    expect(p.count).toBe(2);
    expect(p.label).toContain("Flag 2");
  });

  it("is null when everything stale is already flagged, so no button renders", () => {
    expect(recheckPrompt(mk({ stale: [topic("a", 1, true)] }))).toBeNull();
    expect(recheckPrompt(mk({ assessable: 40 }))).toBeNull();
  });

  it("says what the write does AND what it does not do", () => {
    const p = recheckPrompt(mk({ stale: [topic("a")] }))!;
    expect(p.confirm).toContain("model-changed");
    expect(p.confirm).toContain("never closes an issue");
    expect(p.confirm).toContain("Running it again changes nothing");
  });
});

describe("the panel is WIRED to the reading — the pure tests above cannot see this", () => {
  // Source-level, and the limit is stated: a render inside `if (false)` would pass these. The pure
  // assertions prove the decision; these prove the decision reaches a screen, and that the two
  // routes are actually called. Anchored on `__file__` because `vitest` and `run_tests.py` start
  // from different directories.
  const SRC = readFileSync(
    resolve(dirname(fileURLToPath(import.meta.url)), "modelReviewPanel.ts"), "utf-8");

  it("calls BOTH routes — the read per version and the write behind the prompt", () => {
    expect(SRC).toContain("api.coordinationStale(pid, prev.version, r.version)");
    expect(SRC).toContain("api.coordinationStaleRecheck(pid, a, b)");
  });

  it("renders the headline, the DETAIL and the counts", () => {
    // PRODUCED, not only consumed. Found by mutation: replacing `freshnessReading(cs)` with a
    // literal `{headline: "", detail: "", tone: "", kind: "clean"}` left every assertion below
    // green, because they all read `read.<field>` and those spellings survive. *Asserting that a
    // value is used is not asserting where it came from* — the same hole K11 had one line over,
    // where a pin on `cs.unanchored_topics` matched the identifier inside a type annotation.
    expect(SRC).toContain("freshnessReading(cs)");
    expect(SRC).toContain("escapeHtml(read.headline)");
    expect(SRC).toContain("escapeHtml(read.detail)");
    expect(SRC).toContain("freshnessRows(cs)");
  });

  it("NAMES the topics it could not rule on, rather than only counting them", () => {
    // The count alone sends nobody anywhere. Anchoring those topics is the only action that makes
    // this check apply to them, so the reader has to know which ones.
    // THE ITERATION, not the identifier. Asserting `cs.unanchored_topics` alone survived a mutation
    // that replaced the loop source with `[] as typeof cs.unanchored_topics` — the string was still
    // in the file, inside a type annotation. *A source pin that matches a NAME matches every mention
    // of the name, including the ones that are not the code.*
    expect(SRC).toContain("for (const u of cs.unanchored_topics.slice(");
    expect(SRC).toContain("no element GlobalIds, so this ");
  });

  it("gates the write on `recheckPrompt` and on a confirm, not on the stale count", () => {
    expect(SRC).toContain("const prompt = recheckPrompt(cs);");
    expect(SRC).toContain("if (prompt) {");
    expect(SRC).toContain("confirmModal(\"Flag for re-verification?\", prompt.confirm");
  });

  it("offers the control only where a previous version exists", () => {
    // A button that can only 422 reads as a broken feature — the same argument the panel's NEXT
    // table already makes for the review actions.
    expect(SRC).toContain("const prev = rows.find((x) => x.version === r.version - 1);");
    expect(SRC).toContain("if (prev) {");
  });

  it("reports what the SERVER flagged, not what was offered", () => {
    // The scan re-runs server-side and the set can have moved since the read; echoing the offered
    // count would show a number no write produced.
    expect(SRC).toContain("${res.flagged} issue(s) flagged");
  });

  it("and the client DECLARES the coverage fields, or no derivation over declarations sees them", () => {
    const api = readFileSync(
      resolve(dirname(fileURLToPath(import.meta.url)), "../../api/model.ts"), "utf-8");
    expect(api).toContain("assessable: number");
    expect(api).toContain("unanchored: number");
    expect(api).toContain("comparable: boolean");
    // ONE declaration shared by the read and the write: `recheck` returns the same scan plus
    // `flagged`, and two copies would be two answers the moment either grew a field.
    expect(api).toContain("CoordStale & { flagged: number }");
  });
});
