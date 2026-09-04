/**
 * PROGRAMME-GANTT — the cross-project bar chart, R22-PIPELINE's last visualisation item.
 *
 * ## The roadmap said this needed a new engine. It did not.
 *
 * That entry lists "a cross-project Gantt (`schedule_viz.py` is per-project)" as genuinely missing.
 * Half true: `schedule_viz` *is* per-project, but R46's portfolio scheduler already computes
 * `project_starts` and `project_finishes` in its merged pass, and the route already puts them on the
 * wire. What was missing is that **the client type declared three scalars and dropped the rest** —
 * `programme_finish`, `project_count`, `external_link_count` — so the dates arrived in the browser
 * and were discarded before anything could draw them. The bars here are geometry over data the
 * server was already sending.
 *
 * That matters for where the dates come from. These are the finishes from the ONE merged pass, not
 * each project's standalone schedule: a project that looks comfortable alone can be critical to the
 * programme, and a bar drawn from its own CPM run would show the comfortable answer.
 *
 * ## A bar needs both ends
 *
 * A project with a start and no finish (or the reverse) gets **no bar at all**, and is returned in
 * `unplotted` with the reason. The alternative is to substitute the programme's own start or finish
 * for the missing end, which draws a bar that looks measured and is not — the same defect the risk
 * heat map refuses when it declines to render an unmeasured cell as a green zero.
 */

const DAY_MS = 86_400_000;

export type ProgrammeInput = {
  projects: { id: string; name: string; activities: number }[];
  project_starts?: Record<string, string>;
  project_finishes?: Record<string, string>;
  crossing_activities?: string[];
  external_links?: { predecessor: string; successor: string }[];
};

export type ProgrammeBar = {
  id: string; name: string; activities: number;
  start: string; finish: string;
  /** Left edge and width as percentages of the programme span, ready for a CSS bar. */
  left: number; width: number;
  days: number;
  /** This project is named by at least one external link — its dates are a commitment. */
  linked: boolean;
  /** Finishes on the programme's own finish date: it is what the whole span waits for. */
  driving: boolean;
};

export type ProgrammeBars = {
  bars: ProgrammeBar[];
  unplotted: { id: string; name: string; reason: string }[];
  span: { start: string; finish: string; days: number } | null;
};

function day(s: string | undefined): Date | null {
  if (!s) return null;
  const d = new Date(`${String(s).slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

/**
 * Bar geometry for one programme run. Pure — no DOM, no fetch — so the rules above ("a bar needs
 * both ends", "driving is measured against the programme finish") are unit-testable rather than
 * only visible on screen.
 */
export function programmeBars(r: ProgrammeInput): ProgrammeBars {
  const starts = r.project_starts ?? {};
  const finishes = r.project_finishes ?? {};
  const linked = new Set<string>();
  for (const ln of r.external_links ?? []) {
    // Link endpoints are "<project><sep><activity>"; the project id is the part before the
    // separator, and an id containing no separator is already the project.
    for (const end of [ln.predecessor, ln.successor]) {
      const p = (r.projects ?? []).find((x) => String(end).startsWith(x.id));
      if (p) linked.add(p.id);
    }
  }

  const rows: { p: ProgrammeInput["projects"][number]; s: Date; f: Date }[] = [];
  const unplotted: ProgrammeBars["unplotted"] = [];
  for (const p of r.projects ?? []) {
    const s = day(starts[p.id]), f = day(finishes[p.id]);
    if (!s && !f) { unplotted.push({ id: p.id, name: p.name, reason: "no scheduled dates" }); continue; }
    if (!s || !f) {
      // Deliberately NOT clamped to the programme span — see the header.
      unplotted.push({ id: p.id, name: p.name, reason: s ? "no finish date" : "no start date" });
      continue;
    }
    if (f < s) { unplotted.push({ id: p.id, name: p.name, reason: "finish precedes start" }); continue; }
    rows.push({ p, s, f });
  }
  if (!rows.length) return { bars: [], unplotted, span: null };

  const t0 = Math.min(...rows.map((x) => x.s.getTime()));
  const t1 = Math.max(...rows.map((x) => x.f.getTime()));
  // A single-day programme has zero span; dividing by it would give NaN widths, so every bar
  // occupies the full track instead — which is what a one-day programme actually looks like.
  const total = t1 - t0 || 1;
  const bars = rows.map(({ p, s, f }) => ({
    id: p.id, name: p.name, activities: p.activities,
    start: s.toISOString().slice(0, 10), finish: f.toISOString().slice(0, 10),
    left: t1 === t0 ? 0 : ((s.getTime() - t0) / total) * 100,
    width: t1 === t0 ? 100 : Math.max(((f.getTime() - s.getTime()) / total) * 100, 0.8),
    days: Math.round((f.getTime() - s.getTime()) / DAY_MS) + 1,
    linked: linked.has(p.id),
    driving: f.getTime() === t1,
  }));
  bars.sort((a, b) => a.left - b.left || b.width - a.width || a.name.localeCompare(b.name));
  return {
    bars, unplotted,
    span: { start: new Date(t0).toISOString().slice(0, 10),
            finish: new Date(t1).toISOString().slice(0, 10),
            days: Math.round((t1 - t0) / DAY_MS) + 1 },
  };
}
