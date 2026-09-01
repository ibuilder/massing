import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { MIN_CHARS, auditRooms, auditWorkspaces, compareRuns, isDisplayed, judgePane, judgeRoom, realText, summarise } from "./liveAudit";

/**
 * R26-V-LIVE. The audit that started R26 was a click-through, and click-throughs do not survive —
 * the next person redoes the whole thing, and nobody can tell afterwards whether a pane was blank or
 * merely unmeasured.
 *
 * What is tested here is not "does the app render"; it is **does the auditor lie**. Every trap below
 * produced a false "blank" in a real DOM audit of this app, and all three fail in the same direction:
 * they invent defects, which then get "fixed".
 */
function el(html: string, displayed = true): HTMLElement {
  const d = document.createElement("div");
  d.innerHTML = html;
  document.body.appendChild(d);
  if (!displayed) d.style.display = "none";
  return d;
}

beforeEach(() => { document.body.innerHTML = ""; });

describe("trap 1 — a node that is not laid out is not a blank node", () => {
  it("reads text without depending on layout", () => {
    const hidden = el("<p>Real content that a reader would see on screen.</p>", false);
    // innerText would be "" here; textContent is not layout-dependent
    expect(realText(hidden).length).toBeGreaterThan(MIN_CHARS);
  });

  it("reports a non-displayed pane as hidden, never as empty", () => {
    const hidden = el("<p>plenty of words in here to clear the threshold easily</p>", false);
    const r = judgePane("x", hidden, hidden);
    expect(r.verdict).toBe("hidden");
    expect(r.verdict).not.toBe("empty");
    expect(r.detail).toMatch(/not the same as empty/);
  });

  it("ignores script and style text — it is text, but not to a reader", () => {
    const d = el("<style>.a{color:red;font-size:12px;padding:4px 8px;margin:0}</style><p>hi</p>");
    expect(realText(d)).toBe("hi");
  });

  it("sees a display:none ANCESTOR — a child of a hidden parent computes its own display normally", () => {
    const outer = el(`<div><section><p>${"word ".repeat(20)}</p></section></div>`, false);
    const inner = outer.querySelector<HTMLElement>("section")!;
    expect(isDisplayed(inner)).toBe(false);
    expect(judgePane("x", inner, inner).verdict).toBe("hidden");
  });

  it("does NOT call a visible fixed-position element hidden", () => {
    // The first draft tested `offsetParent`, which is null for position:fixed — so the floating
    // toolbar and every modal would have been reported as hidden by the auditor whose whole job is
    // not producing false negatives.
    const d = el(`<div style="position:fixed"><button>Save</button></div>`);
    expect(isDisplayed(d)).toBe(true);
    expect(judgePane("x", d, d).verdict).toBe("ok");
  });

  it("respects the [hidden] attribute as well as the style", () => {
    const d = el(`<div><button>Save</button></div>`);
    d.hidden = true;
    expect(isDisplayed(d)).toBe(false);
  });
});

describe("trap 3 — the shell is not the content", () => {
  it("judges the content pane, not the wrapper that also holds the rail", () => {
    const shell = el(`<div class="portal-shell">
        <nav class="portal-nav"><button>Dashboard</button><button>Budget</button></nav>
        <div class="portal-content"></div>
      </div>`);
    const content = shell.querySelector<HTMLElement>(".portal-content")!;
    // the shell has two controls and plenty of text; the CONTENT pane has neither
    expect(judgePane("p", shell, shell).verdict).toBe("ok");
    expect(judgePane("p", shell, content).verdict).toBe("empty");
  });

  it("says `unknown` when the content element is missing, rather than guessing", () => {
    const shell = el(`<div><nav>rail</nav></div>`);
    const r = judgePane("p", shell, null);
    expect(r.verdict).toBe("unknown");
    expect(r.detail).toMatch(/structure differs, or it is broken/);
  });
});

describe("a pane counts as populated on text OR controls", () => {
  it("passes a pane of buttons with almost no prose", () => {
    const d = el(`<div><button>Go</button><button>Stop</button></div>`);
    expect(judgePane("p", d, d).verdict).toBe("ok");
  });

  it("passes a pane of prose with no controls", () => {
    const d = el(`<div>${"word ".repeat(20)}</div>`);
    expect(judgePane("p", d, d).verdict).toBe("ok");
  });

  it("fails a spinner — displayed, but nothing in it yet", () => {
    const d = el(`<div><span>…</span></div>`);
    const r = judgePane("p", d, d);
    expect(r.verdict).toBe("empty");
    expect(r.chars).toBeLessThan(MIN_CHARS);
  });

  it("reports a missing element as missing, not as empty", () => {
    expect(judgePane("p", null).verdict).toBe("missing");
  });
});

