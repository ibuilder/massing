import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { DRAFT_ELEMENTS } from "./draftCatalog";
import {
  draftGlyph, FALLBACK_GLYPH, GLYPHS, GLYPH_VIEWBOX, glyphElement, hasExplicitGlyph,
  normaliseIfcClass,
} from "./draftGlyph";

/**
 * UX-3 — is there a glyph for every element the palette can actually list?
 *
 * THE FAILURE THIS IS SHAPED AROUND
 *     A glyph table is the easiest thing in this repository to make vacuous. Write
 *     `expect(draftGlyph("IfcWall")).toBeTruthy()` and it passes for every string ever written,
 *     because `draftGlyph` always returns something — the fallback. A test that cannot tell the
 *     fallback from a real entry reports "all classes covered" over a table with one row in it.
 *     So every assertion below goes through `hasExplicitGlyph`, never through truthiness, and the
 *     last test proves the distinction by asserting the fallback IS reached for an unknown class.
 *
 * AND THE POPULATION IS DERIVED, NOT LISTED
 *     Three catalogs can put a row in the Draft palette, and only one of them is TypeScript:
 *     `DRAFT_ELEMENTS` here, `content.py` (GET /content/catalog) and `families.py`
 *     (GET /families/catalog). Listing the classes in this file would make it a copy that drifts —
 *     the exact defect `test_seeding_sweep.py` and `roadmapLanes.test.ts` were both written for. It
 *     reads all three sources instead, so adding a draft element or a family with a new IFC class
 *     reds the build until the table gains an entry.
 *
 *     The two Python files are read as TEXT, not imported. That is a real limitation and it is
 *     stated rather than hidden: a class assembled at runtime (`"Ifc" + kind`) would be invisible
 *     here. Both files today write every `ifc_class` as a literal, and the count assertions below
 *     fail loudly if a refactor makes that stop being true — a source that suddenly yields zero
 *     classes is caught, which is the failure mode that would otherwise pass silently.
 */

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "../../../../..");

function pyClasses(rel: string): string[] {
  const src = readFileSync(resolve(REPO, rel), "utf8");
  return [...src.matchAll(/"ifc_class":\s*"(Ifc[A-Za-z]+)"/g)].map((m) => m[1]!);
}

const CONTENT_PY = "services/data/src/aec_data/content.py";
const FAMILIES_PY = "services/data/src/aec_data/families.py";

describe("draftGlyph — coverage over the derived palette population", () => {
  it("every built-in draft element has an explicit glyph", () => {
    const missing = DRAFT_ELEMENTS
      .filter((e) => !hasExplicitGlyph(e.ifcClass))
      .map((e) => `${e.key} (${e.ifcClass})`);
    expect(missing).toEqual([]);
    expect(DRAFT_ELEMENTS.length).toBeGreaterThan(30);   // the source still yields a real catalog
  });

  it("every content-catalog class has an explicit glyph", () => {
    const classes = pyClasses(CONTENT_PY);
    expect(classes.length).toBeGreaterThan(10);          // content.py still parses as expected
    expect([...new Set(classes)].filter((c) => !hasExplicitGlyph(c))).toEqual([]);
  });

  it("every family-library class has an explicit glyph", () => {
    const classes = pyClasses(FAMILIES_PY);
    expect(classes.length).toBeGreaterThan(20);          // families.py still parses as expected
    expect([...new Set(classes)].filter((c) => !hasExplicitGlyph(c))).toEqual([]);
  });

  it("the table has no entry no catalog can reach — a glyph for nothing is dead weight", () => {
    const reachable = new Set([
      ...DRAFT_ELEMENTS.map((e) => e.ifcClass),
      ...pyClasses(CONTENT_PY),
      ...pyClasses(FAMILIES_PY),
    ].map(normaliseIfcClass));
    expect(Object.keys(GLYPHS).filter((k) => !reachable.has(k))).toEqual([]);
  });
});

