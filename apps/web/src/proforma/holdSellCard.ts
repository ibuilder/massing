import type { ApiClient } from "../api/client";
import { money } from "../ui/charts";
import { escapeHtml as esc } from "../ui/feedback";

/** Hold versus sell — and the coverage of the answer (HOLDSELL-UNMEASURED).
 *
 *  `services/api/src/aec_api/hold_sell.py` answers the question an asset manager is actually asked:
 *  not "what is the IRR" but *"does another year of this beat the cheque today"*. It measures the
 *  hold case as the IRR of **incremental** cash flows against the net proceeds declined today —
 *  "holding costs you the cheque you did not take" — with cap drift as an explicit input because
 *  *"a bet nobody wrote down is the one that loses money"*.
 *
 *  `ApiClient.holdSell()` was callerless, so none of it was reachable.
 *
 *  ### Why the engine had to be fixed BEFORE this card existed
 *
 *  `_irr` returns None when the incremental flows never change sign, and for an **over-levered**
 *  asset that is structural: net proceeds today are negative, so the t=0 flow is positive, every
 *  later flow is non-negative, and there is no root. The engine was right to refuse — and
 *  `beats_hurdle` read the refusal as a failure, so `recommendation` came back **`"sell"`** with a
 *  note asserting that no hold period cleared the hurdle. Measured: NOI 500k at a 6% cap against a
 *  9M loan → net proceeds today **-833,333**, four of five periods unevaluable, `"sell"`.
 *
 *  *Wiring this card first would have shipped that verdict to a user*, which is why the engine now
 *  carries `coverage` and a third `unmeasured` state, and why this card renders the coverage on every
 *  answer rather than only when it is bad — the complement `services/api/test_verdict_coverage.py`
 *  requires of a consumer, and the one thing a source-level gate cannot prove.
 */

type HoldSell = Awaited<ReturnType<ApiClient["holdSell"]>>;

export interface HoldSellCtx {
  api: ApiClient;
  projectId: () => string | null | undefined;
  setStatus: (m: string) => void;
  /** Values the live deal already knows, so an asset manager is not retyping the underwriting. */
  prefill?: () => { noi?: number | null; cap?: number | null; sellingCostPct?: number | null };
}

/** The word for a recommendation, in the engine's own terms.
 *
 *  `unmeasured` is NOT folded into either call, and that is the whole point of the third state: a
 *  reader who sees "sell" acts on it. */
export const VERDICT: Record<string, { word: string; colour: string }> = {
  hold: { word: "HOLD", colour: "var(--status-good)" },
  sell: { word: "SELL", colour: "var(--status-warn)" },
  unmeasured: { word: "NO CALL — not enough of the horizon could be measured",
                colour: "var(--status-crit)" },
};

/** The coverage sentence, rendered on EVERY answer.
 *
 *  Returned even when coverage is complete, because "8 of 8 hold periods measured" is what makes the
 *  partial case legible as partial. A card that printed coverage only when it was short would train
 *  a reader to read its absence as completeness. */
export function coverageLine(r: HoldSell): string {
  const c = r.coverage;
  if (!c) return "";
  const head = `${c.measured} of ${c.hold_periods} hold period(s) measured`;
  if (!c.unevaluable_years?.length) return head + " — the recommendation covers the whole horizon.";
  return `${head}; year(s) ${c.unevaluable_years.join(", ")} could not be measured`
    + (c.reason ? ` — ${c.reason}` : "") + ".";
}

/** True when selling today costs money rather than producing a cheque. The headline for an
 *  over-levered asset, and the reason its hold case cannot be measured at all. */
export function isUnderwater(r: HoldSell): boolean {
  return !!r.sell_now && r.sell_now.net_proceeds <= 0;
}

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