describe("the summary never launders an unjudged pane into a pass", () => {
  it("keeps hidden and unknown out of BOTH the ok count and the problems", () => {
    const s = summarise([
      { id: "a", verdict: "ok", chars: 99, controls: 2, detail: "" },
      { id: "b", verdict: "empty", chars: 0, controls: 0, detail: "" },
      { id: "c", verdict: "hidden", chars: 0, controls: 0, detail: "" },
      { id: "d", verdict: "unknown", chars: 0, controls: 0, detail: "" },
      { id: "e", verdict: "missing", chars: 0, controls: 0, detail: "" },
    ]);
    expect(s.ok).toBe(1);
    expect(s.problems.map((p) => p.id)).toEqual(["b", "e"]);
    expect(s.unknown.map((p) => p.id)).toEqual(["c", "d"]);
    // and the report says so, so a reader does not have to infer it
    expect(s.note).toMatch(/NOT passes and NOT failures/);
  });
});

describe("trap 4 — a pane that is still booting is not an empty pane", () => {
  it("re-looks before calling anything empty, and marks it slow rather than broken", async () => {
    // Found by running the auditor against the real app: Model, Design and Developer all reported
    // blank on the first pass and were fully populated seconds later. An auditor that cannot tell
    // "nothing here" from "not yet" manufactures the exact false blanks the other guards prevent.
    el(`<div id="workspaces"><button>Slow</button></div>
        <section class="workspace active"><div class="portal-content"></div></section>`);
    // The injected clock IS the mount: the pane fills during the SECOND wait, i.e. inside the retry
    // window. Deterministic, unlike racing two real timers.
    let waits = 0;
    const wait = () => {
      if (++waits === 2) {
        document.querySelector(".portal-content")!.textContent =
          "Content that arrived a moment after the first measurement was taken.";
      }
      return Promise.resolve();
    };
    const report = await auditWorkspaces({ settleMs: 0, wait });
    expect(report.problems).toEqual([]);
    expect(report.ok).toBe(1);
    expect(report.panes[0]!.detail).toMatch(/filled on retry/);
  });

  it("still reports a genuinely empty pane as empty after the retry", async () => {
    el(`<div id="workspaces"><button>Dead</button></div>
        <section class="workspace active"><div class="portal-content"></div></section>`);
    const report = await auditWorkspaces({ settleMs: 0, wait: () => Promise.resolve() });
    expect(report.problems.map((p) => p.id)).toEqual(["workspace:Dead"]);
    expect(report.ok).toBe(0);
  });

  it("counts `slow` as a pass — the pane rendered, it just needed a second look", () => {
    const s = summarise([{ id: "a", verdict: "slow", chars: 99, controls: 1, detail: "" }]);
    expect(s.ok).toBe(1);
    expect(s.problems).toEqual([]);
    expect(s.unknown).toEqual([]);
  });
});

describe("trap 2 — a click rebuilds the nav, detaching anything you held", () => {
  it("re-finds each tab by name instead of reusing a captured node", async () => {
    // This mirrors the real shell: every tab click re-creates the tab strip. An auditor that held a
    // reference from before the click would be clicking a detached node — which silently does
    // nothing, so every workspace after the first would report blank.
    const clicked: string[] = [];
    const build = () => {
      const bar = document.getElementById("workspaces")!;
      bar.replaceChildren();
      for (const n of ["Model", "Cost", "Schedule"]) {
        const b = document.createElement("button");
        b.textContent = n;
        b.onclick = () => {
          clicked.push(n);
          build();                                   // the detaching rebuild
          const ws = document.querySelector<HTMLElement>(".workspace.active")!;
          ws.querySelector(".portal-content")!.textContent = `${n} content, long enough to pass the bar.`;
        };
        bar.appendChild(b);
      }
    };
    el(`<div id="workspaces"></div>
        <section class="workspace active"><div class="portal-content"></div></section>`);
    build();

    const report = await auditWorkspaces({ settleMs: 0, wait: () => Promise.resolve() });
    expect(clicked).toEqual(["Model", "Cost", "Schedule"]);   // every tab was really clicked
    expect(report.problems).toEqual([]);
    expect(report.ok).toBe(3);
  });
});

