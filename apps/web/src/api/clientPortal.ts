/** Client portal — how does someone with no account see this project, and answer back?
 *
 *  SCALE-SEAM (90), third slice from the methods above the STAYING banner.
 *
 *  Two halves of one question. The OWNER's half mints, lists and revokes share tokens
 *  (`createShareToken`, `shareTokens`, `revokeShareToken`) and reads what came back
 *  (`clientDecisions`). The RECIPIENT's half is the token-authenticated public surface:
 *  `sharedPageUrl` and `sharedDigestUrl` build the no-login URLs, and `sharedComment` and
 *  `sharedDecision` post back a comment or an approve/acknowledge/decline.
 *
 *  They belong together because the token is the seam: it is minted on one side, IS the credential
 *  on the other, and revoking it closes both. Splitting owner-side from recipient-side would put a
 *  capability and its only means of exercise in different files.
 *
 *  `services/api/src/aec_api/routers/client_portal.py` groups the same set — 8 of its 9 routes are
 *  exactly these methods, checked rather than assumed. The ninth, `GET /shared/{token}/model.frag`,
 *  still has no client method: it is a whole-file response a recipient opens by URL, not JSON this
 *  SPA parses. What it DOES need from here is the mint-time opt-in that makes it answer at all.
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
  /** PORTAL-TXN phase 3 — post a client comment through a share token (public; lands on the token's
   * BCF feedback topic, so the team answers from the Issue Board). */
  sharedComment(token: string, body: { text: string; client_name?: string }) {
    return this.json<{ topic_id: string; comment_id: string; author: string | null; text: string;
      created_at: string | null }>(
      `/shared/${encodeURIComponent(token)}/comment`, { method: "POST", body: JSON.stringify(body) });
  }
  /** PORTAL-TXN — record a client decision through a share token (public; approve/acknowledge/decline). */
  sharedDecision(token: string, body: {
    item_type: string; item_ref: string; action: "approved" | "acknowledged" | "declined";
    client_name?: string; note?: string;
  }) {
    return this.json<{
      id: number; item_type: string; item_ref: string; action: string;
      client_name: string | null; note: string | null; created_at: string | null;
    }>(`/shared/${encodeURIComponent(token)}/decision`, { method: "POST", body: JSON.stringify(body) });
  }
  /** PORTAL-TXN — the project's client-decision feed (editor only), newest first. */
  clientDecisions(pid: string, limit = 500) {
    type D = { id: number; item_type: string; item_ref: string; action: string; client_name: string | null;
      note: string | null; created_at: string | null; token: string };
    return this.json<{ decisions: D[] }>(`/projects/${pid}/client-decisions?limit=${encodeURIComponent(limit)}`);
  }
  };
}
