import { beforeEach, describe, expect, it } from "vitest";

import { DrawingsUI } from "./drawings";

/**
 * CHARACTERIZATION TESTS — written before the markup layer is extracted, not after.
 *
 * `DrawingsUI` is 493 lines and nothing mounted it in any test. R36-VIEWER-SUBAPP slice 6 wants the
 * markup layer reachable from the Sheets canvas, which means lifting it out of this class — and
 * refactoring untested code is how a room quietly loses a feature while every suite stays green. So
 * this pins the behaviour that exists TODAY. If the extraction changes any of it, that is a decision
 * someone has to make on purpose rather than discover later.
 *
 * These assert what the class DOES, including things that are arguably wrong. Where something looks
 * like a defect it is noted rather than corrected, because a characterization test that "fixes"
 * behaviour on the way past stops being a record of what was there.
 */

interface FakeOpts {
  storeys?: Array<{ name: string | null; elevation: number; guid: string }>;
  pins?: unknown[];
  takeoff?: unknown[];
  /** Markups stored under the PRE-GUID key `plan:<storeyName>` — read-only legacy rows. */
  legacyPins?: unknown[];
  legacyTakeoff?: unknown[];
  failStoreys?: boolean;
  failMarkup?: boolean;
}

function mount(opts: FakeOpts = {}) {
  const calls: string[] = [];
  let streamStatus: ((s: string, why?: string) => void) | null = null;
  const host = document.createElement("div");
  document.body.appendChild(host);

  // `show()` fetches the sheet SVG with the GLOBAL fetch, and on failure it returns early WITHOUT
  // loading pins — so without a stub every markup assertion below would pass vacuously against an
  // empty pin layer. Serving a real <svg> is what makes the rest of this file mean anything.
  globalThis.fetch = (async () => ({
    ok: true,
    status: 200,
    text: async () => '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"></svg>',
  })) as unknown as typeof fetch;

  const api = {
    drawingStoreys: async (pid: string) => {
      calls.push(`storeys:${pid}`);
      if (opts.failStoreys) throw new Error("no source IFC");
      return opts.storeys ?? [{ name: "L1", elevation: 0, guid: "g1" }];
    },
    // KEY-AWARE on purpose. This stub used to ignore `id` and serve the same rows for every key,
    // which modelled an API that does not exist: `sheet_id` is a column, so two keys never return
    // the same row. That mattered the moment plans gained a legacy key — the layer reads
    // `plan:<guid>` and `plan:<name>`, and a key-blind stub reported every pin twice, which looks
    // exactly like a merge bug in code that is correct.
    drawingMarkup: async (_pid: string, id: string) => {
      calls.push(`markup:${id}`);
      if (opts.failMarkup) throw new Error("markup down");
      const base = id.replace(/#pdf$/, "");
      const storeys = opts.storeys ?? [{ name: "L1", elevation: 0, guid: "g1" }];
      // The pre-GUID form for this project's storeys. Derived from the same list the sheet builder
      // uses, so renaming the fixture cannot make the two disagree.
      if (storeys.some((st) => base === `plan:${st.name}`)) {
        return (id.endsWith("#pdf") ? opts.legacyTakeoff : opts.legacyPins) ?? [];
      }
      return (id.endsWith("#pdf") ? opts.takeoff : opts.pins) ?? [];
    },
    // THE THIRD ARGUMENT IS CAPTURED, not ignored. The old stub dropped it, which is exactly how a
    // subscriber that passes no `onStatus` goes unnoticed: the fake accepts either shape.
    markupStream: (_pid: string, _cb: () => void,
                   onStatus?: (s: string, why?: string) => void) => {
      calls.push("stream");
      streamStatus = onStatus ?? null;
      return {
        get connected() { return true; },
        close() { calls.push("stream:close"); },
        retry() { calls.push("stream:retry"); },
      };
    },
    url: (p: string) => p,
    authHeaders: () => ({}),
  };

  const ui = new DrawingsUI(host, {
    api: api as never,
    projectId: () => "p1",
    setStatus: (m: string) => calls.push(`status:${m}`),
  } as never);
  return { ui, host, calls, api, status: () => streamStatus };
}

/** Let the open()/show() promise chains settle. */
const settle = async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); };

beforeEach(() => { document.body.innerHTML = ""; });

