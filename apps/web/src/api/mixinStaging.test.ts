import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { ApiClient } from "./client";

/**
 * MIXIN-CEILING. `client.ts` composes its mixins in TWO STAGES, and the shape is load-bearing
 * rather than stylistic — collapsing it back into one nested `extends` makes `tsc` fail outright,
 * on the next route group anyone adds.
 *
 * WHAT WAS MEASURED, in both directions:
 *
 * | composition | mixins | `tsc` |
 * |---|---|---|
 * | one nested `extends` | 49 | passes |
 * | one nested `extends` | 50 | **TS2589** |
 * | `const Stage = withA(withB(…))` split | 50 | **TS2589** |
 * | `class _StageA extends …` declarations | 50 | passes |
 *
 * Two things that follow, both of which rule out an easier fix:
 *
 *  - **It is DEPTH, not accumulated members.** A 50th mixin declaring NO methods at all fails
 *    identically, so trimming the API surface would not buy headroom.
 *  - **A `const` split does not work.** It infers the same nested anonymous type, so the depth is
 *    unchanged. Only a `class` DECLARATION names the type nominally, letting the second stage start
 *    from a resolved base instead of re-walking the first.
 *
 * WHY A TEST AND NOT A COMMENT. The comment in `client.ts` explains the shape; nothing but this
 * enforces it. A tidy-minded refactor that inlines the two stages compiles fine TODAY at 49 and
 * strands the next person at 50 with an error message naming neither the cause nor the limit — the
 * position this repo was actually in when BSDD-LOOKUP hit it.
 *
 * A NOTE ON HOW THE LAST assertion WAS VERIFIED. The first attempt to mutate a stage hollow
 * silently failed to apply — an f-string rebuild that did not match the source byte for byte — and
 * the suite reported green, which reads exactly like a correct implementation. *A mutation that does
 * not apply is a test that was never exercised.* The mutation now asserts the file changed before
 * running anything. Same family as the rest of this repo's lessons: the check did not fail, it
 * answered.
 *
 * This does NOT re-measure the ceiling: a test cannot add a 50th mixin and typecheck. It asserts
 * the structure the measurement justified. `api/surface.test.ts` separately floors the method count,
 * so a stage dropped on the floor is caught there rather than here.
 */
//: `__dirname`, not `import.meta.url` — under vitest's transform the module URL is a virtual path
//: that does not exist on disk (the reason `api/httpStatus.test.ts` gives).
const SRC = readFileSync(join(resolve(__dirname), "client.ts"), "utf8");

describe("the ApiClient mixin chain stays staged", () => {
  it("is reading the file it thinks it is", () => {
    // Without this every assertion below passes forever against an empty string.
    expect(SRC).toContain("export class ApiClient");
    expect(SRC).toContain("HttpCore");
  });

  it("composes through intermediate CLASS DECLARATIONS, not one expression", () => {
    // `class _X extends …` specifically: a `const` split was measured and does NOT clear TS2589.
    const stages = SRC.match(/^class _ApiStage[A-Z] extends /gm) ?? [];
    expect(stages.length).toBeGreaterThanOrEqual(2);
  });

  it("has ApiClient extend the last stage rather than a nested chain", () => {
    const ext = SRC.match(/export class ApiClient extends (\w+)/);
    expect(ext).not.toBeNull();
    // A bare identifier. If this becomes `withFoo(withBar(` again the ceiling is back.
    expect(ext![1]).toMatch(/^_ApiStage[A-Z]$/);
  });

  it("spreads the mixins across the stages instead of parking them all in one", () => {
    // A "staging" that puts 49 in stage A and 0 in stage B would satisfy the shape and none of the
    // benefit — the deep instantiation would be exactly where it was.
    const perStage = [...SRC.matchAll(/^class _ApiStage[A-Z] extends ([^\n]+)$/gm)]
      .map((m) => ((m[1] ?? "").match(/with[A-Za-z0-9]+/g) ?? []).length);
    expect(perStage.length).toBeGreaterThanOrEqual(2);
    for (const n of perStage) expect(n).toBeGreaterThan(5);
  });

  it("still produces a client with the whole surface on it", () => {
    // The structural assertions above would all hold over a chain missing a stage's methods.
    const api = new ApiClient("http://localhost:0") as unknown as Record<string, unknown>;
    for (const m of ["bsddSearch", "idsTemplates", "createShareToken", "modelStream"]) {
      expect(typeof api[m], m).toBe("function");
    }
  });
});
