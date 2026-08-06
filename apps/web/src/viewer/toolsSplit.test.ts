/**
 * R24-TOOLS-SPLIT — **the count out must equal the count in.**
 *
 * The `qa` tool section reached 1087 lines and 42 labelled controls under one heading with no
 * internal structure at all: zero sub-headings, one divider. Splitting it into Review ("is the model
 * right") and Analyse ("what does it tell you") is therefore *not* the re-parenting pass RAIL-SPLIT
 * was — there was nothing to re-parent, so the sub-group had to be created first, and a cut is
 * exactly the operation that can drop a control.
 *
 * A dropped control is invisible. It does not throw, it does not warn, and it looks identical to one
 * that was deliberately removed; the next person to notice is a user who needed it. So this asserts
 * the property directly, in **both** directions, against a frozen inventory taken from the section
 * before the cut:
 *
 *   - every one of the 42 pre-split controls still exists in one of the two sections (nothing lost);
 *   - each is in the section the split *intended* (nothing silently reshuffled);
 *   - and the two sections share none (nothing duplicated into both).
 *
 * The inventory is a **ratchet, not an allowlist**: a new tool added to either section passes. Only
 * losing or moving a listed one fails, which is the direction that costs a user something.
 *
 * The second half checks the routing, because a section that exists and is not reachable is the same
 * defect wearing better clothes — `panel-clash` was rebuilt on every persona change for a whole
 * release with no rail item pointing at it. Every destination this file names must be a panel the
 * distribution actually clears and the rail can actually open.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// Resolved from the workspace root (`apps/web`, which is `process.cwd()` under the workspace test
// command) rather than from `import.meta.url` — happy-dom gives that no `file:` scheme.
const read = (rel: string) => readFileSync(resolve(process.cwd(), rel), "utf8");
/**
 * R39-DECOMP-VIEWER: the section builders no longer all live in `app.ts`.
 *
 * This gate reads SOURCE, which makes it one of the few real parity checks `app.ts` has — and when
 * the `qa` builder moved to `tools/qaSection.ts` it went red immediately, correctly: measured from
 * app.ts alone, 42 controls had vanished. **The property it asserts did not change; the file list
 * did.** Extracted sections are listed here so the inventory is still checked in both directions.
 *
 * A future extraction that forgets to add its file fails loudly rather than silently shrinking the
 * population this reads — which is this file's own failure mode, one level up. That is asserted:
 * dropping an entry from this list turns the checks below red.
 */
const SECTION_SOURCES = [
  "src/viewer/app.ts",
  "src/viewer/tools/qaSection.ts",
  "src/viewer/tools/exportsSection.ts",
  "src/viewer/tools/analyseSection.ts",
  "src/viewer/tools/authoringSection.ts",
];
const APP = () => SECTION_SOURCES.map(read).join("\n");

