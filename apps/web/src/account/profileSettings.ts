/** Profile & settings — **one** place for everything about the signed-in person.
 *
 *  This replaces the old account dropdown, in which "Manage users…", "Audit log…", "Errors…" and
 *  "Data connections…" sat as four separate top-level entries visible only to admins. That layout
 *  encoded a product idea we are moving away from: that "admin" is a *place* you go, distinct from
 *  your account. It is not. Administration is a **section of your profile** that appears when your
 *  account happens to carry the capability — the same panel, one section longer.
 *
 *  Practically that means: a user who gains or loses admin sees the same navigation with one section
 *  added or removed, rather than four menu items materialising somewhere else; and every setting that
 *  is *about the person* (identity, cloud link, password, MFA, sessions, preferences) is reachable
 *  from one control instead of from a dropdown, a modal and a separate settings panel.
 *
 *  **Sections are injected, not imported.** The existing modals (`adminModal`, `auditModal`, …) stay
 *  private to `accountUI.ts`, which owns them; this module receives them as callbacks. That keeps the
 *  dependency one-way and lets this panel be tested against a stub with no DOM-heavy modal behind it.
 */
import { escapeHtml, toast } from "../ui/feedback";
import { modalShell, confirmModal } from "../ui/modal";
import { identityHeader, type ChipIdentity } from "./accountChip";
import type { CloudStatus } from "../api/cloud";

/** The actions this panel offers. Everything is a callback so the panel owns no domain logic. */
export interface ProfileActions {
  manageUsers: () => void;
  auditLog: () => void;
  errorLog: () => void;
  dataConnections: () => void;
  projectMembers: (() => void) | null;   // null when there is no project / not a project admin
  changePassword: () => void;
  twoFactor: () => void;
  appSettings: () => void;               // viewer/shortcut settings, owned by main.ts
  signOutEverywhere: () => void;
  signOut: () => void;
  connectCloud: () => void;
  refreshCloud: () => Promise<CloudStatus>;
  disconnectCloud: () => Promise<void>;
  openLibrary: () => void;
}

export interface ProfileDeps {
  identity: ChipIdentity;
  platformAdmin: boolean;
  /** massing.cloud link state; `null` when the status call failed (offline) — rendered as such. */
  cloud: CloudStatus | null;
  tierLabel: string;
  actions: ProfileActions;
}

interface Section { id: string; label: string; build: (body: HTMLElement) => void }

/** A labelled row with an action button on the right — the panel's one repeating unit. */
function row(title: string, detail: string, actionLabel?: string, onClick?: () => void): HTMLElement {
  const el = document.createElement("div");
  el.style.cssText = "display:flex;align-items:center;gap:12px;padding:9px 10px;border:1px solid var(--line);"
    + "border-radius:7px;background:var(--bg-elev)";
  const col = document.createElement("div");
  col.style.cssText = "display:flex;flex-direction:column;gap:2px;min-width:0;flex:1";
  const t = document.createElement("span");
  t.textContent = title; t.style.cssText = "font-size:13px";
  const d = document.createElement("span");
  d.className = "meta"; d.innerHTML = escapeHtml(detail);
  col.append(t, d);
  el.append(col);
  if (actionLabel && onClick) {
    const b = document.createElement("button");
    b.className = "tool-btn"; b.textContent = actionLabel; b.style.flex = "0 0 auto";
    b.onclick = onClick;
    el.append(b);
  }
  return el;
}

function group(body: HTMLElement, heading: string): HTMLElement {
  const h = document.createElement("div");
  h.textContent = heading;
  h.style.cssText = "font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);"
    + "margin:6px 0 2px";
  const wrap = document.createElement("div");
  wrap.style.cssText = "display:flex;flex-direction:column;gap:7px";
  body.append(h, wrap);
  return wrap;
}