describe("draftGlyph — the fallback stays distinguishable", () => {
  it("an unknown class gets the fallback, and the fallback is not an explicit entry", () => {
    expect(draftGlyph("IfcSomethingNobodyModelledYet")).toBe(FALLBACK_GLYPH);
    expect(hasExplicitGlyph("IfcSomethingNobodyModelledYet")).toBe(false);
    expect(Object.values(GLYPHS)).not.toContain(FALLBACK_GLYPH);
  });

  it("normalisation strips the Ifc prefix and only a TRAILING Type", () => {
    expect(normaliseIfcClass("IfcWallType")).toBe("Wall");
    expect(normaliseIfcClass("IfcWall")).toBe("Wall");
    expect(normaliseIfcClass("IfcTransportElementType")).toBe("TransportElement");
    // The row badge used `.replace("Type", "")`, which removes the FIRST match anywhere. Nothing in
    // the catalogs hits that today; asserting the suffix rule keeps it that way by construction.
    expect(normaliseIfcClass("IfcTypedThing")).toBe("TypedThing");
  });

  it("a family type and its instance class share one glyph", () => {
    expect(draftGlyph("IfcWallType")).toBe(draftGlyph("IfcWall"));
    expect(draftGlyph("IfcFurnitureType")).toBe(draftGlyph("IfcFurniture"));
  });
});

describe("draftGlyph — the drawn output", () => {
  it("every glyph is real path data, distinct from the fallback and from each other", () => {
    // Compared as WHOLE GLYPHS, not path by path. Five explicit entries legitimately open with the
    // same outer box the fallback uses — a panel, an appliance, a diffuser — and the first draft of
    // this test rejected them, which would have pushed the table toward worse drawings to satisfy a
    // check. What must not collide is the finished shape.
    const sig = (g: { d: readonly string[] }) => g.d.join("|");
    const seen = new Map<string, string>();
    for (const [name, g] of Object.entries(GLYPHS)) {
      expect(g.d.length, name).toBeGreaterThan(0);
      expect(g.title, name).toMatch(/^[a-z][a-z ]*$/);       // lowercase, for a tooltip mid-sentence
      for (const d of g.d) {
        expect(d, name).toMatch(/^[MmLlHhVvCcSsQqTtAaZz0-9.\s-]+$/);   // path data only, never markup
      }
      expect(sig(g), `${name} is drawn as the fallback`).not.toBe(sig(FALLBACK_GLYPH));
      // A hand-authored table of 36 shapes is a copy-paste hazard, and two classes wearing the same
      // drawing is indistinguishable from a missing one on screen. If two SHOULD share a shape, make
      // them share one Glyph object — this compares by content, so a deliberate share still fails
      // here and has to be argued for rather than pasted in.
      expect(seen.get(sig(g)), `${name} duplicates ${seen.get(sig(g))}`).toBeUndefined();
      seen.set(sig(g), name);
    }
    expect(FALLBACK_GLYPH.d.join("|")).toBe("M3 3h10v10H3z|M8 8h0.01");
  });

  it("glyphElement builds SVG nodes — no markup is parsed, and it adds NO text to the row", () => {
    const svg = glyphElement(draftGlyph("IfcWall"));
    expect(svg.namespaceURI).toBe("http://www.w3.org/2000/svg");
    expect(svg.getAttribute("viewBox")).toBe(GLYPH_VIEWBOX);
    expect(svg.getAttribute("aria-hidden")).toBe("true");
    expect(svg.querySelectorAll("path").length).toBe(GLYPHS.Wall!.d.length);
    // The regression that made this assertion exist: an `<svg><title>` child counts toward the
    // enclosing row's textContent, so every palette row read "wallWall IfcWall". A decorative icon
    // must contribute nothing to the row's text — `draftPanel.test.ts` matches on it.
    expect(svg.textContent).toBe("");
    expect(svg.querySelector("title")).toBeNull();
  });

  it("a hostile class name reaches the DOM as text, never as an element", () => {
    // The row renders `normaliseIfcClass(item.ifcClass)`, and ifcClass is server-supplied for
    // families and content. This asserts the normaliser cannot mint markup out of one.
    const hostile = 'Ifc<img src=x onerror="alert(1)">';
    const span = document.createElement("span");
    span.textContent = normaliseIfcClass(hostile);
    expect(span.querySelector("img")).toBeNull();
    expect(span.textContent).toContain("<img");
    expect(draftGlyph(hostile)).toBe(FALLBACK_GLYPH);
  });
});
