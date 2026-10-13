import type { ApiClient } from "../api/client";
import { escapeHtml as esc } from "../ui/feedback";

/** Is this deal's output admissible in an IC memo or a claim? (PROVENANCE-DARK)
 *
 *  `services/api/src/aec_api/provenance_report.py` answers it across three legs — the scenario's
 *  material assumptions, the basis-of-estimate ledger, and the recorded agent answers — and refuses
 *  to blend them: *"a single percentage lets a well-cited proforma hide an uncited estimate, and a
 *  memo is not admissible because it scored well — each leg answers for itself."*
 *
 *  **Both of its routes had no client method**, so the verdict was computed for nobody, and neither
 *  existing gate could say so: `test_route_reachability` asks whether a route is CALLED and
 *  `clientCallers.test.ts` whether a METHOD is called, and a route with no method is absent from the
 *  second by construction. `services/api/test_verdict_reachable.py` asks the third question.
 *
 *  ### The one distinction this card exists to preserve
 *
 *  `no_data` and `not_captured` are different answers and the engine says why: *"'you have not
 *  filled this in' and 'this system has nowhere to put it' send a reader to completely different
 *  places"* — one fills a field, the other changes a schema. A card that rendered both as a dash
 *  would destroy the thing the engine was built around, so they get different words, different
 *  colours and different next steps.
 *
 *  And `incomplete` is NOT a pass. The engine reaches it when every leg that holds data is fully
 *  cited but some leg holds nothing at all: *"an absent leg is not a clean one, and calling this
 *  admissible would let an empty estimate pass as a documented one."*
 */

type Admissibility = Awaited<ReturnType<ApiClient["projectAdmissibility"]>>;
type Leg = Admissibility["legs"][number];

export interface AdmissibilityCtx {
  api: ApiClient;
  projectId: () => string | null | undefined;
  setStatus: (m: string) => void;
}

/** The verdict's presentation. `incomplete` is deliberately not green and not neutral. */
export const VERDICT_TONE: Record<string, { word: string; colour: string }> = {
  admissible: { word: "ADMISSIBLE", colour: "var(--status-good)" },
  blocked: { word: "BLOCKED", colour: "var(--status-crit)" },
  incomplete: { word: "INCOMPLETE — not a pass", colour: "var(--status-warn)" },
};

/** Each leg status in the engine's own terms, with the next step it implies.
 *
 *  `no_data` and `not_captured` differ in BOTH halves — what happened and what to do about it — and
 *  that is the whole reason this table exists rather than a tick and a cross. */
export const LEG_STATUS: Record<string, { word: string; colour: string; next: string }> = {
  cited: { word: "cited", colour: "var(--status-good)", next: "" },
  has_uncited: { word: "has uncited items", colour: "var(--status-crit)",
                 next: "cite the items named below" },
  no_data: { word: "nothing recorded", colour: "var(--status-warn)",
             next: "nobody has filled this in — an absent leg is not a clean one" },
  not_captured: { word: "nowhere to record it", colour: "var(--status-warn)",
                  next: "this deployment has no store for this leg — a schema change, not a data entry" },
};

/** How many uncited items a leg NAMES versus how many it HAS.
 *
 *  The engine caps `uncited` at `MAX_NAMED` (25) and keeps `uncited_count` as the total, so printing
 *  `uncited.length` is TRUNC-COUNTED a fourth time: a leg with 48 uncited items would read as having
 *  25. Returns null when nothing is held back, so the caller says nothing rather than "25 of 25". */
export function namedBound(leg: Leg): { named: number; total: number } | null {
  const total = leg.uncited_count ?? 0;
  const named = (leg.uncited ?? []).length;
  return named && total > named ? { named, total } : null;
}

/** True when the leg's own evidence is what blocks, rather than its absence. */
export function isBlocking(leg: Leg): boolean {
  return leg.status === "has_uncited";
}

export function renderAdmissibilityCard(root: HTMLElement, ctx: AdmissibilityCtx): HTMLElement {
  const host = document.createElement("div");
  host.id = "pf-admissibility";
  host.className = "fin-card";
  host.style.marginTop = "10px";
  host.innerHTML = `<div class="section-title">Admissibility of the record</div>`
    + `<div class="meta">Is this deal's output admissible in an IC memo or a claim? Three legs —`
    + ` assumptions, basis of estimate, recorded answers — each answering for itself. There is`
    + ` deliberately no blended score.</div>`;
  const out = document.createElement("div"); out.style.marginTop = "6px";
  out.innerHTML = `<div class="meta">reading the record…</div>`;
  host.appendChild(out);
  root.appendChild(host);

  const pid = ctx.projectId();
  if (!pid) {
    out.innerHTML = `<div class="meta">Open or save a project to judge its record.</div>`;
    return host;
  }

  void ctx.api.projectAdmissibility(pid).then((a) => {
    const tone = VERDICT_TONE[a.verdict] ?? { word: esc(a.verdict), colour: "var(--status-warn)" };
    const legs = a.legs.map((leg) => {
      const st = LEG_STATUS[leg.status]
        ?? { word: esc(leg.status), colour: "var(--status-warn)", next: "" };
      const bound = namedBound(leg);
      const items = (leg.uncited ?? []).length
        ? `<ul style="margin:2px 0 0 16px">`
          + (leg.uncited ?? []).map((u) => `<li class="meta">${esc(u)}</li>`).join("")
          + `</ul>`
          // A BOUND, never a page length dressed as a total.
          + (bound ? `<div class="meta" style="opacity:.8">naming ${bound.named} of `
              + `${bound.total} — the engine caps the list</div>` : "")
        : "";
      return `<div style="margin:6px 0">`
        + `<div style="display:flex;gap:8px;align-items:baseline;flex-wrap:wrap">`
        + `<b style="flex:0 0 auto">${esc(leg.leg)}</b>`
        + `<span style="font-size:11px;font-weight:700;text-transform:uppercase;`
        + `letter-spacing:.04em;color:${st.colour}">${esc(st.word)}</span>`
        + `<span class="meta" style="flex:1 1 120px">${leg.counted} item(s) counted`
        + (leg.uncited_count ? ` · ${leg.uncited_count} uncited` : "") + `</span></div>`
        + (leg.note ? `<div class="meta" style="opacity:.85">${esc(leg.note)}</div>` : "")
        + (st.next ? `<div class="meta" style="color:${st.colour}">→ ${esc(st.next)}</div>` : "")
        + items + `</div>`;
    }).join("");
    out.innerHTML =
      `<div style="font-size:16px;font-weight:700;color:${tone.colour}">${tone.word}</div>`
      + `<div class="meta" style="margin:2px 0 6px">${esc(a.reason)}</div>`
      + legs
      + (a.scenario_id
        ? `<div class="meta" style="margin-top:6px;opacity:.8">Judged on scenario `
          + `${esc(a.scenario_id)} — the project's most recent, which is the one a memo is written `
          + `from.</div>`
        : `<div class="meta" style="margin-top:6px;color:var(--status-warn)">No saved scenario — the `
          + `assumptions leg has nothing to read.</div>`)
      + `<div class="meta" style="margin-top:6px;opacity:.85">${esc(a.note)}</div>`;
    ctx.setStatus(`Admissibility: ${tone.word}`);
  }).catch((e: Error) => {
    out.innerHTML = `<div class="meta">Admissibility unavailable: ${esc(e.message)}</div>`;
  });

  return host;
}