/** Open the profile panel. `initial` selects a section by id (e.g. "cloud" from a deep link). */
export function openProfileSettings(deps: ProfileDeps, initial = "profile"): void {
  const { platformAdmin, actions } = deps;
  const { card, close, ready } = modalShell("Profile & settings", 720);

  const layout = document.createElement("div");
  layout.style.cssText = "display:flex;gap:16px;align-items:flex-start;min-height:320px";
  const nav = document.createElement("div");
  nav.setAttribute("role", "tablist");
  nav.setAttribute("aria-orientation", "vertical");
  nav.style.cssText = "display:flex;flex-direction:column;gap:2px;flex:0 0 168px;border-right:1px solid var(--line);"
    + "padding-right:12px";
  const body = document.createElement("div");
  body.style.cssText = "flex:1;display:flex;flex-direction:column;gap:8px;min-width:0";
  layout.append(nav, body);
  card.append(layout);

  const sections: Section[] = [
    { id: "profile", label: "Profile", build: (b) => buildProfile(b, deps) },
    { id: "cloud", label: "massing.cloud", build: (b) => buildCloud(b, deps) },
    { id: "security", label: "Security", build: (b) => buildSecurity(b, actions) },
    { id: "preferences", label: "Preferences", build: (b) => buildPreferences(b, actions) },
  ];
  // The whole point of this panel: administration is a SECTION, present only when the account
  // carries the capability — not a separate console reached from somewhere else.
  if (platformAdmin) {
    sections.push({ id: "admin", label: "Administration", build: (b) => buildAdmin(b, deps) });
  }

  const buttons = new Map<string, HTMLButtonElement>();
  const show = (id: string) => {
    body.textContent = "";
    for (const [bid, b] of buttons) {
      const on = bid === id;
      b.setAttribute("aria-selected", String(on));
      b.style.background = on ? "var(--control-hover)" : "transparent";
      b.style.color = on ? "var(--text)" : "";
    }
    sections.find((s) => s.id === id)?.build(body);
  };
  for (const s of sections) {
    const b = document.createElement("button");
    b.className = "tool-btn"; b.textContent = s.label;
    b.setAttribute("role", "tab");
    b.style.cssText = "justify-content:flex-start;width:100%;text-align:left;border:none;background:transparent";
    b.onclick = () => show(s.id);
    buttons.set(s.id, b);
    nav.append(b);
  }

  const signOut = document.createElement("button");
  signOut.className = "tool-btn";
  signOut.textContent = "Sign out";
  signOut.style.cssText = "justify-content:flex-start;width:100%;text-align:left;border:none;"
    + "background:transparent;margin-top:auto;color:var(--danger)";
  signOut.onclick = () => { close(); actions.signOut(); };
  nav.append(signOut);

  show(sections.some((s) => s.id === initial) ? initial : "profile");
  ready?.();
}

function buildProfile(body: HTMLElement, deps: ProfileDeps): void {
  const { identity, cloud, tierLabel } = deps;
  const via = cloud?.linked && cloud.providers?.length
    ? `signed in via ${cloud.providers.join(", ")}`
    : "signed in with a password on this server";
  body.append(identityHeader(identity, `${identity.username} · ${via}`));

  const g = group(body, "Account");
  g.append(row("Plan", tierLabel
    ? `${tierLabel}${cloud?.linked ? " — from your massing.cloud subscription" : ""}`
    : "Free"));
  g.append(row("Signed in as", identity.username));
  if (identity.isAdmin) {
    g.append(row("Administrator", cloud?.linked && cloud.roles?.length
      ? `granted by your massing.cloud role (${cloud.roles.join(", ")})`
      : "granted on this server"));
  }
}

