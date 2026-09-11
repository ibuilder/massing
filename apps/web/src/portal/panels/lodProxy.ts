/** The coarse-proxy action's wording — pure, so the rules can be tested without a DOM.
 *
 *  `lodCensus` has always returned `plan.pct_saved` and the standards panel has always rendered it —
 *  *"proxy would save 47%"* — while `POST …/model/lod/proxy` had no client method at all. **A stated
 *  benefit with no way to act on it**, which is the same shape as the budget card's "1 offline
 *  baseline(s) installable" that PR #523 closed, and it was found the same way: the route surfaced
 *  as newly-visible dark once the reachability gate stopped letting English vouch for a route.
 */

/** What `lodCensus().plan` says can be done, as the button and its explanation. */
export interface ProxyPlan {
  status: string;
  proxied?: string[];
  triangles_saved?: number | null;
  pct_saved?: number | null;
  reason?: string;
}

/** Whether building a proxy is worth offering, and — when it is not — the reason to show instead.
 *
 *  A plan with nothing to proxy is the common case on a small model, and the server refuses it
 *  anyway (`stored: false` with a reason). Offering a button that will certainly be refused is the
 *  offered-and-refused shape this codebase keeps removing, so the reason is shown in its place. */
export function proxyOffer(plan: ProxyPlan): { can: boolean; why: string } {
  if (plan.reason) return { can: false, why: plan.reason };
  if (!plan.proxied?.length) {
    return { can: false, why: "nothing in this model is worth replacing with a coarse stand-in" };
  }
  if (plan.pct_saved == null || plan.pct_saved <= 0) {
    return { can: false, why: "the census measured no triangle saving, so a proxy would cost more than it returns" };
  }
  return { can: true, why: "" };
}

/** The confirmation. Names what the artefact IS, because a stand-in mistaken for real geometry is
 *  the failure the server's own docstring says it stamps every box to prevent. */
export function proxyConfirm(plan: ProxyPlan): string {
  const cls = plan.proxied?.length ?? 0;
  return `Build a coarse proxy for ${cls} class${cls === 1 ? "" : "es"}, saving about `
    + `${plan.pct_saved}% of triangles?\n\nThis writes a SEPARATE file beside the model — it does not `
    + "change the model. Every box is stamped as a stand-in that must not be measured, scheduled or "
    + "priced, and the original geometry is untouched.";
}

/** What the build actually did. A refusal is reported as one, never as a quiet success. */
export function proxySummary(r: {
  written: boolean; stored: boolean; elements_replaced?: number; storeys_proxied?: number;
  reason?: string;
}): string {
  if (!r.stored) {
    return `No proxy was stored — ${r.reason || "the model had nothing to replace"}. `
      + "Nothing was written beside the model.";
  }
  const n = r.elements_replaced ?? 0;
  const s = r.storeys_proxied ?? 0;
  return `Proxy stored: ${n} element${n === 1 ? "" : "s"} replaced across ${s} storey`
    + `${s === 1 ? "" : "s"}. It is an ordinary IFC and needs converting before the viewer can serve `
    + "it as a coarse tier.";
}
