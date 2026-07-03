# Production go-live checklist

The runnable, copy-paste gate for exposing a deployment. Companion to
[deploy.md](deploy.md) (how to stand the stack up) and [operations.md](operations.md)
(backups, upgrades, monitoring). Work top to bottom; don't expose the stack until the
preflight passes.

## 1. Stand up the stack

```bash
# on the VM (Docker + a DNS A record for $DOMAIN pointing at it, ports 80/443 open)
export DOMAIN=app.example.com
export AEC_AUTH_SECRET="$(openssl rand -hex 48)"      # store it in your secret manager
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile full up -d --build
```

## 2. Run the preflight (the go/no-go gate)

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm api python /app/scripts/validate_prod_config.py
```

Exit 0 required. It asserts, among others:

| Check | Why |
|---|---|
| `AEC_RBAC=1` | without it, every authenticated user sees every project |
| `AEC_AUTH_SECRET` set (long) | default secret ⇒ forgeable tokens |
| `AEC_REQUIRE_SECRET=1` | missing secret is a boot failure, not a silent risk |
| `AEC_TRUST_XUSER` unset | X-User header impersonation is dev-only |
| `AEC_COOKIE_SECURE=1` | auth cookie never travels over plain HTTP |
| `AEC_CSP=1`, `AEC_HSTS=1` | strict CSP + HSTS behind TLS |
| Redis wired when workers > 1 + rate limit on | otherwise the limit is per-worker |
| non-default Postgres/MinIO credentials | obvious, and checked anyway |

The API also **fail-fasts at boot** on Postgres without RBAC or with the default secret
(`AEC_ALLOW_OPEN=1` is the explicit opt-out for intentionally-open internal deployments).

## 3. Never do in production

- **Never run the demo seed** (`--profile seed` / `seed_demo.py`) against production.
  The script refuses when the target already has projects; don't `--force` it.
- Never expose ports 8000/8080/5432/9000 directly — only Caddy's 80/443
  (`ufw allow 80,443/tcp`, deny the rest).
- Never set `AEC_TRUST_XUSER=1` or `AEC_ALLOW_OPEN=1` outside a lab.

## 4. First-day operations

- **Backups:** schedule `scripts/backup.sh` (pg_dump + MinIO + IFC dir) daily; do one
  restore drill into a scratch stack before go-live (see operations.md).
- **Monitoring:** scrape `/metrics` (Prometheus text). Alert on
  `http_responses_by_class_total{class="5xx"}` rate and `/ready` failures.
  Watch the `aec.publish` / `aec.autosync` loggers for conversion/sync failures.
- **Users & roles:** create the first admin via `AEC_ADMIN_EMAILS`; grant per-project
  roles (viewer < reviewer < editor < admin) — nobody sees a project they're not a member of.
- **Host pinning (optional):** set `AEC_ALLOWED_HOSTS=app.example.com,localhost`
  (localhost keeps container healthchecks working).

## 5. Known limits (accepted, documented)

- JWT tokens have no revocation list — compromise remedy is rotating `AEC_AUTH_SECRET`
  (invalidates ALL sessions) or waiting out the TTL.
- Presence/collaboration state is per-worker (cosmetic at multi-worker scale).
- The `/metrics` counters are per-process; scrape all workers or run single-worker
  behind the proxy if you need exact totals.
- Background publish runs on daemon threads (deliberate: no Celery for the self-hosted
  mission); an interrupted publish reports `error` after 15 min staleness.
