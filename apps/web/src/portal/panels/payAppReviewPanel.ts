/**
 * PAY-APP-SCREEN — renders the G702 certificate and its G703 continuation sheet in a dialog.
 *
 * The rules live in `payAppReview.ts` and are tested there; this file is the DOM and the fetch.
 * Before it existed, a pay application could be frozen and downloaded but never read: the nine
 * certificate lines were only ever rendered inside a PDF blob, which is why an over-billing defect
 * in line 7 shipped and survived until the next draw asked for the whole job again.
 */
import type { ApiClient } from "../../api/client";
import { usd } from "../../ui/charts";
import { modalShell } from "../../ui/modal";

import {
  CERT_LINES, type Certificate, type Sheet,
  line7Basis, line7Note, summary,
} from "./payAppReview";

const cell = (text: string, align: "left" | "right" = "left", bold = false) => {
  const td = document.createElement("td");
  td.textContent = text;
  td.style.cssText = `padding:3px 8px;text-align:${align};${bold ? "font-weight:600;" : ""}`;
  return td;
};

/** The nine lines, as the AIA prints them, with line 8 emphasised — it is the ask. */
function certTable(cert: Certificate): HTMLTableElement {
  const t = document.createElement("table");
  t.style.cssText = "width:100%;border-collapse:collapse;font-size:13px";
  for (const l of CERT_LINES) {
    const tr = document.createElement("tr");
    const emphasis = l.no === 8;
    tr.style.cssText = `border-top:1px solid var(--line)${emphasis ? ";background:var(--hover)" : ""}`;
    tr.append(cell(String(l.no), "left"), cell(l.label, "left", emphasis),
              cell(usd(cert[l.key] as number), "right", emphasis));
    t.appendChild(tr);
  }
  return t;
}

/** The continuation sheet. Wrapped by the caller in an overflow container — it is a wide table. */
function sheetTable(sheet: Sheet): HTMLTableElement {
  const t = document.createElement("table");
  t.style.cssText = "width:100%;border-collapse:collapse;font-size:12px;min-width:640px";
  const head = document.createElement("tr");
  head.style.cssText = "border-bottom:1px solid var(--line);color:var(--muted)";
  for (const [h, a] of [["Item", "left"], ["Description", "left"], ["Scheduled", "right"],
    ["Previous", "right"], ["This period", "right"], ["Stored", "right"],
    ["Completed", "right"], ["%", "right"], ["Balance", "right"], ["Retainage", "right"]] as const) {
    const th = document.createElement("th");
    th.textContent = h;
    th.style.cssText = `padding:3px 8px;text-align:${a};font-weight:500`;
    head.appendChild(th);
  }
  t.appendChild(head);
  for (const l of sheet.lines) {
    const tr = document.createElement("tr");
    tr.style.cssText = "border-top:1px solid var(--line)";
    tr.append(cell(l.item_no ?? "—"), cell(l.description ?? "—"),
              cell(usd(l.scheduled_value), "right"), cell(usd(l.completed_prev), "right"),
              cell(usd(l.completed_this), "right"), cell(usd(l.materials_stored), "right"),
              cell(usd(l.total_completed_stored), "right"), cell(`${l.percent}%`, "right"),
              cell(usd(l.balance_to_finish), "right"), cell(usd(l.retainage), "right"));
    t.appendChild(tr);
  }
  const tot = document.createElement("tr");
  tot.style.cssText = "border-top:2px solid var(--line);font-weight:600";
  const T = sheet.totals;
  tot.append(cell(""), cell("Totals", "left", true), cell(usd(T.scheduled), "right", true),
             cell(usd(T.prev), "right", true), cell(usd(T.this), "right", true),
             cell(usd(T.stored), "right", true), cell(usd(T.completed), "right", true),
             cell("", "right"), cell(usd(T.balance), "right", true), cell(usd(T.retainage), "right", true));
  t.appendChild(tot);
  return t;
}

