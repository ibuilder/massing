/** COMPTIER-DARK — the render half. The reading is in `proforma/compTierRead.ts`, with its tests.
 *
 *  One screen for `GET /projects/{pid}/comps/tiered`, which had none. The order below is the order
 *  the engine argues for, not the order the payload happens to arrive in: **coverage first**, then
 *  the band, then what the band rests on, then what it left out, then the tie-breaks, then the
 *  appraiser's exclusions, then the comps themselves.
 */
import type { ApiClient } from "../api/client";
import type { TieredComps } from "../api/creDeal";
import { escapeHtml as esc } from "../ui/feedback";
import {
  type Tone, FIELDS, TONE_CSS, bandHeadline, bandRow, blankNote, conflictNote, conflictRows,
  excludedNote, fieldSpec, setState, tierMix, unattributedNote,
} from "./compTierRead";

const meta = (html: string, tone?: Tone) =>
  `<div class="meta" style="margin-top:4px${tone ? `;color:${TONE_CSS[tone]}` : ""}">${html}</div>`;

/** Render one evaluated comp set for one requested field. */
export function renderTieredComps(host: HTMLElement, r: TieredComps): HTMLElement {
  const el = document.createElement("div");
  el.style.marginTop = "8px";

  // An empty register and a register whose every comp was excluded are different problems.
  const state = setState(r);
  if (state) {
    el.insertAdjacentHTML("beforeend", meta(esc(state.text), state.empty ? "warn" : "crit"));
    host.appendChild(el);
    return el;
  }

  const b = r.requested;
  const head = bandHeadline(b, r.ladder);
  el.insertAdjacentHTML("beforeend",
    `<div style="font-weight:600;color:${TONE_CSS[head.tone]}">${head.text}</div>`);

  // The band, in the field's own units.
  const row = bandRow(b);
  if (row) {
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:8px">`
      + `<tr class="fin-sub"><td>${esc(row.label)}</td>`
      + row.cells.map(([k]) => `<td class="num">${esc(k)}</td>`).join("") + `</tr>`
      + `<tr><td>band</td>`
      + row.cells.map(([, v]) => `<td class="num">${esc(v)}</td>`).join("") + `</tr>`
      + `</table>`);
  }

  // THE ENGINE'S OWN QUALIFIER, verbatim. This sentence is the whole reason the leaf exists —
  // *"Strengthen that source before the number carries a decision"* — and until this card there was
  // no screen to carry it. It is rendered on every band rather than only on weak ones, because the
  // engine writes it for every band and suppressing it on the strong ones would make its presence a
  // signal the engine never intended.
  if (b.note) el.insertAdjacentHTML("beforeend", meta(esc(b.note), head.tone));

  const un = unattributedNote(b);
  if (un) el.insertAdjacentHTML("beforeend", meta(esc(un), "warn"));

  const blank = blankNote(b);
  if (blank) el.insertAdjacentHTML("beforeend", meta(esc(blank), "warn"));

  // The tier mix, in the ladder's order.
  const mix = tierMix(b, r.ladder);
  if (mix.length) {
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:8px">`
      + `<tr class="fin-sub"><td>Source tier (strongest first)</td><td class="num">comps in band</td></tr>`
      + mix.map((m) => `<tr><td${m.weak ? ` style="color:${TONE_CSS.warn}"` : ""}>`
          + `${esc(m.label)}</td><td class="num">${m.count}</td></tr>`).join("")
      + `</table>`);
  }

  // The other two fields, so a reader can see which have a population at all before switching.
  const others = FIELDS.filter((f) => f.key !== b.field);
  if (others.length) {
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:6px">`
      + `<tr class="fin-sub"><td>Other bands</td><td class="num">n / comps</td><td>median</td>`
      + `<td>weakest source</td></tr>`
      + others.map((f) => {
          const s = r.statistics[f.key];
          if (!s) return `<tr><td>${esc(f.label)}</td><td class="num">—</td><td>—</td><td>—</td></tr>`;
          return `<tr><td>${esc(f.label)}</td>`
            + `<td class="num">${s.n} / ${s.of_comps}</td>`
            + `<td>${s.median == null ? "—" : esc(fieldSpec(f.key).fmt(s.median))}</td>`
            + `<td>${esc(s.worst_tier_label ?? "—")}</td></tr>`;
        }).join("")
      + `</table>`);
  }

  const conf = conflictNote(b);
  if (conf) el.insertAdjacentHTML("beforeend", meta(esc(conf)));

  const rows = conflictRows(r);
  if (rows.length) {
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:6px">`
      + `<tr class="fin-sub"><td>Address</td><td>kept tier</td><td>outranked</td></tr>`
      + rows.map((c) => `<tr><td>${esc(c.address)}`
          + (c.deltas.length
             ? `<div class="meta">${c.deltas.map((d) => esc(d)).join("<br>")}</div>` : "")
          + `</td><td>${esc(c.kept)}</td><td>${esc(c.outranked)}</td></tr>`).join("")
      + `</table>`);
  }

  const ex = excludedNote(r);
  if (ex) el.insertAdjacentHTML("beforeend", meta(esc(ex), "warn"));

  // The comps themselves, strongest first — the engine already sorted them.
  el.insertAdjacentHTML("beforeend",
    `<table class="fin-table" style="margin-top:8px">`
    + `<tr class="fin-sub"><td>Comp</td><td>tier</td><td class="num">$/SF</td>`
    + `<td class="num">cap</td><td class="num">rent</td></tr>`
    + r.comps.map((c) => {
        const num = (v: number | null, key: string) =>
          v == null ? "—" : esc(fieldSpec(key).fmt(v));
        return `<tr><td>${esc(c.address || "(unnamed)")}`
          + `<div class="meta">${esc(c.ref ?? "")}`
          // `matched: false` is a source string the ladder could not place, which is NOT the same
          // fact as the register's own `Other` option — that one is recognised and says there is no
          // attribution. The distinction is only visible here, so it is said here.
          + (c.source ? ` · ${esc(c.source)}` : " · no source set")
          + (c.matched ? "" : ` · <em>unrecognised source</em>`)
          + `</div></td>`
          + `<td>${esc(c.label)}</td><td class="num">${num(c.price_psf, "price_psf")}</td>`
          + `<td class="num">${num(c.cap_rate, "cap_rate")}</td>`
          + `<td class="num">${num(c.rent_psf, "rent_psf")}</td></tr>`;
      }).join("")
    + `</table>`);

  el.insertAdjacentHTML("beforeend", meta(esc(r.note)));
  host.appendChild(el);
  return el;
}

