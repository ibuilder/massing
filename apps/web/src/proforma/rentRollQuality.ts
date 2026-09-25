/** Can you believe this rent roll? — the two CRE-R20 engines that answer that, and had no screen.
 *
 *  The Operations tab shows **face** numbers: base rent, in-place income, occupancy, WALT. Face rent
 *  is what a broker quotes. Two engines shipped to qualify it and neither was ever called —
 *  `ApiClient.netEffectiveRent()` and `ApiClient.rentRollScrub()` both sat in
 *  `apps/web/src/api/clientCallers.test.ts`'s `UNCALLED` list, reachable only from a script.
 *
 *  BOTH ENGINES ARE BUILT AROUND A REFUSAL, AND THE REFUSAL IS WHAT A PANEL DESTROYS.
 *
 *  `rent_scrub.py`'s module docstring states the rule outright: *"a check that cannot run says so …
 *  A scrub that reports 'no findings' because half its inputs were missing is worse than no scrub —
 *  it launders absent data into apparent confidence."* And `clean` is computed as
 *  `bool(ran) and not failed` — so **one** check running and passing, with six unable to run, is
 *  `clean: true`. A card that renders a green tick off that flag is the exact defect the engine was
 *  written to prevent, committed by its own consumer. So `clean` is never rendered alone here: the
 *  coverage is the headline and the flag is a qualifier on it.
 *
 *  `net_effective.py` is the same shape one level quieter. Its totals — `face_gpr_annual`,
 *  `concession_load_pct`, `face_to_ner_delta_*` — are summed over the **computable** leases only
 *  (`roll_up` filters to `ok` before summing), and `lease_count` is that subset's size, not the rent
 *  roll's. So with any `skipped_count > 0` the face GPR in this card is a DIFFERENT population from
 *  the "Base rent / yr" in the rent-roll card directly above it, and the two sit on one screen
 *  inviting the reader to subtract them. Said out loud rather than left to be noticed.
 *
 *  And `skipped` is capped at 50 while `skipped_count` is not, so the list can be a page of a larger
 *  set — the CLASH-TRUNC shape, where a screen reported over a partial matrix and declared it whole.
 *  The card says when it is showing a page.
 */
import type { ApiClient } from "../api/client";
import { escapeHtml as esc } from "../ui/feedback";
import { money, pct } from "./format";

type Ner = Awaited<ReturnType<ApiClient["netEffectiveRent"]>>;
type Scrub = Awaited<ReturnType<ApiClient["rentRollScrub"]>>;

const card = (title: string) => {
  const el = document.createElement("div");
  el.className = "fin-card";
  el.style.marginTop = "10px";
  el.innerHTML = `<div class="section-title">${esc(title)}</div>`;
  return el;
};

const meta = (html: string, colour?: string) =>
  `<div class="meta" style="margin-top:4px${colour ? `;color:${colour}` : ""}">${html}</div>`;

