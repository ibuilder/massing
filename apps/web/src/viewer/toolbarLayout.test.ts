import { describe, expect, it } from "vitest";
import { hasIcon } from "../ui/icons";
import { GROUP_LABELS, MAX_PRIMARY, TOOLS, TOOL_ICON, describe as describeTool, iconFor, primaryTitles, specFor, unlaidTitles } from "./toolbarLayout";
import { installToolbarView } from "./toolbarView";

/**
 * R26-TOOLBAR. The audit's finding was 25 unlabeled glyphs, all of them, always. The risk in fixing
 * it is losing a tool — so the tests below are mostly about *nothing disappearing*, and only then
 * about the bar being short.
 */
const ctx = (selection: boolean, canEdit = true) => ({ selection, canEdit });

describe("the table describes every tool, and nothing it does not", () => {
  it("has a unique label and group for each entry", () => {
    for (const t of TOOLS) {
      expect(t.label.trim().length, t.title).toBeGreaterThan(0);
      expect(GROUP_LABELS.map(([g]) => g), t.title).toContain(t.group);
    }
  });

  it("keys on titles, and titles are unique", () => {
    const titles = TOOLS.map((t) => t.title);
    expect(new Set(titles).size).toBe(titles.length);
  });

  it("reports an undescribed tool instead of silently dropping it", () => {
    expect(unlaidTitles(TOOLS.map((t) => t.title))).toEqual([]);
    expect(unlaidTitles(["Some new tool nobody laid out"])).toEqual(["Some new tool nobody laid out"]);
    expect(specFor("nope")).toBeNull();
  });

  it("pulls the More description from the title's own second half", () => {
    const withDash = TOOLS.find((t) => t.title.includes(" — "))!;
    expect(describeTool(withDash)).toBe(withDash.title.split(" — ")[1]);
    const plain = TOOLS.find((t) => !t.title.includes(" — "))!;
    expect(describeTool(plain)).toBe("");
  });
});

describe("the primary set is short, and contextual", () => {
  it("never exceeds the cap — 'contextual' that still shows fifteen has solved nothing", () => {
    for (const c of [ctx(false), ctx(true), ctx(true, false), ctx(false, false)]) {
      expect(primaryTitles(c).length).toBeLessThanOrEqual(MAX_PRIMARY);
    }
  });

  it("promotes the transform verbs only when something is selected", () => {
    const idle = primaryTitles(ctx(false));
    const picked = primaryTitles(ctx(true));
    expect(idle.some((t) => t.startsWith("Move selected"))).toBe(false);
    expect(picked.some((t) => t.startsWith("Move selected"))).toBe(true);
  });

  it("holds the pinned verbs in FIXED positions as context changes", () => {
    // The first version of this table failed here: contextual verbs pushed Ask past the cap, so it
    // silently moved into More the moment you selected something. A verb you learn the position of
    // and then cannot find is worse than one that was never on the bar.
    const idle = primaryTitles(ctx(false));
    for (const c of [ctx(true), ctx(true, false), ctx(false, false)]) {
      expect(primaryTitles(c).slice(0, idle.length)).toEqual(idle);
    }
  });

  it("keeps author verbs out of the primary row below Editor — they stay in More, dimmed", () => {
    const noEdit = primaryTitles(ctx(true, false));
    expect(noEdit.some((t) => t.startsWith("Move selected"))).toBe(false);
    expect(noEdit).toContain("Measure distance (M)");
  });

  it("fills the bar from what is INSTALLED, not from the table", () => {
    // Capping against the whole table and intersecting afterwards would leave a stripped-down
    // toolbar with fewer primary buttons than it has room for.
    const two = ["Measure distance (M)", "Ask the model — plain-English questions about the data"];
    expect(primaryTitles(ctx(true), two).sort()).toEqual([...two].sort());
    expect(primaryTitles(ctx(true), [])).toEqual([]);
  });
});

