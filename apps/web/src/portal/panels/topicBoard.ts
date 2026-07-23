import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * TOPIC-BOARD panel — the BCF kanban: columns by status/priority/assignee/type in stable workflow order
 * (server-computed), with a QUERY-DSL smart-filter box (`status=open & priority=High`, `title~duct`).
 * Read-only board view over /topics/board; every topic value is escaped (issue titles are free text).
 */
const COL_COLOR: Record<string, string> = {
  "open": "#b42318", "in progress": "#9a6700", "in_progress": "#9a6700",
  "resolved": "#1a7f37", "closed": "#57606a", "reopened": "#b42318",
};

export async function renderTopicBoard(ctx: PanelContext) {
  const pid = ctx.host.projectId()!;
  ctx.root.innerHTML = "";
  ctx.root.appendChild(ctx.bar("🗂 Issue board", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));

  const controls = document.createElement("div");
  controls.className = "dash-card";
  controls.style.cssText = "display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px";
  controls.innerHTML = `<label class="meta" style="margin:0">Group by
      <select id="tb-group" style="margin-left:6px">
        <option value="status">Status</option><option value="priority">Priority</option>
        <option value="assignee">Assignee</option><option value="type">Type</option>
      </select></label>
    <input id="tb-filter" type="text" placeholder="Filter — e.g. status=open & priority=High, title~duct"
      style="flex:1;min-width:220px;padding:6px 8px;font-size:12px">
    <button id="tb-apply" class="btn">Apply</button>
    <span id="tb-count" class="meta" style="margin:0"></span>`;
  ctx.root.appendChild(controls);

  const body = document.createElement("div");
  ctx.root.appendChild(body);

  async function load() {
    const groupBy = (controls.querySelector("#tb-group") as HTMLSelectElement).value as
      "status" | "priority" | "assignee" | "type";
    const filter = (controls.querySelector("#tb-filter") as HTMLInputElement).value.trim() || undefined;
    body.innerHTML = `<div class="meta">Loading the board…</div>`;
    try {
      const b = await ctx.host.api.topicsBoard(pid, groupBy, filter);
      (controls.querySelector("#tb-count") as HTMLElement).textContent =
        `${b.total} topic(s) · ${b.column_count} column(s)`;
      body.replaceChildren();
      if (!b.total) {
        body.innerHTML = `<div class="meta">No topics match${filter ? " this filter" : ""} — issues, RFIs and clashes land here.</div>`;
        return;
      }
      const lanes = document.createElement("div");
      lanes.style.cssText = "display:flex;gap:10px;align-items:flex-start;overflow-x:auto;padding-bottom:6px";
      for (const col of b.columns) {
        const lane = document.createElement("div");
        lane.className = "dash-card";
        lane.style.cssText = "min-width:230px;max-width:280px;flex:0 0 auto;padding:10px";
        const color = COL_COLOR[col.key.toLowerCase()] || "#57606a";
        lane.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px">`
          + `<b style="color:${color};text-transform:capitalize">${esc(col.key)}</b>`
          + `<span class="meta" style="margin:0">${col.count}</span></div>`;
        const list = document.createElement("div");
        list.style.cssText = "display:flex;flex-direction:column;gap:6px";
        for (const t of col.topics.slice(0, 50)) {
          const card = document.createElement("div");
          card.style.cssText = "border:1px solid var(--border,#e5e7eb);border-radius:8px;padding:7px 9px;font-size:12px;cursor:pointer";
          card.title = "Click for the topic timeline";
          card.innerHTML = `<div style="font-weight:600">${esc(t.title)}</div>`
            + `<div class="meta" style="margin:2px 0 0;display:flex;gap:8px;flex-wrap:wrap">`
            + `<span>${esc(t.type)}</span>`
            + (t.priority ? `<span>${esc(t.priority)}</span>` : "")
            + (t.assignee ? `<span>@${esc(t.assignee)}</span>` : "")
            + (t.due_date ? `<span>due ${esc(t.due_date.slice(0, 10))}</span>` : "")
            + `</div>`;
          // TOPIC-LIFE: click toggles an inline timeline drawer (merged history, oldest→newest)
          let drawer: HTMLElement | null = null;
          card.onclick = async () => {
            if (drawer) { drawer.remove(); drawer = null; return; }
            drawer = document.createElement("div");
            drawer.style.cssText = "margin-top:6px;border-top:1px dashed var(--border,#e5e7eb);padding-top:5px";
            drawer.innerHTML = `<div class="meta">loading…</div>`;
            card.appendChild(drawer);
            try {
              const tl = await ctx.host.api.topicTimeline(pid, t.id);
              drawer.innerHTML = tl.events.slice(-12).map((e) =>
                `<div style="display:flex;gap:6px;margin:2px 0;font-size:11px">`
                + `<span class="meta" style="margin:0;white-space:nowrap">${e.ts ? esc(e.ts.slice(0, 16).replace("T", " ")) : ""}</span>`
                + `<span>${e.kind === "comment" ? "💬 " : ""}${e.detail?.reply_to ? "↳ " : ""}${esc(e.summary)}${e.actor ? ` <i class="meta" style="margin:0">— ${esc(e.actor)}</i>` : ""}</span>`
                + `</div>`).join("")
                + (tl.event_count > 12 ? `<div class="meta" style="opacity:.7">…${tl.event_count - 12} earlier event(s)</div>` : "")
                + (tl.allowed_next.length ? `<div class="meta" style="margin-top:3px;opacity:.8">next: ${tl.allowed_next.map(esc).join(" · ")}</div>` : "");
            } catch (e) {
              drawer.innerHTML = `<div class="meta">timeline unavailable: ${esc((e as Error).message)}</div>`;
            }
          };
          list.appendChild(card);
        }
        if (col.topics.length > 50) {
          list.insertAdjacentHTML("beforeend", `<div class="meta" style="opacity:.7">+${col.topics.length - 50} more</div>`);
        }
        lane.appendChild(list);
        lanes.appendChild(lane);
      }
      body.appendChild(lanes);
      const note = document.createElement("div");
      note.className = "meta"; note.style.cssText = "margin-top:8px;opacity:.8";
      note.textContent = b.note;
      body.appendChild(note);
    } catch (e) {
      body.innerHTML = `<div class="meta">Board unavailable: ${esc((e as Error).message)}</div>`;
    }
  }

  (controls.querySelector("#tb-apply") as HTMLButtonElement).onclick = () => void load();
  (controls.querySelector("#tb-group") as HTMLSelectElement).onchange = () => void load();
  (controls.querySelector("#tb-filter") as HTMLInputElement).onkeydown = (e) => {
    if (e.key === "Enter") void load();
  };
  await load();
}
