import type { MaterialEntry } from "../../api/client";
import { noProjectHtml } from "../../ui/empty";
import { toast } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * Material editor (M1) — edit the per-project palette that maps each IFC element class to an
 * IfcMaterial + surface-style colour, then re-colour + republish the model. The default palette is
 * the built-in per-category table; only the classes you change are saved as overrides. "Apply"
 * re-runs the material/surface-style assignment on the source IFC and kicks the convert→fragments
 * reindex so the viewer shows the new colours.
 */

const hex = (c: [number, number, number]) =>
  "#" + c.map((v) => Math.round(Math.max(0, Math.min(1, v)) * 255).toString(16).padStart(2, "0")).join("");
const fromHex = (h: string): [number, number, number] => {
  const n = h.replace("#", "");
  return [parseInt(n.slice(0, 2), 16) / 255, parseInt(n.slice(2, 4), 16) / 255, parseInt(n.slice(4, 6), 16) / 255];
};

export async function renderMaterials(ctx: PanelContext) {
  const root = ctx.root; root.innerHTML = "";
  root.appendChild(ctx.bar("🎨 Materials", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
  const pid = ctx.host.projectId();
  if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Materials")); return; }

  const intro = document.createElement("div"); intro.className = "meta"; intro.style.marginBottom = "8px";
  intro.textContent = "Per-project material palette: each IFC element class gets a material + colour. "
    + "Edit a colour, transparency, or name; only changed classes are saved as overrides. Apply re-colours "
    + "the model (IfcMaterial + IfcSurfaceStyle) and republishes it so the viewer shows the new look.";
  root.appendChild(intro);

  const body = document.createElement("div"); body.innerHTML = `<div class="meta">loading palette…</div>`;
  root.appendChild(body);

  let effective: Record<string, MaterialEntry> = {};
  let base: Record<string, MaterialEntry> = {};
  const overrides: Record<string, MaterialEntry> = {};

  const markOverride = (cls: string, e: MaterialEntry) => { overrides[cls] = e; effective[cls] = e; };

  const paint = () => {
    body.innerHTML = "";
    const table = document.createElement("table"); table.className = "mini-table";
    table.style.cssText = "width:100%;font-size:12px;border-collapse:collapse";
    table.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Element class</th><th scope="col">Material</th>`
      + `<th scope="col">Colour</th><th scope="col">Transp.</th><th scope="col"><span class="sr-only">Edited</span></th></tr></thead>`;
    const tb = document.createElement("tbody");
    for (const cls of Object.keys(effective).sort()) {
      const e = effective[cls]; if (!e) continue;
      const isOv = cls in overrides;
      const tr = document.createElement("tr");
      const nameCell = document.createElement("td");
      const nameInp = document.createElement("input"); nameInp.type = "text"; nameInp.value = e.name;
      nameInp.style.cssText = "width:130px;font-size:11px";
      nameInp.setAttribute("aria-label", `Material name for ${cls}`);
      nameInp.oninput = () => markOverride(cls, { ...e, name: nameInp.value });
      nameCell.appendChild(nameInp);
      const colorCell = document.createElement("td"); colorCell.style.textAlign = "center";
      const color = document.createElement("input"); color.type = "color"; color.value = hex(e.color);
      color.setAttribute("aria-label", `Colour for ${cls}`);
      color.oninput = () => markOverride(cls, { ...effective[cls]!, color: fromHex(color.value) });
      colorCell.appendChild(color);
      const tCell = document.createElement("td"); tCell.style.textAlign = "center";
      const t = document.createElement("input"); t.type = "number"; t.min = "0"; t.max = "1"; t.step = "0.05";
      t.value = String(e.transparency); t.style.width = "56px";
      t.setAttribute("aria-label", `Transparency for ${cls} (0–1)`);
      t.oninput = () => markOverride(cls, { ...effective[cls]!, transparency: Math.max(0, Math.min(1, parseFloat(t.value) || 0)) });
      tCell.appendChild(t);
      const flagCell = document.createElement("td"); flagCell.className = "meta";
      flagCell.textContent = isOv ? "● edited" : "";
      tr.innerHTML = `<td style="font-family:monospace">${cls}</td>`;
      tr.append(nameCell, colorCell, tCell, flagCell);
      tb.appendChild(tr);
    }
    table.appendChild(tb);
    const wrap = document.createElement("div"); wrap.style.overflowX = "auto"; wrap.appendChild(table);
    body.appendChild(wrap);

    const btnRow = document.createElement("div"); btnRow.style.cssText = "display:flex;gap:6px;margin-top:8px;align-items:center";
    const saveBtn = document.createElement("button"); saveBtn.className = "tool-btn"; saveBtn.textContent = "Save overrides";
    saveBtn.onclick = async () => {
      try { await ctx.host.api.saveMaterialPalette(pid, overrides); toast(`Saved ${Object.keys(overrides).length} material override(s)`, "success"); }
      catch (e) { toast(`Save failed: ${(e as Error).message}`, "error"); }
    };
    const applyBtn = document.createElement("button"); applyBtn.className = "file-btn"; applyBtn.textContent = "Apply + republish";
    applyBtn.onclick = async () => {
      applyBtn.disabled = true; applyBtn.textContent = "applying…";
      try {
        await ctx.host.api.saveMaterialPalette(pid, overrides);
        const r = await ctx.host.api.applyMaterialPalette(pid);
        toast(`Re-coloured ${r.applied.styled} surfaces across ${r.applied.classes} classes — republishing`, "success");
      } catch (e) { toast(`Apply failed: ${(e as Error).message}`, "error"); }
      finally { applyBtn.disabled = false; applyBtn.textContent = "Apply + republish"; }
    };
    const resetBtn = document.createElement("button"); resetBtn.className = "tool-btn"; resetBtn.textContent = "Reset to default";
    resetBtn.onclick = () => { for (const k of Object.keys(overrides)) delete overrides[k]; effective = { ...base }; paint(); };
    const count = document.createElement("span"); count.className = "meta";
    count.textContent = `${Object.keys(effective).length} classes · ${Object.keys(overrides).length} edited`;
    btnRow.append(saveBtn, applyBtn, resetBtn, count);
    body.appendChild(btnRow);
  };

  try {
    const p = await ctx.host.api.materialPalette(pid);
    base = p.default; effective = { ...p.effective };
    for (const [k, v] of Object.entries(p.overrides)) overrides[k] = v;
    paint();
  } catch (e) { body.innerHTML = `<div class="meta">Palette unavailable: ${(e as Error).message}</div>`; }
}
