import { money as cmoney, usd } from "../../ui/charts";
import { noProjectHtml } from "../../ui/empty";
import { escapeHtml as esc, toast } from "../../ui/feedback";
import { promptModal } from "../../ui/modal";
import type { PanelContext } from "../panelContext";

/**
 * General ledger — the balanced double-entry journal posted from job cost + billing + the WIP
 * percentage-of-completion adjustment, its trial balance, and one-click CSV / QuickBooks-IIF export.
 * The posting bridge to the accounting system of record.
 */
export async function renderLedger(ctx: PanelContext) {
  const root = ctx.root; root.innerHTML = "";
  const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
  root.appendChild(ctx.bar("📒 General Ledger", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
  const pid = ctx.host.projectId();
  if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("General Ledger")); return; }

  const intro = el("div", "meta"); intro.style.marginBottom = "8px";
  intro.innerHTML = "Balanced double-entry journal from job cost (Dr Construction Costs / Cr AP), owner "
    + "billing (Dr AR / Cr Revenue) and the WIP POC adjustment — so Contract Revenue nets to <b>earned</b>. "
    + "Export the GL as CSV or a QuickBooks IIF for your accounting system of record.";
  root.appendChild(intro);
  const dl = (label: string, href: string) => {
    const a = el("a", "portal-btn") as HTMLAnchorElement; a.textContent = label; a.href = href;
    a.style.marginRight = "6px"; a.target = "_blank"; a.rel = "noopener"; return a;
  };
  root.append(dl("⬇ GL CSV", ctx.host.api.accountingGlCsvUrl(pid)),
    dl("⬇ QuickBooks IIF", ctx.host.api.accountingIifUrl(pid)));
  const body = el("div"); body.style.marginTop = "8px"; body.textContent = "loading…"; root.appendChild(body);

  let tb; let je; let coa;
  try {
    tb = await ctx.host.api.trialBalance(pid);
    je = await ctx.host.api.journalEntries(pid).catch(() => null);
    coa = await ctx.host.api.chartOfAccounts(pid).catch(() => null);
  }
  catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
  body.innerHTML = "";
  if (coa?.accounts.length) {
    const chart = el("div", "dash-card"); chart.style.marginBottom = "8px";
    chart.innerHTML = `<b>Chart of accounts</b> <span class="meta">${coa.accounts.length} accounts · construction COA</span>`
      + `<table class="portal-table" style="width:100%;font-size:12px;margin-top:4px">`
      + `<thead><tr><th scope="col" style="text-align:left">Code</th><th scope="col" style="text-align:left">Account</th>`
      + `<th scope="col">Type</th><th scope="col">Normal</th></tr></thead><tbody>`
      + coa.accounts.map((a) => `<tr><td>${esc(a.code)}</td><td>${esc(a.name)}</td>`
        + `<td style="text-align:center">${esc(a.type)}</td>`
        + `<td style="text-align:center">${esc(a.normal)}</td></tr>`).join("")
      + `</tbody></table>`;
    body.append(chart);
  }
  if (!tb.accounts.length) {
    body.insertAdjacentHTML("beforeend", `<div class="meta">No postable transactions yet — add <b>direct costs</b> / <b>sub `
      + `invoices</b> (cost → AP) and <b>owner invoices</b> (billing) to build the ledger.</div>`);
    return;
  }

  // trial balance
  const bal = el("div", "dash-card"); bal.style.marginBottom = "8px";
  bal.innerHTML = `<b>Trial balance</b> <span class="meta">${tb.balanced ? "✅ balanced" : "⚠ out of balance"}</span>`
    + `<table class="portal-table" style="width:100%;font-size:12px;margin-top:4px">`
    + `<thead><tr><th scope="col" style="text-align:left">Account</th><th scope="col">Type</th>`
    + `<th scope="col">Debit</th><th scope="col">Credit</th></tr></thead><tbody>`
    + tb.accounts.map((a) => `<tr><td>${esc(a.code)} ${esc(a.account)}</td><td style="text-align:center">${esc(a.type)}</td>`
      + `<td style="text-align:right">${a.debit ? usd(a.debit) : "—"}</td>`
      + `<td style="text-align:right">${a.credit ? usd(a.credit) : "—"}</td></tr>`).join("")
    + `<tr class="fin-total"><td colspan="2">Total</td><td style="text-align:right">${usd(tb.debit_total)}</td>`
    + `<td style="text-align:right">${usd(tb.credit_total)}</td></tr></tbody></table>`;
  body.append(bal);

  // journal entries
  if (je && je.entries.length) {
    const j = el("div", "dash-card");
    j.innerHTML = `<b>Journal</b> <span class="meta">${je.entries.length} entries · ${je.balanced ? "balanced" : "⚠"}</span>`
      + `<table class="portal-table" style="width:100%;font-size:11px;margin-top:4px">`
      + `<thead><tr><th scope="col" style="text-align:left">Ref</th><th scope="col" style="text-align:left">Account</th>`
      + `<th scope="col">Debit</th><th scope="col">Credit</th></tr></thead><tbody>`
      + je.entries.flatMap((e) => e.lines.map((ln, i) => `<tr><td>${i === 0 ? esc(e.ref || "—") : ""}</td>`
        + `<td>${esc(ln.account)}</td><td style="text-align:right">${ln.debit ? usd(ln.debit) : ""}</td>`
        + `<td style="text-align:right">${ln.credit ? usd(ln.credit) : ""}</td></tr>`)).join("")
      + `</tbody></table>`;
    body.append(j);
  }

  // --- approval-gated export batches ------------------------------------------------------------
  // A batch FREEZES the current books into an auditable snapshot that moves draft → submitted →
  // approved → exported; the accountant imports only the reviewed, approved figures.
  const batches = el("div", "dash-card"); batches.style.marginTop = "8px"; body.append(batches);
  const stateBadge = (s: string) => {
    const c = s === "approved" || s === "exported" ? "var(--status-good)"
      : s === "rejected" ? "var(--status-crit)" : s === "submitted" ? "var(--status-warn)" : "var(--muted)";
    return `<span style="font-size:10px;font-weight:600;color:${c};border:1px solid ${c};border-radius:8px;padding:1px 6px">${esc(s)}</span>`;
  };
  const loadBatches = async () => {
    batches.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center">`
      + `<b>Journal export batches</b><span class="meta">freeze → submit → approve → export</span></div>`;
    const newBtn = el("button", "file-btn") as HTMLButtonElement;
    newBtn.textContent = "＋ Freeze current books into a batch"; newBtn.style.margin = "6px 0";
    newBtn.onclick = async () => {
      const v = await promptModal("New journal export batch", [
        { name: "period", label: "Accounting period (e.g. 2026-07)", required: true },
        { name: "memo", label: "Memo (optional)" },
      ], "Freeze & create",
      "Snapshots the current GL, journal and trial balance. Export stays locked until the batch is approved.");
      if (!v) return;
      try { await ctx.host.api.createJournalBatch(pid, v.period ?? "", v.memo || "");
        toast("Batch frozen (draft) — submit it for approval", "success"); await loadBatches(); }
      catch (e) { toast((e as Error).message, "error"); }
    };
    batches.append(newBtn);
    let recs; let cachedNote: string;
    try {
      // A register the user reopens constantly — show the last answer at once, revalidate behind.
      const { freshnessLabel } = await import("../../api/recordCache");
      const got = await ctx.host.api.moduleRecordsCached(pid, "journal_batch", () => void loadBatches());
      recs = got.value; cachedNote = freshnessLabel(got);
    }
    catch { batches.insertAdjacentHTML("beforeend", `<div class="meta">No batches yet.</div>`); return; }
    if (cachedNote) {
      const stale = el("div", "meta");
      stale.style.cssText = "font-size:11px;margin-bottom:6px;color:var(--muted)";
      stale.textContent = `${cachedNote} — refreshing…`;
      batches.append(stale);
    }
    if (!recs.length) { batches.insertAdjacentHTML("beforeend", `<div class="meta">No batches yet — freeze one to hand the books to accounting under an approval gate.</div>`); return; }
    for (const r of recs) {
      const d = r.data as Record<string, unknown>;
      const row = el("div"); row.style.cssText = "border-top:1px solid var(--line);padding:6px 0;display:flex;flex-wrap:wrap;gap:8px;align-items:center";
      const bal = d.balanced === "yes";
      row.innerHTML = `<b>${esc(r.ref || "batch")}</b> ${stateBadge(r.workflow_state)}`
        + `<span class="meta">${esc(String(d.period ?? ""))} · Dr ${usd(Number(d.total_debits ?? 0))} / Cr ${usd(Number(d.total_credits ?? 0))}`
        + ` · ${bal ? "balanced" : "⚠ out of balance"}</span>`;
      const acts = el("span"); acts.style.cssText = "margin-left:auto;display:flex;gap:6px;align-items:center";
      for (const a of (r.available_actions ?? [])) {
        const b = el("button", "file-btn") as HTMLButtonElement; b.textContent = a.action;
        b.style.textTransform = "capitalize";
        b.onclick = async () => {
          try { await ctx.host.api.transitionRecord(pid, "journal_batch", r.id, a.action);
            toast(`Batch ${a.action}d`, "success"); await loadBatches(); }
          catch (e) { toast((e as Error).message, "error"); }
        };
        acts.append(b);
      }
      if (r.workflow_state === "approved" || r.workflow_state === "exported") {
        for (const [label, fmt] of [["⬇ GL CSV", "gl"], ["⬇ IIF", "iif"]] as const) {
          const a = el("a", "file-btn") as HTMLAnchorElement; a.textContent = label;
          a.href = ctx.host.api.journalBatchExportUrl(pid, r.id, fmt); a.target = "_blank"; a.rel = "noopener";
          acts.append(a);
        }
      }
      row.append(acts); batches.append(row);
    }
  };
  await loadBatches();
  await renderFinanceGovernance(ctx, pid, root, el);
}

