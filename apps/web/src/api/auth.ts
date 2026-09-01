/** Authentication, MFA, sessions, project membership, and ops observability.
 *
 *  SCALE-SEAM ⑦. Route-group `/auth`, 20 methods, taken out of `client.ts` by the
 *  route each method calls — the recipe ⑥ established. They sat in **four** separate regions
 *  (`authProviders` at the top of the class, `stepUp` down among the sealing methods, the login/MFA
 *  run, and the user-admin run), which is again the concrete form of "the `// --- section ---`
 *  comments no longer delimit anything".
 *
 *  **The group the roadmap flagged as needing care, and the care turned out to be already taken.**
 *  SCALE-SEAM ⑥ predicted `/auth` would be awkward because it "owns token state rather than just
 *  calling routes". It does mutate token state — `changePassword` and `logoutAll` both adopt the
 *  fresh token the server returns — but the state itself has lived on `HttpCore` since the T2
 *  transport extraction, behind a **public** `setToken`. A mixin is a BASE of `ApiClient`, so it
 *  cannot see `ApiClient`'s privates; it can see its own base's public and protected members. The
 *  blocker that stopped the SSE methods travelling in ③ (`liveStream` was private on `ApiClient`)
 *  has no analogue here. `token` itself stays `private` on `HttpCore` and is not touched.
 *
 *  SCALE-SEAM ⓮ adds the project roster — *who is on this project?* `myRole`, `members`,
 *  `addMember`, `removeMember`. Routes are `/projects/{pid}/me` and `/members`, not `/auth`.
 *  Grouped by what they ANSWER, not by first path segment.
 *
 *  SCALE-SEAM ⓯ adds ops observability — *what did the system just do, and what broke?*
 *  `auditLog`, `errorLog`, `clearErrorLog`, `reportClientError`. **⑦ left these behind on
 *  purpose:** they sit under the `// --- admin: user management ---` banner but route to
 *  `/audit`, `/admin/errors` and `/client-errors`. ⑦ grouped by route; ⓯ groups by ANSWER.
 *  The banner was never the domain. ⑦ was right for its recipe; this slice uses a later one.
 *
 *  SCALE-SEAM ⓶ adds the project catalog — *which projects can I open?* List, one, create, delete, import-bundle. `meta` and the discipline tree stayed.
 *
 *  SCALE-SEAM ⓷ adds deploy entitlement — *is this deployment entitled and wired?* Integrations, capabilities, licence, cloud-check. Photo upload stayed (PHOTO-PIN).
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it: moving
 *  a method is invisible to it, losing one fails it by number.
 */
