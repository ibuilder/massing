/**
 * COL-PAIR — the pair rule, and the two ways it can go quietly wrong.
 *
 * The first is DRIFT: the suffix list exists twice, here and in
 * `services/api/test_module_fields.py`, and a pair the two disagree about is simply not detected —
 * no error, the column just goes back to showing one era. So the list is read out of the Python file
 * and compared, rather than trusted.
 *
 * The second is POPULATION: this rule earns its place only if registers really do list one half of a
 * pair. That is asserted against the shipped manifests, not against a number written down here, and
 * the assertion is a FLOOR on how many such columns the rule now covers — so deleting the rule's
 * reason to exist fails the build rather than passing it silently.
 */
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { type PairField, REF_SUFFIXES, pairedValue, referenceHalf, textHalf } from "./fieldPairs";

// happy-dom gives `import.meta.url` no `file:` scheme, so resolve from cwd (which is `apps/web`)
const REPO = join(process.cwd(), "..", "..");
const PY_GATE = join(REPO, "services", "api", "test_module_fields.py");

const by = (fields: PairField[]) => new Map(fields.map((f) => [f.name, f]));

interface Manifest { key: string; fields: PairField[]; list_columns?: string[] }

function manifests(): Manifest[] {
  const out = execFileSync("git", ["ls-files", "services/api/modules/*/module.json"],
    { cwd: REPO, encoding: "utf8" }).trim().split("\n").filter(Boolean);
  return out.map((rel) => {
    const j = JSON.parse(readFileSync(join(REPO, rel), "utf8")) as Manifest;
    const parts = rel.split("/");
    return { ...j, key: parts[parts.length - 2] ?? rel };
  });
}

describe("the suffix list does not drift from the Python rule", () => {
  it("names exactly the suffixes services/api/test_module_fields.py names", () => {
    const py = readFileSync(PY_GATE, "utf8");
    const m = /^REF_SUFFIXES = \(([^)]*)\)/m.exec(py);
    if (!m) throw new Error("REF_SUFFIXES not found in test_module_fields.py — did it get renamed?");
    const pySuffixes = [...(m[1] ?? "").matchAll(/"([^"]+)"/g)].map((x) => x[1] ?? "");
    // sorted: the ORDER is not the contract, the SET is. Order matters only within `textHalf`, where
    // a name ending in two of them takes the first — and no shipped field does.
    expect([...pySuffixes].sort()).toEqual([...REF_SUFFIXES].sort());
    expect(pySuffixes.length).toBeGreaterThan(4);   // a regex that matched nothing would "agree" too
  });
});

describe("textHalf / referenceHalf", () => {
  const fields: PairField[] = [
    { name: "supplier", type: "text" },
    { name: "supplier_company", type: "reference", module: "company" },
    { name: "assignee_name", type: "text" },
    { name: "assignee_contact", type: "reference", module: "contact" },
    { name: "notes", type: "textarea" },
    { name: "lonely_company", type: "reference", module: "company" },
  ];
  const map = by(fields);

  it("finds the plain stem", () => expect(textHalf("supplier_company", map)).toBe("supplier"));
  it("finds the _name stem", () => expect(textHalf("assignee_contact", map)).toBe("assignee_name"));
  it("returns null for a reference with no text beside it",
    () => expect(textHalf("lonely_company", map)).toBeNull());
  it("returns null when asked about a text field", () => expect(textHalf("supplier", map)).toBeNull());

  it("inverts", () => {
    expect(referenceHalf("supplier", map)).toBe("supplier_company");
    expect(referenceHalf("assignee_name", map)).toBe("assignee_contact");
  });
  it("does not invent a pair for an unclaimed text field",
    () => expect(referenceHalf("notes", map)).toBeNull());

  // `referenceHalf` asks the references rather than string-building `name + "_company"`. This is the
  // case that would break if it ever did: the stems differ, so the built name would be
  // `assignee_name_contact`, which no module declares.
  it("pairs assignee_name without building a candidate name from it", () => {
    const built = new Map(map);
    expect(built.has("assignee_name_contact")).toBe(false);
    expect(referenceHalf("assignee_name", map)).toBe("assignee_contact");
  });
});