describe("the workspace it builds", () => {
  it("creates the side register, the toolbar, and the stage the markup layer lives on", async () => {
    const { ui, host } = mount();
    await ui.open();
    await settle();
    expect(host.classList.contains("dwg-wrap")).toBe(true);
    expect(host.querySelector(".dwg-side")).toBeTruthy();
    expect(host.querySelector("#dwg-toolbar")).toBeTruthy();
    expect(host.querySelector(".dwg-viewport")).toBeTruthy();
    expect(host.querySelector(".dwg-stage")).toBeTruthy();
    // The two the markup layer owns — an extraction has to keep both, or pins have nowhere to go.
    expect(host.querySelector(".dwg-svg"), "the SVG host pins are positioned against").toBeTruthy();
    expect(host.querySelector(".dwg-pins"), "the pin layer itself").toBeTruthy();
  });

  it("is idempotent — opening twice does not rebuild the DOM", async () => {
    const { ui, host } = mount();
    await ui.open();
    await settle();
    const stage = host.querySelector(".dwg-stage");
    await ui.open();
    await settle();
    expect(host.querySelector(".dwg-stage"), "same node, not a replacement").toBe(stage);
  });
});

describe("the sheet register", () => {
  it("lists a plan per storey, four elevations, a section and a composed sheet", async () => {
    const { ui, host } = mount({
      storeys: [{ name: "L1", elevation: 0, guid: "a" }, { name: "L2", elevation: 3.5, guid: "b" }],
    });
    await ui.open();
    await settle();
    const labels = [...host.querySelectorAll(".dwg-item")].map((b) => b.textContent);
    expect(labels).toContain("Plan — L1");
    expect(labels).toContain("Plan — L2");
    expect(labels.filter((l) => l?.startsWith("Elevation"))).toHaveLength(4);
    expect(labels.some((l) => l?.startsWith("Section"))).toBe(true);
    expect(labels.some((l) => l?.includes("S-101"))).toBe(true);
  });

  it("still offers elevations and the section when there is no source IFC", async () => {
    const { ui, host } = mount({ failStoreys: true });
    await ui.open();
    await settle();
    expect(host.textContent).toContain("No storeys");
    expect([...host.querySelectorAll(".dwg-item")].length).toBeGreaterThan(0);
  });

  it("auto-opens the first sheet and marks it active", async () => {
    const { ui, host } = mount();
    await ui.open();
    await settle();
    expect(host.querySelector(".dwg-item.active")).toBeTruthy();
  });
});

