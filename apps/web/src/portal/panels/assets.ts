import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * ASSET-REG panel (R16) — the maintainable-asset register derived from the IFC: counts by discipline /
 * category / class, the asset list, and a one-click "seed the asset_register module" action (idempotent).
 */
export async function renderAssets(ctx: PanelContext) {
  const pid = ctx.host.projectId()!;
  ctx.root.innerHTML = "";
  ctx.root.appendChild(ctx.bar("🔧 Asset register", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));

  const body = document.createElement("div");
  body.innerHTML = `<div class="meta">Deriving maintainable assets from the model…</div>`;
  ctx.root.appendChild(body);

  try {
    const r = await ctx.host.api.modelAssets(pid);
    body.replaceChildren();

    const head = document.createElement("div"); head.className = "dash-card"; head.style.marginBottom = "10px";
    const chips = (arr: { count: number }[], key: string) =>
      arr.slice(0, 8).map((t) => `<span style="white-space:nowrap">${esc(String((t as Record<string, unknown>)[key] ?? "—"))} <b>${t.count}</b></span>`).join(" · ");
    head.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap">`
      + `<div class="section-title" style="margin:0">Maintainable assets</div>`
      + `<div style="font-size:20px;font-weight:800">${r.count}</div></div>`
      + (r.count ? `<div class="meta" style="margin-top:3px">By category: ${chips(r.by_category, "category")}</div>`
        + `<div class="meta" style="margin-top:2px">By discipline: ${chips(r.by_discipline, "discipline")}</div>` : "");
    body.appendChild(head);

    if (!r.count) {
      body.appendChild(Object.assign(document.createElement("div"), { className: "meta",
        textContent: "No maintainable equipment/terminals found in the model yet (needs MEP equipment, terminals, controls or transport)." }));
      return;
    }

    // seed action
    const seedCard = document.createElement("div"); seedCard.className = "dash-card"; seedCard.style.marginBottom = "10px";
    seedCard.innerHTML = `<div class="meta">Populate the <b>Asset Register</b> module from these ${r.count} model assets — then hang preventive maintenance, warranty and serials off each.</div>`;
    const btn = document.createElement("button"); btn.className = "btn"; btn.style.marginTop = "6px";
    btn.textContent = "→ Seed asset register from model";
    btn.title = "Create an asset_register record per maintainable asset (idempotent by tag — re-running only adds what's new).";
    btn.onclick = async () => {
      btn.disabled = true; btn.textContent = "Seeding…";
      try {
        const s = await ctx.host.api.seedModelAssets(pid);
        btn.textContent = `✓ ${s.created} created, ${s.skipped} already registered`;
      } catch (e) {
        btn.disabled = false; btn.textContent = "→ Seed asset register from model";
        seedCard.appendChild(Object.assign(document.createElement("div"), { className: "meta", textContent: `Seed failed: ${(e as Error).message}` }));
      }
    };
    seedCard.appendChild(btn); body.appendChild(seedCard);

    // asset list
    const wrap = document.createElement("div"); wrap.className = "dash-card"; wrap.style.overflowX = "auto";
    const t = document.createElement("table"); t.className = "portal-table"; t.style.cssText = "width:100%;font-size:11px";
    t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Asset</th><th scope="col" style="text-align:left">Class</th>`
      + `<th scope="col" style="text-align:left">Discipline</th><th scope="col" style="text-align:left">Storey</th></tr></thead><tbody>`
      + r.assets.slice(0, 100).map((a) => `<tr><td style="text-align:left">${esc(a.name)}</td>`
        + `<td style="text-align:left">${esc(a.ifc_class.replace("Ifc", ""))}</td>`
        + `<td style="text-align:left">${esc(a.discipline)}</td><td style="text-align:left">${esc(a.storey ?? "—")}</td></tr>`).join("")
      + `</tbody>`;
    wrap.appendChild(t);
    if (r.assets.length > 100) wrap.insertAdjacentHTML("beforeend", `<div class="meta" style="opacity:.7">Showing first 100 of ${r.count}.</div>`);
    body.appendChild(wrap);
  } catch (e) {
    body.innerHTML = `<div class="meta">Asset register unavailable: ${esc((e as Error).message)}</div>`;
  }
}
