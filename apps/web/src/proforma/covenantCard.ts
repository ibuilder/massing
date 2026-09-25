/** The loan covenant and reporting register — and the two verdicts that read clean when nothing was
 *  evaluated.
 *
 *  `services/api/src/aec_api/covenants.py` opens with the case for itself:
 *
 *  > A borrower with clean financials who files on day nine of a "ten business days" notice —
 *  > counted from the lender's notice date, not from the day it landed — has breached exactly as
 *  > surely as one who missed a DSCR test.
 *
 *  `ApiClient.loanCovenants()` was written for it and **no screen ever called it**, so every
 *  property below had no consumer to get them wrong until this file existed.
 *
 *  TWO VERDICTS, BOTH VACUOUS ON AN UNEVALUATED REGISTER — MEASURED, NOT REASONED
 *  -----------------------------------------------------------------------------
 *      register state                                  at_risk   financial.clean
 *      2 uncomputable obligations, 2 untested covenants  false         false
 *      1 of 3 covenants tested and passing               false        TRUE
 *
 *  `at_risk` is `overdue > 0 or due_soon > 0 or breach > 0 or cure_period_open > 0`, so a register
 *  that could evaluate **nothing** reports *not at risk* — every count it reads is zero for want of
 *  inputs rather than for want of problems. And `clean` is `bool(tested) and all(passing)`, which
 *  fails closed only when ZERO covenants are tested; one tested and two not is `true`.
 *
 *  The engine is not wrong and hands over the antidote to both — `summary.untested_covenants`,
 *  `summary.uncomputable_obligations`, and its own note: *"A covenant with no supplied actual is
 *  reported UNTESTED with what it needed — an untested covenant is not a passing one."* So coverage
 *  is the headline here and the verdicts are qualifiers on it, never the other way round.
 *
 *  THE DUE DATE SHOWS ITS WORK, WHICH IS THE ENGINE'S STATED PURPOSE
 *  `covenants.py`: *"the calculated due date shows its work: the anchor date, the basis, the count,
 *  and every non-working day it skipped. **A due date a reviewer cannot re-derive by hand is not a
 *  due date.**"* Those four fields were declared nowhere in `api/creDeal.ts` until this change — the
 *  one property the engine was built for was invisible to its client by construction. They are
 *  rendered, and `alternate_reading` with them: when the lender's notice date and our receipt date
 *  differ, the obligation carries BOTH due dates, the day difference and a warning to confirm the
 *  basis with counsel. A calendar that shows one of two possible dates is worse than one that admits
 *  it has two.
 *
 *  WHERE THE REGISTER LIVES, stated rather than left to be discovered
 *  There is no `loan` module: the route is stateless and takes the register in the body. This card
 *  keeps it in `localStorage`, per project, the way `testfitTab.ts` keeps a unit mix — **a per-browser
 *  convenience, not a shared system of record**, and the card says so where somebody might otherwise
 *  rely on it. A register module would make it shared and is a product decision rather than a
 *  wiring one; recorded here as chosen-against rather than overlooked.
 */
import type { ApiClient } from "../api/client";
import { escapeHtml as esc } from "../ui/feedback";

type Register = Awaited<ReturnType<ApiClient["loanCovenants"]>>;

const meta = (html: string, colour?: string) =>
  `<div class="meta" style="margin-top:4px${colour ? `;color:${colour}` : ""}">${html}</div>`;

/** A realistic skeleton, so the body shape is discoverable without reading the route's docstring. */
export const EXAMPLE_REGISTER = {
  name: "Senior construction facility",
  lender: "Example Bank",
  holidays: ["2026-12-25", "2026-12-26"],
  obligations: [
    { name: "Quarterly financials", days: 10, day_basis: "business", clock_start: "our_receipt",
      lender_notice_date: "2026-09-01", received_date: "2026-09-03" },
    { name: "Annual audited accounts", days: 120, day_basis: "calendar", clock_start: "lender_notice",
      period_end: "2026-12-31" },
  ],
  covenants: [
    { name: "DSCR", metric: "dscr", direction: "min", threshold: 1.25, frequency: "quarterly",
      cure_days: 30 },
    { name: "Debt yield", metric: "debt_yield", direction: "min", threshold: 0.09 },
    { name: "LTV", metric: "ltv", direction: "max", threshold: 0.65 },
  ],
};

/** `dscr = 1.41` / `ltv: 0.62` — one metric per line. Returns `null` for a line it cannot read, so a
 *  typo becomes a reported problem rather than a silently absent actual (and hence an untested
 *  covenant, which is exactly the state this card exists to make visible). */
