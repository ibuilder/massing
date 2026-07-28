import { describe, expect, it } from "vitest";

import { type ActionCandidate, buildPulse, nextBestAction } from "./pulse";

/**
 * Project Pulse.
 *
 * The design this reconstructs made one bet worth protecting: **the number is not the point, the
 * sentence is**. "Cost −0.7%" is something a chart already tells you. "Three CORs unpriced could
 * take that to +1.4%" is what makes somebody act before lunch. So the tests below are mostly about
 * the prose — that it names specific things, that it never contradicts its own number, and that it
 * stays silent instead of padding.
 *
 * The failure mode being guarded against is a summary panel that is *always reassuring*. Those get
 * ignored within a week, and then the one week it should have been alarming, nobody is reading it.
 */

describe("cards appear only when there is data behind them", () => {
  it("a project mid-setup shows nothing rather than confident zeros", () => {
    expect(buildPulse({})).toEqual([]);
  });

  it("a missing proforma means NO deal card — not 0.0%", () => {
    const cards = buildPulse({ model: { score: 90 }, deal: null });
    expect(cards.map((c) => c.key)).toEqual(["model"]);
  });

  it("a present-but-empty source is still omitted", () => {
    // `{}` for cost means "we asked and there is no variance yet", which is not "variance is 0".
    expect(buildPulse({ cost: {} }).length).toBe(0);
  });
});

describe("the model card does not contradict itself", () => {
  it("says 'integrity clean' only when it IS clean", () => {
    const [c] = buildPulse({ model: { score: 95, issues: 0 } });
    expect(c!.headline).toMatch(/clean/i);
    expect(c!.tone).toBe("good");
  });

  it("never says clean beside a non-zero issue count", () => {
    const [c] = buildPulse({ model: { score: 82, issues: 12 } });
    expect(c!.headline).not.toMatch(/clean/i);
    expect(c!.headline).toContain("12");
  });

  it("a blocking issue is risk-toned and names what it blocks", () => {
    const [c] = buildPulse({
      model: { score: 82, issues: 12, blocking: "12 elements missing fire rating blocks the permit set." },
    });
    expect(c!.tone).toBe("risk");
    expect(c!.risk).toContain("permit set");
  });
});

describe("the cost card earns its place by naming the exposure", () => {
  it("under budget with nothing open is good, and says nothing further", () => {
    const [c] = buildPulse({ cost: { variancePct: -0.7, unpricedChanges: 0 } });
    expect(c!.value).toBe("−0.7%");
    expect(c!.tone).toBe("good");
    expect(c!.risk).toBeNull();      // silence, not filler
  });

  it("under budget TODAY but exposed once changes are priced is a watch, with the number", () => {
    const [c] = buildPulse({ cost: { variancePct: -0.7, unpricedChanges: 3, exposurePct: 1.4 } });
    expect(c!.tone).toBe("watch");
    expect(c!.risk).toContain("3 changes unpriced");
    expect(c!.risk).toContain("+1.4%");
  });

  it("one change reads as singular — plural bugs are how a panel loses trust", () => {
    const [c] = buildPulse({ cost: { variancePct: 0.2, unpricedChanges: 1, exposurePct: 0.9 } });
    expect(c!.risk).toContain("1 change unpriced");
    expect(c!.risk).not.toContain("1 changes");
  });

  it("over budget is risk regardless of what is still unpriced", () => {
    const [c] = buildPulse({ cost: { variancePct: 2.1, unpricedChanges: 0 } });
    expect(c!.tone).toBe("risk");
    expect(c!.value).toBe("+2.1%");
  });
});

describe("the work card names the overdue items", () => {
  it("gives names, not just a count — a count makes you go looking", () => {
    const [c] = buildPulse({ work: { open: 23, mine: 6, overdue: ["RFI-118", "submittal 08-4100"] } });
    expect(c!.risk).toContain("RFI-118");
    expect(c!.risk).toContain("submittal 08-4100");
    expect(c!.risk).toContain("6 are yours");
    expect(c!.tone).toBe("risk");
  });

  it("reads naturally with one, two and three overdue", () => {
    const one = buildPulse({ work: { open: 3, overdue: ["RFI-1"] } })[0]!;
    expect(one.risk).toContain("1 is overdue: RFI-1.");
    const two = buildPulse({ work: { open: 3, overdue: ["A", "B"] } })[0]!;
    expect(two.risk).toContain("2 are overdue: A and B.");
    const three = buildPulse({ work: { open: 5, overdue: ["A", "B", "C"] } })[0]!;
    expect(three.risk).toContain("A, B and C.");
  });

  it("an empty queue says so and stays quiet", () => {
    const [c] = buildPulse({ work: { open: 0, mine: 0, overdue: [] } });
    expect(c!.headline).toMatch(/nothing outstanding/i);
    expect(c!.risk).toBeNull();
    expect(c!.tone).toBe("good");
  });
});

