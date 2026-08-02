/**
 * R38-SYNC-VIEW — the plan, in the room.
 *
 * The plan drawing has always been one click away and one WINDOW away: "Generate plan (SVG)" opened
 * a browser tab, so reading a plan meant leaving the model. This docks it beside the 3D view and
 * keeps it on the storey you are working in — the first half of "model and documents in one room".
 *
 * **What this slice deliberately does NOT do: selection sync.** The drawing pipeline discards
 * element identity at bake time (`drawings._bake_uncached` has `shape.guid` and keeps only
 * `(cls, mesh)`), so no polyline in the returned SVG can name the element it draws. Clicking a wall
 * in the plan therefore cannot select it in 3D, and pretending otherwise — highlighting a nearby
 * element by coordinate guess — would be the confident-wrong shape. Selection sync is
 * R38-SYNC-SELECT and waits on R38-PLAN-IDENTITY carrying the GUID through the bake.
 *
 * Storey sync IS honest today: the plan is a cut at a level, and the level is something the viewer
 * knows exactly.
 */

/** The query for a plan cut. Pure so the storey/scale contract is testable without a network. */
export function planParams(storey: string | null, scale = 100): URLSearchParams {
  const q = new URLSearchParams({ scale: String(scale) });
  if (storey) q.set("storey", storey);
  return q;
}

/** Should the pane re-fetch? Only when the CUT changes — a selection change in 3D must not cost a
 *  drawing round-trip, which is what makes the pane cheap enough to leave open. */
export function needsRefetch(prev: { storey: string | null; scale: number } | null,
                             next: { storey: string | null; scale: number }): boolean {
  if (!prev) return true;
  return prev.storey !== next.storey || prev.scale !== next.scale;
}

export interface PlanPaneDeps {
  /** Absolute URL for an API path (the client's `api.url`). */
  url: (path: string) => string;
  projectId: () => string | null;
  /** The storey the modeler is working in, or null for the whole model. */
  activeStorey: () => string | null;
  notify: (msg: string, kind: "info" | "success" | "error") => void;
}

export class PlanPane {
  readonly el = document.createElement("div");
  private body = document.createElement("div");
  private last: { storey: string | null; scale: number } | null = null;
  private scale = 100;
  private open = false;

  constructor(private d: PlanPaneDeps) {
    this.el.className = "plan-pane";
    this.el.style.cssText = "position:absolute;top:0;right:0;bottom:0;width:38%;min-width:280px;"
      + "z-index:20;display:none;background:var(--panel,#0f172a);border-left:1px solid var(--line,#334155);"
      + "flex-direction:column";
    const bar = document.createElement("div");
    bar.style.cssText = "display:flex;align-items:center;gap:6px;padding:5px 8px;font-size:12px;"
      + "border-bottom:1px solid var(--line,#334155)";
    const title = document.createElement("span");
    title.textContent = "Plan";
    title.style.fontWeight = "600";
    const lvl = document.createElement("span");
    lvl.className = "plan-pane-level";
    lvl.style.cssText = "color:var(--muted,#94a3b8);flex:1";
    const zoomOut = document.createElement("button");
    zoomOut.className = "tool-btn"; zoomOut.textContent = "−"; zoomOut.title = "Coarser scale (1:200)";
    zoomOut.onclick = () => { this.scale = Math.min(500, this.scale * 2); void this.refresh(true); };
    const zoomIn = document.createElement("button");
    zoomIn.className = "tool-btn"; zoomIn.textContent = "+"; zoomIn.title = "Finer scale (1:50)";
    zoomIn.onclick = () => { this.scale = Math.max(20, Math.round(this.scale / 2)); void this.refresh(true); };
    const pop = document.createElement("button");
    pop.className = "tool-btn"; pop.textContent = "↗"; pop.title = "Open this plan in a new tab";
    pop.onclick = () => {
      const pid = this.d.projectId();
      if (pid) window.open(this.d.url(`/projects/${pid}/drawings/plan.svg?${this.params()}`), "_blank");
    };
    bar.append(title, lvl, zoomOut, zoomIn, pop);
    this.body.style.cssText = "flex:1;overflow:auto;background:#fff";
    this.el.append(bar, this.body);
  }

  private params(): string { return planParams(this.d.activeStorey(), this.scale).toString(); }

  private levelLabel(): string {
    const s = this.d.activeStorey();
    return `${s ?? "whole model"} · 1:${this.scale}`;
  }

  /** Fetch the cut if it changed (or `force`). Never throws — a failed drawing must not break the
   *  viewer, and an empty pane with a message beats a blank pane that looks like an empty model. */
  async refresh(force = false): Promise<void> {
    if (!this.open) return;
    const pid = this.d.projectId();
    const lbl = this.el.querySelector<HTMLElement>(".plan-pane-level");
    if (lbl) lbl.textContent = this.levelLabel();
    if (!pid) { this.body.innerHTML = ""; return; }
    const next = { storey: this.d.activeStorey(), scale: this.scale };
    if (!force && !needsRefetch(this.last, next)) return;
    this.last = next;
    try {
      const res = await fetch(this.d.url(`/projects/${pid}/drawings/plan.svg?${this.params()}`),
                              { credentials: "include" });
      if (!res.ok) throw new Error(`plan ${res.status}`);
      const svg = await res.text();
      // The SVG is server-generated from our own geometry, not user content; it is inserted as
      // markup because that is what it is. It carries no scripts — the generator emits paths, text
      // and style only.
      this.body.innerHTML = svg;
      const el = this.body.querySelector("svg");
      if (el) { el.setAttribute("width", "100%"); el.removeAttribute("height"); }
    } catch (err) {
      this.body.innerHTML = "";
      const p = document.createElement("div");
      p.style.cssText = "padding:10px;font-size:12px;color:#334155";
      p.textContent = `No plan for this level yet (${(err as Error).message}).`;
      this.body.appendChild(p);
    }
  }

  toggle(): boolean {
    this.open = !this.open;
    this.el.style.display = this.open ? "flex" : "none";
    if (this.open) void this.refresh(true);
    else this.d.notify("Plan pane closed", "info");
    return this.open;
  }

  get isOpen(): boolean { return this.open; }
}
