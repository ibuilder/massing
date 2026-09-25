/** Competitive supply — who else is delivering into this project's lease-up window, weighted by
 *  what is actually *recorded* about them.
 *
 *  `services/api/src/aec_api/supply_pipeline.py` states the distinction it exists for:
 *
 *  > "Under construction" on a broker deck and "under construction" with a recorded construction
 *  > deed of trust are not the same fact, and a rendering with no permit is neither certain supply
 *  > nor zero.
 *
 *  `ApiClient.competitiveSupply()` was written for it and **no screen called it**, so the whole
 *  engine — two filters, an eight-tier evidence weight, and the raw-versus-weighted supply index —
 *  was unreachable. Its response was additionally typed `Record<string, unknown>`, so every field
 *  was invisible to `apps/web/src/api/deadFieldTyped.test.ts` and to any other audit that starts
 *  from the client's own declarations. Both are fixed here; the shapes now live in
 *  `apps/web/src/api/creDeal.ts`.
 *
 *  MEASURED BEFORE WRITING A LINE OF THIS CARD, and it is the sharpest instance of the shape this
 *  session kept finding. A pipeline of four projects, none of them matching the subject's product
 *  type, returns:
 *
 *  | | |
 *  |---|---|
 *  | `counts.competing` | **0** |
 *  | `excluded.counts.wrong_product` | **4** |
 *  | `weighted_index.band` | **`"undersupplied"`** |
 *  | `lsi` | **0** |
 *  | `discount_pct` | **0.0** |
 *
 *  **A market in which every supplied project was filtered out reports the single most favourable
 *  verdict the engine can produce**, and reports it identically to a market that genuinely has no
 *  competition. "Undersupplied" is an argument to build. That is worse than the four `clean: true`
 *  cases this session fixed, because those at least read as neutral.
 *
 *  **The engine is not wrong — nothing in it claims coverage.** `counts.competing` and
 *  `excluded.counts` are right there in the response, and its own note says the excluded projects
 *  are listed *"so a thin competitive set is visible, not implied"*. The defect would have been
 *  entirely this card's, which is why it is built the way it is:
 *
 *  * **The band is WITHHELD when nothing competed.** No competing project means no reading, not a
 *    favourable one. The card says what was excluded and why, and offers no supply verdict at all.
 *  * **`discount_pct` is withheld when `raw_units` is 0**, where the engine's `if raw else 0.0`
 *    makes "nothing to discount" indistinguishable from "no discount applied".
 *  * **Certain and rumored totals are never added.** The engine keeps them apart on purpose; a
 *    single "total competing units" would undo the one thing it is most careful about.
 *  * **`from_status_label` is rendered**, because it marks the row where the evidence tier was
 *    inferred from a status string rather than read from a recorded flag — the exact difference
 *    between a fact and a broker's assertion, and the reason the whole table exists.
 */
import type { ApiClient } from "../api/client";
import type { LotSupplyIndex, SupplyAssessment, SupplyIndexResult } from "../api/creDeal";
import { escapeHtml as esc } from "../ui/feedback";

const meta = (html: string, colour?: string) =>
  `<div class="meta" style="margin-top:4px${colour ? `;color:${colour}` : ""}">${html}</div>`;

const n0 = (v: number) => Math.round(v).toLocaleString("en-US");

/** `supply_pipeline.EVIDENCE`, in the engine's rank order. Mirrored so the editor can OFFER a tier
 *  that no project in the pipeline currently carries — the response only ever names the tiers that
 *  are present, exactly as `authorityCard.ts` has to mirror `FACT_TYPES`. Pinned against the Python
 *  by `supplyCard.test.ts`; the WEIGHT is the load-bearing column, because a drift there makes this
 *  card offer a discount the engine will not apply. */
export const EVIDENCE: readonly [string, string, number][] = [
  ["loan_recorded", "Construction loan recorded", 1.0],
  ["under_construction", "GC mobilized / vertical construction", 1.0],
  ["permit_issued", "Building permit issued", 0.85],
  ["permit_applied", "Permit application filed", 0.5],
  ["entitled", "Entitled / approved", 0.35],
  ["planning_filed", "Planning application filed", 0.2],
  ["announced", "Announced / rendering only", 0.05],
  ["unknown", "No recorded evidence", 0.05],
];

