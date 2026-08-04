import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * MOD-TABLEREF — a `reference` column inside a `table` field.
 *
 * **This type was excluded on purpose, and the exclusion note said why:** *"a picker per row is a real
 * feature and shipping it half-done would put unresolvable ids in rows, which is the exact defect
 * `refCell` was written to stop."* Admitting it meant meeting that condition, not deleting the
 * sentence — so this file asserts the condition, not the feature.
 *
 * **Inside a `<select>`, an unresolvable id is worse than a bad label — it is silent data loss.** A
 * stored value that matches no `<option>` leaves the control showing the blank option. Nothing errors,
 * nothing is marked, and the next save writes that blank over a link somebody deliberately made. The
 * row comes back empty and the only evidence is gone. A fake link at least still contains the id.
 *
 * Two situations produce a stored value with no matching option, and both are ordinary:
 *   1. the target record was deleted, or lies past `REF_RESOLVE_LIMIT` in a large register;
 *   2. the column used to be free text — `bid_package.spec_sections` held prose until this change —
 *      so live rows contain a section number somebody typed, not an id.
 *
 * **Why a source assertion rather than a DOM test.** The failure is not "the picker renders wrong",
 * it is "a branch is missing", and a DOM test proves the branch it exercises and nothing about the
 * one nobody wrote. The same reasoning as `fieldTypeCoverage.test.ts`: assert the property that has
 * to hold, in the place it has to hold.
 */

// The register renderer, which is where `tableEditor` and `refCell` live. It was inside
// `portal.ts` until v0.3.850 — see `register/register.ts` for why it moved.
const PORTAL = resolve(__dirname, "register", "register.ts");
const MODULES_DIR = resolve(__dirname, "../../../../services/api/modules");

function referenceColumns(): { module: string; field: string; column: string; target: string }[] {
  const out: { module: string; field: string; column: string; target: string }[] = [];
  for (const dir of readdirSync(MODULES_DIR)) {
    let mod: { key: string; fields?: { name: string; columns?: { name: string; type: string; module?: string }[] }[] };
    try {
      mod = JSON.parse(readFileSync(resolve(MODULES_DIR, dir, "module.json"), "utf8"));
    } catch { continue; }
    for (const f of mod.fields ?? []) {
      for (const c of f.columns ?? []) {
        if (c.type === "reference") out.push({ module: mod.key, field: f.name, column: c.name, target: c.module ?? "" });
      }
    }
  }
  return out;
}

describe("MOD-TABLEREF — a reference column in a line-item table", () => {
  it("is actually used by a shipped module — a column type nothing declares is dead config", () => {
    const cols = referenceColumns();
    expect(cols.length).toBeGreaterThan(0);
    // every one names a register that exists on disk; the server gate enforces this too, and it is
    // repeated here because the two run at different times and the web build must not ship a picker
    // pointed at nothing
    const installed = new Set(readdirSync(MODULES_DIR));
    for (const c of cols) {
      expect(installed.has(c.target), `${c.module}.${c.field}[${c.column}] -> ${c.target}`).toBe(true);
    }
  });

  it("keeps a stored value the options do not contain, so saving a row cannot erase a link", () => {
    const src = readFileSync(PORTAL, "utf8");
    const start = src.indexOf('if (c.type === "reference")');
    expect(start, "the reference-column branch is missing from tableEditor").toBeGreaterThan(0);
    const branch = src.slice(start, start + 2400);

    // the stored value is read, and compared against the fetched options rather than assumed present
    expect(branch).toMatch(/const stored = /);
    expect(branch).toMatch(/!opts\.some\(/);
    // ...and when it is absent, an option carrying that exact value is added and selected. Without
    // BOTH of these the control silently resets to blank.
    expect(branch).toMatch(/keep\.value = stored/);
    expect(branch).toMatch(/inp\.value = stored/);
  });

  it("shows an unresolved id as an id and free text in full — refCell's three-way split, per row", () => {
    const src = readFileSync(PORTAL, "utf8");
    const start = src.indexOf('if (c.type === "reference")');
    const branch = src.slice(start, start + 2400);
    // a UUID that resolved to nothing is truncated and marked "not found" — it is an id, and showing
    // it whole implies a record that is not there
    expect(branch).toMatch(/UUID_RE\.test\(stored\)/);
    expect(branch).toMatch(/not found/);
    // free text is NOT truncated: it is the only handle anyone has for re-linking the row, and eight
    // characters of it is the precise defect refCell was written to remove
    expect(branch).toMatch(/not linked/);
    expect(branch).not.toMatch(/stored\.slice\(0, 8\)[^)]*\(not linked\)/);
  });
});
