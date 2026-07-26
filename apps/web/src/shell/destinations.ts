/**
 * R26-SHELL — the first-class destination catalog, as data.
 *
 * These 40-odd entries used to be a literal inside `buildNav()`, which is why nobody noticed that a
 * destination could appear in two workspaces' rails under two different stages, or that Facility
 * Condition was listed twice in the Developer rail alone. A catalog you can only read by scrolling
 * through the function that renders it is a catalog nobody audits.
 *
 * Moving it here buys three things the literal could not:
 *
 * * **The rail is built from the catalog, not the other way round.** Both the current stage rail and
 *   the five-room spine read the same entries, so the two shells cannot drift apart on what exists.
 * * **`needs` is declarative.** A destination that only makes sense when a module is installed says
 *   so; previously that was a `this.mods.some(...)` spread inline, easy to forget on a new entry.
 * * **It can be checked.** `ALL_DESTS` is the exact set a test asserts is fully roomed — a
 *   destination with no room is then a build failure rather than something a user finds missing.
 */

export interface Dest {
  key: string;
  icon: string;
  label: string;
  /** Only shown when this module key is installed on the project. */
  needs?: string;
  /** Hop to another workspace instead of rendering a panel here. */
  goto?: string;
}

/** Workspace → ordered [stage, destinations]. The stage rail's structure, verbatim. */
export const STAGES_BY_WS: Record<string, [string, Dest[]][]> = {
  // GC / builder — plan → build → turn over. Money is deliberately its own stage: "Build" had grown
  // to 13 entries of which 7 were project accounting, so a superintendent looking for today's
  // schedule scanned past the general ledger to find it.
  construction: [
    ["Plan & derisk", [
      { key: "__review__", icon: "🛡", label: "Risk Review" },
      { key: "__riskcost__", icon: "⚖️", label: "Risk & Cost" },
      { key: "__responsibility__", icon: "🧭", label: "Responsibility" },
    ]],
    ["Build", [
      { key: "__schedule__", icon: "📅", label: "Schedule", needs: "schedule_activity" },
      { key: "__resload__", icon: "👷", label: "Resource Loading", needs: "schedule_activity" },
      { key: "__equipment__", icon: "🔩", label: "Equipment" },
      { key: "__topicboard__", icon: "🗂", label: "Issue Board" },
      { key: "__resilience__", icon: "🌊", label: "Climate Resilience" },
      { key: "__aiassist__", icon: "✍️", label: "AI Assist" },
    ]],
    // Ordered the way the question is actually asked: what did we plan, what is it costing, are we
    // ahead or behind, what do we bill, what does accounting see.
    ["Money", [
      { key: "__budget__", icon: "💰", label: "Budget" },
      { key: "__margin__", icon: "📒", label: "Cost-code Margin", needs: "cost_code" },
      { key: "__selections__", icon: "◈", label: "Selections", needs: "selection" },
      { key: "__evm__", icon: "📊", label: "Earned Value" },
      { key: "__wip__", icon: "📄", label: "WIP Schedule" },
      { key: "__ledger__", icon: "📒", label: "General Ledger" },
      { key: "__traceability__", icon: "🔗", label: "Cost Traceability" },
    ]],
    ["Documents", [
      { key: "__documents__", icon: "📁", label: "Documents" },
    ]],
    ["Turn over & operate", [
      { key: "__turnover__", icon: "🏁", label: "Turnover" },
      { key: "__operations__", icon: "🔧", label: "Operations" },
      { key: "__assets__", icon: "🔧", label: "Asset Register", needs: "asset_register" },
      { key: "__fca__", icon: "🏥", label: "Facility Condition" },
      { key: "__energy__", icon: "⚡", label: "Energy" },
    ]],
  ],
  // Architect / engineer — the design-phase seat (AIA SD/DD/CD · RIBA 2–4).
  design: [
    ["Brief & program", [
      { key: "__program__", icon: "🧩", label: "Space Program" },
      { key: "__conceptrender__", icon: "🖼", label: "Concept Renders" },
      { key: "__lifecycle__", icon: "🧭", label: "Project Lifecycle" },
      { key: "__masterbuilder__", icon: "🏛", label: "Master Builder" },
    ]],
    // Split from "Analyse & check" for the same reason as Build/Money: you set standards once and
    // check the model continuously. Two sittings, two stages.
    ["Model & standards", [
      { key: "__ids__", icon: "📋", label: "IDS Requirements" },
      { key: "__standards__", icon: "🗂", label: "CDE / Standards" },
      { key: "__responsibility__", icon: "🧭", label: "Responsibility" },
      { key: "__documents__", icon: "📁", label: "Documents" },
      { key: "__materials__", icon: "🎨", label: "Materials" },
      { key: "__modulegraph__", icon: "🕸", label: "Module Relations" },
      { key: "__spine__", icon: "🔗", label: "Discipline Spine" },
    ]],
    ["Analyse & check", [
      { key: "__modelqa__", icon: "✅", label: "Model Health" },
      { key: "__modelanalysis__", icon: "🔬", label: "Model Analysis" },
      { key: "__bimkpi__", icon: "📊", label: "BIM KPIs" },
      { key: "__designmetrics__", icon: "📐", label: "Design Metrics" },
      { key: "__spaceutil__", icon: "🪑", label: "Space Utilization" },
      { key: "__mepfittings__", icon: "🔩", label: "MEP Fittings" },
      { key: "__resilience__", icon: "🌊", label: "Climate Resilience" },
    ]],
  ],
  // Owner / developer — acquire → design & build (phase gates) → operate.
  developer: [
    ["Acquire", [
      { key: "__uw__", icon: "📊", label: "Underwriting", goto: "finance" },
      { key: "__land__", icon: "🗺️", label: "Land Screening" },
      { key: "__massingopt__", icon: "🧮", label: "Massing Optioneer" },
      { key: "__diligence__", icon: "📜", label: "Diligence & Entitlements" },
      { key: "__market__", icon: "💹", label: "Market Intelligence" },
    ]],
    ["Design & build", [
      { key: "__lifecycle__", icon: "🧭", label: "Project Lifecycle" },
    ]],
    ["Operate", [
      { key: "__fca__", icon: "🏥", label: "Facility Condition" },
      { key: "__resilience__", icon: "🌊", label: "Climate Resilience" },
      { key: "__esg__", icon: "🌱", label: "ESG & POE" },
    ]],
    ["Documents & model", [
      { key: "__documents__", icon: "📁", label: "Documents" },
      { key: "__modelanalysis__", icon: "🔬", label: "Model Analysis" },
    ]],
  ],
};