/** Is the assessment an answer, or an absence? True when the engine evaluated nothing — which the
 *  totals cannot express, because every one of them is 0 either way. */
export function isVacuous(s: SupplyAssessment): boolean {
  return s.counts.competing === 0;
}

/** How many projects the two filters removed. */
export function excludedCount(s: SupplyAssessment): number {
  return s.excluded.counts.out_of_window + s.excluded.counts.wrong_product;
}

/** The coverage line — always rendered, and it LEADS, because every total below it is computed over
 *  the competing set alone. */
function coverage(s: SupplyAssessment): string {
  const ex = excludedCount(s);
  const parts: string[] = [];
  if (s.excluded.counts.out_of_window) {
    parts.push(`${s.excluded.counts.out_of_window} outside the delivery window`);
  }
  if (s.excluded.counts.wrong_product) {
    parts.push(`${s.excluded.counts.wrong_product} a different product type`);
  }
  if (isVacuous(s)) {
    return `<div style="font-weight:600;color:var(--status-warn)">No competitive set</div>`
      + meta(ex
        ? `All ${ex} project(s) supplied were filtered out — ${esc(parts.join(", "))}. `
          + `<strong>This is not a finding of no competition.</strong> Every total below would read `
          + `zero either way, so no supply reading is shown.`
        : `No projects were supplied, so there is nothing to weigh.`, "var(--status-warn)");
  }
  return `<div style="font-weight:600">`
    + `${s.counts.competing} competing project(s)</div>`
    + meta(ex
      ? `${ex} excluded — ${esc(parts.join(", "))}. Every total below covers the `
        + `${s.counts.competing} that compete, not the ${s.counts.competing + ex} supplied.`
      : `Nothing was excluded: every project supplied competes.`);
}

/** One supply index, or the reason there is not one. */
function indexRow(label: string, ix: LotSupplyIndex): string {
  if (ix.months_of_supply == null || ix.lsi == null) {
    return `<tr><td>${esc(label)}</td><td colspan="2">${esc(ix.note)}</td></tr>`;
  }
  const colour = ix.band === "oversupplied" ? "var(--status-crit)"
    : ix.band === "undersupplied" ? "var(--status-good)" : "";
  return `<tr><td>${esc(label)}</td>`
    + `<td class="num">${ix.months_of_supply.toFixed(1)} mo · LSI ${ix.lsi}</td>`
    + `<td style="color:${colour}">${esc(ix.band)}</td></tr>`;
}

