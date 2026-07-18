import type { ApiClient, StampTemplate } from "./api/client";
import { money } from "./ui/charts";
import { toast, escapeHtml } from "./ui/feedback";
import { modalShell } from "./ui/modal";
import { askText } from "./ui/prompt";
import { showResult } from "./ui/result";

/** REL-4 leaf — the Report Center modal: every exportable report (PDF/Excel/markup) plus the
 *  interactive project tools & analytics (drawing-set register + issuance + pre-flight gate,
 *  WH-347 payroll, PDF tools, project health, assistant, field-verification coverage, …).
 *  Extracted verbatim from main.ts; the host passes its ApiClient + current project id. */

export async function openReportCenter(api: ApiClient, projectId: string | null) {
  if (!projectId) { toast("Open a project first", "info"); return; }
  const pid = projectId;
  let cat;
  try { cat = (await api.reports()).reports; } catch { toast("couldn't load reports (connect a project)", "error"); return; }
  const { card } = modalShell("Report Center", 420);
  card.append(Object.assign(document.createElement("div"), { className: "meta", textContent: "Detailed reports — download as PDF or Excel:" }));
  const groups = [...new Set(cat.map((r) => r.group))];
  for (const g of groups) {
    const h = document.createElement("div"); h.className = "section-title"; h.textContent = g; h.style.marginTop = "8px"; card.appendChild(h);
    for (const rep of cat.filter((r) => r.group === g)) {
      const row = document.createElement("div"); row.className = "layer-row";
      const name = document.createElement("span"); name.className = "name"; name.textContent = rep.name;
      const pdf = document.createElement("button"); pdf.className = "tool-btn"; pdf.textContent = "⬇ PDF";
      pdf.onclick = () => window.open(api.reportUrl(pid, rep.id, "pdf"), "_blank");
      const mk = document.createElement("button"); mk.className = "tool-btn"; mk.textContent = "🖊 Markup";
      mk.title = "Open the report in the in-app viewer to review / mark up";
      mk.onclick = async () => { const o = await import("./drawings/openPdf"); await o.openPdfUrl(api, api.reportUrl(pid, rep.id, "pdf"), `${rep.name}.pdf`, { saveLabel: "Save to Documents", onSave: o.saveToDocuments(api, pid) }); };
      const xls = document.createElement("button"); xls.className = "tool-btn"; xls.textContent = "⬇ Excel";
      xls.onclick = () => window.open(api.reportUrl(pid, rep.id, "xlsx"), "_blank");
      row.append(name, pdf, mk, xls); card.appendChild(row);
    }
  }
  // interactive / parameterized analytics that aren't plain PDF reports
  const th = document.createElement("div"); th.className = "section-title"; th.textContent = "Project tools & analytics"; th.style.marginTop = "8px"; card.appendChild(th);
  const tool = (label: string, fn: () => void) => {
    const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = label;
    b.style.cssText = "display:block;width:100%;text-align:left;margin:2px 0"; b.onclick = fn; card.appendChild(b);
  };
  const table = (body: HTMLElement, headers: string[], rows: (string | number)[][]) => {
    // append a real element — `innerHTML +=` would reparse the whole body and silently detach every
    // event handler wired to earlier buttons (bit the issuance tools: the register table killed them)
    const t = document.createElement("table");
    t.className = "fin-table"; t.style.cssText = "width:100%;font-size:12px";
    t.innerHTML = "<tr>"
      + headers.map((h) => `<th style="text-align:left">${escapeHtml(h)}</th>`).join("") + "</tr>"
      + rows.map((r) => "<tr>" + r.map((c) => `<td>${escapeHtml(String(c))}</td>`).join("") + "</tr>").join("");
    body.appendChild(t);
  };
  tool("🩺 Project health (executive rollup)", () => showResult("Project health", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const h = await api.projectHealth(pid);
      const dot = (s: string) => s === "red" ? "🔴" : s === "amber" ? "🟡" : s === "green" ? "🟢" : "⚪";
      body.innerHTML = `<div style="font-size:22px;font-weight:700">${dot(h.overall_status)} ${h.health_score ?? "—"}/100 · ${h.overall_status.toUpperCase()}</div>`
        + `<div class="meta">${h.open_items_total} open items · ${h.overdue_items_total} overdue across domains</div>`;
      table(body, ["Domain", "Status", "Summary", "Open", "Overdue"],
        h.domains.map((d) => [`${dot(d.status)} ${d.label}`, d.status.toUpperCase(), d.headline, d.open_count, d.overdue_count]));
      if (h.attention_items.length) {
        body.innerHTML += `<div class="section-title" style="margin-top:12px">Attention items</div>`;
        table(body, ["Status", "Domain", "Issue"], h.attention_items.map((a) => [`${dot(a.status)} ${a.status.toUpperCase()}`, a.domain, a.issue]));
      } }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("🤖 Project assistant — ask about RFIs, budget, schedule…", () => showResult("Project assistant", (body) => {
    const inp = document.createElement("input"); inp.type = "text"; inp.placeholder = "e.g. how many open RFIs? what's the SPI?"; inp.style.cssText = "width:100%;padding:8px;box-sizing:border-box";
    const ans = document.createElement("div"); ans.style.cssText = "margin-top:10px;white-space:pre-wrap;line-height:1.5";
    const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Ask"; go.style.marginTop = "8px";
    const run = async () => { const q = inp.value.trim(); if (!q) return; ans.textContent = "Thinking…"; go.disabled = true;
      try { const r = await api.askProject(pid, q); ans.textContent = r.answer || ""; if (r.source !== "claude" && r.snapshot) ans.textContent = (r.answer || "") + "\n\n" + JSON.stringify(r.snapshot, null, 2); }
      catch (e) { ans.textContent = (e as Error).message; } finally { go.disabled = false; } };
    go.onclick = () => void run(); inp.addEventListener("keydown", (e) => { if (e.key === "Enter") void run(); });
    body.append(inp, go, ans); inp.focus();
  }));
  tool("💵 Certified payroll (WH-347)", () => showResult("Certified payroll (WH-347)", (body) => {
    body.innerHTML = `<div class="meta">Weekly Davis-Bacon certified payroll from timesheets × labor rates.</div>`;
    const wk = document.createElement("input"); wk.type = "date"; wk.style.cssText = "margin:8px 8px 8px 0;padding:6px";
    const open = document.createElement("button"); open.className = "file-btn"; open.textContent = "⬇ Open WH-347 PDF";
    open.onclick = async () => { const o = await import("./drawings/openPdf"); await o.openPdfUrl(api, api.wh347Url(pid, wk.value || undefined), "WH-347.pdf", { saveLabel: "Save to Documents", onSave: o.saveToDocuments(api, pid) }); };
    const sum = document.createElement("button"); sum.className = "file-btn"; sum.textContent = "Preview"; sum.style.marginLeft = "4px";
    const out = document.createElement("div"); out.style.marginTop = "10px";
    sum.onclick = async () => { try { const p = await api.payroll(pid, wk.value || undefined); out.innerHTML = `<div class="meta">Week ${p.week_ending} · ${p.worker_count} workers · ${p.total_hours} h · total ${money(p.total_gross)}</div>`;
      table(out, ["Worker", "Hours", "Gross"], p.rows.map((r: any) => [r.worker, r.total, money(r.gross)])); } catch (e) { out.textContent = (e as Error).message; } };
    body.append(wk, open, sum, out);
  }));
  tool("📐 Drawing-set register", () => showResult("Drawing-set register", async (body) => {
    const load = async () => {
      body.innerHTML = `<div class="meta">Loading…</div>`;
      try {
        const d = await api.drawingSet(pid);
        body.innerHTML = `<div class="meta">${d.current_count} current · ${d.new_count} new · ${d.revised_count} revised · ${d.superseded_count} superseded · ${d.sheet_count} sheets</div>`;
        // generate a full discipline sheet set (one NCS series per discipline: S-/A-/M-/E-/P-/FP-/FA-/T-)
        const gen = document.createElement("button"); gen.className = "file-btn"; gen.textContent = "⚙ Generate discipline sheet set";
        gen.style.margin = "6px 6px 6px 0";
        gen.onclick = async () => {
          gen.disabled = true; gen.textContent = "Generating…";
          try {
            const g = await api.generateDrawingSet(pid, { all: true });
            toast(`Created ${g.created} sheets across ${Object.keys(g.by_discipline).length} disciplines`
              + (g.skipped_existing ? ` (${g.skipped_existing} already existed)` : ""), "success");
            await load();
          } catch (e) { toast((e as Error).message, "error"); gen.disabled = false; gen.textContent = "⚙ Generate discipline sheet set"; }
        };
        body.appendChild(gen);
        const xmit = document.createElement("a"); xmit.className = "file-btn"; xmit.textContent = "⬇ Transmittal (PDF)";
        xmit.href = api.drawingTransmittalUrl(pid); xmit.target = "_blank"; xmit.rel = "noopener"; xmit.style.margin = "6px 0";
        body.appendChild(xmit);
        if (Object.keys(d.by_discipline || {}).length)
          body.insertAdjacentHTML("beforeend", `<div class="meta" style="margin:4px 0">By discipline: ${Object.entries(d.by_discipline).map(([k, v]) => `${escapeHtml(k)} ${v}`).join(" · ")}</div>`);

        // --- AIA issuance: issue the set for a purpose + issuance register + sheet×issuance matrix ---
        const iss = document.createElement("div"); iss.style.margin = "10px 0 4px";
        iss.innerHTML = `<div class="section-title">Issuances (AIA)</div>`;
        const row = document.createElement("div"); row.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:4px 0";
        const sel = document.createElement("select"); sel.className = "portal-filter";
        try { const pu = await api.drawingIssuancePurposes(pid); for (const p of pu.purposes) { const o = document.createElement("option"); o.value = p.name; o.textContent = p.name; sel.appendChild(o); } } catch { /* purposes optional */ }
        // pre-flight gate: PASS/HOLD verdict + deep-linked checklist; the Issue button runs it first
        const gateOut = document.createElement("div"); gateOut.style.margin = "4px 0";
        const STATUS_ICON: Record<string, string> = { pass: "✅", warn: "⚠️", fail: "⛔" };
        const renderGate = (g: import("./api/types").PreflightGate) => {
          gateOut.innerHTML = `<div class="meta" style="font-weight:600">${g.ready ? "🟢" : "🔴"} ${escapeHtml(g.verdict)}`
            + (g.overall_score != null ? ` · health ${g.overall_score}` : "")
            + ` · ${g.blocking} blocking · ${g.warnings} warning(s)</div>`;
          for (const c of g.checks) {
            const line = document.createElement("div"); line.className = "meta"; line.style.margin = "2px 0";
            line.textContent = `${STATUS_ICON[c.status] ?? "•"} ${c.label} — ${c.detail}`;
            if (c.link) {
              const a = document.createElement("a"); a.href = api.url(c.link); a.target = "_blank"; a.rel = "noopener";
              a.textContent = " ↗"; a.title = `Open ${c.link}`; line.appendChild(a);
            }
            gateOut.appendChild(line);
          }
        };
        const pfb = document.createElement("button"); pfb.className = "file-btn"; pfb.textContent = "🚦 Pre-flight";
        pfb.title = "Run the pre-issuance gate: model health · classification/keynotes · drawing-set QA · pinned IDS · open issues";
        pfb.onclick = async () => {
          pfb.disabled = true; const prev = pfb.textContent; pfb.textContent = "Checking…";
          try { renderGate(await api.preflight(pid)); } catch (e) { toast((e as Error).message, "error"); }
          pfb.disabled = false; pfb.textContent = prev;
        };
        const isb = document.createElement("button"); isb.className = "file-btn"; isb.textContent = "📤 Issue set";
        let issueAnyway = false;                       // second click after a HOLD issues without enforcement
        isb.onclick = async () => {
          isb.disabled = true; const prev = "📤 Issue set"; isb.textContent = "Issuing…";
          try {
            const r = await api.issueDrawingSet(pid, { purpose: sel.value, enforce: !issueAnyway });
            toast(`Issued ${r.sheet_count} sheets for ${r.purpose}`
              + (r.preflight && !r.preflight.ready ? " (pre-flight HOLD overridden)" : ""), "success");
            issueAnyway = false; await load();
          } catch (e) {
            const msg = (e as Error).message;
            if (!issueAnyway && msg.includes("-> 409")) {
              // a 409 is either the pre-flight HOLD or "no sheets" — the gate itself tells us which;
              // on HOLD, show the evidence and arm a one-shot override
              let hold = false;
              try { const g = await api.preflight(pid); hold = !g.ready; if (hold) renderGate(g); }
              catch { /* gate detail optional */ }
              if (hold) {
                toast("Pre-flight HOLD — review the blockers below, or click again to issue anyway", "error");
                issueAnyway = true; isb.disabled = false; isb.textContent = "⛔ Issue anyway"; return;
              }
            }
            toast(msg, "error"); isb.disabled = false; isb.textContent = prev;
          }
        };
        row.append(sel, pfb, isb); iss.appendChild(row); iss.appendChild(gateOut); body.appendChild(iss);
        try {
          const reg = await api.drawingIssuances(pid);
          if (reg.issuance_count) {
            table(body, ["Issuance", "Issued For", "Date", "Sheets"], reg.issuances.map((i: any) =>
              [i.number ?? "", i.purpose ?? "", i.issue_date ?? "", String(i.sheet_count ?? "")]));
            // per-issuance transmittal PDFs (stamped with the purpose) + digitally-sealed variant
            const links = document.createElement("div"); links.className = "meta"; links.style.margin = "4px 0";
            for (const i of reg.issuances as any[]) {
              const a = document.createElement("a"); a.href = api.issuanceTransmittalUrl(pid, i.id);
              a.target = "_blank"; a.rel = "noopener"; a.textContent = `⬇ ${i.number ?? "issuance"}`;
              a.style.marginRight = "6px"; links.appendChild(a);
              const s = document.createElement("a"); s.href = api.issuanceSealedUrl(pid, i.id);
              s.target = "_blank"; s.rel = "noopener"; s.textContent = "🔏 sealed"; s.title = "Digitally sealed (PAdES) for permit submittal";
              s.style.marginRight = "14px"; links.appendChild(s);
            }
            body.appendChild(links);
            // sheet × issuance matrix (front-of-set grid): each sheet's revision per issuance
            const mx = await api.drawingIssuanceMatrix(pid);
            const cols = mx.issuances.map((i: any) => `${i.abbr} ${i.issue_date ?? ""}`);
            body.insertAdjacentHTML("beforeend", `<div class="meta" style="margin:6px 0 2px">Sheet × issuance matrix</div>`);
            table(body, ["Sheet", "Discipline", ...cols], mx.rows.map((r) => [r.sheet_number, r.discipline ?? "", ...r.cells.map((c) => c ?? "—")]));
          }
        } catch (e) { body.insertAdjacentHTML("beforeend", `<div class="meta">${escapeHtml((e as Error).message)}</div>`); }

        // revision / delta register (AIA revision block, newest first, with the driving instrument)
        try {
          const rv = await api.drawingRevisions(pid);
          if (rv.delta_count) {
            body.insertAdjacentHTML("beforeend", `<div class="section-title" style="margin-top:10px">Revisions (${rv.delta_count})</div>`);
            table(body, ["Sheet", "Rev", "Date", "Description", "Instrument"], rv.revisions.map((r) =>
              [r.sheet_number, r.rev ?? "", r.date ?? "", r.description ?? "", r.instrument ? `${r.instrument.type ?? ""} ${r.instrument.ref ?? ""}`.trim() : ""]));
          }
        } catch { /* revisions optional */ }

        body.insertAdjacentHTML("beforeend", `<div class="section-title" style="margin-top:10px">Sheet index</div>`);
        table(body, ["Sheet", "Title", "Discipline", "Rev", "Status"], d.sheet_index.map((s: any) => [s.sheet_number, s.title ?? "", s.discipline ?? "", s.current_revision ?? "", s.change]));
      } catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
    };
    await load();
  }));
  tool("🗂 PDF tools (merge / split / rotate)", () => showResult("PDF tools", async (body) => {
    body.innerHTML = `<div class="meta">Combine, split, rotate, or extract pages from PDFs — server-side (pypdf). Files stay unencrypted; nothing is stored.</div>`;
    const dl = (blob: Blob, name: string) => { const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000); };
    const pick = (multi: boolean): Promise<File[]> => new Promise((res) => { const i = document.createElement("input"); i.type = "file"; i.accept = ".pdf,application/pdf"; i.multiple = multi; i.onchange = () => res(i.files ? Array.from(i.files) : []); i.click(); });
    const stem = (n: string) => n.replace(/\.pdf$/i, "");
    const mk = (label: string, on: () => Promise<void>) => { const b = document.createElement("button"); b.className = "file-btn"; b.textContent = label; b.style.margin = "6px 6px 0 0";
      b.onclick = async () => { b.disabled = true; try { await on(); } catch (e) { toast((e as Error).message, "error"); } b.disabled = false; }; return b; };
    body.append(
      mk("👁 Open & mark up…", async () => { const [f] = await pick(false); if (!f) return; const [{ openPdfTakeoff }, { saveToDocuments }] = await Promise.all([import("./drawings/pdfTakeoff"), import("./drawings/openPdf")]); await openPdfTakeoff(f, { saveLabel: "Save to Documents", onSave: saveToDocuments(api, pid) }); }),
      mk("⧉ Merge PDFs…", async () => { const fs = await pick(true); if (fs.length < 2) { toast("pick 2 or more PDFs", "error"); return; } dl(await api.pdfMerge(fs), "merged.pdf"); toast(`merged ${fs.length} PDFs`, "success"); }),
      mk("✂ Split to pages (zip)…", async () => { const [f] = await pick(false); if (!f) return; dl(await api.pdfSplitZip(f), stem(f.name) + "-pages.zip"); toast("split into pages", "success"); }),
      mk("↻ Rotate 90°…", async () => { const [f] = await pick(false); if (!f) return; dl(await api.pdfRotate(f, 90), stem(f.name) + "-rotated.pdf"); toast("rotated", "success"); }),
      mk("⇲ Extract pages…", async () => { const [f] = await pick(false); if (!f) return; const p = await askText("Extract Pages", { label: "Pages to extract (e.g. 1,3,5-7):", value: "1" }); if (!p) return; dl(await api.pdfExtract(f, p), stem(f.name) + "-extract.pdf"); toast("extracted", "success"); }),
    );
  }));
  tool("🏛 Stamp & seal PDF", () => showResult("Stamp & seal", async (body) => {
    body.innerHTML = `<div class="meta">Loading stamp library…</div>`;
    let lib: StampTemplate[];
    try { lib = (await api.stampLibrary()).templates; }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; return; }
    const byId: Record<string, StampTemplate> = Object.fromEntries(lib.map((t) => [t.id, t]));
    body.innerHTML = `<div class="meta">Apply an A/E/C review stamp (EJCDC / CSI dispositions with the design-conformance disclaimer), an inspection or status stamp, or a professional seal (visible seal + tamper-evident PAdES signature). Server-side; nothing is stored.</div>`;
    const dl = (blob: Blob, name: string) => { const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000); };
    const pickFile = (): Promise<File | null> => new Promise((res) => { const i = document.createElement("input"); i.type = "file"; i.accept = ".pdf,application/pdf"; i.onchange = () => res(i.files && i.files[0] ? i.files[0] : null); i.click(); });
    const today = new Date().toISOString().slice(0, 10);
    const me = localStorage.getItem("aec_markup_user") || localStorage.getItem("aec_user") || "";
    let file: File | null = null;

    const fileBtn = document.createElement("button"); fileBtn.className = "file-btn"; fileBtn.textContent = "① Choose PDF…"; fileBtn.style.margin = "8px 8px 0 0";
    const fileLbl = document.createElement("span"); fileLbl.className = "meta"; fileLbl.textContent = " no PDF chosen";
    fileBtn.onclick = async () => { const f = await pickFile(); if (f) { file = f; fileLbl.textContent = ` ${f.name}`; } };

    const sel = document.createElement("select"); sel.className = "portal-filter"; sel.style.margin = "8px 0";
    for (const t of lib) { const o = document.createElement("option"); o.value = t.id; o.textContent = `${t.category === "seal" ? "🏛" : t.category === "review" ? "📋" : t.category === "inspection" ? "🔍" : "🔖"} ${t.name}`; sel.appendChild(o); }

    const form = document.createElement("div"); form.style.margin = "8px 0";
    const row = (label: string, el: HTMLElement) => { const d = document.createElement("label"); d.style.cssText = "display:flex;gap:8px;align-items:center;margin:4px 0;font-size:12px"; const s = document.createElement("span"); s.textContent = label; s.style.cssText = "min-width:130px;color:var(--muted,#888)"; d.append(s, el); return d; };
    const inp = (val = "") => { const i = document.createElement("input"); i.className = "portal-filter"; i.value = val; i.style.flex = "1"; return i; };
    const inputs: Record<string, HTMLInputElement> = {};
    let dispSel: HTMLSelectElement | null = null;
    const act = document.createElement("button"); act.className = "file-btn"; act.style.margin = "8px 0 0";
    const note = document.createElement("div"); note.className = "meta"; note.style.marginTop = "6px";

    function renderForm() {
      const t = byId[sel.value]; form.innerHTML = ""; note.textContent = "";
      for (const k of Object.keys(inputs)) delete inputs[k];
      dispSel = null;
      if (!t) return;
      const isSeal = t.category === "seal";
      if (t.dispositions && t.dispositions.length) {
        dispSel = document.createElement("select"); dispSel.className = "portal-filter"; dispSel.style.flex = "1";
        for (const d of t.dispositions) { const o = document.createElement("option"); o.value = d; o.textContent = d; dispSel.appendChild(o); }
        form.append(row(t.category === "inspection" ? "Result" : "Disposition", dispSel));
      }
      for (const f of t.fields) {
        const dflt = f.type === "date" ? today : (f.type === "user" ? me : "");
        const i = inp(dflt); inputs[f.key] = i; form.append(row(f.label, i));
      }
      const page = inp("1"); page.type = "number"; page.style.maxWidth = "70px"; inputs.__page = page;
      const x = inp("36"); x.type = "number"; x.style.maxWidth = "70px"; inputs.__x = x;
      const y = inp("36"); y.type = "number"; y.style.maxWidth = "70px"; inputs.__y = y;
      const pos = document.createElement("div"); pos.style.cssText = "display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:12px;margin:4px 0";
      pos.append(Object.assign(document.createElement("span"), { textContent: "Page/X/Y (pts from top-left):", style: "min-width:130px;color:var(--muted,#888)" }), page, x, y);
      form.append(pos);
      if (isSeal) form.insertAdjacentHTML("beforeend", `<div class="meta" style="margin-top:6px">The seal is rendered visibly and signed with a tamper-evident PAdES signature applied last. The platform's self-signed certificate is for demonstration / tamper-evidence — configure the licensee's own certificate for board-accepted sealing.</div>`);
      act.textContent = isSeal ? "🏛 Apply seal & sign" : "📋 Apply stamp";
    }
    sel.onchange = renderForm; renderForm();

    act.onclick = async () => {
      if (!file) { toast("choose a PDF first", "error"); return; }
      const t = byId[sel.value];
      if (!t) return;
      const values: Record<string, string> = {};
      for (const f of t.fields) { const iv = inputs[f.key]; if (iv?.value) values[f.key] = iv.value; }
      const page = parseInt(inputs.__page?.value ?? "") || 1, x = parseFloat(inputs.__x?.value ?? "") || 36, y = parseFloat(inputs.__y?.value ?? "") || 36;
      act.disabled = true;
      try {
        if (t.category === "seal") {
          const r = await api.pdfSeal(file, { template_id: t.id, profile: values, page, x, y });
          dl(r.blob, file.name.replace(/\.pdf$/i, "") + "-sealed.pdf");
          note.textContent = r.compliance; toast(r.sealed ? "sealed & signed" : "seal applied", "success");
        } else {
          const blob = await api.pdfStamp(file, { template_id: t.id, page, x, y, disposition: dispSel?.value || "", values });
          dl(blob, file.name.replace(/\.pdf$/i, "") + "-stamped.pdf");
          toast("stamp applied", "success");
        }
      } catch (e) { toast((e as Error).message, "error"); }
      act.disabled = false;
    };

    body.append(fileBtn, fileLbl, document.createElement("br"), sel, form, act, note);
  }));
  tool("📋 ITB coverage (bid invitations)", () => showResult("ITB coverage", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const t = await api.itb(pid); body.innerHTML = `<div class="meta">${t.package_count} packages · ${t.total_responses}/${t.total_invited} responses · ${t.packages_without_bids} with no bids</div>`;
      table(body, ["Package", "Invited", "Responses", "Coverage"], t.rows.map((r: any) => [r.package, r.invited, r.responses, r.coverage])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("💵 T&M / eTicket rollup", () => showResult("Time & Material rollup", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.tmSummary(pid); body.innerHTML = `<div class="meta">${s.ticket_count} tickets · labor ${money(s.labor_total)} · material ${money(s.material_total)} · equipment ${money(s.equipment_total)} · <b>total ${money(s.grand_total)}</b> · unbilled ${money(s.unbilled_total)}</div>`;
      table(body, ["Ref", "Subject", "Total", "Status"], s.rows.map((r: any) => [r.ref ?? "", r.subject ?? "", money(r.total), r.status]));
      // T&M rolled up by the change event each ticket is linked to (field T&M -> CO -> billing)
      const bce = await api.tmByChangeEvent(pid);
      if (bce.groups.length) {
        body.insertAdjacentHTML("beforeend", `<div class="meta" style="margin-top:8px">By change event · linked ${money(bce.linked_total)} · unassigned ${money(bce.unassigned_total)}</div>`);
        table(body, ["Change event", "Subject", "Tickets", "Total"], bce.groups.map((g: any) => [g.ref ?? "—", g.subject ?? "", g.ticket_count, money(g.total)]));
      } }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("▟ Site feasibility (zoning envelope)", () => showResult("Site feasibility / zoning envelope", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const f = await api.feasibility(pid);
      if (f.error) { body.innerHTML = `<div class="meta">${escapeHtml(f.error)} — add a <b>Zoning &amp; Site</b> record under Preconstruction.</div>`; return; }
      const sf = (v: number | null | undefined) => (typeof v === "number" ? `${Math.round(v).toLocaleString()} SF` : "—");
      const m = f.model;
      body.innerHTML = `<div class="meta">${escapeHtml(f.site ?? "Site")} · ${(f.site_area_sf ?? 0).toLocaleString()} SF (${f.site_area_acres ?? "—"} ac) · <b>allowed ${sf(f.allowed_gfa_sf)}</b> (binds on ${f.binding_constraint ?? "—"}) · ${f.max_floors ?? "—"} floors · yield ${f.unit_yield ?? "—"} units · parking ${f.parking_required ?? "—"}${m ? ` · model uses ${m.pct_of_allowed}% of allowed (${m.status})` : ""}</div>`;
      table(body, ["Constraint", "Limit GFA", "Basis"], (f.constraints ?? []).map((c) => [c.constraint, sf(c.limit_gfa_sf), c.basis]));
      if (m) table(body, ["Actual GFA", "FAR used", "% of allowed", "Headroom", "Status"], [[sf(m.actual_gfa_sf), String(m.far_used), `${m.pct_of_allowed}%`, sf(m.headroom_gfa_sf), m.status]]);
      if (f.warnings?.length) body.insertAdjacentHTML("beforeend", `<div class="meta" style="margin-top:8px">${f.warnings.map((w) => "• " + escapeHtml(w)).join("<br>")}</div>`); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("⤓ Import clash report (Solibri / Navisworks XLSX)", () => showResult("Import clash report", (body) => {
    body.innerHTML = `<div class="meta">Upload a Solibri or Navisworks clash/coordination report (.xlsx). Each row becomes a <b>coordination issue</b> (GUIDs anchor it on the model; issues round-trip to BCF). Columns are auto-detected.</div>`;
    const bar = document.createElement("div"); bar.style.cssText = "display:flex;gap:8px;margin-top:8px;align-items:center";
    const inp = document.createElement("input"); inp.type = "file"; inp.accept = ".xlsx"; inp.setAttribute("aria-label", "Clash report XLSX");
    const out = document.createElement("div"); out.style.marginTop = "8px";
    inp.onchange = async () => {
      const f = inp.files?.[0]; if (!f) return; out.innerHTML = `<div class="meta">Importing ${escapeHtml(f.name)}…</div>`;
      try { const r = await api.importClashXlsx(pid, f);
        out.innerHTML = `<div class="meta"><b>${r.imported}</b> coordination issue(s) imported from sheet “${escapeHtml(r.sheet)}” · columns: ${r.detected_columns.map(escapeHtml).join(", ") || "—"}</div>`; }
      catch (e) { out.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
    };
    bar.append(inp); body.append(bar, out);
  }));
  tool("▟ Compare feasibility scenarios", () => showResult("Compare feasibility scenarios", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const c = await api.feasibilityCompare(pid);
      if (!c.count) { body.innerHTML = `<div class="meta">Add two or more <b>Zoning &amp; Site</b> records (one per scheme) to compare.</div>`; return; }
      const sf = (v: number | null | undefined) => (typeof v === "number" ? `${Math.round(v).toLocaleString()} SF` : "—");
      body.innerHTML = `<div class="meta"><b>${c.count} scheme(s)</b> ranked by buildable yield · best: ${escapeHtml(c.best_ref ?? "—")}</div>`;
      table(body, ["Scheme", "Site", "FAR", "Floors", "Allowed GFA", "Binds on", "Units", "Parking", "Δ units"],
        c.scenarios.map((s) => [s.ref ?? "", s.site ?? "", s.far ?? "—", s.max_floors ?? "—", sf(s.allowed_gfa_sf),
          s.binding_constraint ?? "—", s.unit_yield ?? "—", s.parking_required ?? "—",
          (s.delta_units ?? 0) === 0 ? "—" : String(s.delta_units)])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("§ Spec submittal log (from specs)", () => showResult("Spec-driven submittal log", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.specSubmittalLog(pid);
      body.innerHTML = `<div class="meta">${s.spec_count} spec sections · ${s.required_total} required submittals · ${s.logged_total} logged · <b>${s.missing_total} missing</b> · coverage ${s.coverage_pct ?? "—"}%</div>`;
      table(body, ["Section", "Title", "Required", "Logged", "Missing", "Responsible"], s.rows.map((r: any) => [r.section_number ?? "", r.title ?? "", r.required_count, r.logged_count, r.missing_count ? "⚠ " + r.missing_count : "0", r.responsible ?? ""])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("✨ Extract submittals from a spec", () => showResult("Extract submittals from spec", (body) => {
    body.innerHTML = `<div class="meta">Paste a spec section (or its Part 1 “Submittals” article). Extraction uses AI when a key is set, else a built-in parser.</div>`;
    const ta = document.createElement("textarea"); ta.placeholder = "SECTION 03 30 00 — CAST-IN-PLACE CONCRETE\n1.3 SUBMITTALS\n  A. Product Data: for each mix design.\n  B. Shop Drawings: reinforcement placing drawings.\n  C. Samples: …";
    ta.setAttribute("aria-label", "Specification text"); ta.style.cssText = "width:100%;min-height:120px;margin-top:8px;font-family:monospace;font-size:12px";
    const bar = document.createElement("div"); bar.style.cssText = "display:flex;gap:8px;margin-top:8px;align-items:center";
    const ex = document.createElement("button"); ex.className = "file-btn"; ex.textContent = "Extract";
    const cr = document.createElement("button"); cr.className = "file-btn"; cr.textContent = "Extract + add to log";
    const out = document.createElement("div"); out.style.marginTop = "8px";
    const run = (create: boolean) => async () => {
      if (!ta.value.trim()) return; ex.disabled = cr.disabled = true; out.innerHTML = `<div class="meta">Extracting…</div>`;
      try { const r = await api.extractSubmittals(pid, ta.value, create);
        out.innerHTML = `<div class="meta">${r.items.length} submittal(s) · source: ${r.source}${r.created_submittals != null ? ` · ${r.created_submittals} added to the log` : ""}${r.message ? " · " + escapeHtml(r.message) : ""}</div>`;
        table(out, ["Section", "Submittal", "Type"], r.items.map((i) => [i.section_number ?? "", i.title, i.type])); }
      catch (e) { out.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
      finally { ex.disabled = cr.disabled = false; }
    };
    ex.onclick = run(false); cr.onclick = run(true);
    bar.append(ex, cr); body.append(ta, bar, out);
  }));
  tool("🎯 Preconstruction alignment", () => showResult("Preconstruction alignment", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const a = await api.preconAlignment(pid);
      const varr = a.variance_to_budget == null ? "" : ` · ${a.variance_to_budget > 0 ? "OVER" : "under"} budget ${money(Math.abs(a.variance_to_budget))}`;
      body.innerHTML = `<div class="meta"><b>Alignment ${a.alignment_score ?? "—"}/100 · ${String(a.overall_status).toUpperCase()}</b> · latest ${money(a.latest_total)} (${a.latest_milestone ?? "—"})${varr} · VE accepted ${money(a.ve_accepted)} · ${a.open_decisions} open decisions · ${a.open_assumptions} open assumptions</div>`;
      table(body, ["Domain", "Status", "Detail"], a.domains.map((d: any) => [d.label, String(d.status).toUpperCase(), d.headline])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("✔ Decision log", () => showResult("Decision log", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.decisionLog(pid);
      body.innerHTML = `<div class="meta">${s.decision_count} decisions · ${s.open_count} open · ${s.disputed_count} disputed · cost exposure ${money(s.open_cost_exposure)} · ${s.open_schedule_exposure_days} sched days</div>`;
      table(body, ["Decision", "Category", "Alignment", "State", "Cost"], s.rows.map((r: any) => [r.subject ?? "", r.category ?? "", r.alignment ?? "", r.state ?? "", money(r.cost_impact)])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("Σ Estimate continuity (preconstruction)", () => showResult("Estimate continuity", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.estimateContinuity(pid);
      const drift = s.total_drift_pct != null ? ` (${s.total_drift_pct > 0 ? "+" : ""}${s.total_drift_pct}%)` : "";
      const varr = s.variance_to_budget == null ? "" : ` · <b>${s.over_budget ? "OVER" : "under"} budget ${money(Math.abs(s.variance_to_budget))}</b>`;
      body.innerHTML = `<div class="meta">${s.set_count} estimate sets · latest ${money(s.latest_total)} (${s.latest_milestone ?? "—"}${s.latest_psf ? `, ${money(s.latest_psf)}/SF` : ""}) · drift ${money(s.total_drift)}${drift} · budget ${s.budget != null ? money(s.budget) : "—"}${varr}</div>`;
      table(body, ["Milestone", "Total", "$/SF", "Δ vs prev", "Basis"], s.rows.map((r: any) => [r.milestone ?? "", money(r.total), r.psf != null ? money(r.psf) : "—", r.delta_total != null ? money(r.delta_total) : "—", r.basis ?? ""])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("💲 Change-order log", () => showResult("Change-order log", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.coLog(pid); body.innerHTML = `<div class="meta">${s.co_count} COs · total ${money(s.total_value)} · pending ${money(s.pending_value)} · approved ${money(s.approved_value)} · <b>executed ${money(s.executed_value)}</b> · ${s.total_schedule_days} sched days · CE ROM exposure ${money(s.change_event_rom_exposure)}</div>`;
      table(body, ["Ref", "Subject", "State", "Ball in court", "Reason", "Amount"], s.rows.map((r: any) => [r.ref ?? "", r.subject ?? "", r.state ?? "", r.ball_in_court ?? "", r.reason ?? "", money(r.amount)])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("✅ Meeting action-item tracker", () => showResult("Meeting action-item tracker", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.actionTracker(pid); body.innerHTML = `<div class="meta">${s.action_count} action items · ${s.open_count} open · ${s.overdue_count} overdue · <b>${s.completion_pct ?? "—"}% complete</b> · ${s.meeting_count} meetings · last ${s.last_meeting ?? "—"}</div>`;
      table(body, ["Ref", "Subject", "Assignee", "Priority", "Due", "State"], s.rows.map((r: any) => [r.ref ?? "", r.subject ?? "", r.assignee ?? "", r.priority ?? "", (r.overdue ? "OVERDUE " : "") + (r.due_date ?? ""), r.state ?? ""])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("📑 Submittal register", () => showResult("Submittal register", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.submittalRegister(pid); body.innerHTML = `<div class="meta">${s.submittal_count} submittals · ${s.open_count} open · ${s.overdue_count} overdue · avg turnaround ${s.avg_turnaround_days ?? "—"} d</div>`;
      table(body, ["Ref", "Spec", "Title", "Turn (d)", "Status"], s.rows.map((r: any) => [r.ref ?? "", r.spec_section ?? "", r.title ?? "", r.turnaround_days ?? "", (r.overdue ? "OVERDUE " : "") + r.status])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("🏁 Closeout dashboard", () => showResult("Closeout dashboard", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.closeoutSummary(pid); const p = s.punchlist, cx = s.commissioning, w = s.warranties, om = s.om_manuals;
      body.innerHTML = `<div class="meta">Punch <b>${p.complete_pct ?? "—"}% complete</b> (${p.open_count} open, ${p.overdue_count} overdue, ${money(p.open_cost)} open cost) · `
        + `Cx pass ${cx.pass_rate ?? "—"}% (${cx.cx_count} tests) · warranties ${w.active} active / ${w.expiring_soon} expiring / ${w.expired} expired · O&M ${om.accepted_pct ?? "—"}% accepted</div>`;
      table(body, ["Punch item", "Ball in court", "Trade", "Due", "Cost"], p.rows.map((r: any) => [r.description ?? "", r.ball_in_court ?? "", r.trade ?? "", (r.overdue ? "OVERDUE " : "") + (r.due_date ?? ""), money(r.cost)])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("⚑ Safety dashboard (OSHA)", () => showResult("Safety dashboard (OSHA)", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.safetySummary(pid); const i = s.incidents, o = s.observations, t = s.toolbox_talks;
      body.innerHTML = `<div class="meta">${i.incident_count} incidents · ${i.recordable_count} recordable · <b>TRIR ${i.trir ?? "—"}</b> · DART ${i.dart_rate ?? "—"} · LTIFR ${i.ltifr ?? "—"} · ${i.total_lost_days} lost days`
        + ` · ${o.observation_count} observations (safe:at-risk ${o.safe_to_at_risk ?? "—"}) · ${t.talk_count} toolbox talks`
        + `<br><span style="opacity:.7">on ${i.hours_worked.toLocaleString()} worker-hours${s.hours_estimated ? " (estimated from manpower)" : ""}</span></div>`;
      table(body, ["Incident", "Date", "OSHA class", "Recordable", "DART", "Lost d"], i.rows.map((r: any) => [r.subject ?? "", r.date ?? "", r.classification ?? "", r.recordable ? "yes" : "—", r.dart ? "yes" : "—", r.lost_days ?? ""])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("☼ Field-log rollup", () => showResult("Field-log rollup", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.fieldLogSummary(pid); body.innerHTML = `<div class="meta">${s.report_count} daily reports · coverage ${s.coverage_pct ?? "—"}% · total manpower ${s.total_manpower} · avg ${s.avg_manpower ?? "—"}/day · peak ${s.peak_manpower.count} (${s.peak_manpower.date ?? "—"}) · weather lost-days ${s.weather_lost_days} · ${s.delay_days} delay days</div>`;
      table(body, ["Date", "Weather", "Impact", "Manpower", "Delay"], s.rows.map((r: any) => [r.report_date ?? "", r.weather ?? "", r.weather_impact ?? "", r.manpower ?? "", r.has_delay ? "yes" : "—"])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("❓ RFI register", () => showResult("RFI register", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.rfiRegister(pid); body.innerHTML = `<div class="meta">${s.rfi_count} RFIs · ${s.open_count} open · ${s.overdue_count} overdue · avg response ${s.avg_response_days ?? "—"} d · ${s.cost_impacted_count} cost-impacting · ${s.schedule_impacted_count} schedule-impacting</div>`;
      table(body, ["Ref", "Subject", "Discipline", "Ball in court", "Due"], s.rows.map((r: any) => [r.ref ?? "", r.subject ?? "", r.discipline ?? "", r.ball_in_court ?? "", (r.overdue ? "OVERDUE " : "") + (r.due_date ?? "")])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("🔍 Quality dashboard", () => showResult("Quality dashboard", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const q = await api.qualitySummary(pid); const i = q.inspections, n = q.ncrs, d = q.deficiencies;
      body.innerHTML = `<div class="meta">${i.total} inspections · pass rate <b>${i.pass_rate ?? "—"}%</b> · first-pass yield ${i.first_pass_yield ?? "—"}% · `
        + `NCRs ${n.open_count} open / ${n.overdue_count} overdue · deficiencies ${d.open_count} open / ${d.overdue_count} overdue</div>`;
      table(body, ["Deficiency", "Ball in court", "Trade", "Severity", "Due"],
        d.rows.map((r: any) => [r.description ?? "", r.ball_in_court ?? "", r.trade ?? "", r.severity ?? "", (r.overdue ? "OVERDUE " : "") + (r.due_date ?? "")])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("✓ Field-verification coverage", () => showResult("Field-verification coverage", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const c = await api.verificationCoverage(pid); body.innerHTML =
      `<div style="font-size:22px;font-weight:700">${c.verified_pct}% verified · ${c.installed_pct}% installed</div>`
      + `<div class="meta">${c.verified} verified · ${c.installed} installed · ${c.deviations} deviations · of ${c.total_elements} elements</div>`; }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
}
