/**
 * RAIL-TOOLBOX — **nothing is forgotten.**
 *
 * The move from a floating bar to the rail is a re-parenting pass over 28 tools created in five
 * different modules. The user's words when asking for it: *"dont forget any because its too hard"* —
 * and that is exactly right, because a dropped tool is invisible. It does not error, it does not
 * warn; a button that was never appended looks the same as one that was deliberately removed, and
 * the next person to notice is a user who needed it.
 *
 * So this asserts the property directly rather than trusting the implementation: **every tool in the
 * layout table lands in a named group, and the number that come out equals the number that went in.**
 *
 * The counting test is the one that catches the whole class. `place()` puts a tool in its group or,
 * failing that, in a visible tagged spill — so a tool can only be "lost" by not being counted at
 * all, and a total that matches TOOLS.length proves none was.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { createRailToolbox } from "./railToolbox";
import { GROUP_LABELS, TOOLS } from "./toolbarLayout";

function btn(title: string): HTMLButtonElement {
  const b = document.createElement("button");
  b.textContent = "◻";           // the glyph the real toolBtn sets
  b.title = title;
  return b;
}

/** Install every tool the layout table knows about, the way `toolBtn` does. */
function fullToolbox() {
  const tb = createRailToolbox();
  for (const t of TOOLS) tb.place(btn(t.title), t.title);
  return tb;
}

/**
 * Every host the toolbox owns, mounted. RAIL-SPLIT sends the five groups to THREE different rail
 * panels, so "nothing was forgotten" now has to be counted across all of them — a per-panel count
 * would pass while a whole group went missing.
 */
function mountAll(tb: ReturnType<typeof createRailToolbox>, host: HTMLElement): HTMLElement {
  for (const k of tb.hostKeys()) host.appendChild(tb.hostFor(k)!);
  return host;
}

describe("every tool reaches the rail", () => {
  let host: HTMLElement;
  beforeEach(() => {
    host = document.createElement("div");
    document.body.appendChild(host);
  });

  it("the table is big enough that this test is measuring something", () => {
    // Vacuous-pass guard: if TOOLS ever comes back empty, every assertion below passes trivially.
    expect(TOOLS.length).toBeGreaterThan(20);
  });

  it("places EVERY tool — the count out equals the count in", () => {
    const tb = fullToolbox();
    mountAll(tb, host);
    const placed = host.querySelectorAll("button").length;
    expect(placed, "a tool went in and did not come out").toBe(TOOLS.length);
  });

  it("none lands in the unlaid spill — every tool has a real group", () => {
    const tb = fullToolbox();
    mountAll(tb, host);
    const spilled = [...host.querySelectorAll(".rail-toolbox-unlaid button")]
      .map((b) => b.getAttribute("title"));
    expect(spilled, "tools with no group in the layout table").toEqual([]);
    expect(tb.unlaid(), "titles the layout table does not describe").toEqual([]);
  });

  it("every group named in the table gets a container — a new group cannot be forgotten", () => {
    const tb = fullToolbox();
    mountAll(tb, host);
    const used = new Set(TOOLS.map((t) => t.group));
    for (const g of used) {
      expect(host.querySelector(`[data-group="${g}"]`), `no container rendered for group "${g}"`)
        .not.toBeNull();
    }
    // and the containers carry the human heading, not the raw id
    for (const [id, label] of GROUP_LABELS) {
      if (!used.has(id)) continue;
      const head = host.querySelector(`[data-group="${id}"] .rail-toolgroup-head`);
      expect(head?.textContent, `group "${id}" heading`).toBe(label);
    }
  });

  it("each tool keeps its title, handler and capability gate through the move", () => {
    // Re-parenting must not strip identity: the title is the key every gate and the pinned-position
    // test uses, and data-cap drives the capability dimming.
    const tb = createRailToolbox();
    const b = btn(TOOLS[0]!.title);
    b.dataset.cap = "edit";
    let clicked = 0;
    b.onclick = () => { clicked += 1; };
    tb.place(b, TOOLS[0]!.title);
    mountAll(tb, host);
    expect(b.getAttribute("title")).toBe(TOOLS[0]!.title);
    expect(b.dataset.cap).toBe("edit");
    b.click();
    expect(clicked, "the handler did not survive re-parenting").toBe(1);
  });

  it("labels the button — a glyph without a word is a puzzle", () => {
    const tb = createRailToolbox();
    const spec = TOOLS.find((t) => t.label === "Measure")!;
    const b = btn(spec.title);
    tb.place(b, spec.title);
    mountAll(tb, host);
    expect(b.dataset.label).toBe("Measure");
  });

  it("the label SURVIVES the owning module re-rendering its own button", () => {
    // Found by driving the real app: the presence tool rewrites its button to show who is viewing
    // (title gains "— no one else viewing", content becomes a live count). The first implementation
    // injected label spans INTO the button, so that re-render wiped them and left a bare glyph.
    // These buttons belong to the modules that made them — the toolbox decorates, it does not own
    // their contents, so the label lives in an attribute that innerHTML cannot touch.
    const tb = createRailToolbox();
    const spec = TOOLS.find((t) => t.label === "Presence")!;
    const b = btn(spec.title);
    tb.place(b, spec.title);
    mountAll(tb, host);

    b.innerHTML = "👥 3";                                  // the owner re-renders, as it really does
    b.title = `${spec.title} — 3 people viewing`;
    expect(b.dataset.label, "the label did not survive the owner's re-render").toBe("Presence");
    expect(b.classList.contains("rail-tool"), "styling must survive too").toBe(true);
  });

  it("an UNDESCRIBED tool is still shown, tagged — never dropped", () => {
    // The honesty valve. A tool the table forgot must appear anyway, because vanishing silently is
    // the failure this whole file exists to prevent.
    const tb = createRailToolbox();
    tb.place(btn("Some brand new tool nobody described"), "Some brand new tool nobody described");
    mountAll(tb, host);
    expect(host.querySelectorAll("button").length).toBe(1);
    expect(host.querySelector("button")?.dataset.unlaid).toBe("1");
    expect(tb.unlaid().length).toBe(1);
  });
});

describe("context dims, it never hides or moves", () => {
  it("selection verbs go quiet with nothing selected, and stay in place", () => {
    const tb = fullToolbox();
    const host = mountAll(tb, document.createElement("div"));
    const move = [...host.querySelectorAll("button")]
      .find((b) => (b.getAttribute("title") || "").startsWith("Move selected"))!;
    const parentBefore = move.parentElement;

    tb.update({ selection: false, canEdit: true });
    expect(move.classList.contains("rail-tool-off")).toBe(true);
    expect(move.getAttribute("aria-disabled")).toBe("true");
    expect(move.dataset.why).toBeTruthy();          // says WHY it is quiet
    expect(move.parentElement, "a dimmed tool must not move").toBe(parentBefore);

    tb.update({ selection: true, canEdit: true });
    expect(move.classList.contains("rail-tool-off")).toBe(false);
    expect(move.dataset.why).toBeUndefined();
    expect(move.parentElement, "an enabled tool must not move either").toBe(parentBefore);
  });

  it("tools that never needed a selection are never dimmed", () => {
    const tb = fullToolbox();
    const host = mountAll(tb, document.createElement("div"));
    tb.update({ selection: false, canEdit: true });
    const measure = [...host.querySelectorAll("button")]
      .find((b) => (b.getAttribute("title") || "").startsWith("Measure distance"))!;
    expect(measure.classList.contains("rail-tool-off")).toBe(false);
  });
});
