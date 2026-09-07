/**
 * How a reference renders in a register table — the resolve bound, the id shape, and the cell.
 *
 * Extracted from `register.ts` by COL-PAIR, which pushed that file past its extraction ratchet. A
 * genuine leaf: it builds one `<td>` from a value and a resolved map, and reaches back into the
 * register for exactly one thing — what to do when the link is clicked — which arrives as a
 * callback. It sits beside `fieldPairs.ts` because the two answer the same question from opposite
 * ends: which field a column should show, and how a reference looks once chosen.
 */
import type { ModuleDef } from "../../api/client";

/**
 * How many records of a referenced module are fetched to build the id→label map for a table.
 *
 * A bound is necessary — a reference column must not pull an unbounded register to render one page —
 * but the bound is also a correctness boundary, so it is named rather than buried as a literal. Past
 * this many records the tail of the target module is genuinely unresolvable from the client, and
 * `refCell` is required to SAY so instead of inventing a label. See MOD-SWEEP below.
 */
export const REF_RESOLVE_LIMIT = 500;

/** A record id is a `uuid.uuid4()` string server-side, so this distinguishes an id from free text. */
export const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** The id→label map a table builds once per referenced module. */
export type RefMap = Map<string, { ref: string; title: string | null }>;

/**
 * MOD-SWEEP — a reference cell that never pretends to have resolved.
 *
 * The old inline version rendered EVERY non-empty reference as a clickable link labelled
 * `String(v).slice(0, 8)`, falling back to those eight characters whenever the id was not in the
 * resolved map. Three different values took that path and all three looked identical to a working
 * link: a record deleted since it was referenced, a record past `REF_RESOLVE_LIMIT` in a large
 * register, and — the one that matters for the field sweep — a **legacy free-text value** in a field
 * that used to be `text`. Converting `coi.vendor` from text to reference would have turned
 * "Acme Electrical Inc" into a link reading `Acme Ele` that opens nothing.
 *
 * So the three cases are now distinguished, because they call for different things from the user:
 *
 * - **resolved** → the link, labelled `REF-001 · Title`, navigating on click.
 * - **an id we could not resolve** (UUID-shaped, absent from the map) → the short id, NOT a link,
 *   marked as unresolved. The record may be deleted or beyond the fetch bound; either way clicking
 *   is not the answer and offering it is a lie.
 * - **not an id at all** → the value verbatim, full length, marked as unlinked text. This is what a
 *   pre-conversion value looks like, and showing it whole is what lets someone re-link it by hand.
 *
 * Truncating to 8 characters was the specific harm in every case: it is short enough to look like an
 * id and long enough to look deliberate.
 *
 * COL-PAIR now also routes a PAIR TWIN through here — a text column whose record filled the linked
 * half instead. That value is an id and resolves normally; the three cases above are unchanged.
 */
export function refCell(
  v: string,
  c: ModuleDef["fields"][number],
  map: RefMap | undefined,
  onOpen: (module: string, id: string) => void,
): HTMLElement {
  const td = document.createElement("td");
  const info = map?.get(v);
  const target = String(c.module ?? "record").replace(/_/g, " ");
  if (info) {
    const a = document.createElement("a"); a.href = "#"; a.className = "ref-link";
    a.textContent = info.title ? `${info.ref} · ${info.title}` : info.ref;
    a.title = `Open linked ${target} ${info.ref}`;
    a.onclick = (e) => { e.preventDefault(); e.stopPropagation(); onOpen(c.module!, v); };
    td.appendChild(a);
    return td;
  }
  const span = document.createElement("span");
  if (UUID_RE.test(v)) {
    span.className = "ref-unresolved";
    span.textContent = `${v.slice(0, 8)}…`;
    span.title = `This ${target} could not be resolved — it may have been deleted, or lie beyond `
      + `the first ${REF_RESOLVE_LIMIT} records of ${target}. Not a working link.`;
  } else {
    span.className = "ref-unlinked";
    span.textContent = v;                        // in full: it is the only handle for re-linking
    span.title = `Plain text, not a link to a ${target} record. Edit the field to pick the `
      + `${target} it refers to.`;
  }
  td.appendChild(span);
  return td;
}