/**
 * FIN-GOV / FIN-INGEST — period close, two-way reconciliation, and import lineage.
 *
 * WHY THIS IS WORSE THAN AN ORDINARY MISSING SCREEN
 *     The period lock is not advisory. `PUT /projects/{pid}/finance/lock` closes the books through a
 *     month, and from then on **every finance-module mutation dated into a closed month is refused
 *     with a 409** — routes, imports and internal flows alike. That enforcement shipped and worked.
 *     What never shipped was any way to see the lock or set it.
 *
 *     So the constraint was live and its control was invisible: a user posting a cost into a closed
 *     month got a 409 with nothing in the interface that would explain why, and no way to open the
 *     period. An unreachable feature is a feature nobody can use; an unreachable *control over an
 *     enforced rule* is a feature that actively blocks people. That is the sharper end of the same
 *     defect, and the reason this group was worth taking first.
 *
 * All four `/finance` client methods were in the uncalled set — the whole domain had no path in.
 */
async function renderFinanceGovernance(
  ctx: PanelContext, pid: string, root: HTMLElement,
  el: (t: string, c?: string) => HTMLElement,
) {
  const api = ctx.host.api;
  const head = el("div"); head.style.cssText = "margin-top:14px;font-weight:600";
  head.textContent = "Period close & reconciliation";
  root.appendChild(head);

  // --- the lock ---------------------------------------------------------------------------------
  const lockRow = el("div", "meta");
  lockRow.style.cssText = "display:flex;gap:8px;align-items:center;margin:4px 0 8px;flex-wrap:wrap";
  root.appendChild(lockRow);
  const paintLock = async () => {
    lockRow.textContent = "";
    let lock;
    try { lock = await api.financeLock(pid); }
    catch (e) { lockRow.textContent = `lock status unavailable: ${(e as Error).message}`; return; }
    const state = el("span");
    state.style.fontWeight = "600";
    // Says what it MEANS, not just the date: "closed through 2026-06" is only actionable if you know
    // that postings into it will be refused.
    state.textContent = lock.lock_date
      ? `Books closed through ${lock.lock_date} — postings dated on or before it are refused`
      : "Books open — no period is closed";
    lockRow.append(state);
    if (lock.lock_date && (lock.set_by || lock.note)) {
      const who = el("span"); who.className = "meta";
      who.textContent = `set by ${lock.set_by ?? "?"}${lock.note ? ` · ${lock.note}` : ""}`;
      lockRow.append(who);
    }
    const set = el("button", "file-btn"); set.textContent = lock.lock_date ? "Change close date" : "Close a period";
    set.onclick = async () => {
      const v = await promptModal("Close the books", [
        { name: "date", label: "Close through (YYYY-MM or YYYY-MM-DD)", required: true },
        { name: "note", label: "Note (why)" },
      ], "Close");
      if (!v) return;
      try {
        await api.setFinanceLock(pid, (v.date ?? "").trim(), v.note ?? "");
        toast("period closed", "success"); await paintLock();
      } catch (e) { toast(`could not close: ${(e as Error).message}`, "error"); }
    };
    lockRow.append(set);
    if (lock.lock_date) {
      const clear = el("button", "file-btn"); clear.textContent = "Reopen";
      clear.title = "Clear the lock so postings into the closed period are accepted again";
      clear.onclick = async () => {
        try { await api.setFinanceLock(pid, null, "reopened"); toast("period reopened", "success"); await paintLock(); }
        catch (e) { toast(`could not reopen: ${(e as Error).message}`, "error"); }
      };
      lockRow.append(clear);
    }
  };
  await paintLock();

  // --- reconciliation ---------------------------------------------------------------------------
  const rec = el("div"); root.appendChild(rec);
  try {
    const r = await api.financeReconcile(pid);
    const c = r.counts;
    const line = el("div", "meta");
    // The counts are reported separately on purpose. The server matches budget and actuals BOTH ways
    // and never nets them, because a budget line with no actual and an actual with no budget are
    // different problems — netting them to one variance hides both.
    line.innerHTML = `<b>${c.matched}</b> matched · <b>${c.budget_only}</b> budget with no actual · `
      + `<b>${c.actuals_only}</b> actual with no budget · <b>${c.uncoded}</b> uncoded`
      // "fully reconciled" is defined by the ABSENCE of two problem lists, not by anything having
      // matched - fin_ingest.py returns `not actuals_only and not uncoded`. A project with no cost
      // codes yields empty lists, so the flag is true and the line reads
      //     0 matched - 0 budget with no actual - 0 actual with no budget - 0 uncoded - fully reconciled
      // under a heading that says "Period close". A controller scans the verdict, not the zeros, and
      // reads "the books tie out" where the truth is "there are no books".
      + (!(c.matched + c.budget_only + c.actuals_only + c.uncoded)
        ? " — no coded cost data to reconcile yet"
        : r.fully_reconciled ? " — fully reconciled" : "");
    rec.appendChild(line);
    // Actuals with no budget and uncoded actuals are the two that cost money; show those, highest
    // value first (the server already sorts them that way).
    for (const row of r.actuals_only.slice(0, 6)) {
      const d = el("div", "meta");
      d.style.cssText = "display:flex;gap:8px;border-top:1px solid var(--line);padding:3px 0";
      d.append(
        Object.assign(document.createElement("span"), { textContent: row.cost_code ?? "(no cost code)", style: "flex:1" }),
        Object.assign(document.createElement("span"), { textContent: "no budget" }),
        Object.assign(document.createElement("span"), { textContent: cmoney(row.actual ?? 0) }),
      );
      rec.appendChild(d);
    }
    for (const u of r.uncoded.slice(0, 6)) {
      const d = el("div", "meta");
      d.style.cssText = "display:flex;gap:8px;border-top:1px solid var(--line);padding:3px 0";
      d.append(
        Object.assign(document.createElement("span"), { textContent: `${u.ref ?? u.module} — uncoded`, style: "flex:1" }),
        Object.assign(document.createElement("span"), { textContent: esc(u.vendor ?? "") }),
        Object.assign(document.createElement("span"), { textContent: cmoney(u.amount ?? 0) }),
      );
      rec.appendChild(d);
    }
  } catch (e) {
    rec.innerHTML = `<div class="meta">reconciliation unavailable: ${esc((e as Error).message)}</div>`;
  }

  // --- where the numbers came from --------------------------------------------------------------
  try {
    const imports = await api.financeImports(pid);
    if (imports.length) {
      const h = el("div"); h.style.cssText = "margin-top:10px;font-weight:600;font-size:12.5px";
      h.textContent = "Import lineage";
      root.appendChild(h);
      for (const b of imports.slice(0, 8)) {
        const d = el("div", "meta");
        d.style.cssText = "display:flex;gap:8px;border-top:1px solid var(--line);padding:3px 0";
        d.append(
          Object.assign(document.createElement("span"), { textContent: b.filename || "(no file)", style: "flex:1" }),
          Object.assign(document.createElement("span"), { textContent: b.module }),
          Object.assign(document.createElement("span"), { textContent: `${b.imported} rows${b.error_count ? ` · ${b.error_count} errors` : ""}` }),
          Object.assign(document.createElement("span"), { textContent: `${b.actor ?? "?"} ${b.ts ?? ""}` }),
        );
        root.appendChild(d);
      }
    }
  } catch { /* lineage is context, not a blocker — a project with no imports has none */ }
}
