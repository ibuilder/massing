/**
 * Account / auth / admin UI — sign-in (password + SSO) and reset, the account dropdown, self-service
 * password change, platform-admin user management + audit log, and project-member management.
 * Extracted from main.ts (round 2). buildAuthControl() is called once at startup with a small deps
 * object; everything else is internal. The Data-connections admin modal is lazily imported on demand.
 *
 * All modals use the shared modalShell (Esc-to-close, focus trap, dialog ARIA) — including sign-in,
 * which previously hand-rolled its own overlay and so lacked that behaviour.
 */
import type { ApiClient, AccountUser, AuditEntry, ProjectMember, ProjectRole } from "../api/client";
import { modalShell, confirmModal } from "../ui/modal";
import { askText } from "../ui/prompt";
import { escapeHtml, toast } from "../ui/feedback";

export interface AccountDeps {
  api: ApiClient;
  toolbar: HTMLElement;
  statusEl: HTMLElement;
  getProjectId: () => string | null;
  getIsProjectAdmin: () => boolean;
  openSettings: () => void;        // main owns settingsModal (tied to viewer settings state)
}

let D: AccountDeps;
const PROJECT_ROLES = ["viewer", "reviewer", "editor", "admin"] as const;
const PARTY_ROLES = ["", "GC", "Owner", "OwnersRep", "Consultant", "Subcontractor"];

/** Build (and insert) the toolbar sign-in / account control. Call once at startup. */
export async function buildAuthControl(deps: AccountDeps): Promise<void> {
  D = deps;
  const { api, toolbar, statusEl } = D;
  const el = document.createElement("button");
  el.className = "tool-btn"; el.style.marginLeft = "6px"; el.dataset.tour = "account";
  if (api.authed) {
    let name = "account", platformAdmin = false, tier = "free";
    try {
      const m = await api.me();
      if (m.authenticated) { name = m.username; platformAdmin = !!m.platform_admin; tier = m.tier || "free"; }
      else api.setToken("");
    } catch { /* keep token; offline */ }
    el.textContent = `${name} ▾`; el.title = "Account";
    el.onclick = () => accountMenu(el, platformAdmin, tier);
  } else {
    el.textContent = "Sign in"; el.title = "Sign in";
    el.onclick = loginModal;
  }
  toolbar.insertBefore(el, statusEl);
}

function loginModal() {
  const { card, msg, close } = modalShell("Sign in");
  msg.style.color = "var(--err)";
  const u = document.createElement("input"); u.placeholder = "username"; u.className = "portal-filter";
  const p = document.createElement("input"); p.type = "password"; p.placeholder = "password"; p.className = "portal-filter";
  const row = document.createElement("div"); row.style.cssText = "display:flex;gap:8px;justify-content:flex-end";
  const cancel = document.createElement("button"); cancel.className = "tool-btn"; cancel.textContent = "Cancel"; cancel.onclick = close;
  const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Sign in";
  const submit = async () => {
    if (!u.value.trim() || !p.value) { msg.textContent = "enter a username and password"; return; }
    try {
      const r = await D.api.login(u.value.trim(), p.value);
      if (r.mfa_required && r.mfa_token) { close(); mfaChallengeModal(r.mfa_token); return; }
      if (r.token) { D.api.setToken(r.token); close(); location.reload(); }
    } catch { msg.textContent = "invalid username or password"; }
  };
  go.onclick = () => void submit();
  p.onkeydown = (e) => { if (e.key === "Enter") void submit(); };
  const resetLink = document.createElement("a");
  resetLink.textContent = "Have a reset token?"; resetLink.href = "#";
  resetLink.style.cssText = "font-size:12px;color:var(--muted);align-self:flex-start";
  resetLink.onclick = (e) => { e.preventDefault(); close(); resetModal(); };
  row.append(cancel, go); card.append(u, p, msg, row, resetLink);
  // SSO buttons (only the providers configured on the server), shown above the password form
  void D.api.authProviders().then(({ providers }) => {
    if (!providers.length) {
      // no OAuth configured — tell the operator SSO is available rather than silently hiding it
      const hint = document.createElement("div"); hint.className = "meta";
      hint.style.cssText = "margin-top:8px;font-size:11px";
      hint.innerHTML = "Single sign-on (Google · Microsoft · Procore) is supported — set the "
        + "<code>AEC_OAUTH_*</code> client IDs on the server to show the buttons here.";
      card.appendChild(hint);
      return;
    }
    const wrap = document.createElement("div"); wrap.style.cssText = "display:flex;flex-direction:column;gap:6px";
    for (const pv of providers) {
      const b = document.createElement("button"); b.className = "file-btn";
      b.textContent = `Continue with ${pv.label}`;
      b.onclick = () => { window.location.href = D.api.url(`/auth/oauth/${pv.id}/login`); };
      wrap.appendChild(b);
    }
    const div = document.createElement("div"); div.className = "meta"; div.textContent = "— or sign in with a password —";
    div.style.cssText = "text-align:center;margin:4px 0";
    card.insertBefore(div, u); card.insertBefore(wrap, div);
  }).catch(() => {});
}