describe("the layout pass moves tools, it cannot lose them", () => {
  function host(titles: string[]): HTMLElement {
    const h = document.createElement("div");
    for (const t of titles) {
      const b = document.createElement("button");
      b.className = "tool-btn icon-btn"; b.title = t; b.textContent = "◆";
      h.append(b);
    }
    const sep = document.createElement("span"); sep.className = "tool-sep"; h.append(sep);
    document.body.append(h);
    return h;
  }
  const ALL = TOOLS.map((t) => t.title);

  it("keeps every button in the DOM, primary or not", () => {
    const h = host(ALL);
    const view = installToolbarView(h);
    view.update(ctx(false));
    const seen = [...h.querySelectorAll<HTMLButtonElement>(".tool-btn")]
      .map((b) => b.title).filter((t) => t !== "More tools");
    expect(new Set(seen)).toEqual(new Set(ALL));
    expect(view.unlaid()).toEqual([]);
  });

  it("shows only the primary set in the bar and the rest under More", () => {
    const h = host(ALL);
    installToolbarView(h).update(ctx(false));
    const bar = [...h.querySelectorAll<HTMLButtonElement>(".vt-primary .tool-btn")].map((b) => b.title);
    expect(bar).toEqual(primaryTitles(ctx(false), ALL));
    const menu = h.querySelector<HTMLElement>(".vt-menu")!;
    expect(menu.hidden).toBe(true);
    expect(menu.querySelectorAll(".tool-btn").length).toBe(ALL.length - bar.length);
  });

  it("labels every primary button — the glyph alone was the problem", () => {
    const h = host(ALL);
    installToolbarView(h).update(ctx(true));
    for (const b of h.querySelectorAll<HTMLButtonElement>(".vt-primary .tool-btn")) {
      expect(b.querySelector(".vt-label")?.textContent, b.title).toBeTruthy();
      // A MARK survives beside the word — one or the other, never neither. Until v0.3.711 that mark
      // was always the emoji this fixture supplies; now a mapped tool wears its vendored icon
      // instead. Asserting "a mark, of either kind" keeps what this test was actually protecting
      // (the bar does not become a wall of naked words) without pinning which kind it is.
      const mark = b.querySelector("svg.vt-icon") ?? b.querySelector(".vt-glyph");
      expect(mark, b.title).toBeTruthy();
    }
  });

  it("surfaces an undescribed button under More rather than dropping it", () => {
    const h = host([...ALL, "Brand new tool"]);
    const view = installToolbarView(h);
    view.update(ctx(false));
    expect(view.unlaid()).toEqual(["Brand new tool"]);
    const menu = h.querySelector<HTMLElement>(".vt-menu")!;
    expect(menu.dataset.unlaid).toBe("1");
    expect([...menu.querySelectorAll<HTMLButtonElement>(".tool-btn")].map((b) => b.title))
      .toContain("Brand new tool");
  });

  it("survives a toolbar missing some tools — a table entry with no button is not an error", () => {
    const h = host(["Measure distance (M)", "Ask the model — plain-English questions about the data"]);
    const view = installToolbarView(h);
    view.update(ctx(true));
    expect(view.unlaid()).toEqual([]);
    expect([...h.querySelectorAll<HTMLButtonElement>(".vt-primary .tool-btn")].map((b) => b.title))
      .toEqual(primaryTitles(ctx(true), ["Measure distance (M)", "Ask the model — plain-English questions about the data"]));
  });

  it("preserves the click handler and the capability tag across the move", () => {
    const h = host(["Move selected element (E,N,Z metres)", "Measure distance (M)"]);
    const moved = h.querySelector<HTMLButtonElement>('[title^="Move selected"]')!;
    moved.dataset.cap = "edit";
    let clicks = 0; moved.onclick = () => { clicks++; };
    installToolbarView(h).update(ctx(true));
    h.querySelector<HTMLButtonElement>('[title^="Move selected"]')!.click();
    expect(clicks).toBe(1);
    expect(h.querySelector<HTMLButtonElement>('[title^="Move selected"]')!.dataset.cap).toBe("edit");
  });

  it("re-lays without duplicating anything when the context changes", () => {
    const h = host(ALL);
    const view = installToolbarView(h);
    view.update(ctx(false));
    view.update(ctx(true));
    view.update(ctx(false));
    const seen = [...h.querySelectorAll<HTMLButtonElement>(".tool-btn")]
      .map((b) => b.title).filter((t) => t !== "More tools");
    expect(seen.length).toBe(ALL.length);
  });
});

