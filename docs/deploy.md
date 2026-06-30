# Phase 7 — Hardening & deployment

## Stack (docker-compose)
- `postgres` — primary store (projects/members/topics/comments/viewpoints/attachments/audit).
- `minio` — object storage (source IFC, `.frag` tiles, `props.json`, attachments).
- `api` — FastAPI; image bundles `services/data` so exports/clash/validate/drawings work.
- `web` — Vite build served by nginx (COOP/COEP headers for web-ifc threading).
- `converter` — Node IFC→Fragments, run as a job (`docker compose run`).

```bash
# core stack (api + web + postgres + minio)
docker compose --profile full up --build
#   web → http://localhost:8080    api → http://localhost:8000    minio console → :9001

# convert a model (drop it in ./data first)
docker compose --profile tools run --rm converter /data/model.ifc /data/model.frag

# enforce project roles
AEC_RBAC=1 docker compose --profile full up --build

# smoke test a running stack
API=http://localhost:8000 bash scripts/smoke-stack.sh samples/school_str.ifc
```

## Configuration (env)
| Var | Service | Purpose |
|---|---|---|
| `DATABASE_URL` | api | `postgresql+psycopg://…` (sqlite if unset, dev) |
| `S3_ENDPOINT` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` / `S3_BUCKET` | api | MinIO/S3 object storage; unset → local `STORAGE_DIR` |
| `AEC_RBAC` | api | `1` enforces project-scoped roles |
| `AEC_API_KEY` | api | bearer treated as admin (service-to-service) |

## Auth & roles (RBAC)
Project-scoped roles, least→most: **viewer < reviewer < editor < admin** (`rbac.py`).
- viewer: read models/properties/issues/drawings/exports
- reviewer: + create/comment topics & viewpoints, attachments (RFIs, markup)
- editor: + author IFC (`/edit`, `/publish`), clash-with-topics, BCF import
- admin: + project settings, manage members
The project creator becomes admin. Caller identified by `X-User` (swap for your IdP/JWT in
prod). Off by default (`AEC_RBAC` unset) so local dev stays open. Verified: `test_rbac.py`.

**Accounts & identity** (independent of `AEC_RBAC`): the built-in auth issues signed bearer
tokens + an httpOnly cookie (`auth.py`). The first `/auth/register` bootstraps a global **admin**;
after that, admins manage accounts via `/auth/users` (create / list / set role / activate /
deactivate / reset password) — surfaced in the web app under the account menu → *Manage users*.
Users change their own password at `/auth/password` (account menu → *Change password*).
Deactivating an account blocks new logins **and** invalidates its existing tokens immediately;
the last active admin can't be removed. Verified: `test_auth.py`.

## Object storage & streaming
`storage.py` has Local and S3 (boto3) backends behind one interface incl. byte-range reads.
`.frag` tiles and attachments are served with **HTTP range requests** (`serving.py`): `206
Partial Content`, `Accept-Ranges`, `Content-Range`, immutable cache headers — so the viewer/
CDN stream large models. Verified: `test_serving.py` (200 full / 206 ranged / 416).

> Note: `/publish` reconvert spawns the Node converter; in the container that step is
> best-effort (reindex always runs). For prod, run conversion via the `converter` service
> and write the `.frag` to MinIO under `<project_id>/model.frag`.

## Audit & backups
Every write records an `AuditLog` row (actor, action, method, path, topic, detail) — RFIs/
punchlist are contractual records. The DB + attachments + uploaded source IFCs are the system
of record; `.frag` tiles are reproducible from source IFC.

**Backup/restore runbook** (`scripts/backup.sh` / `scripts/restore.sh`, run from the repo root
with the stack up; Windows: Git Bash or WSL):

```bash
# back up DB (pg_dump) + MinIO objects + uploaded source IFCs → one timestamped tarball
./scripts/backup.sh                      # → ./backups/aec-backup-<ts>.tgz

# schedule it (crontab): nightly at 02:00, then prune backups older than 14 days
0 2 * * *  cd /srv/massing && ./scripts/backup.sh >> /var/log/aec-backup.log 2>&1
0 3 * * *  find /srv/massing/backups -name 'aec-backup-*.tgz' -mtime +14 -delete

# restore (DESTRUCTIVE — overwrites DB, objects, IFCs; stops the app while restoring)
./scripts/restore.sh ./backups/aec-backup-<ts>.tgz
```

`backup.sh` logically dumps Postgres (`pg_dump --clean`) and tars the MinIO + IFC volumes via a
throwaway `alpine` container (`--volumes-from`, so no volume-name or S3-credential coupling).
Verify a backup by restoring into a throwaway compose project and hitting `/health` + a known
project before trusting it. Keep backups off-box (e.g. `aws s3 cp`, `rclone`) for DR.

## Deploy to a cloud VM with HTTPS (turnkey demo / production)

The base stack runs anywhere Docker does. For a public, TLS-secured demo, layer the
production overlay — it adds a **Caddy** reverse proxy that fetches + renews a Let's Encrypt
cert automatically, enforces auth (`AEC_RBAC=1`), and sets restart policies.

```bash
# 1. a small VM (1–2 vCPU, 2–4 GB) with Docker + a DNS A record for your domain → the VM IP
# 2. firewall: allow only 80 + 443
sudo ufw allow OpenSSH && sudo ufw allow 80,443/tcp && sudo ufw enable

