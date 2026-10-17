import type { CvBridgeStatus } from "../../api/types";
import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * CV-BRIDGE-DARK — the site-photo progress bridge, and the half of it a person is supposed to read.
 *
 * `services/api/src/aec_api/cv_bridge.py` is a feature-flagged bridge, not a model: the platform
 * never runs computer vision itself. An operator sets `AEC_CV_BRIDGE` and points a vision service
 * at `POST …/cv-progress/ingest` (one estimate) or `…/ingest-batch` (a photo sweep), and each
 * accepted estimate is written to a `schedule_activity`'s percent.
 *
 * **Three routes were frozen as unreachable and only ONE of them wants a screen.** `ingest` and
 * `ingest-batch` are INBOUND machine doors — the caller is the vendor's service, so a browser
 * caller would be the wrong thing to build, exactly as for `/scim/v2/Users`. `…/status` is the
 * human-facing half: it answers *is this wired up, and what do I hand my vision vendor?* and
 * nothing asked it. *A count of "three dark routes" overstated the product gap by two, and the
 * reachability list cannot tell the two kinds apart* — it records that nobody calls a route, which
 * is a defect for a screen's route and the design for a webhook's.
 *
 * So the card states the flag, and when the flag is off it says what turning it on would require
 * rather than hiding the feature: a disabled integration that is invisible is indistinguishable
 * from one that does not exist, and the difference is a purchase decision.
 */

/** The flag, in the two states an operator can be in. Returned rather than written to a DOM. */
export function bridgeNote(st: CvBridgeStatus): { html: string; kind: "ok" | "warn" } {
  if (!st.enabled) {
    return {
      html: "<b>NOT ENABLED</b> — no site-photo progress is being accepted. The platform does not "
        + "run a vision model itself; set <code>AEC_CV_BRIDGE</code> on the API and point a vision "
        + "service at the two endpoints below. Nothing is estimated or fabricated while this is off.",
      kind: "warn",
    };
  }
  return {
    html: "<b>ENABLED</b> — estimates POSTed by your vision service are written to the matching "
      + "activity's percent. Every write is attributed to the posting account and shows in the "
      + "schedule like any other progress update.",
    kind: "ok",
  };
}

/** The wire contract, as rows, so the integrator does not have to read the OpenAPI document. */
export function contractRows(st: CvBridgeStatus): { field: string; meaning: string }[] {
  return Object.entries(st.contract || {}).map(([field, meaning]) => ({ field, meaning }));
}

/** The two endpoints, with which one a sweep should use. */
export function endpointRows(pid: string): { method: string; path: string; use: string }[] {
  return [
    { method: "POST", path: `/projects/${pid}/cv-progress/ingest`,
      use: "one estimate — a single activity observed in a single photo" },
    { method: "POST", path: `/projects/${pid}/cv-progress/ingest-batch`,
      use: "a photo sweep — many estimates in one request" },
  ];
}

/**
 * Render the card into `host`.
 *
 * `host` is a slot appended up front by the caller, and the `isConnected` check before the write is
 * this panel file's own recorded hazard: `ctx.root` is shared by every panel and cleared by
 * whoever renders next, so a late `.then` appending straight onto it puts this card into a
 * different screen. That was found in review on PR #527; leaving the guard out would be rebuilding
 * it on purpose.
 */
export async function renderCvBridge(ctx: PanelContext, host: HTMLElement, pid: string): Promise<void> {
  let st: CvBridgeStatus;
  try {
    st = await ctx.host.api.cvProgressStatus(pid);
  } catch {
    return;                                   // the bridge status is informational; never a banner
  }
  if (!host.isConnected) return;

  const note = bridgeNote(st);
  const rows = contractRows(st);
  const eps = endpointRows(pid);
  const batch = Object.entries(st.batch_contract || {})
    .map(([k, v]) => `<code>${esc(k)}</code> — ${esc(v)}`).join("<br>");

  host.className = "dash-card";
  host.style.margin = "0 0 8px";
  host.innerHTML = `<div><b>📷 Site-photo progress (CV bridge)</b></div>`
    + `<div class="result-note ${note.kind}" style="margin-top:4px">${note.html}</div>`
    + `<table class="mini" style="margin-top:6px"><thead><tr><th>method</th><th>endpoint</th>`
    + `<th>when</th></tr></thead><tbody>`
    + eps.map((e) => `<tr><td>${esc(e.method)}</td><td><code>${esc(e.path)}</code></td>`
        + `<td class="meta">${esc(e.use)}</td></tr>`).join("")
    + `</tbody></table>`
    + `<div class="meta" style="margin-top:6px"><b>One estimate</b>: `
    + rows.map((r) => `<code>${esc(r.field)}</code> — ${esc(r.meaning)}`).join("<br>")
    + `</div>`
    + (batch ? `<div class="meta" style="margin-top:4px"><b>A sweep</b>: ${batch}</div>` : "")
    + `<div class="meta" style="margin-top:6px">${esc(st.note)}</div>`
    + `<div class="meta" style="margin-top:2px">Reference client: <code>${esc(st.reference_adapter)}</code>`
    + ` · feature flag <code>${esc(st.feature)}</code></div>`;
}
