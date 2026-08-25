/** CLOUD-SSO / CLOUD-LIBRARY client — massing.cloud identity + the user's project library.
 *
 *  **Why this is standalone functions rather than the usual `withX` mixin.** Every other API domain
 *  in this folder is a mixin folded into `ApiClient`'s inheritance chain, and this one is written to
 *  match that shape *except* for the last step: it takes the client as its first argument instead of
 *  being `extends`-ed onto it. `HttpCore` exposes `url()` and `authHeaders()` publicly, so nothing is
 *  lost by doing so — and folding it in would mean editing `client.ts`, whose one-line mixin chain is
 *  the single most contended line in the repository. Promoting these to a mixin later is a mechanical
 *  change with no call-site churn.
 *
 *  **No token ever crosses this boundary.** The massing.cloud access/refresh tokens live server-side
 *  on the `cloud_identities` row; the browser holds only this app's own session. That is why the
 *  library is read through our API rather than called directly from here — see `routers/cloud.py`.
 *  The one exception is `download_url` on a model, which is a signed, short-lived, model-scoped URL
 *  the browser fetches **without** an Authorization header (`openModelBytes` below).
 */
import type { ApiClient } from "./client";

/** What `/auth/cloud/status` reports. Never includes a token. */
export interface CloudStatus {
  enabled: boolean;
  linked: boolean;
  site_url: string;
  sub?: string;
  email?: string | null;
  name?: string | null;
  avatar_url?: string | null;
  /** massing.cloud licence vocabulary: free | home | commercial | enterprise. */
  tier?: string;
  tier_label?: string;
  roles?: string[];
  providers?: string[];
  is_admin?: boolean;
  library_access?: boolean;
  linked_at?: string | null;
  last_sync?: string | null;
}

export interface CloudProject {
  id: number | string;
  title: string;
  cloud_project_id?: string | null;
  status: string;
  model_count: number;
  updated?: string | null;
}

export interface CloudModel {
  id: number | string;
  title: string;
  project_id?: number | string | null;
  format: string;
  size_bytes: number;
  version: number;
  cloud_model_id?: string | null;
  thumb_url?: string | null;
  preview_url?: string | null;
  metrics: Record<string, unknown>;
  download_url?: string | null;
  updated?: string | null;
}

/** A refusal the user can act on: 402 = needs a paid plan, 403 = not linked, 409 = plan limit. */
export class CloudError extends Error {
  constructor(readonly status: number, message: string) { super(message); }
  /** True when the fix is "upgrade", which the UI renders as a link rather than an error toast. */
  get needsUpgrade() { return this.status === 402; }
  get notLinked() { return this.status === 403; }
}

async function call<T>(api: ApiClient, path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(api.url(path), {
    ...init,
    headers: { "Content-Type": "application/json", ...api.authHeaders(), ...(init?.headers || {}) },
  });
  if (!res.ok) {
    let detail = "";
    try { detail = ((await res.json()) as { detail?: string }).detail || ""; } catch { /* non-JSON */ }
    throw new CloudError(res.status, detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

/** Where to send the browser to start the massing.cloud sign-in (a full-page navigation, because
 *  the broker must be able to show its own login UI and set its own cookies). */
export function cloudLoginUrl(api: ApiClient): string {
  return api.url("/auth/cloud/login");
}

export function cloudStatus(api: ApiClient) {
  return call<CloudStatus>(api, "/auth/cloud/status");
}

/** Re-read the profile from massing.cloud so a plan upgrade or a role change lands without a
 *  sign-out/sign-in round trip. */
export function cloudRefresh(api: ApiClient) {
  return call<CloudStatus>(api, "/auth/cloud/refresh", { method: "POST" });
}

export function cloudDisconnect(api: ApiClient) {
  return call<{ ok: boolean; linked: boolean }>(api, "/auth/cloud/disconnect", { method: "POST" });
}

export async function cloudProjects(api: ApiClient): Promise<CloudProject[]> {
  const r = await call<{ projects: CloudProject[] }>(api, "/cloud/library/projects");
  return r.projects || [];
}

export function cloudProject(api: ApiClient, id: string | number) {
  return call<CloudProject>(api, `/cloud/library/projects/${encodeURIComponent(String(id))}`);
}

export function cloudModel(api: ApiClient, id: string | number) {
  return call<CloudModel>(api, `/cloud/library/models/${encodeURIComponent(String(id))}`);
}

/** Fetch a model's bytes from its signed `download_url`.
 *
 *  Deliberately a bare `fetch` with **no** auth header and no credentials: the URL already carries a
 *  signed, ~15-minute, model-scoped token, and attaching this app's bearer to a massing.cloud origin
 *  would leak a credential cross-origin to no purpose. */
export async function openModelBytes(model: CloudModel): Promise<Blob> {
  if (!model.download_url) throw new CloudError(404, "this model has no downloadable file");
  const res = await fetch(model.download_url, { credentials: "omit" });
  if (!res.ok) throw new CloudError(res.status, `could not download “${model.title}”`);
  return res.blob();
}

/** Human-readable byte size for the library list. */
export function formatBytes(n: number): string {
  if (!n) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0, v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v >= 10 || i === 0 ? Math.round(v) : v.toFixed(1)} ${units[i]}`;
}
