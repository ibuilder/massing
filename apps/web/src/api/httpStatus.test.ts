import { readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { CloudError } from "./cloud";
import { HttpError, permanentRejection } from "./httpCore";

/**
 * UPLOAD-POISON's gate: an HTTP failure this client raises must CARRY its status, not describe it.
 *
 * WHY THIS EXISTS. FIELD-POISON gave `HttpCore.json` an `HttpError` so the offline field queue could
 * tell a permanent refusal from a transient one. That fixed the busiest call path and left the class
 * open: 50 of the 51 `!res.ok` guards in this directory still threw a bare `Error` whose only record
 * of the status was the text of its message. The portal's offline UPLOAD queue sat behind two of
 * them, so it could not have been fixed without this even after the field queue was.
 *
 * A caller reduced to `/-> (\d+)$/` on a message is coupled to a spelling, which is the brittleness
 * `services/api/test_money_spine.py` had just spent a PR removing from a different scan. The rule is
 * therefore not "some errors carry a status" but "every one does", and it is asserted over a
 * population DERIVED from the source rather than a list somebody remembered to extend.
 *
 * WHAT IT DOES NOT CHECK. That the status is the RIGHT one, or that a caller does anything sensible
 * with it. This is the structural half; `permanentRejection` below and the two queues' own tests are
 * the behavioural half.
 */
//: `__dirname`, not `import.meta.url` — under vitest's transform the module URL is a
//: virtual path and resolves to `/src/api`, which does not exist on disk.
const API_DIR = resolve(__dirname);

/** A `throw` inside an `if (!x.ok)` guard — the shape every failed-response raise in here takes. */
const GUARDED_THROW = /if \(!(\w+)\.ok\)[\s\S]{0,400}?throw new (\w+)\(/g;

function scan(text: string): { ctor: string; guard: string }[] {
  const out: { ctor: string; guard: string }[] = [];
  for (const m of text.matchAll(GUARDED_THROW)) out.push({ guard: m[1]!, ctor: m[2]! });
  return out;
}

/** Constructors that take the status as an argument rather than baking it into a string. */
const CARRIES_STATUS = new Set(["HttpError", "CloudError"]);

const sources = readdirSync(API_DIR)
  .filter((f) => f.endsWith(".ts") && !f.endsWith(".test.ts") && !f.endsWith(".d.ts"))
  .map((f) => ({ file: f, text: readFileSync(join(API_DIR, f), "utf8") }));

describe("every HTTP failure this client raises carries its status", () => {
  it("scans the real API directory, not a remembered handful", () => {
    // The scope assertion, not a formality: a scan that silently reaches nothing reports a clean
    // tree forever. MONEY-SCOPE's gate passed for weeks over three files it had been handed.
    expect(sources.length).toBeGreaterThan(15);
    expect(sources.map((s) => s.file)).toContain("httpCore.ts");
    expect(sources.map((s) => s.file)).toContain("modules.ts");   // the offline upload queue's two
  });

  it("finds the guarded throws it is supposed to be checking", () => {
    const total = sources.reduce((n, s) => n + scan(s.text).length, 0);
    expect(total).toBeGreaterThan(40);
  });

  it("raises no bare Error from a failed response", () => {
    const bare = sources.flatMap(({ file, text }) =>
      scan(text).filter((t) => !CARRIES_STATUS.has(t.ctor)).map((t) => `${file}: ${t.ctor}`));
    expect(bare, "these bury the status in a message, so only a string parse can read it").toEqual([]);
  });

  it("its own detector is not vacuous — it reports a bare throw when one is present", () => {
    // Both directions. A predicate that decides what to LOOK at is the failure mode that has bitten
    // this repo twice, so the probe proves the scan SEES the shape it is meant to reject, rather
    // than only that the tree is currently clean.
    expect(scan('if (!res.ok) throw new Error(`x -> ${res.status}`);')).toEqual([
      { guard: "res", ctor: "Error" },
    ]);
    expect(scan('if (!r.ok) throw new HttpError((await r.text()) || "x", r.status);')).toEqual([
      { guard: "r", ctor: "HttpError" },
    ]);
  });
});

describe("permanentRejection — the shared retry policy", () => {
  const cases: [unknown, boolean][] = [
    [new HttpError("bad", 400), true],
    [new HttpError("nope", 401), true],
    [new HttpError("nope", 403), true],
    [new HttpError("gone", 404), true],
    [new HttpError("teapot", 418), true],
    [new HttpError("timeout", 408), false],       // explicitly invites a retry
    [new HttpError("slow down", 429), false],     // ditto
    [new HttpError("boom", 500), false],
    [new HttpError("gateway", 503), false],
    [new TypeError("Failed to fetch"), false],    // offline — the most retryable failure there is
    ["not an error at all", false],
  ];

  for (const [err, permanent] of cases) {
    const label = err instanceof HttpError ? `HTTP ${err.status}` : String(err);
    it(`${label} is ${permanent ? "permanent" : "worth retrying"}`, () => {
      expect(permanentRejection(err) !== null).toBe(permanent);
    });
  }

  it("a permanent refusal always comes with something a person can read", () => {
    for (const [err, permanent] of cases) {
      if (!permanent) continue;
      expect(permanentRejection(err)).toBeTruthy();
    }
  });

  it("reads a CloudError too, since it now extends HttpError", () => {
    // The consolidation is the point: before this, a cloud refusal carried its status in a class of
    // its own and no shared classifier could see it.
    const e = new CloudError(402, "needs a paid plan");
    expect(e).toBeInstanceOf(HttpError);
    expect(e.needsUpgrade).toBe(true);
    expect(permanentRejection(e)).toBeTruthy();
    expect(e.name).toBe("CloudError");
  });
});
