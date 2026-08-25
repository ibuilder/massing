/** The toolbar identity control — "signed in as", with the massing.cloud (WordPress) avatar.
 *
 *  Replaces the plain `"<username> ▾"` text button. The point is recognition at a glance: the chip
 *  is the most-looked-at control in the shell, and a photo answers "whose session is this?" faster
 *  than an email address does — which matters here because a browser in a site trailer is routinely
 *  a shared machine.
 *
 *  **Three states, one control.** Signed out → a plain "Sign in". Signed in with a cloud link → the
 *  avatar massing.cloud serves for that account. Signed in *without* one (password or direct-IdP
 *  accounts, which have no avatar and never will) → a generated initials disc in a colour derived
 *  from the name. The fallback is a rendering branch, never an error: `avatar_url` being absent is
 *  the normal case for a local account.
 *
 *  The avatar is decorative — the accessible name is carried by `aria-label` on the button, so a
 *  screen reader reads "Account: Ada Lovelace", not a filename.
 */
import { escapeHtml, safeHref } from "../ui/feedback";

export interface ChipIdentity {
  username: string;
  displayName?: string | null;
  avatarUrl?: string | null;
  tierLabel?: string | null;
  isAdmin?: boolean;
}

/** Stable hue from a string, so a given person keeps the same fallback colour across reloads. */
function hueFor(seed: string): number {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) % 360;
  return h;
}

/** "Ada Lovelace" → "AL"; "ada@example.com" → "AD". Never more than two glyphs. */
export function initialsFor(name: string): string {
  const clean = (name || "").trim();
  if (!clean) return "?";
  const local = (clean.includes("@") ? clean.split("@")[0] : clean) || clean;
  const parts = local.split(/[\s._-]+/).filter(Boolean);
  if (parts.length >= 2) return ((parts[0]![0] ?? "") + (parts[1]![0] ?? "")).toUpperCase();
  return local.slice(0, 2).toUpperCase();
}

/** Build the 22px avatar element: an <img> when there is a URL, else an initials disc.
 *
 *  A broken/blocked avatar URL swaps itself for the initials disc on `error` — an offline desktop
 *  session would otherwise show the browser's broken-image glyph on the primary account control. */
export function avatarEl(identity: ChipIdentity, size = 22): HTMLElement {
  const label = identity.displayName || identity.username;
  const disc = () => {
    const d = document.createElement("span");
    d.textContent = initialsFor(label);
    d.style.cssText = `width:${size}px;height:${size}px;border-radius:50%;flex:0 0 auto;`
      + `display:inline-flex;align-items:center;justify-content:center;`
      + `font-size:${Math.round(size * 0.42)}px;font-weight:600;letter-spacing:.02em;`
      // Legacy comma syntax on purpose: the space-separated `hsl(H S% L%)` form is dropped outright
      // by some CSS parsers (happy-dom among them), which would leave the disc transparent.
      + `background:hsl(${hueFor(label)}, 45%, 32%);color:#fff`;
    d.setAttribute("aria-hidden", "true");
    return d;
  };
  if (!identity.avatarUrl) return disc();
  // The avatar URL is external data — it reaches us from massing.cloud's `userinfo`, which in turn
  // reflects whatever avatar host that account uses. `safeHref` collapses anything outside the
  // http(s) allowlist to "#"; rather than set `src="#"` and rely on the error handler, refuse it
  // up front and draw the initials disc, which is the same outcome without the failed request.
  const href = safeHref(identity.avatarUrl);
  if (href === "#") return disc();
  const img = document.createElement("img");
  img.src = href;
  img.alt = "";                                   // decorative; the button carries the name
  img.decoding = "async";
  img.referrerPolicy = "no-referrer";
  img.style.cssText = `width:${size}px;height:${size}px;border-radius:50%;flex:0 0 auto;object-fit:cover;`
    + "background:var(--control)";
  img.onerror = () => img.replaceWith(disc());
  return img;
}

/** Render the signed-in chip into `btn` (avatar + name + chevron). */
export function renderChip(btn: HTMLButtonElement, identity: ChipIdentity): void {
  btn.textContent = "";
  // Set properties individually rather than appending to `cssText`: the button already carries
  // inline styles from the toolbar, and `cssText +=` would re-append these declarations on every
  // re-render, growing the attribute without bound.
  Object.assign(btn.style, {
    display: "inline-flex", alignItems: "center", gap: "7px",
    paddingLeft: "5px", maxWidth: "220px",
  });
  const name = identity.displayName || identity.username;
  btn.append(avatarEl(identity));
  const label = document.createElement("span");
  label.textContent = name;
  label.style.cssText = "overflow:hidden;text-overflow:ellipsis;white-space:nowrap";
  btn.append(label);
  if (identity.isAdmin) {
    const badge = document.createElement("span");
    badge.textContent = "admin";
    badge.style.cssText = "font-size:9px;text-transform:uppercase;letter-spacing:.04em;padding:1px 5px;"
      + "border-radius:999px;background:var(--accent-soft);color:var(--accent);flex:0 0 auto";
    btn.append(badge);
  }
  const chev = document.createElement("span");
  chev.textContent = "▾"; chev.style.cssText = "opacity:.6;flex:0 0 auto";
  btn.append(chev);
  btn.setAttribute("aria-label", `Account: ${name}`);
  btn.title = identity.tierLabel ? `${name} — ${identity.tierLabel} plan` : name;
}

/** The larger identity block at the top of the profile panel. */
export function identityHeader(identity: ChipIdentity, subtitle: string): HTMLElement {
  const wrap = document.createElement("div");
  wrap.style.cssText = "display:flex;align-items:center;gap:12px;padding:2px 0 8px";
  wrap.append(avatarEl(identity, 44));
  const col = document.createElement("div");
  col.style.cssText = "display:flex;flex-direction:column;gap:2px;min-width:0";
  const nm = document.createElement("strong");
  nm.textContent = identity.displayName || identity.username;
  nm.style.cssText = "font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap";
  const sub = document.createElement("span");
  sub.className = "meta";
  sub.innerHTML = escapeHtml(subtitle);
  col.append(nm, sub);
  wrap.append(col);
  return wrap;
}
