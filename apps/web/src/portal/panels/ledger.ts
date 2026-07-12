import { money as cmoney } from "../../ui/charts";
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

  let tb; let je;
  try { tb = await ctx.host.api.trialBalance(pid); je = await ctx.host.api.journalEntries(pid).catch(() => null); }
  catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
  body.innerHTML = "";
  const usd = (n: number) => cmoney(n);
  if (!tb.accounts.length) {
    body.innerHTML = `<div class="meta">No postable transactions yet — add <b>direct costs</b> / <b>sub `
      + `invoices</b> (cost → AP) and <b>owner invoices</b> (billing) to build the ledger.</div>`;
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
    let recs;
    try { recs = await ctx.host.api.moduleRecords(pid, "journal_batch"); }
    catch { batches.insertAdjacentHTML("beforeend", `<div class="meta">No batches yet.</div>`); return; }
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
}
