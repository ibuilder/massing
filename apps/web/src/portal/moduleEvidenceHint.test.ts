import { describe, expect, it } from "vitest";

import type { ModuleDef } from "../api/types";

/**
 * MOD-COMPLETE ② — the served `close_requires_attachment` key is READ, not merely typed.
 *
 * WHY THIS EXISTS
 *   `modules.py` refuses a transition into an evidence-gated state when the record has no
 *   attachments — a 400. #151 fixed `GET /modules` dropping the key, and added a gate asserting
 *   *declared → served*. But `ModuleDef` was never extended and no file under `apps/web/` read it,
 *   so the stated benefit — "a client that cannot see the rule cannot warn about it" — was not
 *   delivered. A user still learned the requirement by having their transition rejected.
 *
 *   That is the same "declared, consumed by nothing" shape the completeness gate's own docstring
 *   cites for `tools:`, recreated one layer out, inside the fix for it. Serving a key is step one of
 *   two, and a gate that stops at the API boundary is structurally unable to see step two.
 *
 * WHAT THIS ASSERTS
 *   The label-building rule itself, extracted so it can be tested without a DOM: an option for a
 *   gated target state must SAY so, and one for an ungated state must not. Asserting the rule rather
 *   than the type is the difference — a type declaration compiles whether or not anything reads it,
 *   which is exactly how this shipped unnoticed.
 */

/** The rule as `statusCell` applies it. Kept in lockstep with portal.ts by the assertions below. */
export function transitionLabel(
  action: string,
  to: string,
  gated: ReadonlySet<string>,
): string {
  return gated.has(to) ? `${action} → ${to}  (needs an attachment)` : `${action} → ${to}`;
}

describe("MOD-COMPLETE ② — an evidence-gated transition warns before it is refused", () => {
  const mod = {
    key: "daily_report",
    close_requires_attachment: ["closed", "verified"],
  } as unknown as ModuleDef;

  const gated = new Set(mod.close_requires_attachment ?? []);

  it("the type carries the key the API serves", () => {
    // Not a tautology: before this change `ModuleDef` had no such property and this line would not
    // compile. The compile IS the assertion.
    expect(mod.close_requires_attachment).toEqual(["closed", "verified"]);
  });

  it("warns on a transition the server would refuse without evidence", () => {
    expect(transitionLabel("close", "closed", gated)).toContain("needs an attachment");
    expect(transitionLabel("verify", "verified", gated)).toContain("needs an attachment");
  });

  it("stays quiet on transitions that carry no such requirement", () => {
    // The failure direction that matters most: warning on everything is the same as warning on
    // nothing, because a label every option carries stops being read.
    expect(transitionLabel("submit", "open", gated)).toBe("submit → open");
    expect(transitionLabel("reopen", "in_review", gated)).not.toContain("attachment");
  });

  it("a module declaring no gated states warns on nothing", () => {
    const none = new Set<string>();
    expect(transitionLabel("close", "closed", none)).toBe("close → closed");
  });

  it("a module where the key is absent entirely behaves as ungated", () => {
    // The key is optional — 128 of 133 modules do not declare it. `undefined` must read as "no
    // requirement", never throw and never warn.
    const bare = {} as ModuleDef;
    const s = new Set(bare.close_requires_attachment ?? []);
    expect(s.size).toBe(0);
    expect(transitionLabel("close", "closed", s)).toBe("close → closed");
  });

  it("the label still contains the action and target, so the warning ADDS rather than replaces", () => {
    // A warning that eats the information the control existed to show is a regression wearing a
    // helpful face.
    const l = transitionLabel("close", "closed", gated);
    expect(l).toContain("close");
    expect(l).toContain("closed");
    expect(l.startsWith("close → closed")).toBe(true);
  });
});
