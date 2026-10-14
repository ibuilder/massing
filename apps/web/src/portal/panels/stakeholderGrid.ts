import type { StakeholderAnalysis, StakeholderBrief } from "../../api/types";
import { escapeHtml as esc } from "../../ui/feedback";

/**
 * STAKEHOLDER-MEDIUM — the Mendelow grid, and the three things a wall of "Monitor" can mean.
 *
 * `services/api/src/aec_api/stakeholder.py` turns the stakeholder register into a power/interest
 * grid so a PM knows who to manage closely and which high-power parties are blockers. **No screen
 * called it**, and when one does, three things about that grid have to be said out loud:
 *
 * **① `Medium` is a declared option that a 2×2 cannot hold.** The register scores `power` and
 * `interest` as three-option selects (High / Medium / Low) and Mendelow splits once, so Medium
 * lands on the LOW side of both axes: a party assessed Medium/Medium is advised *"monitor with
 * minimal effort"*. That may be the right policy; what it must not be is invisible. Medium/Medium
 * is also the most likely assessment for most parties, so the common case is the one that looks
 * like a finding.
 *
 * **② Unassessed is not low.** A record with no power or no interest used to fall through the same
 * default branch — so a register nobody had filled in read as "everybody is low priority and
 * there are no blockers". *The default branch of a 2×2 is not a place to put "unknown".*
 *
 * **③ A Medium-power blocker was never mentioned.** `high_power_blockers` demands `power ===
 * "High"`, and on a three-level scale the party a PM most needs warning about is often the one at
 * Medium. The engine now lists every blocker with its level; the high-power list is still there as
 * the subset it always was.
 */

/** Blockers ordered by how loudly they need saying: High, then Medium, then Low, then unassessed. */
export function blockerRows(a: StakeholderAnalysis): StakeholderBrief[] {
  const rank = (b: StakeholderBrief) => {
    const i = a.grid.levels.indexOf(b.power ?? "");
    return i === -1 ? a.grid.levels.length : i;      // unassessed sorts last, not first
  };
  return [...a.blockers].sort((x, y) => rank(x) - rank(y));
}

/**
 * The headline, in the states the register can be in. Returns a value so each is assertable.
 *
 * `bad` only for a blocker, because a blocker is the one thing on this screen that is somebody's
 * problem today. `warn` when the grid could not place everybody, or when nothing has been
 * assessed at all — a grid over nothing is not a clean grid.
 */
export function gridReading(a: StakeholderAnalysis): { text: string; tone: "ok" | "warn" | "bad" } {
  const g = a.grid;
  if (!a.total) return { text: "No active stakeholders recorded.", tone: "warn" };
  if (!a.assessed) {
    return { text: `NONE ASSESSED — all ${a.total} active stakeholder(s) are missing a power or `
                 + "an interest level, so the grid places none of them.", tone: "warn" };
  }
  const mediums = (g.by_level.power.Medium ?? 0) + (g.by_level.interest.Medium ?? 0);
  const parts: string[] = [`${a.assessed} of ${a.total} assessed`];
  if (g.unassessed) parts.push(`${g.unassessed} not assessed`);
  if (mediums) parts.push(`${mediums} Medium score(s) sit on the LOW side of a 2×2 split at ${g.high_level}`);
  if (a.blockers.length) {
    const hp = a.high_power_blockers.length;
    parts.push(`${a.blockers.length} blocker(s)${hp ? ` · ${hp} at ${g.high_level} power` : ""}`);
  }
  return { text: parts.join(" · "), tone: a.blockers.length ? "bad" : g.unassessed ? "warn" : "ok" };
}

/** Render the card into `host` — a slot the caller appended before awaiting. */
export async function renderStakeholderGrid(
  api: { stakeholderAnalysis(pid: string): Promise<StakeholderAnalysis> },
  host: HTMLElement,
  pid: string,
): Promise<void> {
  let a: StakeholderAnalysis;
  try { a = await api.stakeholderAnalysis(pid); }
  catch { return; }                         // the grid is advisory; never a banner over the matrix
  if (!host.isConnected) return;            // PR #527: `ctx.root` belongs to whoever rendered last

  const read = gridReading(a);
  const css = read.tone === "bad" ? "var(--status-crit)"
    : read.tone === "warn" ? "var(--status-warn)" : "var(--status-good)";
  // ALL FIVE rows, including the zeros. A quadrant that is absent reads as "not applicable" and a
  // quadrant showing 0 reads as "nobody is here", which are different facts — and "Not assessed: 0"
  // is the one a PM most needs to be able to see.
  const QUADS = ["manage_closely", "keep_satisfied", "keep_informed", "monitor", "unassessed"];
  const rows = QUADS.map((k) => a.quadrants[k])
    .filter((q): q is NonNullable<typeof q> => !!q)
    .map((q) => `<tr><td><b>${esc(q.label)}</b></td><td style="text-align:right">${q.count}</td>`
      + `<td class="meta">${esc(q.advice)}</td></tr>`).join("");

  host.className = "dash-card";
  host.style.margin = "0 0 8px";
  host.innerHTML = `<div><b>🫱 Stakeholders (power / interest)</b></div>`
    + `<div class="meta" style="margin-top:2px;color:${css}">${esc(read.text)}</div>`
    + `<table class="mini" style="margin-top:6px"><tbody>${rows}</tbody></table>`
    + (a.blockers.length
      ? `<div class="meta" style="margin-top:6px"><b>Blockers</b>: `
        + blockerRows(a).map((b) => `${esc(b.name || b.ref || "(unnamed)")}`
          + ` <span style="opacity:.7">(${esc(b.power || "power not recorded")})</span>`).join(", ")
        + `</div>`
      : "")
    + `<div class="meta" style="margin-top:6px">${esc(a.grid.reason)}</div>`;
}