/** The source text of one `section("<key>", …)` builder, up to the next section. */
function sectionBody(key: string): string {
  const parts = APP().split(/const b = section\("(\w+)"/);
  for (let i = 1; i < parts.length; i += 2) if (parts[i] === key) return parts[i + 1]!;
  return "";
}

/** Every string-literal control label built in a section (nested ones included — they move with
 *  their parent, so set-equality still holds over the whole tree). */
function labels(key: string): string[] {
  return [...sectionBody(key).matchAll(/toolBtn2\("([^"]+)"/g)].map((m) => m[1]!);
}

/**
 * The 42 controls the single `qa` section carried before the cut, each with the side of the seam it
 * belongs to. Measured from `app.ts` at v0.3.847, not estimated.
 *
 * `analyse` is the four ranges the premise-check named — 4D, code (IBC + IEBC), egress, cost — plus
 * the natural-language Ask, which is the one tool the `analyse` toolbox group already had and the
 * reason it was folded into Review in the first place.
 */
const INVENTORY: Record<string, "qa" | "analyse"> = {
  "⚡ Run clash (struct)": "qa",
  "Open Issues panel": "qa",
  "🔎 Model digest (what's in the model)": "qa",
  "🩺 Model Health (all checks, one score)": "qa",
  "📋 Normative validation (openBIM conformance)": "qa",
  "🔍 Data QA (required-property completeness)": "qa",
  "🔎 Query-select (filter language)": "qa",
  "★ Smart views (saved presets)": "qa",
  "🧹 Model cleanup (maintenance)": "qa",
  "⇄ Property round-trip (CSV/XLSX)": "qa",
  "✔ Rule check (rule library)": "qa",
  "⛶ Geometry check (clearance/egress)": "qa",
  "▢ Model CI (quality gate)": "qa",
  "🔗 Coordinate clashes (grouped issues)": "qa",
  "📊 Coordination KPIs": "qa",
  "📍 Field layout (points CSV / DXF)": "qa",
  "🕸 Related elements (model graph)": "qa",
  "🧬 Property layers (IFC5 overlays)": "qa",
  "🚫 Decision-readiness (RFI-prevention)": "qa",
  "🏗 Structural analytical model": "qa",
  "⬇ Write member loads (solver-ready IFC)": "qa",
  "⏚ Add base supports (pinned)": "qa",
  "📐 Apply loads + solve statics": "qa",
  "⬇ Export OpenSees (.tcl)": "qa",
  "⬇ Export Code_Aster (.mail)": "qa",
  "🌪 Lateral (wind + seismic base shear)": "qa",
  "✅ Approvability pre-flight (permit-readiness)": "qa",
  "◎ Isolate flagged elements in 3D": "qa",
  "🔧 Normalize properties (IDS-ready)": "qa",
  "🏛 Load takedown (preliminary)": "qa",
  "✅ Verified-as-built progress": "qa",
  "📐 Alignment check (storey + origin)": "qa",
  "＋ Add discipline IFC…": "qa",
  "✓ Validate (IDS)": "qa",
  // --- the cut ---
  "🏗 Site logistics (4D timeline)": "analyse",
  "⏱ 4D construction sequence (playback)": "analyse",
  "🏛 Occupancy & egress (IBC pre-check)": "analyse",
  "◎ Isolate narrow doors in 3D": "analyse",
  "🏛 Code analysis (G-series summary)": "analyse",
  "🏚 Existing-building code (IEBC scope)": "analyse",
  "💰 Cost estimate (labour · material · equipment)": "analyse",
};

describe("the qa/analyse split loses nothing", () => {
  it("the parsers found real data — a regex that matches nothing passes everything", () => {
    // Without this, a rename of `section(` or `toolBtn2(` turns every assertion below green while
    // measuring an empty string.
    expect(sectionBody("qa").length, "parsed no `qa` section body").toBeGreaterThan(10000);
    expect(sectionBody("analyse").length, "parsed no `analyse` section body").toBeGreaterThan(5000);
    expect(labels("qa").length, "parsed no controls in `qa`").toBeGreaterThan(20);
    expect(labels("analyse").length, "parsed no controls in `analyse`").toBeGreaterThan(4);
    expect(Object.keys(INVENTORY).length, "the frozen inventory is the yardstick").toBe(41);
  });

  it("EVERY pre-split control still exists — nothing was dropped in the cut", () => {
    const present = new Set([...labels("qa"), ...labels("analyse")]);
    const lost = Object.keys(INVENTORY).filter((l) => !present.has(l));
    expect(lost, "controls that went into the split and did not come out — a dropped control looks " +
      "exactly like a deliberately removed one").toEqual([]);
  });

  it("each control is on the side of the seam the split intended", () => {
    const qa = new Set(labels("qa"));
    const an = new Set(labels("analyse"));
    const wrong: string[] = [];
    for (const [label, want] of Object.entries(INVENTORY)) {
      const got = qa.has(label) ? (an.has(label) ? "both" : "qa") : an.has(label) ? "analyse" : "gone";
      if (got !== want) wrong.push(`${label}: expected ${want}, found ${got}`);
    }
    expect(wrong, "controls that changed sides — reshuffling is as invisible as dropping").toEqual([]);
  });

  it("no control is in BOTH sections — a copy is not a move", () => {
    const an = new Set(labels("analyse"));
    const both = labels("qa").filter((l) => an.has(l));
    expect([...new Set(both)], "duplicated controls: two buttons, one of them with dead handlers")
      .toEqual([]);
  });

  it("the natural-language Ask moved with the analyses it cites", () => {
    // The whole reason `GROUP_PANEL` folded Analyse into Review: Ask was the group's only tool and
    // the analyses it belongs beside were locked inside `qa`. It has to be on the Analyse side now,
    // or the fold was removed without the thing that justified removing it.
    expect(sectionBody("analyse")).toContain("api.rfiQa(");
    expect(sectionBody("qa")).not.toContain("api.rfiQa(");
  });

  it("Review keeps the checks — the split did not hollow it out", () => {
    // The twin of the assertion above: "Analyse has contents" passes just as happily if `qa` were
    // emptied wholesale, which would be a much worse outcome than not splitting at all.
    expect(labels("qa").length, "`qa` should keep the larger half").toBeGreaterThan(labels("analyse").length);
    for (const probe of ["api.runClash(", "api.modelHealth(", "api.rulesRun(", "api.dataQa("]) {
      expect(sectionBody("qa"), `\`qa\` lost ${probe}`).toContain(probe);
    }
  });
});

describe("the new section is reachable", () => {
  /** `analyse: "…"` style maps, parsed from a named object literal. */
  function mapEntries(src: string, marker: string): Record<string, string> {
    const block = src.split(marker)[1]?.split("};")[0] ?? "";
    const out: Record<string, string> = {};
    for (const m of block.matchAll(/^\s*(\w+):\s*"([\w-]+)"/gm)) out[m[1]!] = m[2]!;
    return out;
  }

  const home = () => mapEntries(APP(), "const HOME: Record<string, string> = {");
  const groupPanel = () => mapEntries(read("src/viewer/railToolbox.ts"), "export const GROUP_PANEL: Record<ToolGroup, string> = {");
  const distributed = () => new Set(
    [...(APP().split("const DISTRIBUTED_PANELS =")[1]?.split("];")[0] ?? "").matchAll(/"(\w+)"/g)].map((m) => m[1]!),
  );
  const panelIds = () => new Set(
    [...read("index.html").matchAll(/id="panel-(\w+)"[^>]*class="rpanel/g)].map((m) => m[1]!),
  );

  it("the parsers found real data", () => {
    expect(Object.keys(home()).length, "parsed no HOME entries").toBeGreaterThan(5);
    expect(Object.keys(groupPanel()).length, "parsed no GROUP_PANEL entries").toBeGreaterThan(3);
    expect(distributed().size, "parsed no DISTRIBUTED_PANELS").toBeGreaterThan(5);
    expect(panelIds().size, "parsed no .rpanel ids").toBeGreaterThan(8);
  });

  it("the `analyse` section is built at all", () => {
    // `builders` only runs the keys ALL_TOOLS names. A section defined and never invoked is dead
    // code that reads as a shipped feature.
    const all = APP().split("const ALL_TOOLS =")[1]?.split("];")[0] ?? "";
    expect([...all.matchAll(/"(\w+)"/g)].map((m) => m[1]), "ALL_TOOLS drives the builder loop")
      .toContain("analyse");
  });

  it("every persona lists `analyse` — an unlisted section renders folded under `more`", () => {
    const block = APP().split("const TOOLS_BY_PERSONA: Record<string, string[]> = {")[1]?.split("\n  };")[0] ?? "";
    const lists = [...block.matchAll(/(\w+):\s*\[([^\]]*)\]/g)];
    expect(lists.length, "parsed no persona tool lists").toBeGreaterThan(2);
    const without = lists.filter(([, , items]) => !/"analyse"/.test(items!)).map(([, p]) => p!);
    expect(without, "personas that would open the Analyse rail item onto a collapsed group").toEqual([]);
  });

  it("both tool-group destinations are panels the distribution owns AND the shell declares", () => {
    // The class of failure this catches is the one that orphaned `panel-clash`: a routing table can
    // name a destination that no panel exists for, and nothing anywhere errors.
    const dests = [...new Set([...Object.values(home()), ...Object.values(groupPanel())])];
    expect(dests, "sanity: the split's own destination").toContain("analyse");
    const undeclared = [...dests].filter((d) => !panelIds().has(d));
    expect(undeclared, "routing destinations with no .rpanel in index.html").toEqual([]);
    const uncleared = [...dests].filter((d) => !distributed().has(d));
    expect(uncleared, "destinations never cleared between rebuilds — each persona switch stacks a " +
      "second, identical-looking copy whose handlers are dead").toEqual([]);
  });

  it("Analyse is no longer folded into Review", () => {
    expect(groupPanel().analyse, "the toolbox `analyse` group must follow the section it belongs to")
      .toBe("analyse");
    expect(home().qa, "Review keeps the checks").toBe("review");
    expect(home().analyse, "Analyse gets its own panel").toBe("analyse");
  });
});
