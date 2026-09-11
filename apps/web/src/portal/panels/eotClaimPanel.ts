/**
 * R40-EOT — the extension-of-time screen.
 *
 * Two analyses of the same claim, and the DEFAULT is the sourced one: its baseline is a captured
 * artefact rather than a typed date, and the baseline is the most contested input in a delay claim.
 * The typed path stays because a claim is sometimes argued before a baseline exists, and it is
 * labelled for what it is rather than offered as an equal.
 *
 * **The method list is fetched, never hardcoded.** Posting with no method returns `method_required`
 * carrying `methods_available`, so the closed set the engine enforces is the closed set the screen
 * offers. A second copy of the AACE/SCL taxonomy in the client is a copy that can drift from the one
 * doing the refusing.
 *
 * All wording rules live in `eotClaim.ts`; this function only draws them.
 */
import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";
import {
  methodGate, refusal, claimHeadline, eventFinding, concurrencyNote, coverageNote,
  provenanceLine, sourcedRefusal,
} from "./eotClaim";
import type { EotResult, EotSourced } from "../../api/schedule";

export async function renderEotClaim(ctx: PanelContext): Promise<HTMLElement> {
  const pid = ctx.host.projectId()!;
  const card = document.createElement("div");
  card.className = "dash-card";
  card.innerHTML = `<div class="section-title" style="margin:0 0 8px">⏱ Extension of time `
    + `<span style="opacity:.6;font-weight:500;font-size:11px">(AACE 29R-03 / SCL Protocol)</span></div>`
    + `<div class="meta">Loading the method taxonomy…</div>`;

  // The engine's own closed set, asked for rather than restated.
  let methods: Record<string, string> = {};
  try {
    const probe = await ctx.host.api.scheduleEot(pid, {});
    methods = probe.methods_available || {};
  } catch (e) {
    card.innerHTML += `<div class="meta">Method list unavailable: ${esc((e as Error).message)}</div>`;
    return card;
  }

  const opts = Object.keys(methods).map((m) =>
    `<option value="${esc(m)}">${esc(m.replace(/_/g, " "))}</option>`).join("");
  card.innerHTML = `<div class="section-title" style="margin:0 0 8px">⏱ Extension of time `
    + `<span style="opacity:.6;font-weight:500;font-size:11px">(AACE 29R-03 / SCL Protocol)</span></div>`
    + `<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end">`
    + `<label style="display:flex;flex-direction:column;gap:2px;font-size:11px;color:var(--muted)">Method`
    + `<select class="portal-filter" data-eot="method"><option value="">— choose —</option>${opts}</select></label>`
    + `<label style="display:flex;flex-direction:column;gap:2px;font-size:11px;color:var(--muted)">Baseline finish`
    + `<input class="portal-filter" data-eot="baseline_finish" type="date" style="width:150px"></label>`
    + `<label style="display:flex;flex-direction:column;gap:2px;font-size:11px;color:var(--muted)">Actual finish`
    + `<input class="portal-filter" data-eot="actual_finish" type="date" style="width:150px"></label>`
    + `<button class="mini-btn" data-eot-run="sourced" type="button">Analyse from captured baseline</button>`
    + `<button class="mini-btn" data-eot-run="typed" type="button">Analyse from typed dates</button></div>`
    + `<div data-eot-meaning class="meta" style="margin-top:6px"></div>`
    + `<div data-eot-out style="margin-top:10px"></div>`;

  const sel = card.querySelector<HTMLSelectElement>('[data-eot="method"]')!;
  const meaning = card.querySelector<HTMLElement>("[data-eot-meaning]")!;
  const out = card.querySelector<HTMLElement>("[data-eot-out]")!;
  // The method's own published weakness, shown at the moment of choosing it rather than after.
  sel.addEventListener("change", () => {
    meaning.textContent = methods[sel.value] ? `${sel.value}: ${methods[sel.value]}` : "";
  });

  const read = () => {
    const v = (k: string) =>
      card.querySelector<HTMLInputElement>(`[data-eot="${k}"]`)!.value.trim() || null;
    return { method: sel.value || null, baseline_finish: v("baseline_finish"),
             actual_finish: v("actual_finish") };
  };

  card.querySelectorAll<HTMLButtonElement>("[data-eot-run]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const form = read();
      const g = methodGate(form.method);
      if (!g.can) { out.innerHTML = `<div class="meta">Cannot analyse — ${esc(g.why)}.</div>`; return; }
      const sourced = btn.dataset.eotRun === "sourced";
      card.querySelectorAll<HTMLButtonElement>("[data-eot-run]").forEach((b) => { b.disabled = true; });
      out.innerHTML = `<div class="meta">Analysing…</div>`;
      try {
        const s = sourced ? await ctx.host.api.scheduleEotSourced(pid, form) : null;
        const r: EotResult = s ? (s.analysis as EotResult) : await ctx.host.api.scheduleEot(pid, form);
        out.replaceChildren();
        out.innerHTML = draw(r, s);
      } catch (e) {
        out.innerHTML = `<div class="meta">Analysis unavailable: ${esc((e as Error).message)}</div>`;
      } finally {
        card.querySelectorAll<HTMLButtonElement>("[data-eot-run]").forEach((b) => { b.disabled = false; });
      }
    });
  });
  return card;
}

/** One analysis, rendered. A refusal is drawn as the instruction it is, never as a blank. */
function draw(r: EotResult, s: EotSourced | null): string {
  const sr = s ? sourcedRefusal(s) : null;
  if (sr) return `<div class="meta" style="color:#9a6700">${esc(sr)}</div>`;
  if (!r) return `<div class="meta">The server returned no analysis.</div>`;

  const refused = refusal(r);
  const head = `<div style="font-weight:700;color:${refused ? "#9a6700" : "#1a7f37"}">`
    + `${esc(claimHeadline(r))}</div>`;
  const prov = `<div class="meta" style="margin-top:6px">${esc(provenanceLine(s))}</div>`;
  const cover = (s ? coverageNote(s) : [])
    .map((c) => `<div class="meta" style="margin-top:6px;color:#9a6700">⚠ ${esc(c)}</div>`).join("");
  if (refused) return head + prov + cover;

  const rows = (r.events || []).map((e) =>
    `<tr><td>${esc(e.id)}</td><td>${esc(e.kind || "—")}</td>`
    + `<td>${esc(e.activity_id || "—")}</td>`
    + `<td style="text-align:right;font-variant-numeric:tabular-nums">${e.days}</td>`
    + `<td>${esc(eventFinding(e))}</td></tr>`).join("");
  const table = rows
    ? `<table class="portal-table" style="margin-top:8px"><thead><tr><th scope="col">Event</th>`
      + `<th scope="col">Kind</th><th scope="col">Activity</th>`
      + `<th scope="col" style="text-align:right">Days</th><th scope="col">Finding</th>`
      + `</tr></thead><tbody>${rows}</tbody></table>`
    : `<div class="meta" style="margin-top:8px">No events reached the analysis.</div>`;

  return head + prov + cover + table
    + `<div class="section-title" style="margin:10px 0 4px">Concurrency</div>`
    + `<div class="meta">${esc(concurrencyNote(r))}</div>`
    + (r.note ? `<div class="meta" style="margin-top:8px;opacity:.8">${esc(r.note)}</div>` : "");
}
