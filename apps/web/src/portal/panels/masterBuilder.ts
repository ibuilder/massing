import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * MASTER-BUILDER brief — the 8-step Master Builder Protocol run over the whole project, grounded in its
 * jurisdiction. One synthesis card per step (place → program/HBU → feasibility → regulatory → design →
 * delivery → risk → handover) with a readiness pill, the "why", what's present, and the concrete gap.
 * A readiness synthesis over the data on hand — not a substitute for licensed judgment / a plan check.
 */
export async function renderMasterBuilder(ctx: PanelContext) {
  const pid = ctx.host.projectId()!;
  ctx.root.innerHTML = "";
  ctx.root.appendChild(ctx.bar("🏛 Master Builder", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));

  const body = document.createElement("div");
  body.innerHTML = `<div class="meta">Holding the whole project in one view…</div>`;
  ctx.root.appendChild(body);

  const pill = (status: string) => {
    const col = status === "ready" ? "var(--status-good)" : status === "partial" ? "var(--status-warn)" : "var(--status-crit)";
    return `<span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:${col};border:1px solid ${col};border-radius:10px;padding:1px 7px">${status}</span>`;
  };

  try {
    const b = await ctx.host.api.masterBuilderBrief(pid);

    // --- grounding + readiness header --------------------------------------------------------------
    const head = document.createElement("div"); head.className = "dash-card"; head.style.marginBottom = "10px";
    const scoreCol = b.readiness_pct >= 66 ? "var(--status-good)" : b.readiness_pct >= 33 ? "var(--status-warn)" : "var(--status-crit)";
    const place = b.grounded_in_place
      ? `Grounded in place — jurisdiction <b>${esc(b.jurisdiction ?? "")}</b>`
      : `<b style="color:var(--status-crit)">Not grounded in place</b> — set a jurisdiction so code editions + loads resolve`;
    const pgr = b.place_grounding;
    const coordStr = pgr.coordinates ? `${pgr.coordinates.latitude}°, ${pgr.coordinates.longitude}° (${esc(pgr.hemisphere ?? "")})` : null;
    const groundLine = [
      pgr.code_family ? `Code family <b>${esc(pgr.code_family)}</b>` : null,
      coordStr ? `📍 ${coordStr}` : null,
      pgr.climate_band ? `${esc(pgr.climate_band)} climate` : null,
    ].filter(Boolean).join(" · ");
    head.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap">`
      + `<div class="section-title" style="margin:0">${esc(b.project ?? "Project")} — project readiness</div>`
      + `<div style="display:flex;gap:10px;align-items:baseline">`
      + `<a class="tool-btn" href="${ctx.host.api.masterBuilderBriefMdUrl(pid)}" target="_blank" rel="noopener" title="Download the brief as a shareable Markdown one-pager">⬇ Markdown</a>`
      + `<div style="font-size:22px;font-weight:800;color:${scoreCol}">${b.readiness_pct}%</div></div></div>`
      + `<div class="meta" style="margin-top:2px">${place} · <b>${b.ready_steps}</b>/${b.step_count} steps ready · <b>${b.gap_steps}</b> gap(s)</div>`
      + (groundLine ? `<div class="meta" style="margin-top:3px">${groundLine}</div>` : "")
      + `<div class="meta" style="margin-top:4px;opacity:.85">🔎 ${esc(b.reframe_prompt)}</div>`;
    body.replaceChildren(head);

    // hazards to verify locally — the parameters a builder reads from the site's hazard basis
    if (pgr.hazards_to_verify.length) {
      const hz = document.createElement("details"); hz.className = "dash-card"; hz.style.marginBottom = "10px";
      hz.innerHTML = `<summary style="cursor:pointer;font-weight:600;font-size:12px">⚠ Verify locally — site hazard basis (${pgr.hazards_to_verify.length})</summary>`
        + `<div class="meta" style="margin-top:4px">` + pgr.hazards_to_verify.map((h) => `<div style="margin:1px 0">◦ ${esc(h)}</div>`).join("") + `</div>`;
      body.appendChild(hz);
    }

    // --- one card per protocol step ----------------------------------------------------------------
    for (const s of b.steps) {
      const card = document.createElement("div"); card.className = "dash-card"; card.style.marginBottom = "8px";
      const findings = s.findings.length
        ? s.findings.map((f) => `<div class="meta" style="margin:1px 0">✓ ${esc(f.label)}${f.detail ? ` <span style="opacity:.6">— ${esc(f.detail)}</span>` : ""}</div>`).join("")
        : "";
      const gaps = s.gaps.length
        ? `<div class="meta" style="margin-top:3px">` + s.gaps.map((g) => `<div style="margin:1px 0;color:var(--status-crit)">◦ needs: ${esc(g)}</div>`).join("") + `</div>`
        : "";
      card.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;gap:8px">`
        + `<div class="section-title" style="margin:0">${s.n}. ${esc(s.title)}</div>${pill(s.status)}</div>`
        + `<div class="meta" style="margin:2px 0 4px;opacity:.8">${esc(s.why)}</div>`
        + findings + gaps;
      // SPRINT MB: a deep-link to the portal destination that closes this step — emphasized when there's
      // a gap/partial, quiet when the step is already ready.
      if (s.dest) {
        const go = document.createElement("button");
        const open = s.status !== "ready";
        go.className = open ? "btn" : "tool-btn";
        go.style.cssText = "margin-top:6px;font-size:11px;padding:2px 8px";
        go.textContent = open ? "→ Close this gap" : "→ Open tool";
        go.title = `Jump to the tool that closes step ${s.n}`;
        go.onclick = () => ctx.navigate(s.dest);
        card.appendChild(go);
      }
      body.appendChild(card);
    }

    // --- share read-only: mint / list / revoke tokens for the public readiness digest --------------
    const share = document.createElement("div"); share.className = "dash-card"; share.style.marginTop = "10px";
    share.innerHTML = `<div class="section-title">🔗 Share read-only</div>`
      + `<div class="meta" style="margin:2px 0 6px">Give an owner or stakeholder a link to a <b>read-only readiness digest</b> — high-level only, no record-level data. Revoke anytime.</div>`;
    const shareBody = document.createElement("div"); shareBody.innerHTML = `<div class="meta">loading…</div>`;
    const mkRow = document.createElement("div"); mkRow.style.cssText = "display:flex;gap:6px;margin-bottom:6px;flex-wrap:wrap";
    const labelI = document.createElement("input"); labelI.className = "portal-filter"; labelI.placeholder = "label (e.g. Owner review)"; labelI.style.cssText = "flex:1 1 160px;font-size:12px";
    const mkBtn = document.createElement("button"); mkBtn.className = "tool-btn on"; mkBtn.textContent = "＋ Create link";
    mkRow.append(labelI, mkBtn); share.append(mkRow, shareBody); body.appendChild(share);
    const loadTokens = async () => {
      shareBody.innerHTML = `<div class="meta">loading…</div>`;
      try {
        const { tokens } = await ctx.host.api.shareTokens(pid);
        const live = tokens.filter((t) => !t.revoked);
        if (!live.length) { shareBody.innerHTML = `<div class="meta">No active share links.</div>`; return; }
        shareBody.innerHTML = "";
        for (const t of live) {
          const row = document.createElement("div"); row.style.cssText = "display:flex;gap:6px;align-items:center;margin:2px 0;flex-wrap:wrap";
          const link = document.createElement("a"); link.href = ctx.host.api.sharedPageUrl(t.token); link.target = "_blank"; link.rel = "noopener";
          link.className = "meta"; link.style.cssText = "flex:1 1 200px;word-break:break-all";
          link.textContent = `🔗 ${t.label ? t.label + " · " : ""}…${t.token.slice(-8)} (${t.view_count} view${t.view_count === 1 ? "" : "s"})`;
          const del = document.createElement("button"); del.className = "selset-del"; del.textContent = "✕ revoke"; del.title = "Revoke this link immediately";
          del.onclick = async () => { try { await ctx.host.api.revokeShareToken(pid, t.token); void loadTokens(); } catch (e) { alert((e as Error).message); } };
          row.append(link, del); shareBody.appendChild(row);
        }
      } catch (e) { shareBody.innerHTML = `<div class="meta">Share links unavailable: ${esc((e as Error).message)}</div>`; }
    };
    mkBtn.onclick = async () => {
      mkBtn.disabled = true;
      try { await ctx.host.api.createShareToken(pid, labelI.value.trim() || undefined); labelI.value = ""; await loadTokens(); }
      catch (e) { alert((e as Error).message); }
      finally { mkBtn.disabled = false; }
    };
    void loadTokens();

    const disc = document.createElement("div"); disc.className = "meta";
    disc.style.cssText = "margin-top:8px;opacity:.7;font-size:11px;line-height:1.4";
    disc.textContent = b.disclaimer;
    body.appendChild(disc);
  } catch (e) {
    body.innerHTML = `<div class="meta">Master Builder brief unavailable: ${esc((e as Error).message)}</div>`;
  }
}
