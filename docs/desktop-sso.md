# Massing Desktop App — Sign in through massing.cloud (implementation guide)

**Audience:** the agent/developer working in the **Massing desktop app** repo.
**Goal:** add "Sign in with massing.cloud" to the desktop app. After sign-in, the app shows the user's
**name and avatar** and holds a token it can use for authenticated calls.

You do **not** implement any OAuth provider logic. massing.cloud is already a finished OAuth2
**authorization server** (an identity broker). It handles Microsoft / Google / Procore / Autodesk and
username-password behind the scenes. The desktop app only speaks to massing.cloud using the standard
**PKCE + loopback-redirect** flow (RFC 8252, the OAuth best practice for native apps).

The server side already exists and is tested — this guide is the client half.

> Related but separate: [`massing-cloud-bridge.md`](massing-cloud-bridge.md) is the **licence**
> contract against the same host. It is offline-first and off by default, deliberately, so a
> massing.cloud outage can never lock a paying operator out of their own app. Sign-in inherits that
> rule (§9.3) — do not couple the two.

---

## 1. What you're building (the flow)

```
Desktop app                         massing.cloud                    IdP (MS/Google/…)
   │  1. start a local http listener on 127.0.0.1:<port>
   │  2. open the system browser →  /massing-sso/authorize
   │        (client_id, PKCE challenge, redirect_uri=127.0.0.1:<port>, state)
   │                                       │  user signs in (SSO or password) ──→ IdP
   │  3. browser ← 302 → http://127.0.0.1:<port>/callback?code=…&state=…
   │        (your local listener captures the code, checks state)
   │  4. POST /wp-json/massing-sso/v1/token   (code + code_verifier)
   │  5. ← { access_token, refresh_token, expires_in }
   │  6. GET /wp-json/massing-sso/v1/userinfo   (Bearer access_token)
   │  7. ← { sub, name, email, avatar_url, tier, providers }
   │        → render name + avatar in the app window
```

Steps 2 and 3 happen in the user's real browser, so any provider's login, MFA and passkeys all work
without this app knowing about them. Everything else is a normal HTTPS request.

---

## 2. Configuration

| Setting | Value |
|---|---|
| Base URL | `https://massing.cloud` (configurable for staging/self-host) |
| `client_id` | `massing-desktop` (a pre-registered **public** client) |
| `redirect_uri` | `http://127.0.0.1:<port>/callback` — loopback, ephemeral port chosen at runtime |
| `scope` | `profile email` |
| PKCE | **required**, method `S256` |

| Purpose | Method | URL |
|---|---|---|
| Authorize (opens in browser) | GET | `/massing-sso/authorize` |
| Token exchange / refresh | POST | `/wp-json/massing-sso/v1/token` |
| User info | GET | `/wp-json/massing-sso/v1/userinfo` |
| Revoke (sign out) | POST | `/wp-json/massing-sso/v1/revoke` |

> Loopback only: the server accepts `redirect_uri` hosts `127.0.0.1`, `localhost` or `[::1]` on any
> port. If the framework cannot run a loopback listener, ask the massing.cloud maintainer to register
> a custom URI scheme (e.g. `massing://auth`) for the `massing-desktop` client instead.

---

## 3. The HTTP contract (language-agnostic)

### 3a. Authorize — open in the system browser

```
GET https://massing.cloud/massing-sso/authorize
      ?client_id=massing-desktop
      &response_type=code
      &redirect_uri=http://127.0.0.1:52140/callback
      &code_challenge=<base64url(sha256(verifier))>
      &code_challenge_method=S256
      &state=<random>
      &scope=profile+email
```

The browser redirects to `http://127.0.0.1:52140/callback?code=<code>&state=<same random>`. The local
listener must **verify `state` matches** before using `code`. On failure you get
`?error=...&error_description=...` instead.

### 3b. Token — exchange the code

```
POST /wp-json/massing-sso/v1/token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&code=<authorization_code>
&code_verifier=<the original PKCE verifier>
&redirect_uri=http://127.0.0.1:52140/callback
&client_id=massing-desktop
```

200 returns `{ access_token, token_type: "Bearer", expires_in: 28800, refresh_token, scope }`.
Codes are single-use and expire in 120 s. Errors are `400` with `{ error, error_description }`.

### 3c. Userinfo — get the profile

```
GET /wp-json/massing-sso/v1/userinfo
Authorization: Bearer <access_token>
```

200 returns `{ sub, name, email, avatar_url, tier, providers }` — this is what you render.
`401` means missing/expired/revoked: refresh (3d) or re-authenticate.

### 3d. Refresh — before the access token expires

```
POST /wp-json/massing-sso/v1/token
grant_type=refresh_token&refresh_token=<token>&client_id=massing-desktop
```