/** Login step 2 — the account has MFA on: enter a 6-digit authenticator code (or a recovery code). */
function mfaChallengeModal(mfaToken: string) {
  const { card, msg, close } = modalShell("Two-factor authentication");
  msg.style.color = "var(--err)";
  const hint = document.createElement("div"); hint.className = "meta";
  hint.textContent = "Enter the 6-digit code from your authenticator app (or a recovery code).";
  const code = document.createElement("input"); code.placeholder = "123456"; code.className = "portal-filter";
  code.autocomplete = "one-time-code"; code.inputMode = "numeric";
  const row = document.createElement("div"); row.style.cssText = "display:flex;gap:8px;justify-content:flex-end";
  const cancel = document.createElement("button"); cancel.className = "tool-btn"; cancel.textContent = "Cancel"; cancel.onclick = close;
  const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Verify";
  const submit = async () => {
    if (!code.value.trim()) { msg.textContent = "enter your authentication code"; return; }
    try { const r = await D.api.mfaVerify(mfaToken, code.value.trim()); D.api.setToken(r.token); close(); location.reload(); }
    catch { msg.textContent = "invalid or expired code — try again"; }
  };
  go.onclick = () => void submit();
  code.onkeydown = (e) => { if (e.key === "Enter") void submit(); };
  row.append(cancel, go); card.append(hint, code, msg, row); code.focus();
}

/** Manage two-factor auth for the signed-in user: enroll (QR + code), view recovery status, disable. */
async function mfaModal() {
  const { card, msg, close } = modalShell("Two-factor authentication");
  msg.style.color = "var(--err)";
  const body = document.createElement("div"); body.style.cssText = "display:flex;flex-direction:column;gap:8px";
  card.append(body);
  const render = async () => {
    body.textContent = "Loading…";
    const st = await D.api.mfaStatus().catch(() => null);
    body.textContent = "";
    if (!st) { body.textContent = "Could not load MFA status."; return; }
    if (st.enabled) {
      const on = document.createElement("div"); on.className = "meta";
      on.innerHTML = `✅ <b>Enabled</b> · ${st.recovery_remaining} recovery code(s) remaining`;
      const off = document.createElement("button"); off.className = "tool-btn"; off.textContent = "Disable MFA…";
      off.onclick = async () => {
        const pw = await askText("Disable MFA", { label: "Confirm your password:", password: true });
        if (pw == null) return;
        const cd = await askText("Disable MFA", { label: "Enter a current authenticator or recovery code:" });
        if (cd == null) return;
        try { await D.api.mfaDisable(pw, cd); toast("Two-factor auth disabled", "info"); await render(); }
        catch { msg.textContent = "password + a valid code are required to disable MFA"; }
      };
      body.append(on, off);
      return;
    }
    // not enabled → enrollment flow
    const start = document.createElement("button"); start.className = "file-btn"; start.textContent = "Set up authenticator app";
    start.onclick = async () => {
      const s = await D.api.mfaSetup().catch(() => null);
      if (!s) { msg.textContent = "could not start MFA setup"; return; }
      body.textContent = "";
      const steps = document.createElement("div"); steps.className = "meta";
      steps.innerHTML = "1. Add this key to your authenticator app (Google Authenticator, 1Password, Authy…):";
      const key = document.createElement("code"); key.textContent = s.secret;
      key.style.cssText = "display:block;padding:6px 8px;background:var(--panel-2,#f4f4f4);border-radius:6px;word-break:break-all;user-select:all";
      const uri = document.createElement("div"); uri.className = "meta";
      uri.innerHTML = `<a href="${escapeHtml(s.otpauth_uri)}">Open in an authenticator</a> · then enter the 6-digit code it shows:`;
      const cin = document.createElement("input"); cin.placeholder = "123456"; cin.className = "portal-filter"; cin.inputMode = "numeric";
      const confirm = document.createElement("button"); confirm.className = "file-btn"; confirm.textContent = "Confirm & enable";
      confirm.onclick = async () => {
        try {
          const r = await D.api.mfaEnable(cin.value.trim());
          body.textContent = "";
          const done = document.createElement("div"); done.className = "meta";
          done.innerHTML = "✅ <b>MFA enabled.</b> Save these one-time recovery codes somewhere safe — "
            + "each works once if you lose your device:";
          const codes = document.createElement("textarea"); codes.readOnly = true; codes.rows = 5;
          codes.style.cssText = "width:100%;font-family:monospace;user-select:all";
          codes.value = r.recovery_codes.join("\n");
          const ok = document.createElement("button"); ok.className = "file-btn"; ok.textContent = "Done"; ok.onclick = close;
          body.append(done, codes, ok);
        } catch { msg.textContent = "that code did not match — check the app and try again"; }
      };
      body.append(steps, key, uri, cin, confirm); cin.focus();
    };
    const note = document.createElement("div"); note.className = "meta";
    note.textContent = "Add a second factor: after your password, you'll enter a time-based code at sign-in.";
    body.append(note, start);
  };
  await render();
}

