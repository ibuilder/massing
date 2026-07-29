/**
 * R26-VITALS — the six numbers along the bottom.
 *
 * **LOD · area · $/ft² · float · IRR · health.**
 *
 * The redesign audit's finding 13: ten 3D viewport controls (Fit, Grid, Section, Orbit, Snap, Units…)
 * were pinned to the bottom of *every* room, including the four with no viewport to orbit, section or
 * snap in — "ten permanent controls, irrelevant on four of seven tabs, occupying the most valuable
 * strip of the window". Its prescription was to give that strip to these six instead, described as
 * *"the only continuous proof of the one-model claim"*. Three of the prototype's four pillars shipped
 * in v0.3.7xx; this is the fourth, and it is why the app did not look like the prototype.
 *
 * All six arrive from **one** endpoint (`GET /projects/{pid}/vitals`). That is not a performance
 * choice: the same audit's finding 03 is that the app contradicts itself on screen — the same project
 * scored 24 for model health in one workspace and 77 in another. Six client fetches would rebuild
 * exactly that.
 *
 * **An absent number renders as an em-dash with its reason in the tooltip, never as `0`.** A zero
 * float reads as "no slack" and a zero IRR reads as "worthless"; both are lies about a project that
 * simply has not been scheduled or underwritten. The distinction is the whole point of the strip: it
 * claims to prove the model is one thing, so a fabricated number in it discredits everything else.
 */

/** One vital as the API returns it. `value === null` means "not yet", and `note` says why. */
export interface Vital {
  value: number | string | null;
  unit: string;
  note?: string | null;
  band?: string | null;
}

export interface VitalsPayload {
  order: string[];
  [key: string]: Vital | string[] | undefined;
}

/** Short labels — the strip is scanned, not read. */
const LABEL: Record<string, string> = {
  lod: "LOD", area: "Area", cost_sf: "$/ft²", float: "Float", irr: "IRR", health: "Health",
};

/** Compact 12 500 → "12.5k", 1 240 000 → "1.24M". A bottom strip has no room for thousands separators. */
export function compact(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return (n / 1_000_000).toFixed(2).replace(/\.?0+$/, "") + "M";
  if (abs >= 1_000) return (n / 1_000).toFixed(1).replace(/\.0$/, "") + "k";
  return String(Math.round(n * 100) / 100);
}

/**
 * The text for one cell.
 *
 * Returns the em-dash for `null` — deliberately not "0", "n/a" or "—%" — so a missing number cannot
 * be mistaken for a measured one at a glance.
 */
export function cellText(key: string, v: Vital | undefined): string {
  if (!v || v.value === null || v.value === undefined) return "—";
  const val = typeof v.value === "number" ? compact(v.value) : String(v.value);
  // The unit goes where a reader expects it: currency and LOD lead, everything else trails.
  if (key === "cost_sf") return "$" + val;
  if (key === "lod") return "LOD " + val;
  if (v.unit === "%") return val + "%";
  return val + (v.unit ? " " + v.unit : "");
}

/** Tooltip: the reason when there is no number, the full precision when there is. */
export function cellTitle(key: string, v: Vital | undefined): string {
  const label = LABEL[key] ?? key;
  if (!v || v.value === null || v.value === undefined) {
    return `${label} — ${v?.note || "not available yet"}`;
  }
  return `${label}: ${v.value}${v.unit && v.unit !== "%" ? " " + v.unit : v.unit || ""}`;
}

/**
 * Render the strip into `host`, replacing its contents.
 *
 * Renders **nothing** when there is no payload — an empty six-cell skeleton on a project that has not
 * loaded would be six em-dashes claiming to be measurements.
 */
export function renderVitals(
  host: HTMLElement,
  data: VitalsPayload | null,
  onPick?: (key: string) => void,
): void {
  host.innerHTML = "";
  const order = data?.order;
  host.hidden = !order || !order.length;
  if (!order || !order.length) return;

  for (const key of order) {
    const v = data![key] as Vital | undefined;
    const cell = document.createElement(onPick ? "button" : "span");
    cell.className = "vit" + (v?.band ? ` vit-${v.band}` : "") +
      (!v || v.value === null || v.value === undefined ? " vit-empty" : "");
    cell.title = cellTitle(key, v);

    const lbl = document.createElement("span");
    lbl.className = "vit-k";
    lbl.textContent = LABEL[key] ?? key;

    const val = document.createElement("span");
    val.className = "vit-v";
    // textContent throughout: these are server numbers, and this strip renders on every screen.
    val.textContent = cellText(key, v);

    cell.append(lbl, val);
    if (onPick) {
      (cell as HTMLButtonElement).type = "button";
      cell.addEventListener("click", () => onPick(key));
    }
    host.appendChild(cell);
  }
}