# 3. clone + configure secrets (REQUIRED in prod)
git clone https://github.com/ibuilder/massing.git && cd Massing
cp .env.example .env       # set POSTGRES_PASSWORD, S3_ACCESS_KEY/SECRET, AEC_API_KEY, AEC_AUTH_SECRET

# 4. bring it up behind Caddy (auto-HTTPS for $DOMAIN)
DOMAIN=app.example.com docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    --profile full up -d --build

# 5. create the first admin (bootstraps as admin), then sign in at https://app.example.com
curl -s -X POST https://app.example.com/api/auth/register \
    -H "Content-Type: application/json" -d '{"username":"admin","password":"<strong-password>"}'

# optional: seed a demo project across all relation chains
DOMAIN=app.example.com docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    --profile full --profile seed run --rm seed
```

Caddy is the only public entrypoint (web/api/postgres/minio stay on the Docker network — keep
8000/8080/5432/9000 off the public firewall). Cookie auth + the SSE feed + downloads all work
because everything is same-origin behind the proxy. Managed hosts (Fly.io, Render, Railway)
work too — run the same images, swap MinIO for their S3-compatible bucket + managed Postgres,
and front the web service with their TLS.

> **GitHub note:** Pages is static-only and can't host this stack (it needs the API + Postgres
> + MinIO). Pages can serve the marketing page (`docs/index.html`) and, with extra setup, a
> viewer-only build; the full app needs a Docker host as above.

## Free single-project desktop app (.exe)
The whole platform runs in **one process** for a single operator — FastAPI serving both the API and
the web SPA on `127.0.0.1:8765`, backed by **SQLite + local files** (no Docker / Postgres / MinIO),
in **local mode** (no login — the operator owns the one site). This is the "free, Bluebeam-style"
build; projects are saved/opened as portable `.mmproj` bundles (Open/Save menu).

- **Run from source:** `python -m aec_api.desktop` (from `services/api`, with the venv) — builds the
  web first with `npm run build:desktop` so the SPA calls the same-origin API (`.env.desktop` sets
  `VITE_API_URL=`).
- **Package the .exe:** `services/api/build-desktop.ps1` runs the desktop web build, then PyInstaller
  (`desktop.spec`) into `services/api/dist_desktop/AEC-BIM/AEC-BIM.exe`. The bundle includes the SPA
  (`web/`), the 68 module definitions (`modules/`), and ifcopenshell. Data lives under
  `%LOCALAPPDATA%\AEC-BIM` (override with `AEC_DATA_DIR`); uninstall = delete that folder + the app.
- **Env knobs:** `AEC_PORT` (8765), `AEC_OPEN_BROWSER` (1), `AEC_DATA_DIR`, `AEC_HOST`. The frozen
  build resolves the bundled SPA + module catalog via `_MEIPASS` (`AEC_WEB_DIST` / `AEC_MODULES_DIR`).

A native-window wrapper (Tauri, below) can host this same backend; the PyInstaller `.exe` already
ships a complete, double-clickable app on its own (it opens the system browser).

### Auto-update
- **Update check (built-in, no setup):** on launch the app checks the project's GitHub *Releases*
  for a newer version than the one baked in at build (`VITE_APP_VERSION` ← `package.json`), and shows
  a dismissible banner with a download link; there's also a manual "Check for updates" in Settings
  (`apps/web/src/ui/update.ts`). Works for the `.exe`, the Tauri build, and the browser. It links to
  the new installer rather than hot-swapping (an OS can't replace a running `.exe` in place).
- **Silent self-install (Tauri, optional):** for true in-app install, enable the Tauri updater —
  it requires a signing keypair:
  1. `npx @tauri-apps/cli signer generate -w aec.key` → keep the **public** key, guard the private one.
  2. Put the public key in `tauri.conf.json` under `plugins.updater.pubkey` and set
     `bundle.createUpdaterArtifacts: true` + `plugins.updater.endpoints` to the release `latest.json`.
  3. Add repo secrets `TAURI_SIGNING_PRIVATE_KEY` + `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` and pass them
     to the `tauri-action` step (tauri-action then emits the signed updater bundles + `latest.json`).
  Not enabled by default because `createUpdaterArtifacts` makes the build *require* the signing key —
  so flip it on only once the secret is configured (otherwise the release build fails).

## Mobile apps (Capacitor — iOS / Android)
The same web build (`dist`) wraps into native iOS/Android apps via Capacitor (`capacitor.config.ts`,
appId `com.ibuilder.aecbim`). A phone has no local Python backend, so a mobile build must target a
hosted API.

1. **Point at your API:** edit `apps/web/.env.mobile` → `VITE_API_URL=https://your-cloud-api`
   (blank = viewer-only offline build; the portal/proforma need the API).
2. **Build the web + sync:** `npm run build:mobile` then `npx cap sync` (or the one-shot
   `npm run mobile:android` / `npm run mobile:ios`).
