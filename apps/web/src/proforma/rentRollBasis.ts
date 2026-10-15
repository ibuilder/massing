/**
 * RENTROLL-BASIS — 30% occupancy reads as 100% when the building's area is unset.
 *
 * `rentroll.summarize` computes
 * `total_rentable = building_rentable_sf if building_rentable_sf else occupied_sf`, and
 * `rentroll.rent_roll` sources that area from `project.dev_property["sqft"]` — a field nobody is
 * obliged to fill. When it is missing the DENOMINATOR becomes the numerator.
 *
 * Measured on the engine, same two leases both times:
 *
 * | building area | total_rentable_sf | occupied_sf | vacant_sf | occupancy_pct |
 * |---|---|---|---|---|
 * | 20,000 sf | 20,000 | 6,000 | 14,000 | **30.0%** |
 * | unset | 6,000 | 6,000 | 0 | **100.0%** |
 *
 * `occupancy_pct` was the only one of those four the client declared, so the Operations card
 * printed **"Occupancy 100%"** with no vacancy row and no basis — and could not have shown the
 * basis, because the fields that carry it were undeclared. RESPKEY-HOP2 is what made them visible.
 *
 * **It does not stop at the screen, which is the part that matters.** `occupancy_pct` is a KPI in
 * the rent-roll PDF (`report_builders/finance.py`), it is passed into the income basis
 * (`proforma/income_basis.py`) and into the assistant's project snapshot. A figure that leaves the
 * building as a lender-facing KPI is a different class of wrong from a caption.
 *
 * **Why the client cannot work this out for itself.** With the basis unpublished, "unknown building
 * area" and "a fully leased building" produce the SAME numbers — `total_rentable_sf ===
 * occupied_sf`, `vacant_sf === 0`, `occupancy_pct === 100`. That is SQL-CAP's shape exactly: *an
 * equality cannot separate two equal things*, so the server states `occupancy_basis` as a fact and
 * the fallback here refuses to guess rather than guessing wrong.
 *
 * **The number is kept and the presentation refuses**, following WF-BASIS: the payload still
 * carries `occupancy_pct` for every existing consumer, and no screen prints it bare. 100% of the
 * leased area is leased — a true statement, and a vacuous one.
 */

/** Which denominator the percentage was computed against. `"leased"` means there wasn't one. */
export type OccupancyBasis = "building" | "leased" | "unknown";

/** The fields these functions READ, not the whole response — `api/proforma.ts` declares that, and
 *  declaring it twice is what `api/noRespelledShapes.test.ts` refuses. A narrow parameter view is
 *  deliberate: every field here is optional so the functions stay total over a response that
 *  predates `occupancy_basis`, and that fallback is reachable rather than decorative. */
export interface RentRollBasisFields {
  occupancy_pct?: number;
  total_rentable_sf?: number;
  occupied_sf?: number;
  vacant_sf?: number;
  /** The server's own answer. Preferred over anything derived, because nothing CAN be derived. */
  occupancy_basis?: OccupancyBasis | string;
  /** The project's rentable area as supplied, or null when it was not set. */
  building_rentable_sf?: number | null;
  /** The engine's sentence about the basis. Preferred over the wording below. */
  occupancy_note?: string;
}

/**
 * The basis, from the server, or `"unknown"`.
 *
 * The fallback deliberately does NOT infer `"leased"` from `total_rentable_sf === occupied_sf`: a
 * genuinely full building reports exactly that, so the inference would relabel every fully leased
 * asset as unmeasured. Reporting `"unknown"` costs a hedged sentence; guessing costs the truth
 * about a real building.
 */
export function occupancyBasis(rr: RentRollBasisFields): OccupancyBasis {
  const b = rr.occupancy_basis;
  return b === "building" || b === "leased" ? b : "unknown";
}

const num = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;

const sf = (v: unknown): string => {
  const n = num(v);
  return n === null ? "—" : `${Math.round(n).toLocaleString("en-US")} sf`;
};

/**
 * What goes in the Occupancy cell. Never a bare percentage on an unmeasured basis.
 *
 * On `"leased"` the figure is 100% by construction and says nothing, so the cell says `n/a`. On
 * `"unknown"` the figure may be right and may be the same artefact, so it is shown with a mark.
 */
export function occupancyText(rr: RentRollBasisFields): string {
  const pct = num(rr.occupancy_pct);
  const basis = occupancyBasis(rr);
  if (basis === "leased") return "n/a";
  if (pct === null) return "—";
  return basis === "building" ? `${pct}%` : `${pct}%†`;
}

/**
 * The sentence under the figure, or null when the basis is sound and needs no caveat.
 *
 * **The engine's own `occupancy_note` wins.** It says the same thing, `assistant.py` surfaces that
 * exact string to anyone who asks the project a question, and keeping a second copy here in another
 * language is how the two come to disagree — the hazard `api/noRespelledShapes.test.ts` refuses for
 * shapes, applied to a sentence. The local wording below is the fallback for a response that
 * predates the field, and is reachable because every field on this view is optional.
 */
export function occupancyLine(rr: RentRollBasisFields): string | null {
  const basis = occupancyBasis(rr);
  if (basis === "building") return null;
  if (basis === "leased") {
    const note = rr.occupancy_note;
    if (typeof note === "string" && note.trim()) return note.trim();
    return "Occupancy could not be computed: this project has no rentable building area, so the "
      + `denominator fell back to the leased area (${sf(rr.occupied_sf)}) and the percentage would `
      + "be 100% of itself whatever the leases say. Set the project's Rentable SF to get a real "
      + "occupancy and a real vacancy.";
  }
  // On an UNKNOWN basis the server said nothing, so there is no note to prefer -- and a note that
  // arrived without a basis could not be trusted to be about this case anyway.
  return "† The server did not say which area this percentage was computed against. If the "
    + "project's rentable area is unset it is 100% by construction — a full building and an "
    + "unmeasured one report the same numbers, so this cannot be told apart here.";
}

/** The three areas, so the denominator is on screen rather than implied by a percentage. */
export function areaRows(rr: RentRollBasisFields): { label: string; value: string }[] {
  const basis = occupancyBasis(rr);
  return [
    { label: basis === "leased" ? "Rentable area (not set)" : "Rentable area",
      value: basis === "leased" ? "—" : sf(rr.total_rentable_sf) },
    { label: "Leased area", value: sf(rr.occupied_sf) },
    { label: basis === "leased" ? "Vacant area (unknown)" : "Vacant area",
      value: basis === "leased" ? "—" : sf(rr.vacant_sf) },
  ];
}

/** Whether the occupancy figure should be rendered as a caveat rather than as a result. */
export function occupancySuspect(rr: RentRollBasisFields): boolean {
  return occupancyBasis(rr) !== "building";
}
