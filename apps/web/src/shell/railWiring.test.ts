/**
 * RAIL-WIRING — every button the left rail renders must actually go somewhere.
 *
 * The rail builds a button for each entry in the destination catalog, and clicking it looks the key
 * up in the portal's `destDispatch()` map. Those are two lists maintained in two files, so a
 * destination added to the catalog without a handler renders a button that **does nothing when
 * clicked** — no error, no console message, no visual difference from a working one. That is the
 * worst failure shape in a navigation surface: it is invisible until a user tries it, and it looks
 * like the app is broken rather than like a missing line.
 *
 * The two legitimate exceptions are `goto` destinations, which hand off to another workspace instead
 * of rendering a panel here and therefore have no local handler by design.
 *
 * **This test exists because a hand-audit produced a FALSE POSITIVE.** The first pass matched each
 * catalog record with `key:\s*"(__\w+__)",[^}]*goto:` — and `[^}]*` stops at the `}` inside an emoji
 * escape like `\u{1F4D0}`, so `__drawings__` (which *does* carry a goto) was reported as a dead
 * button. Parse each record by SPLITTING on the record boundary rather than by a character class
 * that a unicode escape can terminate early. An alarming result should raise the bar on the
 * instrument, not lower it.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (rel: string) => readFileSync(resolve(HERE, rel), "utf8");

/** Catalog destination keys, and the subset that hands off via `goto`. */
function catalog(): { keys: Set<string>; goto: Set<string> } {
  const src = read("./destinations.ts");
  const keys = new Set([...src.matchAll(/key:\s*"(__\w+__)"/g)].map((m) => m[1]!));
  // Split on the record boundary — see the header note about `\u{...}` breaking a `[^}]*` scan.
  const goto = new Set<string>();
  for (const rec of src.split(/(?=\{\s*key:\s*"__)/)) {
    const k = /key:\s*"(__\w+__)"/.exec(rec)?.[1];
    if (k && /goto:\s*"/.test(rec.split("},")[0] ?? "")) goto.add(k);
  }
  return { keys, goto };
}

/** Keys the portal can actually dispatch. */
function dispatchable(): Set<string> {
  const src = read("../portal/portal.ts");
  const block = src.split("destDispatch(): Record<string, () => unknown> {")[1]?.split("\n  }")[0] ?? "";
  return new Set([...block.matchAll(/(__\w+__):/g)].map((m) => m[1]!));
}

describe("every rail button goes somewhere", () => {
  it("the parsers found real data — a regex that matches nothing passes everything", () => {
    // The vacuous-pass guard. Without it, a refactor that changes either file's shape turns this
    // whole suite green while checking nothing.
    expect(catalog().keys.size, "parsed no destinations from destinations.ts").toBeGreaterThan(30);
    expect(dispatchable().size, "parsed no handlers from portal.ts destDispatch()").toBeGreaterThan(30);
    expect(catalog().goto.size, "parsed no goto destinations — the \\u{...} trap is back")
      .toBeGreaterThan(0);
  });

  it("no destination renders a button with no handler", () => {
    const { keys, goto } = catalog();
    const dead = [...keys].filter((k) => !dispatchable().has(k) && !goto.has(k)).sort();
    expect(dead, "rail buttons that render but do nothing when clicked").toEqual([]);
  });

  it("no handler exists for a destination the rail never renders", () => {
    // The other direction: dead code that looks like a working feature in the dispatch map.
    const { keys } = catalog();
    const orphan = [...dispatchable()].filter((k) => !keys.has(k)).sort();
    expect(orphan, "dispatch handlers for destinations no rail button reaches").toEqual([]);
  });

  it("a goto destination is a DELIBERATE hand-off, not an accident", () => {
    // Both known hand-offs leave the portal for another workspace. If a third appears, it should be
    // because someone decided that — `spine.test.ts` separately forbids a goto being a room's home.
    expect([...catalog().goto].sort()).toEqual(["__drawings__", "__uw__"]);
  });
});
