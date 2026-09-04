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
 *  has no client method BY DESIGN: it is fetched by the server-rendered share page, not by this SPA.
 *
 *  ### A capability this file cannot currently reach
 *
 *  That ninth route serves geometry only to a token minted with `show_model`, which the backend
 *  treats as an opt-in independent of `show_payments` — *"a token may carry payments, or geometry,
 *  or neither, and granting one never implies the other"*. **`createShareToken` below does not send
 *  it**, and the row type `shareTokens` returns has no `show_model` field, so every token this
 *  product mints has it false and that route always 404s for them. The public 3D viewer is dark from
 *  the UI's side.
 *
 *  Not fixed here on purpose: this slice's claim is that no behaviour changed, and adding a
 *  parameter would falsify it. Recorded so the next reader of this file finds it at the method
 *  rather than in a backlog.
 *
 *  A mixin, so every call site resolves unchanged; `api/surface.test.ts` is what proves it.
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

export function withClientPortal<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class ClientPortal extends Base {
  /** `showPayments` is the explicit opt-in for THIS token's digest to carry the payment schedule. */
  createShareToken(pid: string, label?: string, showPayments?: boolean) {
    return this.json<{ token: string; label: string | null; share_path: string; revoked: boolean }>(
      `/projects/${pid}/share-tokens`,
      { method: "POST", body: JSON.stringify({ label: label ?? "", show_payments: !!showPayments }) });
  }
  /** CLIENT-PORTAL — read-only share tokens for a project-readiness digest. */
  shareTokens(pid: string) {
    type Tok = { token: string; label: string | null; revoked: boolean; created_at: string | null;
      created_by: string | null; view_count: number; last_viewed_at: string | null; share_path: string;
      show_payments: boolean };
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
