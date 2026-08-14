/**
 * R26-INSPECTOR ② — the Inspector's tabs, over the lifecycle strip that is its spine.
 *
 * Sprint C shipped the strip: select an element and six states say how far it has got. What it did
 * not ship were the **tabs** — so the strip could tell you a cost state was `done` and there was
 * nowhere to go and see the number. A summary with no detail behind it is a claim you cannot check,
 * which is the opposite of what the last two rings were for: the 5D binding supplies the rate, the 4D
 * binding supplies the dates, and neither was reachable from the element they describe.
 *
 * **The tab bar states availability before you click.** Four tabs where three are frequently empty is
 * a shell game if the only way to learn that is to click each one. So each tab carries a mark, and
 * the marks are **the strip's own vocabulary** — `●` done, `○` none, `–` unknown — rather than a
 * second glyph language meaning the same three things. Same reasoning as the colour contract: one
 * meaning per symbol, enforced, or the symbols stop carrying meaning at all.
 *
 * **`unknown` and `none` are different tabs.** This is the distinction the whole codebase keeps
 * landing on. "This element has no cost code" is a finding — it tells an estimator something true and
 * actionable. "We never asked the server" is not a finding, and rendering it as *no cost* invents an
 * absence. A tab whose data failed to load says so and offers nothing else; a tab whose data loaded
 * and was empty explains what being empty means for that tab.
 *
 * Everything here is text-only by construction (`textContent`, never `innerHTML`): the values are
 * model- and server-derived free text, which is the exact class the XSS gate exists for.
 */
import type { LifecycleStrip } from "../api/types";
import { usd } from "../ui/charts";

export type TabKey = "properties" | "cost" | "schedule" | "field";

/** Availability of a tab's content. The same three-way the strip uses, for the same reason. */
export type TabState = "ready" | "none" | "unknown";

/** The strip's marks, reused deliberately. A second vocabulary for the same three states is how a
 *  symbol stops meaning anything. */
export const TAB_MARK: Record<TabState, string> = { ready: "●", none: "○", unknown: "–" };

export const TAB_MEANS: Record<TabState, string> = {
  ready: "has content",
  none: "nothing recorded for this element — a finding, not an error",
  unknown: "not loaded — this run never asked, which is not the same as nothing being there",
};

export interface Element5d {
  schedule: { ref: string; name: string; trade: string | null; percent: number;
              start: string | null; finish: string | null; state: string | null;
              hard_tied: boolean } | null;
  cost: { code: string | null; ref: string | null; name: string | null; division: string | null;
          budget: number; committed: number; actual: number; eac: number;
          variance: number } | null;
}

export interface InspectorData {
  /** `null` means the 5D call was never made or failed — NOT that the element has no 5D. */
  fived: Element5d | null;
  /** `null` means the lifecycle call was never made or failed. */
  lifecycle: LifecycleStrip | null;
}

export const TAB_LABELS: Record<TabKey, string> = {
  properties: "Properties", cost: "Cost", schedule: "Schedule", field: "Field",
};

/** Which field states the Field tab reports on. These are the strip's later states — the ones that
 *  are about what happened on site rather than what was drawn. */
export const FIELD_STATES = ["installed", "verified"] as const;

/**
 * What each tab can currently show.
 *
 * Properties is always `ready`: it is rendered from the element the user just selected, so there is
 * no fetch that can fail. The others distinguish a failed/absent fetch (`unknown`) from a successful
 * fetch that found nothing (`none`) — collapsing those two is how a UI reports an absence it never
 * checked for.
 */
export function tabStates(data: InspectorData): Record<TabKey, TabState> {
  const fived = data.fived;
  const lc = data.lifecycle;
  return {
    properties: "ready",
    cost: fived === null ? "unknown" : fived.cost ? "ready" : "none",
    schedule: fived === null ? "unknown" : fived.schedule ? "ready" : "none",
    field: lc === null
      ? "unknown"
      : (lc.states || []).some((s) => (FIELD_STATES as readonly string[]).includes(s.key)
                                      && s.status === "done") ? "ready" : "none",
  };
}

function el(tag: string, cls?: string, text?: string): HTMLElement {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;               // never innerHTML: server/model text
  return n;
}

function row(label: string, value: string): HTMLElement {
  const r = el("div", "insp-row");
  r.append(el("span", "insp-k", label), el("span", "insp-v", value));
  return r;
}


/** The explanatory body for a tab that has nothing to show. States WHICH kind of nothing. */
export function emptyBody(key: TabKey, state: TabState): HTMLElement {
  const box = el("div", "insp-empty");
  if (state === "unknown") {
    box.append(el("div", "insp-empty-t", "Not loaded"));
    box.append(el("div", "meta", TAB_MEANS.unknown));
    return box;
  }
  const says: Record<TabKey, string> = {
    properties: "",
    cost: "No cost code is tied to this element. Its scope is unpriced — that is a gap in the "
        + "estimate, not an error here.",
    schedule: "No activity builds this element. It is not on the programme, so no date covers it.",
    field: "Nothing has been recorded from site for this element yet — not installed, not verified.",
  };
  box.append(el("div", "insp-empty-t", "Nothing recorded"));
  box.append(el("div", "meta", says[key]));
  return box;
}