/** Render an assessment. `index` is present only when an absorption rate was supplied. */
export function renderSupply(host: HTMLElement, s: SupplyAssessment,
                             index?: SupplyIndexResult): HTMLElement {
  const el = document.createElement("div");
  el.style.marginTop = "8px";
  el.insertAdjacentHTML("beforeend", coverage(s));

  if (!isVacuous(s)) {
    // CERTAIN AND RUMORED ARE NEVER ADDED. The engine reports them as two totals on purpose and
    // says so in its note; one combined figure is precisely the number it refuses to produce.
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:6px">`
      + `<tr class="fin-sub"><td>Supply</td><td class="num">units</td><td>basis</td></tr>`
      + `<tr><td>Certain</td><td class="num">${n0(s.certain_supply_units)}</td>`
      + `<td>${s.counts.certain} project(s) with recorded evidence</td></tr>`
      + `<tr><td>Rumored</td><td class="num">${n0(s.rumored_supply_units)}</td>`
      + `<td>${s.counts.rumored} announced or unevidenced — <strong>not</strong> added to certain</td></tr>`
      + `<tr><td>Evidence-weighted</td><td class="num">${n0(s.weighted_units)}</td>`
      + `<td>of ${n0(s.raw_units)} raw`
      + (s.raw_units > 0 ? ` — a ${s.discount_pct.toFixed(1)}% discount` : ``)
      + `</td></tr>`
      + `</table>`);

    if (s.by_evidence.length) {
      el.insertAdjacentHTML("beforeend",
        `<table class="fin-table" style="margin-top:6px">`
        + `<tr class="fin-sub"><td>Evidence</td><td class="num">projects</td>`
        + `<td class="num">units</td><td class="num">weighted</td></tr>`
        + s.by_evidence.map((b) => `<tr><td>${esc(b.label)}</td>`
            + `<td class="num">${b.projects}</td><td class="num">${n0(b.units)}</td>`
            + `<td class="num">${n0(b.weighted)}</td></tr>`).join("")
        + `</table>`);
    }

    const inferred = s.competing.filter((r) => r.from_status_label);
    if (inferred.length) {
      el.insertAdjacentHTML("beforeend", meta(
        `${inferred.length} project(s) were tiered from a STATUS LABEL rather than a recorded flag: `
        + `${esc(inferred.map((r) => r.name ?? "unnamed").join(", "))}. A label is an assertion; `
        + `the weights above are only as good as it is.`, "var(--status-warn)"));
    }

    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:6px">`
      + `<tr class="fin-sub"><td>Project</td><td class="num">units</td><td>delivers</td>`
      + `<td>evidence</td><td class="num">weighted</td></tr>`
      + s.competing.map((r) => `<tr><td>${esc(r.name ?? "—")}`
          + (r.rumored ? ` <span class="meta">rumored</span>` : ``)
          + (r.from_status_label ? ` <span class="meta">from label</span>` : ``)
          + `</td><td class="num">${n0(r.units)}</td><td>${esc(r.delivery_date ?? "—")}</td>`
          + `<td>${esc(r.evidence_label)}</td>`
          + `<td class="num">${n0(r.weighted_units)}</td></tr>`).join("")
      + `</table>`);
  }

  // THE EXCLUSIONS ARE RENDERED WITH THEIR REASONS whether or not anything competed — when nothing
  // did, they are the only thing on the card that carries information.
  const excluded = [...s.excluded.out_of_window, ...s.excluded.wrong_product];
  if (excluded.length) {
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:6px">`
      + `<tr class="fin-sub"><td>Excluded</td><td class="num">units</td><td>delivers</td>`
      + `<td>why</td></tr>`
      + excluded.map((r) => `<tr><td>${esc(r.name ?? "—")}</td>`
          + `<td class="num">${n0(r.units)}</td><td>${esc(r.delivery_date ?? "—")}</td>`
          + `<td>${esc(r.excluded ?? "")}</td></tr>`).join("")
      + `</table>`);
  }

  // THE INDEX IS WITHHELD ON A VACUOUS SET. With nothing competing the weighted VDL is 0, which the
  // index reads as "undersupplied" — the most favourable verdict it can return, for want of input.
  if (index && !isVacuous(s)) {
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:8px">`
      + `<tr class="fin-sub"><td>Months of supply</td><td class="num">reading</td><td>band</td></tr>`
      + indexRow("Evidence-weighted — underwrite this", index.weighted_index)
      + indexRow("Raw, undiscounted", index.raw_index)
      + `</table>`
      + meta(index.delta_months != null
        ? `The discount is worth <strong>${index.delta_months.toFixed(1)} month(s)</strong> of `
          + `supply. ${esc(index.note)}`
        : esc(index.note)));
  } else if (index) {
    el.insertAdjacentHTML("beforeend", meta(
      `No months-of-supply reading: with nothing in the competitive set the weighted VDL is zero, `
      + `which the index would report as <em>undersupplied</em> — the most favourable band it can `
      + `return, on no evidence.`, "var(--status-warn)"));
  }

  el.insertAdjacentHTML("beforeend", meta(esc(s.note)));
  host.appendChild(el);
  return el;
}

/** One row of the pipeline the card sends. */
export interface SupplyProject {
  name: string;
  units: number;
  delivery_date: string;
  product_type: string;
  evidence: string;
}

/** The request body, with the evidence tier expanded into the boolean flag the engine reads.
 *  `evidence_of` prefers an explicit flag over a status label, so sending the flag is what makes
 *  `from_status_label` false — a row typed here is a recorded fact as far as this card knows. */
