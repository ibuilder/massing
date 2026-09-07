import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { definedVars, unreferencedVars, varRefs, voidVars } from "./cssVars";

/**
 * CSS-VAR-VOID. `apps/web/src/style.css` referenced `var(--border)` at six sites and TypeScript
 * referenced five void tokens at thirteen more, none with a fallback, none defined anywhere. A
 * `var()` that resolves to nothing makes the whole declaration invalid at computed-value time, so
 * the property falls back to *unset* — and what that costs depends on the property. Measured in
 * Chromium before the fix:
 *
 *   .att-drop         border 1.5px dashed  ->  border-style: none, width: 0px   (a FILE DROPZONE
 *                     whose only affordance is that outline; `.att-drop.over` computed the accent
 *                     colour and painted zero pixels of it, so drag-over feedback was dead too)
 *   .att-cell         border 1px solid     ->  none 0px
 *   .pf-addopt        border 1px dashed    ->  none 0px   (background:transparent — the outline IS
 *                                                          the button)
 *   qaSection rows    border-bottom        ->  none 0px   (x6, plus one in repairPanel)
 *   profile row       background            ->  rgba(0,0,0,0)
 *   "Sign out"        color: var(--danger)  ->  the body colour, not danger red
 *   Pareto baseline   stroke="var(--fg)"    ->  `none`, on a fill="none" rect — INVISIBLE
 *
 * **Six sites were NOT defects**, and saying so mattered: `color: var(--fg)` is an inherited
 * property, so it landed on the ancestor's colour, which is exactly `--text`, which is what it
 * wanted. The same token as an SVG `stroke` inherited `none` and erased a chart marker. *Same
 * token, opposite severity, decided by the property* — a rename sweep would have been right by
 * luck and wrong in its description.
 */
const WEB = process.cwd();
const REPO = join(WEB, "..", "..");

/** Every tracked web source that can define or reference a custom property. */
function sources(): { file: string; text: string }[] {
  // Derived from git, not listed. An earlier draft of this scan globbed `apps/web/src/**.css`,
  // which does NOT match `apps/web/src/style.css` (no intervening directory) — so the palette
  // itself was excluded and every token in it looked undefined. The population must come from the
  // index, and the count below must be asserted, or a glob can silently empty it again.
  const out = execFileSync("git", ["ls-files", "apps/web/**.css", "apps/web/**.html", "apps/web/**.ts"],
    { cwd: REPO, encoding: "utf8" }).trim().split("\n").filter(Boolean);
  return out.map((rel) => ({ file: rel, text: readFileSync(join(REPO, rel), "utf8") }));
}

describe("every var() names a custom property something defines", () => {
  const src = sources();

  it("scans a plausible number of files — a glob that matches nothing reports a clean tree", () => {
    expect(src.filter((s) => s.file.endsWith(".css")).length).toBeGreaterThanOrEqual(3);
    expect(src.filter((s) => s.file.endsWith(".ts")).length).toBeGreaterThan(400);
    // The palette itself must be in scope. This is the file the first draft silently dropped.
    expect(src.some((s) => s.file === "apps/web/src/style.css")).toBe(true);
  });

  it("finds the palette's tokens", () => {
    const d = definedVars(src);
    for (const t of ["--text", "--line", "--panel2", "--err", "--accent"]) expect(d.has(t)).toBe(true);
  });

  it("has no var() without a fallback pointing at a token nothing defines", () => {
    expect(voidVars(src)).toEqual([]);
  });

  it("keeps no token that nothing references — the other direction", () => {
    expect(unreferencedVars(src)).toEqual([]);
  });
});

describe("the reader", () => {
  const S = (text: string, file = "x.css") => [{ file, text }];

  it("treats a fallback as safe — `var(--x, #ccc)` renders the fallback", () => {
    expect(voidVars(S(`a { color: var(--nope, #ccc); }`))).toEqual([]);
    expect(varRefs(S(`a { color: var(--nope, #ccc); }`)).withFallback.has("--nope")).toBe(true);
  });

  it("reports a bare reference to an undefined token", () => {
    expect(voidVars(S(`a { color: var(--nope); }`)).map((u) => u.name)).toEqual(["--nope"]);
  });

  it("counts a definition in CSS as covering a reference from TypeScript", () => {
    // `--err` is declared in style.css and used only from accountUI.ts. A CSS-only scan would call
    // it dead; a TS-only scan would call it undefined. Both directions need both sources.
    const src = [
      { file: "a.css", text: `:root { --err: red; }` },
      { file: "b.ts", text: `el.style.color = "var(--err)";` },
    ];
    expect(voidVars(src)).toEqual([]);
    expect(unreferencedVars(src)).toEqual([]);
  });

  it("does NOT count a `--x:` inside a .ts string as a definition", () => {
    // Only a real CSS declaration or an explicit setProperty defines a token. Otherwise any
    // TypeScript that happens to build a style string would define away its own bugs.
    expect(voidVars([{ file: "b.ts", text: `el.style.cssText = "--made-up: red; color: var(--made-up)";` }])
      .map((u) => u.name)).toEqual(["--made-up"]);
  });

  it("accepts a token set at runtime through setProperty", () => {
    expect(voidVars([{ file: "b.ts", text: `el.style.setProperty("--rail-w", w); const s = "var(--rail-w)";` }]))
      .toEqual([]);
  });

  it("ignores commented-out CSS definitions, via the shared scanner", () => {
    expect(voidVars(S(`/* :root { --ghost: red; } */ a { color: var(--ghost); }`)).map((u) => u.name))
      .toEqual(["--ghost"]);
  });
});
