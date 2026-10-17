import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ViewTemplate } from "../../api/model";
import type { PanelContext } from "../panelContext";
import { badColors, carriedThrough, flattenedCategories, isDeclared, MAX_STYLES, MAX_WEIGHT,
  MIN_WEIGHT, renderViewTemplates, styleIssues, summarise } from "./viewTemplates";

const tpl = (over: Partial<ViewTemplate> = {}): ViewTemplate => ({
  id: "t1", name: "Fire plan", hide_classes: [], isolate: null, rules: [], ...over,
});

describe("isDeclared — the server's one refusal, checked before the round trip", () => {
  it("is false for a template that sets nothing", () => {
    expect(isDeclared(tpl())).toBe(false);
  });

  it("is true for any ONE of the four, which is exactly what the server requires", () => {
    expect(isDeclared(tpl({ hide_classes: ["IfcSpace"] }))).toBe(true);
    expect(isDeclared(tpl({ isolate: "ifc_class = IfcWall" }))).toBe(true);
    expect(isDeclared(tpl({ rules: [{ selector: "x", color: "#111111" }] }))).toBe(true);
    expect(isDeclared(tpl({ object_styles: { ifcwall: { cut: { weight: 0.7 } } } }))).toBe(true);
  });

  it("does not count a whitespace isolate as a declaration", () => {
    // The server strips it to None, so a template whose only content is "   " would be accepted
    // here and refused there — the one direction this check must not be wrong in.
    expect(isDeclared(tpl({ isolate: "   " }))).toBe(false);
  });
});

describe("badColors", () => {
  it("names the rule indexes whose colour is not #rrggbb", () => {
    expect(badColors([{ selector: "a", color: "#112233" }, { selector: "b", color: "red" },
                      { selector: "c", color: "#abc" }])).toEqual([1, 2]);
  });

  it("accepts upper case, which the server lowercases rather than rejects", () => {
    expect(badColors([{ selector: "a", color: "#AABBCC" }])).toEqual([]);
  });
});

describe("carriedThrough — counting what this editor preserves but does not author", () => {
  it("counts object-style categories and rule-level graphic overrides separately", () => {
    const t = tpl({
      object_styles: { ifcwall: { cut: { weight: 0.7 } }, ifcdoor: { projection: { halftone: true } } },
      rules: [{ selector: "a", color: "#111111", weight: 0.5 },
              { selector: "b", color: "#222222" },
              { selector: "c", color: "#333333", pattern: "dashed" }],
    });
    // VG-STYLES added `unauthored`, which is the one the preservation note reads. It counts rule-
    // level overrides ALONE now, because the editor authors the object-style table — a note saying
    // "preserved unchanged" over a field the user just edited is worse than no note. `styles` is
    // kept because the section heading and `summarise` both want it. *A count does not become wrong
    // when the product changes; the SENTENCE it was feeding does.*
    expect(carriedThrough(t)).toEqual({ styles: 2, overrides: 2, unauthored: 2 });
  });

  it("counts a halftone:false override as present, because false is a decision", () => {
    // `_norm_override` stores `halftone` whenever it is not None, so `false` is a stored fact and
    // dropping it on a round trip would change the drawing.
    expect(carriedThrough(tpl({ rules: [{ selector: "a", color: "#111111", halftone: false }] }))
      .overrides).toBe(1);
  });

  it("is zero for a plain template", () => {
    expect(carriedThrough(tpl({ rules: [{ selector: "a", color: "#111111" }] })))
      .toEqual({ styles: 0, overrides: 0, unauthored: 0 });
  });
});

