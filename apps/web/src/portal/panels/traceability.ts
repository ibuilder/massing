import { money as cmoney } from "../../ui/charts";
import { noProjectHtml } from "../../ui/empty";
import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * Cost traceability by IFC GlobalId — the model→cost→GL link no cost-code-only stack can make. Shows
 * how much of the job's cost is tied to actual model elements (coverage) per cost code, and looks up
 * "what did this element cost?" by GlobalId.
 */
export async function renderTraceability(ctx: PanelContext) {
  const root = ctx.root; root.innerHTML = "";
  const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
  root.appendChild(ctx.bar("🔗 Cost Traceability", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
  const pid = ctx.host.projectId();
  if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Cost Traceability")); return; }

  const intro = el("div", "meta"); intro.style.marginBottom = "8px";
  intro.innerHTML = "Every cost record can be tagged with the <b>IFC elements</b> it pays for (by GlobalId). "
    + "That makes cost and billing defensible against the model — click an element, see what it cost. "
    + "Coverage = the share of cost tied to real model elements.";
  root.appendChild(intro);
  const body = el("div"); body.textContent = "loading…"; root.appendChild(body);

  let s;
  try { s = await ctx.host.api.costTraceability(pid); }
  catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
  body.innerHTML = "";
  const usd = (n: number) => cmoney(n);

  // coverage KPIs
  const cards = el("div"); cards.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px";
  const col = s.coverage_pct >= 75 ? "var(--status-good)" : s.coverage_pct >= 40 ? "var(--status-warn)" : "var(--status-crit)";
  const card = (label: string, value: string, c?: string, sub?: string) => {
    const cc = el("div", "dash-card"); cc.style.cssText = `min-width:110px${c ? `;border-left:3px solid ${c}` : ""}`;
    cc.innerHTML = `<div style="font-size:18px;font-weight:600${c ? `;color:${c}` : ""}">${value}</div>`
      + `<div class="meta">${label}</div>` + (sub ? `<div class="meta" style="font-size:10px">${sub}</div>` : "");
    return cc;
  };
  cards.append(
    card("Coverage", `${s.coverage_pct}%`, col, `${usd(s.traceable_cost)} of ${usd(s.total_cost)}`),
    card("Untraceable", usd(s.untraceable_cost), s.untraceable_cost ? "var(--status-warn)" : undefined, "not tagged"),
    card("Elements", `${s.elements_referenced}`, undefined, `${s.line_count} cost lines`));
  body.append(cards);

  // GUID lookup — "what did this element cost?"
  const look = el("div", "dash-card"); look.style.marginBottom = "8px";
  look.innerHTML = `<b>What did this element cost?</b>`;
  const row = el("div"); row.style.cssText = "display:flex;gap:6px;margin-top:4px;flex-wrap:wrap";
  const gi = el("input") as HTMLInputElement; gi.type = "text"; gi.placeholder = "Paste an IFC GlobalId";
  gi.style.cssText = "flex:1;min-width:180px;padding:4px 6px;border:1px solid var(--line);border-radius:4px;background:var(--bg,#fff);color:inherit;font-size:12px";
  const go = el("button", "portal-btn"); go.textContent = "Look up";
  const out = el("div", "meta"); out.style.marginTop = "4px";
  const lookup = async () => {
    const g = gi.value.trim(); if (!g) return;
    out.textContent = "…";
    try {
      const r = await ctx.host.api.elementCosts(pid, g);
      out.innerHTML = r.count
        ? `<b>${usd(r.total)}</b> across ${r.count} line(s): ` + r.lines.map((l) => `${esc(l.kind)} ${usd(l.amount)}`).join(", ")
        : "No cost tagged to that GlobalId.";
    } catch (e) { out.textContent = `failed: ${(e as Error).message}`; }
  };
  go.addEventListener("click", () => void lookup());
  gi.addEventListener("keydown", (e) => { if ((e as KeyboardEvent).key === "Enter") void lookup(); });
  row.append(gi, go); look.append(row, out); body.append(look);

  // per-cost-code coverage — and the elements behind each figure
  if (s.by_cost_code.length) {
    const h = el("div", "meta"); h.style.cssText = "font-weight:700;margin:6px 0 2px";
    h.textContent = "Coverage by cost code";
    const hint = el("div", "meta"); hint.style.cssText = "font-size:11px;margin-bottom:4px";
    hint.textContent = "Click a row to see the model elements behind that number.";
    const tbl = el("table", "portal-table") as HTMLTableElement; tbl.style.cssText = "width:100%;font-size:12px";
    tbl.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Cost code</th><th scope="col">Total</th>`
      + `<th scope="col">Traceable</th><th scope="col">Elements</th><th scope="col">Coverage</th></tr></thead>`;
    const tb = el("tbody") as HTMLTableSectionElement;

    for (const r of s.by_cost_code) {
      const c = r.coverage_pct >= 75 ? "var(--status-good)"
        : r.coverage_pct >= 40 ? "var(--status-warn)" : "var(--status-crit)";
      const tr = el("tr") as HTMLTableRowElement;
      // Only rows with elements are openable. A row with nothing behind it must not offer a
      // disclosure that reveals an empty box — that is the "click here for nothing" pattern the
      // coverage number is meant to warn you about in the first place.
      const openable = r.element_count > 0;
      if (openable) { tr.style.cursor = "pointer"; tr.tabIndex = 0; tr.setAttribute("aria-expanded", "false"); }
      tr.innerHTML = `<td>${openable ? "<span class=\"trc-caret\">▸</span> " : ""}${esc(r.cost_code)}</td>`
        + `<td style="text-align:right">${usd(r.total)}</td>`
        + `<td style="text-align:right">${usd(r.traceable)}</td>`
        + `<td style="text-align:right">${r.element_count || "—"}</td>`
        + `<td style="text-align:right;color:${c}">${r.coverage_pct}%</td>`;
      tb.appendChild(tr);

      if (!openable) continue;
      const det = el("tr") as HTMLTableRowElement;
      det.hidden = true;
      const cell = el("td") as HTMLTableCellElement;
      cell.colSpan = 5; cell.style.cssText = "padding:6px 10px;background:var(--hover,rgba(255,255,255,.03))";
      // The count is exact; the list may be a sample. Say so rather than letting 200 rows imply 200
      // elements — a truncated list presented as complete is the same defect as a fabricated number.
      const shown = r.guids.length;
      const capped = shown < r.element_count;
      const lead = el("div", "meta");
      lead.style.cssText = "font-size:11px;margin-bottom:4px";
      lead.textContent = capped
        ? `${r.element_count} elements — showing the first ${shown}`
        : `${r.element_count} element${r.element_count === 1 ? "" : "s"}`;
      const list = el("div");
      list.style.cssText = "display:flex;flex-wrap:wrap;gap:4px;max-height:150px;overflow:auto";
      for (const g of r.guids) {
        const b = el("button", "portal-btn") as HTMLButtonElement;
        b.type = "button";
        b.style.cssText = "font-family:ui-monospace,monospace;font-size:10px;padding:1px 5px";
        b.textContent = g;                                   // textContent: a GUID is server data
        b.title = `Look up what ${g} cost`;
        // Reuse the lookup that already exists rather than adding a second way to ask the same
        // question — one implementation, one answer.
        b.addEventListener("click", () => { gi.value = g; void lookup(); look.scrollIntoView({ block: "nearest" }); });
        list.appendChild(b);
      }
      cell.append(lead, list); det.appendChild(cell); tb.appendChild(det);

      const toggle = () => {
        det.hidden = !det.hidden;
        tr.setAttribute("aria-expanded", String(!det.hidden));
        const caret = tr.querySelector(".trc-caret");
        if (caret) caret.textContent = det.hidden ? "▸" : "▾";
      };
      tr.addEventListener("click", toggle);
      tr.addEventListener("keydown", (e) => {
        const k = (e as KeyboardEvent).key;
        if (k === "Enter" || k === " ") { e.preventDefault(); toggle(); }
      });
    }
    tbl.appendChild(tb);
    body.append(h, hint, tbl);
  }
}
