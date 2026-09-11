/** Which sign-in doors the login modal offers, and in what order.
 *
 *  Pure, and separate from the modal, because the ordering is the part with a rule in it and the
 *  modal is the part with a `document` in it. It was inline, and while it was inline the one door
 *  nobody could see was the one that is not an OAuth provider at all: a workspace's own SAML IdP
 *  has no `/auth/oauth/{id}/login` URL, so it could never be an entry in `providers`, and the modal
 *  had no other way to render a door. `GET /auth/providers` had been returning `saml` the whole
 *  time; the client type did not declare it, so nothing downstream could reach it.
 *
 *  `lead` is the big-button group; the rest collapse behind "More sign-in options".
 */
export type OauthProvider = { id: string; label: string };
export type SignInDoor = { key: string; label: string; path: string; lead: boolean };

/** Providers that lead when configured — the two consumer identities most people already have. */
const PRIMARY = new Set(["google", "microsoft"]);

export function signInDoors(providers: OauthProvider[], saml: boolean): SignInDoor[] {
  const doors: SignInDoor[] = [];
  if (saml) {
    // First, deliberately: an organisation that wired its own IdP signs its people in through that,
    // not through a consumer provider that happens to also be configured on the same server. The
    // caller may render this true ONLY because the server already checked both halves — an IdP is
    // configured AND the tier entitles `sso` — so the button cannot 402 on click.
    doors.push({ key: "saml", label: "single sign-on", path: "/auth/saml/login", lead: true });
  }
  const primary = providers.filter((pv) => PRIMARY.has(pv.id));
  // No primary provider configured: the first one still takes a lead slot, so a server with only
  // Procore does not hide its only OAuth door behind a disclosure link.
  const lead = new Set(primary.length ? primary : providers.slice(0, 1));
  for (const pv of providers) {
    doors.push({ key: pv.id, label: pv.label, path: `/auth/oauth/${pv.id}/login`, lead: lead.has(pv) });
  }
  return doors;
}

/** The doors that collapse — i.e. how many "More sign-in options" is offering. */
export function collapsedDoors(doors: SignInDoor[]): SignInDoor[] {
  return doors.filter((d) => !d.lead);
}
