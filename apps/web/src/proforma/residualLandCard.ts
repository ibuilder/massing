/** Residual land value — *what can you pay for the site?* — the inverse of every other number on
 *  this tab.
 *
 *  FIN-CALC shipped `services/api/src/aec_api/proforma/residual.py` and
 *  `POST /proforma/residual-land`, and `ApiClient.residualLand()` was written for it. **Nothing ever
 *  called it.** The engine bisects the land line over the same forward `solve()` the rest of the
 *  panel reports from, so the answer is consistent with the deal on screen rather than a second
 *  model — and it was reachable only from a script. Frozen in
 *  `apps/web/src/api/clientCallers.test.ts`'s `UNCALLED` list until this card.
 *
 *  WHY THIS IS THE CANONICAL DEVELOPER QUESTION. Every other figure here runs forward from a land
 *  price somebody typed. Site acquisition is the one number a developer actually negotiates, and the
 *  question at the table is not "what is this deal's IRR" but "what is the most I can pay and still
 *  clear my hurdle". That is a different solve, not a re-reading of the same one.
 *
 *  THREE CAVEATS THE ENGINE RETURNS, AND WHY ALL THREE ARE RENDERED
 *      `residual_land_value` is careful in a way a panel can easily throw away, and this repo's
 *      SCREEN-VS-REPORT axis is precisely the class of defect where it does:
 *
 *      * `land_value: null` — the target is unreachable **even at $0 land**. The engine's own note
 *        calls this *"the deal, not the dirt"*. Printing a land value here would be inventing one;
 *        printing nothing would read as a failure. It renders as the finding it is, with
 *        `at_zero_land` as the evidence.
 *      * `converged: false` with a number — the bisection hit its cap, so the figure is a **bracket
 *        endpoint, not a solution**. A panel that prints the money and drops the flag states a
 *        precision it does not have.
 *      * `bounds` — **was declared nowhere in this client.** The route returns it, the engine's
 *        docstring lists it, and `ApiClient.residualLand()`'s return type omitted it, so no
 *        unread-field audit in this tree could see it: every one of them starts from the declared
 *        interfaces. It is the honest answer in the un-converged case — the range the land value is
 *        known to lie in — which is exactly when it matters. Declared now, and read here.
 *
 *  It is deliberately NOT auto-solved on assumption edits. One residual solve is up to ~90 forward
 *  solves; firing that on every keystroke in the driver form would make the whole tab feel broken.
 */
import type { ApiClient } from "../api/client";
import { escapeHtml as esc } from "../ui/feedback";
import { money, pct } from "./format";

/** The five targets `proforma/residual.py::_TARGETS` supports, with how each one reads to a human. */
const TARGETS: { key: string; label: string; unit: "pct" | "x"; placeholder: number }[] = [
  { key: "equity_irr", label: "Equity IRR", unit: "pct", placeholder: 15 },
  { key: "project_irr", label: "Project IRR", unit: "pct", placeholder: 12 },
  { key: "equity_multiple", label: "Equity multiple", unit: "x", placeholder: 1.8 },
  { key: "yield_on_cost", label: "Yield on cost", unit: "pct", placeholder: 6.5 },
  { key: "profit_margin", label: "Profit margin", unit: "pct", placeholder: 15 },
];

export interface ResidualLandCtx {
  api: ApiClient;
  /** The live assumption set the rest of the tab is solving — read at click time, not captured. */
  assumptions: () => unknown;
  /** The land line's current amount, so the answer can be shown as a delta against what is typed. */
  currentLand: () => number | null;
  /** Write the solved value back into the land line and re-solve the forward deal. */
  applyLandValue: (v: number) => void;
  setStatus: (m: string) => void;
}

/** One cost line, as far as the land basis is concerned. */
export interface LandLine { category?: string; amount: number }

/** The land basis `proforma/residual.py` actually solves for: the FIRST `category: "land"` line.
 *
 *  Not `cost_lines[0]`, which is what the driver form's "Land $" field happens to be bound to — true
 *  of the default assumption set and not guaranteed of an adopted one. Reading the basis under a
 *  looser definition than the one it was SOLVED under is how an inverse answer stops reconciling with
 *  the deal it came from. */