function buildCloud(body: HTMLElement, deps: ProfileDeps): void {
  const { cloud, actions } = deps;
  if (cloud === null) {
    body.append(row("massing.cloud", "Could not reach the server to check your connection."));
    return;
  }
  if (!cloud.enabled) {
    const g = group(body, "massing.cloud");
    g.append(row("Not configured", "An administrator has not enabled massing.cloud sign-in on this "
      + "server. Turn it on under Administration → Server settings."));
    return;
  }
  if (!cloud.linked) {
    const g = group(body, "massing.cloud");
    g.append(row("Not connected",
      "Connect your massing.cloud account to sign in with Microsoft, Google, Procore or Autodesk "
      + "and open the projects in your cloud library.",
      "Connect…", actions.connectCloud));
    return;
  }

  const g = group(body, "Connection");
  g.append(row("Account", `${cloud.name || cloud.email || "—"}${cloud.email ? ` · ${cloud.email}` : ""}`));
  g.append(row("Plan", cloud.tier_label || cloud.tier || "Free"));
  if (cloud.providers?.length) g.append(row("Connected accounts", cloud.providers.join(", ")));
  if (cloud.roles?.length) g.append(row("Role on massing.cloud", cloud.roles.join(", ")));
  g.append(row("Last checked", cloud.last_sync ? new Date(cloud.last_sync).toLocaleString() : "—",
    "Refresh", () => {
      void actions.refreshCloud()
        .then(() => toast("Updated from massing.cloud", "info"))
        .catch(() => toast("Could not reach massing.cloud", "error"));
    }));

  const lib = group(body, "Project library");
  if (cloud.library_access) {
    lib.append(row("Your cloud projects",
      "Browse and open the projects saved to your massing.cloud vault.",
      "Open library…", actions.openLibrary));
  } else {
    // An unentitled library and an empty one must not look the same — say which it is, and where
    // the fix is. This mirrors the server's 402, which names the upgrade page rather than
    // returning an empty list.
    lib.append(row("Included with any paid plan",
      "Your massing.cloud plan is Free, so there is no cloud library to open yet.",
      "See plans", () => window.open(`${cloud.site_url}/pricing/`, "_blank", "noopener")));
  }

  const danger = group(body, "Disconnect");
  danger.append(row("Disconnect massing.cloud",
    "Removes the link and this app's access to your cloud library. Your local projects are untouched.",
    "Disconnect…", async () => {
      if (!await confirmModal("Disconnect massing.cloud",
        "Sign-in through massing.cloud and your cloud library will stop working until you reconnect. "
        + "Projects stored on this server are not affected.", "Disconnect")) return;
      try { await actions.disconnectCloud(); toast("Disconnected from massing.cloud", "info"); }
      catch { toast("Could not disconnect", "error"); }
    }));
}

function buildSecurity(body: HTMLElement, a: ProfileActions): void {
  const g = group(body, "Sign-in");
  g.append(row("Password", "Change the password for this account.", "Change…", a.changePassword));
  g.append(row("Two-factor authentication", "Protect this account with an authenticator app.",
    "Manage…", a.twoFactor));
  const s = group(body, "Sessions");
  s.append(row("Sign out everywhere",
    "Ends every other session on every device. This tab stays signed in.",
    "Revoke…", a.signOutEverywhere));
}

function buildPreferences(body: HTMLElement, a: ProfileActions): void {
  const g = group(body, "Application");
  g.append(row("Viewer & shortcuts", "Keyboard shortcuts, units and viewer defaults.",
    "Open…", a.appSettings));
}

function buildAdmin(body: HTMLElement, deps: ProfileDeps): void {
  const { actions: a, cloud } = deps;
  const note = document.createElement("div");
  note.className = "meta";
  note.style.cssText = "padding:2px 0 4px";
  note.textContent = cloud?.linked && cloud.roles?.length
    ? `You see this section because your massing.cloud role is ${cloud.roles.join(", ")}.`
    : "You see this section because this account has administrator access on this server.";
  body.append(note);

  const people = group(body, "People");
  people.append(row("Users", "Create accounts, change roles, reset passwords.", "Manage…", a.manageUsers));
  if (a.projectMembers) {
    people.append(row("Project members", "Roles and parties on the current project.",
      "Manage…", a.projectMembers));
  }
  const server = group(body, "Server");
  server.append(row("Data connections", "Connect external data sources for this deployment.",
    "Open…", a.dataConnections));
  server.append(row("Server settings", "Licence, integrations and API keys.", "Open…", a.appSettings));
  const logs = group(body, "Diagnostics");
  logs.append(row("Audit log", "Who did what, newest first.", "View…", a.auditLog));
  logs.append(row("Errors", "Recent server-side errors.", "View…", a.errorLog));
}