Same response shape as 3b. **Refresh tokens rotate** — the old one is invalidated, so always persist
the new `refresh_token` from the response. They last 30 days.

### 3e. Sign out — revoke

```
POST /wp-json/massing-sso/v1/revoke
token=<access_or_refresh_token>
```

Then delete the stored tokens locally.

---

## 4. Reference implementation (TypeScript / Node — Electron/Tauri main process)

Dependency-light reference; §3 is the source of truth if you port it. **Read §9 before copying this
into this repo** — two details below do not satisfy gates that exist here.

```ts
import http from 'node:http';
import crypto from 'node:crypto';
import { AddressInfo } from 'node:net';
import { shell } from 'electron';   // Tauri: the shell-open plugin

const BASE = process.env.MASSING_BASE_URL ?? 'https://massing.cloud';
const CLIENT_ID = 'massing-desktop';
const SCOPE = 'profile email';

const b64url = (buf: Buffer) =>
  buf.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

export interface MassingSession { accessToken: string; refreshToken: string; expiresAt: number; }
export interface MassingUser {
  sub: string; name: string; email: string;
  avatar_url: string; tier: string; providers: string[];
}

/** Full interactive login. Resolves once the user finishes in the browser. */
export async function signIn(): Promise<MassingSession> {
  const verifier = b64url(crypto.randomBytes(32));
  const challenge = b64url(crypto.createHash('sha256').update(verifier).digest());
  const state = b64url(crypto.randomBytes(16));

  const { code, redirectUri } = await new Promise<{ code: string; redirectUri: string }>(
    (resolve, reject) => {
      const server = http.createServer((req, res) => {
        const url = new URL(req.url ?? '', 'http://127.0.0.1');
        if (url.pathname !== '/callback') { res.writeHead(404).end(); return; }
        const err = url.searchParams.get('error');
        // Fixed string, never the parameter — see 9.2.
        if (err) { res.writeHead(400).end('Sign-in failed.'); server.close(); reject(new Error(err)); return; }
        if (url.searchParams.get('state') !== state) {
          res.writeHead(400).end('State mismatch.'); server.close();
          reject(new Error('state_mismatch')); return;
        }
        const code = url.searchParams.get('code')!;
        res.writeHead(200, { 'Content-Type': 'text/html' })
           .end('<h2>Signed in to Massing</h2><p>You can close this window.</p>');
        server.close();
        resolve({ code, redirectUri: `http://127.0.0.1:${(server.address() as AddressInfo).port}/callback` });
      });
      server.listen(0, '127.0.0.1', () => {
        const port = (server.address() as AddressInfo).port;
        const redirectUri = `http://127.0.0.1:${port}/callback`;
        const authUrl = new URL(`${BASE}/massing-sso/authorize`);
        authUrl.search = new URLSearchParams({
          client_id: CLIENT_ID, response_type: 'code', redirect_uri: redirectUri,
          code_challenge: challenge, code_challenge_method: 'S256', state, scope: SCOPE,
        }).toString();
        shell.openExternal(authUrl.toString());
      });
      setTimeout(() => { server.close(); reject(new Error('timeout')); }, 5 * 60_000);
    },
  );

  const tok = await postForm(`${BASE}/wp-json/massing-sso/v1/token`, {
    grant_type: 'authorization_code',
    code, code_verifier: verifier, redirect_uri: redirectUri, client_id: CLIENT_ID,
  });
  return toSession(tok);
}

/** Refresh — rotates the refresh token, so persist the new one. */
export async function refresh(session: MassingSession): Promise<MassingSession> {
  const tok = await postForm(`${BASE}/wp-json/massing-sso/v1/token`, {
    grant_type: 'refresh_token', refresh_token: session.refreshToken, client_id: CLIENT_ID,
  });
  return toSession(tok);
}

/** Fetch the profile; auto-refresh once on 401. */
export async function getUser(
  session: MassingSession,
): Promise<{ user: MassingUser; session: MassingSession }> {
  let s = session;
  if (s.expiresAt - 60 < Math.floor(Date.now() / 1000)) s = await refresh(s);
  const call = (t: string) => fetch(`${BASE}/wp-json/massing-sso/v1/userinfo`,
    { headers: { Authorization: `Bearer ${t}` } });
  let res = await call(s.accessToken);
  if (res.status === 401) { s = await refresh(s); res = await call(s.accessToken); }
  if (!res.ok) throw new Error(`userinfo ${res.status}`);
  return { user: (await res.json()) as MassingUser, session: s };
}

export async function signOut(session: MassingSession): Promise<void> {
  await postForm(`${BASE}/wp-json/massing-sso/v1/revoke`, { token: session.refreshToken });
}

async function postForm(url: string, body: Record<string, string>) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json' },
    body: new URLSearchParams(body).toString(),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`${json.error ?? res.status}: ${json.error_description ?? ''}`);
  return json;
}

