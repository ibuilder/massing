import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ViewTemplate } from "../../api/model";
import type { PanelContext } from "../panelContext";
import { badColors, carriedThrough, isDeclared, renderViewTemplates, summarise } from "./viewTemplates";

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
    expect(carriedThrough(t)).toEqual({ styles: 2, overrides: 2 });
  });

  it("counts a halftone:false override as present, because false is a decision", () => {
    // `_norm_override` stores `halftone` whenever it is not None, so `false` is a stored fact and
    // dropping it on a round trip would change the drawing.
    expect(carriedThrough(tpl({ rules: [{ selector: "a", color: "#111111", halftone: false }] }))
      .overrides).toBe(1);
  });

  it("is zero for a plain template", () => {
    expect(carriedThrough(tpl({ rules: [{ selector: "a", color: "#111111" }] })))
      .toEqual({ styles: 0, overrides: 0 });
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
const input = (host: HTMLElement, placeholder: string) =>
  Array.from(host.querySelectorAll("input"))
    .find((i) => (i.placeholder ?? "").includes(placeholder))!;

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
    expect(host.textContent).toContain("1 object-style category");
    expect(host.textContent).toContain("1 rule-level weight/pattern override");
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
