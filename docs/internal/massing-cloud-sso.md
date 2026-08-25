# massing.cloud SSO + project library — integration notes

Internal notes for the CLOUD-SSO / CLOUD-LIBRARY work. The site-side contract is
massing.cloud `docs/18-sso-and-desktop-auth.md`, `docs/19-desktop-sso-client-implementation.md`
and `docs/31-massing-app-integration.md`; this file records **what we built against it, what we
verified rather than assumed, and the one thing the site still owes us.**

## What this adds

massing.cloud becomes an **identity broker** for this app: the user signs in once on the site,
picking Microsoft / Google / Procore / Autodesk / password there, and this deployment holds **no
provider secret at all**. If their plan is anything but Free, their massing.cloud project vault
becomes browsable and openable from inside the app.

| Piece | Where |
|---|---|
| PKCE broker client | `services/api/src/aec_api/massing_cloud_auth.py` |
| Vault (library) client | `services/api/src/aec_api/massing_cloud_vault.py` |
| Routes | `services/api/src/aec_api/routers/cloud.py` |
| Link table | `CloudIdentity` in `services/api/src/aec_api/models.py` |
| Browser client | `apps/web/src/api/cloud.ts` |
| Identity chip | `apps/web/src/account/accountChip.ts` |
| Profile & settings | `apps/web/src/account/profileSettings.ts` |
| Library browser | `apps/web/src/account/cloudLibrary.ts` |
| Test | `services/api/test_massing_cloud_sso.py` |

## Turning it on

No secret to configure — the app is a registered **public** client and PKCE replaces the secret.

```
MASSING_CLOUD_SSO_ENABLED=1
MASSING_CLOUD_SITE_URL=https://www.massing.cloud     # default
MASSING_CLOUD_SSO_CLIENT_ID=massing-desktop          # default, already registered site-side
MASSING_CLOUD_ROLE_SYNC=1                            # default
MASSING_CLOUD_ADMIN_ROLES=administrator,editor       # default
```

The redirect URI is this app's own callback, `{api}/auth/cloud/callback`. For a normal desktop /
self-hosted install that is a loopback address (`http://127.0.0.1:8093/auth/cloud/callback`), which
the `massing-desktop` public client already allows. **A hosted deployment must have its https
callback registered site-side** via the `massing_sso_clients` filter — loopback-only is the default.

## Three decisions worth knowing about

**1. The code exchange happens on our server, not in the browser.** Doc 31 describes a native app
doing the exchange itself. We do it server-side for three reasons: the cloud refresh token is good
for 30 days and has no business in `localStorage`; the Vault API is then reachable without
massing.cloud having to CORS-allow this origin; and it reuses the existing session/RBAC/audit layer
instead of running a second identity system in the client. PKCE requires no client secret, so
nothing about being a public client is compromised by doing it from the server.

**2. The PKCE verifier travels in a cookie, never in `state`.** `state` is echoed by the broker
through the user agent. An attacker who can observe the redirect would hold the code *and* the
verifier — precisely what PKCE exists to prevent. `auth.seal_pkce` / `auth.open_pkce` HMAC-seal the
verifier into an HttpOnly `SameSite=Lax` cookie scoped to `/auth/cloud`, bound to that specific
`state` so it cannot be replayed against another attempt.

**3. The two tier vocabularies must not be crossed — this one nearly shipped as a bug.**
`licensing.TIER_ORDER` is `free | home | commercial | enterprise`, which is exactly what
massing.cloud sends. `tiers.TIERS` is `free | pro | enterprise`, the per-user entitlement seam on
`User.tier`. Running a cloud tier through `tiers.normalize` maps **`commercial` → `free`**, because
`commercial` is not in that tuple — a paying customer silently told they have no library.
`massing_cloud_auth.normalize_tier` normalises against `licensing`; `app_tier_for` converts for
storage (`home`/`commercial` → `pro`). Asserted in the test.

