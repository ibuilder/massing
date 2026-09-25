/** The seller's trailing twelve, normalised — and the gate that refuses to guess, made reachable.
 *
 *  `services/api/src/aec_api/t12.py` exists for one refusal, stated in its own module docstring:
 *
 *  > income, expense and NOI must reconcile *before* and *after* mapping, or the engine stops and
 *  > lists the reconciling items. It does not publish an adjusted NOI on top of a mapping that lost
 *  > money.
 *
 *  `ApiClient.normalizeT12()` was written for it and **no screen ever called it** — frozen in
 *  `apps/web/src/api/clientCallers.test.ts`'s `UNCALLED` list.
 *
 *  T12-SELFTIE — WHAT MEASURING IT FOUND, AND IT IS WORTH MORE THAN THE WIRING
 *  --------------------------------------------------------------------------
 *  `normalize()`'s docstring says what it does, and the consequence is easy to miss: *"When the
 *  caller supplies source totals they are the reference the mapping must reproduce; **without them
 *  the sum of the source lines is**."* Both sides of the comparison are then computed from the same
 *  mapped rows, so the deltas are zero by construction and **the gate passes vacuously.**
 *
 *  Measured on one T-12 carrying a single unmapped $90,000 line, through the real engine:
 *
 *      no stated totals    reconciles: true    deltas all 0.0    adjusted_noi: 3,180,000
 *      with stated totals  reconciles: false   expense −90,000   stopped: true · adjusted_noi: null
 *
 *  The $90k reclass — precisely what the gate exists to catch — is invisible in the first case, and
 *  the engine publishes an adjusted NOI on top of it. That is not an engine defect: it is a **caller
 *  obligation that never had a caller.** *A guard is only as sound as the evidence it is handed* —
 *  the CLASH-TRUNC lesson one layer over, where a panel fed the guard a page of a matrix and declared
 *  it whole. Here a caller can feed it a reference derived from the answer.
 *
 *  So stated totals are the PRIMARY input here, not an optional extra, and with them absent this card
 *  never prints a passing tie-out. It says the mapping tied to itself and puts `unmapped_count` —
 *  the only signal left — where the verdict would otherwise be.
 *
 *  WHY IT LIVES BESIDE THE RENT-ROLL SCRUB
 *  A T-12 is acquisition diligence and the Underwriting tab would be the tidier home. It is here
 *  because `rentRollScrub` takes an `income` body and five of its seven checks report
 *  `applicable: false` for want of one — so the normalised output is the scrub's missing input, and
 *  the handoff has to be adjacent to be found at all.
 */
import type { ApiClient } from "../api/client";
import { escapeHtml as esc } from "../ui/feedback";
import { money } from "./format";

type T12 = Awaited<ReturnType<ApiClient["normalizeT12"]>>;

/** One pasted T-12 line. */
export interface T12Line { description: string; amount: number }

/**
 * Parse a pasted T-12: one line per row, `description<sep>amount`, where the separator is a tab or
 * the LAST comma on the line.
 *
 * The last comma rather than the first, deliberately: account names carry commas
 * ("Repairs, maintenance & turnover") and amounts do not carry tabs. Splitting on the first comma
 * silently truncates the description and, worse, reads the remainder as the amount — which parses,
 * so the failure would be a wrong number rather than an error. Currency marks, thousands separators
 * and parenthesised negatives are all accepted because that is what a spreadsheet paste contains.
 */
export function parseT12(text: string): { lines: T12Line[]; skipped: string[] } {
  const lines: T12Line[] = [];
  const skipped: string[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const row = raw.trim();
    if (!row) continue;
    const tab = row.lastIndexOf("\t");
    const cut = tab >= 0 ? tab : row.lastIndexOf(",");
    if (cut <= 0) { skipped.push(row); continue; }
    const desc = row.slice(0, cut).trim().replace(/^"|"$/g, "");
    const amount = parseAmount(row.slice(cut + 1));
    if (!desc || amount === null) { skipped.push(row); continue; }
    lines.push({ description: desc, amount });
  }
  return { lines, skipped };
}

/** `$1,234.50`, `(1,234.50)` and `-1234.5` all parse; anything else is `null`, never 0. */
export function parseAmount(s: string): number | null {
  const t = s.trim().replace(/^"|"$/g, "");
  if (!t) return null;
  const negative = /^\(.*\)$/.test(t);
  const digits = t.replace(/[()$£€\s,]/g, "");
  if (!/^-?\d*\.?\d+$/.test(digits)) return null;
  const n = parseFloat(digits);
  return negative ? -Math.abs(n) : n;
}