3. **Add a platform once:** `npx cap add android` / `npx cap add ios` (folders are gitignored;
   regenerate anytime).
4. **Build the binary** (your toolchain): Android needs the **Android SDK + JDK** (`cap open android`
   → Gradle build/APK/AAB); iOS needs **macOS + Xcode** (`cap open ios`).
5. **Validate on device:** the model viewer uses threaded WASM (web-ifc, SharedArrayBuffer) — confirm
   it runs in the device WebView before relying on 3D; the portal/proforma/2D work everywhere.
6. **Store submission:** Apple Developer + Google Play accounts (signing + listings are store-side).

Scaffolding is wired and verified (`cap add android` syncs the web build); the binary build,
on-device WASM validation, and store accounts are the external pieces.

## Desktop installers (Tauri) & code signing
`.github/workflows/desktop.yml` builds Windows / macOS (arm64) / Linux installers. Push a tag
(`v0.1.0`) for a draft Release; run it manually (Actions → Desktop release → Run workflow) for
artifact-only smoke builds. Without the secrets below, builds are **unsigned** (Gatekeeper /
SmartScreen warn on first launch) — everything still works; add the secrets to sign + notarize.

**Native window + bundled backend (sidecar).** The Tauri shell ([`src/lib.rs`](../apps/web/src-tauri/src/lib.rs))
spawns the Python backend as a sidecar (`binaries/aec-bim-server`, declared in `tauri.conf.json`
`externalBin`), waits for `127.0.0.1:8765`, then points the WebView at it — so the installed app is
the full platform (API + SPA + SQLite, local mode), same-origin, fully offline, in a native window.
CI builds that sidecar per-platform with `services/api/build_sidecar.py` (PyInstaller can't
cross-compile, so each runner builds its own; the binary is named with the Rust target triple).
The shell's `beforeBuildCommand` is `npm run build:desktop` so the bundled SPA targets the
same-origin API. To build locally: `npm run build:desktop` → `python services/api/build_sidecar.py`
→ `npm --prefix apps/web run tauri build` (needs the Rust toolchain).

| Platform | Repo secrets | Notes |
|---|---|---|
| macOS | `APPLE_CERTIFICATE` (base64 of a Developer ID `.p12`), `APPLE_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY` (e.g. `Developer ID Application: Name (TEAMID)`), `APPLE_ID`, `APPLE_PASSWORD` (app-specific password), `APPLE_TEAM_ID` | `tauri-action` imports the cert and notarizes automatically when all are set. |
| Windows | `WINDOWS_CERTIFICATE` (base64 of an Authenticode `.pfx`), `WINDOWS_CERTIFICATE_PASSWORD` | The workflow imports the PFX and writes its thumbprint into `tauri.conf.json` before building. For an EV/HSM or Azure Trusted Signing cert, replace that step with the vendor's `signtool` flow. |
| Linux | — | `.deb`/`.AppImage` are not signed; distribute over HTTPS / via checksums. |

Generate `APPLE_CERTIFICATE` / `WINDOWS_CERTIFICATE` with `base64 -w0 cert.p12` (Linux) or
`[Convert]::ToBase64String([IO.File]::ReadAllBytes("cert.pfx"))` (PowerShell), and add them under
Settings → Secrets and variables → Actions. The workflow then signs automatically on the next tag —
**no code change needed** (the import + thumbprint + notarize steps are already wired and guarded so
unsigned builds stay green until the secrets exist).

**Where to get the certs (the only external piece):**
- **Windows** — an Authenticode code-signing cert from a CA (DigiCert, Sectigo, SSL.com; OV ≈
  $200–400/yr). OV still shows a SmartScreen prompt until it earns reputation; an **EV** cert (HSM/
  token) or **Azure Trusted Signing** (~$10/mo, cloud, no physical token) clears SmartScreen
  immediately — for those, swap the PFX-import step for the vendor's `signtool`/Trusted-Signing action.
- **macOS** — Apple Developer Program ($99/yr) → a **Developer ID Application** cert (export `.p12`)
  + an app-specific password for notarization. Fills all six `APPLE_*` secrets above.
- **Linux** — `.deb`/`.AppImage` aren't OS-signed; publish SHA-256 checksums (GitHub shows asset
  digests) and/or GPG-detach-sign if your channel needs it.

## Observability
`GET /metrics` exposes Prometheus text (request counts + latency summary by method/route
template, in-flight gauge, uptime) — point a Prometheus scrape at it. Each request also emits
a structured JSON access line on the `aec.access` logger (method/route/status/dur_ms) for log
aggregation. Metrics are per-process; with multiple uvicorn workers use a multiprocess
collector or scrape each worker. (Endpoint is unauthenticated — keep it on an internal network
or front it with auth at the proxy.)

## Offline / jobsite
web-ifc WASM + the Fragments worker are bundled into the web image; tiles serve from your own
MinIO. No external CDN — the viewer runs fully offline.

## Licensing — see ../LICENSE-NOTES.md
Bonsai/Blender GPL (separate process), IfcOpenShell LGPL, That Open MIT-style.
