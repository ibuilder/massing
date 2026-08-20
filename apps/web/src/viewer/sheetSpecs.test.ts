import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import {
  DEFAULT_SHEET_PAGE, PAGE_CATALOG, PAGE_KEYS, SHEET_PAGE_STORAGE_KEY, SHEET_PARAMS,
  encodeViews, isSheetPage, railSheetOptions, readSheetPage, sheetPath, sheetQuery,
  viewsForCanvas, writeSheetPage,
} from "./sheetSpecs";

const REPO = resolve(__dirname, "../../../..");

beforeEach(() => {
  try { localStorage.removeItem(SHEET_PAGE_STORAGE_KEY); }
  catch { /* node without storage */ }
});

/**
 * R36 print slice 3 — and the defect that made it necessary.
 *
 * The rail built its sheet URLs inline, three times, and sent `number`, `title` and `scale`. The
 * route accepts `sheet`, `page`, `purpose`, `rev`, `storey`, `views`. Measured live before the fix:
 *
 *     GET …/drawings/sheet.svg?number=A-999&title=TEST   ->  a sheet numbered A-101
 *
 * FastAPI drops unknown query parameters, so all three were discarded in silence. It looked correct
 * because the rail's `number=A-101` equalled the route's default — the per-storey title it computed
 * never reached the paper, and nothing anywhere said so.
 *
 * These tests exist so a parameter that goes nowhere cannot be sent: the emitted key set is asserted
 * against the ROUTE'S OWN SIGNATURE, read from the Python source, rather than against a list someone
 * has to remember to update.
 */

function routeParams(): Set<string> {
  const src = readFileSync(
    resolve(REPO, "services/api/src/aec_api/routers/drawings.py"), "utf8");
  const at = src.indexOf("def sheet_svg(");
  expect(at, "sheet_svg not found — this gate can no longer read the contract").toBeGreaterThan(-1);
  const sig = src.slice(at, src.indexOf("):", at));
  const names = new Set<string>();
  for (const m of sig.matchAll(/(\w+)\s*:/g)) names.add(m[1]!);
  names.delete("pid"); names.delete("db"); names.delete("_sec");   // path + dependencies, not query
  return names;
}

describe("the client can only send parameters the route accepts", () => {
  it("SHEET_PARAMS matches the route signature exactly — asserted as a SET", () => {
    // Both directions. A missing name means the client cannot use a real feature; an extra means it
    // sends something discarded in silence, which is the bug this file exists for.
    const route = routeParams();
    expect(new Set(SHEET_PARAMS)).toEqual(route);
  });

  it("never emits the keys the rail used to send", () => {
    const q = sheetQuery({ sheet: "A-101", purpose: "LEVEL 2 PLAN", storey: "Level 2" });
    for (const dead of ["number", "title", "scale"]) {
      expect(q.has(dead), `${dead}= is not a route parameter and must never be sent`).toBe(false);
    }
    expect(q.get("sheet")).toBe("A-101");
    expect(q.get("purpose"), "the per-level description belongs in purpose — there is no title field")
      .toBe("LEVEL 2 PLAN");
  });

  it("the rail names ARCH-C (24×18 in) by default, not a silent A3 / a tooltip that says ARCH-D", () => {
    // compose() defaults to A3 when `page` is omitted. 24×18 in is ARCH C, not an ISO A sheet.
    const q = sheetQuery(railSheetOptions("Level 2"));
    expect(q.get("page")).toBe("ARCH-C");
    expect(q.get("sheet")).toBe("A-101");
  });

  it("the picker writes the size the next Issue/PDF request sends", () => {
    writeSheetPage("ARCH-B");
    expect(readSheetPage()).toBe("ARCH-B");
    expect(sheetQuery(railSheetOptions("Level 2")).get("page")).toBe("ARCH-B");
  });

  it("an unknown stored value falls back to ARCH-C rather than sending it", () => {
    localStorage.setItem(SHEET_PAGE_STORAGE_KEY, "TABLOID");
    expect(readSheetPage()).toBe(DEFAULT_SHEET_PAGE);
    expect(isSheetPage("TABLOID")).toBe(false);
  });

  it("drops empty values rather than sending them blank", () => {
    // `purpose=` would overwrite a meaningful default with nothing. "Sent empty" and "did not
    // mention" are different requests.
    const q = sheetQuery({ sheet: "A-101", purpose: "", rev: undefined, storey: null });
    expect([...q.keys()]).toEqual(["sheet"]);
  });
});