export interface CompTierCtx {
  api: ApiClient;
  projectId: () => string | null | undefined;
  setStatus: (m: string) => void;
}

export function renderCompTierCard(root: HTMLElement, ctx: CompTierCtx): HTMLElement {
  const host = document.createElement("div");
  host.id = "pf-comp-tier";
  host.className = "fin-card";
  host.style.marginTop = "10px";
  host.innerHTML = `<div class="section-title">Comparables by source tier</div>`
    + `<div class="meta">A median resting on one asking price is not the same number as a median `
    + `resting on six recorded sales. Comps for the same address are resolved by source tier rather `
    + `than averaged, and every band reports the weakest source it rests on.</div>`;

  const bar = document.createElement("div");
  bar.style.cssText = "margin-top:6px;display:flex;gap:6px;align-items:center;flex-wrap:wrap";
  const sel = document.createElement("select");
  sel.className = "portal-filter";
  // `esc()` on values that come from `FIELDS`, a local literal in `compTierRead.ts`. The escape is
  // not load-bearing today and `ui/innerHtmlGuard.test.ts` flagged it anyway, which is the correct
  // behaviour: its alternative is a BASELINE entry asserting these stay local, and a declaration
  // that a value is safe is a claim somebody has to re-check every time the list moves. Escaping is
  // unconditionally right and costs nothing.
  sel.innerHTML = FIELDS.map((f) =>
    `<option value="${esc(f.key)}">${esc(f.label)}</option>`).join("");
  const go = document.createElement("button");
  go.className = "file-btn";
  go.textContent = "Read comps";
  bar.append(sel, go);
  host.appendChild(bar);

  const out = document.createElement("div");
  host.appendChild(out);
  root.appendChild(host);

  const load = async () => {
    const project = ctx.projectId();
    if (!project) { out.innerHTML = meta("Open a project first."); return; }
    go.disabled = true;
    out.innerHTML = meta("reading the comparables register…");
    ctx.setStatus("ranking comparables by source tier…");
    try {
      const r = await ctx.api.tieredComps(project, sel.value);
      out.innerHTML = "";
      renderTieredComps(out, r);
      // THE COVERAGE, not the median. A status line reading "median $310/sf" is the one sentence
      // somebody quotes, and the engine refuses to publish that number without its weakest source —
      // so neither does this.
      const b = r.requested;
      ctx.setStatus(r.comp_count === 0 ? "no comparables on file"
        : b.n === 0 ? `no ${fieldSpec(b.field).label} on any of ${b.of_comps} comp(s)`
        : `${fieldSpec(b.field).label} band on ${b.n} of ${b.of_comps} comp(s) · weakest source `
          + `${b.worst_tier_label ?? b.worst_tier ?? "?"}`);
    } catch (e) {
      out.innerHTML = meta(esc((e as Error).message), "crit");
      ctx.setStatus("comparables could not be read");
    } finally {
      go.disabled = false;
    }
  };

  go.onclick = load;
  // Re-read on a field change rather than making the reader press the button again: `field` only
  // chooses which band is `requested`, so a switch is a different view of one call's worth of data
  // and a stale band beside a changed selector is the kind of mismatch nobody notices.
  sel.onchange = () => { if (!go.disabled) void load(); };

  return host;
}