/** Net effective rent: what the rent roll is worth after concessions, and over which leases. */
export function renderNetEffective(host: HTMLElement, n: Ner): HTMLElement {
  const el = card("Net effective rent (after concessions)");

  if (n.lease_count === 0) {
    // Nothing computable. Saying "0" for every total would render an absence as a measurement.
    el.insertAdjacentHTML("beforeend", meta(
      n.skipped_count > 0
        ? `No lease carries the fields this needs — ${n.skipped_count} active lease(s) were skipped. `
          + `Net effective rent cannot be stated for this rent roll yet.`
        : `No active leases to value.`));
    host.appendChild(el);
    return el;
  }

  el.insertAdjacentHTML("beforeend",
    `<table class="fin-table">`
    + `<tr><td>Face GPR / yr</td><td class="num">${esc(money(n.face_gpr_annual))}</td></tr>`
    + `<tr><td>NER / yr (discounted @ ${esc(pct(n.discount_rate))})</td>`
    + `<td class="num">${esc(money(n.ner_gpr_annual_discounted))}</td></tr>`
    + `<tr><td>NER / yr (straight-line)</td>`
    + `<td class="num">${esc(money(n.ner_gpr_annual_straight_line))}</td></tr>`
    + `<tr><td>Concession load</td><td class="num">${n.concession_load_pct}%</td></tr>`
    + `<tr class="fin-total"><td>Face → NER</td>`
    + `<td class="num">−${esc(money(n.face_to_ner_delta_annual))} (${n.face_to_ner_delta_pct}%)</td></tr>`
    + `</table>`);

  // The discounted form is the commercial underwriting figure; the straight-line one is the
  // quick-look average. Saying which is which is the difference between two numbers and a choice.
  el.insertAdjacentHTML("beforeend", meta(
    `The <strong>discounted</strong> figure prices <em>when</em> the free rent and the TI cheque land; `
    + `straight-line averages them over the term. Agency underwriting uses the discounted one.`));

  // `lc_included` is false unless the caller supplies a rate — and without it the landlord's costs
  // are understated, so both NERs are the OPTIMISTIC case. The engine refuses to invent the rate;
  // the panel must not let its absence read as a complete answer.
  if (!n.lc_included) {
    el.insertAdjacentHTML("beforeend", meta(
      `Leasing commission is <strong>not</strong> included — no rate was supplied, and the engine `
      + `never invents one. Both NERs above are therefore the optimistic case.`,
      "var(--status-warn)"));
  }

  // POPULATION. Every total above is summed over the computable leases only.
  const parts: string[] = [`<strong>${n.lease_count}</strong> lease(s) valued`];
  if (n.skipped_count > 0) parts.push(`<strong>${n.skipped_count}</strong> skipped`);
  if (n.excluded_not_active > 0) parts.push(`${n.excluded_not_active} excluded as not active`);
  el.insertAdjacentHTML("beforeend", meta(parts.join(" · ")));

  if (n.skipped_count > 0) {
    el.insertAdjacentHTML("beforeend", meta(
      `Every figure above covers the <strong>${n.lease_count}</strong> lease(s) that could be valued — `
      + `so the Face GPR here is a smaller population than the rent roll's base rent above it, and the `
      + `two are not meant to reconcile.`, "var(--status-warn)"));
    const shown = n.skipped.length;
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table"><tr class="fin-sub"><td>Skipped lease</td><td>why</td></tr>`
      + n.skipped.map((s) =>
          `<tr><td>${esc(s.tenant || "—")}${s.suite ? ` <span class="meta">${esc(s.suite)}</span>` : ""}</td>`
          + `<td>${esc(s.reason || "—")}</td></tr>`).join("")
      + `</table>`);
    // `skipped` is capped at 50 server-side while `skipped_count` is not. A list presented as the
    // whole set when it is a page is how a screen reports over a partial view and calls it complete.
    if (shown < n.skipped_count) {
      el.insertAdjacentHTML("beforeend", meta(
        `Showing ${shown} of ${n.skipped_count} skipped leases.`, "var(--status-warn)"));
    }
  }

  if (n.leases.length) {
    // Ordered by face→NER delta server-side: the leases an underwriter re-cuts first.
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:6px">`
      + `<tr class="fin-sub"><td>Widest face → NER</td><td class="num">face</td>`
      + `<td class="num">NER</td><td class="num">load</td></tr>`
      + n.leases.slice(0, 8).map((l) =>
          `<tr><td>${esc(l.tenant || "—")}${l.suite ? ` <span class="meta">${esc(l.suite)}</span>` : ""}</td>`
          + `<td class="num">${esc(money(l.face_rent_annual))}</td>`
          + `<td class="num">${esc(money(l.ner_annual_discounted))}</td>`
          + `<td class="num">${l.concession_load_pct}%</td></tr>`).join("")
      + `</table>`);
  }

  host.appendChild(el);
  return el;
}