export function costBody(fived: Element5d): HTMLElement {
  const c = fived.cost!;
  const box = el("div", "insp-body");
  box.append(row("Cost code", c.code || "—"));
  if (c.name) box.append(row("Name", c.name));
  if (c.division) box.append(row("Division", c.division));
  box.append(row("Budget", usd(c.budget)));
  box.append(row("Committed", usd(c.committed)));
  box.append(row("Actual", usd(c.actual)));
  box.append(row("Forecast (EAC)", usd(c.eac)));
  // Stated as a signed number with its direction named, rather than left for the reader to infer a
  // sign convention. A variance whose direction is ambiguous is worse than no variance.
  const v = c.variance;
  box.append(row("Variance", `${usd(v)} ${v < 0 ? "(over budget)" : v > 0 ? "(under budget)" : ""}`.trim()));
  return box;
}

export function scheduleBody(fived: Element5d): HTMLElement {
  const s = fived.schedule!;
  const box = el("div", "insp-body");
  box.append(row("Activity", s.name || s.ref));
  if (s.trade) box.append(row("Trade", s.trade));
  box.append(row("Progress", `${Math.round(s.percent)}%`));
  box.append(row("Start", s.start || "—"));
  box.append(row("Finish", s.finish || "—"));
  if (s.state) box.append(row("Status", s.state));
  // The provenance of the link itself. A binding written into the IFC is a different claim from one
  // inferred by a matching rule, and the Inspector is exactly where that difference should be legible.
  box.append(row("Binding", s.hard_tied
    ? "tied to this element in the model"
    : "matched by rule — not bound in the model"));
  return box;
}

export function fieldBody(lc: LifecycleStrip): HTMLElement {
  const box = el("div", "insp-body");
  const byKey = new Map((lc.states || []).map((s) => [s.key, s]));
  for (const key of FIELD_STATES) {
    const s = byKey.get(key);
    const mark = s ? (s.status === "done" ? "●" : s.status === "none" ? "○" : "–") : "–";
    box.append(row(`${mark} ${key}`, s ? (s.means || s.status) : "not reported by the server"));
  }
  // Out-of-order combinations are real data defects and the strip already detects them. Surfacing
  // them here rather than only in a tooltip is the point of having a tab at all.
  if (lc.inconsistencies?.length) {
    const warn = el("div", "insp-warn");
    warn.append(el("div", "insp-empty-t", "Inconsistent"));
    for (const i of lc.inconsistencies) warn.append(el("div", "meta", i));
    box.append(warn);
  }
  return box;
}

/**
 * Build the tab bar and body.
 *
 * `properties` is supplied by the caller because it is already built — this module does not rebuild
 * the properties view, it gives it a home alongside the other three. `onSelect` is optional and used
 * only for tests and instrumentation; switching tabs is handled internally.
 */
export function buildInspectorTabs(
  properties: HTMLElement,
  data: InspectorData,
  opts: { active?: TabKey; onSelect?: (k: TabKey) => void } = {},
): HTMLElement {
  const states = tabStates(data);
  const host = el("div", "insp-tabs");
  const bar = el("div", "insp-tabbar");
  const body = el("div", "insp-tabbody");
  const keys: TabKey[] = ["properties", "cost", "schedule", "field"];

  const render = (k: TabKey) => {
    if (k === "properties") { body.replaceChildren(properties); return; }
    const st = states[k];
    if (st !== "ready") { body.replaceChildren(emptyBody(k, st)); return; }
    if (k === "cost") body.replaceChildren(costBody(data.fived!));
    else if (k === "schedule") body.replaceChildren(scheduleBody(data.fived!));
    else body.replaceChildren(fieldBody(data.lifecycle!));
  };

  const active = opts.active && keys.includes(opts.active) ? opts.active : "properties";
  for (const k of keys) {
    const b = document.createElement("button");
    b.className = "insp-tab" + (k === active ? " active" : "");
    b.dataset.tab = k;
    b.dataset.state = states[k];
    // The mark is part of the label, not a decoration: a tab bar that hides which tabs are empty
    // makes the user click all four to find out.
    b.append(el("span", "insp-tab-mark", TAB_MARK[states[k]]), el("span", "insp-tab-l", TAB_LABELS[k]));
    b.title = `${TAB_LABELS[k]} — ${TAB_MEANS[states[k]]}`;
    // Never disabled. An empty tab still has something to say — which KIND of empty it is — and
    // disabling it would remove the only place that distinction is visible.
    b.onclick = () => {
      bar.querySelectorAll(".insp-tab").forEach((n) => n.classList.remove("active"));
      b.classList.add("active");
      render(k);
      opts.onSelect?.(k);
    };
    bar.appendChild(b);
  }
  render(active);
  host.append(bar, body);
  return host;
}