/** Set a new password using an admin-issued one-time reset token (no email infra). */
function resetModal() {
  const { card, msg, close } = modalShell("Reset password with token");
  const tk = document.createElement("input"); tk.placeholder = "reset token"; tk.className = "portal-filter";
  const np = document.createElement("input"); np.type = "password"; np.placeholder = "new password (min 8)"; np.className = "portal-filter";
  msg.style.color = "var(--err)";
  const row = document.createElement("div"); row.style.cssText = "display:flex;gap:8px;justify-content:flex-end";
  const cancel = document.createElement("button"); cancel.className = "tool-btn"; cancel.textContent = "Cancel"; cancel.onclick = close;
  const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Set password";
  go.onclick = async () => {
    if (!tk.value.trim()) { msg.textContent = "paste your reset token"; return; }
    if (np.value.length < 8) { msg.textContent = "new password must be at least 8 characters"; return; }
    try { await D.api.resetWithToken(tk.value.trim(), np.value); close(); toast("Password set — please sign in", "info"); loginModal(); }
    catch { msg.textContent = "invalid or expired reset token"; }
  };
  row.append(cancel, go); card.append(tk, np, msg, row); tk.focus();
}

/** Account dropdown anchored to the account button: self-service + (admins) platform consoles. */
function accountMenu(anchor: HTMLElement, platformAdmin = false, tier = "free") {
  document.querySelector(".acct-menu")?.remove();
  const menu = document.createElement("div");
  menu.className = "acct-menu";
  const r = anchor.getBoundingClientRect();
  menu.style.cssText = `position:fixed;top:${r.bottom + 4}px;right:${window.innerWidth - r.right}px;z-index:200;`
    + "background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:5px;display:flex;flex-direction:column;min-width:160px";
  const badge = document.createElement("div");
  badge.className = "meta";
  badge.style.cssText = "padding:4px 8px;display:flex;justify-content:space-between;gap:8px;align-items:center";
  badge.innerHTML = `<span>Plan</span><span style="text-transform:capitalize;color:var(--text)">${escapeHtml(tier)}</span>`;
  menu.append(badge);
  const item = (label: string, fn: () => void) => {
    const b = document.createElement("button");
    b.className = "tool-btn"; b.textContent = label; b.style.cssText = "justify-content:flex-start;width:100%;text-align:left";
    b.onclick = () => { menu.remove(); fn(); };
    return b;
  };
  const pid = D.getProjectId();
  if (platformAdmin) menu.append(item("Manage users…", adminModal));
  if (platformAdmin) menu.append(item("Audit log…", auditModal));
  if (platformAdmin) menu.append(item("Data connections…",
    () => void import("../connections/connectionsUI").then((m) => m.openConnectionsModal(D.api, D.getProjectId))));
  if (D.getIsProjectAdmin() && pid) menu.append(item("Project members…", () => membersModal(pid)));
  menu.append(item("Settings…", D.openSettings));
  menu.append(item("Change password…", passwordModal));
  menu.append(item("Two-factor auth…", () => void mfaModal()));
  menu.append(item("Sign out everywhere…", async () => {
    if (!await confirmModal("Sign out everywhere",
        "Sign out of every other device and session? This tab stays signed in.", "Revoke sessions")) return;
    try { await D.api.logoutAll(); toast("Signed out of all other sessions", "info"); }
    catch { toast("Could not revoke sessions", "error"); }
  }));
  menu.append(item("Sign out", async () => { await D.api.logout(); D.api.setToken(""); location.reload(); }));
  document.body.appendChild(menu);
  setTimeout(() => document.addEventListener("pointerdown", function off(e) {
    if (!menu.contains(e.target as Node)) { menu.remove(); document.removeEventListener("pointerdown", off); }
  }), 0);
}

