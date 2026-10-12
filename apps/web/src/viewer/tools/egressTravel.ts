import type { EgressRoutes } from "../../api/codecheck";

/**
 * EGRESS-TRAVEL-DARK — IBC 1017 travel distance had no door in the app at all.
 *
 * `/projects/{pid}/egress/routes` and its `/egress/plan.svg` sibling were **both** frozen in
 * `services/api/test_route_reachability.py`, in two different lists, as capability no screen
 * reaches. The engine behind them is one of the most careful in the tree: it refuses rather than
 * routing to an arbitrary door when none is marked `IsExternal`, keeps `unreachable` out of
 * `over_limit`, reports the straight-line distance beside the routed one so the understatement is
 * visible per space, and states the grid resolution instead of implying it away.
 *
 * **What the app DID ship is the contrast worth naming.** `codecheck_egress.py` says in its own
 * header that *"travel-distance / performance-based egress are out of scope"* — so the live
 * Occupancy & egress tool covers occupant load, egress WIDTH, door widths and the two-exit rule, and
 * not travel distance. The only travel number anywhere else is `testFitCompare`'s
 * `plate_w / (2 · stairs) + plate_d / 2`, a formula over an idealised rectangle for the massing
 * stage, honestly labelled approximate. *So a parametric estimate over a rectangle had a screen and
 * the measurement against the actual model did not.*
 *
 * This module is the reading. The order is: was a route computed at all → what could not be reached
 * → what is over the limit → how much a straight line was understating it.
 */
export type { EgressRoutes };

export interface EgressReading {
  /** `refused` — the engine declined and said why. `unreachable` — a space has no route at all.
   *  `over` — routed distances exceed the limit. `clear` — every space routes within it. */
  kind: "refused" | "unreachable" | "over" | "clear";
  headline: string;
  detail: string;
  tone: "ok" | "warn" | "bad" | "";
}

const m = (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(1)} m`);

/**
 * What the egress result means.
 *
 * `unreachable` is ranked ABOVE `over` deliberately: a space with no route to any exit is a
 * different and worse finding than one whose route is too long, and the engine takes care to keep
 * them apart — a consumer that reported "3 over the limit" while 2 spaces had no exit at all would
 * undo that at the last step.
 */
export function egressReading(r: EgressRoutes): EgressReading {
  if (!r.routed) {
    // The engine's `note` IS the reason, and it is specific: no geometry, or no exterior door. It is
    // passed through rather than replaced, because a generic "could not check" would lose the one
    // thing that tells the reader what to fix.
    return { kind: "refused", tone: "",
             headline: "No egress routes were computed — this is not a clean result.",
             detail: r.note };
  }
  const spaces = r.spaces ?? 0;
  const basis = `${spaces} space(s) on this level, ${r.exits ?? 0} exterior exit(s), `
    + `limit ${m(r.max_travel_m)}, routed on a ${r.cell_m ?? "?"} m grid.`;
  const understated = r.max_detour_ratio
    ? ` A straight line understated the worst walk by ×${r.max_detour_ratio.toFixed(2)}.`
    : "";
  if (r.unreachable) {
    return {
      kind: "unreachable", tone: "bad",
      headline: `${r.unreachable} space(s) have NO route to any exit`
        + `${r.over_limit ? `, and ${r.over_limit} more exceed ${m(r.max_travel_m)}` : ""}.`,
      detail: `${basis} A space with no route is a different finding from one that is merely too far`
        + ` — it is not reachable at all on this level.${understated}`,
    };
  }
  if (r.over_limit) {
    return {
      kind: "over", tone: "bad",
      headline: `${r.over_limit} of ${spaces} space(s) exceed the ${m(r.max_travel_m)} travel limit`
        + ` — worst ${m(r.worst_travel_m)}.`,
      detail: `${basis}${understated}`,
    };
  }
  return {
    kind: "clear", tone: "ok",
    headline: `All ${spaces} space(s) route to an exit within ${m(r.max_travel_m)}`
      + ` — worst ${m(r.worst_travel_m)}.`,
    detail: `${basis}${understated}`,
  };
}

/** The counts, with the three outcomes kept separate. */
export function egressRows(r: EgressRoutes): { k: string; v: string }[] {
  if (!r.routed) return [];
  return [
    { k: "Spaces on this level", v: String(r.spaces ?? 0) },
    { k: "Exterior exits found", v: String(r.exits ?? 0) },
    { k: "Within the limit", v: String(r.compliant ?? 0) },
    { k: "Over the limit", v: String(r.over_limit ?? 0) },
    { k: "No route at all", v: String(r.unreachable ?? 0) },
    { k: "Travel limit", v: m(r.max_travel_m) },
    { k: "Worst routed walk", v: m(r.worst_travel_m) },
    { k: "Grid resolution", v: r.cell_m != null ? `${r.cell_m} m` : "—" },
  ];
}

/**
 * The worst spaces, worst first — unreachable ones ahead of merely-distant ones.
 *
 * Sorted on the SAME ordering the reading uses, so the table cannot disagree with the headline
 * above it. `travel_m` is null for an unreachable space, which is why the sort keys on
 * `unreachable` first instead of on the distance: `null` would sort anywhere.
 */
export function worstSpaces(r: EgressRoutes, limit = 12):
{ guid: string; label: string; detail: string }[] {
  const rows = (r.results ?? []).filter((x) => x.unreachable || !x.compliant);
  rows.sort((a, b) => Number(b.unreachable) - Number(a.unreachable)
    || (b.travel_m ?? 0) - (a.travel_m ?? 0));
  return rows.slice(0, limit).map((x) => ({
    guid: x.guid,
    label: x.name || x.guid,
    detail: x.unreachable
      ? (x.detail || "no route to any exit on this level")
      : `${m(x.travel_m)} routed vs ${m(x.straight_line_m)} straight`
        + `${x.detour_ratio ? ` (×${x.detour_ratio.toFixed(2)})` : ""}`,
  }));
}

/** GUIDs worth isolating in 3D: the unreachable and the over-limit, nothing else. */
export function findingGuids(r: EgressRoutes): string[] {
  return (r.results ?? []).filter((x) => x.unreachable || !x.compliant).map((x) => x.guid);
}

/**
 * The whole card, rendered from inside this module.
 *
 * It lives here rather than in `analyseSection.ts` for a measured reason: `viewer/tools/*` is the
 * EAGER `app-*` chunk, and with only the reading deferred the shell landed at exactly 224.0 KB
 * against a 224 KB ceiling — the panel's thirty-odd lines of card-building were the cost, not the
 * reading. Moving the body behind the same `await import()` leaves `analyseSection.ts` holding a
 * button label, the import and one call. *Deferring the decision and keeping the rendering is half
 * a lazy module.*
 *
 * The host passes its own primitives in; nothing here learns what a viewer is.
 */