/**
 * Open the review dialog for a project's CURRENT G702/G703.
 *
 * `ready()` is called in a `finally`: the user's wait ends when the dialog is usable OR when the
 * error appears, and this panel genuinely fetches, so it is not one of the data-in-hand dialogs
 * exempt from reporting (see the classification in `src/ui/panelReady.test.ts`).
 */
export async function payAppReviewModal(api: ApiClient, pid: string): Promise<void> {
  const { card, close, ready } = modalShell("Pay application — review", 560);
  const body = document.createElement("div");
  body.className = "meta";
  body.textContent = "Loading the certificate…";
  card.appendChild(body);

  try {
    const [cert, sheet] = await Promise.all([api.g702(pid), api.g703(pid)]);
    const s = summary(cert, sheet);
    body.textContent = "";
    body.className = "";

    const head = document.createElement("div");
    head.style.cssText = "display:flex;gap:14px;flex-wrap:wrap;align-items:baseline";
    const due = document.createElement("div");
    due.style.cssText = "font-size:20px;font-weight:600";
    due.textContent = usd(s.due);
    const ctx = document.createElement("div");
    ctx.className = "meta";
    ctx.textContent = `Application ${cert.application_no}`
      + (cert.period ? ` · ${cert.period}` : "")
      + ` · ${s.percent}% complete`
      + (cert.retainage_released ? " · retainage released" : "");
    head.append(due, ctx);
    body.appendChild(head);

    // The arithmetic, checked. A certificate that does not add up is the thing a reviewer most needs
    // told, so it sits above the numbers rather than below them.
    const verdict = document.createElement("div");
    verdict.style.cssText = "margin:10px 0;padding:8px 10px;border-radius:6px;font-size:13px;"
      + `border:1px solid ${s.sound ? "var(--status-good)" : "var(--status-crit)"}`;
    if (s.sound) {
      verdict.textContent = "✓ The certificate adds up — all six identities hold against the continuation sheet.";
    } else {
      verdict.textContent = `⚠ ${s.failures.length} check(s) failed:`;
      for (const f of s.failures) {
        const li = document.createElement("div");
        li.className = "meta";
        li.style.marginTop = "3px";
        li.textContent = `${f.label} — ${f.detail}`;
        verdict.appendChild(li);
      }
    }
    body.appendChild(verdict);

    body.appendChild(certTable(cert));

    // Line 7's provenance — the figure the over-billing bug corrupted. Saying which basis it has
    // keeps a reconstruction from reading as a signed fact.
    const basis = document.createElement("div");
    basis.className = "meta";
    basis.style.cssText = "margin-top:8px;font-size:12px";
    basis.textContent = `Line 7 ${line7Note(line7Basis(cert, sheet))}.`;
    body.appendChild(basis);

    const sheetTitle = document.createElement("div");
    sheetTitle.className = "section-title";
    sheetTitle.style.marginTop = "14px";
    sheetTitle.textContent = `G703 continuation sheet — ${sheet.lines.length} line(s)`;
    body.appendChild(sheetTitle);
    const scroll = document.createElement("div");
    scroll.style.cssText = "overflow-x:auto";
    scroll.appendChild(sheetTable(sheet));
    body.appendChild(scroll);

    const row = document.createElement("div");
    row.style.cssText = "display:flex;gap:6px;justify-content:flex-end;margin-top:14px";
    const pdf = document.createElement("button");
    pdf.className = "tool-btn";
    pdf.textContent = "⬇ Download as PDF";
    pdf.onclick = async () => {
      pdf.disabled = true;
      try {
        const blob = await api.payAppPdf(pid, cert.application_no);
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `pay-app-${cert.application_no}.pdf`;
        a.click();
        URL.revokeObjectURL(a.href);
      } finally { pdf.disabled = false; }
    };
    const done = document.createElement("button");
    done.className = "tool-btn";
    done.textContent = "Close";
    done.onclick = close;
    row.append(pdf, done);
    body.appendChild(row);
  } catch (e) {
    body.className = "meta";
    body.textContent = `Could not load the certificate: ${(e as Error).message}`;
  } finally {
    ready();
  }
}
