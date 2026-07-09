import { lineChart, money as cmoney } from "../../ui/charts";
import { noProjectHtml } from "../../ui/empty";
import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * Earned Value Management dashboard (E4+E5) — surfaces the EVM engine: the indices dashboard
 * (CPI/SPI/SPI(t) with health bands), the EAC/ETC/VAC/TCPI forecast panel, the three-line S-curve
 * (PV/EV/AC), Earned Schedule (forecast finish), and the per-control-account (cost code) table.
 */

const BAND: Record<string, string> = {
  good: "var(--status-good)", acceptable: "var(--status-warn)",
  concerning: "var(--status-warn)", critical: "var(--status-crit)", no_data: "var(--muted)",
};

export async function renderEvm(ctx: PanelContext) {
  const root = ctx.root; root.innerHTML = "";
  const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
  root.appendChild(ctx.bar("📊 Earned Value (EVM)", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
  const pid = ctx.host.projectId();
  if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Earned Value")); return; }
  const intro = el("div", "meta"); intro.style.marginBottom = "8px";
  intro.innerHTML = "Cost + schedule performance against the baseline, joined by cost code. Needs "
    + "<b>schedule activities</b> with a budget + % complete (for EV/PV) and <b>direct costs</b> by cost "
    + "code (for AC). CPI/SPI &lt;1 = over budget / behind; the forecast family projects the final cost.";
  root.appendChild(intro);
  const pdf = el("a", "portal-btn") as HTMLAnchorElement; pdf.textContent = "⬇ EVM report (PDF)";
  pdf.href = ctx.host.api.reportUrl(pid, "evm", "pdf"); pdf.target = "_blank"; pdf.rel = "noopener";
  root.appendChild(pdf);
  const body = el("div"); body.style.marginTop = "8px"; body.textContent = "loading…"; root.appendChild(body);

  let d; let sc; let mev;
  try {
    d = await ctx.host.api.evm(pid);
    sc = await ctx.host.api.evmScurve(pid).catch(() => null);
    mev = await ctx.host.api.evmModelEv(pid).catch(() => null);
  } catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
  body.innerHTML = "";
  const t = d.totals;
  if (!t.bac) {
    body.innerHTML = `<div class="meta">No budgeted schedule activities yet — add activities with a <b>budget</b> and <b>% complete</b> (Schedule) and <b>direct costs</b> by cost code to compute EVM.</div>`;
    return;
  }
  const usd = (n: number | null) => (n == null ? "—" : cmoney(n));
  const idx = (v: number | null) => (v == null ? "—" : v.toFixed(2));

  // --- indices dashboard ---
  const cards = el("div"); cards.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px";
  const card = (label: string, value: string, color?: string, sub?: string) => {
    const c = el("div", "dash-card"); c.style.cssText = `min-width:104px${color ? `;border-left:3px solid ${color}` : ""}`;
    c.innerHTML = `<div style="font-size:19px;font-weight:600${color ? `;color:${color}` : ""}">${value}</div>`
      + `<div class="meta">${label}</div>` + (sub ? `<div class="meta" style="font-size:10px">${sub}</div>` : "");
    return c;
  };
  const es = d.earned_schedule;
  cards.append(
    card("CPI (cost)", idx(t.cpi), BAND[t.cpi_band], `CV ${usd(t.cv)}`),
    card("SPI ($ sched)", idx(t.spi), BAND[t.spi_band], `SV ${usd(t.sv)}`),
    card("SPI(t) (time)", es ? idx(es.spi_t) : "—", es ? BAND[es.spi_t_band] : undefined,
      es ? `SV(t) ${es.sv_t_periods} ${es.period}s` : "earned schedule"),
    card("% complete", `${t.percent_complete}%`, undefined, `% spent ${t.percent_spent}%`),
    card("BAC", usd(t.bac), undefined, `EV ${usd(t.ev)} · AC ${usd(t.ac)}`));
  body.append(cards);

  // --- S-curve ---
  if (sc && sc.pv?.length) {
    const wrap = el("div", "dash-card"); wrap.style.marginBottom = "8px";
    wrap.innerHTML = lineChart([
      { name: "PV (planned)", values: sc.pv, color: "#5a9bd4" },
      { name: "EV (earned)", values: sc.ev, color: "#2e9e5b" },
      { name: "AC (actual)", values: sc.ac, color: "#d9822b" },
    ], { title: "Cost / schedule S-curve", fmt: (n) => cmoney(n), xlabels: sc.labels, height: 190 });
    body.append(wrap);
  }

  // --- forecast family ---
  const f = t.forecast;
  const fc = el("div", "dash-card"); fc.style.marginBottom = "8px";
  fc.innerHTML = `<b>Forecast at completion</b>`
    + `<table class="fin-table" style="width:100%;font-size:12px;margin-top:4px">`
    + `<tr><td>EAC — at current cost efficiency (BAC/CPI)</td><td class="num">${usd(f.eac.cpi)}</td></tr>`
    + `<tr><td>EAC — remaining at plan (AC+BAC−EV)</td><td class="num">${usd(f.eac.at_plan)}</td></tr>`
    + `<tr><td>EAC — cost + schedule drag (÷CPI·SPI)</td><td class="num">${usd(f.eac.cpi_spi)}</td></tr>`
    + `<tr class="fin-total"><td>Working EAC · ETC ${usd(f.etc)}</td><td class="num">${usd(f.eac_working)}</td></tr>`
    + `<tr><td>VAC (BAC − EAC)</td><td class="num" style="color:${(f.vac ?? 0) < 0 ? "var(--status-crit)" : "var(--status-good)"}">${usd(f.vac)}</td></tr>`
    + `<tr><td>TCPI to budget${f.tcpi_warning ? ' <span style="color:var(--status-crit)">⚠ &gt;1.10</span>' : ""}</td><td class="num">${idx(f.tcpi_bac)}</td></tr>`
    + `</table>`
    + (f.recommended ? `<div class="meta" style="margin-top:4px">📈 <b>${esc(f.recommended.stage)} stage</b> — ${esc(f.recommended.guidance)}</div>` : "");
  body.append(fc);

  // --- earned schedule forecast ---
  if (es && es.forecast_finish) {
    const esc2 = el("div", "dash-card"); esc2.style.marginBottom = "8px";
    esc2.innerHTML = `<b>Earned Schedule</b> <span class="meta">(time-based — stays valid at completion)</span>`
      + `<div class="meta" style="margin-top:2px">ES <b>${es.earned_schedule_periods}</b> of ${es.planned_duration_periods} ${es.period}s · `
      + `SPI(t) <b style="color:${BAND[es.spi_t_band]}">${idx(es.spi_t)}</b> · `
      + `forecast finish <b>${es.forecast_finish}</b>${es.days_late && es.days_late > 0 ? ` (<span style="color:var(--status-crit)">${es.days_late}d late</span>)` : ""}</div>`;
    body.append(esc2);
  }

  // --- model-based EV (physically installed elements) ---
  if (mev && mev.total_elements > 0) {
    const mc = el("div", "dash-card"); mc.style.cssText = `margin-bottom:8px${mev.front_loaded_flag ? ";border-left:3px solid var(--status-warn)" : ""}`;
    mc.innerHTML = `<b>Model-based EV</b> <span class="meta">(units-complete from installed model elements)</span>`
      + `<div class="meta" style="margin-top:2px">${mev.installed_elements} of ${mev.total_elements} elements installed = `
      + `<b>${mev.model_percent_complete}%</b> · EV(model) <b>${usd(mev.ev_model)}</b> vs EV(schedule) ${usd(mev.ev_schedule)}</div>`
      + (mev.front_loaded_flag
        ? `<div class="meta" style="color:var(--status-warn)">⚠ Reported progress is running ahead of physical installation (divergence ${usd(mev.divergence)}) — possible front-loaded SOV.</div>`
        : `<div class="meta">Schedule EV tracks physical installation (divergence ${usd(mev.divergence)}).</div>`);
    body.append(mc);
  }

  // --- control-account table ---
  if (d.control_accounts.length) {
    const tbl = el("table", "portal-table") as HTMLTableElement; tbl.style.cssText = "width:100%;font-size:12px";
    tbl.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Control account (cost code)</th>`
      + `<th scope="col">BAC</th><th scope="col">EV</th><th scope="col">AC</th><th scope="col">CV</th>`
      + `<th scope="col">SV</th><th scope="col">CPI</th><th scope="col">SPI</th></tr></thead><tbody>`
      + d.control_accounts.map((r) => {
        const cvc = r.cv < 0 ? "var(--status-crit)" : "var(--status-good)";
        const svc = r.sv < 0 ? "var(--status-warn)" : "var(--status-good)";
        return `<tr><td>${esc(r.cost_code)}</td><td style="text-align:right">${usd(r.bac)}</td>`
          + `<td style="text-align:right">${usd(r.ev)}</td><td style="text-align:right">${usd(r.ac)}</td>`
          + `<td style="text-align:right;color:${cvc}">${usd(r.cv)}</td><td style="text-align:right;color:${svc}">${usd(r.sv)}</td>`
          + `<td style="text-align:center">${idx(r.cpi)}</td><td style="text-align:center">${idx(r.spi)}</td></tr>`;
      }).join("") + `</tbody>`;
    const h = el("div", "meta"); h.style.cssText = "font-weight:700;margin:6px 0 2px"; h.textContent = "Control accounts (worst variance first)";
    body.append(h, tbl);
  }
}
