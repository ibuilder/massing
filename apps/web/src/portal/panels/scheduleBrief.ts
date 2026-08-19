import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * R36-ROOM-BRIEFS — Schedule (superintendent).
 *
 * The room opens with three answers, then the rest of the board. Work (`workQueue.ts`) is the
 * template: a landing that is the job, not a toolbar in front of the job.
 *
 * 1. **Today's lookahead** — what is in this week's interval. Empty is a sentence, not a 0.
 * 2. **Blockers** — high/medium predictive alerts. A failed fetch is a reason, never "0 high".
 * 3. **Yesterday's variance** — slip vs the captured baseline. No baseline is a reason
 *    (the 409), never "0 slipped".
 *
 * The three engines already exist (`scheduleLookahead`, `scheduleAlerts`, `scheduleVariance`).
 * This file only puts them first. Remaining rooms (Deal, …) are still open on R36.
 */
export const SCHEDULE_BRIEF_QUESTIONS = [
  { key: "lookahead", title: "Today's lookahead" },
  { key: "blockers", title: "Blockers" },
  { key: "variance", title: "Yesterday's variance" },
] as const;

type Alert = { level: string; title: string; detail: string; ref?: string };

function card(title: string): { root: HTMLElement; body: HTMLElement } {
  const root = document.createElement("div");
  root.className = "dash-card";
  root.style.cssText = "flex:1 1 220px;min-width:200px;margin:0";
  const h = document.createElement("div");
  h.className = "section-title";
  h.style.margin = "0 0 4px";
  h.textContent = title;
  const body = document.createElement("div");
  body.className = "meta";
  body.textContent = "Loading…";
  root.append(h, body);
  return { root, body };
}

function fail(body: HTMLElement, reason: string): void {
  body.dataset.unavailable = "1";
  body.textContent = reason;
}

export async function renderScheduleBrief(ctx: PanelContext): Promise<HTMLElement> {
  const pid = ctx.host.projectId()!;
  const wrap = document.createElement("div");
  wrap.dataset.scheduleBrief = "1";
  wrap.style.cssText = "display:flex;flex-wrap:wrap;gap:8px;margin:0 0 10px";

  const byKey = Object.fromEntries(
    SCHEDULE_BRIEF_QUESTIONS.map((q) => {
      const c = card(q.title);
      c.root.dataset.brief = q.key;
      wrap.appendChild(c.root);
      return [q.key, c] as const;
    }),
  );
  const laCard = byKey.lookahead!;
  const blCard = byKey.blockers!;
  const vaCard = byKey.variance!;

  const [la, al, va] = await Promise.allSettled([
    ctx.host.api.scheduleLookahead(pid, 3),
    ctx.host.api.scheduleAlerts(pid),
    ctx.host.api.scheduleVariance(pid),
  ]);

  if (la.status === "rejected") {
    fail(laCard.body, `Lookahead unavailable: ${(la.reason as Error).message}`);
  } else if (!la.value.count) {
    laCard.body.textContent = "No activities in the next 3 weeks.";
  } else {
    const week = la.value.weeks_detail[0];
    const acts = week?.activities ?? [];
    laCard.body.innerHTML = "";
    const sub = document.createElement("div");
    sub.style.marginBottom = "4px";
    sub.textContent = `${week?.week ?? "This week"} · ${acts.length} in the first interval`;
    laCard.body.appendChild(sub);
    for (const a of acts.slice(0, 6)) {
      const row = document.createElement("div");
      row.style.margin = "1px 0";
      row.textContent = `${a.name}${a.trade ? ` · ${a.trade}` : ""} · ${a.status.replace("_", " ")}`;
      laCard.body.appendChild(row);
    }
  }

  if (al.status === "rejected") {
    fail(blCard.body, `Blockers unavailable: ${(al.reason as Error).message}`);
  } else {
    const blockers = al.value.alerts.filter((a: Alert) => a.level === "high" || a.level === "medium");
    if (!blockers.length) {
      const low = al.value.counts.low || 0;
      blCard.body.textContent = low
        ? `No blockers flagged. ${low} low-priority alert${low === 1 ? "" : "s"} sit further down the board.`
        : "No blockers flagged.";
    } else {
      blCard.body.innerHTML = "";
      for (const a of blockers.slice(0, 6)) {
        const row = document.createElement("div");
        row.style.margin = "2px 0";
        // Alerts name activities from the live schedule / an imported P6 file.
        row.innerHTML = `<b>${esc(a.title)}</b> — ${esc(a.detail)}`
          + (a.ref ? ` <span style="opacity:.6">[${esc(a.ref)}]</span>` : "");
        blCard.body.appendChild(row);
      }
    }
  }

  if (va.status === "rejected") {
    fail(vaCard.body, `Variance unavailable: ${(va.reason as Error).message}`);
  } else {
    const s = va.value.summary;
    const slipped = Number(s.slipped || 0);
    vaCard.body.innerHTML = "";
    const sub = document.createElement("div");
    sub.style.marginBottom = "4px";
    sub.textContent = `Baseline ${va.value.captured_at} · ${slipped} slipped`
      + ` · max ${Number(s.max_slip_days || 0)}d`;
    vaCard.body.appendChild(sub);
    const rows = va.value.activities
      .filter((x) => (x.finish_var || 0) > 0 || x.status === "slipped")
      .slice(0, 5);
    for (const a of rows) {
      const row = document.createElement("div");
      row.style.margin = "1px 0";
      const fv = a.finish_var;
      const tag = fv == null ? a.status : `+${fv}d`;
      row.textContent = `${a.name} · ${tag}`;
      vaCard.body.appendChild(row);
    }
  }

  return wrap;
}
