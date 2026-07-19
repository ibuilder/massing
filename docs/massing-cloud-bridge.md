# massing.cloud licence bridge — integration contract

The self-hosted Massing app can validate a licence key online against **massing.cloud** and read the
authoritative plan. This is **optional and off by default** (offline-first): the tier recorded in
*Settings ▸ Massing licence* is authoritative on its own, so a massing.cloud outage can never lock a
paying operator out of their own app.

App side: [`services/api/src/aec_api/license_cloud.py`](../services/api/src/aec_api/license_cloud.py).
This document is the contract the **massing.cloud WordPress plugin** implements on the other end.

## Configuration (operator, in the app's Settings)

| Setting | Meaning |
| --- | --- |
| `MASSING_CLOUD_ONLINE` | `1` to enable online validation (default `0` = offline) |
| `MASSING_CLOUD_URL` | REST base, default `https://www.massing.cloud/wp-json/massing/v1` |
| `MASSING_CLOUD_SECRET` | shared secret sent as `X-Massing-Secret` (a **secret** field — masked, never returned by the API, never logged) |

The secret is stored only in the operator's app config (DB/env), never in the repo. Rotate it on
massing.cloud if it is ever exposed.

## Endpoint the plugin must expose

```
POST  {MASSING_CLOUD_URL}/validate
Headers:  X-Massing-Secret: <shared secret>     Content-Type: application/json
Body:     { "key": "MASS-XXXX-XXXX-XXXX-XXXX", "instance": "<optional install id>", "app": "massing" }
```

Reject the request with `401` if `X-Massing-Secret` does not match. On success return `200`:

```jsonc
{ "valid": true, "tier": "commercial", "seats": 5, "expires": "2027-01-01",
  "features": { }, "message": "optional human note" }
// or
{ "valid": false, "reason": "revoked" }   // reason ∈ revoked | expired | unknown
```

`tier` must be one of `free | home | commercial | enterprise` (the app degrades an unknown/absent
tier to `free`). `seats`, `expires`, `features`, `message` are optional and passed through for display.

## How the app applies the result

`POST /license/cloud-check` (admin) validates the recorded key and:

- **valid** → writes `tier` to `MASSING_LICENSE_TIER` (the entitlement gates then read the
  cloud-confirmed plan).
- **`valid:false` with a reason** → downgrades the local tier to `free` (a reachable cloud said "no").
- **unreachable / transport error** → **no change** (offline; the recorded tier stands).

The app does not call `/validate` on every request — it caches by applying the tier to Settings, so
provisioning/downgrade is an explicit action (or a scheduled `license.cloud_check` you can wire later).

## Provisioning webhook (massing.cloud side only)

massing.cloud POSTs signed licence events (`provisioned` / `updated` / `revoked`) to its own
`https://api.massing.cloud/hooks/licenses` to provision or tear down models/DBs/seats in real time.
That flow is entirely within massing.cloud and needs nothing from this app.