/** Self-service password change (any signed-in user). */
function passwordModal() {
  const { card, msg, close } = modalShell("Change password");
  const cur = document.createElement("input"); cur.type = "password"; cur.placeholder = "current password"; cur.className = "portal-filter";
  const nw = document.createElement("input"); nw.type = "password"; nw.placeholder = "new password (min 8)"; nw.className = "portal-filter";
  msg.style.color = "var(--err)";
  const row = document.createElement("div"); row.style.cssText = "display:flex;gap:8px;justify-content:flex-end";
  const cancel = document.createElement("button"); cancel.className = "tool-btn"; cancel.textContent = "Cancel"; cancel.onclick = close;
  const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Update";
  go.onclick = async () => {
    if (nw.value.length < 8) { msg.textContent = "new password must be at least 8 characters"; return; }
    try { await D.api.changePassword(cur.value, nw.value); close(); toast("Password updated", "info"); }
    catch { msg.textContent = "current password is incorrect"; }
  };
  row.append(cancel, go); card.append(cur, nw, msg, row); cur.focus();
}

/** Admin user management: create accounts, toggle role/active, reset passwords. */
function adminModal() {
  const { card, msg } = modalShell("Manage users", 460);
  const list = document.createElement("div"); list.style.cssText = "display:flex;flex-direction:column;gap:6px";
  msg.style.color = "var(--err)";
  const api = D.api;

  const render = async () => {
    list.textContent = "";
    let users: AccountUser[] = [];
    try { users = await api.listUsers(); } catch { msg.textContent = "could not load users"; return; }
    for (const u of users) {
      const row = document.createElement("div");
      row.style.cssText = "display:flex;align-items:center;gap:8px;padding:6px 8px;border:1px solid var(--line);border-radius:6px";
      const nm = document.createElement("span"); nm.textContent = u.username; nm.style.cssText = "font-weight:600;min-width:90px";
      const tags = document.createElement("span"); tags.className = "meta";
      tags.textContent = `${u.role}${u.active ? "" : " · deactivated"}${u.email ? " · " + u.email : ""}`;
      tags.style.color = u.active ? "var(--muted)" : "#e2554a";
      const spacer = document.createElement("span"); spacer.style.flex = "1";
      const act = (label: string, fn: () => Promise<unknown>) => {
        const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = label;
        b.onclick = async () => { try { await fn(); await render(); } catch { msg.textContent = `action failed for ${u.username}`; } };
        return b;
      };
      const roleBtn = act(u.role === "admin" ? "Make user" : "Make admin",
        () => api.updateUser(u.username, { role: u.role === "admin" ? "user" : "admin" }));
      const activeBtn = act(u.active ? "Deactivate" : "Reactivate",
        () => api.updateUser(u.username, { active: !u.active }));
      const pwBtn = act("Reset password", async () => {
        const np = await askText("Reset password", { label: `New password for ${u.username} (min 8):` });
        if (np == null) return;
        if (np.length < 8) { msg.textContent = "password must be at least 8 characters"; return; }
        await api.resetUserPassword(u.username, np);
        toast(`Password reset for ${u.username}`, "info");
      });
      const linkBtn = act("Reset link", async () => {
        const { reset_token } = await api.issueResetToken(u.username);
        await navigator.clipboard?.writeText(reset_token).catch(() => {});
        await askText("Reset link", { label: `One-time reset token for ${u.username} (copied; expires in 1h). They paste it at Sign in → "Have a reset token?":`, value: reset_token });
      });
      const emailBtn = act("Email", async () => {
        const e = await askText("Edit email", { label: `Email for ${u.username} (blank to clear):`, value: u.email || "" });
        if (e === null) return;
        await api.updateUser(u.username, { email: e.trim() });
        toast(`Email updated for ${u.username}`, "info");
      });
      const revokeBtn = act("Revoke sessions", async () => {
        if (!await confirmModal("Revoke sessions",
            `Sign ${u.username} out of all devices? They must sign in again.`, "Revoke")) return;
        await api.revokeUserSessions(u.username);
        toast(`Revoked ${u.username}'s sessions`, "info");
      });
      row.append(nm, tags, spacer, roleBtn, activeBtn, pwBtn, revokeBtn, linkBtn, emailBtn);
      list.append(row);
    }
  };

  const form = document.createElement("div"); form.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center";
  const nu = document.createElement("input"); nu.placeholder = "new username"; nu.className = "portal-filter"; nu.style.flex = "1";
  const np = document.createElement("input"); np.type = "password"; np.placeholder = "password (min 8)"; np.className = "portal-filter"; np.style.flex = "1";
  const ne = document.createElement("input"); ne.type = "email"; ne.placeholder = "email (for digests, optional)"; ne.className = "portal-filter"; ne.style.flex = "1";
  const nr = document.createElement("select"); nr.className = "portal-filter";
  nr.innerHTML = '<option value="user">user</option><option value="admin">admin</option>';
  const add = document.createElement("button"); add.className = "file-btn"; add.textContent = "Add";
  add.onclick = async () => {
    msg.textContent = "";
    if (!nu.value.trim() || np.value.length < 8) { msg.textContent = "username + password (min 8) required"; return; }
    try {
      await api.createUser(nu.value.trim(), np.value, nr.value as "admin" | "user", ne.value.trim() || undefined);
      nu.value = ""; np.value = ""; ne.value = ""; await render();
    } catch { msg.textContent = "could not create user (name may be taken)"; }
  };
  form.append(nu, np, ne, nr, add);
  card.append(list, document.createElement("hr"), form, msg);
  void render();
}

