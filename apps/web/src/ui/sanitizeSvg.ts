/** Sanitise server-rendered SVG before it is inserted into the DOM.
 *
 *  Why this exists: the drawings pane renders a sheet by fetching SVG from the API and assigning it
 *  straight to `innerHTML`. SVG is not inert — `<script>`, `<foreignObject>`, `on*` handlers and
 *  `href="javascript:"` all execute when parsed into the live document. That SVG is generated from
 *  the project's IFC model, and IFC files arrive from consultants, subs and clients, so a hostile
 *  model that smuggled markup through any one unescaped interpolation in the generator would become
 *  stored XSS for every user who opens the sheet.
 *
 *  The generator does escape its text nodes today. This is the second half of that defence: it makes
 *  the viewer safe by construction, so a future unescaped interpolation server-side is a rendering
 *  bug rather than an account compromise. Parse inertly, strip anything executable, then adopt.
 */

/** Elements that can execute script or embed arbitrary HTML, and have no place in a drawing sheet. */
const FORBIDDEN_TAGS = new Set([
  "script", "foreignobject", "iframe", "embed", "object", "link", "meta", "base", "handler",
  "audio", "video", "animate", "animatetransform", "animatemotion", "set", "use",
]);

/** Attributes carrying a URL, which must be scheme-checked rather than trusted. */
const URL_ATTRS = new Set(["href", "xlink:href", "src", "from", "to", "values", "attributename"]);

function isSafeUrl(v: string): boolean {
  const probe = v.trim().replace(/[^\x21-\x7E]/g, "").toLowerCase();
  if (!probe) return true;
  if (probe.startsWith("#") || probe.startsWith("/")) return true;      // fragment / same-origin
  if (/^(https?):/.test(probe)) return true;
  return !/^[a-z][a-z0-9+.-]*:/.test(probe);                            // reject javascript:, data:, …
}

function scrub(el: Element): void {
  for (const child of Array.from(el.children)) {
    if (FORBIDDEN_TAGS.has(child.tagName.toLowerCase())) {
      child.remove();
      continue;
    }
    scrub(child);
  }
  for (const attr of Array.from(el.attributes)) {
    const name = attr.name.toLowerCase();
    // every event handler, however the parser cased it
    if (name.startsWith("on")) {
      el.removeAttribute(attr.name);
      continue;
    }
    if (URL_ATTRS.has(name) && !isSafeUrl(attr.value)) {
      el.removeAttribute(attr.name);
    }
  }
}

/** Parse `svgText` inertly, strip everything executable, and return markup safe to assign to
 *  `innerHTML`. Returns "" when the payload does not parse as SVG. */
export function sanitizeSvg(svgText: string): string {
  // image/svg+xml parses into an inert document: no scripts run, no network fetches are issued.
  const doc = new DOMParser().parseFromString(svgText, "image/svg+xml");
  if (doc.getElementsByTagName("parsererror").length) return "";
  const root = doc.documentElement;
  if (!root || root.tagName.toLowerCase() !== "svg") return "";
  scrub(root);
  return new XMLSerializer().serializeToString(root);
}
