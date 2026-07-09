import { money as cmoney } from "../../ui/charts";
import { noProjectHtml } from "../../ui/empty";
import { escapeHtml as esc } from "../../ui/feedback";
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
}
