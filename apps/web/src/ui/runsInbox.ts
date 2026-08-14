/**
 * R24-RUNS-INBOX phase 1 — the rendering half. The computation is in `ui/runs.ts` and is pure.
 *
 * One decision worth stating, because the opposite was easier: **a kind with one run still gets a
 * section, and its single run says "first run — nothing to compare".** Hiding it until there are two
 * would mean the inbox is empty the first time anyone opens it, which is exactly when someone is
 * trying to find out whether the feature exists.
 *
 * Everything user-facing goes through `textContent`. A job's `kind` can come from a plugin, its
 * `actor` from an identity provider, and its `error` from any handler's exception — all three reach
 * this list, and none is ours.
 */
import type { Job } from "../api/types";
import { ABSENT, formatDelta, runHistory, type MetricDelta, type Run } from "./runs";

/** Rows past this per run are hidden behind a count — a diff nobody scrolls is a diff nobody reads. */
const SHOW_DELTAS = 6;

function el(tag: string, cls?: string, text?: string): HTMLElement {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

/** `2026-08-14T03:12:00Z` → a short local stamp. An unparseable value is shown verbatim, not dropped. */
export function shortTime(iso: string | null): string {
  if (!iso) return ABSENT;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

/** One metric row: `findings  412 → 389  −23`. */
function deltaRow(d: MetricDelta): HTMLElement {
  const row = el("div");
  row.style.cssText = "display:flex;gap:8px;align-items:baseline;font-size:12px;padding:1px 0";
  row.dataset.metric = d.key;
  const key = el("span", undefined, d.key);
  key.style.cssText = "flex:1;opacity:.85";
  const from = el("span", "meta", `${d.prev ?? ABSENT} → ${d.next ?? ABSENT}`);
  from.style.cssText = "font-variant-numeric:tabular-nums;opacity:.7";
  const delta = el("span", undefined, d.delta === null ? ABSENT : formatDelta(d.delta));
  // Absent is neutral grey, never a colour that reads as good or bad news about a number we do not
  // have. Only a real movement gets a semantic hue.
  delta.style.cssText = "font-variant-numeric:tabular-nums;min-width:52px;text-align:right;color:"
    + (d.delta === null || d.delta === 0 ? "var(--fg-muted,#8b95a5)"
       : d.delta > 0 ? "var(--status-warn,#d99a2b)" : "var(--status-ok,#3ba55d)");
  row.append(key, from, delta);
  return row;
}

/** One run: what it was, when, by whom, and what moved since the run before it. */
export function renderRun(r: Run): HTMLElement {
  const box = el("div");
  box.style.cssText = "border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin:6px 0";
  box.dataset.job = r.job.id;
  box.dataset.state = r.job.state;

  const head = el("div");
  head.style.cssText = "display:flex;gap:8px;align-items:baseline;justify-content:space-between";
  head.append(
    el("span", undefined, shortTime(r.job.finished_at ?? r.job.created_at)),
    el("span", "meta", [r.job.state, r.job.actor].filter(Boolean).join(" · ")),
  );
  box.appendChild(head);

  if (r.job.state === "error") {
    // The failure text, verbatim and never truncated into meaninglessness. It is the only content
    // this row has, and a failed run is the one people open the inbox to find.
    const err = el("div", "meta", r.job.error ?? "failed, with no detail recorded");
    err.style.cssText = "color:var(--status-bad,#d9534f);font-size:12px;margin-top:4px";
    box.appendChild(err);
    return box;
  }

  if (!r.previous) {
    box.appendChild(el("div", "meta", "First run — nothing to compare against yet."));
    return box;
  }

  const moved = r.deltas.filter((d) => d.delta !== 0);
  if (!moved.length) {
    box.appendChild(el("div", "meta", `No change from the run at ${shortTime(r.previous.finished_at)}.`));
    return box;
  }
  const cmp = el("div", "meta", `vs ${shortTime(r.previous.finished_at)}`);
  cmp.style.cssText = "font-size:11px;margin:4px 0 2px;opacity:.7";
  box.appendChild(cmp);
  for (const d of moved.slice(0, SHOW_DELTAS)) box.appendChild(deltaRow(d));
  if (moved.length > SHOW_DELTAS) {
    box.appendChild(el("div", "meta", `+${moved.length - SHOW_DELTAS} more metric(s)`));
  }
  return box;
}

/**
 * The inbox: every kind that has run on this project, newest run first.
 *
 * An empty list is not an error and does not render as one. The four analyses the audit named — clash,
 * IDS, cost, energy — still run in the request thread behind a modal, so on most projects this is
 * genuinely empty, and the copy says which half of the item is missing rather than implying the
 * feature is broken.
 */
export function renderRunsInbox(host: HTMLElement, jobs: readonly Job[], label: (kind: string) => string): void {
  host.innerHTML = "";
  const history = runHistory(jobs);
  if (!history.size) {
    const empty = el("div", "meta");
    empty.dataset.empty = "none";
    empty.textContent = "No runs yet on this project. Analyses that go through the background queue "
      + "appear here with a comparison against the previous run; clash, IDS, cost and energy still "
      + "run in the foreground and are not queued yet.";
    host.appendChild(empty);
    return;
  }
  // Kinds ordered by their most recent activity, so what you just ran is at the top.
  const kinds = [...history.keys()].sort((a, b) => {
    const ta = history.get(a)![0]?.job.created_at ?? "";
    const tb = history.get(b)![0]?.job.created_at ?? "";
    return tb.localeCompare(ta);
  });
  for (const kind of kinds) {
    const runs = history.get(kind)!;
    const sec = document.createElement("details");
    sec.open = true;
    sec.style.cssText = "margin:8px 0";
    sec.dataset.kind = kind;
    const sum = el("summary", undefined, `${label(kind)} · ${runs.length}`);
    sum.style.cssText = "cursor:pointer;font-weight:600;list-style:revert";
    sec.appendChild(sum);
    for (const r of runs) sec.appendChild(renderRun(r));
    host.appendChild(sec);
  }
}
