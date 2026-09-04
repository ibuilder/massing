/**
 * Mixins that call `editIfc` must be composed OUTSIDE `withAuthoring`.
 *
 * WHY THIS EXISTS
 *     `editIfc` is declared on the `Authoring` mixin, not on `HttpCore`. A mixin typed
 *     `Ctor<HttpCore>` therefore cannot see it: the extraction does not compile, and nothing says
 *     why. SCALE-SEAM (92) diagnosed that as the likely reason 24 edit recipes sat in `client.ts`
 *     through eleven slices, and (93) and (94) then found two more slices — ⑲ and ㊻ — that had each
 *     left work behind for it. Three mixins now declare `NeedsEditIfc` as their base requirement.
 *
 *     That requirement was, until this file, enforced only as a side effect of `tsc` succeeding on
 *     the real chain in `client.ts`. Nothing stated it, and nothing would say WHICH constraint broke
 *     if someone reordered the chain — only that a very long expression stopped compiling.
 *
 *     The review of #411 is what forced this. I reported the constraint as "mutation-checked", but
 *     the check was a scratch file I deleted, so the reviewer could not verify it and neither could
 *     anyone after me. **A verification that leaves no artifact is a claim, not a check.**
 *
 *     Worse, the first version of that scratch check was WORTHLESS: it rebalanced parentheses
 *     wrongly and went red with `TS1005` syntax errors, proving nothing about composition order
 *     while looking exactly like a passing mutation test. Reading its output is the only reason I
 *     knew. **A check that goes red for a reason other than the one claimed is the same defect as
 *     one that goes green for it** — and this repo's history is mostly the second kind.
 *
 * HOW IT WORKS
 *     `@ts-expect-error` fails the typecheck if the error does NOT occur. So each line below is an
 *     assertion that applying the mixin to bare `HttpCore` is a type error — the constraint stated
 *     positively, checked by `npm run typecheck`, and named per mixin when it breaks.
 */
import { describe, expect, it } from "vitest";
import { HttpCore } from "./httpCore";
import { withAnnotate } from "./annotate";
import { withMep } from "./mep";
import { withModel } from "./model";

describe("mixins requiring editIfc", () => {
  it("reject a base that lacks it, so a bad chain order fails at compile time", () => {
    // @ts-expect-error withAnnotate needs NeedsEditIfc; bare HttpCore has no editIfc.
    void (() => withAnnotate(HttpCore));
    // @ts-expect-error withMep needs NeedsEditIfc; bare HttpCore has no editIfc.
    void (() => withMep(HttpCore));
    // @ts-expect-error withModel needs NeedsEditIfc; bare HttpCore has no editIfc.
    void (() => withModel(HttpCore));
    expect(true).toBe(true);
  });
});