describe("the markup layer, as it behaves today", () => {
  it("the SVG really rendered — else every pin assertion below is vacuous", async () => {
    const { ui, host } = mount();
    await ui.open();
    await settle();
    expect(host.querySelector(".dwg-svg svg"), "show() reached the point where pins are loaded").toBeTruthy();
  });

  it("fetches BOTH the sheet's pins and the PDF editor's takeoff markups", async () => {
    const { ui, calls } = mount();
    await ui.open();
    await settle();
    const markupCalls = calls.filter((c) => c.startsWith("markup:"));
    expect(markupCalls.some((c) => !c.endsWith("#pdf")), "the sheet's own pins").toBe(true);
    expect(markupCalls.some((c) => c.endsWith("#pdf")), "the takeoff markups").toBe(true);
  });

  // The `#pdf` suffix is the coupling that makes this a LAYER rather than a list: two sources, one
  // surface. An extraction that kept only the first would lose takeoff markups silently.
  it("keeps only takeoff markups that carry a normalized anchor", async () => {
    const { ui, host } = mount({
      pins: [{ id: "p1", data: {} }],
      takeoff: [{ id: "t1", kind: "area", data: { nx: 0.5, ny: 0.5 } },
                { id: "t2", kind: "area", data: {} }],
    });
    await ui.open();
    await settle();
    // t2 has no `nx`, so it cannot be placed and is dropped.
    expect(host.querySelectorAll(".dwg-pin")).toHaveLength(2);
  });

  // R36 premise-check, 2026-08-26. Slice 6 shipped keyed on the storey NAME. The entry itself had
  // specified the GlobalId ("levels can be renamed here, and every markup on that level would orphan
  // silently"), the project's first non-negotiable says the same, and `drawingStoreys` had been
  // serving `guid` beside `name` all along. The key was the one thing that did not follow.
  it("keys a storey plan's markups on the storey GUID, never its renameable name", async () => {
    const { ui, calls } = mount({ storeys: [{ name: "Level 1", elevation: 0, guid: "3aB7xQ" }] });
    await ui.open();
    await settle();
    const keys = calls.filter((c) => c.startsWith("markup:") && !c.endsWith("#pdf"));
    expect(keys, "the GUID is the key new markups are written under").toContain("markup:plan:3aB7xQ");
  });

  it("still reads markups stored under the pre-GUID name key, so none disappear", async () => {
    const { ui, host, calls } = mount({
      storeys: [{ name: "Level 1", elevation: 0, guid: "3aB7xQ" }],
      pins: [{ id: "new", data: {} }],
      legacyPins: [{ id: "old", data: {} }],
    });
    await ui.open();
    await settle();
    expect(calls.filter((c) => c.startsWith("markup:"))).toContain("markup:plan:Level 1");
    // Both sources on one surface. Switching the key WITHOUT this read would have "fixed" the
    // rename bug by hiding every markup already stored, which is the same data loss by other means.
    expect(host.querySelectorAll(".dwg-pin"), "the new GUID-keyed pin and the legacy one").toHaveLength(2);
  });

  // The inverse. Reading two keys is only correct if it does not double-count: a stub that served
  // every key the same rows reported 4 pins for 2 and looked exactly like this feature misbehaving.
  it("does not double-count when the legacy key holds nothing", async () => {
    const { ui, host } = mount({
      storeys: [{ name: "Level 1", elevation: 0, guid: "3aB7xQ" }],
      pins: [{ id: "p1", data: {} }, { id: "p2", data: {} }],
    });
    await ui.open();
    await settle();
    expect(host.querySelectorAll(".dwg-pin")).toHaveLength(2);
  });

  it("renders a pin per markup, and marks the ones linked to a topic", async () => {
    const { ui, host } = mount({
      pins: [{ id: "p1", data: {}, topic_id: "t-1" }, { id: "p2", data: {} }],
    });
    await ui.open();
    await settle();
    const pins = [...host.querySelectorAll(".dwg-pin")];
    expect(pins).toHaveLength(2);
    expect(pins.filter((p) => p.classList.contains("linked"))).toHaveLength(1);
  });

  it("marks a markup carried from an earlier revision", async () => {
    const { ui, host } = mount({ pins: [{ id: "p1", data: { carried_from: "rev-1" } }] });
    await ui.open();
    await settle();
    expect(host.querySelector(".dwg-pin.carried")).toBeTruthy();
  });

  // Failure is swallowed and the sheet still renders. Worth pinning because the obvious "improvement"
  // during an extraction is to surface the error — which would put an error banner over a drawing
  // whose markups merely have not loaded.
  it("a markup fetch failure leaves the sheet usable and shows no pins", async () => {
    const { ui, host } = mount({ failMarkup: true });
    await ui.open();
    await settle();
    expect(host.querySelector(".dwg-stage")).toBeTruthy();
    expect(host.querySelectorAll(".dwg-pin")).toHaveLength(0);
  });

  it("subscribes to the live markup stream exactly once across repeated opens", async () => {
    const { ui, calls } = mount();
    await ui.open();
    await settle();
    await ui.open();
    await settle();
    expect(calls.filter((c) => c === "stream")).toHaveLength(1);
  });
});

describe("the markup toggle", () => {
  it("flips the viewport into marking mode and back", async () => {
    const { ui, host } = mount();
    await ui.open();
    await settle();
    const btn = [...host.querySelectorAll("button")].find((b) => b.textContent?.includes("Markup"));
    expect(btn, "the Markup button is on the toolbar").toBeTruthy();
    const viewport = host.querySelector(".dwg-viewport")!;
    expect(viewport.classList.contains("marking")).toBe(false);
    btn!.click();
    expect(viewport.classList.contains("marking")).toBe(true);
    const again = [...host.querySelectorAll("button")].find((b) => b.textContent?.includes("Markup"));
    again!.click();
    expect(viewport.classList.contains("marking")).toBe(false);
  });
});

