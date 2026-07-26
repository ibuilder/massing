import { describe, expect, it } from "vitest";
import { GROUP_LABELS, MAX_PRIMARY, TOOLS, describe as describeTool, primaryTitles, specFor, unlaidTitles } from "./toolbarLayout";
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
      expect(b.querySelector(".vt-glyph")?.textContent, b.title).toBe("◆");
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
