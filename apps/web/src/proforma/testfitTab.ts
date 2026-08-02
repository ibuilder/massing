/** Test Fit: compare unit-mix schemes on a floor plate — yield (units, efficiency, NSF) + parking,
 *  ranked. The TestFit-style "explore scenarios, find the deal that pencils" surface. Extracted from
 *  the ProformaUI god class along its LCOM4 seam; behavior pinned by proforma.render.test.ts. */
import type { ApiClient } from "../api/client";

export interface TestFitTabCtx {
  api: ApiClient;
  setStatus: (m: string) => void;
}

export function renderTestFitTab(root: HTMLElement, ctx: TestFitTabCtx): void {
  const host = document.createElement("div"); host.id = "pf-testfit";
  host.style.cssText = "margin:8px 0;padding:8px 10px;border:1px dashed var(--line);border-radius:8px";
  host.innerHTML = `<div class="section-title" style="margin:0 0 6px">📐 Test Fit — compare unit-mix schemes</div>`
    + `<div class="meta" style="margin-bottom:6px">Fit a unit mix to a floor plate; compare yield + parking across schemes.</div>`;
  const grid = document.createElement("div"); grid.className = "pf-form";
  const inp = (label: string, val: number) => {
    const w = document.createElement("label"); w.className = "pf-field"; w.innerHTML = `<span>${label}</span>`;
    const i = document.createElement("input"); i.type = "number"; i.step = "any"; i.value = String(val); w.appendChild(i); grid.appendChild(w); return i;
  };
  const wi = inp("Plate width (m)", 40), di = inp("Plate depth (m)", 18), fi = inp("Floors", 6);
  host.appendChild(grid);

  // --- A1b: custom unit-type mix editor (define + save your own studio/1BR/2BR… mix) ----------
  const MIX_KEY = "testfit-mix";
  type UType = { name: string; target_sf: number; mix_pct: number };
  const loadMix = (): UType[] => {
    try { const m = JSON.parse(localStorage.getItem(MIX_KEY) || ""); if (Array.isArray(m) && m.length) return m; } catch { /* default */ }
    return [{ name: "Studio", target_sf: 500, mix_pct: 0.2 }, { name: "1BR", target_sf: 750, mix_pct: 0.5 }, { name: "2BR", target_sf: 1050, mix_pct: 0.3 }];
  };
  const mix: UType[] = loadMix();
  const mixBox = document.createElement("div");
  mixBox.style.cssText = "margin:6px 0;padding:6px 8px;border:1px solid var(--line);border-radius:6px";
  const renderMix = () => {
    const total = mix.reduce((s, u) => s + (+u.mix_pct || 0), 0);
    mixBox.innerHTML = `<div class="meta" style="display:flex;justify-content:space-between"><span>Your unit mix</span>`
      + `<span${Math.abs(total - 1) > 0.011 ? ' style="color:var(--status-crit)"' : ""}>mix Σ ${(total * 100).toFixed(0)}%</span></div>`;
    mix.forEach((u, idx) => {
      const row = document.createElement("div"); row.style.cssText = "display:flex;gap:4px;align-items:center;margin-top:4px";
      const nm = document.createElement("input"); nm.value = u.name; nm.className = "portal-filter"; nm.style.flex = "1"; nm.placeholder = "type";
      const sf = document.createElement("input"); sf.type = "number"; sf.value = String(u.target_sf); sf.className = "portal-filter"; sf.style.width = "72px"; sf.title = "target SF";
      const pc = document.createElement("input"); pc.type = "number"; pc.value = String(Math.round(u.mix_pct * 100)); pc.className = "portal-filter"; pc.style.width = "56px"; pc.title = "mix %";
      nm.onchange = () => { u.name = nm.value; }; sf.onchange = () => { u.target_sf = +sf.value; };
      pc.onchange = () => { u.mix_pct = (+pc.value || 0) / 100; renderMix(); };
      const rm = document.createElement("button"); rm.className = "tool-btn"; rm.textContent = "✕"; rm.title = "remove";
      rm.onclick = () => { mix.splice(idx, 1); renderMix(); };
      const pct = document.createElement("span"); pct.className = "meta"; pct.textContent = "%";
      row.append(nm, sf, pc, pct, rm); mixBox.appendChild(row);
    });
    const bar = document.createElement("div"); bar.style.cssText = "display:flex;gap:6px;margin-top:6px";
    const add = document.createElement("button"); add.className = "tool-btn"; add.textContent = "+ unit type";
    add.onclick = () => { mix.push({ name: "Unit", target_sf: 800, mix_pct: 0.1 }); renderMix(); };
    const save = document.createElement("button"); save.className = "tool-btn"; save.textContent = "Save mix";
    save.onclick = () => { localStorage.setItem(MIX_KEY, JSON.stringify(mix)); ctx.setStatus("unit mix saved"); };
    bar.append(add, save); mixBox.appendChild(bar);
  };
  renderMix(); host.appendChild(mixBox);

  const out = document.createElement("div"); out.style.marginTop = "6px";
  // Sweep plate depth: makes daylight-limited leasable depth an optimize dimension (form follows finance)
  const sweepLbl = document.createElement("label"); sweepLbl.className = "meta";
  sweepLbl.style.cssText = "margin-left:8px;cursor:pointer;user-select:none";
  const sweepCb = document.createElement("input"); sweepCb.type = "checkbox"; sweepCb.style.verticalAlign = "middle";
  sweepLbl.append(sweepCb, document.createTextNode(" sweep plate depth"));
  sweepLbl.title = "Also sweep plate depth (×0.6–1.4) — find the depth where daylight-limited yield peaks before a dark core eats rentable area";
  const opt = document.createElement("button"); opt.className = "tool-btn"; opt.style.marginLeft = "6px";
  opt.textContent = "⚡ Optimize (find the deal that pencils)";
  opt.onclick = async () => {
    out.innerHTML = `<span class="meta">sweeping schemes…</span>`;
    try {
      const targets: Record<string, number | string | boolean> = { min_units: 1 };
      if (sweepCb.checked) targets.sweep_depth = true;
      const r = await ctx.api.testFitOptimize({ plate_w: +wi.value, plate_d: +di.value, floors: +fi.value, targets });
      if (!r.best) { out.innerHTML = `<div class="meta">no feasible scheme for these targets</div>`; return; }
      const dcol = r.swept_depths.length > 1 ? `<th>Depth</th>` : "";
      const rows = r.ranked.map((s, n) => `<tr${n === 0 ? ' style="font-weight:700"' : ""}>`
        + `<th style="text-align:left">${s.name}${n === 0 ? " ★" : ""}</th>`
        + (r.swept_depths.length > 1 ? `<td style="text-align:right">${s.plate_d ?? ""}m</td>` : "")
        + `<td style="text-align:right">${s.total_units}</td><td style="text-align:right">${(s.efficiency * 100).toFixed(0)}%</td>`
        + `<td style="text-align:right">${s.parking_stalls}</td><td style="text-align:right">${(s.yield_on_cost * 100).toFixed(1)}%</td></tr>`).join("");
      // form-follows-finance curve: best yield + daylight/core efficiency per swept depth
      let curveHtml = "";
      if (r.depth_curve.length > 1 && r.best_depth_m != null) {
        const crows = r.depth_curve.map((p) => `<tr${p.plate_d === r.best_depth_m ? ' style="font-weight:700"' : ""}>`
          + `<th style="text-align:left">${p.plate_d}m${p.plate_d === r.best_depth_m ? " ★" : ""}</th>`
          + `<td style="text-align:right">${(p.yield_on_cost * 100).toFixed(1)}%</td>`
          + `<td style="text-align:right">${(p.daylight_efficiency * 100).toFixed(0)}%</td>`
          + `<td style="text-align:right">${(p.core_efficiency * 100).toFixed(0)}%</td>`
          + `<td style="text-align:right">${p.total_units}</td></tr>`).join("");
        curveHtml = `<div class="meta" style="margin:6px 0 2px">Plate-depth sweep — best at <b>${r.best_depth_m}m</b> `
          + `(daylight-limited yield peaks before the dark core eats rentable area):</div>`
          + `<table class="sens-table" style="font-size:12px"><tr><th style="text-align:left">Depth</th><th>YoC</th>`
          + `<th>Daylight</th><th>Core</th><th>Units</th></tr>${crows}</table>`;
      }
      out.innerHTML = `<div class="meta" style="margin-bottom:2px">Swept ${r.considered} schemes · ${r.feasible} feasible · ranked by ${r.objective.replace(/_/g, " ")}</div>`
        + `<table class="sens-table" style="font-size:12px"><tr><th style="text-align:left">Scheme</th>${dcol}<th>Units</th><th>Eff.</th><th>Stalls</th><th>YoC</th></tr>${rows}</table>`
        + curveHtml;
    } catch { out.innerHTML = `<div class="meta">optimize unavailable (API offline)</div>`; }
  };
  const run = document.createElement("button"); run.className = "file-btn"; run.textContent = "Compare schemes";
  run.onclick = async () => {
    out.innerHTML = `<span class="meta">fitting…</span>`;
    try {
      const schemes = mix.length ? [{ name: "My mix", unit_types: mix }] : undefined;
      const r = await ctx.api.testFitCompare({ plate_w: +wi.value, plate_d: +di.value, floors: +fi.value, schemes, with_defaults: !!schemes });
      const rows = r.schemes.map((s) => `<tr${s.name === r.best ? ' style="font-weight:700"' : ""}>`
        + `<th style="text-align:left">${s.name}${s.name === r.best ? " ★" : ""}</th>`
        + `<td style="text-align:right">${s.total_units}</td>`
        + `<td style="text-align:right"${s.daylight_limited ? ' title="deep plate — dark interior earns no rent"' : ""}>${(s.daylight_efficiency * 100).toFixed(0)}%${s.daylight_limited ? " ⚠" : ""}</td>`
        + `<td style="text-align:right">${s.avg_unit_sf.toLocaleString()}</td><td style="text-align:right">${s.total_nsf.toLocaleString()}</td>`
        + `<td style="text-align:right">${s.parking_stalls}</td></tr>`).join("");
      const eg = r.egress;
      const egLine = eg
        ? `<div class="meta" style="margin-top:6px;padding:6px 8px;border-radius:6px;background:var(--panel2);border:1px solid var(--line)">`
          + `<b>${eg.compliant ? "✅" : "⚠️"} Egress / life-safety (A2)</b> — `
          + `${eg.occupant_load_per_floor} occ/floor · max travel ${eg.max_travel_m} m (limit ${eg.limit_m}) · `
          + `${eg.min_exits_required} exits req'd · separation ${eg.exit_separation_m}/${eg.required_separation_m} m`
          + (eg.flags.length ? `<br><span style="color:var(--status-crit)">${eg.flags.map((f) => "• " + f).join("<br>")}</span>` : "")
          + `</div>`
        : "";
      out.innerHTML = `<table class="sens-table" style="font-size:12px"><tr><th style="text-align:left">Scheme</th>`
        + `<th>Units</th><th title="rentable ÷ gross, daylight-limited">Daylight</th><th>Avg SF</th><th>Rent. SF</th><th>Stalls</th></tr>${rows}</table>`
        + `<div class="meta" style="margin-top:4px">Best by units: <b>${r.best}</b> · daylight efficiency = rentable area within ~9 m of a window ÷ gross</div>`
        + egLine;
    } catch { out.innerHTML = `<div class="meta">test-fit unavailable (API offline)</div>`; }
  };
  host.append(run, opt, sweepLbl, out); root.appendChild(host);
}
