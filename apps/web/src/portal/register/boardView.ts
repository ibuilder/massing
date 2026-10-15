import type { ModuleDef } from "../../api/types";
import { escapeHtml as esc } from "../../ui/feedback";
import { boardDepthNote, columnCount, columnCountTitle, extraStatesNote, noTransitionNote,
  workflowBasisNote } from "./boardRead";
import type { PanelContext } from "../panelContext";

/**
 * BOARD-SHIPPED — the kanban board, out of `register.ts`.
 *
 * **It left because of the extraction ratchet, and it is lazily imported because of the bundle
 * budget.** The three readings the board needed put `register.ts` 18 lines over its
 * `services/api/test_file_sizes.py` pin; the ratchet's precedent is that the file gives up lines
 * rather than the pin moving up. *This time the gate was run before the commit rather than after* —
 * the lesson the `qaSection.ts` entry in that same file records twice, once from each of us.
 *
 * `portal/*` is lazy by construction, so the dynamic import is belt-and-braces rather than load
 * bearing; the board is also a click-driven view that most sessions never open.
 */

export interface BoardViewDeps {
  skeleton: (msg: string) => void;
  openModule: () => void;
  openRecord: (rid: string) => void;
  /** Re-fetch and redraw after a successful transition. */
  rerender: () => void;
}

export async function renderBoardView(ctx: PanelContext, m: ModuleDef,
                                      d: BoardViewDeps): Promise<void> {
  const pid = ctx.host.projectId()!;
  d.skeleton(`Loading ${m.name} board…`);
  const data = await ctx.host.api.moduleBoard(pid, m.key);
  ctx.root.innerHTML = "";
  ctx.root.appendChild(ctx.bar(`${m.name} — board`, () => d.openModule()));
  const board = document.createElement("div");
  board.className = "kanban";
  for (const state of data.states) {
    const col = document.createElement("div");
    col.className = "kan-col";
    col.dataset.state = state;
    // This printed `(columns[state] ?? []).length` — the PAGE length. Measured at 205 records in
    // one state, the column serves 200 and the head said 200. `counts` carries the SQL GROUP BY
    // truth, and `columnCount` shows both when they differ.
    col.innerHTML = `<div class="kan-head" title="${esc(columnCountTitle(data, state))}">`
      + `${esc(state)} <span class="count">${esc(columnCount(data, state))}</span></div>`;
    col.ondragover = (e) => { e.preventDefault(); col.classList.add("over"); };
    col.ondragleave = () => col.classList.remove("over");
    col.ondrop = async (e) => {
      e.preventDefault();
      col.classList.remove("over");
      const rid = e.dataTransfer?.getData("rid");
      const from = e.dataTransfer?.getData("from");
      if (!rid || from === state) return;
      const tr = data.transitions.find((t: { from: string; to: string }) =>
        t.from === from && t.to === state);
      // `data.transitions` is the project's EFFECTIVE workflow now — it used to be the SHIPPED one,
      // so on an overridden project every drag offered here 409'd and the one that would have
      // worked was refused by this very line.
      if (!tr) { ctx.host.setStatus(noTransitionNote(data, from ?? "", state)); return; }
      try {
        await ctx.host.api.transitionRecord(pid, m.key, rid, tr.action);
        d.rerender();
      } catch (err) { ctx.host.setStatus(`blocked: ${(err as Error).message}`); }
    };
    for (const c of data.columns[state] ?? []) {
      const card = document.createElement("div");
      card.className = "kan-card";
      card.draggable = true;
      card.innerHTML = `<div class="kc-ref">${esc(c.ref)}</div>`
        + `<div class="kc-title">${esc(c.title ?? "")}</div>`
        + (c.assignee ? `<div class="kc-asg">@${esc(c.assignee)}</div>` : "");
      card.ondragstart = (e) => {
        e.dataTransfer?.setData("rid", c.id);
        e.dataTransfer?.setData("from", state);
      };
      card.onclick = () => d.openRecord(c.id);
      col.appendChild(card);
    }
    board.appendChild(col);
  }
  ctx.root.appendChild(board);
  // Three things the board had no way to say: a column deeper than the cap, a state holding
  // records the workflow does not declare, and a workflow this project overrides.
  for (const line of [boardDepthNote(data), extraStatesNote(data), workflowBasisNote(data)]) {
    if (!line) continue;
    const n = document.createElement("div");
    n.className = "meta";
    n.style.cssText = "margin-top:6px;font-size:11px";
    n.textContent = line;
    ctx.root.appendChild(n);
  }
}
