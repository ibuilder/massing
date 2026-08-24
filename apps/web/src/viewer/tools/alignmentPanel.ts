// The federation alignment panel — extracted from `qaSection.ts` (R39-DECOMP-VIEWER) and given the
// yaw fit (R41-MODEL-ALIGN).
//
// Two questions about the same problem, and they belong together:
//
//   DO THEY AGREE?   `modelAlignment` — do the discipline models share a storey scheme and a
//                    georeferenced origin? The #1 coordination problem, and a pure report.
//   WHAT DO I DO?    `modelAlignmentFit` — is a model simply ROTATED, and by how much? A yaw-only
//                    oriented box fitted to its footprint, proposed only when it saves at least 20%
//                    of the axis-aligned area.
//
// The report alone says "these models disagree" and leaves the user to guess why. Most of the time
// the answer is that one arrived rotated, which is the thing the fit can measure and the report
// cannot: a rotated building and a square-on one have the same storeys and the same origin.
//
// **Every fit is a proposal.** Nothing here writes to a model or its IFC. The panel says what the
// rotation is; applying it is a stored transform and a separate change.
//
// Extracted rather than added in place because `qaSection.ts` sits exactly on its size ratchet, and a
// panel that asks two questions and renders three shapes of answer is no longer a button.

export interface AlignmentPanelDeps {
  readonly pid: string;
  readonly api: {
    modelAlignment(pid: string): Promise<AlignmentReport>;
    projectModels(pid: string): Promise<Array<{ id: string; discipline: string }>>;
    modelAlignmentFit(pid: string, mid: string): Promise<FitReply>;
  };
  readonly toast: (message: string, kind?: "info" | "success" | "error") => void;
  /** Render into a result surface the host owns. */
  readonly showResult: (title: string, build: (body: HTMLElement) => void) => void;
  readonly resultNote: (text: string, tone: "ok" | "bad") => HTMLElement;
  readonly kvTable: (rows: Array<{ k: string; v: string }>) => HTMLElement;
  /** Short status line beside the tool button. */
  readonly setOut: (text: string) => void;
}

export interface AlignmentReport {
  aligned: boolean;
  message: string;
  models: Array<{ name: string; storey_count: number; error?: string; georef: unknown | null }>;
  issues: Array<{ type: string; severity: string; model: string; detail: string }>;
}

export interface FitReply {
  model: string;
  discipline: string;
  fit: null | {
    yaw_deg: number; currently_at_deg: number; extent_m: [number, number];
    obb_area_m2: number; aabb_area_m2: number; area_saving: number;
    accepted: boolean; reason: string;
  };
}

const TONE: Record<string, string> = {
  high: "var(--status-crit,#e2554a)",
  medium: "var(--status-warn,#ffd479)",
  low: "var(--muted)",
};

/** One line per model whose footprint suggests it is rotated. */
export function rotatedModels(fits: readonly FitReply[]): FitReply[] {
  return fits.filter((f) => f.fit?.accepted);
}

/**
 * Run both checks and render them.
 *
 * The fits are fetched for every model and **failures are swallowed per model**: a model whose
 * geometry cannot be read must not cost the user the alignment report, which is the part that works
 * without any geometry at all. A panel that shows nothing because one of five models is unreadable is
 * worse than one that shows four answers and stays quiet about the fifth.
 */
export async function runAlignmentPanel(d: AlignmentPanelDeps): Promise<void> {
  let report: AlignmentReport;
  try {
    report = await d.api.modelAlignment(d.pid);
  } catch {
    d.toast("Alignment needs ≥2 models — add one with “＋ Add discipline IFC”", "error");
    return;
  }

  const fits: FitReply[] = [];
  try {
    const models = await d.api.projectModels(d.pid);
    for (const m of models) {
      try {
        fits.push(await d.api.modelAlignmentFit(d.pid, m.id));
      } catch { /* one unreadable model must not cost the whole report */ }
    }
  } catch { /* no model list is not a reason to hide the report */ }

  const rotated = rotatedModels(fits);
  d.setOut(report.aligned && !rotated.length
    ? "Models aligned ✓"
    : `${report.issues.length + rotated.length} alignment issue(s)`);
  d.toast(report.message, report.aligned ? "success" : "info");

  d.showResult("Model alignment", (body) => {
    body.appendChild(d.resultNote(report.message, report.aligned ? "ok" : "bad"));
    body.appendChild(d.kvTable(report.models.map((m) => ({
      k: m.name,
      v: m.error ? `error: ${m.error}` : `${m.storey_count} storeys${m.georef ? " · georef" : ""}`,
    }))));
    for (const i of report.issues) {
      const el = document.createElement("div");
      el.style.cssText = `font-size:12px;margin:3px 0;border-left:3px solid ${TONE[i.severity] || "var(--muted)"};padding-left:6px`;
      const b = document.createElement("b"); b.textContent = i.model;
      el.appendChild(b);
      el.appendChild(document.createTextNode(` — ${i.detail}`));
      body.appendChild(el);
    }

    if (!rotated.length) return;
    const h = document.createElement("div");
    h.className = "meta";
    h.style.cssText = "margin-top:10px;font-weight:600";
    h.textContent = "Rotated models — a yaw correction is available";
    body.appendChild(h);
    for (const f of rotated) {
      const fit = f.fit!;
      const el = document.createElement("div");
      el.style.cssText = "font-size:12px;margin:3px 0;border-left:3px solid var(--status-warn,#ffd479);padding-left:6px";
      const b = document.createElement("b"); b.textContent = f.discipline;
      el.appendChild(b);
      el.appendChild(document.createTextNode(
        ` sits at ${fit.currently_at_deg.toFixed(1)}° — rotate ${fit.yaw_deg.toFixed(1)}° to square it `
        + `(true extent ${fit.extent_m[0].toFixed(1)} × ${fit.extent_m[1].toFixed(1)} m, `
        + `${Math.round(fit.area_saving * 100)}% tighter than its bounding box)`));
      body.appendChild(el);
    }
    const note = document.createElement("div");
    note.className = "meta";
    note.style.cssText = "margin-top:8px;font-size:11px";
    note.textContent = "A proposal only — the source IFC is never modified. A fit is offered when the "
      + "oriented box is at least 20% tighter than the axis-aligned one; below that the smallest "
      + "rectangle and a wall-parallel one stop agreeing, and the smallest one is the wrong answer.";
    body.appendChild(note);
  });
}