/** Project-member management (project admins): grant/change role + party, set company, remove. */
function membersModal(pid: string) {
  const { card, msg } = modalShell("Project members", 520);
  const list = document.createElement("div"); list.style.cssText = "display:flex;flex-direction:column;gap:6px";
  msg.style.color = "var(--err)";
  const api = D.api;
  const sel = (opts: readonly string[], value: string) => {
    const s = document.createElement("select"); s.className = "portal-filter";
    for (const o of opts) { const op = document.createElement("option"); op.value = o; op.textContent = o || "— party —"; s.appendChild(op); }
    s.value = value; return s;
  };

  const render = async () => {
    list.textContent = "";
    let members: ProjectMember[] = [];
    try { members = await api.members(pid); } catch { msg.textContent = "could not load members"; return; }
    for (const m of members) {
      const row = document.createElement("div");
      row.style.cssText = "display:flex;align-items:center;gap:8px;padding:6px 8px;border:1px solid var(--line);border-radius:6px";
      const nm = document.createElement("span"); nm.textContent = m.user; nm.style.cssText = "font-weight:600;min-width:90px";
      const meta = document.createElement("span"); meta.className = "meta"; meta.style.flex = "1";
      meta.textContent = m.company || "";
      const roleSel = sel(PROJECT_ROLES, m.role);
      const partySel = sel(PARTY_ROLES, m.party_role ?? "");
      const save = async () => {
        try { await api.addMember(pid, { user: m.user, role: roleSel.value as ProjectRole, party_role: partySel.value || null, company: m.company }); await render(); }
        catch { msg.textContent = `could not update ${m.user}`; }
      };
      roleSel.onchange = save; partySel.onchange = save;
      const rm = document.createElement("button"); rm.className = "tool-btn"; rm.textContent = "Remove";
      rm.onclick = async () => {
        if (!(await confirmModal(`Remove ${m.user} from this project?`, "", "Remove", true))) return;
        try { await api.removeMember(pid, m.user); await render(); }
        catch { msg.textContent = `could not remove ${m.user} (last admin?)`; }
      };
      row.append(nm, roleSel, partySel, meta, rm);
      list.append(row);
    }
  };

  const form = document.createElement("div"); form.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center";
  const nu = document.createElement("input"); nu.placeholder = "username"; nu.className = "portal-filter"; nu.style.flex = "1";
  const nrole = sel(PROJECT_ROLES, "viewer");
  const nparty = sel(PARTY_ROLES, "");
  const nco = document.createElement("input"); nco.placeholder = "company (optional)"; nco.className = "portal-filter"; nco.style.flex = "1";
  const add = document.createElement("button"); add.className = "file-btn"; add.textContent = "Add";
  add.onclick = async () => {
    msg.textContent = "";
    if (!nu.value.trim()) { msg.textContent = "enter a username"; return; }
    try {
      await api.addMember(pid, { user: nu.value.trim(), role: nrole.value as ProjectRole, party_role: nparty.value || null, company: nco.value.trim() || null });
      nu.value = ""; nco.value = ""; await render();
    } catch { msg.textContent = "could not add member"; }
  };
  form.append(nu, nrole, nparty, nco, add);

  const hint = document.createElement("div"); hint.className = "meta";
  hint.textContent = "Role = capability (viewer→admin). Party = workflow side (GC, Owner, …). The account must already exist (Manage users).";
  card.append(list, document.createElement("hr"), form, hint, msg);
  void render();
}