// --- R26 RELEASE GATE: the audit had never been pointed at the shell it was built to verify -------
// This file shipped with zero references to the spine, so its "all 7 workspaces ok, 0 problems"
// belonged to the CLASSIC shell — and was read as evidence for the redesign it never touched. An
// audit that does not state its configuration produces results that migrate to the wrong claim.
describe("a report says what it could NOT judge, rather than scoring it", () => {
  // This block used to assert the report named which shell it measured — a field added because its
  // absence had let a classic-shell result be read as evidence for the spine. With one shell left
  // (v0.3.779) that field is a constant, and a constant is not a disclosure. What still matters, and
  // is what the field was really protecting, is that unjudgeable panes stay out of the pass count.
  it("hidden and unknown panes are neither passes nor problems", () => {
    const s = summarise([
      { id: "a", verdict: "ok", chars: 99, controls: 1, detail: "" },
      { id: "b", verdict: "hidden", chars: 0, controls: 0, detail: "" },
      { id: "c", verdict: "unknown", chars: 0, controls: 0, detail: "" },
    ]);
    expect(s.ok).toBe(1);
    expect(s.problems).toEqual([]);
    expect(s.unknown.map((p) => p.id)).toEqual(["b", "c"]);
  });
});

describe("judgeRoom — a room is judged by what it contains", () => {
  const room = (html: string) => {
    const d = document.createElement("details");
    d.className = "pnav-room";
    d.innerHTML = html;
    document.body.appendChild(d);
    return d;
  };
  afterEach(() => { document.body.innerHTML = ""; });

  it("a rendered room with no destinations is EMPTY, not ok", () => {
    // Worse than an absent room: it looks like a place to go.
    const r = judgeRoom(room("<summary>Model</summary>"), "model");
    expect(r.verdict).toBe("empty");
    expect(r.detail).toContain("leads nowhere");
  });
  it("the room's own summary is not miscounted as a destination", () => {
    const r = judgeRoom(room("<summary>Model</summary><button>Viewer</button>"), "model");
    expect(r.verdict).toBe("ok");
    expect(r.destinations).toBe(1);
  });
  it("a room the rail never rendered is MISSING, never empty", () => {
    expect(judgeRoom(null, "cost").verdict).toBe("missing");
  });
  it("a collapsed room is reported but NOT scored — that is a user's preference, not a defect", () => {
    const d = room("<summary>Cost</summary><button>Budget</button>");
    (d as HTMLDetailsElement).open = false;
    const r = judgeRoom(d, "cost");
    expect(r.verdict).toBe("ok");
    expect(r.open).toBe(false);
  });
  it("a hidden room is unjudgeable, which is not the same as empty", () => {
    const d = room("<summary>Field</summary>");
    d.style.display = "none";
    expect(judgeRoom(d, "field").verdict).toBe("hidden");
  });
});

describe("compareRuns — the gate on any change to the shell", () => {
  const rep = (_label: string, panes: Array<[string, "ok" | "empty" | "slow"]>) =>
    summarise(panes.map(([id, verdict]) => ({ id, verdict, chars: 0, controls: 0, detail: "" })));

  it("a pane that rendered before and not after is a REGRESSION", () => {
    const d = compareRuns(rep("before", [["ws:Cost", "ok"]]), rep("after", [["ws:Cost", "empty"]]));
    expect(d.regressions).toEqual(["ws:Cost"]);
    expect(d.gains).toEqual([]);
  });
  it("`slow` is a pass on both sides, so a slower-but-rendering pane is not a regression", () => {
    const d = compareRuns(rep("before", [["ws:Model", "ok"]]), rep("after", [["ws:Model", "slow"]]));
    expect(d.regressions).toEqual([]);
    expect(d.same).toBe(1);
  });
  it("a pane fixed by the later run is a gain, not silence", () => {
    const d = compareRuns(rep("before", [["ws:Field", "empty"]]), rep("after", [["ws:Field", "ok"]]));
    expect(d.gains).toEqual(["ws:Field"]);
  });
  it("a pane present in only one run is INCOMPARABLE, never a regression", () => {
    // The two runs may have walked different tab sets; calling that a defect would block a release
    // on a measurement artifact rather than on a real one.
    const d = compareRuns(rep("before", [["ws:Only", "ok"]]), rep("after", [["ws:Other", "ok"]]));
    expect(d.regressions).toEqual([]);
    expect(d.incomparable).toEqual(["ws:Only", "ws:Other"]);
    expect(d.same).toBe(0);
  });
  it("identical runs report no regressions and no gains", () => {
    const d = compareRuns(rep("before", [["a", "ok"], ["b", "ok"]]),
                            rep("after", [["a", "ok"], ["b", "ok"]]));
    expect(d).toMatchObject({ regressions: [], gains: [], incomparable: [], same: 2 });
  });
});