describe("live co-markup says so when it stops — R24-FIELD-MODE ⑦", () => {
  // This subscriber passed no `onStatus`, so `HttpCore.liveStream`'s refusal classification was
  // disabled for it: a stream the server will never serve this client again retried for ever and
  // the pins simply stopped updating. Nothing looked wrong, which is the whole problem — two people
  // mark up the same sheet believing they can see each other's work. *A stale drawing is
  // indistinguishable from a quiet one, and only one of them is safe.*
  it("THE DEFECT: it asks to be told at all", async () => {
    const { ui, status } = mount();
    await ui.open();
    await settle();
    expect(status(), "a subscriber that passes no onStatus cannot be told it was refused")
      .not.toBeNull();
  });

  it("a refusal is shown in the toolbar, with the server's reason as visible text", async () => {
    const { ui, host, status } = mount();
    await ui.open();
    await settle();
    status()!("refused", "you were removed from this project");
    const note = host.querySelector("#dwg-live-refused");
    expect(note, "the notice mounts").toBeTruthy();
    expect(note!.textContent).toContain("you were removed from this project");
    // The consequence, not the transport — "the SSE stream closed" is not actionable.
    expect(note!.textContent).toContain("markups will not appear");
    // No hover-only reason: this is read on a tablet in the field.
    expect(note!.querySelector("[title]"), "nothing hides the reason behind a tooltip").toBeNull();
  });

  it("the retry control is a real button whose visible label is its accessible name", async () => {
    const { ui, host, status } = mount();
    await ui.open();
    await settle();
    status()!("refused", "gone");
    const b = host.querySelector<HTMLButtonElement>("#dwg-live-refused button")!;
    expect(b.tagName).toBe("BUTTON");
    expect(b.type).toBe("button");
    expect(b.textContent).toBe("Try again");
    expect(b.getAttribute("aria-label"), "no second name to drift from the first").toBeNull();
    expect(b.getAttribute("title")).toBeNull();
  });

  it("...and clicking it actually resumes the stream", async () => {
    // The lesson slice ⑤'s review paid for: its first escape hatch cleared the mark and
    // re-rendered without sending, and the test did not notice because the test did the sending.
    const { ui, host, calls, status } = mount();
    await ui.open();
    await settle();
    status()!("refused", "gone");
    host.querySelector<HTMLButtonElement>("#dwg-live-refused button")!.click();
    expect(calls, "retry() reaches the stream handle").toContain("stream:retry");
    expect(host.querySelector("#dwg-live-refused"), "and the notice clears").toBeNull();
  });

  it("an EMPTY reason still shows a refusal — empty is not absent", async () => {
    const { ui, host, status } = mount();
    await ui.open();
    await settle();
    status()!("refused", "");
    const note = host.querySelector("#dwg-live-refused");
    expect(note, "a refusal with no stated reason is still a refusal").toBeTruthy();
    expect(note!.textContent).toContain("refused by the server");
    expect(note!.textContent, "and never a dangling dash").not.toMatch(/—\s*\./);
  });

  it("a transient reconnect is NOT shown — a retry the user can see is not the problem", async () => {
    const { ui, host, status } = mount();
    await ui.open();
    await settle();
    status()!("reconnecting");
    expect(host.querySelector("#dwg-live-refused")).toBeNull();
  });

  it("a recovered stream clears a notice that was up", async () => {
    const { ui, host, status } = mount();
    await ui.open();
    await settle();
    status()!("refused", "gone");
    expect(host.querySelector("#dwg-live-refused")).toBeTruthy();
    status()!("connected");
    expect(host.querySelector("#dwg-live-refused"), "it must not outlive the refusal").toBeNull();
  });

  it("two refusals in a row leave ONE notice, not two", async () => {
    const { ui, host, status } = mount();
    await ui.open();
    await settle();
    status()!("refused", "gone");
    status()!("refused", "still gone");
    expect(host.querySelectorAll("#dwg-live-refused").length).toBe(1);
    expect(host.querySelector("#dwg-live-refused")!.textContent).toContain("still gone");
  });
});

