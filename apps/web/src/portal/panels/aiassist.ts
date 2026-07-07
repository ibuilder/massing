import type { ApiClient } from "../../api/client";
import { escapeHtml as esc, toast } from "../../ui/feedback";
import { money as cmoney } from "../../ui/charts";
import { noProjectHtml } from "../../ui/empty";
import type { PanelContext } from "../panelContext";

/**
 * AI-assist / risk-review render cluster (contract risk, scope gaps, doc Q&A, draft RFI/scope/
 * submittal, sheet index, bid leveling, code check). Extracted from portal.ts as free
 * render*(ctx) functions (portal.ts decomposition).
 */

// Severity → status colour, shared by the risk-review sub-renderers.
const SEV_TONE: Record<string, string> = {
  high: "var(--status-crit)", medium: "var(--status-warn)", low: "var(--status-good)" };

  // --- Risk Review (preconstruction intelligence) ------------------------------------------------
export function renderRiskReview(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const pid = ctx.host.projectId();
    if (!pid) { root.innerHTML = noProjectHtml("Risk Review"); return; }
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("🛡 Risk Review", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const intro = el("div", "meta");
    intro.textContent = "Review an incoming contract for risky clauses, find scope gaps in specs/notes, "
      + "or ask a document a question with citations. Works offline (built-in clause library); set an "
      + "Anthropic key in Settings for full AI review.";
    intro.style.marginBottom = "8px"; root.appendChild(intro);

    const tabs = el("div"); tabs.style.cssText = "display:flex;gap:6px;margin-bottom:8px";
    const body = el("div"); root.append(tabs, body);
    const TABS: [string, string][] = [["contract", "🛡 Contract risk"], ["scope", "🔍 Scope gaps"], ["ask", "💬 Ask a doc"]];
    let active = "contract";

    const render = () => {
      body.innerHTML = "";
      [...tabs.children].forEach((b, i) => b.classList.toggle("active", TABS[i][0] === active));
      const fileInp = el("input") as HTMLInputElement; fileInp.type = "file"; fileInp.accept = ".pdf,.txt";
      fileInp.style.cssText = "display:block;margin:4px 0";
      const ta = el("textarea", "portal-filter") as HTMLTextAreaElement;
      ta.placeholder = active === "ask" ? "Paste the document text (or choose a PDF above)…"
        : `Paste the ${active === "contract" ? "contract" : "spec / drawing notes"} text (or choose a PDF above)…`;
      ta.style.cssText = "width:100%;min-height:120px;margin:6px 0";
      let qInp: HTMLInputElement | undefined;
      if (active === "ask") {
        qInp = el("input", "portal-filter") as HTMLInputElement;
        qInp.placeholder = "Your question — e.g. what is the retainage %?"; qInp.style.cssText = "width:100%;margin:6px 0";
      }
      const run = el("button", "file-btn") as HTMLButtonElement;
      run.textContent = active === "contract" ? "Review contract" : active === "scope" ? "Find scope gaps" : "Ask";
      const out = el("div"); out.style.marginTop = "8px";
      const doRun = async () => {
        const opts = { file: fileInp.files?.[0], text: ta.value.trim() || undefined };
        if (active === "ask" && !(qInp!.value.trim())) { toast("Enter a question", "error"); return; }
        if (!opts.file && !opts.text) { toast("Choose a PDF or paste text", "error"); return; }
        out.textContent = "analyzing…";
        try {
          if (active === "contract") renderContractFindings(ctx, out, await ctx.host.api.reviewContract(pid, opts), pid);
          else if (active === "scope") renderScopeGaps(out, await ctx.host.api.reviewScope(pid, opts));
          else renderDocAnswer(out, await ctx.host.api.reviewAsk(pid, qInp!.value.trim(), opts));
        } catch (e) { out.textContent = `failed: ${(e as Error).message}`; }
      };
      run.onclick = () => void doRun();
      body.append(fileInp);
      if (qInp) body.append(qInp);
      body.append(ta, run, out);
    };
    for (const [k, label] of TABS) {
      const b = el("button", "tool-btn") as HTMLButtonElement; b.textContent = label;
      b.onclick = () => { active = k; render(); };
      tabs.appendChild(b);
    }
    render();
  }

  // --- AI Assist: draft RFI / scope / submittal summary + bid leveling --------------------------
export async function renderAiAssist(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const pid = ctx.host.projectId();
    if (!pid) { root.innerHTML = noProjectHtml("AI Assist"); return; }
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("✍️ AI Assist", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const intro = el("div", "meta");
    intro.textContent = "Turn a note or a PDF into an editable draft, and level bids apples-to-apples. "
      + "Works offline; set an Anthropic key in Settings for full AI output. Nothing is created until you click Create.";
    intro.style.marginBottom = "8px"; root.appendChild(intro);
    const tabs = el("div"); tabs.style.cssText = "display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap";
    const body = el("div"); root.append(tabs, body);
    const TABS: [string, string][] = [["rfi", "📝 Draft RFI"], ["scope", "📋 Draft scope"],
      ["submittal", "📄 Submittal summary"], ["sheets", "🗂 Sheet index"], ["level", "⚖️ Bid leveling"],
      ["code", "🏛️ Code check"]];
    let active = "rfi";

    const fileRow = (accept: string) => {
      const f = el("input") as HTMLInputElement; f.type = "file"; f.accept = accept;
      f.style.cssText = "display:block;margin:4px 0"; return f;
    };
    const list = (title: string, items: string[]) => {
      const w = el("div"); w.style.marginTop = "6px";
      const h = el("div", "meta"); h.innerHTML = `<b>${title}</b> (${items.length})`; w.appendChild(h);
      const ul = el("ul"); ul.style.cssText = "margin:2px 0 0 16px;font-size:12px";
      items.forEach((s) => { const li = el("li"); li.textContent = s; ul.appendChild(li); });
      if (!items.length) { const li = el("div", "meta"); li.textContent = "—"; li.style.marginLeft = "4px"; w.appendChild(li); }
      else w.appendChild(ul);
      return w;
    };

    const render = async () => {
      body.innerHTML = "";
      [...tabs.children].forEach((b, i) => b.classList.toggle("active", TABS[i][0] === active));

      if (active === "level") {
        const pick = el("select", "portal-filter") as HTMLSelectElement; pick.style.cssText = "margin:4px 0";
        pick.innerHTML = `<option value="">Loading packages…</option>`;
        const out = el("div"); out.style.marginTop = "8px";
        body.append(pick, out);
        try {
          const pkgs = await ctx.host.api.moduleRecords(pid, "bid_package");
          pick.innerHTML = `<option value="">Choose a bid package…</option>`
            + pkgs.map((p) => `<option value="${p.id}">${(p.title || p.ref || p.id) as string}</option>`).join("");
        } catch { pick.innerHTML = `<option value="">No bid packages</option>`; }
        pick.onchange = async () => {
          if (!pick.value) return;
          out.textContent = "leveling…";
          try { renderLeveling(out, await ctx.host.api.bidLevelingDetail(pid, pick.value)); }
          catch (e) { out.textContent = `failed: ${(e as Error).message}`; }
        };
        return;
      }

      if (active === "sheets") {
        const hint = el("div", "meta"); hint.style.marginBottom = "4px";
        hint.textContent = "Upload a drawing set (PDF) or paste a sheet index; the sheet numbers, titles "
          + "and disciplines are extracted from the text — image-only scans need an Anthropic key.";
        const file = fileRow(".pdf,.txt");
        const ta = el("textarea", "portal-filter") as HTMLTextAreaElement;
        ta.placeholder = "Or paste a sheet index — e.g.\nA-101  First Floor Plan\nS-201  Framing Plan";
        ta.style.cssText = "width:100%;min-height:90px;margin:6px 0";
        const mk = el("label", "meta"); mk.style.cssText = "display:block;margin:4px 0";
        const cb = el("input") as HTMLInputElement; cb.type = "checkbox"; cb.style.marginRight = "6px";
        mk.append(cb, document.createTextNode(" Also create Drawing records"));
        const run = el("button", "file-btn") as HTMLButtonElement; run.textContent = "Extract sheets";
        const out = el("div"); out.style.marginTop = "8px";
        run.onclick = async () => {
          out.textContent = "extracting…";
          try {
            const r = await ctx.host.api.extractSheets(pid, { file: file.files?.[0], text: ta.value.trim() || undefined, create: cb.checked });
            out.innerHTML = "";
            const h = el("div", "meta"); h.innerHTML = `<b>${r.sheets.length} sheet(s)</b> · ${esc(r.method)}`
              + (r.created ? ` · created ${r.created.length} drawing record(s)` : "");
            out.append(h);
            if (r.sheets.length) {
              const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px;margin-top:6px";
              t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Sheet</th><th scope="col" style="text-align:left">Title</th>`
                + `<th scope="col" style="text-align:left">Discipline</th></tr></thead><tbody>`
                + r.sheets.map((s) => `<tr><td><b>${esc(s.number)}</b></td><td>${esc(s.title)}</td><td>${esc(s.discipline)}</td></tr>`).join("") + `</tbody>`;
              out.append(t);
            }
            if (r.note) { const m = el("div", "meta"); m.textContent = r.note; m.style.marginTop = "6px"; out.append(m); }
          } catch (e) { out.textContent = `failed: ${(e as Error).message}`; }
        };
        body.append(hint, file, ta, mk, run, out);
        return;
      }

      if (active === "code") {
        const ta = el("textarea", "portal-filter") as HTMLTextAreaElement;
        ta.placeholder = "Describe the project — occupancy/use, area (sf), stories, occupants…";
        ta.style.cssText = "width:100%;min-height:80px;margin:6px 0";
        const run = el("button", "file-btn") as HTMLButtonElement; run.textContent = "Check applicable codes";
        const out = el("div"); out.style.marginTop = "8px";
        run.onclick = async () => {
          if (!ta.value.trim()) { toast("Describe the project", "error"); return; }
          out.textContent = "checking…";
          try {
            const r = await ctx.host.api.codeComplianceCheck(pid, ta.value.trim());
            out.innerHTML = "";
            const d = r.detected;
            const head = el("div", "meta");
            head.textContent = "Detected: " + [d?.occupancy ? `${d.occupancy.label} (${d.occupancy.group})` : null,
              d?.area_sf ? `${d.area_sf.toLocaleString()} sf` : null, d?.stories ? `${d.stories} stories` : null]
              .filter(Boolean).join(" · ") + `  ·  ${r.source}`;
            out.append(head);
            const tbl = el("table", "portal-table") as HTMLTableElement; tbl.style.cssText = "width:100%;font-size:12px;margin-top:6px";
            tbl.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Code</th><th scope="col" style="text-align:left">Section</th>`
              + `<th scope="col" style="text-align:left">Requirement</th></tr></thead><tbody>`
              + r.topics.map((t) => `<tr><td>${t.code}</td><td><b>${t.section}</b> — ${t.title}</td>`
                + `<td>${t.requirement}</td></tr>`).join("") + `</tbody>`;
            out.append(tbl);
            const note = el("div", "meta"); note.style.marginTop = "6px";
            note.textContent = r.message || "Confirm all provisions with the Authority Having Jurisdiction (AHJ).";
            out.append(note);
          } catch (e) { out.textContent = `failed: ${(e as Error).message}`; }
        };
        body.append(ta, run, out);
        return;
      }

      const wantsTrade = active === "scope";
      let tradeInp: HTMLInputElement | undefined;
      if (wantsTrade) {
        tradeInp = el("input", "portal-filter") as HTMLInputElement;
        tradeInp.placeholder = "Trade — e.g. Concrete, Electrical, HVAC"; tradeInp.style.cssText = "width:100%;margin:4px 0";
      }
      const noteInp = active === "rfi" ? el("input", "portal-filter") as HTMLInputElement : undefined;
      if (noteInp) { noteInp.placeholder = "Describe the question — e.g. beam at B4 clashes with duct per 5/S-201";
        noteInp.style.cssText = "width:100%;margin:4px 0"; }
      const file = fileRow(".pdf,.txt");
      const ta = el("textarea", "portal-filter") as HTMLTextAreaElement;
      ta.placeholder = "Or paste the spec/plan/submittal text…"; ta.style.cssText = "width:100%;min-height:100px;margin:6px 0";
      const run = el("button", "file-btn") as HTMLButtonElement;
      run.textContent = active === "rfi" ? "Draft RFI" : active === "scope" ? "Draft scope" : "Summarize submittal";
      const out = el("div"); out.style.marginTop = "8px";

      const doRun = async () => {
        const opts = { file: file.files?.[0], text: ta.value.trim() || undefined };
        out.textContent = "drafting…";
        try {
          if (active === "rfi") {
            const d = await ctx.host.api.aiDraftRfi(pid, { note: noteInp!.value.trim(), ...opts });
            renderRfiDraft(ctx, out, pid, d);
          } else if (active === "scope") {
            const d = await ctx.host.api.draftScope(pid, tradeInp!.value.trim() || "General", opts);
            out.innerHTML = "";
            const h = el("div", "meta"); h.innerHTML = `<b>Scope — ${d.trade}</b> · <span class="meta">${d.source}</span>`;
            out.append(h, list("Inclusions", d.inclusions || []), list("Exclusions", d.exclusions || []),
              list("Clarifications", d.clarifications || []), list("Spec sections", d.spec_sections || []));
            if (d.message) { const m = el("div", "meta"); m.textContent = d.message; m.style.marginTop = "6px"; out.append(m); }
          } else {
            const d = await ctx.host.api.draftSubmittalSummary(pid, opts);
            out.innerHTML = "";
            const h = el("div"); h.innerHTML = `<b>${d.title || "Submittal"}</b> — ${d.spec_section || ""} ${d.type || ""}`;
            const s = el("div"); s.style.cssText = "font-size:12px;margin:4px 0"; s.textContent = d.summary || "";
            out.append(h, s, list("Key items", d.key_items || []), list("Missing / review", d.missing_or_review || []));
            if (d.message) { const m = el("div", "meta"); m.textContent = d.message; m.style.marginTop = "6px"; out.append(m); }
          }
        } catch (e) { out.textContent = `failed: ${(e as Error).message}`; }
      };
      run.onclick = () => void doRun();
      if (tradeInp) body.append(tradeInp);
      if (noteInp) body.append(noteInp);
      body.append(file, ta, run, out);
    };
    for (const [k, label] of TABS) {
      const b = el("button", "tool-btn") as HTMLButtonElement; b.textContent = label;
      b.onclick = () => { active = k; void render(); };
      tabs.appendChild(b);
    }
    await render();
  }

  function renderRfiDraft(ctx: PanelContext, out: HTMLElement, pid: string,
      d: { subject: string; question: string; discipline: string; spec_section?: string; priority: string;
           citations?: { page: number; snippet?: string }[]; source: string; message?: string }) {
    out.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    const subj = el("input", "portal-filter") as HTMLInputElement; subj.value = d.subject; subj.style.cssText = "width:100%;margin:2px 0";
    const q = el("textarea", "portal-filter") as HTMLTextAreaElement; q.value = d.question; q.style.cssText = "width:100%;min-height:80px;margin:2px 0";
    const meta = el("div", "meta"); meta.style.margin = "4px 0";
    meta.textContent = `Discipline: ${d.discipline}${d.spec_section ? " · Spec " + d.spec_section : ""} · Priority ${d.priority} · ${d.source}`;
    const cite = el("div", "meta");
    if (d.citations?.length) cite.textContent = "Source: " + d.citations.map((c) => `p.${c.page}`).join(", ");
    const create = el("button", "file-btn") as HTMLButtonElement; create.textContent = "Create RFI";
    create.onclick = async () => {
      create.disabled = true; create.textContent = "creating…";
      try {
        await ctx.host.api.createModuleRecord(pid, "rfi", { data: {
          subject: subj.value, question: q.value, discipline: d.discipline,
          spec_section: d.spec_section || "", priority: d.priority } });
        toast("RFI created", "success"); create.textContent = "✓ Created";
      } catch (e) { toast(`Create failed: ${(e as Error).message}`, "error"); create.disabled = false; create.textContent = "Create RFI"; }
    };
    out.append(el("div", "meta").appendChild(document.createTextNode("Subject")).parentElement!, subj, q, meta, cite, create);
    if (d.message) { const m = el("div", "meta"); m.textContent = d.message; m.style.marginTop = "6px"; out.append(m); }
  }

  function renderLeveling(out: HTMLElement, r: Awaited<ReturnType<ApiClient["bidLevelingDetail"]>>) {
    out.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    if (!r.vendors.length) { out.innerHTML = `<div class="meta">${r.message || "No bids to level."}</div>`; return; }
    const bs = r.base_stats;
    const head = el("div", "meta"); head.style.marginBottom = "6px";
    head.innerHTML = `<b>${r.package}</b> · ${r.vendors.length} bidders · low ${cmoney(bs.low ?? 0)} · median ${cmoney(bs.median ?? 0)}`
      + ` · high ${cmoney(bs.high ?? 0)} · spread ${bs.spread_pct ?? 0}%`
      + (r.outliers.length ? ` · <span style="color:var(--status-warn)">outliers: ${r.outliers.join(", ")}</span>` : "");
    out.append(head);
    if (r.recommendation) {
      const rec = el("div"); rec.style.cssText = "margin:4px 0;font-size:12px";
      rec.innerHTML = `<b>Recommend:</b> ${r.recommendation.apparent_low} @ ${cmoney(r.recommendation.base)} — `
        + `<span style="color:${r.recommendation.missing_scope.length ? "var(--status-warn)" : "var(--status-good)"}">${r.recommendation.note}</span>`;
      out.append(rec);
    }
    // scope matrix
    const tbl = el("table", "portal-table") as HTMLTableElement; tbl.style.cssText = "width:100%;font-size:11px;margin-top:6px";
    const thead = `<tr><th scope="col" style="text-align:left">Scope item</th>${r.vendors.map((v) => `<th scope="col">${v}</th>`).join("")}</tr>`;
    const rows = r.scope_rows.map((row) => {
      const cells = r.vendors.map((v) => {
        const inc = row.included_by.includes(v); const exc = row.excluded_by.includes(v);
        const mark = inc ? "✓" : exc ? "✗" : "–";
        const col = inc ? "var(--status-good)" : exc ? "var(--status-crit)" : "var(--muted)";
        return `<td style="text-align:center;color:${col}">${mark}</td>`;
      }).join("");
      const bg = row.gap ? ' style="background:var(--status-warn-bg,#3a2a0022)"' : "";
      return `<tr${bg}><td>${row.item}${row.gap ? ' <span title="scope gap">⚠️</span>' : ""}</td>${cells}</tr>`;
    }).join("");
    tbl.innerHTML = `<thead>${thead}</thead><tbody>${rows}</tbody>`;
    out.append(tbl);
    if (r.gaps.length) { const g = el("div", "meta"); g.style.marginTop = "6px";
      g.textContent = `⚠️ ${r.gaps.length} scope gap(s) — items some bidders carry that others don't. Level these before award.`;
      out.append(g); }
  }

  function renderContractFindings(ctx: PanelContext, out: HTMLElement, r: { findings: { clause: string; severity: string; category: string;
      rationale: string; suggested_action: string; snippet: string }[]; counts: Record<string, number>; source: string; message?: string }, pid: string) {
    out.innerHTML = "";
    const head = document.createElement("div"); head.className = "meta"; head.style.marginBottom = "6px";
    head.innerHTML = `<b>${r.findings.length}</b> flagged`
      + ` · <span style="color:${SEV_TONE.high}">${r.counts.high || 0} high</span>`
      + ` · <span style="color:${SEV_TONE.medium}">${r.counts.medium || 0} med</span>`
      + ` · <span style="color:${SEV_TONE.low}">${r.counts.low || 0} low</span>`
      + `  <span class="badge">${r.source === "claude" ? "AI" : "rules"}</span>`;
    out.appendChild(head);
    if (r.message) { const m = document.createElement("div"); m.className = "meta"; m.textContent = r.message; out.appendChild(m); }
    for (const f of r.findings) {
      const tone = SEV_TONE[f.severity] || "var(--muted)";
      const card = document.createElement("div"); card.className = "dash-card"; card.style.cssText = `border-left:3px solid ${tone};margin:6px 0`;
      card.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center">`
        + `<b>${esc(f.clause)}</b><span class="ball-badge" style="background:${tone}22;color:${tone};border-color:${tone}">${esc(f.severity)}</span></div>`
        + `<div class="meta" style="margin:3px 0">${esc(f.rationale)}</div>`
        + `<div style="font-size:12px"><b>Suggested:</b> ${esc(f.suggested_action)}</div>`
        + (f.snippet ? `<div class="meta" style="font-style:italic;margin-top:3px">“${esc(f.snippet)}”</div>` : "");
      const actions = document.createElement("div"); actions.style.cssText = "display:flex;gap:6px;margin-top:6px";
      const add = document.createElement("button"); add.className = "tool-btn"; add.textContent = "＋ Add to Risk Register";
      add.onclick = async () => {
        const sev = f.severity === "high" ? "High" : f.severity === "medium" ? "Medium" : "Low";
        try {
          await ctx.host.api.createModuleRecord(pid, "risk", { data: {
            title: `${f.category}: ${f.clause}`, category: "Other", probability: sev, impact: sev,
            response_strategy: "Mitigate", mitigation: f.suggested_action, trigger: f.snippet } });
          add.textContent = "✓ Added"; add.disabled = true; toast("Added to Risk Register", "success");
        } catch (e) { toast(`Add failed: ${(e as Error).message}`, "error"); }
      };
      actions.appendChild(add); card.appendChild(actions); out.appendChild(card);
    }
  }

  function renderScopeGaps(out: HTMLElement, r: { gaps: { marker: string; note: string; snippet: string }[]; source: string; message?: string }) {
    out.innerHTML = "";
    const head = document.createElement("div"); head.className = "meta"; head.style.marginBottom = "6px";
    head.innerHTML = `<b>${r.gaps.length}</b> scope-gap marker${r.gaps.length === 1 ? "" : "s"} <span class="badge">${r.source === "claude" ? "AI" : "rules"}</span>`;
    out.appendChild(head);
    if (r.message) { const m = document.createElement("div"); m.className = "meta"; m.textContent = r.message; out.appendChild(m); }
    for (const g of r.gaps) {
      const card = document.createElement("div"); card.className = "dash-card"; card.style.margin = "6px 0";
      card.innerHTML = `<b>${esc(g.marker)}</b><div class="meta" style="margin:2px 0">${esc(g.note)}</div>`
        + (g.snippet ? `<div class="meta" style="font-style:italic">“${esc(g.snippet)}”</div>` : "");
      out.appendChild(card);
    }
  }

  function renderDocAnswer(out: HTMLElement, r: { answer: string; citations: { page: number; snippet: string }[]; source: string; message?: string }) {
    out.innerHTML = "";
    const ans = document.createElement("div"); ans.className = "dash-card"; ans.style.margin = "6px 0";
    ans.innerHTML = `<div>${esc(r.answer || r.message || "No answer.")}</div>`
      + `<div class="meta" style="margin-top:4px"><span class="badge">${r.source === "claude" ? "AI" : "extract"}</span></div>`;
    out.appendChild(ans);
    for (const c of r.citations) {
      const cite = document.createElement("div"); cite.className = "meta"; cite.style.margin = "3px 0";
      cite.innerHTML = `<b>p.${c.page}</b> — ${esc(c.snippet)}`;
      out.appendChild(cite);
    }
  }
