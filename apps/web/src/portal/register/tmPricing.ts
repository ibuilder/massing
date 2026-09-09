import type { ModuleDef, ModuleRecord } from "../../api/client";
import type { TmPricingReport } from "../../api/cost";
import type { PortalHost } from "../portal";
import { rate as rateFmt, usd } from "../../ui/charts";
import { escapeHtml as esc } from "../../ui/feedback";

/**
 * TM-RATES — price a T&M ticket from the project's rate registers, on the ticket.
 *
 * ## What was missing
 *
 * `labor_rate`, `material_rate` and `equipment_rate` are registers a project fills in once: trade →
 * $/hr, material → unit price, equipment → $/hr. Certified payroll reads `labor_rate`. Nothing
 * else did. A superintendent filing an eTicket typed the rate onto every line by hand, and the rate
 * on a T&M ticket is precisely the number that gets argued about when the change order is
 * negotiated — a typo there is money, and a rate that quietly disagrees with the contract rate
 * table is worse than a blank one.
 *
 * The engine to fix that shipped in June (`cost.price_ticket_lines`, then `cost.price_tm`) and
 * **had no caller in this application at all**: no button, no client method, not even a stale one.
 * It was found by asking which route body parameters nothing in the web tree ever sends —
 * `eticket_id` was required by a route and named nowhere.
 *
 * ## Why the control reports rather than just acting
 *
 * Pricing is not a total: it is a per-row claim about what work costs. So the run answers for every
 * row it did NOT price, and the panel shows all four answers —
 *
 * - `filled` — a blank rate the register supplied. The feature.
 * - `variance` — a typed rate that disagrees with the register. **Left as typed**, and shown. A GC
 *   wants to see that before signing; silently overwriting it is how a ticket stops matching the
 *   agreement it is evidence for.
 * - `unmatched` — a trade or material no register knows. Left alone, and named, so the fix (add it
 *   to the register) is obvious.
 * - `unpriced` — overtime and idle hours. Neither register holds an OT or idle rate, so those hours
 *   are reported, never multiplied by an assumed 1.5x. **A multiplier nobody agreed to is a
 *   contract term, not a default.**
 *
 * A run that changes nothing says so, rather than looking like a run that failed.
 */

/** The only module this control belongs on — the register whose lines the rate tables price. */
export const TM_MODULE = "eticket";

/** What the panel needs from the host, so it can be driven in a test without standing one up. */
export interface TmPricingHost {
  api: { priceTicket: PortalHost["api"]["priceTicket"] };
}

/**
 * One report line. `tone` is a CSS variable, not a literal colour, so the three warning shades stay
 * on the app's palette in both themes — the omission `cssVars` (CSS-VAR-VOID) was built to catch.
 */
function line(text: string, tone?: string): HTMLElement {
  const d = document.createElement("div");
  d.className = "meta";
  if (tone) d.style.color = tone;
  d.textContent = text;
  return d;
}

/** Render one pricing run's report into `box`. Exported so a test can assert on the report alone. */
export function renderTmReport(box: HTMLElement, rep: TmPricingReport): void {
  box.innerHTML = "";
  const t = rep.totals;
  box.appendChild(line(
    `${rep.priced} line(s) priced · labour ${usd(t.labor_total)} · material ${usd(t.material_total)}`
    + ` · equipment ${usd(t.equipment_total)} · total ${usd(t.grand_total)}`));
  if (!rep.priced) {
    box.appendChild(line("Nothing changed — every line already carries the rate it prices at.",
      "var(--muted)"));
  }
  for (const f of rep.filled) {
    box.appendChild(line(`✓ ${f.name}: rate ${rateFmt(f.rate)} from the register`));
  }
  // A disagreement with the rate table is the finding this control exists to surface, so it is
  // stated in full — both numbers — and never quietly resolved in either direction.
  for (const v of rep.variance) {
    // `field` distinguishes the two: a rate that disagrees with the register, and an AMOUNT that
    // disagrees with rate x quantity — which is usually an overtime premium or a negotiated
    // allowance, and is exactly the figure that must not be silently recomputed away.
    box.appendChild(line(v.field === "amount"
      ? `⚠ ${v.name}: this line's amount is ${rateFmt(v.typed)} and rate × quantity is `
        + `${rateFmt(v.register)} — left as entered`
      : `⚠ ${v.name}: this line is at ${rateFmt(v.typed)} and the register says `
        + `${rateFmt(v.register)} — left as entered`, "var(--status-warn)"));
  }
  for (const u of rep.unmatched) {
    box.appendChild(line(
      `? ${u.name || "(no name)"}: not in ${u.register} — left as entered; add it to the register`
      + " to price this line", "var(--status-warn)"));
  }
  for (const u of rep.unpriced) {
    box.appendChild(line(
      `⏱ ${u.name}: ${u.quantity} ${u.column.replace("_", " ")} are NOT in the figures above — `
      + u.reason, "var(--status-warn)"));
  }
}

/**
 * The control itself. Returns null for every module but {@link TM_MODULE}, so the caller can append
 * unconditionally — a `null` guard at one call site beats a module test at the call site AND here.
 */
export function tmPricingControl(
  host: TmPricingHost, pid: string, m: ModuleDef, r: ModuleRecord, onReload: () => void,
): HTMLElement | null {
  if (m.key !== TM_MODULE) return null;
  const wrap = document.createElement("div");
  wrap.style.margin = "6px 0";
  const btn = document.createElement("button");
  btn.className = "tool-btn";
  btn.textContent = "💲 Price from rate tables";
  btn.title = "Fill each line's rate from the project's labour / material / equipment registers and"
    + " recompute its amount. A rate already entered is kept and reported, never overwritten.";
  const out = document.createElement("div");
  out.style.marginTop = "4px";
  btn.onclick = async () => {
    btn.disabled = true;
    out.innerHTML = `<div class="meta">pricing ${esc(r.ref ?? "ticket")}…</div>`;
    try {
      const rep = await host.api.priceTicket(pid, r.id);
      renderTmReport(out, rep);
      // Deliberately NOT auto-reloading. `openRecord` repaints the whole record, which would
      // destroy the report in the same tick it appeared — and the report, not the total, is what
      // the user asked for: which line disagrees with the register, and which hours nothing could
      // price. So the stale fields above are NAMED and reloading is offered as a choice.
      if (rep.priced) {
        const again = document.createElement("button");
        again.className = "tool-btn";
        again.style.marginTop = "4px";
        again.textContent = "Reload the ticket to show the new totals";
        again.onclick = () => onReload();
        out.appendChild(again);
      }
    } catch (e) {
      out.innerHTML = "";
      out.appendChild(line(`pricing failed: ${(e as Error).message}`, "var(--status-crit)"));
    } finally {
      btn.disabled = false;
    }
  };
  wrap.append(btn, out);
  return wrap;
}