describe("pairedValue picks the half that has something to say", () => {
  const fields: PairField[] = [
    { name: "supplier", type: "text" },
    { name: "supplier_company", type: "reference", module: "company" },
    { name: "qty", type: "number" },
  ];
  const map = by(fields);
  const rec = (d: Record<string, unknown>) => (n: string) => d[n];

  it("a text column shows the linked record when the record filled the link", () => {
    const pv = pairedValue(map.get("supplier")!, map, rec({ supplier_company: "uuid-1" }));
    expect(pv.field.name).toBe("supplier_company");
    expect(pv.as).toBe("reference");
  });

  it("a reference column shows the typed name when the record filled the text", () => {
    const pv = pairedValue(map.get("supplier_company")!, map, rec({ supplier: "Acme Electrical" }));
    expect(pv.field.name).toBe("supplier");
    expect(pv.as).toBe("text");
  });

  it("the column's OWN value wins when both halves are filled", () => {
    const pv = pairedValue(map.get("supplier")!, map,
      rec({ supplier: "Acme Electrical", supplier_company: "uuid-1" }));
    expect(pv.field.name).toBe("supplier");
  });

  it("an empty string counts as unfilled, not as a value", () => {
    const pv = pairedValue(map.get("supplier")!, map, rec({ supplier: "", supplier_company: "uuid-1" }));
    expect(pv.field.name).toBe("supplier_company");
  });

  it("falls back to the column itself when neither half is filled", () => {
    expect(pairedValue(map.get("supplier")!, map, rec({})).field.name).toBe("supplier");
  });

  it("leaves a field that is not half of a pair exactly where it was", () => {
    const pv = pairedValue(map.get("qty")!, map, rec({ supplier: "Acme" }));
    expect(pv.field.name).toBe("qty");
    expect(pv.as).toBe("text");
  });
});

/**
 * A source assertion, for the reason `tableRefColumn.test.ts` gives: the failure mode here is not
 * "the cell renders wrong", it is "the renderer stopped calling this rule", and a DOM test proves
 * the branch it exercises and nothing about a branch nobody kept. Everything above proves the rule
 * is correct; a correct rule nothing calls is the shape of defect this whole session kept finding.
 */
describe("the register renderer actually uses the rule", () => {
  const REGISTER = join(process.cwd(), "src", "portal", "register", "register.ts");
  const src = readFileSync(REGISTER, "utf8");

  it("dispatches read-only cells through pairedValue", () => {
    expect(src).toContain("pairedValue(");
    expect(src).toMatch(/import .*pairedValue.* from "\.\/fieldPairs"/);
  });

  it("resolves the reference twins of TEXT columns, not just reference columns", () => {
    // Without this the pair-aware cell finds the twin, renders it through `refCell`, and `refCell`
    // — correctly, having no map — reports every linked record as unresolvable. The rule would look
    // wired and make the 19 registers WORSE than the blank they had.
    expect(src).toContain("referenceHalf(");
    const build = src.slice(src.indexOf("const refCols"), src.indexOf("const refMaps"));
    expect(build).toContain("referenceHalf(");
  });

  it("leaves the editing path alone", () => {
    // A cell that edits a different field than its header names is worse than a blank one, so the
    // fallback is read-only by construction. If `pairedValue` ever appears inside an `editing`
    // branch this must be reconsidered deliberately, not discovered in production.
    const cellLoop = src.slice(src.indexOf("for (const c of cols) {"), src.indexOf("tr.appendChild(this.assigneeCell"));
    const pairIdx = cellLoop.indexOf("pairedValue(");
    const lastEditing = cellLoop.lastIndexOf("editing &&");
    expect(pairIdx).toBeGreaterThan(lastEditing);
  });
});

describe("the shipped registers that this rule is for", () => {
  const mods = manifests();

  it("reads every module manifest", () => {
    expect(mods.length).toBeGreaterThan(130);
    expect(mods.find((m) => m.key === "delivery")).toBeTruthy();
  });

  it("covers the registers whose column is one half of a pair", () => {
    const halfPaired: string[] = [];
    for (const m of mods) {
      const map = by(m.fields ?? []);
      for (const col of m.list_columns ?? []) {
        const f = map.get(col);
        if (!f) continue;
        const twin = f.type === "reference" ? textHalf(col, map) : referenceHalf(col, map);
        if (twin && !(m.list_columns ?? []).includes(twin)) halfPaired.push(`${m.key}.${col}`);
      }
    }
    // A FLOOR, measured at 20 (19 text-half columns + subcontract's reference-half one) the day this
    // shipped. Adding a register never has to touch this file; removing the rule's reason to exist
    // fails it.
    expect(halfPaired.length).toBeGreaterThanOrEqual(20);
    // The four PARTY-REFS registers whose text column would have gone blank for every linked record.
    for (const name of ["delivery.supplier", "asset_register.manufacturer", "assumption.owner",
      "project_charter.project_manager"]) {
      expect(halfPaired, `${name} is what this rule was written for`).toContain(name);
    }
    // And the one that fails the other way: subcontract lists the reference, so a legacy typed name
    // was the era going blank there.
    expect(halfPaired).toContain("subcontract.vendor_company");
  });

  it("every pair it detects points at a module that exists", () => {
    const keys = new Set(mods.map((m) => m.key));
    for (const m of mods) {
      const map = by(m.fields ?? []);
      for (const f of m.fields ?? []) {
        if (f.type !== "reference" || !textHalf(f.name, map)) continue;
        expect(keys, `${m.key}.${f.name} -> ${f.module}`).toContain(f.module);
      }
    }
  });
});
