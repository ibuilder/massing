/**
 * UX-READINESS-EVERYWHERE — the Master Builder 8-step synthesis, as a home strip.
 *
 * The full brief already exists (`panels/masterBuilder.ts`) and is reachable from Design only.
 * That is the defect: the product's own "what do I do next" surface is hidden on the one workspace
 * whose occupant already lives in the model. This module is the *strip*: score, the steps that
 * belong to this workspace/persona, and one hop to close the first gap. The full eight-card brief
 * stays on `__masterbuilder__`.
 *
 * Fail-open: a brief that cannot load leaves the host empty. A summary must not take down the
 * dashboard it summarises (same rule as Pulse).
 */
export type ReadinessStatus = "ready" | "partial" | "gap";

export interface ReadinessStep {
  n: number;
  key: string;
  title: string;
  dest: string;
  status: ReadinessStatus;
  gaps: string[];
}

export interface ReadinessBrief {
  readiness_pct: number;
  ready_steps: number;
  gap_steps: number;
  step_count: number;
  grounded_in_place: boolean;
  steps: ReadinessStep[];
  scope?: { workspace: string; persona: string; keys: string[] };
}

/** Protocol keys this workspace actually asks. Unknown workspaces get the builder's set. */
export const STEPS_BY_WORKSPACE: Record<string, readonly string[]> = {
  construction: ["delivery", "risk", "design", "handover"],
  design: ["place", "program", "design", "regulatory"],
  developer: ["place", "program", "feasibility", "regulatory"],
};

/**
 * Persona overlay — intersected with the workspace set so a superintendent on Design still sees
 * design steps rather than an empty strip. `all` (and unknown) keep the workspace set whole.
 */
export const STEPS_BY_PERSONA: Record<string, readonly string[]> = {
  superintendent: ["delivery", "risk", "handover"],
  project_manager: ["delivery", "risk", "feasibility", "design"],
  gc: ["delivery", "risk", "design", "feasibility"],
  architect: ["place", "program", "design", "regulatory"],
  engineer: ["design", "regulatory", "place"],
  developer: ["place", "program", "feasibility", "regulatory"],
  subcontractor: ["delivery", "risk"],
};

export function readinessStepKeys(workspace: string, persona: string): string[] {
  const ws = STEPS_BY_WORKSPACE[workspace] ?? STEPS_BY_WORKSPACE.construction!;
  const p = persona && persona !== "all" ? STEPS_BY_PERSONA[persona] : undefined;
  if (!p) return [...ws];
  const keep = new Set(p);
  const scoped = ws.filter((k) => keep.has(k));
  return scoped.length ? scoped : [...ws];
}

export function firstOpenStep(steps: ReadinessStep[]): ReadinessStep | null {
  return steps.find((s) => s.status !== "ready") ?? null;
}

const PILL_COL: Record<ReadinessStatus, string> = {
  ready: "var(--status-good)",
  partial: "var(--status-warn)",
  gap: "var(--status-crit)",
};

export async function mountReadinessStrip(
  host: HTMLElement,
  opts: {
    load: () => Promise<ReadinessBrief>;
    workspace: string;
    persona: string;
    onOpen: (dest: string) => void;
  },
): Promise<void> {
  host.replaceChildren();
  let brief: ReadinessBrief;
  try { brief = await opts.load(); }
  catch { return; }

  const order = readinessStepKeys(opts.workspace, opts.persona);
  const byKey = new Map(brief.steps.map((s) => [s.key, s]));
  const steps = order.map((k) => byKey.get(k)).filter((s): s is ReadinessStep => !!s);
  if (!steps.length) return;

  const wrap = document.createElement("div");
  wrap.className = "dash-card";
  wrap.setAttribute("data-readiness", "strip");
  wrap.style.cssText = "margin-bottom:8px";

  const head = document.createElement("div");
  head.style.cssText = "display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap";
  const title = document.createElement("div");
  title.className = "section-title";
  title.style.margin = "0";
  title.textContent = "Next on this project";
  const pct = document.createElement("div");
  pct.style.cssText = "font-size:18px;font-weight:800";
  const col = brief.readiness_pct >= 66 ? "var(--status-good)"
    : brief.readiness_pct >= 33 ? "var(--status-warn)" : "var(--status-crit)";
  pct.style.color = col;
  pct.textContent = `${brief.readiness_pct}%`;
  pct.title = `${brief.ready_steps}/${brief.step_count} protocol steps ready`;
  head.append(title, pct);
  wrap.appendChild(head);

  const meta = document.createElement("div");
  meta.className = "meta";
  meta.style.margin = "2px 0 6px";
  meta.textContent = brief.grounded_in_place
    ? "Labels reflect what is present, not what is correct."
    : "Not grounded in place — set a jurisdiction so code editions and loads resolve.";
  wrap.appendChild(meta);

  const row = document.createElement("div");
  row.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center";
  for (const s of steps) {
    const pill = document.createElement("button");
    pill.type = "button";
    pill.className = "tool-btn";
    pill.style.cssText = "font-size:11px;padding:2px 8px";
    const mark = document.createElement("span");
    mark.style.cssText = `color:${PILL_COL[s.status]};font-weight:700;margin-right:4px`;
    mark.textContent = s.status === "ready" ? "●" : s.status === "partial" ? "◐" : "○";
    pill.append(mark, document.createTextNode(s.title));
    pill.title = s.gaps.length ? `needs: ${s.gaps.join("; ")}` : s.status;
    pill.onclick = () => opts.onOpen(s.dest);
    row.appendChild(pill);
  }
  wrap.appendChild(row);

  const actions = document.createElement("div");
  actions.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-top:6px";
  const open = firstOpenStep(steps);
  if (open) {
    const go = document.createElement("button");
    go.type = "button";
    go.className = "btn";
    go.style.cssText = "font-size:11px;padding:2px 8px";
    go.textContent = `→ Close this gap — ${open.title}`;
    go.onclick = () => opts.onOpen(open.dest);
    actions.appendChild(go);
  }
  const full = document.createElement("button");
  full.type = "button";
  full.className = "tool-btn";
  full.style.cssText = "font-size:11px;padding:2px 8px";
  full.textContent = "Full brief";
  full.onclick = () => opts.onOpen("__masterbuilder__");
  actions.appendChild(full);
  wrap.appendChild(actions);

  host.appendChild(wrap);
}