export function parseActuals(text: string): { actuals: Record<string, number>; skipped: string[] } {
  const actuals: Record<string, number> = {};
  const skipped: string[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const row = raw.trim();
    if (!row) continue;
    const m = /^([A-Za-z_][\w.]*)\s*[=:]\s*(.+)$/.exec(row);
    const n = m ? Number(m[2]!.replace(/[%\s,]/g, "")) : NaN;
    if (!m || !isFinite(n)) { skipped.push(row); continue; }
    actuals[m[1]!] = n;
  }
  return { actuals, skipped };
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** `2026-09-17` → `17 Sep 2026`; anything unparsable comes back unchanged, never as "Invalid Date".
 *
 *  Formatted from a fixed table rather than through `toLocaleDateString`, which was the first draft
 *  and was **environment-dependent**: this Node's ICU renders `en-GB` short September as "Sept", an
 *  older or differently-built one renders "Sep", and the test that pinned it would then pass or fail
 *  on which runtime happened to execute it. A covenant calendar is read across machines and a date
 *  that is spelled differently on two of them is the wrong kind of surprise — the same reason
 *  `test_route_reachability` had to make its own verdict invariant under file order. */
export function day(iso?: string | null): string {
  if (!iso) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const month = MONTHS[Number(m[2]) - 1];
  if (!month) return iso;
  return `${Number(m[3])} ${month} ${m[1]}`;
}

/** Render one evaluated register. */
export function renderRegister(host: HTMLElement, r: Register): HTMLElement {
  const el = document.createElement("div");
  el.style.marginTop = "8px";
  const rep = r.reporting, fin = r.financial;
  const untested = fin.counts.untested ?? 0;
  const uncomputable = rep.not_computable.length;

  // ---- COVERAGE FIRST. `at_risk` alone is false on a register that evaluated nothing. -----------
  const evaluatedNothing = (rep.counts.computable ?? 0) === 0 && (fin.counts.tested ?? 0) === 0;
  const trouble = (r.summary.overdue_filings ?? 0) + (r.summary.covenant_breaches ?? 0)
                + (r.summary.in_cure_period ?? 0);
  const colour = trouble > 0 ? "var(--status-crit)"
    : (untested || uncomputable) ? "var(--status-warn)" : "var(--status-good)";
  el.insertAdjacentHTML("beforeend",
    `<div style="font-weight:600;color:${colour}">`
    + `${rep.counts.computable ?? 0} of ${rep.counts.total ?? 0} obligations computable · `
    + `${fin.counts.tested ?? 0} of ${fin.counts.total ?? 0} covenants tested`
    + `</div>`);

  if (evaluatedNothing) {
    // The sharpest case: every count `at_risk` reads is zero for want of inputs, so it says false.
    el.insertAdjacentHTML("beforeend", meta(
      `<strong>Nothing in this register could be evaluated.</strong> The engine reports `
      + `<code>at_risk: false</code> because every count it reads is zero — that is an absence of `
      + `inputs, not an absence of risk. Supply the dates and the actuals below before treating this `
      + `as a calendar.`, "var(--status-crit)"));
  } else {
    el.insertAdjacentHTML("beforeend", meta(
      r.at_risk
        ? `<strong>At risk</strong> — ${r.summary.overdue_filings ?? 0} overdue · `
          + `${r.summary.filings_due_soon ?? 0} due soon · ${r.summary.covenant_breaches ?? 0} breach · `
          + `${r.summary.in_cure_period ?? 0} in cure`
        : `Nothing overdue, due soon, breached or in cure among what could be evaluated.`,
      r.at_risk ? "var(--status-crit)" : undefined));
  }

  // `clean` is `bool(tested) and all(passing)` — true with one tested and two untested. The engine's
  // own note is the wording; rendering the flag without it is what this card exists to refuse.
  if (fin.clean && untested > 0) {
    el.insertAdjacentHTML("beforeend", meta(
      `Every covenant that was <em>tested</em> passed — and ${untested} could not be tested. `
      + esc(fin.note), "var(--status-warn)"));
  }

  // ---- the reporting calendar -----------------------------------------------------------------
  const computable = rep.obligations.filter((o) => o.computable);
  if (computable.length) {
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:8px">`
      + `<tr class="fin-sub"><td>Obligation</td><td>due</td><td>anchor</td><td class="num">days</td></tr>`
      + computable.map((o) => {
          const risk = o.risk === "overdue" ? "var(--status-crit)"
            : o.risk === "due_soon" || o.risk === "late_filed" ? "var(--status-warn)" : "";
          // The engine's whole point: anchor, basis, count and the skipped days, so a reviewer can
          // re-derive the date by hand. Rendering only `due_date` throws that away.
          const skipped = o.non_working_days_skipped ?? [];
          const work = `${o.days ?? "?"} ${esc(o.day_basis ?? "")} day(s) from `
            + `${esc(o.anchor_source ?? "")} ${day(o.anchor_date)}`
            + (skipped.length ? `, skipping ${skipped.length} non-working day(s): `
               + skipped.slice(0, 6).map((s) => `${day(s.date)} (${esc(s.why)})`).join(", ")
               + (skipped.length > 6 ? ` …` : "") : "");
          return `<tr><td>${esc(o.name)}<div class="meta">${work}</div>`
            + (o.clock_start_matters && o.alternate_reading
               ? `<div class="meta" style="color:var(--status-warn)">`
                 + `Under the <strong>${esc(o.alternate_reading.clock_start.replace(/_/g, " "))}</strong> `
                 + `reading it is due ${day(o.alternate_reading.due_date)} — `
                 + `${Math.abs(o.alternate_reading.days_difference)} day(s) different. `
                 + `${esc(o.alternate_reading.warning)}</div>` : "")
            + `</td><td${risk ? ` style="color:${risk}"` : ""}>${day(o.due_date)}</td>`
            + `<td>${esc(o.status?.replace(/_/g, " ") ?? "")}`
            + (o.days_early != null && o.delivered_date
               ? ` <span class="meta">${o.days_early >= 0 ? `${o.days_early}d early` : `${-o.days_early}d late`}</span>` : "")
            + `</td>`
            + `<td class="num">${o.days_remaining ?? "—"}</td></tr>`;
        }).join("")
      + `</table>`);
  }

  if (uncomputable) {
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:6px">`
      + `<tr class="fin-sub"><td>No due date could be computed</td><td>needs</td></tr>`
      + rep.not_computable.map((n) => `<tr><td>${esc(n.name ?? "—")}</td>`
          + `<td>${esc(n.reason ?? "—")}</td></tr>`).join("")
      + `</table>`
      + meta(`These carry no date at all — they are not "not due yet".`, "var(--status-warn)"));
  }

  // ---- financial covenants --------------------------------------------------------------------
  const tested = fin.covenants.filter((c) => c.tested);
  if (tested.length) {
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:8px">`
      + `<tr class="fin-sub"><td>Covenant</td><td class="num">actual</td><td class="num">threshold</td>`
      + `<td class="num">headroom</td><td>state</td></tr>`
      + tested.map((c) => {
          // THREE states, not two. The engine separates `cure_period_open` from `breach` and says
          // why in its own note; folding them together loses the only distinction that matters at
          // the moment somebody has to act.
          const colourFor = c.status === "breach" ? "var(--status-crit)"
            : c.status === "cure_period_open" ? "var(--status-warn)" : "var(--status-good)";
          return `<tr><td>${esc(c.name)}`
            + (c.note ? `<div class="meta">${esc(c.note)}</div>` : "")
            + `</td><td class="num">${c.actual ?? "—"}</td><td class="num">${c.threshold ?? "—"}</td>`
            + `<td class="num">${c.headroom ?? "—"}</td>`
            + `<td style="color:${colourFor}">${esc((c.status ?? "").replace(/_/g, " "))}`
            + (c.cure_ends ? `<div class="meta">cure ends ${day(c.cure_ends)}</div>` : "")
            + `</td></tr>`;
        }).join("")
      + `</table>`);
  }

  if (untested) {
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:6px">`
      + `<tr class="fin-sub"><td>Not tested</td><td>needs</td></tr>`
      + fin.untested.map((u) => `<tr><td>${esc(u.name)}</td><td>${esc(u.reason)}</td></tr>`).join("")
      + `</table>`
      + meta(esc(fin.note), "var(--status-warn)"));
  }

  el.insertAdjacentHTML("beforeend", meta(
    `As of ${day(rep.as_of)} · horizon ${rep.horizon_days} days. ${esc(rep.note)}`));

  host.appendChild(el);
  return el;
}