// --- the guard's own unknown-vs-none bug, found by running it against the real app ----------------
// auditRooms() reported every room `missing` whenever the nav had not been built — the landing page,
// before a project opens, the portal's empty state. That reads as "the spine rail is broken" when the
// truth is "there was nothing here to judge". Same confusion the audit exists to prevent, committed
// one level up inside the guard itself.
describe("auditRooms — no rail is not a broken rail", () => {
  afterEach(() => { document.body.innerHTML = ""; localStorage.clear(); });

  it("reports UNKNOWN, not missing, when no nav was rendered at all", () => {
    const r = auditRooms(["model", "cost"]);
    expect(r.rooms.every((x) => x.verdict === "unknown")).toBe(true);
    expect(r.missing).toEqual([]);          // nothing may be blamed on the rail
    expect(r.empty).toEqual([]);
    expect(r.note).toContain("NO NAV RENDERED");
    expect(r.rooms[0]!.detail).toContain("not the same as a rail that omitted this room");
  });

  it("only calls a room MISSING when a rail exists and omits it", () => {
    const nav = document.createElement("div");
    nav.className = "pnav";
    nav.innerHTML = '<details class="pnav-room" data-room="model">'
                  + "<summary>Model</summary><button>Viewer</button></details>";
    document.body.appendChild(nav);
    const r = auditRooms(["model", "cost"]);
    expect(r.rooms.find((x) => x.id === "model")!.verdict).toBe("ok");
    expect(r.missing).toEqual(["cost"]);    // the rail is there and genuinely lacks this room
  });

  it("looks for rooms INSIDE the nav, not anywhere in the document", () => {
    // A stray .pnav-room outside the rail would otherwise launder a missing room into a pass.
    const stray = document.createElement("details");
    stray.className = "pnav-room";
    stray.dataset.room = "cost";
    stray.innerHTML = "<summary>Cost</summary><button>Budget</button>";
    document.body.appendChild(stray);
    const nav = document.createElement("div");
    nav.className = "pnav";
    document.body.appendChild(nav);
    expect(auditRooms(["cost"]).missing).toEqual(["cost"]);
  });
});

// --- the direction this file never guarded, and the one that actually bit ---------------------------
// Every other trap here is about a false BLANK. This is a false PASS: the app's "No project open"
// placeholder runs to 123 characters — three times MIN_CHARS — so a workspace showing nothing but
// that placeholder scored `ok`, and was reported as rendering fine while being, to a user, empty.
// A false blank gets investigated; a false pass gets shipped.
describe("an empty-state placeholder is not content", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  const pane = (inner: string) => {
    const host = document.createElement("div");
    host.innerHTML = `<div class="portal-content">${inner}</div>`;
    document.body.appendChild(host);
    return { host, content: host.querySelector<HTMLElement>(".portal-content") };
  };

  it("scores EMPTY even when the placeholder text is far longer than MIN_CHARS", () => {
    const long = "No project open. Create one with + New in the top bar (or pick an existing "
               + "project), then the developer workspace loads here.";
    expect(long.length).toBeGreaterThan(MIN_CHARS * 2);   // the real message really is this long
    const { host, content } = pane(`<div class="empty-state">${long}</div>`);
    const r = judgePane("ws:Developer", host, content);
    expect(r.verdict).toBe("empty");
    expect(r.detail).toContain("empty-state placeholder");
  });

  it("still scores OK when real content sits ALONGSIDE a placeholder", () => {
    // A page may legitimately show an empty state for one card while the rest is populated.
    const { host, content } = pane(
      '<div class="empty-state">No cost data yet</div>'
      + "<div>Schedule of values, budget, commitments and forecast for this project.</div>");
    expect(judgePane("ws:Cost", host, content).verdict).toBe("ok");
  });

  it("a pane with a placeholder AND controls is still judged on the placeholder alone", () => {
    // Guard against the inverse cheat: the placeholder's own "+ New" button must not rescue it.
    const { host, content } = pane(
      '<div class="empty-state">No project open <button>+ New</button></div>');
    expect(judgePane("ws:Design", host, content).verdict).toBe("empty");
  });
});
