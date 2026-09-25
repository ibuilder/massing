/** Scan-to-BIM: the aggregate deviation, and the per-element LOD 500 verification behind it.
 *
 *  Both routes shipped complete and neither had a screen. `scanDeviation` sat in the callerless
 *  freeze list; `/scan/verify-lod500` had **no client method at all** and was frozen in
 *  `services/api/test_route_reachability.py` as unreachable — while `scan_deviation.analyze`'s own
 *  refusal message tells the reader to *"use /scan/verify-lod500, which queries per element and
 *  never truncates the model."* **A refusal that redirects to an unreachable feature is a gate you
 *  can read and cannot satisfy**, which is the AUTHORITY-DARK shape, created here by SCAN-TRUNC's
 *  own wording. Wiring both is what makes that sentence true.
 *
 *  WHAT WAS MEASURED BEFORE ANY OF THIS WAS WRITTEN, and it is a clean negative worth stating.
 *  Five engines this session carried a verdict that went vacuous once nothing had been evaluated, so
 *  the degenerate case was measured first: a scan covering NOTHING returns
 *  `verified: 0, stamped: 0, uncovered: 50`, stamps nothing, and says so — *"absence of points is
 *  not a pass"*. `within_tolerance` is `null` rather than `false` on an uncovered element, which is
 *  the distinction the whole engine exists for. **It fails closed and needed no repair.**
 *
 *  So the card's only job is not to subtract that care:
 *
 *  * the aggregate's REFUSAL is rendered as a refusal, not as a zero — a truncated reference yields
 *    no `within_pct`, and printing "0%" or an empty histogram would reinstate exactly the defect
 *    SCAN-TRUNC closed;
 *  * `uncovered` is given equal weight to `verified`, because a high verified count over a thin
 *    scan is the number somebody would quote;
 *  * a finding is shown as NOT stamped, since verified-as-wrong is a punch item rather than a
 *    handover.
 */
import type { ApiClient } from "../../api/client";
import { escapeHtml as esc } from "../../ui/feedback";

export type Deviation = Awaited<ReturnType<ApiClient["scanDeviation"]>>;
export type Lod500 = Awaited<ReturnType<ApiClient["scanVerifyLod500"]>>;

const meta = (html: string, colour?: string) =>
  `<div class="meta" style="margin-top:4px${colour ? `;color:${colour}` : ""}">${html}</div>`;

const n0 = (v: number) => Math.round(v).toLocaleString("en-US");

/** Did the engine decline to produce a deviation figure? */
export function refused(d: Deviation): boolean {
  return d.within_pct == null;
}

/** The aggregate. On a refusal this renders the reason and NOTHING numeric. */
export function renderDeviation(host: HTMLElement, d: Deviation): HTMLElement {
  const el = document.createElement("div");
  el.style.marginTop = "8px";

  if (refused(d)) {
    el.insertAdjacentHTML("beforeend",
      `<div style="font-weight:600;color:var(--status-warn)">No deviation figure</div>`
      + meta(esc(d.error ?? "the engine returned no reading"), "var(--status-warn)")
      + (d.note ? meta(esc(d.note)) : ""));
    host.appendChild(el);
    return el;
  }

  el.insertAdjacentHTML("beforeend",
    `<div style="font-weight:600">${d.within_pct!.toFixed(1)}% of scan points within `
    + `${d.tolerance ?? "—"} m</div>`
    + meta(`${n0(d.point_count)} scan point(s) against ${n0(d.reference_count)} model surface `
           + `vertices · ${n0(d.out_of_tolerance ?? 0)} out of tolerance`)
    + (d.points_truncated
        ? meta(`Only ${n0(d.point_count)} of ${n0(d.points_total)} readable scan points were `
               + `examined — a scan file is written in sweep order, so this covers a REGION of the `
               + `cloud rather than a sample of it.`, "var(--status-warn)")
        : ""));

  if (d.histogram?.length) {
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:6px">`
      + `<tr class="fin-sub"><td>Deviation band</td><td class="num">points</td></tr>`
      + d.histogram.map((h) => `<tr><td>${esc(h.band)}</td>`
          + `<td class="num">${n0(h.count)}</td></tr>`).join("")
      + `</table>`);
  }
  el.insertAdjacentHTML("beforeend", meta(
    `mean ${d.mean_deviation ?? "—"} m · p95 ${d.p95_deviation ?? "—"} m · max ${d.max_deviation ?? "—"} m`));
  if (d.note) el.insertAdjacentHTML("beforeend", meta(esc(d.note)));
  host.appendChild(el);
  return el;
}

