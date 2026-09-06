import { describe, expect, it, vi } from "vitest";

import type { PanelContext } from "../panelContext";
import { renderMasterBuilder } from "./masterBuilder";

/**
 * The share-link form is the ONLY place this product mints a share token, so it is the only place
 * the geometry opt-in can be offered — and the only place it can be silently dropped.
 *
 * `api/shareTokenGrants.test.ts` proves the client puts `show_model` on the wire. That is a claim
 * about the METHOD. This is the claim about the USE: a checkbox that exists, renders and is never
 * read would satisfy the first test completely and leave the capability exactly as unreachable as
 * it was. This repo has been bitten by that distinction before — a gate that saw a value
 * destructured and stayed green after the calls to it were deleted — so the assertions here drive
 * the real DOM: tick the box, click the button, and read what the client was asked for.
 */

const BRIEF = {
  project: "Test project", readiness_pct: 50, ready_steps: 4, gap_steps: 4, step_count: 8,
  grounded_in_place: true, jurisdiction: "Miami-Dade, FL", reframe_prompt: "What is this place for?",
  place_grounding: { code_family: "IBC", coordinates: null, hemisphere: null, climate_band: null,
    hazards_to_verify: [] },
  steps: [], disclaimer: "Not a substitute for licensed judgment.",
};

const flush = async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); };

function ctx(over: Record<string, unknown> = {}) {
  const api = {
    masterBuilderBrief: vi.fn().mockResolvedValue(BRIEF),
    masterBuilderBriefMdUrl: () => "/md",
    sharedPageUrl: (t: string) => `/shared/${t}`,
    shareTokens: vi.fn().mockResolvedValue({ tokens: [] }),
    createShareToken: vi.fn().mockResolvedValue({ token: "new" }),
    revokeShareToken: vi.fn().mockResolvedValue({ revoked: true }),
    ...over,
  };
  const c: PanelContext = {
    root: document.createElement("div"),
    host: { projectId: () => "p1", api } as unknown as PanelContext["host"],
    mods: [], activeKey: "__mb__",
    bar: (title) => { const b = document.createElement("div"); b.textContent = title; return b; },
    buildNav: () => undefined, renderHome: async () => undefined, openModule: async () => undefined,
    navigate: () => undefined, hasDest: () => true,
  };
  return { c, api };
}

/** The two opt-in checkboxes, found by their labels rather than by DOM order. */
function boxes(root: HTMLElement) {
  const find = (needle: string) => {
    for (const l of Array.from(root.querySelectorAll("label"))) {
      if ((l.textContent ?? "").includes(needle)) return l.querySelector("input") as HTMLInputElement;
    }
    throw new Error(`no opt-in labelled ${needle} — found: `
      + Array.from(root.querySelectorAll("label")).map((l) => l.textContent).join(" | "));
  };
  return { pay: find("payment schedule"), model: find("3D model") };
}

const createBtn = (root: HTMLElement) =>
  Array.from(root.querySelectorAll("button")).find((b) => b.textContent?.includes("Create link"))!;

describe("R22-PUBLIC-VIEWER — the geometry opt-in is offered, and it is READ", () => {
  it("offers a 3D-model opt-in beside the payments one, both unchecked", async () => {
    const { c } = ctx();
    await renderMasterBuilder(c); await flush();
    const b = boxes(c.root as HTMLElement);
    expect(b.pay.checked).toBe(false);
    expect(b.model.checked).toBe(false);
  });

  it("passes the ticked box through to createShareToken — the wiring, not the widget", async () => {
    const { c, api } = ctx();
    await renderMasterBuilder(c); await flush();
    boxes(c.root as HTMLElement).model.checked = true;
    createBtn(c.root as HTMLElement).click();
    await flush();
    expect(api.createShareToken).toHaveBeenCalledTimes(1);
    // (pid, label, showPayments, showModel) — the 4th argument is the one that did not exist.
    expect(api.createShareToken.mock.calls[0]).toEqual(["p1", undefined, false, true]);
  });

  it("grants stay independent: payments alone never carries geometry", async () => {
    // The backend refuses to let one imply the other. A UI that quietly sent both when either was
    // ticked would be a widening the backend's rule exists to forbid, and no backend test could see
    // it — the request would look like a deliberate double opt-in.
    const { c, api } = ctx();
    await renderMasterBuilder(c); await flush();
    boxes(c.root as HTMLElement).pay.checked = true;
    createBtn(c.root as HTMLElement).click();
    await flush();
    expect(api.createShareToken.mock.calls[0]).toEqual(["p1", undefined, true, false]);
  });

  it("resets both boxes after a mint, so a grant never carries to the next link", async () => {
    const { c } = ctx();
    await renderMasterBuilder(c); await flush();
    const b = boxes(c.root as HTMLElement);
    b.model.checked = true; b.pay.checked = true;
    createBtn(c.root as HTMLElement).click();
    await flush();
    expect(b.model.checked).toBe(false);
    expect(b.pay.checked).toBe(false);
  });

  it("marks which live links grant geometry, so the opt-in can be audited after minting", async () => {
    const tok = (over: Record<string, unknown>) => ({
      token: "0123456789abcdef", label: null, revoked: false, created_at: null, created_by: null,
      view_count: 0, last_viewed_at: null, share_path: "/s", show_payments: false, show_model: false,
      ...over,
    });
    const { c } = ctx({ shareTokens: vi.fn().mockResolvedValue({ tokens: [
      tok({ token: "aaaaaaaaaaaaaaaa", label: "digest only" }),
      tok({ token: "bbbbbbbbbbbbbbbb", label: "with model", show_model: true }),
    ] }) });
    await renderMasterBuilder(c); await flush();
    const links = Array.from((c.root as HTMLElement).querySelectorAll("a"))
      .filter((a) => (a.textContent ?? "").includes("…"));
    expect(links).toHaveLength(2);
    const plain = links.find((a) => a.textContent!.includes("digest only"))!;
    const withModel = links.find((a) => a.textContent!.includes("with model"))!;
    expect(withModel.textContent).toContain("🧊");
    expect(withModel.title).toContain("3D model");
    // The negative half. Without it the marker could be unconditional and every assertion above
    // would still pass, which would make the audit trail confidently wrong rather than absent.
    expect(plain.textContent).not.toContain("🧊");
    expect(plain.title).not.toContain("3D model");
  });
});