describe("the views grammar, written to match the server's parser", () => {
  it("encodes every kind in the documented form", () => {
    expect(encodeViews([
      { kind: "plan" },
      { kind: "plan", elevation: 3.5 },
      { kind: "section", axis: "x", offset: 12.5 },
      { kind: "elevation", direction: "north" },
      { kind: "axon" },
      { kind: "axon", azimuth: 30, elevationAngle: 20 },
    ])).toBe("plan,plan@3.5,section:x@12.5,elevation:north,axon,axon@30x20");
  });

  it("a bare axon carries NO angles, so the server's isometric default wins", () => {
    // Emitting `axon@45x35.264` would freeze a rounded elevation angle into every URL. The server
    // computes the true isometric from atan(1/√2) — a rounded 35.264 was measurably not isometric,
    // which is why `axon_basis` computes rather than types it.
    expect(encodeViews([{ kind: "axon" }])).toBe("axon");
    expect(encodeViews([{ kind: "axon", azimuth: 45 }])).toBe("axon");   // partial → still default
  });

  it("every encoded string is one the server's grammar documents", () => {
    // The client writes, the server parses. Pinned against the documented forms so the two cannot
    // drift into a dialect only one of them speaks.
    const grammar = /^(plan(@-?[\d.]+)?|section:[xy]@-?[\d.]+|elevation:(north|south|east|west)|axon(@-?[\d.]+x-?[\d.]+)?)$/;
    const encoded = encodeViews([
      { kind: "plan", elevation: -3 }, { kind: "section", axis: "y", offset: -1.5 },
      { kind: "elevation", direction: "west" }, { kind: "axon", azimuth: 30, elevationAngle: 20 },
    ]);
    for (const token of encoded.split(",")) {
      expect(token, `${token} is not a form the server's grammar documents`).toMatch(grammar);
    }
  });
});

describe("views and storey are not both sent", () => {
  it("explicit views win, and storey is dropped", () => {
    // Naming the viewports AND asking the server to pick a level is a contradiction; the server
    // would honour one and ignore the other, silently. Say one thing.
    const q = sheetQuery({ storey: "Level 2", views: [{ kind: "axon" }] });
    expect(q.get("views")).toBe("axon");
    expect(q.has("storey")).toBe(false);
  });

  it("an empty views array falls back to storey rather than sending views=", () => {
    // `views=` empty is refused by the server (deliberately — it means the caller got the grammar
    // wrong). A client must never produce it by accident.
    const q = sheetQuery({ storey: "Level 2", views: [] });
    expect(q.has("views")).toBe(false);
    expect(q.get("storey")).toBe("Level 2");
  });
});

describe("placing what the canvas is showing", () => {
  it("2D places the active level's plan", () => {
    expect(viewsForCanvas("2d", 3.5)).toEqual([{ kind: "plan", elevation: 3.5 }]);
    expect(viewsForCanvas("2d", null)).toEqual([{ kind: "plan" }]);
  });

  it("3D places an isometric and does NOT pretend to match the camera", () => {
    // The 3D camera is perspective; an axonometric is parallel. "The same view" is not well defined
    // between them, so this places a true isometric rather than guessing a correspondence. Matching
    // the live camera is a real future ask and a harder question than it looks.
    expect(viewsForCanvas("3d", 3.5)).toEqual([{ kind: "axon" }]);
  });

  it("builds a path a browser can open", () => {
    const p = sheetPath("p1", "pdf", { sheet: "A-102", views: [{ kind: "plan", elevation: 0 }] });
    expect(p).toBe("/projects/p1/drawings/sheet.pdf?sheet=A-102&views=plan%400");
  });
});

