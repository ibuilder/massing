import { describe, expect, it, vi } from "vitest";

import { ApiClient } from "./client";

/**
 * A share token's two grants are INDEPENDENT, and the client could only ever send one of them.
 *
 * THE DEFECT. `show_model` is the per-token opt-in that lets a share link fetch the project's
 * geometry — `GET /shared/{token}/model.frag`, gated in `client_portal.model_fragment` on
 * `not getattr(row, "show_model", False)`. The backend has supported it end to end since the column
 * shipped: the route reads `body.get("show_model")`, `_public_row` returns it, and
 * `services/api/test_shared_model.py` already proves the 200-vs-404 pair and that `show_payments`
 * does not imply it. **`createShareToken` sent only `label` and `show_payments`**, so every token
 * this product minted had the flag false and that route 404'd for all of them.
 *
 * WHY NOTHING CAUGHT IT. Both sides were correct in isolation, which is the whole shape of the bug.
 * The backend test mints its own tokens with `json={"show_model": True}` — a body the product never
 * produces — so it passes over a client that cannot ask for the thing it tests. Nothing red, nothing
 * logged, and a 404 from a route nobody had a working link to is indistinguishable from a project
 * with no published fragment, which is deliberately the same response.
 *
 * The assertions are about the ENCODED BODY, not a mock's arguments, for the reason
 * `publishBody.test.ts` gives: what reaches the server is the only thing the route can be wrong
 * about. A test that asserted `createShareToken` was *called* with `true` would have passed against
 * a method that accepted the argument and dropped it — which is one keystroke from the bug.
 */

function captureBody(response: unknown = { token: "t", label: null, share_path: "/shared/t/digest",
  revoked: false, show_payments: false, show_model: false }) {
  const seen: { url: string; body: string | null }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    seen.push({ url: String(url), body: (init?.body as string) ?? null });
    return new Response(JSON.stringify(response), {
      status: 200, headers: { "content-type": "application/json" },
    });
  }));
  return seen;
}

const bodyOf = (raw: string | null) => JSON.parse(raw ?? "{}") as Record<string, unknown>;

describe("POST /projects/{pid}/share-tokens — the geometry opt-in reaches the wire", () => {
  it("sends show_model:true when the caller asks for geometry", async () => {
    const seen = captureBody();
    await new ApiClient("http://x").createShareToken("p1", "Owner review", false, true);
    expect(seen).toHaveLength(1);
    expect(seen[0]!.url).toContain("/projects/p1/share-tokens");
    expect(bodyOf(seen[0]!.body)).toEqual(
      { label: "Owner review", show_payments: false, show_model: true });
    vi.unstubAllGlobals();
  });

  it("ALWAYS sends the key, never omits it — an absent key is not the same request", async () => {
    // `bool(body.get("show_model"))` treats absent and false alike TODAY. This asserts the key is
    // present anyway: the client must state the grant it is asking for rather than rely on a
    // server-side default, because that default is the one thing a future backend could change
    // without touching this file.
    const seen = captureBody();
    await new ApiClient("http://x").createShareToken("p1");
    expect(bodyOf(seen[0]!.body)).toHaveProperty("show_model", false);
    vi.unstubAllGlobals();
  });

  it("the two grants are independent in BOTH directions", async () => {
    // The backend docstring is explicit: "a token may carry payments, or geometry, or neither, and
    // granting one never implies the other." Asserting only the both-true case would pass on a
    // client that had collapsed them into one "share more" flag, which is exactly the design error
    // the wording exists to prevent. So all four corners are checked.
    const seen = captureBody();
    const api = new ApiClient("http://x");
    await api.createShareToken("p1", "a", false, false);
    await api.createShareToken("p1", "b", true, false);
    await api.createShareToken("p1", "c", false, true);
    await api.createShareToken("p1", "d", true, true);
    expect(seen.map((s) => {
      const b = bodyOf(s.body);
      return [b.show_payments, b.show_model];
    })).toEqual([[false, false], [true, false], [false, true], [true, true]]);
    vi.unstubAllGlobals();
  });

  it("the token row carries show_model, so an owner can audit which links grant geometry", async () => {
    // The SECOND half of the defect, and a separate one: `_public_row` has always returned
    // `show_model` and the row type dropped it, so the value was on the wire and unreadable.
    //
    // STATE THE GRADE. This assertion is NOT what guards that half, and pretending otherwise would
    // be the more dangerous outcome — a reader would trust vitest to catch a regression it cannot
    // see. Measured by deleting `show_model` from the `Tok` type: vitest stayed 4/4 GREEN (the
    // runtime reads whatever the response object holds; a type is not there at runtime), while
    // `tsc --noEmit` went red in THREE places — this line and the two `masterBuilder.ts` reads.
    // The typecheck is the gate; this line exists so the field is exercised by a caller at all.
    captureBody({ tokens: [
      { token: "aaaaaaaaaa", label: "digest only", revoked: false, created_at: null, created_by: null,
        view_count: 0, last_viewed_at: null, share_path: "/shared/aaaaaaaaaa/digest",
        show_payments: false, show_model: false },
      { token: "bbbbbbbbbb", label: "with model", revoked: false, created_at: null, created_by: null,
        view_count: 3, last_viewed_at: null, share_path: "/shared/bbbbbbbbbb/digest",
        show_payments: false, show_model: true },
    ] });
    const { tokens } = await new ApiClient("http://x").shareTokens("p1");
    expect(tokens.map((t) => t.show_model)).toEqual([false, true]);
    vi.unstubAllGlobals();
  });
});