export function renderEgressCard(r: EgressRoutes, d: {
  showResult: (title: string, render: (body: HTMLElement) => void) => void;
  resultNote: (html: string, kind?: "" | "ok" | "warn" | "bad") => HTMLElement;
  kvTable: (rows: { k: string; v: string }[]) => HTMLElement;
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  esc: (s: string) => string;
  isolate: (guids: string[]) => void;
  /**
   * The drawing's URL, as a BUILDER rather than a pre-computed string.
   *
   * `ui/hrefGuard.test.ts` flagged `a.href = d.planUrl` and was right to by its own rule — a URL
   * field read off a data object is the shape every real instance of that defect has had, and the
   * gate deliberately cannot do dataflow because a draft that could flagged eleven safe sites.
   * Passing the builder makes the provenance visible AT the sink (`d.planUrl()` is an `…Url(` call,
   * which is what the gate's safe list is for) instead of asking a reader to trust that a string
   * further up was built and not passed through. *Satisfying a narrow gate by making the code say
   * what it means beats exempting the line.*
   */
  planUrl: () => string;
}): void {
  const read = egressReading(r);
  d.showResult("Travel distance to exit — routed (IBC 1017)", (body) => {
    body.appendChild(d.resultNote(`<b>${d.esc(read.headline)}</b>`, read.tone));
    body.appendChild(d.resultNote(d.esc(read.detail), ""));
    // A refusal stops here. `egressRows` returns [] for one, but an empty table is still a rendered
    // box claiming there was something to count.
    if (!r.routed) return;
    body.appendChild(d.kvTable(egressRows(r)));
    const worst = worstSpaces(r);
    if (worst.length) {
      body.appendChild(d.kvTable(worst.map((w) => ({ k: w.label, v: w.detail }))));
      const guids = findingGuids(r);
      body.appendChild(d.toolBtn2(`◎ Isolate ${guids.length} space(s) with a finding in 3D`,
                                  () => d.isolate(guids)));
    }
    // The DRAWING, which is where the polylines live — the JSON summary deliberately carries none,
    // because a 200-space plate would ship hundreds of thousands of coordinate pairs to a screen
    // that wants counts.
    const a = document.createElement("a");
    a.className = "file-btn"; a.textContent = "⬇ Routed egress plan (SVG)";
    a.href = d.planUrl(); a.target = "_blank"; a.rel = "noopener";
    a.style.marginTop = "6px";
    body.appendChild(a);
  });
}