export function landBasis(lines: readonly LandLine[]): number | null {
  const land = lines.find((l) => l.category === "land");
  return typeof land?.amount === "number" ? land.amount : null;
}

/** Write a solved residual back as the TOTAL land basis, mirroring `_with_land`: the first land line
 *  takes the value and any others are zeroed. A second land line left standing would make the forward
 *  re-solve carry more land than the answer allowed for, so the deal would quietly disagree with the
 *  number that produced it. Returns false when there is no land line to write to. */
export function applyLandBasis(lines: LandLine[], value: number): boolean {
  const land = lines.filter((l) => l.category === "land");
  if (!land.length) return false;
  land[0]!.amount = value;
  for (const extra of land.slice(1)) extra.amount = 0;
  return true;
}

/** Render one metric value in the unit its target uses — a multiple is not a percentage. */
function metric(v: number | null, unit: "pct" | "x"): string {
  if (v == null) return "n/a";
  return unit === "pct" ? pct(v) : `${v.toFixed(2)}x`;
}

export function renderResidualLandCard(root: HTMLElement, ctx: ResidualLandCtx): void {
  const host = document.createElement("div");
  host.id = "pf-residual-land";
  host.style.cssText = "margin:8px 0;padding:8px 10px;border:1px dashed var(--line);border-radius:8px";
  host.innerHTML = `<div class="section-title" style="margin:0 0 6px">🪙 Residual land value — what can you pay for the site?</div>`
    + `<div class="meta" style="margin-bottom:6px">The inverse solve: bisects the land line over the same forward model `
    + `every other number here comes from, until the chosen return hits your target.</div>`;

  const grid = document.createElement("div"); grid.className = "pf-form";
  const field = (label: string) => {
    const w = document.createElement("label"); w.className = "pf-field";
    w.innerHTML = `<span>${esc(label)}</span>`; grid.appendChild(w); return w;
  };

  const tWrap = field("Target");
  const tSel = document.createElement("select"); tSel.className = "portal-filter";
  for (const t of TARGETS) {
    const o = document.createElement("option"); o.value = t.key; o.textContent = t.label; tSel.appendChild(o);
  }
  tWrap.appendChild(tSel);

  const vWrap = field("Target value");
  const vInp = document.createElement("input"); vInp.type = "number"; vInp.step = "any";
  vWrap.appendChild(vInp);

  const mWrap = field("Max land $ (optional)");
  const mInp = document.createElement("input"); mInp.type = "number"; mInp.step = "any";
  mInp.placeholder = "auto";
  mInp.title = "Upper bracket for the search. Left empty the engine widens from 2x non-land cost.";
  mWrap.appendChild(mInp);

  /** Keep the value box in the unit the selected target is actually measured in. */
  const syncUnit = () => {
    const t = TARGETS.find((x) => x.key === tSel.value) ?? TARGETS[0]!;
    vWrap.querySelector("span")!.textContent = t.unit === "pct" ? "Target value (%)" : "Target multiple (x)";
    vInp.placeholder = String(t.placeholder);
    if (vInp.value.trim() === "") vInp.value = String(t.placeholder);
  };
  tSel.onchange = syncUnit;
  syncUnit();
  host.appendChild(grid);

  const out = document.createElement("div"); out.style.cssText = "margin-top:6px";
  // `file-btn`, not `btn`: **`.btn` matches no rule in `style.css`**, so a button carrying it renders
  // as a browser default beside styled siblings. Six files under `portal/panels/` use it and this card
  // copied them; every button in `proforma/` uses `file-btn` or `tool-btn`, which is the convention
  // that actually has CSS behind it. A class name is not a style, and nothing typechecks the gap.
  const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Solve residual land";
  const applyBtn = document.createElement("button"); applyBtn.className = "file-btn";
  applyBtn.textContent = "Apply to the deal"; applyBtn.style.display = "none"; applyBtn.style.marginLeft = "6px";
  const actions = document.createElement("div"); actions.style.cssText = "margin-top:6px";
  actions.appendChild(go); actions.appendChild(applyBtn);
  host.appendChild(actions); host.appendChild(out);
  root.appendChild(host);

  go.onclick = async () => {
    const t = TARGETS.find((x) => x.key === tSel.value) ?? TARGETS[0]!;
    const raw = parseFloat(vInp.value);
    if (!isFinite(raw)) { out.innerHTML = `<div class="meta">Enter a target value.</div>`; return; }
    const targetValue = t.unit === "pct" ? raw / 100 : raw;
    const maxLand = mInp.value.trim() === "" ? undefined : parseFloat(mInp.value);
    go.disabled = true; applyBtn.style.display = "none";
    out.innerHTML = `<div class="meta">bisecting the land line…</div>`;
    ctx.setStatus("solving residual land value…");
    try {
      const r = await ctx.api.residualLand(ctx.assumptions(), t.key, targetValue,
                                           isFinite(maxLand as number) ? maxLand : undefined);
      const target = `${t.label} ${metric(targetValue, t.unit)}`;

      // INFEASIBLE — the target cannot be met even with free land. The engine says so and the panel
      // must not invent a number: what the user needs to know is that the shortfall is in the deal.
      if (r.land_value == null) {
        out.innerHTML = `<div style="font-weight:600;color:var(--status-crit)">Not achievable at any land price</div>`
          + `<div class="meta" style="margin-top:4px">Even at <strong>$0</strong> for the land this deal reaches `
          + `<strong>${esc(metric(r.at_zero_land, t.unit))}</strong> against your ${esc(target)} target — `
          + `so the gap is in the deal, not the dirt. Move rents, cost, exit cap or leverage, then re-solve.</div>`
          + (r.note ? `<div class="meta" style="margin-top:4px">${esc(r.note)}</div>` : "");
        ctx.setStatus(`residual land: ${t.label} unreachable at $0 land`);
        return;
      }

      const cur = ctx.currentLand();
      const delta = cur == null ? null : r.land_value - cur;
      const bounds = r.bounds;
      out.innerHTML =
        `<div style="font-size:22px;font-weight:600">${esc(money(r.land_value))}</div>`
        + `<div class="meta">is the most you can pay and still make ${esc(target)}`
        + (r.achieved != null ? ` (solve lands on ${esc(metric(r.achieved, t.unit))})` : "") + `.</div>`
        + (delta == null ? ""
           : `<div class="meta" style="margin-top:4px">Your land line is ${esc(money(cur!))} — `
             + `<strong${delta < 0 ? ' style="color:var(--status-crit)"' : ""}>${delta >= 0 ? "+" : "−"}${esc(money(Math.abs(delta)))}</strong> `
             + `${delta >= 0 ? "of headroom" : "over what the target supports"}.</div>`)
        // `converged: false` means the bisection hit its cap, so the figure above is a BRACKET
        // endpoint. `bounds` is the honest answer in that case and is the whole reason it is now
        // declared on the client type — see this module's header.
        + (r.converged ? `<div class="meta" style="margin-top:4px">Converged in ${r.iterations} solves.</div>`
           : `<div class="meta" style="margin-top:4px;color:var(--status-warn)">Did not converge in ${r.iterations} solves — `
             + `read this as a range, not a price`
             + (bounds && bounds.length === 2
                ? `: between <strong>${esc(money(bounds[0]!))}</strong> and <strong>${esc(money(bounds[1]!))}</strong>`
                : "")
             + `. Narrow it with a Max land $ near the figure above.</div>`);
      applyBtn.style.display = "";
      applyBtn.onclick = () => {
        ctx.applyLandValue(r.land_value!);
        ctx.setStatus(`land set to ${money(r.land_value!)} — re-solving`);
      };
      ctx.setStatus(`residual land ${money(r.land_value)} at ${t.label} ${metric(targetValue, t.unit)}`);
    } catch (e) {
      // The route 400s with the engine's own message when the assumption set has no `land` cost
      // line, which is reachable: a set adopted from elsewhere need not carry one.
      out.innerHTML = `<div class="meta" style="color:var(--status-crit)">${esc((e as Error).message)}</div>`;
      ctx.setStatus("residual land failed");
    } finally {
      go.disabled = false;
    }
  };
}
