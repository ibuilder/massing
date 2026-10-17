import type { ModelOptionBranch, ModelOptionDiff, ModelOptionList } from "../../api/model";

/**
 * MODELOPT-DARK — the model-option branching capability nothing could reach.
 *
 * Five routes, a `model_options` engine tested end to end in
 * `services/api/test_model_options.py`, storage, an index and integration with the undo stack —
 * and **zero references anywhere in `apps/web/src`**. Snapshot a massing as "Scheme A — steel
 * frame", keep editing, switch back undoably, diff the two: all of it worked, none of it had a
 * door.
 *
 * **Only one of the five was counted as dark.** `services/api/test_route_reachability.py` froze
 * `/model/options/{slug}/activate`; the other four fall in that gate's own documented
 * false-negative class, because its rule fires when a route's last static segment appears nowhere
 * in the web source and `options` / `diff` appear all over it. *One capability's parts, each
 * reading as somebody else's gap* — the three-way split CLASSIFY-DARK paid for, here four ways.
 *
 * ## The two numbers that must not be confused
 *
 * `diff_option` caps each GUID list at **100** and does not cap the counts, so a consumer that
 * renders `added_in_current.length` prints a page length as a total. That is TRUNC-COUNTED, which
 * this repo has now paid for on three screens, so the readings below take the count and say when
 * the list is a page of it.
 *
 * ## `identical` over two empty models is TRUE, and that is right
 *
 * The engine's own comment makes the call and explains it: the question *do these differ at the
 * IfcElement GUID-set level?* is genuinely answered "no" for two element-less models, so flipping
 * the flag would be a false alarm in the other direction. What a reader needs beside it is the
 * POPULATION — *"the fix for a vacuous truth is not always to make it false; sometimes it is to say
 * what it is true of"* — so `diffHeadline` never reports a match without the element counts it
 * matched over.
 *
 * Every function here returns PLAIN TEXT: the panel interpolates into `innerHTML`, and
 * `apps/web/src/ui/innerHtmlGuard.test.ts` is the ratchet.
 */

/** Bytes as a reader of a file list writes them. */
function size(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

/** One branch row. `current` is where you are; `available` false means the index outlived the file. */
export function branchLine(b: ModelOptionBranch): string {
  const bits = [b.name];
  if (b.current) bits.push("← current");
  if (b.available === false) bits.push("⚠ file missing");
  bits.push(b.elements == null ? "element count unavailable" : `${b.elements} element(s)`);
  bits.push(size(b.size_bytes));
  if (b.note) bits.push(b.note);
  return bits.join(" · ");
}

/**
 * The list headline, or `null` when there are no branches.
 *
 * Says explicitly when NO branch matches the working model, because that is the normal state after
 * an edit and reads as an error otherwise: the working model has moved on from every snapshot.
 */
export function branchSummary(r: ModelOptionList): string | null {
  if (!r.count) return null;
  const cur = r.options.filter((o) => o.current);
  const missing = r.options.filter((o) => o.available === false).length;
  const bits = [`${r.count} branch(es)`];
  if (cur.length === 1) bits.push(`current: ${cur[0]!.name}`);
  else if (cur.length > 1) bits.push(`${cur.length} branches are byte-identical to the working model`);
  else bits.push("the working model matches no branch — it has been edited since the last snapshot");
  if (missing) bits.push(`${missing} branch(es) have an index entry but no file`);
  return bits.join(" · ");
}

/** What re-using a name does. Said before the write, because it is not what "save" usually means. */
export function snapshotCaveat(r: ModelOptionList, name: string): string | null {
  const slug = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60);
  if (!slug) return null;
  const hit = r.options.find((o) => o.slug === slug);
  if (!hit) return null;
  return `"${hit.name}" already exists and a branch is a HEAD, not an archive — snapshotting this `
    + "name overwrites it. The edit history keeps the archaeology either way.";
}

/**
 * The diff in one line. Never reports a match without the population it matched over.
 */
export function diffHeadline(d: ModelOptionDiff): string {
  if (d.identical) {
    const n = d.current_element_count;
    return n === 0
      ? "No difference — but BOTH models carry zero IfcElement, so this is a match over nothing. "
        + "Check the models have loaded before reading it as agreement."
      : `No difference across ${n} element(s) — same GUID set, same per-class counts.`;
  }
  const bits: string[] = [];
  if (d.added_count) bits.push(`${d.added_count} added in current`);
  if (d.removed_count) bits.push(`${d.removed_count} removed in current`);
  const cls = Object.keys(d.class_deltas).length;
  if (cls) bits.push(`${cls} class(es) differ in count`);
  return `${bits.join(" · ")} — current has ${d.current_element_count} element(s), the branch `
    + `${d.option_element_count}.`;
}

/**
 * `showing N of M` for whichever GUID list is capped, or `null` when neither is.
 *
 * The cap is the server's 100 and the counts are uncapped, so this is the only thing standing
 * between the lists and being read as totals.
 */
export function diffTruncation(d: ModelOptionDiff): string | null {
  const parts: string[] = [];
  if (d.added_in_current.length < d.added_count) {
    parts.push(`${d.added_in_current.length} of ${d.added_count} added`);
  }
  if (d.removed_in_current.length < d.removed_count) {
    parts.push(`${d.removed_in_current.length} of ${d.removed_count} removed`);
  }
  if (!parts.length) return null;
  return `Showing ${parts.join(" and ")} GlobalId(s) — the server caps each list at 100 while the `
    + "counts above are complete.";
}

/** The per-class deltas, biggest movement first. Plain text. */
export function classDeltaLine(d: ModelOptionDiff, max = 8): string | null {
  const entries = Object.entries(d.class_deltas);
  if (!entries.length) return null;
  const sorted = entries.sort((a, b) => Math.abs(b[1].delta) - Math.abs(a[1].delta)
    || a[0].localeCompare(b[0]));
  const shown = sorted.slice(0, max)
    .map(([k, v]) => `${k} ${v.delta > 0 ? "+" : ""}${v.delta}`).join(" · ");
  const more = sorted.length > max ? ` · ${sorted.length - max} more class(es)` : "";
  return `By class (current − branch): ${shown}${more}`;
}

/** What activating does, said before the click rather than after. */
export function activateCaveat(b: ModelOptionBranch): string {
  return `Switching to "${b.name}" replaces the working model and republishes the viewer geometry. `
    + "It goes through the same edit-history push as any edit, so it is ONE undo step — not a "
    + "destructive action.";
}
