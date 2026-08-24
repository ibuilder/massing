/** Developer (real-estate) home — the persona landing screen for the RE workspace.
 *
 *  REL-4. Taken out of `portal.ts` as a genuine LEAF: it touched exactly two things on the class,
 *  `host` and `mods`, so it moves as a free function over a two-field context and nothing else in
 *  the class had to change. Measured by grepping its `this.` references BEFORE naming the slice.
 *
 *  **Its neighbour `renderDesignHome` did NOT come with it, and that is the point of the slice.**
 *  The two sit next to each other, are named alike, share a signature and are called on adjacent
 *  lines — and only this one is a leaf. `renderDesignHome` calls seven sibling methods, so moving it
 *  means inventing a callback bag: coupling added in the name of removing it. Adjacency in a file is
 *  not a relationship, which is the third time that has been written down here (SCALE-SEAM ㉑ and
 *  ㉒ are the other two) and the first time it was checked BEFORE choosing the slice.
 */
import type { ModuleDef } from "../../api/types";
import { countNarrative } from "../../ui/chips";
import { usd } from "../../ui/charts";
import type { PortalHost } from "../portal";

/** Exactly what this screen needs off the portal class — deliberately not the class itself. */
export interface DeveloperHomeCtx { host: PortalHost; mods: ModuleDef[] }

/** Developer (real-estate) home: deal returns + RE register KPIs (listings / comps / capital /
 *  leases / feasibility). Every card jumps to its register; underwriting lives one click away. */
export async function renderDeveloperHome(ctx: DeveloperHomeCtx, root: HTMLElement, pid: string,
    el: (tag: string, cls?: string) => HTMLElement, jump: (key: string, state?: string) => void) {
  const head = el("div", "section-title"); head.style.cssText = "display:flex;justify-content:space-between;align-items:center";
  head.append("Developer — real estate");
  const uw = el("button", "tool-btn") as HTMLButtonElement;
  uw.textContent = "Underwriting →"; uw.title = "Open the proforma / underwriting workspace";
  uw.onclick = () => window.dispatchEvent(new CustomEvent("aec:goto-workspace", { detail: "finance" }));
  head.append(uw); root.appendChild(head);

  // returns strip — blended proforma returns for the deal (hides cleanly if no proforma yet)
  const ret = el("div"); root.appendChild(ret);
  void ctx.host.api.portfolio().then((pf) => {
    if (!pf.deal_count) return;
    const t = pf.totals || {};
    const irr = (t.equity_irr as number | null) ?? pf.deals[0]?.equity_irr ?? null;
    const em = (t.equity_multiple as number | null) ?? pf.deals[0]?.equity_multiple ?? null;
    const card = el("div", "dash-card"); card.style.marginBottom = "10px";
    card.style.cssText += ";cursor:pointer";
    card.title = "Open underwriting"; card.onclick = () => window.dispatchEvent(new CustomEvent("aec:goto-workspace", { detail: "finance" }));
    const kpi = (v: string, l: string, tone?: string) =>
      `<div class="dash-card" style="flex:1;text-align:center"><div style="font-size:18px;font-weight:700${tone ? `;color:${tone}` : ""}">${v}</div><div class="meta">${l}</div></div>`;
    card.innerHTML = `<div class="meta" style="margin-bottom:6px">📊 Deal returns · ${pf.deal_count} scenario${pf.deal_count === 1 ? "" : "s"}</div>`
      + `<div class="dash-cols" style="display:flex;gap:8px">`
      + kpi(irr == null ? "—" : `${(irr * 100).toFixed(1)}%`, "Equity IRR", irr != null && irr >= 0.15 ? "var(--status-good)" : irr != null && irr < 0.08 ? "var(--status-warn)" : undefined)
      + kpi(em == null ? "—" : `${em.toFixed(2)}×`, "Equity multiple")
      + kpi(usd((t.equity as number) || 0), "Equity")
      + kpi(usd((t.loan as number) || 0), "Loan")
      + `</div>`;
    root.insertBefore(card, ret.nextSibling);
  }).catch(() => {});

  // RE register KPIs from the dashboard's per-module counts
  try {
    const d = await ctx.host.api.dashboard(pid);
    const cnt = (k: string) => d.by_module.find((m) => m.key === k)?.count ?? 0;
    const active = (k: string, states: string[]) => {
      const bm = d.by_module.find((m) => m.key === k); if (!bm) return 0;
      return states.reduce((s, st) => s + (bm.by_state[st] ?? 0), 0);
    };
    const kpis = el("div", "kpi-grid");
    const cards: [string, number, (() => void) | undefined][] = [
      ["Active listings", active("listing", ["active", "listed", "available"]) || cnt("listing"), () => jump("listing")],
      ["Comparables", cnt("comparable"), () => jump("comparable")],
      ["Investors", cnt("investor"), () => jump("investor")],
      ["Leases", cnt("lease"), () => jump("lease")],
      ["Feasibility", cnt("zoning"), () => jump("zoning")],
    ];
    for (const [label, val, onClick] of cards) {
      const c = el("div", "kpi" + (onClick ? " kpi-click" : "")) as HTMLElement;
      c.innerHTML = `<div class="kpi-v">${val}</div><div class="kpi-l">${label}</div>`;
      if (onClick) { c.onclick = onClick; c.tabIndex = 0; c.setAttribute("role", "button"); c.onkeydown = (e) => { if ((e as KeyboardEvent).key === "Enter") onClick(); }; }
      kpis.appendChild(c);
    }
    // UX-KPI — the one-line narrative band above the tiles, so the home says what the numbers mean
    // instead of leaving the reader to total them. Deterministic template text, never an LLM; a
    // register with nothing in it is simply absent rather than reported as a zero.
    const narrative = countNarrative(
      cards.map(([label, val]) => [val, label.toLowerCase()] as [number, string]),
      "No developer registers have records yet");
    const band = el("div", "kpi-narrative"); band.style.margin = "2px 0 6px";
    band.textContent = narrative;
    root.appendChild(band);
    root.appendChild(kpis);
  } catch { /* dashboard unavailable — KPI grid just omitted */ }

  // quick-create row for the common developer records
  const quick = el("div"); quick.style.cssText = "margin-top:10px";
  quick.innerHTML = `<div class="section-title">Quick add</div>`;
  const qrow = el("div"); qrow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-top:4px";
  for (const [k, lbl] of [["listing", "＋ Listing"], ["comparable", "＋ Comp"], ["investor", "＋ Investor"], ["lease", "＋ Lease"]] as const) {
    if (!ctx.mods.find((m) => m.key === k)) continue;
    const b = el("button", "tool-btn") as HTMLButtonElement; b.textContent = lbl;
    b.onclick = () => jump(k);
    qrow.appendChild(b);
  }
  quick.appendChild(qrow); root.appendChild(quick);
}
