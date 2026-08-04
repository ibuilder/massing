import { readFileSync, readdirSync } from "node:fs";
import { extname, join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * R24-MONO-DATA — two faces, and the split IS the signal.
 *
 * The audit asks for a sans for language and a **mono** for anything a machine produced: GlobalIds,
 * quantities, currency, dates, keys, statuses. Its claim is that this is the fastest available signal
 * for *"this is data, not prose"*, and unlike the rest of that visual system — the ink canvas, the
 * 24/192 brand grid — it costs nothing and commits to nothing. Which is why this ships and those
 * are still a decision.
 *
 * **The rule that needs enforcing is not "use mono", it is "decide the face once".** Before this
 * there were three hand-rolled `font-family: ui-monospace, monospace` declarations in `style.css`
 * and eleven more inline in TypeScript. Nobody disagreed about the stack; nobody owned it. That is
 * how a type system drifts — one component picks `Menlo` first, another omits `Consolas`, and on a
 * Windows machine two GlobalIds in the same panel render in different faces.
 *
 * So this is a **ratchet, like `innerHtmlGuard`**: a bounded, one-directional count. Converting a
 * literal to `var(--mono)` passes. Adding a new literal fails. The remaining allowance is named, so
 * "why is this not zero" has an answer in the file rather than in someone's memory.
 */

const SRC = resolve(__dirname, "..");

/**
 * The tree walk and the scan are memoised, and that is a correctness concern as much as a speed one.
 *
 * These read 100+ files. Called once per assertion they were the most expensive thing in the suite,
 * and on a loaded parallel run they pushed *sibling* tests past their timeouts — `library.test.ts`
 * at 5 s and `pdfVendor.test.ts` at 20 s both failed intermittently, with no assertion error, purely
 * from contention. A test that makes other tests flaky is a defect in this test, not in theirs.
 */
let _files: string[] | null = null;
let _hits: { file: string; line: number }[] | null = null;

/** Every first-party source file — the vendored engines are not ours to restyle. */
function walk(dir: string, out: string[] = []): string[] {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (e.name === "vendor" || e.name === "node_modules" || e.name === "demo") continue;
    const p = join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if ([".ts", ".css"].includes(extname(e.name)) && !e.name.endsWith(".test.ts")) out.push(p);
  }
  return out;
}

/**
 * Hard-coded mono stacks, excluding the one legitimate definition.
 *
 * `style.css` must contain exactly one — the `--mono` token itself — plus the comment that explains
 * it. Everything else is a literal that should be reading the token.
 */
function sourceFiles(): string[] {
  return (_files ??= walk(SRC));
}

function hardCodedMono(): { file: string; line: number }[] {
  if (_hits) return _hits;
  const hits: { file: string; line: number }[] = [];
  for (const f of sourceFiles()) {
    const rel = f.slice(SRC.length + 1).replace(/\\/g, "/");
    readFileSync(f, "utf8").split("\n").forEach((line, i) => {
      if (!/ui-monospace/.test(line)) return;
      // The token definition and its docs are the point, not a violation.
      if (rel === "style.css" && /--mono:|^\s*\*/.test(line)) return;
      hits.push({ file: rel, line: i + 1 });
    });
  }
  return (_hits = hits);
}

/**
 * Remaining hand-rolled stacks, and why each survives.
 *
 * The survivor is `pasteRows`, and its history is the point. It was left because `portal/portal.ts`
 * was held by another session's in-flight work when this landed — converting it would have meant
 * editing a file two people had open. That was not bad luck: `R24-MONO-DATA` is a Lane B item and
 * `portal.ts` was a Lane A file, so the collision was structural and permanent. v0.3.850 moved the
 * register renderer to `portal/register/register.ts`, which Lane B owns, and this line went with it.
 * It is now a one-line change inside the lane that wants it — and this number going UP is a build
 * failure either way.
 */
const ALLOWANCE = 1;

describe("the mono face is decided once", () => {
  it("style.css defines the token", () => {
    const css = readFileSync(join(SRC, "style.css"), "utf8");
    expect(css).toMatch(/--mono:\s*ui-monospace/);
    expect(css).toMatch(/\.mono\s*\{[^}]*var\(--mono\)/);
  });

  it("no more hand-rolled mono stacks than the named allowance", () => {
    const hits = hardCodedMono();
    expect(hits.length, hits.length > ALLOWANCE
      ? `Hand-rolled mono stacks rose to ${hits.length} (allowance ${ALLOWANCE}):\n`
        + hits.map((h) => `  ${h.file}:${h.line}`).join("\n")
        + "\n\nUse `var(--mono)` — or the `.mono` / `.mono-num` class — rather than repeating the "
        + "font stack. The face is defined once in style.css so two GlobalIds in one panel cannot "
        + "render in different faces."
      : "").toBeLessThanOrEqual(ALLOWANCE);
  });

  it("the ratchet can actually fail — the allowance is not above the real count", () => {
    // A ratchet parked well above reality never fires and reads as protection. This asserts the
    // headroom is zero: the next literal added is the one that breaks the build.
    expect(hardCodedMono().length).toBe(ALLOWANCE);
  });
});

describe("the scanner can see what it claims to", () => {
  it("reads a plausible number of first-party files", () => {
    // Guards the walker: a broken path returns [] and makes every assertion above vacuously pass —
    // the failure mode that let a 'clean' CodeQL query and an empty `gh run list` both read as good news.
    const files = sourceFiles();
    expect(files.length).toBeGreaterThan(100);
    expect(files.some((f) => f.endsWith("style.css"))).toBe(true);
  });

  it("does not police the vendored engines", () => {
    expect(sourceFiles().some((f) => f.replace(/\\/g, "/").includes("/vendor/"))).toBe(false);
  });
});