export function renderHoldSellCard(root: HTMLElement, ctx: HoldSellCtx): HTMLElement {
  const host = document.createElement("div");
  host.id = "pf-holdsell";
  host.className = "fin-card";
  host.style.marginTop = "10px";
  host.innerHTML = `<div class="section-title">Hold versus sell</div>`
    + `<div class="meta">Does another year of this beat the cheque today? The hold case is the IRR of `
    + `<em>incremental</em> cash flows against the net proceeds you decline by not selling — and cap `
    + `drift is an input, because "hold" is a bet on the exit cap.</div>`;
  root.appendChild(host);

  const pre = ctx.prefill?.() ?? {};
  const form = document.createElement("div");
  form.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin:8px 0";
  const num = (label: string, value: number | null | undefined, step: string, title: string) => {
    const l = document.createElement("label"); l.className = "meta";
    l.style.cssText = "display:flex;flex-direction:column;gap:2px;flex:0 0 130px";
    l.textContent = label; l.title = title;
    const i = document.createElement("input"); i.type = "number"; i.step = step;
    i.className = "portal-filter"; i.style.cssText = "font-size:12px";
    if (value != null && Number.isFinite(value)) i.value = String(value);
    l.appendChild(i);
    form.appendChild(l);
    return i;
  };
  const noiI = num("NOI / year", pre.noi ?? null, "1000", "Today's net operating income");
  const capI = num("Exit cap now", pre.cap ?? null, "0.001", "Today's cap rate, as a decimal (0.055 = 5.5%)");
  const loanI = num("Loan balance", null, "1000", "The balance that would be paid off on a sale today");
  const costI = num("Selling cost", pre.sellingCostPct ?? 0.02, "0.001", "As a decimal (0.02 = 2%)");
  const growI = num("NOI growth %", 3, "0.1", "Annual NOI growth, in percent");
  const driftI = num("Cap drift bps/yr", 0, "1", "Positive bps = cap expansion = a worse exit");
  const amortI = num("Amortization / yr", 0, "1000", "Principal repaid each year");
  const capexI = num("Capex / yr", 0, "1000", "Capital spend that reduces the hold stream");
  const hurdleI = num("Hurdle %", 12, "0.1", "The return a hold has to beat");
  const yearsI = num("Horizon (years)", 10, "1", "How many hold periods to test");
  host.appendChild(form);

  const run = document.createElement("button"); run.className = "tool-btn on";
  run.textContent = "Compare";
  const out = document.createElement("div"); out.style.marginTop = "8px";
  host.append(run, out);

  const val = (i: HTMLInputElement) => (i.value.trim() === "" ? undefined : Number(i.value));

  run.onclick = async () => {
    const pid = ctx.projectId();
    if (!pid) { out.innerHTML = `<div class="meta">Open or save a project first.</div>`; return; }
    if (val(noiI) == null || val(capI) == null) {
      out.innerHTML = `<div class="meta">NOI and today's cap are both required — a hold/sell call `
        + `cannot be made without today's income and today's cap.</div>`;
      return;
    }
    run.disabled = true; out.innerHTML = `<div class="meta">comparing…</div>`;
    let r: HoldSell;
    try {
      r = await ctx.api.holdSell(pid, {
        noi_annual: val(noiI), exit_cap_now: val(capI), loan_balance_now: val(loanI) ?? 0,
        selling_cost_pct: val(costI) ?? 0.02, noi_growth_pct: val(growI) ?? 0,
        cap_drift_bps_per_year: val(driftI) ?? 0, annual_loan_amortization: val(amortI) ?? 0,
        capex_per_year: val(capexI) ?? 0,
      }, val(hurdleI) != null ? val(hurdleI)! / 100 : 0.12, val(yearsI) ?? 10);
    } catch (e) {
      out.innerHTML = `<div class="meta">Comparison failed: ${esc((e as Error).message)}</div>`;
      run.disabled = false; return;
    }
    run.disabled = false;
    // The engine's own refusal, rendered as a reason rather than as a zero.
    if (!r.computable) {
      out.innerHTML = `<div class="meta"><b>No call.</b> ${esc(r.reason ?? "")}</div>`;
      return;
    }
    const v = VERDICT[r.recommendation] ?? { word: esc(r.recommendation), colour: "var(--status-warn)" };
    const sell = r.sell_now;
    const rows = r.years.map((y) => `<tr><td>${y.hold_years}</td>`
      + `<td class="num">${pct(y.exit_cap)}</td>`
      + `<td class="num">${money(y.noi_at_exit)}</td>`
      + `<td class="num">${money(y.net_proceeds_at_exit)}</td>`
      // A null IRR is an em dash and a word, never a 0.0% — the defect this whole item is about.
      + `<td class="num">${y.incremental_irr == null
        ? `<span style="color:var(--status-crit)">not measurable</span>` : pct(y.incremental_irr)}</td>`
      + `<td>${y.incremental_irr == null ? "—" : (y.beats_hurdle ? "clears" : "below")}</td></tr>`).join("");
    out.innerHTML =
      `<div style="font-size:18px;font-weight:700;color:${v.colour}">${v.word}</div>`
      + (isUnderwater(r)
        ? `<div class="meta" style="color:var(--status-crit);margin-top:2px"><b>Selling today costs `
          + `${money(Math.abs(sell.net_proceeds))}</b> — the debt exceeds the net sale value, so there `
          + `is no cheque for a hold to be compared against.</div>`
        : `<div class="meta" style="margin-top:2px">Sell today: ${money(sell.gross_sale)} gross, `
          + `${money(sell.loan_payoff)} payoff → <b>${money(sell.net_proceeds)}</b> net at `
          + `${pct(sell.exit_cap)}.</div>`)
      + `<div class="meta" style="margin-top:4px">${esc(coverageLine(r))}</div>`
      + (r.breakeven_hold_years != null
        ? `<div class="meta">Breakeven hold: <b>${r.breakeven_hold_years} year(s)</b> at a `
          + `${pct(r.hurdle_rate)} hurdle.</div>`
        : "")
      + `<table class="fin-table" style="margin-top:6px"><thead><tr><th>Hold</th><th>Exit cap</th>`
      + `<th>NOI at exit</th><th>Net proceeds</th><th>Incremental IRR</th><th>vs hurdle</th></tr>`
      + `</thead><tbody>${rows}</tbody></table>`
      + `<div class="meta" style="margin-top:6px;opacity:.85">${esc(r.note)}</div>`;
    ctx.setStatus(`Hold/sell: ${v.word}`);
  };

  return host;
}
