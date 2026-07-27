/**
 * Who is signed in, as far as *locally stored data* is concerned.
 *
 * This product stores three kinds of thing on the device: cached record lists (fast reads), queued
 * field captures, and queued file uploads. The last two are **unsent work**. All three share one
 * hazard — the machine is often shared. A tablet in a site trailer gets passed between trades, and a
 * kiosk gets used by whoever is standing at it.
 *
 * So every locally stored item is tagged with the identity that created it, and read back through
 * that tag. The tag is not an authorization decision — the server authorizes every real request.
 * It is what keeps the *offline* paths from showing, or acting on, someone else's data before any
 * request has been made.
 */

/**
 * A short, stable, non-reversible tag for a session token.
 *
 * FNV-1a, not a cryptographic hash. The input is a high-entropy token and the output lives in
 * enumerable storage keys, so the requirement is "not reversible into the token", which this meets;
 * the security boundary itself is elsewhere.
 */
export function identityScope(token: string): string {
  if (!token) return "anon";
  let h = 0x811c9dc5;
  for (let i = 0; i < token.length; i++) {
    h ^= token.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(36);
}

/**
 * The tag for whoever is signed in right now.
 *
 * Reads the persisted token directly rather than taking an `ApiClient`, so the queues — which are
 * plain storage modules with no client — can tag and filter without one being threaded through.
 * `aec-token` is the canonical persisted location, written by `HttpCore.setToken`.
 */
export function currentIdentity(): string {
  try { return identityScope(localStorage.getItem("aec-token") || ""); } catch { return "anon"; }
}

/**
 * Whether a stored item belongs to the current session.
 *
 * **Untagged items count as yours.** They predate this tagging, so there is no way to know whose
 * they are — and the two honest options are to show them to everyone (what already happened before
 * this change) or to hide them from everyone (which strands unsent work with no way to recover it).
 * Guessing an owner would be worse than either: it would attribute one person's field photos to
 * whoever happened to sign in next, which is the exact failure this whole mechanism exists to stop.
 *
 * So legacy entries keep their existing behaviour, they are never reassigned, and the untagged set
 * drains to nothing as queues flush. Everything created from here on is tagged.
 */
export function ownedByMe(owner: string | undefined, me: string): boolean {
  return owner === undefined || owner === me;
}
