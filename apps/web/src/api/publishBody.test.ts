import { describe, expect, it, vi } from "vitest";

import { ApiClient } from "./client";

/**
 * `POST /publish` takes a BARE boolean body, and the client sent an object to it.
 *
 * THE DEFECT. The route declares `reconvert: bool = Body(default=True)` with no `embed=True`, so
 * FastAPI treats the whole request body as the value. `api.publish` sent `{"reconvert": true}` —
 * which the server rejects with **422** — from the day it was written. Verified against a running
 * API before fixing:
 *
 *     {"reconvert": true}  ->  422 Unprocessable Entity
 *     true                 ->  202 Accepted
 *
 * TWO USER-FACING PATHS WERE DEAD: the rail's `⟳ Republish (reconvert + reindex)` and the AI
 * authoring plan's Apply, which authors N edits with `publish=false` and then calls `api.publish`
 * to convert them. The second is the worse one — the edits land in the IFC and the geometry is
 * never rebuilt.
 *
 * WHY NOTHING CAUGHT IT. The failure is a rejected promise inside a click handler with no `catch`,
 * so there is no error banner and no console assertion — the button simply never finishes. A
 * screenshot of that state looks like a slow publish. This is why the wire SHAPE deserves a test of
 * its own: every other test in this repo exercises the client's TypeScript surface, which was always
 * correct, against a server contract nothing compared it to.
 *
 * The assertion is deliberately about the encoded body rather than about a mock's arguments: what
 * reaches the server is the only thing the route can be wrong about.
 */

function captureBody() {
  const seen: { url: string; body: string | null }[] = [];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    seen.push({ url: String(url), body: (init?.body as string) ?? null });
    return new Response(JSON.stringify({ state: "running" }), {
      status: 202, headers: { "content-type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return seen;
}

describe("POST /publish wire shape", () => {
  it("sends a BARE boolean, not an object — the shape the route accepts", async () => {
    const seen = captureBody();
    await new ApiClient("http://x").publish("p1");
    expect(seen).toHaveLength(1);
    expect(seen[0]!.url).toContain("/projects/p1/publish");
    // `"true"`, not `'{"reconvert":true}'`. Asserting the exact encoded body is the point: a check
    // that only looked for the substring "true" would pass on the broken object form too.
    expect(seen[0]!.body).toBe("true");
    vi.unstubAllGlobals();
  });

  it("passes reconvert=false through, which is what makes a reindex-only publish reachable", async () => {
    const seen = captureBody();
    await new ApiClient("http://x").publish("p1", false);
    expect(seen[0]!.body).toBe("false");
    vi.unstubAllGlobals();
  });

  it("never sends the object form that 422s", async () => {
    // The regression, stated as the thing that must not come back. Written as a negative because
    // the bug was not a wrong VALUE — it was a wrong CONTAINER, and only the container can express
    // it.
    const seen = captureBody();
    const api = new ApiClient("http://x");
    await api.publish("p1");
    await api.publish("p1", false);
    for (const s of seen) {
      expect(s.body, "an object body is exactly what the server refuses").not.toContain("{");
      expect(s.body, "…and it must not be wrapped under a key either").not.toContain("reconvert");
    }
    vi.unstubAllGlobals();
  });
});
