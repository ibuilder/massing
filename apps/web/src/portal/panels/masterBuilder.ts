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
      + `<div style="font-size:22px;font-weight:800;color:${scoreCol}">${b.readiness_pct}%</div></div>`
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
      body.appendChild(card);
    }

    const disc = document.createElement("div"); disc.className = "meta";
    disc.style.cssText = "margin-top:8px;opacity:.7;font-size:11px;line-height:1.4";
    disc.textContent = b.disclaimer;
    body.appendChild(disc);
  } catch (e) {
    body.innerHTML = `<div class="meta">Master Builder brief unavailable: ${esc((e as Error).message)}</div>`;
  }
}
