import { escapeHtml as esc, toast } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * MEP-EQUIP panel — the procurement equipment schedule derived from the IFC: procurable units grouped by
 * (class, type) into RFQ line-items with a quantity + representative spec, plus by-discipline tallies.
 * (SPEC-CONFLICT cross-check is available on the API; a requirement-set editor is a later slice.)
 */
export async function renderEquipment(ctx: PanelContext) {
  const pid = ctx.host.projectId()!;
  ctx.root.innerHTML = "";
  ctx.root.appendChild(ctx.bar("🔩 Equipment schedule", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));

  const body = document.createElement("div");
  body.innerHTML = `<div class="meta">Deriving the equipment schedule from the model…</div>`;
  ctx.root.appendChild(body);

  const specStr = (spec: Record<string, unknown>) =>
    Object.entries(spec).slice(0, 4).map(([k, v]) => `${esc(k)}: ${esc(String(v))}`).join(" · ");

  try {
    const r = await ctx.host.api.modelEquipment(pid);
    body.replaceChildren();

    const head = document.createElement("div"); head.className = "dash-card"; head.style.marginBottom = "10px";
    const chips = (arr: { count: number }[], key: string) =>
      arr.slice(0, 8).map((t) => `<span style="white-space:nowrap">${esc(String((t as Record<string, unknown>)[key] ?? "—"))} <b>${t.count}</b></span>`).join(" · ");
    head.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap">`
      + `<div class="section-title" style="margin:0">Procurable equipment</div>`
      + `<div style="font-size:20px;font-weight:800">${r.unit_count} <span style="font-size:12px;font-weight:500;opacity:.7">units · ${r.line_count} lines</span></div></div>`
      + (r.line_count ? `<div class="meta" style="margin-top:3px">By discipline: ${chips(r.by_discipline, "discipline")}</div>` : "");
    body.appendChild(head);

    if (!r.line_count) {
      body.appendChild(Object.assign(document.createElement("div"), { className: "meta",
        textContent: "No procurable equipment found in the model yet (needs MEP equipment, terminals or transport — ducts/pipes/fittings are excluded)." }));
      return;
    }

    const note = document.createElement("div"); note.className = "meta"; note.style.margin = "0 0 8px";
    note.textContent = "Grouped by class + type into RFQ line-items — the buyout package derived straight from the model.";
    body.appendChild(note);

    const wrap = document.createElement("div"); wrap.className = "dash-card"; wrap.style.overflowX = "auto";
    const t = document.createElement("table"); t.className = "portal-table"; t.style.cssText = "width:100%;font-size:11px";
    t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Type</th><th scope="col" style="text-align:left">Class</th>`
      + `<th scope="col" style="text-align:right">Qty</th><th scope="col" style="text-align:left">Discipline</th>`
      + `<th scope="col" style="text-align:left">Spec</th></tr></thead><tbody>`
      + r.lines.slice(0, 200).map((l) => `<tr><td style="text-align:left">${esc(l.type)}</td>`
        + `<td style="text-align:left">${esc(l.ifc_class.replace("Ifc", ""))}</td>`
        + `<td style="text-align:right;font-variant-numeric:tabular-nums"><b>${l.count}</b></td>`
        + `<td style="text-align:left">${esc(l.discipline)}</td>`
        + `<td style="text-align:left;opacity:.85">${specStr(l.spec) || "—"}</td></tr>`).join("")
      + `</tbody>`;
    wrap.appendChild(t);
    if (r.lines.length > 200) wrap.insertAdjacentHTML("beforeend", `<div class="meta" style="opacity:.7">Showing first 200 of ${r.line_count} lines.</div>`);
    body.appendChild(wrap);
  } catch (e) {
    body.innerHTML = `<div class="meta">Equipment schedule unavailable: ${esc((e as Error).message)}</div>`;
  }

  const extra = document.createElement("div");
  extra.style.marginTop = "12px";
  ctx.root.appendChild(extra);

  void ctx.host.api.ffeBom(pid).then((bom) => {
    const card = document.createElement("div"); card.className = "dash-card"; card.style.marginBottom = "10px";
    const h = document.createElement("div"); h.className = "section-title";
    h.textContent = "FF&E bill of materials";
    const m = document.createElement("div"); m.className = "meta";
    m.textContent = `${bom.total} placed furnishings · ${bom.line_count} line(s)`;
    card.append(h, m);
    if (bom.items.length) {
      const t = document.createElement("table"); t.className = "portal-table"; t.style.cssText = "width:100%;font-size:11px";
      t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Item</th>`
        + `<th scope="col">Qty</th><th scope="col" style="text-align:left">Levels</th></tr></thead><tbody>`
        + bom.items.slice(0, 80).map((it) => `<tr><td>${esc(it.item)}</td>`
          + `<td style="text-align:center">${it.count}</td>`
          + `<td>${esc(it.storeys.join(", ") || "—")}</td></tr>`).join("")
        + `</tbody>`;
      card.appendChild(t);
    }
    extra.appendChild(card);
  }).catch((e) => {
    const m = document.createElement("div"); m.className = "meta";
    m.textContent = `FF&E BOM unavailable: ${(e as Error).message}`;
    extra.appendChild(m);
  });

  void ctx.host.api.equipmentStarterRequirements(pid).then((st) => {
    const n = Object.keys(st.requirements).length;
    const card = document.createElement("div"); card.className = "dash-card"; card.style.marginBottom = "10px";
    const h = document.createElement("div"); h.className = "section-title";
    h.textContent = "Starter spec-check properties";
    const m = document.createElement("div"); m.className = "meta";
    m.textContent = `${n} equipment class(es) with required properties before buyout (* = presence).`;
    card.append(h, m);
    extra.appendChild(card);
  }).catch(() => { /* no project */ });

  void ctx.host.api.equipmentBudgetLines(pid).then((bl) => {
    const card = document.createElement("div"); card.className = "dash-card"; card.style.marginBottom = "10px";
    const h = document.createElement("div"); h.className = "section-title";
    h.textContent = "Equipment as budget lines";
    const m = document.createElement("div"); m.className = "meta";
    const nPriced = bl.priced_lines;
    const nLines = bl.line_count;
    const amt = bl.priced_total;
    m.textContent = `${nPriced} of ${nLines} priced from the project ledger · ${amt} extended`;
    card.append(h, m);
    extra.appendChild(card);
  }).catch(() => { /* 409 without a source IFC */ });

  const mint = document.createElement("button"); mint.className = "file-btn";
  mint.textContent = "Mint product-data submittals from equipment types";
  mint.onclick = async () => {
    mint.disabled = true;
    try {
      const r = await ctx.host.api.equipmentToSubmittals(pid);
      const n = r.created_count;
      const skip = r.skipped_existing;
      toast(`${n} created · ${skip} already on the log`, n ? "success" : "info");
    } catch (e) { toast((e as Error).message, "error"); }
    finally { mint.disabled = false; }
  };
  extra.appendChild(mint);
}