describe("styleIssues — VG-STYLES: the server's bounds, restated so a user sees every problem", () => {
  it("is empty for a table the server accepts", () => {
    expect(styleIssues({ ifcwall: { cut: { weight: 1.4, color: "#111111", pattern: "solid" } },
                         ifcdoor: { projection: { halftone: true } } })).toEqual([]);
    expect(styleIssues(undefined)).toEqual([]);
    expect(styleIssues({})).toEqual([]);
  });

  it("names the class and side of an out-of-range weight", () => {
    // `_norm_override` quotes the value and the bounds; this names WHICH entry, which the server's
    // message cannot do for the entries it never reached.
    expect(styleIssues({ ifcwall: { cut: { weight: 7 } } }))
      .toEqual([`ifcwall.cut weight 7 is outside ${MIN_WEIGHT}–${MAX_WEIGHT} mm.`]);
    expect(styleIssues({ ifcwall: { cut: { weight: 0.01 } } })[0]).toContain("0.01 is outside");
    expect(styleIssues({ ifcwall: { cut: { weight: MIN_WEIGHT } } })).toEqual([]);
    expect(styleIssues({ ifcwall: { cut: { weight: MAX_WEIGHT } } })).toEqual([]);
  });

  it("names a bad colour and a bad pattern", () => {
    expect(styleIssues({ ifcwall: { projection: { color: "red" } } })[0])
      .toBe('ifcwall.projection colour "red" is not #rrggbb.');
    expect(styleIssues({ ifcwall: { cut: { pattern: "squiggly" } } })[0])
      .toContain('ifcwall.cut pattern "squiggly" is not one of solid, dashed');
  });

  it("refuses an entry that sets neither side, and a side that sets nothing", () => {
    // Two different server refusals with two different remedies: remove the class, or fill the side.
    expect(styleIssues({ ifcwall: {} })[0]).toContain("ifcwall sets neither side");
    expect(styleIssues({ ifcwall: { cut: {} } })[0]).toContain("ifcwall.cut sets nothing");
  });

  it("counts a halftone:false override as SET, because false is a decision", () => {
    // `_norm_override` stores `halftone` whenever it is not None, so an entry whose only content is
    // `halftone: false` is a real override and must not be reported as empty.
    expect(styleIssues({ ifcwall: { cut: { halftone: false } } })).toEqual([]);
  });

  it("reports the category cap, which the server states as a whole-save refusal", () => {
    const big = Object.fromEntries(Array.from({ length: MAX_STYLES + 1 },
      (_, i) => [`ifcthing${i}`, { cut: { weight: 0.5 } }]));
    expect(styleIssues(big)[0]).toContain(`${MAX_STYLES + 1} object-style categories`);
  });

  it("orders by class then side, so two runs read the same", () => {
    // A list whose order follows object-key iteration is a list a user cannot re-find their place in.
    expect(styleIssues({ zz: { cut: { weight: 9 } }, aa: { projection: { weight: 9 } } })
      .map((x) => x.split(" ")[0])).toEqual(["aa.projection", "zz.cut"]);
  });
});

describe("flattenedCategories — the distinction this whole feature exists to express", () => {
  it("names a category whose cut side is no heavier than its projection side", () => {
    expect(flattenedCategories({ ifcwall: { cut: { weight: 0.2 }, projection: { weight: 0.3 } } }))
      .toEqual(["ifcwall"]);
    expect(flattenedCategories({ ifcwall: { cut: { weight: 0.3 }, projection: { weight: 0.3 } } }))
      .toEqual(["ifcwall"]);
  });

  it("says nothing about the normal case: a cut override over a lighter default", () => {
    // A cut-only override is how this is usually authored, and the category default projection is
    // always lighter — ruling on it would warn on every correct entry.
    expect(flattenedCategories({ ifcwall: { cut: { weight: 0.2 } } })).toEqual([]);
    expect(flattenedCategories({ ifcwall: { projection: { weight: 0.9 } } })).toEqual([]);
    expect(flattenedCategories({ ifcwall: { cut: { weight: 1.4 }, projection: { weight: 0.18 } } }))
      .toEqual([]);
  });

  it("is empty rather than throwing on an absent table", () => {
    expect(flattenedCategories(undefined)).toEqual([]);
  });
});

describe("summarise", () => {
  it("describes what the template does, in the viewer's own vocabulary", () => {
    expect(summarise(tpl({ isolate: "ifc_class = IfcWall", hide_classes: ["IfcSpace"],
                           rules: [{ selector: "a", color: "#111111" }] })))
      .toBe("isolate ifc_class = IfcWall · hides 1 · 1 colour rule(s)");
  });

  it("says a template sets nothing rather than printing an empty string", () => {
    expect(summarise(tpl())).toBe("sets nothing yet");
  });
});

