import { describe, expect, it, vi } from "vitest";

import { ApiClient } from "./client";
import { HttpError } from "./httpCore";

/**
 * BSDD-LOOKUP's gate: the two `/bsdd` routes shipped with no client caller at all, and the one
 * thing a reference lookup must never do is make "the dictionary is down" look like "nothing
 * matched".
 *
 * WHY THESE ASSERTIONS AND NOT OTHERS. Two things can be wrong here in a way nothing else notices:
 *
 *  1. **The class URI is a URL inside a URL.** A bSDD class is identified by
 *     `https://identifier.buildingsmart.org/uri/<org>/<dict>/<ver>/class/<code>`, and it goes into
 *     our own query string as `?uri=…`. Interpolating it raw happens to work for the common case
 *     and truncates silently the moment a code carries `&` or `#` — the server then looks up a
 *     prefix of the URI and answers 404 for a class that exists. So the test asserts the ENCODED
 *     URL, the way `shareTokenGrants.test.ts` asserts the encoded body: what reaches the server is
 *     the only thing the route can be wrong about.
 *
 *  2. **502 must survive as a status, not as prose.** `routers/standards.py` deliberately maps a
 *     bSDD outage to 502 rather than letting it 500, so the panel can say "reference service
 *     unavailable" instead of rendering an empty result. That disclosure reads `HttpError.status`;
 *     if the client flattened it to a bare `Error` the panel would fall through to its generic
 *     branch and an outage would be indistinguishable from a dictionary with no matches — which is
 *     precisely the failure the 502 exists to prevent.
 */

function captureUrls(response: unknown, status = 200) {
  const seen: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    seen.push(String(url));
    return new Response(JSON.stringify(response), {
      status, headers: { "content-type": "application/json" },
    });
  }));
  return seen;
}

const api = () => new ApiClient("http://x");

describe("GET /bsdd/search", () => {
  it("sends the free-text query", async () => {
    const seen = captureUrls({ classes: [] });
    await api().bsddSearch("exterior wall");
    expect(seen).toHaveLength(1);
    const u = new URL(seen[0]!);
    expect(u.pathname).toBe("/bsdd/search");
    expect(u.searchParams.get("q")).toBe("exterior wall");
    expect(u.searchParams.has("dictionary")).toBe(false);   // absent, not empty-string
  });

  it("scopes to one dictionary only when asked", async () => {
    const seen = captureUrls({ classes: [] });
    const dict = "https://identifier.buildingsmart.org/uri/buildingsmart/ifc";
    await api().bsddSearch("wall", { dictionary: dict, limit: 5 });
    const u = new URL(seen[0]!);
    expect(u.searchParams.get("dictionary")).toBe(dict);
    expect(u.searchParams.get("limit")).toBe("5");
  });
});

describe("GET /bsdd/class", () => {
  it("encodes the class URI, so a code carrying & or # is not truncated", async () => {
    const seen = captureUrls({ uri: "u", name: "n", code: null, dictionary: null, properties: [] });
    // Not hypothetical punctuation for its own sake: `&` ends a query parameter, so a raw
    // interpolation would send `uri=https://…/class/Pr_20` and lose everything after it.
    const uri = "https://identifier.buildingsmart.org/uri/x/d/1.0/class/A&B#c";
    await api().bsddClass(uri);
    expect(seen[0]).toContain(`uri=${encodeURIComponent(uri)}`);
    // And it round-trips: the server would read back exactly what we meant.
    expect(new URL(seen[0]!).searchParams.get("uri")).toBe(uri);
  });

  it("raises a 502 the panel can tell apart from an empty result", async () => {
    captureUrls({ detail: "bSDD unavailable" }, 502);
    // `.rejects.toThrow(HttpError)` alone would pass against an HttpError carrying status 0 —
    // and 0 is what the panel's generic branch renders. The status is the assertion.
    const err = await api().bsddClass("https://identifier.buildingsmart.org/uri/x/d/1.0/class/A")
      .then(() => null, (e: unknown) => e);
    expect(err).toBeInstanceOf(HttpError);
    expect((err as HttpError).status).toBe(502);
  });

  it("raises a 404 with its own status, so 'no such class' is not reported as an outage", async () => {
    captureUrls({ detail: "class not found" }, 404);
    const err = await api().bsddClass("https://identifier.buildingsmart.org/uri/x/d/1.0/class/Z")
      .then(() => null, (e: unknown) => e);
    expect((err as HttpError).status).toBe(404);
  });
});
