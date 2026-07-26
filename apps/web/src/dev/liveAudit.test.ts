import { beforeEach, describe, expect, it } from "vitest";
import { MIN_CHARS, auditWorkspaces, isDisplayed, judgePane, realText, summarise } from "./liveAudit";

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