// --- the editor ---------------------------------------------------------------------------------

function ctx(over: Record<string, unknown> = {}) {
  const api = {
    viewTemplates: vi.fn().mockResolvedValue({ templates: [] }),
    saveViewTemplates: vi.fn().mockImplementation((_pid: string, t: ViewTemplate[]) =>
      Promise.resolve({ saved: t.length, templates: t.map((x, i) => ({ ...x, id: x.id || `new${i}` })) })),
    ...over,
  };
  const host = document.createElement("div");
  const c = {
    root: document.createElement("div"),
    host: { projectId: () => "p1", api } as unknown as PanelContext["host"],
  } as unknown as PanelContext;
  return { c, api, host };
}

const btn = (host: HTMLElement, text: string) =>
  Array.from(host.querySelectorAll("button")).find((b) => (b.textContent ?? "").includes(text))!;
/** By placeholder SUBSTRING, which is a sharp edge worth naming: probing for `"mm"` matched the
 *  isolate field, because its hint contains `Pset_WallCommon` — "Co-**mm**-on". That sent VG-STYLES'
 *  first weight assertion at a text input three fields away, and the readings it took there
 *  (`min=""`, `step=""`, `valueAsNumber` NaN, no `oninput` delivery) were then written up as a
 *  happy-dom defect in `type="number"`. There is no such defect. *A substring probe answers a
 *  question nobody asked, confidently* — the same thing PROBE-BOUNDARY paid for on the server. Pass
 *  enough of the placeholder to be unambiguous. */
const input = (host: HTMLElement, placeholder: string) => {
  const hits = Array.from(host.querySelectorAll("input"))
    .filter((i) => (i.placeholder ?? "").includes(placeholder));
  // Fails CLOSED on ambiguity rather than silently taking whichever came first in DOM order, which
  // is what let the collision above go unnoticed. `find` would have returned the isolate field with
  // no complaint, and a confident assertion against the wrong element is worse than no assertion.
  if (hits.length !== 1) {
    throw new Error(`input("${placeholder}") matched ${hits.length}: `
      + `${hits.map((i) => JSON.stringify(i.placeholder)).join(", ") || "nothing"}`);
  }
  return hits[0]!;
};