## Roles — the one open dependency on the site

**`userinfo` does not return a role.** Verified against the plugin source
(`plugin/massing-sso/includes/class-broker.php::userinfo`), not the docs: the response is exactly
`{sub, name, email, avatar_url, tier, providers}`. There is no `role` or `roles` key anywhere in
the broker.

So the requirement *"an admin or editor on massing.cloud authenticates as an admin in the app"* is
**built here and inert until the site publishes roles**. `roles_from_userinfo` accepts `roles: []`,
`role: "…"` or `wp_roles`, lower-cases them, and returns `[]` when none are present; `is_cloud_admin`
returns False on `[]`, so the failure mode is *no elevation*, never accidental elevation.

The site already has the filter this needs. Adding it is a few lines in a site mu-plugin:

```php
add_filter( 'massing_sso_userinfo', function ( array $data, int $user_id ) {
    $user = get_userdata( $user_id );
    $data['roles'] = $user ? array_values( (array) $user->roles ) : array();
    return $data;
}, 10, 2 );
```

Scope it if you would rather not publish every role — `array_values( array_intersect( (array)
$user->roles, [ 'administrator', 'editor' ] ) )` sends only the two that mean anything to us.

**Once roles arrive, the mapping is two-way.** Losing `editor` on the site drops the elevation here
on the next `/auth/cloud/refresh` or sign-in, and disconnecting removes it entirely. A one-way map
would leave a live admin behind after the role was revoked, which is the failure that actually
matters. Only cloud-linked accounts are touched, so a local admin is never demoted by this path.

**Why this provider is allowed to grant admin at all.** `routers/auth.py` carries a standing rule —
*"Regular SSO users are never platform admins"* — and it is deliberately kept for the four direct
IdPs in `oauth.py`: a Google account proves an email, not a relationship to this product. The
massing.cloud broker is different in kind because it is first-party — the role it reports is the
role the operator granted on their own site. `MASSING_CLOUD_ROLE_SYNC=0` turns the coupling off and
falls back to `AEC_ADMIN_EMAILS`.

## Admin is a section, not a console

The old account dropdown carried four admin-only entries (Manage users, Audit log, Errors, Data
connections). Those are now the **Administration section of the profile panel**, present only when
the account carries the capability. The user's framing was that an "admin mode" should not really
exist and its settings belong in a user's profile — this is that, without deleting a capability the
product still needs. A non-admin and an admin now see the same panel; the admin's has one section
more. `profileSettings.test.ts` asserts exactly that, including that the admin *actions* are not
built at all for a non-admin (a hidden tab whose body still rendered would leak the buttons).

## What is deliberately NOT here

**Saving back to the cloud.** Doc 31 §3 is an open joint decision: the site's `POST /models` records
a **pointer** (`storage_key`) and assumes the bytes already live in storage. A recent site commit
adds a `.mass` binary upload endpoint, but this app has no `.mass` container writer yet, so there is
nothing to push — wiring a save button now would record a pointer to nothing.

An earlier draft kept `save_model` / `delete_model` wrappers in `massing_cloud_vault.py` "ready for
later". `test_dead_code_population` caught them — two public functions with no caller anywhere — and
they were **removed rather than allowlisted**. That gate's own history is the argument: its
population was corrected 877 → 35 → 13, and eight of the survivors turned out to be live symbols, so
it is not a rule to argue with from the comfort of having just written the code. Re-adding four lines
when the writer lands costs nothing; code that is present, never exercised against a live endpoint,
and believed to work is a liability.

**Opening `.mass`.** `openCloudModel` in `main.ts` accepts `.ifc` and `.frag` and refuses anything
else explicitly, so the library says "can't be opened here yet" rather than handing an unknown
container to the IFC loader.

**Deep links.** Doc 31 §4 (`massing://open?…` and `{app_url}/open?license=…&project=…`) is not
implemented.
