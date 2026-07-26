/**
 * R26-V-LIVE — a repeatable audit of what the running app actually renders.
 *
 * The audit that started R26 was a click-through, and click-throughs do not survive: the next person
 * has to redo the whole thing, and nobody can tell whether a pane was blank or merely unmeasured.
 * This turns it into an artifact you can run and re-run — `window.__liveAudit()` in the app, or the
 * same function driven from a browser tool.
 *
 * **Everything here is shaped by the three ways a DOM audit lies, all of which fail toward a false
 * "blank" — the most expensive direction, because it invents defects that then get "fixed".**
 *
 * 1. **`innerText` is empty for a node that is not laid out.** A hidden workspace, a collapsed
 *    `<details>`, a pane behind `display:none` — all report no text while being perfectly populated.
 *    So content is measured from `textContent` (which does not depend on layout) and a pane that is
 *    not displayed is reported as **`hidden`**, never as `empty`.
 * 2. **Clicking rebuilds the nav, which detaches any node you were holding.** A reference captured
 *    before a click is a live object pointing at nothing. Everything here re-queries after every
 *    interaction and never carries a node across one.
 * 3. **The shell is not the content.** `#panel-portal` contains the rail *and* the content pane; a
 *    populated rail beside an empty pane still measures as "has content". The pane is measured
 *    separately, by class, and its absence is reported distinctly from its emptiness.
 *
 * The report's verdicts follow the rule the rest of this codebase follows: something the audit could
 * not examine is `unknown`, never `ok` and never `empty`.
 */

export type Verdict = "ok" | "empty" | "slow" | "hidden" | "missing" | "unknown";

export interface PaneReport {
  id: string;
  verdict: Verdict;
  /** Characters of real text in the CONTENT pane (not the shell around it). */
  chars: number;
  /** Interactive controls found — a pane of pure prose and a pane of buttons are different. */
  controls: number;
  detail: string;
}

export interface LiveAuditReport {
  panes: PaneReport[];
  ok: number;
  problems: PaneReport[];
  /** Verdicts the audit could not reach. Reported, never counted as passes. */
  unknown: PaneReport[];
  note: string;
}

/** Minimum real text before a pane counts as populated rather than a spinner or a stub. */
export const MIN_CHARS = 40;

/**
 * Is this element displayed?
 *
 * Answered from **computed style up the ancestor chain**, not from `offsetParent`. Two reasons, and
 * the first is a bug the first draft of this file had:
 *
 * * `offsetParent` is null for `position: fixed` elements that are perfectly visible, so an
 *   offsetParent test reports the floating toolbar and every modal as hidden — a false negative in
 *   the auditor whose entire job is not producing false negatives.
 * * `offsetParent` and `getBoundingClientRect` depend on a real layout engine, which means the guard
 *   could not be tested. A guard against the audit's worst failure mode has to be the *best*-tested
 *   thing here, not the least.
 *
 * The ancestor walk is required: an element inside a `display:none` parent computes its own `display`
 * normally, so checking only the element itself misses exactly the case that matters.
 */
export function isDisplayed(el: HTMLElement): boolean {
  let node: HTMLElement | null = el;
  while (node) {
    if (node.hidden) return false;
    const cs = getComputedStyle(node);
    if (cs.display === "none" || cs.visibility === "hidden") return false;
    node = node.parentElement;
  }
  return true;
}

/**
 * Real text in `el`, ignoring layout.
 *
 * `textContent`, not `innerText`: the second is layout-dependent and returns "" for anything not
 * currently rendered, which is trap 1 and the reason an earlier audit reported populated panels as
 * blank. Script and style contents are excluded — they are text, but not to a reader.
 */
export function realText(el: HTMLElement): string {
  const clone = el.cloneNode(true) as HTMLElement;
  clone.querySelectorAll("script,style,template").forEach((n) => n.remove());
  return (clone.textContent || "").replace(/\s+/g, " ").trim();
}

/**
 * Judge one pane.
 *
 * `content` is the element that should hold the pane's *content* — for the portal that is
 * `.portal-content`, not the shell that also contains the rail (trap 3). When the host exists but the
 * content element does not, the verdict is `unknown`: the audit does not know whether that pane has
 * a different structure or is genuinely broken, and guessing either way is worse than saying so.
 */