import { HttpCore } from "./httpCore";
import type { AccountUser, AuditEntry, IntegrationGroup, ProjectMember, ProjectRole } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withAuth<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Auth extends Base {
  /** Enabled SSO providers (Google/Microsoft/Procore) for the login UI. */
  authProviders() {
    return this.json<{ providers: { id: string; label: string }[] }>("/auth/providers");
  }
  /** Re-prove the account password for ONE action, yielding a short-lived assertion.
   *
   *  Sealing needs this because a bearer token identifies a session, not a person: anything holding
   *  the token could otherwise emit documents under the licensee's seal. The returned value is NOT a
   *  session token — the server refuses it as one — so it is safe to pass straight to pdfSeal. */
  stepUp(password: string, act = "pdf.seal") {
    return this.json<{ token: string; act: string; expires_in: number }>(
      "/auth/step-up", { method: "POST", body: JSON.stringify({ password, act }) });
  }
  /** Password login. If the account has MFA on, the reply is `{ mfa_required, mfa_token }` instead
   *  of a token — complete it with `mfaVerify(mfa_token, code)`. */
  login(username: string, password: string) {
    return this.json<{ token?: string; username: string; role?: string;
      mfa_required?: boolean; mfa_token?: string }>(
      "/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
  }
  /** Login step 2: exchange the challenge ticket + a TOTP or recovery code for a session. */
  mfaVerify(mfaToken: string, code: string) {
    return this.json<{ token: string; username: string; role: string }>(
      "/auth/mfa/verify", { method: "POST", body: JSON.stringify({ mfa_token: mfaToken, code }) });
  }
  mfaStatus() {
    return this.json<{ enabled: boolean; pending: boolean; recovery_remaining: number }>("/auth/mfa/status");
  }
  mfaSetup() {
    return this.json<{ secret: string; otpauth_uri: string }>("/auth/mfa/setup", { method: "POST" });
  }
  mfaEnable(code: string) {
    return this.json<{ enabled: boolean; recovery_codes: string[] }>(
      "/auth/mfa/enable", { method: "POST", body: JSON.stringify({ code }) });
  }
  mfaDisable(password: string, code: string) {
    return this.json<{ enabled: boolean }>(
      "/auth/mfa/disable", { method: "POST", body: JSON.stringify({ password, code }) });
  }
  register(username: string, password: string) {
    return this.json<{ username: string; role: string }>(
      "/auth/register", { method: "POST", body: JSON.stringify({ username, password }) });
  }
  me() {
    return this.json<{ username: string; role: string | null; authenticated: boolean;
      tier?: string; features?: Record<string, boolean>; platform_admin?: boolean }>("/auth/me");
  }
  logout() {
    return this.json<{ ok: boolean }>("/auth/logout", { method: "POST" }).catch(() => ({ ok: false }));
  }
  /** Change your own password (requires the current one). The server revokes all other sessions
   *  and returns a fresh token for this tab; adopt it so the current session keeps working. */
  async changePassword(current: string, next: string) {
    const r = await this.json<{ ok: boolean; token?: string }>(
      "/auth/password", { method: "POST", body: JSON.stringify({ current, new: next }) });
    if (r.token) this.setToken(r.token);
    return r;
  }
  /** Sign out of every other session (revoke all outstanding tokens); keeps this tab signed in
   *  via the fresh token the server returns. Use after a suspected token leak. */
  async logoutAll() {
    const r = await this.json<{ ok: boolean; token?: string }>("/auth/logout-all", { method: "POST" });
    if (r.token) this.setToken(r.token);
    return r;
  }
  /** Admin: force-revoke all of a user's outstanding sessions (offboarding / lost device). */
  revokeUserSessions(username: string) {
    return this.json<{ ok: boolean }>(
      `/auth/users/${encodeURIComponent(username)}/revoke-sessions`, { method: "POST" });
  }
  listUsers() {
    return this.json<AccountUser[]>("/auth/users");
  }
  createUser(username: string, password: string, role: "admin" | "user" = "user", email?: string) {
    return this.json<AccountUser>(
      "/auth/users", { method: "POST", body: JSON.stringify({ username, password, role, email }) });
  }
  updateUser(username: string, patch: { role?: "admin" | "user"; active?: boolean; email?: string }) {
    return this.json<AccountUser>(
      `/auth/users/${encodeURIComponent(username)}`, { method: "PATCH", body: JSON.stringify(patch) });
  }
  resetUserPassword(username: string, password: string) {
    return this.json<{ ok: boolean }>(
      `/auth/users/${encodeURIComponent(username)}/password`,
      { method: "POST", body: JSON.stringify({ password }) });
  }
  /** Admin: mint a single-use reset token for a user to set their own password. */
  issueResetToken(username: string) {
    return this.json<{ username: string; reset_token: string; expires_in: number }>(
      `/auth/users/${encodeURIComponent(username)}/reset-token`, { method: "POST" });
  }
  /** Unauthenticated: set a new password using a reset token (the token is the credential). */
  resetWithToken(token: string, next: string) {
    return this.json<{ ok: boolean; username: string }>(
      `/auth/reset`, { method: "POST", body: JSON.stringify({ token, new: next }) });
  }
  /** The caller's own effective role on a project (drives UI capability gating). */
  myRole(pid: string) {
    return this.json<{ user: string; role: ProjectRole | null; party_role: string | null; rbac: boolean }>(
      `/projects/${pid}/me`);
  }
  /** Project members roster — who is on this project, and in what role. */
  members(pid: string) {
    return this.json<ProjectMember[]>(`/projects/${pid}/members`);
  }
  /** Add a project member (admin). */
  addMember(pid: string, body: { user: string; role: ProjectRole; party_role?: string | null; company?: string | null }) {
    return this.json<{ user: string; role: ProjectRole; party_role: string | null }>(
      `/projects/${pid}/members`, { method: "POST", body: JSON.stringify(body) });
  }
  /** Remove a project member (admin). */
  removeMember(pid: string, user: string) {
    return this.json<{ ok: boolean }>(
      `/projects/${pid}/members/${encodeURIComponent(user)}`, { method: "DELETE" });
  }
  /** Admin: read the audit trail (newest first), optionally filtered. */
  auditLog(params: { action?: string; actor?: string; since?: string; limit?: number } = {}) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v) qs.set(k, String(v));
    return this.json<AuditEntry[]>(`/audit${qs.toString() ? `?${qs}` : ""}`);
  }
  /** Admin: the error-log feed (server 500s + reported client errors), newest first. */
  errorLog(params: { source?: string; level?: string; since_hours?: number; limit?: number } = {}) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v != null && v !== "") qs.set(k, String(v));
    return this.json<{ stats: { total: number; by_source: Record<string, number>; [k: string]: unknown };
      errors: { id: string; ts: string; source: string; level: string; kind: string | null;
        message: string | null; method: string | null; path: string | null; status: number | null;
        actor: string | null; project_id: string | null; request_id: string | null;
        traceback: string | null; detail: Record<string, unknown> | null }[] }>(
      `/admin/errors${qs.toString() ? `?${qs}` : ""}`);
  }
  /** Admin: prune the error log to its retention cap. */
  clearErrorLog() {
    return this.json<{ pruned: number }>("/admin/errors", { method: "DELETE" });
  }
  /** Report a browser-side error to the server feed. Fire-and-forget: never throws into the app. */
  reportClientError(e: { message: string; kind?: string; path?: string; level?: string;
    detail?: Record<string, unknown> }): void {
    void fetch(this.url("/client-errors"),
      { method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json", ...this.authHeaders() },
        body: JSON.stringify(e), keepalive: true }).catch(() => { /* best-effort */ });
  }
  /** Every project visible to the caller — id, name, and `model_kind` (which tool a project opens
   *  with). Was documented as "absolute URL for a GET endpoint", a neighbour's comment left behind;
   *  the gate only caught it once `bundleUrl` moved out from under its 14-line lookahead. */
  projects() {
    return this.json<{ id: string; name: string; model_kind?: "frag" | "ifc" | null }[]>(`/projects`);
  }
  /** One project's metadata, incl. model_kind + has_source_ifc (used to gate IFC-only tools). */
  project(pid: string) {
    return this.json<{ id: string; name: string; model_kind?: string | null; has_source_ifc?: boolean }>(
      `/projects/${pid}`);
  }
  /** Create a blank project (no IFC needed) — GC portal + proforma work immediately. */
  createProject(name: string) {
    return this.json<{ id: string; name: string }>("/projects", { method: "POST", body: JSON.stringify({ name }) });
  }
  /** Delete a project and everything it owns (rows + geometry + blobs). */
  deleteProject(pid: string) {
    return this.json<{ deleted: boolean; id: string; rows: Record<string, number> }>(
      `/projects/${pid}`, { method: "DELETE" });
  }
  /** Open a `.mass` container as a new project (fresh id). Legacy `.mmproj` (v1) still works. */
  async importBundle(file: File, name?: string) {
    const fd = new FormData();
    fd.append("file", file);
    if (name) fd.append("name", name);
    const res = await fetch(this.url(`/projects/import-bundle`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error(`import -> ${res.status}`);
    return res.json() as Promise<{ id: string; name: string; model_kind?: string | null }>;
  }
  /** Admin: integration settings (AI / email / SSO). Secret values are never returned. */
  integrations() {
    return this.json<{ groups: IntegrationGroup[] }>("/settings/integrations");
  }
  saveIntegrations(values: Record<string, string>) {
    return this.json<{ groups: IntegrationGroup[] }>(
      "/settings/integrations", { method: "PUT", body: JSON.stringify({ values }) });
  }
  /** Live "Test connection" for one integration group (by its catalog name) → {ok, message}. */
  testIntegration(group: string) {
    return this.json<{ ok: boolean; message: string }>(
      "/settings/integrations/test", { method: "POST", body: JSON.stringify({ group }) });
  }
  /** Which optional integrations are wired (AI / email / SSO) — for status badges. */
  capabilities() {
    return this.json<{ ai: boolean; email: boolean; sso: string[]; local_mode?: boolean;
      license_tier?: string }>("/capabilities");
  }
  /** Massing licence state — plan tier, per-tier features, masked key. Drives the Settings licence panel. */
  license() {
    return this.json<{ tier: string; tier_label: string; enforced: boolean;
      features: { exports: string[]; api_access: boolean; sso: boolean; navisworks: boolean };
      tiers: { id: string; label: string; features: Record<string, unknown> }[];
      key_configured: boolean; key_masked: string; key_format_valid: boolean | null;
      message: string; manage_url: string;
      cloud?: { online: boolean; url?: string; secret_configured?: boolean; note?: string } }>("/license");
  }
  /** CLOUD-BRIDGE: validate the recorded key against massing.cloud + apply the returned plan (admin). */
  licenseCloudCheck() {
    return this.json<{ checked_online: boolean; valid?: boolean; tier?: string; reason?: string | null;
      applied: boolean; tier_before: string; tier_after: string; error?: string }>(
      "/license/cloud-check", { method: "POST" });
  }
  };
}
