/**
 * RAIL-KEYS — **every name for a rail item must resolve, and every panel must be reachable.**
 *
 * RAIL-SPLIT turned one rail item, `tools`, into seven. The item list was updated. Four other places
 * that named `tools` were not, and none of them could fail loudly:
 *
 *   - the per-persona rail allowlists hid any key they did not list, so **every persona except
 *     `all` lost all seven new items** — precisely the panels the tool groups had just moved into.
 *     `all` is the persona with no allowlist, which is why manual testing never saw it;
 *   - the start-a-model-from-scratch flow guarded on `RAIL_ITEMS.some(r => r.key === "tools")`,
 *     which became permanently false, so it silently opened nothing;
 *   - a portal card clicked `.rail-btn[data-rail="tools"]`, which matched nothing — a dead button;
 *   - and `panel-clash` kept being rebuilt on every persona change with **no rail item pointing at
 *     it**, so a whole coordination surface was unreachable while looking healthy in the code.
 *
 * Every one of these is the same defect: a rail key is a shared identifier, but it was only ever
 * *defined* in one place and *spelled* in five. Renaming the definition could not break the spellings
 * because nothing related them. String keys have no referential integrity unless something asserts
 * it, so this asserts it.
 *
 * The reverse direction matters just as much and is the one that caught the clash orphan: a panel
 * nothing can open is invisible in exactly the way a missing feature is not — the code that builds
 * it still runs, still passes review, and still costs time on every rebuild.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (rel: string) => readFileSync(resolve(HERE, rel), "utf8");

/** The keys RAIL_ITEMS actually defines. */
function railKeys(): Set<string> {
  const src = read("../main.ts");
  const block = src.split("const RAIL_ITEMS")[1]?.split("\n];")[0] ?? "";
  return new Set([...block.matchAll(/key:\s*"(\w+)"/g)].map((m) => m[1]!));
}

/** Keys named by the per-persona allowlists, resolving the shared `SPLIT_RAIL` constant. */
function personaKeys(): Set<string> {
  const src = read("../main.ts");
  const split = new Set(
    [...(src.split("const SPLIT_RAIL =")[1]?.split("];")[0] ?? "").matchAll(/"(\w+)"/g)].map((m) => m[1]!),
  );
  const block = src.split("const PERSONAS: Record<string, PersonaCfg> = {")[1]?.split("\n};")[0] ?? "";
  const out = new Set<string>();
  for (const m of block.matchAll(/rail:\s*\[([^\]]*)\]/g)) {
    for (const k of m[1]!.matchAll(/"(\w+)"/g)) out.add(k[1]!);
    if (/\.\.\.SPLIT_RAIL/.test(m[1]!)) for (const k of split) out.add(k);
  }
  return out;
}

/** Every `data-rail="…"` selector written in the web source. */
function selectorKeys(): string[] {
  const out: string[] = [];
  for (const f of ["../main.ts", "../portal/portal.ts", "../viewer/app.ts"]) {
    for (const m of read(f).matchAll(/data-rail=\\?"(\w+)\\?"/g)) out.push(m[1]!);
  }
  return out;
}

/** Every `showRail("…")` call. */
function showRailKeys(): string[] {
  return [...read("../main.ts").matchAll(/showRail\(\s*"(\w+)"/g)].map((m) => m[1]!);
}

describe("every name for a rail item resolves", () => {
  it("the parsers found real data — a regex that matches nothing passes everything", () => {
    expect(railKeys().size, "parsed no RAIL_ITEMS").toBeGreaterThan(10);
    expect(personaKeys().size, "parsed no persona rail allowlists").toBeGreaterThan(5);
    expect(selectorKeys().length, "parsed no data-rail selectors").toBeGreaterThan(0);
  });

  it("persona allowlists name only real rail items", () => {
    const keys = railKeys();
    const unknown = [...personaKeys()].filter((k) => !keys.has(k));
    expect(unknown, "personas hide the rail by allowlist — an unknown key silently hides nothing " +
      "while a MISSING key silently hides a real item").toEqual([]);
  });

  it("every rail item a persona could show is actually reachable for that persona", () => {
    // The half that bit: `tools` was listed, so the allowlist looked maintained, while the seven
    // items that replaced it were absent and therefore hidden for every persona but `all`.
    const keys = railKeys();
    const listed = personaKeys();
    const neverListed = [...keys].filter((k) => !listed.has(k));
    expect(neverListed, "rail items no persona lists — hidden for everyone except `all`").toEqual([]);
  });

  it("no `data-rail` selector points at a key that does not exist", () => {
    const keys = railKeys();
    const dead = [...new Set(selectorKeys())].filter((k) => !keys.has(k));
    expect(dead, "selectors matching nothing — the buttons that use them do nothing").toEqual([]);
  });

  it("no showRail() call names a key that does not exist", () => {
    const keys = railKeys();
    const dead = showRailKeys().filter((k) => !keys.has(k));
    expect(dead, "showRail() targets that cannot open").toEqual([]);
  });
});

describe("every rail panel is reachable", () => {
  /** Panel ids declared in the shell. */
  function panelIds(): string[] {
    const html = read("../../index.html");
    return [...html.matchAll(/id="panel-(\w+)"[^>]*class="rpanel/g)].map((m) => m[1]!);
  }

  it("the parser found the shell's panels", () => {
    expect(panelIds().length, "parsed no .rpanel ids from index.html").toBeGreaterThan(8);
  });

  it("every rail item has a panel OR a launch handler", () => {
    const src = read("../main.ts");
    const block = src.split("const RAIL_ITEMS")[1]?.split("\n];")[0] ?? "";
    const panels = new Set(panelIds());
    const missing: string[] = [];
    for (const rec of block.split(/(?=\{\s*key:)/)) {
      const k = /key:\s*"(\w+)"/.exec(rec)?.[1];
      if (!k) continue;
      // `launch:` items hand off to another workspace and own no panel here, by design.
      if (!panels.has(k) && !/launch:/.test(rec)) missing.push(k);
    }
    expect(missing, "rail items with neither a panel nor a launch handler").toEqual([]);
  });

  it("NO PANEL IS ORPHANED — every .rpanel can be opened from the rail", () => {
    // The direction that caught `panel-clash`: its builder ran on every persona change, but
    // RAIL-SPLIT removed the only item that opened it. A surface nothing can reach does not error,
    // does not warn, and still costs the rebuild — it is simply gone, quietly.
    const keys = railKeys();
    const orphans = panelIds().filter((id) => !keys.has(id));
    expect(orphans, "panels built but unreachable from the rail").toEqual([]);
  });
});
