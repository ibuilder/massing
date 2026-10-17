import { afterEach, describe, expect, it, vi } from "vitest";

import { HttpError } from "../../api/httpCore";
import type { PanelContext } from "../panelContext";
import { renderPrefabKits } from "./prefabKitsPanel";

/**
 * PREFAB-FREEZE-RACE — **the consumer half, which is where this defect class always is.**
 *
 * `prefabKits.ts` is tested beside itself and `test_prefab_route.py` proves the route refuses a
 * stale token. Neither reaches the thing that can still be wrong: *which* token the panel sends, and
 * what it does with the refusal. Mutation made that concrete — every assertion below survives a
 * panel that re-reads the kit and sends a FRESH token, which is the one change that would defeat the
 * precondition entirely while leaving both other test files green.
 *
 * A fresh token is a token for numbers nobody has seen. The point of the precondition is that the
 * string travelling with the write is the one the reader was looking at, so this file asserts the
 * provenance of that string and not merely its presence.
 */

const KIT = {
  id: 7, ref: "KIT-004", name: "Level 3 riser", trade: "mechanical", fabricator: null,
  state: "draft", scope_source: "selector" as const,
  scope_version: "m3.r2026-09-11T08:00:00+00:00",
  selector: { selector: "type=IfcPipeSegment", guids: ["a", "b"], matched: 2 },
  frozen_count: 0, elements: 2,
  bom: { lines: [], totals: {}, unresolved: [] },
  drift: null, blockers: [], ready: true, as_of: "2026-09-11",
};

/** The same kit after a republish: a NEW token, and — deliberately — the SAME counts. */
const AFTER = { ...KIT, scope_version: "m4.r2026-09-11T08:00:00+00:00" };

const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };

/** The panel gates the write behind `window.confirm`, which this environment does not implement —
 *  so it is installed rather than spied on. `vi.spyOn` needs an existing function and fails with
 *  "can only spy on a function", which is a true complaint about the environment and reads as a
 *  complaint about the test. */
const confirming = (answer: boolean) => vi.stubGlobal("confirm", vi.fn(() => answer));

afterEach(() => { vi.unstubAllGlobals(); });

function ctx(freeze: ReturnType<typeof vi.fn>, kitRead = AFTER) {
  const api = {
    prefabRegister: vi.fn().mockResolvedValue({
      kits: [structuredClone(KIT)], total: 1, ready: 1, blocked: 0, blocker_counts: {},
      as_of: "2026-09-11", model_loaded: true,
    }),
    prefabKit: vi.fn().mockImplementation(() => Promise.resolve(structuredClone(kitRead))),
    prefabFreeze: freeze,
  };
  const status: string[] = [];
  const c = {
    root: document.createElement("div"),
    host: {
      projectId: () => "p1", api,
      setStatus: (m: string) => { status.push(m); },
      onSelectGuids: () => undefined,
    } as unknown as PanelContext["host"],
    mods: [], activeKey: "prefab",
    bar: (t: string) => { const b = document.createElement("div"); b.textContent = t; return b; },
    buildNav: () => undefined, renderHome: async () => undefined,
    openModule: async () => undefined, navigate: () => undefined, hasDest: () => true,
  } as unknown as PanelContext;
  return { c, api, status };
}

const writeBtn = (root: HTMLElement) =>
  [...root.querySelectorAll("button")].find((b) => (b.textContent ?? "").includes("the scope"))!;

describe("the token the panel sends", () => {
  it("is the one from the read THIS CARD was built from", async () => {
    const freeze = vi.fn().mockResolvedValue({
      ref: "KIT-004", matched: 2, selector: "x", frozen: 2,
      scope_version: "m3.r2026-09-11T09:00:00+00:00", note: "written",
    });
    confirming(true);
    const { c, api } = ctx(freeze);
    await renderPrefabKits(c); await flush();
    writeBtn(c.root).click(); await flush();
    expect(freeze).toHaveBeenCalledWith("p1", "7", KIT.scope_version);
    // THE PROVENANCE ASSERTION, and it is about ORDER rather than absence. A panel that re-read the
    // kit to get a token would still call `prefabFreeze` with a perfectly valid string, and the
    // server would accept it — over exactly the change the precondition exists to catch. What
    // separates the two panels is that the honest one has not read the kit again BEFORE writing.
    //
    // The first draft of this asserted `prefabKit` was never called, which is false for a reason
    // that matters: a successful write re-reads the kit to rebuild the card. *"Never" and "not
    // yet" are different claims, and the stronger-sounding one was simply wrong.*
    const reads = (api.prefabKit as ReturnType<typeof vi.fn>).mock.invocationCallOrder;
    expect(freeze.mock.invocationCallOrder[0], "the panel read the kit before writing — that token "
      + "is for numbers nobody has seen").toBeLessThan(Math.min(...reads));
  });

  it("does not freeze at all when the confirmation is declined", async () => {
    const freeze = vi.fn();
    confirming(false);
    const { c } = ctx(freeze);
    await renderPrefabKits(c); await flush();
    writeBtn(c.root).click(); await flush();
    expect(freeze).not.toHaveBeenCalled();
  });
});