/** Read-only audit-trail viewer (global admins): filter by action/actor/since, newest first. */
function auditModal() {
  const { card, msg } = modalShell("Audit log", 620);
  msg.style.color = "var(--err)";
  const api = D.api;
  const filters = document.createElement("div"); filters.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center";
  const fAction = document.createElement("input"); fAction.placeholder = "action contains…"; fAction.className = "portal-filter";
  const fActor = document.createElement("input"); fActor.placeholder = "actor contains…"; fActor.className = "portal-filter";
  const fSince = document.createElement("input"); fSince.type = "date"; fSince.className = "portal-filter"; fSince.title = "since (date)";
  const apply = document.createElement("button"); apply.className = "tool-btn"; apply.textContent = "Filter";
  filters.append(fAction, fActor, fSince, apply);
  const table = document.createElement("div"); table.style.cssText = "max-height:55vh;overflow:auto;margin-top:8px";

  const render = async () => {
    table.innerHTML = '<div class="meta">loading…</div>'; msg.textContent = "";
    let rows: AuditEntry[] = [];
    try {
      rows = await api.auditLog({ action: fAction.value.trim() || undefined, actor: fActor.value.trim() || undefined,
        since: fSince.value || undefined, limit: 200 });
    } catch { table.innerHTML = ""; msg.textContent = "could not load audit log (admin only)"; return; }
    if (!rows.length) { table.innerHTML = '<div class="meta">no matching entries</div>'; return; }
    const cell = (s: string) => `<td style="padding:4px 8px;border-bottom:1px solid var(--line);white-space:nowrap">${s}</td>`;
    table.innerHTML = `<table class="sens-table" style="width:100%;font-size:12px"><tr>` +
      `<th style="text-align:left">When</th><th style="text-align:left">Actor</th><th style="text-align:left">Action</th><th style="text-align:left">Detail</th></tr>` +
      rows.map((r) => `<tr>` +
        cell(new Date(r.ts).toLocaleString()) + cell(escapeHtml(r.actor ?? "—")) + cell(escapeHtml(r.action)) +
        `<td style="padding:4px 8px;border-bottom:1px solid var(--line);color:var(--muted)">${escapeHtml(r.detail ? JSON.stringify(r.detail) : (r.path ?? ""))}</td>` +
        `</tr>`).join("") + `</table>`;
  };
  apply.onclick = () => void render();
  fAction.onkeydown = fActor.onkeydown = (e) => { if (e.key === "Enter") void render(); };
  card.append(filters, table, msg);
  void render();
}
