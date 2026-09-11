import { describe, it, expect } from "vitest";
import { deletableViews, deleteWarning, pickedView, scopeFromAnswer, viewLabel } from "./savedViews";
import type { SavedViewDef } from "../../api/client";

const v = (o: Partial<SavedViewDef>): SavedViewDef =>
  ({ id: "v1", name: "Overdue — mine", config: {}, scope: "private", owner: "me@x.com", mine: true, ...o });

describe("viewLabel", () => {
  it("names the owner of a view that is not yours", () => {
    expect(viewLabel(v({ mine: false, owner: "sam@x.com", scope: "project" })))
      .toBe("Overdue — mine · shared by sam@x.com");
  });
  it("marks your own view as shared when it is", () => {
    expect(viewLabel(v({ scope: "project" }))).toBe("Overdue — mine · shared");
  });
  it("leaves a private view of yours alone", () => {
    expect(viewLabel(v({}))).toBe("Overdue — mine");
  });
  it("trusts `mine`, not `owner`, when the two disagree", () => {
    // The server sends `mine` per row for exactly this reason: `owner` is the identity key and a
    // display name is not, so a client comparing strings gets it wrong the moment they differ.
    expect(viewLabel(v({ mine: false, owner: "Sam Okafor" }))).toContain("shared by Sam Okafor");
  });
});

describe("deletableViews", () => {
  it("offers only what DELETE will accept", () => {
    // The route refuses a view that is not yours and returns `deleted: false`, which the register
    // reports as "was already gone". Offering the row at all is what turns a refusal into that lie.
    const mine = v({ id: "a" });
    const theirs = v({ id: "b", mine: false, owner: "sam@x.com", scope: "project" });
    expect(deletableViews([mine, theirs])).toEqual([mine]);
  });
  it("keeps your own shared view, which you CAN delete", () => {
    const shared = v({ scope: "project" });
    expect(deletableViews([shared])).toEqual([shared]);
  });
  it("is empty, not undefined, when nothing is yours", () => {
    expect(deletableViews([v({ mine: false })])).toEqual([]);
  });
});

describe("deleteWarning", () => {
  it("says a shared view goes for everyone", () => {
    const w = deleteWarning(v({ scope: "project" }));
    expect(w).toContain("SHARED with the project");
    expect(w).toContain("removes it for everyone");
    expect(w).not.toContain("yours alone");
  });
  it("says a private view goes only for you", () => {
    const w = deleteWarning(v({}));
    expect(w).toContain("yours alone");
    expect(w).not.toContain("everyone");
  });
  it("always says the records survive and there is no undo", () => {
    for (const scope of ["private", "project"] as const) {
      const w = deleteWarning(v({ scope }));
      expect(w).toContain("records it filters are not touched");
      expect(w).toContain("no undo");
    }
  });
});

describe("scopeFromAnswer", () => {
  it("shares only on an explicit yes", () => {
    for (const yes of ["yes", "Yes", " y ", "YEP"]) expect(scopeFromAnswer(yes)).toBe("project");
  });
  it("keeps everything else private", () => {
    // The cost of guessing wrong is asymmetric: a view wrongly kept private is a second click, and
    // a view wrongly published is already read. An ambiguous, empty or dismissed answer stays in.
    for (const no of ["no", "n", "", "   ", "maybe", "sure", undefined]) {
      expect(scopeFromAnswer(no)).toBe("private");
    }
  });
});

describe("pickedView", () => {
  const own = [v({ id: "a", name: "One" }), v({ id: "b", name: "Two" }), v({ id: "c", name: "Three" })];
  it("resolves a 1-based number", () => {
    expect(pickedView("2", own)?.id).toBe("b");
    expect(pickedView(" 3 ", own)?.id).toBe("c");
  });
  it("refuses a number that only STARTS the string", () => {
    // `parseInt("3abc")` is 3 and would delete the third view. `Number` rejects it outright.
    expect(pickedView("3abc", own)).toBeUndefined();
  });
  it("refuses text, blanks, fractions and out-of-range picks", () => {
    for (const bad of ["abc", "", "   ", "2.5", "0", "4", "-1", undefined]) {
      expect(pickedView(bad, own), `"${bad}" must name no view`).toBeUndefined();
    }
  });
  it("indexes the DELETABLE list, not everything on screen", () => {
    // The number the user typed was rendered from `deletableViews`, so resolving it against the full
    // list would delete a different view than the one they read.
    const all = [v({ id: "theirs", mine: false }), v({ id: "mine" })];
    expect(pickedView("1", deletableViews(all))?.id).toBe("mine");
  });
});