export interface CovenantCtx {
  api: ApiClient;
  projectId: () => string | null | undefined;
  setStatus: (m: string) => void;
}

export function renderCovenantCard(root: HTMLElement, ctx: CovenantCtx): HTMLElement {
  const host = document.createElement("div");
  host.id = "pf-covenants";
  host.className = "fin-card";
  host.style.marginTop = "10px";
  host.innerHTML = `<div class="section-title">Loan covenants + reporting calendar</div>`
    + `<div class="meta">Timing alone can breach a loan: a filing counted in <em>business</em> days `
    + `from the lender's notice is a different date from calendar days from your receipt, and the `
    + `engine computes both when they disagree.</div>`;

  const pid = ctx.projectId();
  // The key is spelled with its LITERAL prefix first, not built through a helper.
  // `apps/web/src/ui/clearCacheKeys.test.ts` walks every `localStorage.*Item` call and refuses an
  // argument it cannot resolve to a stem — *"an unread key is an unclassified key"*, because
  // **Clear cached data** then makes a decision about it that nothing has checked. A template
  // beginning with `${` has no stem to read; this one does.
  //
  // It is KEPT by that button rather than cleared, and that falls out of the denylist design rather
  // than needing a declaration: `CACHE_KEY_PREFIXES` is empty and `isKeeper` is true for everything
  // not named there. Right for this key — a hand-entered register has no server copy, so clearing it
  // loses work rather than evicting a cache, the same argument `clearCache.ts` makes for the offline
  // upload queue.
  const load = (k: string, fallback: string) => {
    try { return pid ? (localStorage.getItem(`covenant-register:${pid}:${k}`) ?? fallback) : fallback; }
    catch { return fallback; }
  };
  const save = (k: string, v: string) => {
    try { if (pid) localStorage.setItem(`covenant-register:${pid}:${k}`, v); }
    catch { /* private window */ }
  };

  const area = (label: string, rows: number, value: string, ph: string) => {
    host.insertAdjacentHTML("beforeend", `<div class="meta" style="margin-top:6px">${esc(label)}</div>`);
    const t = document.createElement("textarea");
    t.rows = rows; t.className = "portal-filter"; t.value = value; t.placeholder = ph;
    t.style.cssText = "width:100%;font-family:var(--mono, monospace);font-size:12px";
    host.appendChild(t); return t;
  };
  const regIn = area("Register (JSON)", 8, load("register", ""),
                     '{"name": …, "obligations": [...], "covenants": [...]}');
  const actIn = area("Actuals — one metric per line", 3, load("actuals", ""), "dscr = 1.41\nltv = 0.62");

  const actions = document.createElement("div"); actions.style.cssText = "margin-top:6px";
  const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Evaluate register";
  const ex = document.createElement("button"); ex.className = "file-btn"; ex.textContent = "Load example";
  ex.style.marginLeft = "6px";
  actions.append(go, ex); host.appendChild(actions);
  host.insertAdjacentHTML("beforeend", meta(
    `Kept in this browser only, per project — a working register, <strong>not a shared system of `
    + `record</strong>. Nobody else sees what you enter here.`));

  const out = document.createElement("div"); host.appendChild(out);
  root.appendChild(host);

  ex.onclick = () => { regIn.value = JSON.stringify(EXAMPLE_REGISTER, null, 2); save("register", regIn.value); };

  go.onclick = async () => {
    const project = ctx.projectId();
    if (!project) { out.innerHTML = meta("Open a project first."); return; }
    let loan: unknown;
    try {
      loan = JSON.parse(regIn.value);
    } catch (e) {
      out.innerHTML = meta(`The register is not valid JSON — ${esc((e as Error).message)}`,
                           "var(--status-crit)");
      return;
    }
    const { actuals, skipped } = parseActuals(actIn.value);
    save("register", regIn.value); save("actuals", actIn.value);

    go.disabled = true;
    out.innerHTML = meta("evaluating…");
    ctx.setStatus("evaluating the covenant register…");
    try {
      const r = await ctx.api.loanCovenants(project, loan, actuals);
      out.innerHTML = "";
      if (skipped.length) {
        // An unreadable actual is an ABSENT actual, and an absent actual is an untested covenant —
        // which the card below reports as untested without knowing a typo caused it. Said here.
        out.insertAdjacentHTML("beforeend", meta(
          `<strong>${skipped.length}</strong> actual(s) could not be read and were not sent: `
          + skipped.slice(0, 4).map((s) => esc(s)).join(" · ")
          + `. A covenant whose metric is missing is reported <em>untested</em> below, so a typo here `
          + `looks exactly like a figure you never had.`, "var(--status-warn)"));
      }
      renderRegister(out, r);
      ctx.setStatus(r.at_risk ? "covenant register: at risk" : "covenant register evaluated");
    } catch (e) {
      out.innerHTML = meta(esc((e as Error).message), "var(--status-crit)");
      ctx.setStatus("covenant evaluation failed");
    } finally {
      go.disabled = false;
    }
  };

  return host;
}
