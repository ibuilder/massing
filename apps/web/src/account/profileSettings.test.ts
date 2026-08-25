import { beforeEach, describe, expect, it, vi } from "vitest";

import { openProfileSettings, type ProfileActions, type ProfileDeps } from "./profileSettings";
import type { CloudStatus } from "../api/cloud";

/**
 * The profile panel is where this change actually lands for a user, so the assertions are about the
 * product claim rather than about markup:
 *
 *  * **Administration is a section, not a console.** A non-admin and an admin see the *same* panel;
 *    the admin's has one more section. That is the whole reorganisation, and it is the thing that
 *    silently regresses if someone re-adds a top-level admin entry point.
 *  * **Capability gates the section, not the actions.** The admin actions must be unreachable for a
 *    non-admin — asserting the tab is missing is not enough on its own, because a hidden tab whose
 *    content is still built would leak the buttons.
 *  * **An unreachable server and an unlinked account are different facts.** `cloud: null` must not
 *    render as "not connected", or a user with a working link is told to reconnect.
 */
function actions(): ProfileActions {
  return {
    manageUsers: vi.fn(), auditLog: vi.fn(), errorLog: vi.fn(), dataConnections: vi.fn(),
    projectMembers: null, changePassword: vi.fn(), twoFactor: vi.fn(), appSettings: vi.fn(),
    signOutEverywhere: vi.fn(), signOut: vi.fn(), connectCloud: vi.fn(),
    refreshCloud: vi.fn(async () => ({} as CloudStatus)), disconnectCloud: vi.fn(async () => {}),
    openLibrary: vi.fn(),
  };
}

const linked: CloudStatus = {
  enabled: true, linked: true, site_url: "https://www.massing.cloud",
  email: "ada@example.com", name: "Ada Lovelace", tier: "commercial", tier_label: "Commercial",
  roles: ["editor"], providers: ["google"], is_admin: true, library_access: true,
};

function open(over: Partial<ProfileDeps> = {}, initial?: string) {
  const deps: ProfileDeps = {
    identity: { username: "ada@example.com", displayName: "Ada Lovelace" },
    platformAdmin: false, cloud: linked, tierLabel: "Commercial", actions: actions(),
    ...over,
  };
  openProfileSettings(deps, initial);
  const dialog = document.querySelector('[role="dialog"]') as HTMLElement;
  return { dialog, deps };
}

const tabNames = (d: HTMLElement) =>
  [...d.querySelectorAll('[role="tab"]')].map((b) => b.textContent);

beforeEach(() => { document.body.textContent = ""; });

describe("openProfileSettings", () => {
  it("shows the same sections to a non-admin, minus Administration", () => {
    const { dialog } = open({ platformAdmin: false });
    expect(tabNames(dialog)).toEqual(["Profile", "massing.cloud", "Security", "Preferences"]);
  });

  it("adds Administration as ONE MORE SECTION for an admin — not a separate console", () => {
    const { dialog } = open({ platformAdmin: true });
    expect(tabNames(dialog)).toEqual(
      ["Profile", "massing.cloud", "Security", "Preferences", "Administration"]);
  });

  it("does not build the admin actions at all for a non-admin", () => {
    // The gate has to be on the section, not merely on the tab: a hidden tab whose body is still
    // constructed would put "Manage…" buttons in the DOM for a user who cannot use them.
    const { dialog } = open({ platformAdmin: false });
    for (const tab of dialog.querySelectorAll('[role="tab"]')) (tab as HTMLElement).click();
    expect(dialog.textContent).not.toContain("Audit log");
    expect(dialog.textContent).not.toContain("Data connections");
  });

  it("reaches the admin actions through the Administration section", () => {
    const { dialog, deps } = open({ platformAdmin: true });
    (([...dialog.querySelectorAll('[role="tab"]')]
      .find((b) => b.textContent === "Administration")) as HTMLElement).click();
    const users = [...dialog.querySelectorAll("button")]
      .find((b) => b.previousSibling?.textContent?.includes("Users"));
    expect(dialog.textContent).toContain("Audit log");
    users?.click();
    expect(deps.actions.manageUsers).toHaveBeenCalled();
  });

  it("tells an admin WHY they see the section, naming the cloud role when that is the reason", () => {
    const { dialog } = open({ platformAdmin: true, cloud: linked });
    (([...dialog.querySelectorAll('[role="tab"]')]
      .find((b) => b.textContent === "Administration")) as HTMLElement).click();
    expect(dialog.textContent).toContain("massing.cloud role is editor");
  });

  it("offers Connect when the broker is enabled but this account is not linked", () => {
    const { dialog, deps } = open({
      cloud: { enabled: true, linked: false, site_url: "https://www.massing.cloud" },
    }, "cloud");
    expect(dialog.textContent).toContain("Not connected");
    ([...dialog.querySelectorAll("button")].find((b) => b.textContent === "Connect…"))?.click();
    expect(deps.actions.connectCloud).toHaveBeenCalled();
  });

  it("points a free plan at pricing instead of an empty library", () => {
    const { dialog } = open({
      cloud: { ...linked, tier: "free", tier_label: "Free", library_access: false },
    }, "cloud");
    expect(dialog.textContent).toContain("Included with any paid plan");
    expect(dialog.textContent).not.toContain("Open library…");
  });

  it("opens the library for an entitled plan", () => {
    const { dialog, deps } = open({ cloud: linked }, "cloud");
    ([...dialog.querySelectorAll("button")].find((b) => b.textContent === "Open library…"))?.click();
    expect(deps.actions.openLibrary).toHaveBeenCalled();
  });

  it("distinguishes 'could not check' from 'not connected'", () => {
    const { dialog } = open({ cloud: null }, "cloud");
    expect(dialog.textContent).toContain("Could not reach the server");
    expect(dialog.textContent).not.toContain("Not connected");
  });

  it("says so when the operator has not enabled the broker at all", () => {
    const { dialog } = open({
      cloud: { enabled: false, linked: false, site_url: "https://www.massing.cloud" },
    }, "cloud");
    expect(dialog.textContent).toContain("Not configured");
  });

  it("falls back to Profile when asked for a section that does not exist for this user", () => {
    // A non-admin deep-linked to "admin" must land somewhere sane rather than on a blank pane.
    const { dialog } = open({ platformAdmin: false }, "admin");
    const selected = dialog.querySelector('[role="tab"][aria-selected="true"]');
    expect(selected?.textContent).toBe("Profile");
  });
});