function toSession(tok: any): MassingSession {
  return {
    accessToken: tok.access_token,
    refreshToken: tok.refresh_token,
    expiresAt: Math.floor(Date.now() / 1000) + Number(tok.expires_in ?? 0),
  };
}
```

Renderer: call `getUser()`, show `user.name` via `textContent`, and set the avatar **through
`safeHref()` — §9.1**. Gate Pro/Enterprise *features* on `user.tier` (but not data — §9.3).

---

## 5. Token storage

- **Never** plain files or `localStorage`. Use the OS secure store: Electron
  `safeStorage.encryptString()` (Keychain / DPAPI / libsecret) or `keytar`; Tauri `stronghold` or
  `keyring`; native Keychain / Credential Manager / libsecret.
- Store the **refresh token** (30 d) securely. The access token (8 h) can live in memory and be
  re-derived by refresh on next launch.
- On every refresh, overwrite the stored refresh token with the new one — they rotate.
- Sign out = call `/revoke`, then delete the stored tokens.

---

## 6. Security requirements (must-haves)

- **PKCE S256 is mandatory** — the server rejects the public client without it. Fresh `code_verifier`
  per sign-in; never reuse or log it.
- **Verify `state`** before using the `code`.
- Bind the listener to **`127.0.0.1` only** (never `0.0.0.0`) and close it after the one callback.
- **No client secret** — this is a public client by design.
- Treat both tokens as secrets: keychain only, never logged, never in telemetry or crash reports.
- Always use the **HTTPS** base URL in production.

---

## 7. Test checklist (against the live broker)

1. `signIn()` opens the browser; after login the app receives tokens.
2. `getUser()` returns the real `name` + `avatar_url`; the avatar renders.
3. Expire or tamper with the access token → `getUser()` auto-refreshes and still works.
4. `signOut()` → a later `getUser()` with the old token returns `401`.
5. Tamper with `state` on the callback → sign-in aborts, no token issued.
6. Wrong/expired `code` → `400 invalid_grant`.

---

## 8. Notes

- First use of a provider auto-creates the account and captures the avatar; later logins are instant.
- `avatar_url` is an HTTPS image URL on massing.cloud — but see §9.1 before putting it in an `<img>`.
- Keep `MASSING_BASE_URL` configurable for offline/self-host; nothing else changes.

---

## 9. Integrating in THIS repo — what the portable guide does not cover

The guide above is written to be portable. This repo has gates that portable code does not know about,
and two of them reject the obvious implementation. Checked against the gates as they currently stand.

### 9.1 The avatar must go through `safeHref()` — `hrefGuard` has a ZERO baseline

Setting the avatar from `user.avatar_url` directly fails
[`apps/web/src/ui/hrefGuard.test.ts`](../apps/web/src/ui/hrefGuard.test.ts). That gate is not a
ratchet and allows no exceptions: it matches "a URL field read off a data object assigned to a URL
attribute", which is exactly this shape. Evaluated against the gate's own patterns:

```
img.src = user.avatar_url;                  ->  FAILS
el.setAttribute("src", user.avatar_url);    ->  FAILS
img.src = safeHref(user.avatar_url);        ->  passes
```

Use `safeHref` from [`apps/web/src/ui/feedback.ts`](../apps/web/src/ui/feedback.ts) — a scheme
allowlist that returns `"#"` for anything not permitted. This is not ceremony: `avatar_url` arrives
from another system, and escaping cannot defend an attribute — `javascript:` has nothing to escape,
and escaping a DOM property corrupts a query string while looking defended.

Render `user.name` with `textContent`, never `innerHTML` (`innerHtmlGuard.test.ts`).

### 9.2 Do not echo the callback's `error` into the response body

The reference prints a fixed `'Sign-in failed.'` rather than interpolating `error`, deliberately.
Anything running on the machine can hit `http://127.0.0.1:<port>/callback?error=<payload>` during the
sign-in window, and reflecting that into an HTML response is a local XSS on a page the user is looking
at. The `state` check does not help — it runs *after* the error branch. Log the real value; do not
render it.

### 9.3 A massing.cloud token is not this app's session

The app has its own auth in [`services/api/src/aec_api/rbac.py`](../services/api/src/aec_api/rbac.py)
with its own bearer tokens, project roles and step-up assertions. A massing.cloud `access_token`
identifies a **massing.cloud account**, not a Massing project role.

- Do not feed it to `current_user`, and do not let it satisfy `require_role`.
- `tier` may gate a Pro **feature**; it must not gate **data**. Project-scoped access stays with
  `require_role` — that is the boundary the whole authorization test suite is built around.
- Sign-in stays **optional**, for the same reason the licence bridge is offline-first and off by
  default: an outage at massing.cloud must never lock an operator out of their own app.
