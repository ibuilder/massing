import { escapeHtml as esc } from "../../ui/feedback";

/**
 * R41-SCHEMA-STALE — the banner shown on a record whose stored values no longer match the
 * register's current fields.
 *
 * **Why this is its own function rather than eight lines inside `renderDetail`.** The failure it
 * reports is *an empty-looking field*, so the only honest test is one that asserts what the reader
 * actually sees — the orphaned key AND its value present in the rendered output. Inside the
 * register class that needs a constructed panel, a fake context and a live project; as a pure
 * `record -> element | null` it needs nothing, and the test can therefore assert the rendering
 * rather than assert that some source file contains a string.
 *
 * Returns `null` when there is nothing wrong, so the caller has no condition of its own to get
 * wrong and a future "always show the schema block" cannot creep in through the call site.
 */
export interface SchemaStatus {
  version: string; stored: string | null; changed: boolean; epoch_behind: boolean;
  orphaned: string[]; mistyped: string[]; stale: boolean;
}

export function schemaStaleBanner(
  schema: SchemaStatus | undefined | null,
  data: Record<string, unknown> | undefined | null,
): HTMLDivElement | null {
  if (!schema?.stale) return null;
  const d = data ?? {};
  const bits: string[] = [];

  // The orphaned values are printed WITH their contents. A banner that says "something is wrong"
  // and does not show the data leaves the reader no way to recover it: the value is unreachable
  // from the form by definition — that is what "orphaned" means — so this is the only place it
  // can still be read. `esc` on both key and value: these are user-entered strings reaching
  // innerHTML, and a register is exactly where someone pastes a supplier's HTML email.
  if (schema.orphaned.length) {
    const items = schema.orphaned
      .map((k) => `<li><code>${esc(k)}</code>: ${esc(String(d[k] ?? ""))}</li>`).join("");
    bits.push(
      `<div>${schema.orphaned.length === 1
        ? "A value is stored under a field that is no longer in this register"
        : "Values are stored under fields that are no longer in this register"}` +
      ` — not shown above:<ul>${items}</ul></div>`);
  }
  if (schema.mistyped.length) {
    bits.push(`<div>Stored in a format the field no longer accepts: ` +
      `${schema.mistyped.map((k) => `<code>${esc(k)}</code>`).join(", ")}</div>`);
  }
  // A meaning change leaves the shape intact, so there is no key to name — only the warning that
  // the numbers above may be on a different basis than the ones beside them.
  if (schema.epoch_behind) {
    bits.push(`<div>This register's fields changed meaning after this record was filed, so the ` +
      `values above may be on a different basis than newer records.</div>`);
  }

  const el = document.createElement("div");
  el.className = "portal-schema-stale";
  el.setAttribute("role", "status");
  el.innerHTML = `<b>⚠ This record predates a change to the register</b>${bits.join("")}` +
    `<div class="meta">Editing and saving re-files it against the current fields.</div>`;
  return el;
}