/** Cross-project roll-ups, appended to every workspace so portfolio views never interleave. */
export const ACROSS_PROJECTS: [string, Dest[]] = ["Across projects", [
  { key: "__portfolio__", icon: "🏢", label: "Portfolio" },
  { key: "__benchmarks__", icon: "📈", label: "Benchmarks" },
]];

/**
 * The stage rail for a workspace, with `needs` resolved. Unknown workspaces fall back to the
 * builder's rail — the same behaviour the inline literal had, kept because an unrecognised
 * workspace showing an empty rail is worse than showing the most common one.
 */
export function stagesFor(ws: string, hasModule: (key: string) => boolean): [string, Dest[]][] {
  const base = STAGES_BY_WS[ws] ?? STAGES_BY_WS.construction ?? [];
  const out: [string, Dest[]][] = base.map(([stage, items]) =>
    [stage, items.filter((d) => !d.needs || hasModule(d.needs))]);
  out.push(ACROSS_PROJECTS);
  return out.filter(([, items]) => items.length > 0);
}

/**
 * Every destination that exists anywhere, deduped by key. The union, not any one workspace's slice —
 * a destination reachable only from the Developer rail is still a destination the spine must place.
 */
export const ALL_DESTS: Dest[] = (() => {
  const seen = new Map<string, Dest>();
  for (const stages of [...Object.values(STAGES_BY_WS), [ACROSS_PROJECTS]]) {
    for (const [, items] of stages) for (const d of items) if (!seen.has(d.key)) seen.set(d.key, d);
  }
  return [...seen.values()];
})();