describe("the schedule and deal cards", () => {
  it("positive float is good and formats with a sign", () => {
    const [c] = buildPulse({ schedule: { floatDays: 4 } });
    expect(c!.value).toBe("+4 d");
    expect(c!.headline).toMatch(/float positive/i);
  });

  it("negative float is risk, not merely a watch", () => {
    const [c] = buildPulse({ schedule: { floatDays: -2 } });
    expect(c!.value).toBe("−2 d");
    expect(c!.tone).toBe("risk");
  });

  it("IRR inside the band is good; outside it is risk", () => {
    expect(buildPulse({ deal: { irrPct: 18.2, band: [15, 22] } })[0]!.tone).toBe("good");
    expect(buildPulse({ deal: { irrPct: 9.1, band: [15, 22] } })[0]!.tone).toBe("risk");
  });

  it("a stale forecast is a watch even when the number looks fine", () => {
    const [c] = buildPulse({ deal: { irrPct: 18.2, band: [15, 22], staleSince: "pay app #7" } });
    expect(c!.tone).toBe("watch");
    expect(c!.risk).toContain("pay app #7");
  });
});

describe("next best action returns exactly one thing", () => {
  const items: ActionCandidate[] = [
    { ref: "SUB-08-4100", title: "Curtain wall shop drawings", verb: "Review", dueInDays: 0 },
    { ref: "RFI-118", title: "Slab depression at L3", verb: "Answer", overdueDays: 1, blocks: 2 },
    { ref: "COR-014", title: "Added fire damper", verb: "Price", dueInDays: 2 },
  ];

  it("picks the overdue item over the one merely due today", () => {
    expect(nextBestAction(items)!.ref).toBe("RFI-118");
  });

  it("returns ONE, never a list — a ranked list is just another queue to triage", () => {
    const r = nextBestAction(items);
    expect(Array.isArray(r)).toBe(false);
    expect(r).toHaveProperty("verb");
  });

  it("an empty queue has no next action, rather than a made-up one", () => {
    expect(nextBestAction([])).toBeNull();
  });

  it("with nothing overdue, what blocks other work wins over what is merely sooner", () => {
    const r = nextBestAction([
      { ref: "A", title: "a", verb: "Do", dueInDays: 1 },
      { ref: "B", title: "b", verb: "Do", dueInDays: 3, blocks: 5 },
    ]);
    expect(r!.ref).toBe("B");
  });
});

describe("rendering honours the rules the logic sets", () => {
  it("a card with no risk draws NO risk line — not an empty one", async () => {
    const { pulseCardEl } = await import("./pulse");
    const [c] = buildPulse({ cost: { variancePct: -0.7, unpricedChanges: 0 } });
    const el = pulseCardEl(c!);
    expect(el.querySelector(".pulse-risk")).toBeNull();
    expect(el.textContent).toContain("−0.7%");
  });

  it("a card with a risk draws it", async () => {
    const { pulseCardEl } = await import("./pulse");
    const [c] = buildPulse({ cost: { variancePct: -0.7, unpricedChanges: 3, exposurePct: 1.4 } });
    expect(pulseCardEl(c!).querySelector(".pulse-risk")?.textContent).toContain("+1.4%");
  });

  it("the tone reaches the DOM so colour is not decided twice", async () => {
    const { pulseCardEl } = await import("./pulse");
    const [c] = buildPulse({ schedule: { floatDays: -2 } });
    expect(pulseCardEl(c!).className).toContain("pulse-risk");
  });

  it("free text is escaped — risk strings come from server data", async () => {
    const { pulseCardEl } = await import("./pulse");
    const el = pulseCardEl({
      key: "model", label: "Model health", value: "82", tone: "risk",
      headline: "x", risk: '<img src=x onerror="alert(1)">',
    });
    expect(el.querySelector("img")).toBeNull();
    expect(el.innerHTML).toContain("&lt;img");
  });

  it("an empty pulse renders NOTHING rather than a titled empty panel", async () => {
    const { pulseRailEl } = await import("./pulse");
    expect(pulseRailEl([])).toBeNull();
    expect(pulseRailEl(buildPulse({ model: { score: 90 } }))).not.toBeNull();
  });
});

/**
 * Reachability. This repo's most expensive recurring defect is building something correct that
 * nothing calls — seven engines once shipped with no route, and every gate measured the engine while
 * none measured the path to it. Pulse was in exactly that state for one release: tested, rendered,
 * and imported by nobody.
 */
describe("the portal actually calls it", () => {
  it("portal.ts imports and invokes the pulse", async () => {
    const src = (await import("../portal.ts?raw") as { default: string }).default;
    expect(typeof src, "?raw did not resolve — the assertions below would be vacuous").toBe("string");
    expect(src.length).toBeGreaterThan(1000);
    expect(src).toMatch(/from "\.\/panels\/pulse"/);
    expect(src, "defined but never called is the orphan case").toMatch(/this\.renderPulse\(/);
  });
});