describe("the control is WIRED INTO the rail, not merely constructed", () => {
  /**
   * This repo's most-repeated defect: a pane or button built, styled, tested and never appended.
   * `planPaneBtn` shipped that way from v0.3.826 to 2026-08-02; `deltaUi` and `placeBtn` each nearly
   * did this week. I could not check this one in a browser — the "Drawings & sheets" rail group only
   * builds when a model is loaded, and in the dev environment the export group renders with zero
   * buttons, siblings included. So the claim is asserted against the source instead of left unmade.
   *
   * A source assertion is the weaker instrument and it is the honest one here: the alternative was to
   * say "verified" about something I did not see.
   */
  const app = readFileSync(resolve(REPO, "apps/web/src/viewer/app.ts"), "utf8");
  const sect = readFileSync(resolve(REPO, "apps/web/src/viewer/tools/drawingsSection.ts"), "utf8");

  /**
   * **R39-DECOMP-VIEWER ⑦ moved this gate's subject and the gate went red — correctly.** Its own
   * failure message said *"the rail moved and this gate is now blind"*, which is exactly what had
   * happened: the buttons are built in `tools/drawingsSection.ts` now and only *appended* in
   * `app.ts`. A gate that names a file is only ever as good as that address, and an extraction is
   * precisely the event that invalidates one.
   *
   * Re-pointing it at the new file alone would have made it weaker than before, because the chain
   * has a new link that can break silently: the module could construct `placeBtn` and forget to
   * **return** it, and `app.ts` would append an array that never contained it. So the check now
   * follows all three hops — built, returned, appended — which is a stronger claim than the single
   * file could make.
   */
  it("placeBtn is constructed, RETURNED, and appended to a rail group", () => {
    expect(sect, "the control must exist").toMatch(/const placeBtn = d\.toolBtn2\(/);

    const ret = sect.match(/return \[[^\]]*\]/s)?.[0] ?? "";
    expect(ret, "the section returns no button array — this gate cannot see the seam")
      .not.toBe("");
    expect(ret, "placeBtn is built but not returned — it would never reach the rail")
      .toContain("placeBtn");

    const group = app.match(/railGroup\("export"[^)]*\)/s)?.[0] ?? "";
    expect(group, "railGroup(\"export\", …) not found — the rail moved and this gate is now blind")
      .not.toBe("");
    // The array the section returns is what the rail group receives. Whatever the caller names it,
    // the group must be fed the section's output rather than a hand-listed subset that can drift.
    expect(group, "the rail group no longer consumes the section's returned buttons")
      .toMatch(/drawingBtns|buildDrawingsSection/);
  });

  it("the sheet buttons go through sheetSpecs, not hand-rolled query strings", () => {
    // The three inline URLSearchParams builders are what sent `number`/`title`/`scale` into the void.
    // If one comes back, this fails before it can silently drop parameters again. Both files are
    // scanned: the construction moved, but `app.ts` must not grow a replacement either.
    for (const [name, src] of [["app.ts", app], ["drawingsSection.ts", sect]] as const) {
      const sheetUrls = src.match(/drawings\/sheet\.(svg|pdf|dxf)\?\$\{/g) ?? [];
      expect(sheetUrls, `a hand-built sheet URL in ${name} bypasses the SHEET_PARAMS allowlist`)
        .toEqual([]);
    }
    expect(sect).toContain("sheetPath(d.projectId!");
    expect(sect, "Issue/PDF claimed ARCH-D while compose defaulted to A3")
      .not.toMatch(/Issue sheet[\s\S]{0,400}ARCH-D/);
    expect(sect).toContain("PAGE_CATALOG");
    expect(sect).toContain("paperPicker()");
  });
});

describe("the page catalog matches the server and names construction sizes", () => {
  it("PAGE_KEYS is lockstep with drawings.PAGES", () => {
    const src = readFileSync(resolve(REPO, "services/data/src/aec_data/drawings.py"), "utf8");
    const at = src.indexOf("PAGES = {");
    expect(at, "PAGES dict not found — this gate cannot see the server catalog").toBeGreaterThan(-1);
    const block = src.slice(at, src.indexOf("\n}", at) + 2);
    const keys = [...block.matchAll(/"([^"]+)":/g)].map((m) => m[1]);
    expect(PAGE_KEYS.slice()).toEqual(keys);
  });

  it("every catalog row is a known key, and 24×18 is ARCH-C", () => {
    expect(PAGE_CATALOG.map((r) => r.key)).toEqual([...PAGE_KEYS]);
    expect(PAGE_CATALOG[0]!.key).toBe("ARCH-C");
    expect(PAGE_CATALOG.find((r) => r.key === "ARCH-C")!.label).toMatch(/24×18/);
    expect(PAGE_CATALOG.find((r) => r.key === "ARCH-B")!.label).toMatch(/half of D/);
    expect(PAGE_CATALOG.find((r) => r.key === "ARCH-A")!.label).toMatch(/quarter of D/);
  });
});
