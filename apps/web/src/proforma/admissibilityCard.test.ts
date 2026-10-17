import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ApiClient } from "../api/client";
import {
  LEG_STATUS, VERDICT_TONE, isBlocking, namedBound, renderAdmissibilityCard,
} from "./admissibilityCard";

type Admissibility = Awaited<ReturnType<ApiClient["projectAdmissibility"]>>;
type Leg = Admissibility["legs"][number];

const leg = (over: Partial<Leg> = {}): Leg => ({
  leg: "assumptions", status: "cited", counted: 12, ...over,
} as Leg);

const result = (over: Partial<Admissibility> = {}): Admissibility => ({
  verdict: "admissible", reason: "every leg carries data and every material item names a source.",
  legs: [leg(), leg({ leg: "estimate" }), leg({ leg: "answers" })],
  legs_with_data: ["assumptions", "estimate", "answers"], legs_absent: [],
  legs_not_captured: [], blocking_legs: [], uncited_total: 0,
  project_id: "p1", scenario_id: "s1", note: "there is deliberately NO blended provenance score.",
  ...over,
} as Admissibility);

describe("namedBound — the engine caps the list and keeps the total", () => {
  it("returns the pair when the naming stops short", () => {
    expect(namedBound(leg({ status: "has_uncited", uncited_count: 48,
                            uncited: Array.from({ length: 25 }, (_, i) => `a${i}`) })))
      .toEqual({ named: 25, total: 48 });
  });

  it("is null when nothing is held back, so the card says nothing", () => {
    // Not `{named: 3, total: 3}`: "naming 3 of 3" is noise, and a card that printed it would make
    // the real bound harder to notice.
    expect(namedBound(leg({ status: "has_uncited", uncited_count: 3,
                            uncited: ["a", "b", "c"] }))).toBeNull();
  });

  it("is null for a leg with no uncited items at all", () => {
    expect(namedBound(leg())).toBeNull();
    expect(namedBound(leg({ status: "no_data", counted: 0 }))).toBeNull();
  });
});

describe("isBlocking — absence is not the same as a gap in the evidence", () => {
  it("is true only for a leg whose own items are uncited", () => {
    expect(isBlocking(leg({ status: "has_uncited" }))).toBe(true);
    expect(isBlocking(leg({ status: "no_data" }))).toBe(false);
    expect(isBlocking(leg({ status: "not_captured" }))).toBe(false);
    expect(isBlocking(leg())).toBe(false);
  });
});

describe("the distinction this card exists to preserve", () => {
  it("renders no_data and not_captured as DIFFERENT answers with different next steps", () => {
    // The engine's central claim: "you have not filled this in" and "this system has nowhere to put
    // it" send a reader to completely different places — one fills a field, the other changes a
    // schema. A card that rendered both as a dash would destroy it.
    expect(LEG_STATUS.no_data!.word).not.toBe(LEG_STATUS.not_captured!.word);
    expect(LEG_STATUS.no_data!.next).not.toBe(LEG_STATUS.not_captured!.next);
    expect(LEG_STATUS.no_data!.next).toContain("filled this in");
    expect(LEG_STATUS.not_captured!.next).toContain("schema");
  });

  it("never presents `incomplete` as a pass", () => {
    expect(VERDICT_TONE.incomplete!.word).toContain("not a pass");
    expect(VERDICT_TONE.incomplete!.colour).not.toBe(VERDICT_TONE.admissible!.colour);
  });
});

// --- the card -----------------------------------------------------------------------------------

function ctx(over: Record<string, unknown> = {}) {
  const api = { projectAdmissibility: vi.fn().mockResolvedValue(result()),
                ...over } as unknown as ApiClient;
  const root = document.createElement("div");
  const status: string[] = [];
  return { root, api, status,
           c: { api, projectId: () => (over.pid === null ? null : "p1"),
                setStatus: (m: string) => status.push(m) } };
}
const flush = async () => { for (let i = 0; i < 4; i++) await Promise.resolve(); };

describe("renderAdmissibilityCard", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the verdict, its reason and every leg", async () => {
    const { root, c } = ctx();
    const host = renderAdmissibilityCard(root, c as never);
    await flush();
    const txt = host.textContent ?? "";
    expect(txt).toContain("ADMISSIBLE");
    expect(txt).toContain("every material item names a source");
    for (const l of ["assumptions", "estimate", "answers"]) expect(txt).toContain(l);
  });

  it("prints a BOUND on a capped list rather than its length as a total", async () => {
    const { root, c } = ctx({
      projectAdmissibility: vi.fn().mockResolvedValue(result({
        verdict: "blocked",
        reason: "48 item(s) across 1 leg(s) carry no source.",
        legs: [leg({ status: "has_uncited", uncited_count: 48,
                     uncited: Array.from({ length: 25 }, (_, i) => `equity.lp_pct.${i}`) }),
               leg({ leg: "estimate" }), leg({ leg: "answers" })],
        blocking_legs: ["assumptions"], uncited_total: 48,
      })),
    });
    const host = renderAdmissibilityCard(root, c as never);
    await flush();
    const txt = host.textContent ?? "";
    expect(txt).toContain("BLOCKED");
    expect(txt).toContain("48 uncited");
    expect(txt).toContain("naming 25 of 48");
    expect(txt).toContain("equity.lp_pct.0");
  });

  it("tells the two kinds of absence apart on screen", async () => {
    const { root, c } = ctx({
      projectAdmissibility: vi.fn().mockResolvedValue(result({
        verdict: "incomplete",
        reason: "every leg that HAS data is fully cited, but 2 leg(s) hold nothing at all.",
        legs: [leg(),
               leg({ leg: "estimate", status: "no_data", counted: 0,
                     note: "the ledger holds no lines" }),
               leg({ leg: "answers", status: "not_captured", counted: 0,
                     note: "no store keeps the claims" })],
        legs_absent: ["estimate"], legs_not_captured: ["answers"],
      })),
    });
    const host = renderAdmissibilityCard(root, c as never);
    await flush();
    const txt = host.textContent ?? "";
    expect(txt).toContain("INCOMPLETE — not a pass");
    expect(txt).toContain("nothing recorded");
    expect(txt).toContain("nowhere to record it");
    expect(txt).toContain("filled this in");
    expect(txt).toContain("schema");
  });

  it("says when there is no scenario to judge, rather than reporting a clean assumptions leg", async () => {
    const { root, c } = ctx({
      projectAdmissibility: vi.fn().mockResolvedValue(result({
        verdict: "incomplete", scenario_id: null,
        legs: [leg({ status: "no_data", counted: 0 }), leg({ leg: "estimate" }),
               leg({ leg: "answers" })],
      })),
    });
    const host = renderAdmissibilityCard(root, c as never);
    await flush();
    expect(host.textContent).toContain("No saved scenario");
  });

  it("refuses without a project, and does not call the route", async () => {
    const { root, c, api } = ctx({ pid: null });
    const host = renderAdmissibilityCard(root, c as never);
    await flush();
    expect(host.textContent).toContain("Open or save a project");
    expect((api as unknown as { projectAdmissibility: ReturnType<typeof vi.fn> })
      .projectAdmissibility).not.toHaveBeenCalled();
  });

  it("reports a failure as a reason, never as an admissible record", async () => {
    const { root, c } = ctx({
      projectAdmissibility: vi.fn().mockRejectedValue(new Error("403 forbidden")),
    });
    const host = renderAdmissibilityCard(root, c as never);
    await flush();
    expect(host.textContent).toContain("Admissibility unavailable: 403 forbidden");
    expect(host.textContent).not.toContain("ADMISSIBLE");
  });
});
