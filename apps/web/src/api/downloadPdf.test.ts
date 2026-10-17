import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { camStatementPath, downloadPostedPdf, optionsBoardBody, optionsBoardPath } from "./downloadPdf";

describe("CAM statement is a POST path, not a GET href", () => {
  it("names the lease PDF route the UI will POST", () => {
    expect(camStatementPath("p1", "lease-9")).toBe("/projects/p1/cam/statement/lease-9.pdf");
  });
});

describe("OPTION-BOARD-DARK — the design-option deck is a POST with a body", () => {
  const api = { url: (p: string) => `http://x${p}`, authHeaders: () => ({ Authorization: "Bearer t" }) };

  /** A minimal PDF response, plus the click the browser would do. */
  function stubFetch(): { calls: RequestInit[] } {
    const calls: RequestInit[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_u: string, init: RequestInit) => {
      calls.push(init);
      return {
        ok: true,
        headers: new Headers({ "Content-Disposition": 'inline; filename="x-options-board.pdf"' }),
        blob: async () => new Blob([new Uint8Array([37, 80, 68, 70])], { type: "application/pdf" }),
      } as unknown as Response;
    }));
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:1");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    return { calls };
  }

  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("names the board route the UI will POST", () => {
    expect(optionsBoardPath("p1")).toBe("/projects/p1/design/options/board.pdf");
  });

  it("sends the option set as a JSON body, with the content type that implies", async () => {
    const { calls } = stubFetch();
    await downloadPostedPdf(api, optionsBoardPath("p1"), "b.pdf", { options: [{ label: "A" }] });
    expect(calls).toHaveLength(1);
    expect(calls[0]?.method).toBe("POST");
    expect(JSON.parse(String(calls[0]?.body))).toEqual({ options: [{ label: "A" }] });
    const h = calls[0]?.headers as Record<string, string>;
    expect(h["Content-Type"]).toBe("application/json");
    expect(h.Authorization).toBe("Bearer t");       // the auth header is not lost to the spread
  });

  /**
   * The CAM statement takes its input from the URL and has always POSTed with NO body. Sending
   * `{}` instead of nothing would make FastAPI's `Body(..., embed=True)` 422 on a missing key, so
   * "no body" has to stay exactly that rather than becoming an empty object.
   */
  it("still sends NO body — and no JSON content type — when none is given", async () => {
    const { calls } = stubFetch();
    await downloadPostedPdf(api, camStatementPath("p1", "lease-9"), "c.pdf");
    expect(calls[0]?.body).toBeUndefined();
    expect("body" in (calls[0] ?? {})).toBe(false);
    expect((calls[0]?.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });
});

describe("the deck is built from the set that was SCORED", () => {
  it("passes the option set through, not a copy and not a re-derivation", () => {
    const options = [{ label: "A" }, { label: "B" }];
    const body = optionsBoardBody({ options });
    expect(body.options).toBe(options);          // identity: nothing re-derived on the way out
    expect("weights" in body).toBe(false);       // absent, not `undefined` — see the docstring
  });

  it("carries explicit weights so the deck ranks the way the table did", () => {
    expect(optionsBoardBody({ options: [], weights: { cost: 2 } }))
      .toEqual({ options: [], weights: { cost: 2 } });
  });

  /**
   * THE SOURCE-LEVEL HALF, and its limit is stated rather than discovered later.
   *
   * The panel that owns the choice (`portal/panels/analytics.ts`) has no test file, and the wrong
   * alternative sits one identifier away: `s.options` is the SCORED output, `g.options` the set
   * that was scored. A swap between them is invisible in a diff and produces a deck that can
   * disagree with the table it was taken from. This is the same bargain
   * `services/api/test_route_reachability.py` makes for URL literals — it pins the TEXT, so it
   * cannot see a click handler that never runs, and it can see this.
   *
   * It asserts its own anchor first, so a rename of the holder makes the check fail loudly rather
   * than pass by matching nothing.
   */
  it("the GEN-SCORE card posts the scored INPUT, held at score time", () => {
    const src = readFileSync(resolve(__dirname, "../portal/panels/analytics.ts"), "utf8");
    expect(src, "the board button's holder is gone — re-read the panel before trusting this")
      .toContain("optionsBoardBody(scored)");
    expect(src, "`scored` must be assigned the GENERATED set that was passed to the score call")
      .toContain("scored = { options: g.options }");
    expect(src.includes("scored = { options: s.options }"),
           "the holder now keeps the SCORED OUTPUT, so the deck would re-score the engine's own "
           + "answer — post the set that was scored").toBe(false);
  });
});