export function judgePane(id: string, host: HTMLElement | null, content?: HTMLElement | null): PaneReport {
  if (!host) return { id, verdict: "missing", chars: 0, controls: 0, detail: "no such element" };
  if (!isDisplayed(host)) {
    return { id, verdict: "hidden", chars: 0, controls: 0,
             detail: "not displayed — cannot be judged from here, which is not the same as empty" };
  }
  if (content === null) {
    return { id, verdict: "unknown", chars: 0, controls: 0,
             detail: "expected a content element and found none — structure differs, or it is broken" };
  }
  const target = content ?? host;
  const chars = realText(target).length;
  const controls = target.querySelectorAll("button, a[href], input, select, textarea").length;
  if (chars >= MIN_CHARS || controls > 0) {
    return { id, verdict: "ok", chars, controls, detail: `${chars} chars · ${controls} controls` };
  }
  return { id, verdict: "empty", chars, controls,
           detail: `only ${chars} chars and no controls — displayed but with nothing in it` };
}

export function summarise(panes: PaneReport[]): LiveAuditReport {
  return {
    panes,
    // `slow` is a pass: the pane rendered, it just took a second look to see it.
    ok: panes.filter((p) => p.verdict === "ok" || p.verdict === "slow").length,
    problems: panes.filter((p) => p.verdict === "empty" || p.verdict === "missing"),
    unknown: panes.filter((p) => p.verdict === "unknown" || p.verdict === "hidden"),
    note: ("`hidden` and `unknown` are NOT passes and NOT failures — they are panes this run could "
           + "not judge. Counting them either way is how an audit invents defects or hides them. "
           + "`slow` IS a pass: the pane rendered, it just needed a second look."),
  };
}

/**
 * Walk the app: click each workspace tab, wait for it to settle, judge its content pane.
 *
 * Re-queries after every click (trap 2) and returns a report rather than logging, so a caller can
 * assert on it. `wait` is injectable so a test can drive it without real timers.
 */
export async function auditWorkspaces(
  opts: { settleMs?: number; wait?: (ms: number) => Promise<void> } = {},
): Promise<LiveAuditReport> {
  const settle = opts.settleMs ?? 2500;
  const wait = opts.wait ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  const panes: PaneReport[] = [];

  const tabs = [...document.querySelectorAll<HTMLElement>("#workspaces [role='tab'], #workspaces button")];
  for (const tab of tabs) {
    const name = (tab.textContent || "").trim();
    if (!name) continue;
    // Re-find the tab by name after every interaction: the one captured above may be detached by the
    // time we come back to it, and a click on a detached node silently does nothing.
    const live = [...document.querySelectorAll<HTMLElement>("#workspaces [role='tab'], #workspaces button")]
      .find((t) => (t.textContent || "").trim() === name);
    live?.click();
    await wait(settle);

    const look = () => {
      const ws = document.querySelector<HTMLElement>(".workspace.active");
      // The content pane, not the shell that also holds the rail (trap 3).
      const content = ws?.querySelector<HTMLElement>(".portal-content, .fullpanel, #container") ?? null;
      return judgePane(`workspace:${name}`, ws ?? null, ws ? content : undefined);
    };

    let r = look();
    // TRAP 4, found by running this against the real app: a pane that is still BOOTING is not an
    // empty pane. The first run reported Model, Design and Developer blank; all three were mid-boot
    // and fully populated seconds later. An auditor that cannot tell "nothing here" from "not yet"
    // manufactures exactly the false blanks the other three guards exist to prevent — so an empty
    // verdict is never final on first look. It costs one extra wait, and only for panes that would
    // otherwise be reported as defects.
    if (r.verdict === "empty") {
      await wait(settle * 2);
      const again = look();
      r = again.verdict === "ok"
        ? { ...again, verdict: "slow", detail: `${again.detail} — empty on first look, filled on retry` }
        : again;
    }
    panes.push(r);
  }
  return summarise(panes);
}

declare global {
  interface Window { __liveAudit?: typeof auditWorkspaces }
}

/** Expose for a console run. Dev affordance only — no behaviour attaches to it. */
export function installLiveAudit(): void {
  window.__liveAudit = auditWorkspaces;
}
