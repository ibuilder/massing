import { describe, expect, it, vi } from "vitest";

import {
  REGISTER_EMPTY_ACTION,
  REGISTER_EMPTY_KINDS,
  type RegisterEmptyKind,
  registerEmptyCopy,
  registerEmptyEl,
  registerNoun,
} from "./empty";

/**
 * R36-EMPTY-STATE — three reasons a register has no rows, and they must not read alike.
 *
 * The defect this guards was reported as "something is wrong with specs" and was none of the things
 * that sentence suggests: the register rendered perfectly around zero rows. The value of this work is
 * *entirely* in the distinction between the three cases, so the gate is written on the partition —
 * "the three differ, in every part a reader looks at" — rather than on any one string. Asserting a
 * particular sentence would pass just as happily if the other two said the same sentence, which is
 * the exact state of the world before this change.
 *
 * **Which of these still passes if the function does nothing?** None. Every assertion below is
 * positive: a stub returning an empty element fails the DOM tests, a stub returning one shared copy
 * object fails the distinctness tests, and a stub that drops the reason fails the `failed` test.
 */

const KINDS = REGISTER_EMPTY_KINDS;

describe("R36-EMPTY-STATE — the three cases are distinguishable", () => {
  it("covers exactly the three reasons, with no fourth and no duplicate", () => {
    expect([...KINDS].sort()).toEqual(["failed", "filtered", "none"]);
    expect(new Set(KINDS).size).toBe(KINDS.length);
    // the action table is total over the kinds — a new kind with no action fails here, not on screen
    expect(Object.keys(REGISTER_EMPTY_ACTION).sort()).toEqual([...KINDS].sort());
  });

  it("gives every kind its own title, its own hint and its own action verb", () => {
    const copies = KINDS.map((kind) =>
      registerEmptyCopy({ kind, name: "Specifications", hint: "Import a spec set.", reason: "500", filterCount: 2 }));
    for (const part of ["title", "hint", "action"] as const) {
      const seen = copies.map((c) => c[part]);
      // set-equality both ways: three non-empty strings, three distinct values
      expect(new Set(seen).size, `${part}: ${seen.join(" | ")}`).toBe(KINDS.length);
      for (const s of seen) expect(s.length).toBeGreaterThan(0);
    }
  });

  it("marks the kind on the element AND on its button, so a check can read which was decided", () => {
    for (const kind of KINDS) {
      const box = registerEmptyEl({ kind, name: "Specifications", reason: "boom" }, () => {});
      expect(box.className).toBe("empty-state");
      expect(box.dataset.empty).toBe(kind);
      const btn = box.querySelector("button");
      expect(btn, kind).not.toBeNull();
      expect(btn!.dataset.emptyAction).toBe(kind);
      expect(btn!.textContent).toBe(REGISTER_EMPTY_ACTION[kind]);
      expect(box.querySelector(".es-hint")!.textContent!.length).toBeGreaterThan(20);
    }
  });

  it("runs the handler on click — the offer is an action, not a sentence about one", () => {
    for (const kind of KINDS) {
      const spy = vi.fn();
      const btn = registerEmptyEl({ kind, name: "RFIs" }, spy).querySelector("button")!;
      btn.click();
      expect(spy, kind).toHaveBeenCalledTimes(1);
    }
  });

  it("renders the copy with no button when no handler is given", () => {
    const box = registerEmptyEl({ kind: "none", name: "RFIs", hint: "Raise one from a drawing." });
    expect(box.querySelector("button")).toBeNull();
    expect(box.textContent).toContain("No RFIs yet");
    expect(box.textContent).toContain("Raise one from a drawing.");
  });
});

describe("R36-EMPTY-STATE — each case says the true thing", () => {
  it("`none` is an invitation carrying the curated upstream guidance", () => {
    const c = registerEmptyCopy({ kind: "none", name: "Submittals", hint: "Driven by spec sections." });
    expect(c.title).toBe("No submittals yet");
    expect(c.hint).toBe("Driven by spec sections.");
  });

  it("`none` falls back to generic copy rather than inventing an upstream", () => {
    const c = registerEmptyCopy({ kind: "none", name: "Submittals" });
    expect(c.hint).toContain("create the first one");
    // and a blank/whitespace hint is treated as absent, not rendered as an empty line
    expect(registerEmptyCopy({ kind: "none", name: "Submittals", hint: "   " }).hint).toBe(c.hint);
  });

  it("`filtered` says the rows are hidden and not missing, and counts what is hiding them", () => {
    const three = registerEmptyCopy({ kind: "filtered", name: "Change Events", filterCount: 3 });
    expect(three.title).toBe("No change events match the current filters");
    expect(three.hint).toContain("3 filters are");
    expect(three.hint).toContain("hidden, not missing");
    // singular/plural agreement — "1 filters are" is the tell that the count is decorative
    expect(registerEmptyCopy({ kind: "filtered", name: "RFIs", filterCount: 1 }).hint).toContain("1 filter is");
    expect(registerEmptyCopy({ kind: "filtered", name: "RFIs" }).hint).toContain("A filter is");
  });

  it("`failed` refuses to claim the register is empty, and names the cause when it has one", () => {
    const c = registerEmptyCopy({ kind: "failed", name: "Specifications", reason: "HTTP 500" });
    expect(c.title).toBe("Couldn't load specifications");
    expect(c.hint).toContain("HTTP 500");
    expect(c.hint).toContain("not an empty register");
    // the twin of that refusal: the `none` copy DOES make the emptiness claim, so the assertion
    // above is about this branch rather than about a phrase nothing ever produces
    expect(registerEmptyCopy({ kind: "none", name: "Specifications" }).title).toBe("No specifications yet");
    // a reason-less failure still renders and still refuses to invent one
    const bare = registerEmptyCopy({ kind: "failed", name: "Specifications" });
    expect(bare.title).toBe(c.title);
    expect(bare.hint).not.toContain("HTTP");
    expect(bare.hint).toContain("not an empty register");
  });
});

describe("R36-EMPTY-STATE — a register's name in mid-sentence", () => {
  it("lower-cases ordinary words and leaves acronyms alone", () => {
    expect(registerNoun("Specifications")).toBe("specifications");
    expect(registerNoun("Change Events")).toBe("change events");
    expect(registerNoun("Non-Conformance Reports")).toBe("non-conformance reports");
    // the shipped line was `m.name.toLowerCase()`, which rendered the busiest register on a jobsite
    // as "No rfis yet". A display name is not a slug.
    expect(registerNoun("RFIs")).toBe("RFIs");
    expect(registerNoun("ASIs")).toBe("ASIs");
    expect(registerNoun("MEP Fittings")).toBe("MEP fittings");
  });

  it("is what the copy actually uses — not a helper nothing calls", () => {
    expect(registerEmptyCopy({ kind: "none", name: "RFIs" }).title).toBe("No RFIs yet");
    expect(registerEmptyCopy({ kind: "failed", name: "RFIs" }).title).toBe("Couldn't load RFIs");
    expect(registerEmptyCopy({ kind: "filtered", name: "RFIs" }).title).toContain("No RFIs match");
  });
});

describe("R36-EMPTY-STATE — the name and the reason are untrusted strings", () => {
  it("writes both as text, in what used to be an innerHTML sink", () => {
    const payload = `<img src=x onerror="alert(1)">`;
    for (const kind of KINDS) {
      const box = registerEmptyEl({ kind: kind as RegisterEmptyKind, name: payload, reason: payload }, () => {});
      expect(box.querySelector("img"), kind).toBeNull();
      expect(box.textContent, kind).toContain("<img");     // shown verbatim, never parsed
    }
  });
});
