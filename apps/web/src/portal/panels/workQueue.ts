import { escapeHtml as esc, toast } from "../../ui/feedback";
import { markPrimary } from "../../ui/a11yJourney";
import type { PanelContext } from "../panelContext";
import type { QueueItem } from "../../api/types";

/**
 * R26-WORK-QUEUE — the Work room's home: what is in your court, in the order it needs you, acted on
 * without leaving the queue.
 *
 * The design decisions that matter are in the engine (`work_queue.py`); the two this file has to
 * honour are:
 *
 * * **`undated` renders as its own group, above `later`, with its reason on screen.** An item nobody
 *   dated is a gap somebody should close, and the fastest way to close it is to be told it exists.
 * * **A button here runs a transition the server has already agreed to.** The engine returns only the
 *   actions this party can perform from this state, so the queue never offers a click that 409s. An
 *   action the module gates behind required fields is shown as a *link into the record* instead —
 *   it needs a form, not a click, and pretending otherwise is how a one-click button becomes a dead
 *   end.
 */
export async function renderWorkQueue(ctx: PanelContext) {
  const pid = ctx.host.projectId()!;
  ctx.root.innerHTML = "";
  ctx.root.appendChild(ctx.bar("✅ My work", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));

  const body = document.createElement("div");
  body.innerHTML = `<div class="meta">Gathering what is in your court…</div>`;
  ctx.root.appendChild(body);

  // Open the record's own module, filtered to it — the queue hands off rather than re-implementing
  // a record view, so there is one place a record is edited.
  const open = (it: QueueItem) => {
    const m = ctx.mods.find((x) => x.key === it.module);
    if (m) { ctx.activeKey = it.module; void ctx.openModule(m, { q: it.ref }); ctx.buildNav(); }
  };

  async function load() {
    let q;
    try { q = await ctx.host.api.workQueue(pid); }
    catch (e) { body.innerHTML = `<div class="meta">Couldn't load the queue: ${esc((e as Error).message)}</div>`; return; }
    body.replaceChildren();

    const restoreFocus = () => {
      const p = body.querySelector<HTMLElement>("[data-room-primary]");
      if (p && !body.contains(document.activeElement)) p.focus();
    };

    const head = document.createElement("div");
    head.className = "dash-card"; head.style.marginBottom = "10px";
    // "You have 14 things" and "14 things, 3 of them waiting on somebody else" are different
    // statements, and only the second lets someone plan a day.
    head.innerHTML = `<div class="section-title" style="margin:0 0 4px">In your court</div>`
      + `<div class="meta">${q.total} item${q.total === 1 ? "" : "s"} · `
      + `<b>${q.actionable}</b> you can move now`
      + (q.no_action ? ` · ${q.no_action} waiting on someone else` : "") + `</div>`;
    body.appendChild(head);

    if (!q.total) {
      const none = document.createElement("div");
      none.className = "dash-card";
      none.innerHTML = `<div class="meta">Nothing is in your court right now.</div>`;
      const refresh = document.createElement("button");
      refresh.type = "button";
      refresh.className = "tool-btn";
      refresh.style.marginTop = "8px";
      refresh.textContent = "Refresh queue";
      refresh.onclick = () => void load();
      markPrimary(refresh, "work");
      none.appendChild(refresh);
      body.appendChild(none);
      restoreFocus();
      return;
    }

    let marked = false;
    for (const b of q.buckets) {
      // An empty bucket is skipped EXCEPT overdue: rendering "Overdue 0" is worth the line, because
      // a missing heading makes the reader check whether it was hidden or genuinely clear.
      if (!b.count && b.key !== "overdue") continue;
      const card = document.createElement("div");
      card.className = "dash-card"; card.style.marginBottom = "10px";
      card.dataset.bucket = b.key;
      const h = document.createElement("div");
      h.className = "section-title"; h.style.margin = "0 0 2px";
      h.textContent = `${b.label} · ${b.count}`;
      const why = document.createElement("div");
      why.className = "meta"; why.style.marginBottom = "6px";
      why.textContent = b.means;
      card.append(h, why);

      for (const it of b.items) {
        const row = document.createElement("div");
        row.className = "wq-row";
        row.dataset.module = it.module;

        const main = document.createElement("button");
        main.className = "wq-open";
        main.type = "button";
        main.title = `Open ${it.ref}`;
        if (!marked) { markPrimary(main, "work"); marked = true; }
        main.innerHTML = `<span class="ic">${esc(it.icon || "•")}</span> `
          + `<b>${esc(it.ref)}</b> ${esc(it.title || "(untitled)")}`
          + `<span class="meta"> — ${esc(it.module_name)} · ${esc(it.state)}`
          + (it.due ? ` · due ${esc(it.due)}` : "")
          + (it.reason === "assigned" ? " · assigned to you" : "") + `</span>`;
        main.onclick = () => open(it);
        row.appendChild(main);

        const acts = document.createElement("span");
        acts.className = "wq-acts";
        for (const a of it.actions) {
          if (it.blocked_actions.includes(a)) {
            // Needs a form, not a click. Say which, and go there.
            const link = document.createElement("button");
            link.className = "wq-act wq-act-form";
            link.textContent = `${a}…`;
            link.title = `${a} needs fields filled in — opens the record`;
            link.onclick = () => open(it);
            acts.appendChild(link);
            continue;
          }
          const btn = document.createElement("button");
          btn.className = "wq-act";
          btn.textContent = a;
          btn.title = `${a} — ${it.ref}`;
          btn.onclick = async () => {
            btn.disabled = true;
            try {
              await ctx.host.api.transitionRecord(pid, it.module, it.id, a);
              toast(`${it.ref}: ${a}`, "success");
              await load();                     // the queue is the point — stay in it
            } catch (e) {
              btn.disabled = false;
              toast(`Couldn't ${a} ${it.ref}: ${(e as Error).message}`, "error");
            }
          };
          acts.appendChild(btn);
        }
        if (!it.actions.length) {
          const w = document.createElement("span");
          w.className = "meta"; w.textContent = "waiting on someone else";
          acts.appendChild(w);
        }
        row.appendChild(acts);
        card.appendChild(row);
      }
      body.appendChild(card);
    }
    restoreFocus();
  }

  await load();
}
