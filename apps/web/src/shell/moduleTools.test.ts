import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { ALL_DESTS } from "./destinations";

/**
 * R30-TOOLS — a register names the tool that operates on it, and the name resolves.
 *
 * **The defect this closes.** Every optional key a `module.json` could carry was presentation: icon,
 * list_columns, pinnable, ref_prefix, title_field, workspace. None of them said what the register
 * could *do*. So a register rendered as a table, a form and a status chip — which is precisely a
 * paper form — while the engine that made it a tool sat one unlinked screen away. `bid_leveling.py`
 * builds a scope-adjusted comparison out of `bid_submission` records; `schedule_cpm.py` runs a real
 * forward/backward pass over `schedule_activity`; `fca.py` computes an FCI from `fca_element`. The
 * depth was never missing. The *seam* was.
 *
 * `destinations.ts` already had half of it: `Dest.needs` lets a panel declare which register it
 * requires. Five of the destinations used it. Nothing let a register declare the reverse, so from
 * inside a register there was no route to its own tool.
 *
 * **What is tested is the drift, not the taste.** A `dest` is a string in a JSON file on the other
 * side of a language boundary from the catalog that defines it. A key that stops existing — renamed,
 * folded into another panel, deleted — leaves a button that points nowhere, and `goToDest` no-ops on
 * an unknown key, so the failure mode is a control that looks fine and does nothing. That is the same
 * shape as every silent-drift defect this repo has already paid for: a writer and a reader that
 * disagree about a key fail quietly, because a write to a slot nobody reads looks exactly like a
 * write that worked.
 *
 * The Python side (`module_schema.ToolRef`) validates the *shape* of a tool and deliberately does not
 * validate the key, because hard-coding a copy of the catalog in Python would make it the third table
 * encoding one fact. This test is where the two tables are made to agree — the same arrangement as
 * `roomNames.test.ts` reading `rooms.py`.
 */

const MODULES_DIR = resolve(__dirname, "../../../../services/api/modules");

interface ToolRef { dest: string; label: string; scope?: string }
interface Mod { key: string; name?: string; section?: string; tools?: ToolRef[] }

function modules(): Mod[] {
  return readdirSync(MODULES_DIR, { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => {
      try {
        return JSON.parse(readFileSync(resolve(MODULES_DIR, e.name, "module.json"), "utf8")) as Mod;
      } catch { return null; }
    })
    .filter((m): m is Mod => !!m?.key);
}

const MODS = modules();
const DEST_KEYS = new Set(ALL_DESTS.map((d) => d.key));

describe("R30-TOOLS — registers reach their tools", () => {
  it("reads the module set off disk, not a hand-kept list", () => {
    // Same reasoning as test_module_rooms: a gate that reads a copy of reality drifts from reality.
    expect(MODS.length).toBeGreaterThanOrEqual(130);
  });

  it("every declared tool points at a destination that exists", () => {
    const broken: string[] = [];
    for (const m of MODS) {
      for (const t of m.tools ?? []) {
        if (!DEST_KEYS.has(t.dest)) broken.push(`${m.key} → ${t.dest}`);
      }
    }
    expect(broken, "a tool whose dest is unknown renders a button that silently does nothing")
      .toEqual([]);
  });

  it("every tool carries a label and a known scope", () => {
    for (const m of MODS) {
      for (const t of m.tools ?? []) {
        expect(t.label?.trim(), `${m.key} → ${t.dest} has no label`).toBeTruthy();
        expect(["register", "record", undefined]).toContain(t.scope);
      }
    }
  });

  /**
   * No module declares a scope the UI cannot draw.
   *
   * `ToolRef` accepts `scope: "record"`, but only the register header reads `tools[]` today — the
   * record detail view does not. Two modules shipped with `scope: "record"` in the first pass and
   * their buttons therefore rendered **nowhere**: valid against the schema, resolving to a real
   * destination, passing every other assertion here, and invisible. That is the same failure as the
   * `/modules` allowlist dropping the key — a value that never arrives, with nothing failing when it
   * doesn't. So the schema keeps the field (the record view is coming) and this asserts nothing uses
   * it until something renders it. Delete this test in the same change that adds the renderer.
   */
  it("no module uses a scope that has no renderer yet", () => {
    const orphaned = MODS.flatMap((m) => (m.tools ?? [])
      .filter((t) => t.scope && t.scope !== "register")
      .map((t) => `${m.key} → ${t.dest} (scope=${t.scope})`));
    expect(orphaned, "record-scoped tools render nowhere — the record view does not read tools[]")
      .toEqual([]);
  });

  it("a register does not declare the same destination twice", () => {
    for (const m of MODS) {
      const dests = (m.tools ?? []).map((t) => t.dest);
      expect(new Set(dests).size, `${m.key} lists a dest more than once`).toBe(dests.length);
    }
  });

  /**
   * The inverse question, which is the one that actually found things: *what did we build that
   * nothing points at?* A panel with no register naming it is reachable only by someone who already
   * knows the rail — which is how a tool ends up shipped and unused.
   *
   * This is a REPORT, not yet a hard gate: many destinations legitimately operate on the model or on
   * the portfolio rather than on any register, so an empty list is not the target. It fails only if
   * the wiring goes *backwards* — if coverage drops below what has already been earned.
   */
  it("does not lose register→tool coverage that already exists", () => {
    const pointed = new Set<string>();
    for (const m of MODS) for (const t of m.tools ?? []) pointed.add(t.dest);
    const unpointed = ALL_DESTS.map((d) => d.key).filter((k) => !pointed.has(k)).sort();
    console.log(`R30-TOOLS: ${pointed.size}/${ALL_DESTS.length} destinations have a register that ` +
      `names them. Still unreferenced: ${unpointed.join(", ")}`);
    expect(pointed.size, "register→tool links were removed without replacing them")
      .toBeGreaterThanOrEqual(17);
  });
});
