/** Installing a cost-database vintage: what to say, and what it costs.
 *
 *  `POST /cost/datasets/import` builds the offline public cost baseline and had **no client method
 *  at all**. Meanwhile `GET /cost/datasets` is called on every budget panel and returns
 *  `available_public` — what the importer could build — so the card has been telling cost managers
 *  *"1 offline baseline(s) installable — no subscription"* while the app offered no way to install
 *  one. A promise with no affordance, and the promise was added by the change that declared the
 *  field.
 *
 *  The action is **platform-admin only** and the reason is the blast radius, not tidiness:
 *  importing flips the global `is_latest`, which reprices every unpinned project's estimate. So it
 *  belongs in Profile & settings → Administration, and the budget card names the role rather than
 *  offering a button that would 403 for the person most likely to click it.
 *
 *  Pure, so the wording and the consequence text are testable without a dialog.
 */

/** One entry of `costDatasets().available_public`. */
export interface AvailableVintage { source_set?: string; origin?: string; tier?: string; note?: string }

/**
 * The budget card's line about what can be installed, or `null` when nothing can be.
 *
 * It names the ROLE rather than offering an action, because the reader of a project budget card is
 * usually not a platform administrator, and a button that 403s is worse than a sentence that tells
 * you who to ask — the same mistake the saved-view delete picker had been making.
 */
export function installableNote(available: AvailableVintage[] | undefined): string | null {
  const n = available?.length ?? 0;
  if (!n) return null;
  const note = available?.[0]?.note;
  return `${n} offline baseline${n === 1 ? "" : "s"} installable by a platform administrator`
    + " — no subscription" + (note ? ` (${note})` : "");
}

/**
 * What the administrator is agreeing to. The blast radius goes in the confirmation, not in a
 * docstring nobody reading the dialog can see: this is a global, cross-project repricing, and a
 * cost manager who pinned their project's vintage is the only one insulated from it.
 */
export function importConfirmText(): string {
  return "Build the offline public cost vintage and make it the latest?\n\n"
    + "Every project that has NOT pinned a vintage will reprice against it — this is a "
    + "server-wide change, not a change to one project.\n\n"
    + "Projects with a pinned vintage are unaffected. The build is idempotent: running it again "
    + "for the same period replaces that vintage rather than adding another.";
}

/** What to report once it lands. `warning` is the server's own — surfaced, never swallowed. */
export function importedSummary(r: { name?: string; vintage?: number; quarter?: number | null;
                                     warning?: string | null }): string {
  const label = r.name
    || (r.vintage != null ? `${r.vintage}${r.quarter ? ` Q${r.quarter}` : ""}` : "new vintage");
  return `Installed ${label} and set it as latest.${r.warning ? ` Note: ${r.warning}` : ""}`;
}