export function bodyFor(rows: SupplyProject[], opts: {
  windowStart?: string; windowEnd?: string; productType?: string; absorption?: number;
}): { projects: unknown[]; window_start?: string; window_end?: string;
      product_type?: string; monthly_absorption?: number } {
  const projects = rows.map((r) => {
    const p: Record<string, unknown> = {
      name: r.name, units: r.units, delivery_date: r.delivery_date,
      product_type: r.product_type,
    };
    if (r.evidence && r.evidence !== "unknown") p[r.evidence] = true;
    return p;
  });
  const body: ReturnType<typeof bodyFor> = { projects };
  if (opts.windowStart) body.window_start = opts.windowStart;
  if (opts.windowEnd) body.window_end = opts.windowEnd;
  if (opts.productType) body.product_type = opts.productType;
  if (opts.absorption != null && opts.absorption > 0) body.monthly_absorption = opts.absorption;
  return body;
}

/** The two response shapes the route returns, told apart by the field only the index form carries. */
export function isIndexResult(r: SupplyAssessment | SupplyIndexResult): r is SupplyIndexResult {
  return "weighted_index" in r;
}

export interface SupplyCtx {
  api: ApiClient;
  projectId: () => string | null | undefined;
  setStatus: (m: string) => void;
}

export function renderSupplyCard(root: HTMLElement, ctx: SupplyCtx): HTMLElement {
  const host = document.createElement("div");
  host.id = "pf-supply";
  host.className = "fin-card";
  host.style.marginTop = "10px";
  host.innerHTML = `<div class="section-title">Competitive supply</div>`
    + `<div class="meta">Units are discounted by what is <strong>recorded</strong> about a project, `
    + `not by the label on the deck. Only projects delivering inside this deal's own window and `
    + `matching its product type compete; everything else is listed with the reason it was left out.`
    + `</div>`;

  const controls = document.createElement("div");
  controls.style.cssText = "margin-top:6px;display:flex;gap:6px;flex-wrap:wrap;align-items:center";
  const mk = (type: string, placeholder: string, width: string, title: string) => {
    const i = document.createElement("input");
    i.type = type; i.className = "portal-filter"; i.placeholder = placeholder;
    i.style.width = width; i.title = title;
    return i;
  };
  const wsIn = mk("date", "window start", "150px",
    "Start of this deal's delivery-and-lease-up window.");
  const weIn = mk("date", "window end", "150px",
    "End of the window. A tower finishing after we stabilize is not our competition.");
  const ptIn = mk("text", "product type", "130px",
    "This deal's product type. A project of a different type is excluded, and counted as excluded.");
  const absIn = mk("number", "absorption /mo", "120px",
    "Units absorbed per month. Supplying it adds the months-of-supply index, raw beside weighted.");
  controls.append(wsIn, weIn, ptIn, absIn);
  host.appendChild(controls);

  const editor = document.createElement("div"); editor.style.marginTop = "6px";
  host.appendChild(editor);
  const actions = document.createElement("div"); actions.style.marginTop = "6px";
  const add = document.createElement("button");
  add.className = "file-btn"; add.textContent = "Add project";
  const go = document.createElement("button");
  go.className = "file-btn"; go.style.marginLeft = "6px"; go.textContent = "Weigh the pipeline";
  actions.append(add, go);
  host.appendChild(actions);
  const out = document.createElement("div"); host.appendChild(out);
  root.appendChild(host);

  const rows: SupplyProject[] = [];

  // Persisted per project: a competitive pipeline is typed in once and consulted for months, and
  // re-entering six projects to re-run a reading is the reason a screen goes unused.
  const load = () => {
    const pid = ctx.projectId();
    if (!pid) return;
    try {
      const raw = localStorage.getItem(`supply-pipeline:${pid}`);
      if (!raw) return;
      const saved = JSON.parse(raw) as { rows?: SupplyProject[]; ws?: string; we?: string;
                                         pt?: string; abs?: string };
      if (Array.isArray(saved.rows)) rows.push(...saved.rows);
      wsIn.value = saved.ws ?? ""; weIn.value = saved.we ?? "";
      ptIn.value = saved.pt ?? ""; absIn.value = saved.abs ?? "";
    } catch { /* a corrupt or unavailable store is an empty form, never an error */ }
  };
  const save = () => {
    const pid = ctx.projectId();
    if (!pid) return;
    try {
      localStorage.setItem(`supply-pipeline:${pid}`, JSON.stringify({
        rows, ws: wsIn.value, we: weIn.value, pt: ptIn.value, abs: absIn.value,
      }));
    } catch { /* private mode, blocked storage — the card still works, it just forgets */ }
  };
  for (const c of [wsIn, weIn, ptIn, absIn]) c.onchange = save;

  const paint = () => {
    editor.replaceChildren();
    if (!rows.length) {
      editor.insertAdjacentHTML("beforeend", meta(
        `No projects yet. Add the ones you know about — including the ones you only half believe; `
        + `the evidence tier is what decides how much of each counts.`));
      return;
    }
    const table = document.createElement("table"); table.className = "fin-table";
    table.innerHTML = `<tr class="fin-sub"><td>Project</td><td class="num">units</td>`
      + `<td>delivers</td><td>product</td><td>recorded evidence</td><td></td></tr>`;
    rows.forEach((r, i) => {
      const tr = document.createElement("tr");
      const cell = (child: HTMLElement, num = false) => {
        const td = document.createElement("td");
        if (num) td.className = "num";
        td.appendChild(child); return td;
      };
      const name = mk("text", "name", "100%", "");
      name.value = r.name;
      const units = mk("number", "units", "80px", "");
      units.value = r.units ? String(r.units) : "";
      const when = mk("date", "", "150px", "");
      when.value = r.delivery_date;
      const product = mk("text", "product", "110px", "");
      product.value = r.product_type;
      const ev = document.createElement("select");
      ev.className = "portal-filter";
      ev.title = "The strongest thing RECORDED about this project. A recorded loan is a fact; "
        + "a press release is not.";
      for (const [key, lab, weight] of EVIDENCE) {
        const o = document.createElement("option");
        o.value = key; o.textContent = `${lab} — ${Math.round(weight * 100)}%`;
        ev.appendChild(o);
      }
      ev.value = r.evidence;
      const del = document.createElement("button");
      del.className = "tool-btn"; del.textContent = "✕"; del.title = "Remove this project";
      del.onclick = () => { rows.splice(i, 1); save(); paint(); };

      const sync = () => {
        rows[i] = {
          name: name.value.trim(), units: Number(units.value) || 0,
          delivery_date: when.value, product_type: product.value.trim(), evidence: ev.value,
        };
        save();
      };
      for (const input of [name, units, when, product]) input.onchange = sync;
      ev.onchange = sync;

      tr.append(cell(name), cell(units, true), cell(when), cell(product), cell(ev), cell(del));
      table.appendChild(tr);
    });
    editor.appendChild(table);
  };

  add.onclick = () => {
    rows.push({ name: "", units: 0, delivery_date: "", product_type: ptIn.value.trim(),
                evidence: "permit_issued" });
    save(); paint();
  };

  go.onclick = async () => {
    const pid = ctx.projectId();
    if (!pid) { out.innerHTML = meta("Open a project first."); return; }
    go.disabled = true;
    out.innerHTML = meta("weighing the pipeline…");
    ctx.setStatus("weighing competitive supply…");
    try {
      const body = bodyFor(rows, {
        windowStart: wsIn.value, windowEnd: weIn.value,
        productType: ptIn.value.trim(), absorption: Number(absIn.value) || undefined,
      });
      const r = await ctx.api.competitiveSupply(pid, body);
      out.replaceChildren();
      const assessment = isIndexResult(r) ? r.supply : r;
      renderSupply(out, assessment, isIndexResult(r) ? r : undefined);
      ctx.setStatus(isVacuous(assessment)
        ? `no competitive set — ${excludedCount(assessment)} excluded`
        : `${assessment.counts.competing} competing · ${n0(assessment.weighted_units)} weighted units`);
    } catch (e) {
      out.innerHTML = meta(esc((e as Error).message), "var(--status-crit)");
      ctx.setStatus("competitive supply failed");
    } finally {
      go.disabled = false;
    }
  };

  load();
  paint();
  return host;
}
