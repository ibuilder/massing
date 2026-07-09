import { lineChart, money as cmoney, stackedBar } from "../../ui/charts";
import { noProjectHtml } from "../../ui/empty";
import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * Resource loading — the cost-loaded manpower histogram (by trade), the cumulative unit + cost
 * S-curves, over-allocation against an availability cap, and a leveling advisory (smooth work that
 * has CPM float). Reads `resource_assignment` records (activity + cost code + units + rate); falls
 * back to activity crew_size.
 */
export async function renderResourceLoading(ctx: PanelContext) {
  const root = ctx.root; root.innerHTML = "";
  const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
  root.appendChild(ctx.bar("👷 Resource loading", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
  const pid = ctx.host.projectId();
  if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Resource loading")); return; }

  const intro = el("div", "meta"); intro.style.marginBottom = "8px";
  intro.innerHTML = "Cost-loaded manpower from <b>resource assignments</b> (each ties a crew/equipment/material "
    + "+ rate to a schedule activity and cost code). Histogram = concurrent units per trade per week; the "
    + "availability <b>cap</b> flags over-allocation and drives the leveling advisory.";
  root.appendChild(intro);

  const ctrl = el("div"); ctrl.style.cssText = "display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap";
  const lbl = el("label", "meta"); lbl.textContent = "Availability cap (units/wk): ";
  const capI = el("input") as HTMLInputElement; capI.type = "number"; capI.min = "0"; capI.value = "25";
  capI.style.cssText = "width:80px;padding:4px 6px;border:1px solid var(--line);border-radius:4px;background:var(--bg,#fff);color:inherit";
  lbl.appendChild(capI);
  const pdf = el("a", "portal-btn") as HTMLAnchorElement; pdf.textContent = "⬇ Report (PDF)";
  pdf.href = ctx.host.api.reportUrl(pid, "resource_loading", "pdf"); pdf.target = "_blank"; pdf.rel = "noopener";
  ctrl.append(lbl, pdf); root.appendChild(ctrl);

  const body = el("div"); body.textContent = "loading…"; root.appendChild(body);

  const draw = async () => {
    const cap = Number(capI.value) || 0;
    body.textContent = "loading…";
    let ld; let lv;
    try {
      ld = await ctx.host.api.resourceLoading(pid, cap || undefined);
      lv = cap > 0 ? await ctx.host.api.resourceLeveling(pid, cap).catch(() => null) : null;
    } catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
    body.innerHTML = "";
    if (!ld.loads) {
      body.innerHTML = `<div class="meta">No resource-loaded work yet — add <b>Resource assignments</b> `
        + `(a crew/equipment + units + rate, linked to a schedule activity and cost code), or set a `
        + `<b>crew size</b> on activities, to build the manpower curve.</div>`;
      return;
    }
    // KPI cards
    const cards = el("div"); cards.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px";
    const card = (label: string, value: string, color?: string, sub?: string) => {
      const cc = el("div", "dash-card"); cc.style.cssText = `min-width:104px${color ? `;border-left:3px solid ${color}` : ""}`;
      cc.innerHTML = `<div style="font-size:19px;font-weight:600${color ? `;color:${color}` : ""}">${value}</div>`
        + `<div class="meta">${label}</div>` + (sub ? `<div class="meta" style="font-size:10px">${sub}</div>` : "");
      return cc;
    };
    const overCount = ld.over_allocation.length;
    cards.append(
      card("Peak units", `${ld.peak.units}`, overCount ? "var(--status-crit)" : undefined, ld.peak.week || ""),
      card("Total cost", cmoney(ld.total_cost), undefined, `${ld.weeks_span} weeks`),
      card("Over-allocated", `${overCount}`, overCount ? "var(--status-crit)" : "var(--status-good)", `weeks > cap ${cap}`),
      card("Source", ld.source === "resource_assignment" ? "assignments" : "crew size", undefined, `${ld.loads} loaded`));
    body.append(cards);

    // manpower histogram — stacked by trade per week
    const hist = el("div", "dash-card"); hist.style.marginBottom = "8px";
    hist.innerHTML = stackedBar(ld.histogram.map((w) => ({
      label: w.week.slice(5), segments: ld.trades.map((t) => ({ name: t, value: w.by_trade[t] || 0 })),
    })), { title: `Manpower histogram (units/week, by trade) · cap ${cap}`, fmt: (n) => `${n}`, height: 200 });
    body.append(hist);

    // cost S-curve
    const sc = el("div", "dash-card"); sc.style.marginBottom = "8px";
    sc.innerHTML = lineChart([{ name: "Cumulative cost", values: ld.cost_curve.map((p) => p.cumulative), color: "#2e9e5b" }],
      { title: "Cost S-curve (cumulative $)", fmt: (n) => cmoney(n), xlabels: ld.cost_curve.map((p) => p.week.slice(5)), height: 180 });
    body.append(sc);

    // leveling advisory
    if (lv && lv.suggestions.length) {
      const tbl = el("table", "portal-table") as HTMLTableElement; tbl.style.cssText = "width:100%;font-size:12px";
      tbl.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Smooth (has float)</th>`
        + `<th scope="col">Resource</th><th scope="col">Trade</th><th scope="col">Float (d)</th></tr></thead><tbody>`
        + lv.suggestions.map((s) => `<tr><td>${esc(s.activity)}</td><td>${esc(s.resource || "—")}</td>`
          + `<td>${esc(s.trade || "—")}</td><td style="text-align:center">${s.total_float_days}</td></tr>`).join("")
        + `</tbody>`;
      const h = el("div", "meta"); h.style.cssText = "font-weight:700;margin:6px 0 2px";
      h.textContent = `⚖ Leveling — ${lv.suggestions.length} smoothing candidate(s) over ${lv.over_weeks} peak week(s)`;
      const note = el("div", "meta"); note.style.fontSize = "10px"; note.textContent = lv.note;
      body.append(h, tbl, note);
    } else if (cap > 0 && lv) {
      const ok = el("div", "meta"); ok.style.margin = "4px 0";
      ok.textContent = "✅ Within the availability cap — no leveling needed.";
      body.append(ok);
    }
  };
  capI.addEventListener("change", () => void draw());
  await draw();
}