describe("the refusal notice is STATE, not a one-shot paint — round 6", () => {
  // Review of slice ⑦ found this branch's own defect reintroduced inside the fix for it. The notice
  // lives in `#dwg-toolbar`, and `buildToolbar()` opens with `bar.innerHTML = ""` — which runs on
  // EVERY sheet selection. The Paper space button rewrites the same bar outright. So the first
  // click after a refusal erased the only thing saying live markup had stopped, and the screen went
  // back to looking healthy while the stream was still refused.
  const twoSheets = {
    storeys: [
      { name: "L1", elevation: 0, guid: "g1" },
      { name: "L2", elevation: 3000, guid: "g2" },
    ],
  };

  it("THE DEFECT: selecting another sheet must not erase an active refusal", async () => {
    const { ui, host, status } = mount(twoSheets);
    await ui.open();
    await settle();
    status()!("refused", "you were removed from this project");
    expect(host.querySelector("#dwg-live-refused"), "it is up").toBeTruthy();

    const items = host.querySelectorAll<HTMLButtonElement>(".dwg-item");
    expect(items.length, "two sheets, so a second one to click").toBeGreaterThan(1);
    items[1]!.click();                       // rebuilds the toolbar via buildToolbar()
    await settle();

    const note = host.querySelector("#dwg-live-refused");
    expect(note, "the stream is still refused, so the notice must still be there").toBeTruthy();
    expect(note!.textContent, "with its reason intact")
      .toContain("you were removed from this project");
    expect(note!.querySelector("button"), "and still answerable").toBeTruthy();
  });

  it("...and the Paper space button's toolbar rewrite must not erase it either", async () => {
    const { ui, host, status } = mount(twoSheets);
    await ui.open();
    await settle();
    status()!("refused", "gone");
    const paper = [...host.querySelectorAll<HTMLButtonElement>("button")]
      .find((b) => /Paper space/i.test(b.textContent ?? ""))!;
    paper.click();
    await settle();
    expect(host.querySelector("#dwg-live-refused"),
           "a second wipe, same consequence").toBeTruthy();
  });

  it("a rebuild does not DUPLICATE the notice either", async () => {
    const { ui, host, status } = mount(twoSheets);
    await ui.open();
    await settle();
    status()!("refused", "gone");
    const items = host.querySelectorAll<HTMLButtonElement>(".dwg-item");
    items[1]!.click();
    await settle();
    items[0]!.click();
    await settle();
    expect(host.querySelectorAll("#dwg-live-refused").length).toBe(1);
  });

  it("retry clears the STATE, so a later rebuild does not resurrect the notice", async () => {
    // Storing the refusal is what makes a rebuild repaint it — which means forgetting to clear the
    // store on retry would bring back a notice the user had dismissed by acting on it.
    const { ui, host, calls, status } = mount(twoSheets);
    await ui.open();
    await settle();
    status()!("refused", "gone");
    host.querySelector<HTMLButtonElement>("#dwg-live-refused button")!.click();
    expect(calls).toContain("stream:retry");
    const items = host.querySelectorAll<HTMLButtonElement>(".dwg-item");
    items[1]!.click();
    await settle();
    expect(host.querySelector("#dwg-live-refused"),
           "the refusal was answered; a redraw must not undo that").toBeNull();
  });

  it("recovery clears the state too", async () => {
    const { ui, host, status } = mount(twoSheets);
    await ui.open();
    await settle();
    status()!("refused", "gone");
    status()!("connected");
    const items = host.querySelectorAll<HTMLButtonElement>(".dwg-item");
    items[1]!.click();
    await settle();
    expect(host.querySelector("#dwg-live-refused")).toBeNull();
  });

  it("the ✎ Markup toggle rebuilds the toolbar too, and must not erase it", async () => {
    // Review named FOUR callers of `buildToolbar()`: `show()`, this toggle, ⧉ Compare, and the
    // `aec:model-published` listener (which goes through `show()`). The repaint sits at the END of
    // `buildToolbar`, so one test of the mechanism covers all four — but this toggle calls it
    // INLINE rather than through `show()`, and that the call graph funnels here is a fact I
    // established with grep. *A grep is a source-level check*, so one of the four is pinned
    // behaviourally: if somebody later makes this toggle rewrite the bar directly, this reds.
    const { ui, host, status } = mount(twoSheets);
    await ui.open();
    await settle();
    status()!("refused", "removed from project");
    [...host.querySelectorAll<HTMLButtonElement>("button")]
      .find((b) => /Markup$/i.test((b.textContent ?? "").trim()))!.click();
    await settle();
    const note = host.querySelector("#dwg-live-refused");
    expect(note, "toggling markup must not hide a live refusal").toBeTruthy();
    expect(note!.textContent).toContain("removed from project");
  });

  it("a refusal with an EMPTY reason survives a rebuild as well", async () => {
    // `liveRefused` is `string | null` precisely so "" ("refused, no reason given") is not confused
    // with null ("not refused") — a boolean or a bare string would lose the distinction and this
    // notice would vanish on the next redraw.
    const { ui, host, status } = mount(twoSheets);
    await ui.open();
    await settle();
    status()!("refused", "");
    const items = host.querySelectorAll<HTMLButtonElement>(".dwg-item");
    items[1]!.click();
    await settle();
    const note = host.querySelector("#dwg-live-refused");
    expect(note).toBeTruthy();
    expect(note!.textContent).toContain("refused by the server");
  });
});
