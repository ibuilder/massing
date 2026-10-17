/** Client portal — how does someone with no account see this project, and answer back?
 *
 *  SCALE-SEAM (90), third slice from the methods above the STAYING banner.
 *
 *  **Everything here is the OWNER's half, and that is the correction PORTAL-TXN-DARK made.** It
 *  mints, lists and revokes share tokens (`createShareToken`, `shareTokens`, `revokeShareToken`),
 *  builds the links to hand out (`sharedPageUrl`, `sharedDigestUrl`), and reads what came back
 *  (`clientDecisions`).
 *
 *  This file used to claim a RECIPIENT's half as well — `sharedComment` and `sharedDecision`, which
 *  posted to the two public write routes. A recipient has no account and arrives from a link, so the
 *  surface that serves them is `client_portal.to_html`, a server-rendered page; neither method could
 *  ever have had a caller here, and both were frozen as unreachable while the transaction had no
 *  screen at either end. They are deleted, and the page now carries the controls.
 *
 *  `services/api/src/aec_api/routers/client_portal.py` holds all nine routes of the seam, and the
 *  split between them is not owner-vs-recipient but **who parses the response**. The four owner
 *  routes are JSON this SPA reads. Of the five public ones, two are whole responses a recipient
 *  opens by URL (`GET /shared/{token}` and `/model.frag` — the first a page, the second a fragment
 *  download), one is JSON nothing here consumes (`/digest`), and two are writes issued by that
 *  page's own script. What the public half DOES need from this file is the mint-time opt-ins that
 *  make the model and the payment schedule answer at all.
 *
 *  ### The opt-in this file could not reach — fixed 2026-09-04
 *
 *  That ninth route serves geometry only to a token minted with `show_model`, which the backend
 *  treats as an opt-in independent of `show_payments` — *"a token may carry payments, or geometry,
 *  or neither, and granting one never implies the other"*. **`createShareToken` did not send it**,
 *  and the row type `shareTokens` returns had no `show_model` field, so every token this product
 *  minted had it false and that route 404'd for all of them.
 *
 *  Both halves are closed below, and they are separate defects with separate consequences. The
 *  missing PARAMETER made the capability unreachable. The missing ROW FIELD made it unauditable —
 *  `_public_row` has always returned `show_model`, the wire carried it, and the type simply dropped
 *  it, so an owner could not have told a geometry link from a digest link even once one existed.
 *  R22-PUBLIC-VIEWER's shipped record claims *"the owner's token list shows which links carry
 *  geometry"*; until this change that was true of the JSON and false of the product.
 *
 *  The two flags are passed as separate arguments, never as one "share more" level, because the
 *  backend's rule is that granting one must never imply the other. A single enum or an ordered
 *  level would make that rule unexpressible at the call site.
 *
 *  A mixin, so every call site resolves unchanged; `api/surface.test.ts` is what proves it.
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

export function withClientPortal<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class ClientPortal extends Base {
  /** Mint a read-only share token. `showPayments` and `showModel` are two INDEPENDENT opt-ins, and
   * the backend is explicit that granting one never implies the other: `showPayments` lets this
   * token's digest carry the owner-invoice payment schedule, `showModel` lets it fetch the project's
   * geometry fragment (`GET /shared/{token}/model.frag` — shapes and placements, never the source
   * IFC). Both default to false; a token already in somebody's inbox is never widened. */
  createShareToken(pid: string, label?: string, showPayments?: boolean, showModel?: boolean) {
    return this.json<{ token: string; label: string | null; share_path: string; revoked: boolean;
      show_payments: boolean; show_model: boolean }>(
      `/projects/${pid}/share-tokens`,
      { method: "POST", body: JSON.stringify({ label: label ?? "", show_payments: !!showPayments,
        show_model: !!showModel }) });
  }
  /** CLIENT-PORTAL — read-only share tokens for a project-readiness digest. */
  shareTokens(pid: string) {
    type Tok = { token: string; label: string | null; revoked: boolean; created_at: string | null;
      created_by: string | null; view_count: number; last_viewed_at: string | null; share_path: string;
      show_payments: boolean; show_model: boolean };
    return this.json<{ tokens: Tok[] }>(`/projects/${pid}/share-tokens`);
  }
  revokeShareToken(pid: string, token: string) {
    return this.json<{ revoked: boolean }>(`/projects/${pid}/share-tokens/${encodeURIComponent(token)}`,
      { method: "DELETE" });
  }
  /** The public read-only HTML page for a share token (opens with no login — the human share link). */
  sharedPageUrl(token: string) { return this.url(`/shared/${encodeURIComponent(token)}`); }
  /** The public digest JSON URL for a share token. */
  sharedDigestUrl(token: string) { return this.url(`/shared/${encodeURIComponent(token)}/digest`); }
  // PORTAL-TXN-DARK — `sharedComment` and `sharedDecision` stood here, and they are DELETED rather
  // than wired. The two routes they addressed are public and token-authenticated, and the person who
  // posts to them has no account: they arrive from a link in an email. The surface that serves them
  // is `client_portal.to_html` — a server-rendered page — so an SPA method for either could never
  // have an SPA caller, and `clientCallers.test.ts` froze both as unreachable for months while the
  // transaction they belong to had no screen at either end.
  //
  // *A callerless method whose only legitimate caller could never be this program is not an unbuilt
  // feature; it is a method on the wrong side of a seam.* The roadmap read these two as "one missing
  // feature, not two missing buttons" and that was half the story — the feature was missing, and
  // these were never going to be the half of it that lived here.
  /** PORTAL-TXN — the project's client-decision feed (editor only), newest first. */
  clientDecisions(pid: string, limit = 500) {
    type D = { id: number; item_type: string; item_ref: string; action: string; client_name: string | null;
      note: string | null; created_at: string | null; token: string };
    return this.json<{ decisions: D[] }>(`/projects/${pid}/client-decisions?limit=${encodeURIComponent(limit)}`);
  }
  };
}