/** The per-element verification. `uncovered` leads beside `verified`, deliberately. */
export function renderLod500(host: HTMLElement, r: Lod500): HTMLElement {
  const el = document.createElement("div");
  el.style.marginTop = "8px";
  const total = r.verified + r.findings_count + r.uncovered;

  el.insertAdjacentHTML("beforeend",
    `<div style="font-weight:600">${r.applied ? `Stamped ${n0(r.stamped)}` : "Dry run"} — `
    + `${n0(r.verified)} verified of ${n0(total)} element(s)</div>`
    // THE UNCOVERED COUNT IS NOT A FOOTNOTE. A verified count over a thin scan is the number
    // somebody quotes, and the engine refuses to treat absence as evidence — so must this.
    + meta(r.uncovered
        ? `<strong>${n0(r.uncovered)} never scanned</strong> — not stamped and not counted against `
          + `the model. They need another scan position; absence of points is not evidence.`
        : `Every element was covered by the scan.`,
      r.uncovered ? "var(--status-warn)" : undefined));

  if (r.findings_count) {
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:6px">`
      + `<tr class="fin-sub"><td>Verified as WRONG — not stamped</td><td>class</td>`
      + `<td class="num">p95</td><td class="num">max</td></tr>`
      + r.findings.map((f) => `<tr><td>${esc((f.guid ?? "").slice(0, 10))}…</td>`
          + `<td>${esc(f.ifc_class ?? "—")}</td>`
          + `<td class="num">${f.p95_deviation ?? "—"}</td>`
          + `<td class="num">${f.max_deviation ?? "—"}</td></tr>`).join("")
      + `</table>`
      + meta(`An element measured outside tolerance is a punch item, not a handover — it is `
             + `deliberately left unstamped.`, "var(--status-crit)"));
  }

  if (r.accuracy_recorded) {
    el.insertAdjacentHTML("beforeend", meta(
      `${n0(r.accuracy_recorded)} stamp(s) carry the measured deviation, so the LOD 500 assertion `
      + `states an accuracy rather than a bare claim.`));
  }
  el.insertAdjacentHTML("beforeend", meta(esc(r.note)));
  host.appendChild(el);
  return el;
}

export interface ScanCtx {
  api: ApiClient;
  projectId: () => string | null | undefined;
  setStatus: (m: string) => void;
}

/** The card: pick a cloud, run the aggregate, then the per-element verification. */
export function renderScanCard(root: HTMLElement, ctx: ScanCtx): HTMLElement {
  const host = document.createElement("div");
  host.id = "scan-verify";
  host.style.marginTop = "8px";
  host.innerHTML = meta(
    `Upload an as-built point cloud (XYZ/CSV). The aggregate answers <em>how close is the build to `
    + `the model</em>; the per-element pass answers <em>which elements can be asserted as built</em> `
    + `— and never truncates the model to do it.`);

  const row = document.createElement("div");
  row.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:6px 0";
  const tol = document.createElement("input");
  tol.type = "number"; tol.step = "0.01"; tol.className = "portal-filter"; tol.style.width = "90px";
  tol.value = "0.05"; tol.title = "Tolerance in metres — the in/out threshold.";
  const label = document.createElement("label");
  label.className = "mini-btn"; label.textContent = "⇪ Point cloud"; label.style.cursor = "pointer";
  const input = document.createElement("input");
  input.type = "file"; input.accept = ".xyz,.csv,.txt"; input.style.display = "none";
  label.appendChild(input);
  row.append(tol, label);
  host.appendChild(row);
  const out = document.createElement("div"); host.appendChild(out);
  root.appendChild(host);

  input.onchange = async () => {
    const f = input.files?.[0]; const pid = ctx.projectId();
    if (!f) return;
    if (!pid) { out.innerHTML = meta("Open a project first."); return; }
    const t = Number(tol.value) || 0.05;
    out.replaceChildren();
    out.innerHTML = meta("comparing the cloud to the model…");
    ctx.setStatus("scan deviation…");
    try {
      const d = await ctx.api.scanDeviation(pid, f, t);
      out.replaceChildren();
      renderDeviation(out, d);
      ctx.setStatus(refused(d) ? "no deviation figure — see the reason"
        : `${d.within_pct!.toFixed(1)}% within ${t} m`);
      // The per-element pass runs whatever the aggregate said: when the aggregate REFUSED because
      // the model reference was cut short, this is the route its own message points at.
      out.insertAdjacentHTML("beforeend", meta("verifying per element…"));
      const r = await ctx.api.scanVerifyLod500(pid, f, { tolerance: t, apply: false });
      out.lastElementChild?.remove();
      renderLod500(out, r);
      ctx.setStatus(`${r.verified} verified · ${r.findings_count} finding(s) · ${r.uncovered} uncovered`);
    } catch (e) {
      out.insertAdjacentHTML("beforeend", meta(esc((e as Error).message), "var(--status-crit)"));
      ctx.setStatus("scan verification failed");
    } finally {
      input.value = "";
    }
  };

  return host;
}