const meta = (html: string, colour?: string) =>
  `<div class="meta" style="margin-top:4px${colour ? `;color:${colour}` : ""}">${html}</div>`;

/** Did the caller give the engine an independent reference to tie against? */
export function hasStatedTotals(t: { income?: number | null; expense?: number | null }): boolean {
  return typeof t.income === "number" && isFinite(t.income)
    && typeof t.expense === "number" && isFinite(t.expense);
}

/** Render one normalisation result. `stated` says whether the caller supplied source totals. */
export function renderT12Result(host: HTMLElement, r: T12, stated: boolean): HTMLElement {
  const el = document.createElement("div");
  el.style.marginTop = "8px";

  // ---- THE VERDICT, and the three cases are genuinely different claims -------------------------
  if (r.stopped) {
    el.insertAdjacentHTML("beforeend",
      `<div style="font-weight:600;color:var(--status-crit)">Tie-out STOPPED — no adjusted NOI</div>`
      + meta(`Source and mapped totals disagree, so nothing derived is published. `
             + `Δ income ${esc(money(r.tie_out.deltas.income ?? 0))} · `
             + `Δ expense ${esc(money(r.tie_out.deltas.expense ?? 0))} · `
             + `Δ NOI ${esc(money(r.tie_out.deltas.noi ?? 0))} `
             + `(tolerance ${esc(money(r.tie_out.tolerance))}).`));
    if (r.reconciling_items?.length) {
      el.insertAdjacentHTML("beforeend",
        `<table class="fin-table" style="margin-top:6px">`
        + `<tr class="fin-sub"><td>Reconciling item</td><td class="num">amount</td></tr>`
        + r.reconciling_items.map((i) =>
            `<tr><td>${esc(i.description || i.issue)}</td>`
            + `<td class="num">${i.amount == null ? "—" : esc(money(i.amount))}</td></tr>`).join("")
        + `</table>`);
    }
    el.insertAdjacentHTML("beforeend", meta(
      `Resolve these and re-run — the add-back questions and the run-rate view are computed only past `
      + `the gate, so they are not merely hidden, they were never calculated.`));
  } else if (!stated) {
    // THE CASE THIS CARD EXISTS FOR. `reconciles: true` here means the mapping was compared with a
    // total derived from the same mapping, so it cannot fail. Printing "passed" would be a claim the
    // response does not support, and the engine's own docstring says why that claim is dangerous.
    el.insertAdjacentHTML("beforeend",
      `<div style="font-weight:600;color:var(--status-warn)">Tie-out tied to itself — not a check</div>`
      + meta(`No stated income/expense totals were supplied, so the engine reconciled the mapping `
             + `against a figure derived from <strong>the same mapping</strong>. The deltas are zero `
             + `by construction and a lost line cannot show up here. `
             + `<strong>${r.unmapped_count}</strong> line(s) did not map — that is the only signal `
             + `left. Enter the statement's own totals to make this a real gate.`));
  } else {
    el.insertAdjacentHTML("beforeend",
      `<div style="font-weight:600;color:var(--status-good)">Tie-out passed against the stated totals</div>`
      + meta(`The mapping reproduces income ${esc(money(r.source_totals.income ?? 0))} and expense `
             + `${esc(money(r.source_totals.expense ?? 0))} as stated, so the derived views below are `
             + `safe to read.`));
  }

  el.insertAdjacentHTML("beforeend",
    `<table class="fin-table" style="margin-top:6px">`
    + `<tr class="fin-sub"><td></td><td class="num">stated</td><td class="num">mapped</td></tr>`
    + `<tr><td>Income</td><td class="num">${esc(money(r.source_totals.income ?? 0))}</td>`
    + `<td class="num">${esc(money(r.mapped_totals.income ?? 0))}</td></tr>`
    + `<tr><td>Expense</td><td class="num">${esc(money(r.source_totals.expense ?? 0))}</td>`
    + `<td class="num">${esc(money(r.mapped_totals.expense ?? 0))}</td></tr>`
    + `<tr class="fin-total"><td>NOI</td><td class="num">${esc(money(r.source_totals.noi ?? 0))}</td>`
    + `<td class="num">${esc(money(r.mapped_totals.noi ?? 0))}</td></tr>`
    + `</table>`
    + meta(`${r.line_count} line(s) mapped`
           + (r.unmapped_count ? ` · <strong>${r.unmapped_count} unmapped</strong>` : "")));

  if (r.unmapped?.length) {
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:6px">`
      + `<tr class="fin-sub"><td>Did not map</td><td class="num">amount</td></tr>`
      + r.unmapped.map((u) => `<tr><td>${esc(u.description)}</td>`
          + `<td class="num">${esc(money(u.amount))}</td></tr>`).join("")
      + `</table>`);
    // `unmapped` is capped at 50 server-side while `unmapped_count` is not — the same page-as-whole
    // shape the NER card guards. Here it is sharper: with no stated totals this list IS the verdict.
    if (r.unmapped.length < r.unmapped_count) {
      el.insertAdjacentHTML("beforeend", meta(
        `Showing ${r.unmapped.length} of ${r.unmapped_count} unmapped lines.`, "var(--status-warn)"));
    }
  }

  // ---- everything below exists only past the gate ---------------------------------------------
  if (r.adjusted_noi != null) {
    el.insertAdjacentHTML("beforeend",
      `<div style="margin-top:8px;font-size:20px;font-weight:600">${esc(money(r.adjusted_noi))}</div>`
      + meta(`Adjusted NOI — one-time income removed, one-time expense added back, capital below the `
             + `line.`));
  }

  if (r.one_time_items?.length || r.capital_items?.length) {
    const rows = [
      ...(r.one_time_items ?? []).map((i) => [`one-time ${i.kind}`, i.description, i.amount] as const),
      ...(r.capital_items ?? []).map((i) => ["capital", i.description, i.amount] as const),
    ];
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:6px">`
      + `<tr class="fin-sub"><td>Treatment</td><td>line</td><td class="num">amount</td></tr>`
      + rows.map(([k, d, a]) => `<tr><td>${esc(k)}</td><td>${esc(d)}</td>`
          + `<td class="num">${esc(money(a))}</td></tr>`).join("")
      + `</table>`);
  }

  if (r.run_rate_vs_trailing?.length) {
    const moved = r.run_rate_vs_trailing.filter((x) => Math.abs(x.delta) > 0.5);
    if (moved.length) {
      el.insertAdjacentHTML("beforeend",
        `<table class="fin-table" style="margin-top:6px">`
        + `<tr class="fin-sub"><td>Run rate vs trailing</td><td class="num">trailing</td>`
        + `<td class="num">last 3 × 4</td><td class="num">Δ</td></tr>`
        + moved.map((x) => `<tr><td>${esc(x.label ?? x.category)}</td>`
            + `<td class="num">${esc(money(x.trailing))}</td>`
            + `<td class="num">${esc(money(x.run_rate))}</td>`
            + `<td class="num">${esc(money(x.delta))}</td></tr>`).join("")
        + `</table>`);
    }
  }

  // Add-backs are QUESTIONS and the engine never applies them. Rendering them as findings would
  // invite the reader to treat them as already priced in, which is the 15–25% NOI miss they exist
  // to prevent. The number behind each one is rendered because the engine's docstring says the
  // number is the point — and it had to be DECLARED on the client type first, which it was not.
  if (r.add_back_questions?.length) {
    el.insertAdjacentHTML("beforeend",
      `<div class="section-title" style="margin:8px 0 4px">Questions to ask before you price it</div>`
      + `<table class="fin-table">`
      + r.add_back_questions.map((q) =>
          `<tr><td>${esc(q.finding)}`
          + (q.amount != null ? ` <span class="meta">${esc(money(q.amount))}`
             + (q.pct_of_income != null ? ` · ${q.pct_of_income}% of income` : "") + `</span>` : "")
          + `<div class="meta">${esc(q.question)}</div></td>`
          + `<td>${esc(q.severity)}</td></tr>`).join("")
      + `</table>`
      + meta(`These are never applied for you — an owner-managed property that a third-party manager `
             + `will run costs more than the T-12 shows.`));
  } else if (!r.stopped) {
    el.insertAdjacentHTML("beforeend", meta(`No owner-operated tells in this statement.`));
  }

  host.appendChild(el);
  return el;
}

