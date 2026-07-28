/**
 * URL vetting for attachment references.
 *
 * An attachment URL is *untrusted input*. It arrives on a markup record, and markup records come
 * from other people — loaded from the server, imported from a file, or synced from a colleague's
 * device. A record carrying `url: "javascript:…"` turns a reviewer clicking an attachment into
 * script execution in the application's origin, with whatever session the reviewer holds.
 *
 * Written as an allowlist. Rejecting known-bad schemes fails to the *permissive* side, and the
 * evasions are endless: a NUL spliced into "javascript" stops the string matching a blacklist, and
 * also stops it parsing as a scheme — so it resolves as a relative path and comes back as a
 * perfectly innocent-looking https URL. Deciding what is allowed leaves nothing to enumerate.
 */

/**
 * Characters a browser discards before reading a scheme.
 *
 * C0 controls and DEL are stripped from a URL during parsing, so a value with a tab or newline
 * spliced into the middle of "javascript" still navigates as javascript. Whitespace goes too: a
 * space is not legal in a scheme, so `java script:` would otherwise be judged as a relative path
 * rather than as the evasion it is.
 */
// eslint-disable-next-line no-control-regex -- matching control characters is the point
const IGNORED = /[\u0000-\u0020\u007f]/g;

/** Scheme of a URL once the characters a parser ignores are removed, or `null` if it is relative. */
function schemeOf(url: string): string | null {
  const flat = url.replace(IGNORED, "").toLowerCase();
  return /^([a-z][a-z0-9+.-]*):/.exec(flat)?.[1] ?? null;
}

/**
 * Media types that cannot carry a script.
 *
 * `image/svg+xml` is deliberately absent. An SVG is a document: it can hold a `<script>`, which is
 * inert inside an `<img>` but runs if the same URL is ever opened in a tab. Allowing it in one
 * policy and not the other is the kind of distinction that survives exactly until someone passes
 * the value to the wrong function.
 */
const INERT_DATA = /^data:(image\/(png|jpeg|gif|webp|avif|bmp)|audio\/[\w.+-]+|video\/[\w.+-]+|application\/pdf)[;,]/i;

/** Resolve a relative or http(s) reference against the page. */
function httpUrl(url: string): string | null {
  try {
    const base = typeof document !== "undefined" ? document.baseURI : "https://localhost/";
    const parsed = new URL(url, base);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
}

/**
 * Vet a URL for `<img>`, `<audio>` or `<video>` `src`.
 *
 * Permits `http(s)`, relative references, `blob:` — same-origin by construction, and how a local
 * file preview works — and `data:` for media types that cannot execute.
 *
 * @returns the URL to load, or `null` if it must not be loaded.
 */
export function safeMediaUrl(url: string | undefined): string | null {
  if (!url) return null;
  const trimmed = url.trim();
  switch (schemeOf(trimmed)) {
    case null:
    case "http":
    case "https":
      return httpUrl(trimmed);
    case "blob":
      return trimmed;
    case "data":
      return INERT_DATA.test(trimmed.replace(IGNORED, "")) ? trimmed : null;
    default:
      return null;
  }
}

/**
 * Vet a URL for opening as a document — a new tab, or anything that navigates.
 *
 * Stricter than {@link safeMediaUrl}: a document context executes script, so `data:` is refused
 * outright rather than filtered by type. Browsers already block top-level `data:` navigation, so
 * permitting it buys a caller nothing and costs the one place where a mis-sniffed type would
 * become script execution.
 *
 * @returns the URL to open, or `null` if it must not be opened.
 */
export function safeNavigableUrl(url: string | undefined): string | null {
  if (!url) return null;
  const trimmed = url.trim();
  switch (schemeOf(trimmed)) {
    case null:
    case "http":
    case "https":
      return httpUrl(trimmed);
    case "blob":
      return trimmed;
    default:
      return null;
  }
}
