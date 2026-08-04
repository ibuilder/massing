import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { EDITABLE_FIELD_TYPES, NUMERIC_FIELD_TYPES, READ_ONLY_FIELD_TYPES } from "./register/register";

/**
 * MOD-PERCENT — every field type a shipped module declares is one the form layer can actually render.
 *
 * **The defect this exists for.** `percent` was a legal field type and the form layer did not know it.
 * Three separate places asked `f.type === "number" || f.type === "currency"`, and `percent` was in
 * none of them, so a percent field was not inline-editable, rendered as `<input type="text">` with no
 * numeric keypad or validation, and — quietest of the three — saved as the STRING `"5"`, because the
 * `Number(v)` coercion was behind the same ternary. `validate_record` calls `float(value)`, so it
 * passed; every consumer coerces, so nothing failed. The column simply accumulated a mixture of `5`
 * and `"5"` depending on which form last touched the record.
 *
 * It survived because it was invisible from both directions. The backend gate reads config *shape* and
 * says nothing about whether a UI can render it; the web suite never built a form containing a percent
 * field. Two green suites, one type nothing handled.
 *
 * **Why this is a coverage test and not a DOM test.** Rendering a form and asserting one input is
 * `type="number"` would prove `percent` works and nothing about the next type. What actually failed
 * here was *completeness* — a hand-maintained list of types, with no check that it covered the types
 * in use. So this asserts the partition instead: every type the 133 shipped modules declare is either
 * editable or deliberately read-only, and every type whose NAME says it holds a magnitude is treated
 * as numeric. Add a field type tomorrow and forget the form layer, and this fails then, not after it
 * has quietly mangled a column.
 */

const MODULES_DIR = resolve(__dirname, "../../../../services/api/modules");
const SCHEMA_PY = resolve(__dirname, "../../../../services/api/src/aec_api/module_schema.py");

/** Every field type actually used by a shipped module, with an example so a failure names one. */
function typesInUse(): Map<string, string> {
  const seen = new Map<string, string>();
  for (const e of readdirSync(MODULES_DIR, { withFileTypes: true })) {
    if (!e.isDirectory()) continue;
    let mod: { key?: string; fields?: { name: string; type: string }[] };
    try {
      mod = JSON.parse(readFileSync(resolve(MODULES_DIR, e.name, "module.json"), "utf8"));
    } catch { continue; }
    for (const f of mod.fields ?? []) {
      if (!seen.has(f.type)) seen.set(f.type, `${mod.key}.${f.name}`);
    }
  }
  return seen;
}

/** `FIELD_TYPES = {...}` from module_schema.py — the server's own list of legal types. */
function declaredTypes(): string[] {
  const src = readFileSync(SCHEMA_PY, "utf8");
  const block = src.slice(src.indexOf("FIELD_TYPES = {"), src.indexOf("}", src.indexOf("FIELD_TYPES = {")));
  const out = [...block.matchAll(/"([a-z]+)"/g)].map((m) => m[1]!);
  expect(out.length, "could not parse FIELD_TYPES — module_schema.py was restructured").toBeGreaterThan(8);
  return out;
}

const IN_USE = typesInUse();
const HANDLED = new Set<string>([...EDITABLE_FIELD_TYPES, ...READ_ONLY_FIELD_TYPES]);

describe("MOD-PERCENT — the form layer handles every field type in use", () => {
  it("reads the real modules, not a fixture", () => {
    expect(IN_USE.size).toBeGreaterThan(8);
  });

  it("every type a shipped module declares is either editable or deliberately read-only", () => {
    const unhandled = [...IN_USE.entries()]
      .filter(([t]) => !HANDLED.has(t))
      .map(([t, eg]) => `${t} (e.g. ${eg})`);
    expect(unhandled, "a type in neither list is one the form cannot render, and nothing will say so")
      .toEqual([]);
  });

  it("no type is in both lists", () => {
    // Overlap would mean the intent is ambiguous and the behaviour depends on which check runs first.
    const both = [...EDITABLE_FIELD_TYPES].filter((t) => (READ_ONLY_FIELD_TYPES as readonly string[]).includes(t));
    expect(both).toEqual([]);
  });

  it("every magnitude-holding type is treated as numeric", () => {
    // The specific regression: `percent` holds a magnitude and was not in the numeric set, so it
    // rendered as text and saved as a string. Asserted by MEANING rather than by listing the three,
    // so a future "decimal" or "quantity" type is caught by the same rule.
    const magnitude = declaredTypes().filter((t) => ["number", "currency", "percent"].includes(t));
    for (const t of magnitude) {
      expect(NUMERIC_FIELD_TYPES as readonly string[],
        `${t} holds a magnitude but the form does not treat it as numeric — it will render as text `
        + "and save as a string").toContain(t);
    }
  });

  it("the server's legal types and the form's handled types have not drifted apart", () => {
    // A type the server accepts but the form cannot render is a module author's trap: the config
    // validates, the build passes, and the field is broken only when somebody opens the form.
    const unrenderable = declaredTypes().filter((t) => !HANDLED.has(t));
    expect(unrenderable, "module_schema.FIELD_TYPES accepts these but the form handles none of them")
      .toEqual([]);
  });

  it("percent specifically is editable, numeric, and in use", () => {
    // The concrete case, kept alongside the general rules: general rules can be satisfied by weakening
    // them, and this one names the field type that actually broke.
    expect(IN_USE.has("percent"), "no module uses `percent` — the sweep converted 21 fields").toBe(true);
    expect(EDITABLE_FIELD_TYPES as readonly string[]).toContain("percent");
    expect(NUMERIC_FIELD_TYPES as readonly string[]).toContain("percent");
  });
});