describe("renderViewTemplates", () => {
  beforeEach(() => vi.clearAllMocks());

  it("says no template is saved, and offers to add one", async () => {
    const { c, host } = ctx();
    await renderViewTemplates(c, host, "p1");
    expect(host.textContent).toContain("No view templates saved");
    expect(btn(host, "＋ template")).toBeTruthy();
  });

  it("refuses locally and NAMES the template that sets nothing", async () => {
    // The server rejects the whole list for one bad template and its message carries no index, so
    // a local refusal that names it is more use than the 422 would be.
    const { c, api, host } = ctx();
    await renderViewTemplates(c, host, "p1");
    btn(host, "＋ template").click();
    btn(host, "Save templates").click();
    await Promise.resolve();
    expect(host.textContent).toContain("Template 1");
    expect(host.textContent).toContain("set nothing");
    expect(api.saveViewTemplates).not.toHaveBeenCalled();
  });

  it("PRESERVES object styles and rule-level overrides through an edit of something else", async () => {
    // THE DEFECT THIS FILE COULD MOST EASILY HAVE SHIPPED. `save` replaces the whole list, so a
    // payload built from a fresh object deletes every graphic fact this editor does not author —
    // and only on the templates the user touched, which is the AUTHORITY-SUPERSEDE shape: the loss
    // is proportional to how much they edited.
    const stored: ViewTemplate = {
      id: "t1", name: "Fire plan", hide_classes: ["IfcSpace"], isolate: null,
      rules: [{ selector: "ifc_class = IfcDoor", color: "#b3261e", applies: "cut",
                weight: 0.7, pattern: "dashed", halftone: false }],
      object_styles: { ifcwall: { cut: { weight: 0.5, color: "#111111" } } },
    };
    const { c, api, host } = ctx({
      viewTemplates: vi.fn().mockResolvedValue({ templates: [stored] }),
    });
    await renderViewTemplates(c, host, "p1");
    const name = input(host, "template name");
    name.value = "Fire plan rev B";
    name.dispatchEvent(new Event("input"));
    btn(host, "Save templates").click();
    await Promise.resolve(); await Promise.resolve();
    const sent = api.saveViewTemplates.mock.calls[0]![1] as ViewTemplate[];
    expect(sent[0]!.name).toBe("Fire plan rev B");
    expect(sent[0]!.object_styles).toEqual({ ifcwall: { cut: { weight: 0.5, color: "#111111" } } });
    expect(sent[0]!.rules[0]).toMatchObject({ applies: "cut", weight: 0.7, pattern: "dashed",
                                              halftone: false });
  });

  it("renders the count of what it preserves, so a silent drop would be visible", async () => {
    const { c, host } = ctx({
      viewTemplates: vi.fn().mockResolvedValue({ templates: [tpl({
        rules: [{ selector: "a", color: "#111111", weight: 0.5 }],
        object_styles: { ifcwall: { cut: { weight: 0.7 } } } })] }),
    });
    await renderViewTemplates(c, host, "p1");
    // The object-style category is no longer "preserved but not authored" — VG-STYLES gave it a
    // form, so claiming preservation over it would be false. The rule-level override is still
    // unauthored and still counted, and the note now says WHY the two differ: one is per class and
    // the other per selector.
    expect(host.textContent).not.toContain("object-style categor");
    expect(host.textContent).toContain("1 rule-level weight/pattern/halftone override");
    expect(host.textContent).toContain("set per SELECTOR rather than per class");
  });

  // ── VG-STYLES: the per-category weight table, authored end to end ─────────────────────────────
  it("authors an object style and SENDS it, which is the whole of VG-STYLES", async () => {
    const { c, api, host } = ctx({
      viewTemplates: vi.fn().mockResolvedValue({ templates: [tpl({ hide_classes: ["IfcSpace"] })] }),
    });
    await renderViewTemplates(c, host, "p1");
    btn(host, "＋ object style").click();
    const mm = input(host, "weight mm");
    mm.value = "1.4"; mm.dispatchEvent(new Event("input"));
    const hex = Array.from(host.querySelectorAll("input"))
      .filter((i) => (i.placeholder ?? "") === "#rrggbb").at(-1)!;
    hex.value = "#cc0000"; hex.dispatchEvent(new Event("input"));
    btn(host, "Save templates").click();
    await Promise.resolve(); await Promise.resolve();
    const sent = api.saveViewTemplates.mock.calls[0]![1] as ViewTemplate[];
    expect(sent[0]!.object_styles).toEqual({ ifcwall: { cut: { weight: 1.4, color: "#cc0000" } } });
  });

  it("clearing a field DELETES the key rather than sending an empty string", async () => {
    // `_norm_override` refuses `""` as a colour and `""` as a weight, so a blanked field must leave
    // the override rather than be sent as a value the server will reject the whole save for.
    const { c, api, host } = ctx({
      viewTemplates: vi.fn().mockResolvedValue({ templates: [tpl({
        hide_classes: ["IfcSpace"],
        object_styles: { ifcwall: { cut: { weight: 0.9, color: "#cc0000" } } } })] }),
    });
    await renderViewTemplates(c, host, "p1");
    const hex = Array.from(host.querySelectorAll("input"))
      .filter((i) => (i.placeholder ?? "") === "#rrggbb").at(-1)!;
    hex.value = ""; hex.dispatchEvent(new Event("input"));
    btn(host, "Save templates").click();
    await Promise.resolve(); await Promise.resolve();
    const sent = api.saveViewTemplates.mock.calls[0]![1] as ViewTemplate[];
    expect(sent[0]!.object_styles).toEqual({ ifcwall: { cut: { weight: 0.9 } } });
  });

  it("refuses locally, naming the template AND the class, before the round trip", async () => {
    const { c, api, host } = ctx({
      viewTemplates: vi.fn().mockResolvedValue({ templates: [tpl({
        hide_classes: ["IfcSpace"], object_styles: { ifcwall: { cut: { weight: 9 } } } })] }),
    });
    await renderViewTemplates(c, host, "p1");
    btn(host, "Save templates").click();
    expect(api.saveViewTemplates).not.toHaveBeenCalled();
    expect(host.textContent).toContain("Fire plan: ifcwall.cut weight 9 is outside");
  });

  it("warns when an authored style flattens the cut/projection distinction, without refusing it", async () => {
    // Stored as written — a drafter may mean it — but losing the depth cue in silence is the defect
    // the partial-override rule exists to prevent, arriving through the front door.
    const { c, host } = ctx({
      viewTemplates: vi.fn().mockResolvedValue({ templates: [tpl({
        object_styles: { ifcwall: { cut: { weight: 0.2 }, projection: { weight: 0.4 } } } })] }),
    });
    await renderViewTemplates(c, host, "p1");
    expect(host.textContent).toContain("cut side is no heavier than the projection side");
    expect(host.textContent).toContain("a warning, not a refusal");
  });

  it("names the sheet-space weight bounds on screen, from one source", async () => {
    const { c, host } = ctx({
      viewTemplates: vi.fn().mockResolvedValue({ templates: [tpl({ hide_classes: ["IfcSpace"] })] }),
    });
    await renderViewTemplates(c, host, "p1");
    expect(host.textContent).toContain(`millimetres ON THE SHEET (${MIN_WEIGHT}–${MAX_WEIGHT})`);
  });

  it("offers the cut / projection scope the client type did not declare before", async () => {
    const { c, host } = ctx({
      viewTemplates: vi.fn().mockResolvedValue({ templates: [tpl({
        rules: [{ selector: "a", color: "#111111", applies: "projection" }] })] }),
    });
    await renderViewTemplates(c, host, "p1");
    const sel = host.querySelector("select") as HTMLSelectElement;
    expect(Array.from(sel.options).map((o) => o.value)).toEqual(["both", "cut", "projection"]);
    expect(sel.value).toBe("projection");
  });

  it("omits a blank id so the server assigns one, and keeps a real id", async () => {
    const { c, api, host } = ctx({
      viewTemplates: vi.fn().mockResolvedValue({ templates: [tpl({ hide_classes: ["IfcSpace"] })] }),
    });
    await renderViewTemplates(c, host, "p1");
    btn(host, "＋ template").click();
    input(host, "IfcFurnishingElement").value = "IfcSpace";
    input(host, "IfcFurnishingElement").dispatchEvent(new Event("input"));
    btn(host, "Save templates").click();
    await Promise.resolve(); await Promise.resolve();
    const sent = api.saveViewTemplates.mock.calls[0]![1] as { id?: string }[];
    expect(sent[0]!.id).toBe("t1");
    expect("id" in sent[1]!).toBe(false);
  });

  it("shows the server's refusal verbatim — it names the selector that failed to parse", async () => {
    const { c, host } = ctx({
      viewTemplates: vi.fn().mockResolvedValue({ templates: [tpl({ hide_classes: ["IfcSpace"] })] }),
      saveViewTemplates: vi.fn().mockRejectedValue(
        new Error("unknown field 'Pset_Foo.Bar' in selector")),
    });
    await renderViewTemplates(c, host, "p1");
    btn(host, "Save templates").click();
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    expect(host.textContent).toContain("unknown field 'Pset_Foo.Bar'");
  });

  it("reports a failed load as a reason, never as an empty list", async () => {
    const { c, host } = ctx({
      viewTemplates: vi.fn().mockRejectedValue(new Error("403 forbidden")),
    });
    await renderViewTemplates(c, host, "p1");
    expect(host.textContent).toContain("View templates unavailable: 403 forbidden");
    expect(host.textContent).not.toContain("No view templates saved");
  });
});