export interface T12Ctx {
  api: ApiClient;
  projectId: () => string | null | undefined;
  setStatus: (m: string) => void;
  /** Re-run the rent-roll scrub with an income statement derived from this T-12. */
  scrubWithIncome?: (income: Record<string, number>) => void;
}

/** The income fields `rent_scrub.py` reads, taken from a normalised T-12's categories.
 *
 *  Only the two it can supply. `prior_bad_debt`, `occupancy_pct` and `prior_occupancy_pct` describe a
 *  PRIOR period and a unit inventory, which a single trailing twelve does not carry — so the check
 *  that needs them stays `applicable: false` and says so. Filling them with this period's figures to
 *  make the check run would be the defect the scrub is written to refuse, committed from the outside.
 */
export function incomeFromT12(r: T12): Record<string, number> {
  const by = new Map((r.by_category ?? []).map((b) => [b.category, b.amount]));
  const out: Record<string, number> = {};
  const gpr = by.get("gross_potential_rent");
  const bad = by.get("bad_debt");
  if (typeof gpr === "number") out.gross_potential_rent = gpr;
  if (typeof bad === "number") out.bad_debt = bad;
  return out;
}

export function renderT12Card(root: HTMLElement, ctx: T12Ctx): HTMLElement {
  const host = document.createElement("div");
  host.id = "pf-t12";
  host.className = "fin-card";
  host.style.marginTop = "10px";
  host.innerHTML = `<div class="section-title">Seller's T-12 — normalise and tie out</div>`
    + `<div class="meta">Paste the statement (one line each, <code>description, amount</code>), then `
    + `give its own stated totals. <strong>The totals are what makes this a check</strong> — without `
    + `them the mapping is reconciled against itself and cannot fail.</div>`;

  const ta = document.createElement("textarea");
  ta.rows = 6;
  ta.className = "portal-filter";
  ta.style.cssText = "width:100%;margin-top:6px;font-family:var(--mono, monospace);font-size:12px";
  ta.placeholder = "Gross potential rent, 3,600,000\nVacancy loss, (180,000)\nRepairs & maintenance, 240,000";
  host.appendChild(ta);

  const grid = document.createElement("div"); grid.className = "pf-form";
  const num = (label: string, title: string) => {
    const w = document.createElement("label"); w.className = "pf-field";
    w.innerHTML = `<span>${esc(label)}</span>`;
    const i = document.createElement("input");
    i.type = "number"; i.step = "any"; i.title = title;
    w.appendChild(i); grid.appendChild(w); return i;
  };
  const incIn = num("Stated income $", "The statement's own total income — the reference the mapping must reproduce.");
  const expIn = num("Stated expense $", "The statement's own total operating expense.");
  const unitsIn = num("Units (optional)", "Unit count, used only for the per-unit maintenance question.");
  host.appendChild(grid);

  const actions = document.createElement("div"); actions.style.cssText = "margin-top:6px";
  const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Normalise + tie out";
  const toScrub = document.createElement("button"); toScrub.className = "file-btn";
  toScrub.textContent = "Use in the rent-roll scrub";
  toScrub.style.cssText = "margin-left:6px;display:none";
  actions.append(go, toScrub); host.appendChild(actions);

  const out = document.createElement("div"); host.appendChild(out);
  root.appendChild(host);

  go.onclick = async () => {
    const pid = ctx.projectId();
    if (!pid) { out.innerHTML = meta("Open a project first."); return; }
    const { lines, skipped } = parseT12(ta.value);
    if (!lines.length) {
      out.innerHTML = meta("No parsable lines — each row needs a description and an amount.",
                           "var(--status-crit)");
      return;
    }
    const income = parseFloat(incIn.value), expense = parseFloat(expIn.value);
    const stated = hasStatedTotals({ income, expense });
    const units = parseFloat(unitsIn.value);
    const body: Record<string, unknown> = { lines };
    if (stated) body.totals = { income, expense };

    go.disabled = true; toScrub.style.display = "none";
    out.innerHTML = meta("mapping and reconciling…");
    ctx.setStatus("normalising the T-12…");
    try {
      const r = await ctx.api.normalizeT12(pid, body, isFinite(units) ? units : undefined);
      out.innerHTML = "";
      if (skipped.length) {
        // Lines this client dropped never reach the engine, so they are absent from BOTH totals and
        // invisible to the tie-out however it is run. Reported here because nothing downstream can.
        out.insertAdjacentHTML("beforeend", meta(
          `<strong>${skipped.length}</strong> pasted row(s) could not be read and were not sent: `
          + skipped.slice(0, 5).map((s) => esc(s)).join(" · ")
          + (skipped.length > 5 ? ` … and ${skipped.length - 5} more` : ""),
          "var(--status-warn)"));
      }
      renderT12Result(out, r, stated);
      if (!r.stopped && ctx.scrubWithIncome) {
        const inc = incomeFromT12(r);
        if (Object.keys(inc).length) {
          toScrub.style.display = "";
          toScrub.onclick = () => {
            ctx.scrubWithIncome!(inc);
            ctx.setStatus("re-running the rent-roll scrub with the normalised T-12");
          };
        }
      }
      ctx.setStatus(r.stopped ? "T-12 tie-out stopped"
                    : stated ? "T-12 tie-out passed" : "T-12 mapped (tie-out tied to itself)");
    } catch (e) {
      out.innerHTML = meta(esc((e as Error).message), "var(--status-crit)");
      ctx.setStatus("T-12 normalisation failed");
    } finally {
      go.disabled = false;
    }
  };

  return host;
}
