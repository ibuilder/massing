import { describe, it, expect, vi, afterEach } from "vitest";
import { ApiClient } from "./client";
import { HttpError } from "./httpCore";

/**
 * `HttpCore.json` used to throw `POST /x -> 422` and DISCARD the response body, so every handler
 * that answers a refusal with a deliberate fixed literal reached the user as a status code.
 *
 * Found by review on `prefabFreeze`, whose own comment claimed the literal was being shown — **a
 * comment asserting a behaviour the platform did not have**, which is worse than no comment,
 * because it stops the next reader from checking.
 */
const api = () => new ApiClient("http://x");

/** The refusal a call produced. Fails loudly if it RESOLVED — a test that silently accepted a
 *  success would assert nothing at all about the error path it is named for. */
async function refusal(p: Promise<unknown>): Promise<HttpError> {
  try { await p; } catch (e) { return e as HttpError; }
  throw new Error("expected the request to be refused, but it resolved");
}

const respond = (status: number, body: unknown, ok = false) => {
  vi.stubGlobal("fetch", vi.fn(async () => ({
    ok, status,
    json: async () => body,
  })));
};

afterEach(() => { vi.unstubAllGlobals(); });

describe("a refused request carries the server's own sentence", () => {
  it("uses `detail` as the error message, and keeps the status", async () => {
    respond(422, { detail: "the selector matched no elements" });
    const e = await refusal(api().prefabFreeze("p1", "k1"));
    expect(e).toBeInstanceOf(HttpError);
    expect(e.message).toBe("the selector matched no elements");
    expect(e.status).toBe(422);
  });

  it("falls back to method + path + status when the body carries no detail", async () => {
    // A 502 from a proxy is not JSON with a `detail`; losing the path there would leave a reader
    // with nothing to search for.
    respond(502, { oops: true });
    const e = await refusal(api().prefabFreeze("p1", "k1"));
    expect(e.message).toContain("/projects/p1/prefab/kits/k1/freeze");
    expect(e.message).toContain("502");
    expect(e.status).toBe(502);
  });

  it("falls back when the body is not JSON at all, rather than throwing while building the error", async () => {
    // The failure path must not have its own failure path. An HTML error page from a reverse proxy
    // rejects in `res.json()`, and a throw there would replace a useful HttpError with a parse error.
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: false, status: 504, json: async () => { throw new SyntaxError("Unexpected token <"); },
    })));
    const e = await refusal(api().prefabFreeze("p1", "k1"));
    expect(e).toBeInstanceOf(HttpError);
    expect(e.status).toBe(504);
    expect(e.message).toContain("504");
  });

  it("ignores a non-string detail instead of rendering [object Object]", async () => {
    // FastAPI's *validation* errors put an ARRAY in `detail`. Interpolating that gives the user
    // "[object Object]", which is strictly worse than the status line it replaced.
    respond(422, { detail: [{ loc: ["body", "x"], msg: "field required" }] });
    const e = await refusal(api().prefabFreeze("p1", "k1"));
    expect(e.message).toContain("422");
    expect(e.message).not.toContain("object Object");
  });
});