/** Rent-roll scrub: which diligence checks ran, which could not, and what they would need. */
export function renderRentScrub(host: HTMLElement, s: Scrub): HTMLElement {
  const el = card("Rent-roll scrub (diligence checks)");
  const { total, ran, not_applicable: notRun, passed, failed } = s.counts;

  // COVERAGE IS THE HEADLINE, not `clean`. `clean` is `bool(ran) && !failed`, so one check running
  // and passing while six cannot run is `true` — and a green tick off that flag is precisely the
  // laundering of absent data into confidence that rent_scrub.py exists to refuse.
  const colour = failed > 0 ? "var(--status-crit)"
    : notRun > 0 ? "var(--status-warn)" : "var(--status-good)";
  el.insertAdjacentHTML("beforeend",
    `<div style="font-weight:600;color:${colour}">`
    + `${ran} of ${total} checks could run`
    + (failed > 0 ? ` · ${failed} finding(s)` : ran > 0 ? ` · ${passed} passed` : "")
    + `</div>`
    + meta(esc(s.coverage_note)));

  if (s.clean && notRun > 0) {
    // The one sentence this card exists for.
    el.insertAdjacentHTML("beforeend", meta(
      `No findings <em>among the ${ran} check(s) that ran</em> — which is not the same as a clean `
      + `rent roll. ${notRun} check(s) had no inputs to run on.`, "var(--status-warn)"));
  }

  if (s.findings.length) {
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:6px">`
      + `<tr class="fin-sub"><td>Finding</td><td>severity</td></tr>`
      + s.findings.map((f) =>
          `<tr><td>${esc(f.finding)}</td><td>${esc(f.severity || "—")}</td></tr>`).join("")
      + `</table>`);
  }

  // The not-run checks with what each one NEEDS: this is the actionable half — it tells the user
  // which document to go and get, rather than leaving the gap as an absence of green ticks.
  const blocked = s.checks.filter((c) => !c.applicable);
  if (blocked.length) {
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:6px">`
      + `<tr class="fin-sub"><td>Could not run</td><td>needs</td></tr>`
      + blocked.map((c) =>
          `<tr><td>${esc(c.check)}</td><td>${esc(c.needs || c.finding || "—")}</td></tr>`).join("")
      + `</table>`);
  }

  const pop: string[] = [`${s.lease_count} active lease(s) scrubbed`];
  if (s.excluded_not_active > 0) pop.push(`${s.excluded_not_active} excluded as not active`);
  el.insertAdjacentHTML("beforeend", meta(pop.join(" · ")));

  host.appendChild(el);
  return el;
}

export interface RentRollQualityCtx {
  api: ApiClient;
  setStatus: (m: string) => void;
}

/** Fetch both and render them under the rent roll. Each failure is reported on its own card, so one
 *  engine being unavailable does not hide the other's answer. */
export async function renderRentRollQuality(host: HTMLElement, pid: string,
                                            ctx: RentRollQualityCtx): Promise<void> {
  const [ner, scrub] = await Promise.allSettled([
    ctx.api.netEffectiveRent(pid),
    ctx.api.rentRollScrub(pid),
  ]);
  if (ner.status === "fulfilled") renderNetEffective(host, ner.value);
  else {
    const el = card("Net effective rent (after concessions)");
    el.insertAdjacentHTML("beforeend", meta(esc((ner.reason as Error).message), "var(--status-crit)"));
    host.appendChild(el);
  }
  if (scrub.status === "fulfilled") renderRentScrub(host, scrub.value);
  else {
    const el = card("Rent-roll scrub (diligence checks)");
    el.insertAdjacentHTML("beforeend", meta(esc((scrub.reason as Error).message), "var(--status-crit)"));
    host.appendChild(el);
  }
  if (ner.status === "rejected" && scrub.status === "rejected") ctx.setStatus("rent-roll quality unavailable");
}