describe("a 409 is the precondition working, not a failure", () => {
  /** The route's own literal, as `prefab_kit.FREEZE_STALE_SCOPE` sends it. */
  const STALE = "the kit's scope changed since you were shown it — the model was republished or the "
    + "record was edited, so this write would record a list you have not seen; re-read the kit and "
    + "confirm against the new numbers";
  /**
   * The OTHER 409 body, and the reason the recovery is keyed on the status.
   * `modules.update_record`'s stale-write refusal puts a DICT in `detail`, and `httpCore.json` only
   * surfaces a string one — so that 409 reaches the client as this bare fallback, with no sentence
   * in it at all. A branch keyed on the message cannot see it.
   *
   * **This fixture exists because mutation found the hole in its predecessor.** The first draft
   * rejected with `new HttpError("scope moved", 409)`, and swapping the status check for
   * `message.includes("scope moved")` then passed every test in this file — *a fixture whose
   * message happens to match makes a message-keyed bug invisible.* The literals here are the two
   * the server actually sends.
   */
  const BARE = "POST /projects/p1/prefab/kits/7/freeze -> 409";
  const stale = () => vi.fn().mockRejectedValue(new HttpError(STALE, 409));

  it("re-reads the kit, swaps the card, and says WHAT moved", async () => {
    confirming(true);
    const { c, api, status } = ctx(stale());
    await renderPrefabKits(c); await flush();
    writeBtn(c.root).click(); await flush();
    expect(api.prefabKit).toHaveBeenCalledWith("p1", "7");
    expect(status.join(" ")).toContain("not written");
    expect(status.join(" ")).toContain("The model was republished");
    // It must NOT read as a failure. "could not write the scope" invites a blind retry, which is
    // the behaviour this whole item exists to stop.
    expect(status.join(" ")).not.toContain("could not write the scope");
  });

  it("RE-ARMS with the new token, so a second click is a fresh decision", async () => {
    // The recovery is only a recovery if the next write carries the numbers the reader has now
    // seen. A card that came back holding the spent token would 409 for ever and look like a
    // server fault.
    const freeze = vi.fn()
      .mockRejectedValueOnce(new HttpError("scope moved", 409))
      .mockResolvedValueOnce({ ref: "KIT-004", matched: 2, selector: "x", frozen: 2,
                               scope_version: "m5.r0", note: "written" });
    confirming(true);
    const { c } = ctx(freeze);
    await renderPrefabKits(c); await flush();
    writeBtn(c.root).click(); await flush();
    writeBtn(c.root).click(); await flush();
    expect(freeze).toHaveBeenNthCalledWith(1, "p1", "7", KIT.scope_version);
    expect(freeze).toHaveBeenNthCalledWith(2, "p1", "7", AFTER.scope_version);
  });

  it("recovers from the OTHER 409 too — the one carrying no sentence", async () => {
    // `modules.update_record`'s stale-write 409 has a dict detail, so it arrives as a bare
    // method-path-status line. Two bodies, one recovery: the panel keys on the status, which is the
    // only thing both carry.
    confirming(true);
    const { c, api, status } = ctx(vi.fn().mockRejectedValue(new HttpError(BARE, 409)));
    await renderPrefabKits(c); await flush();
    writeBtn(c.root).click(); await flush();
    expect(api.prefabKit).toHaveBeenCalledWith("p1", "7");
    expect(status.join(" ")).toContain("not written");
    expect(status.join(" ")).not.toContain("could not write the scope");
  });

  it("says nothing was written even when the re-read ALSO fails", async () => {
    // Two things went wrong and only one of them matters to the reader: the write did not happen.
    // Reporting the re-read's failure as the headline would leave them unsure whether the shop's
    // list changed.
    confirming(true);
    const { c, api, status } = ctx(stale());
    (api.prefabKit as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("offline"));
    await renderPrefabKits(c); await flush();
    writeBtn(c.root).click(); await flush();
    expect(status.join(" ")).toContain("nothing was written");
    expect(status.join(" ")).not.toContain("offline");
  });
});

describe("the other refusals are unchanged", () => {
  it("a 422 still shows the server's own literal, not the 409 recovery", async () => {
    confirming(true);
    const { c, api, status } = ctx(
      vi.fn().mockRejectedValue(new HttpError("the selector matches no elements", 422)));
    await renderPrefabKits(c); await flush();
    writeBtn(c.root).click(); await flush();
    expect(status.join(" ")).toContain("the selector matches no elements");
    expect(api.prefabKit, "a 422 is about the scope, not about staleness — nothing to re-read")
      .not.toHaveBeenCalled();
  });

  it("a plain Error (no status) is not mistaken for a 409", async () => {
    // `HttpError` carries the status; a transport failure arrives as a bare Error. Keying the
    // recovery on `message` rather than `status` would have matched neither reliably.
    confirming(true);
    const { c, api, status } = ctx(vi.fn().mockRejectedValue(new Error("network down")));
    await renderPrefabKits(c); await flush();
    writeBtn(c.root).click(); await flush();
    expect(status.join(" ")).toContain("could not write the scope");
    expect(api.prefabKit).not.toHaveBeenCalled();
  });
});

describe("a successful write", () => {
  it("reports what was written and re-reads the kit for the new card", async () => {
    const freeze = vi.fn().mockResolvedValue({
      ref: "KIT-004", matched: 2, selector: "x", frozen: 2, scope_version: "m3.r9", note: "written",
    });
    confirming(true);
    const { c, api, status } = ctx(freeze);
    await renderPrefabKits(c); await flush();
    writeBtn(c.root).click(); await flush();
    expect(status.join(" ")).toContain("2 elements written");
    expect(api.prefabKit).toHaveBeenCalledWith("p1", "7");
  });
});