// --- R26-ICONS: every verb wears an icon, and every icon is one we actually vendored -------------
describe("the icon map covers the toolbar and nothing else", () => {
  it("every labelled tool has an icon — a new verb cannot ship wearing a blank", () => {
    const missing = TOOLS.map((t) => t.label).filter((l) => !iconFor(l));
    expect(missing).toEqual([]);
  });
  it("every icon named is one that was actually vendored", () => {
    // The map is written by hand; the set is generated. A typo here would render nothing at all,
    // and "nothing at all" looks identical to "this button has no icon yet".
    const unknown = Object.values(TOOL_ICON).filter((n) => !hasIcon(n));
    expect(unknown).toEqual([]);
  });
  it("maps no label that is not a real tool", () => {
    const labels = new Set(TOOLS.map((t) => t.label));
    expect(Object.keys(TOOL_ICON).filter((l) => !labels.has(l))).toEqual([]);
  });
  it("the two walk tools deliberately share one icon", () => {
    // They are the same verb. v0.3.691 established the DUPLICATION is the finding; distinct icons
    // would disguise it.
    expect(iconFor("Walk (drag)")).toBe(iconFor("Walk (locked)"));
  });
  it("an unmapped label returns null rather than an inherited property", () => {
    expect(iconFor("constructor")).toBeNull();
    expect(iconFor("nope")).toBeNull();
  });
});

// --- A2-ICON-RENDER (v0.3.711) — the map is READ ------------------------------------------------
// `TOOL_ICON` shipped complete and tested at v0.3.708 and `toolbarView` never called `iconFor`, so
// "all 27 verbs mapped" was true and nothing on screen changed. Asserting the table is not asserting
// the render; this drives the real installer and looks at what it produced.
describe("the toolbar renders the icons it maps", () => {
  function bar(titles: string[]): HTMLElement {
    const host = document.createElement("div");
    for (const t of titles) {
      const b = document.createElement("button");
      b.className = "tool-btn"; b.title = t; b.textContent = "⚙";
      host.append(b);
    }
    document.body.append(host);
    return host;
  }

  it("puts an <svg>, not an emoji span, on a tool the map covers", () => {
    const spec = TOOLS.find((t) => TOOL_ICON[t.label])!;
    const host = bar([spec.title]);
    installToolbarView(host).update(ctx(true));
    const btn = host.querySelector<HTMLElement>(`[title="${spec.title}"]`)!;
    expect(btn.querySelector("svg.vt-icon")).not.toBeNull();
    expect(btn.querySelector(".vt-glyph")).toBeNull();
    expect(btn.dataset.glyphFallback).toBeUndefined();
    expect(btn.querySelector(".vt-label")?.textContent).toBe(spec.label);
  });

  it("falls back to the glyph and SAYS SO rather than rendering a blank", () => {
    // An unlaid tool has no spec and so no mapped icon. It must still show something, and the
    // fallback must be legible in the DOM — a silent blank is a tool the user cannot find.
    const host = bar(["Not a tool this table describes"]);
    installToolbarView(host).update(ctx(false));
    const btn = host.querySelector<HTMLElement>('[title="Not a tool this table describes"]')!;
    expect(btn.querySelector("svg")).toBeNull();
    expect(btn.querySelector(".vt-glyph")?.textContent).toBe("⚙");
    expect(btn.dataset.glyphFallback).toBe("unmapped");
  });

  it("renders an icon for EVERY laid-out tool, so the fallback is never reached in a real bar", () => {
    const host = bar(TOOLS.map((t) => t.title));
    installToolbarView(host).update(ctx(true));
    const fell = [...host.querySelectorAll<HTMLElement>("[data-glyph-fallback]")]
      .map((b) => b.getAttribute("title"));
    expect(fell).toEqual([]);
    expect(host.querySelectorAll("svg.vt-icon").length).toBe(TOOLS.length);
  });
});
