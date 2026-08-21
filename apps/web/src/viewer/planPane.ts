import { groundToPlan, readPlanTransform, worldToPixel } from "./planTransform";

/**
 * R38-SYNC-VIEW + R38-SYNC-SELECT — the plan, in the room, and talking to it.
 *
 * The plan drawing has always been one click away and one WINDOW away: "Generate plan (SVG)" opened
 * a browser tab, so reading a plan meant leaving the model. This docks it beside the 3D view and
 * keeps it on the storey you are working in — "model and documents in one room".
 *
 * SYNC-SELECT (2026-08-02): the served plan's polylines now carry `data-guid` (R38-PLAN-IDENTITY
 * carried the GlobalId through the bake; the SVG generator emits it), so selection syncs BOTH ways:
 * clicking linework in the plan selects that element in 3D, and selecting in 3D lights the
 * element's loops in the plan. **One element is many polylines** — a wall cut at a doorway sections
 * into several loops — so highlight and click both operate on "every node with this guid", never
 * "the node".
 *
 * Two deliberate shapes:
 *  - Drawn linework is ~1px and unclickable at plan scale, so every identified polyline gets an
 *    invisible fat twin (`data-hit`) that exists only to be clicked. The twin is a clone, so it can
 *    never drift from the geometry it fronts.
 *  - A selection change never refetches (`needsRefetch` ignores it) — highlighting is a style pass
 *    over nodes already on screen, which is what makes the pane cheap enough to leave open.
 */

/** The query for a plan cut. Pure so the storey contract is testable without a network.
 *
 *  `byDiscipline` reaches DISC-poché, which strokes each element's linework in its discipline
 *  colour and adds a legend. The route has offered it since it shipped and **this function never
 *  sent it**, so every plan in the product came back monochrome — the capability was built,
 *  routed, and unreachable, the same shape as the six routes v0.3.1044 surfaced. Sent only when
 *  ON: an absent parameter and `false` mean the same thing to the route, and the shorter URL is
 *  the one that reads correctly when a user copies it out of the pop-out button.
 */
export function planParams(storey: string | null, scale = 100,
                           byDiscipline = false): URLSearchParams {
  const q = new URLSearchParams({ scale: String(scale) });
  if (storey) q.set("storey", storey);
  if (byDiscipline) q.set("by_discipline", "true");
  return q;
}

/** Should the pane re-fetch? Only when the CUT changes — a selection change in 3D must not cost a
 *  drawing round-trip, which is what makes the pane cheap enough to leave open. */
export function needsRefetch(prev: { storey: string | null; scale: number } | null,
                             next: { storey: string | null; scale: number }): boolean {
  if (!prev) return true;
  return prev.storey !== next.storey || prev.scale !== next.scale;
}

/**
 * Give every identified polyline an invisible, fat, clickable twin. Returns how many were added.
 * Idempotent: a node already twinned is skipped, so calling after every refresh cannot stack twins.
 */
export function addHitTargets(root: ParentNode): number {
  let added = 0;
  root.querySelectorAll<SVGElement>("polyline[data-guid]").forEach((el) => {
    if (el.hasAttribute("data-hit")) return;                        // this IS a twin
    const next = el.nextElementSibling;
    if (next?.hasAttribute("data-hit")) return;                     // already twinned
    const hit = el.cloneNode(false) as SVGElement;
    hit.setAttribute("data-hit", "1");
    hit.setAttribute("stroke", "transparent");   // painted (≠ none), so it hit-tests; invisible
    hit.setAttribute("stroke-width", "8");
    hit.setAttribute("fill", "none");
    hit.setAttribute("pointer-events", "stroke");
    hit.setAttribute("cursor", "pointer");
    el.after(hit);
    added++;
  });
  return added;
}

/**
 * Light every loop of `guid`; restore everything else. Returns how many loops lit — an element cut
 * at an opening sections into several, and a return of 0 for a non-null guid means the element is
 * not on this storey's plan (a fact worth surfacing, not an error).
 */
export function syncPlanHighlight(root: ParentNode, guid: string | null): number {
  let lit = 0;
  root.querySelectorAll<SVGElement>("polyline[data-guid]").forEach((el) => {
    if (el.hasAttribute("data-hit")) return;                        // twins stay invisible
    const on = guid !== null && el.getAttribute("data-guid") === guid;
    if (on) {
      if (!el.hasAttribute("data-orig-stroke")) {
        el.setAttribute("data-orig-stroke", el.getAttribute("stroke") ?? "");
        el.setAttribute("data-orig-width", el.getAttribute("stroke-width") ?? "");
      }
      el.setAttribute("stroke", "#2563eb");
      el.setAttribute("stroke-width", "2.4");
      lit++;
    } else if (el.hasAttribute("data-orig-stroke")) {
      el.setAttribute("stroke", el.getAttribute("data-orig-stroke") ?? "");
      el.setAttribute("stroke-width", el.getAttribute("data-orig-width") ?? "");
      el.removeAttribute("data-orig-stroke");
      el.removeAttribute("data-orig-width");
    }
  });
  return lit;
}

export interface PlanPaneDeps {
  /** Absolute URL for an API path (the client's `api.url`). */
  url: (path: string) => string;
  projectId: () => string | null;
  /** The storey the modeler is working in, or null for the whole model. */
  activeStorey: () => string | null;
  notify: (msg: string, kind: "info" | "success" | "error") => void;
  /** SYNC-SELECT: a click on identified linework names an element; the viewer selects it. */
  onPick?: (guid: string) => void;
  /** The api client's auth headers — the pane fetches like every other client call. */
  headers?: () => Record<string, string>;
}

export class PlanPane {
  readonly el = document.createElement("div");
  private body = document.createElement("div");
  private last: { storey: string | null; scale: number } | null = null;
  private open = false;
  /** Client-side zoom (CSS width %). The server `scale` param stays fixed: zoom is presentation,
   *  and a zoom that refetched the drawing would cost a bake round-trip per click. */
  private zoomPct = 100;
  /** The selected element, re-lit after every refetch so a storey change keeps the selection. */
  private sel: string | null = null;
  /** Live 3D cursor, drawn in SVG user space from the plan's own transform. Hidden when unknown. */
  private cursor = document.createElementNS("http://www.w3.org/2000/svg", "circle");

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
    zoomOut.className = "tool-btn"; zoomOut.textContent = "−"; zoomOut.title = "Zoom out";
    zoomOut.onclick = () => { this.zoomPct = Math.max(50, this.zoomPct / 2); this.applyZoom(); };
    const zoomIn = document.createElement("button");
    zoomIn.className = "tool-btn"; zoomIn.textContent = "+"; zoomIn.title = "Zoom in";
    zoomIn.onclick = () => { this.zoomPct = Math.min(800, this.zoomPct * 2); this.applyZoom(); };
    const pop = document.createElement("button");
    pop.className = "tool-btn"; pop.textContent = "↗"; pop.title = "Open this plan in a new tab";
    pop.onclick = () => {
      const pid = this.d.projectId();
      if (pid) window.open(this.d.url(`/projects/${pid}/drawings/plan.svg?${this.params()}`), "_blank");
    };
    // DISC-poché toggle. Off by default: a monochrome plan is the drafting convention, and colour
    // is an analysis overlay rather than the sheet you would issue. Re-fetches, because the colour
    // is applied server-side at cut time — there is no client-side restyle to do.
    const disc = document.createElement("button");
    disc.className = "tool-btn"; disc.textContent = "◑";
    disc.title = "Colour the linework by discipline (adds a legend)";
    disc.onclick = () => {
      this.byDiscipline = !this.byDiscipline;
      disc.classList.toggle("on", this.byDiscipline);
      disc.title = this.byDiscipline
        ? "Discipline colour ON — click for monochrome"
        : "Colour the linework by discipline (adds a legend)";
      void this.refresh(true);
    };
    bar.append(title, lvl, disc, zoomOut, zoomIn, pop);
    this.body.style.cssText = "flex:1;overflow:auto;background:#fff";
    // Delegated ONCE on the persistent body, not per refresh — a listener per refetch is how a
    // single click comes to select the same element N times.
    this.cursor.setAttribute("r", "4");
    this.cursor.setAttribute("fill", "#2563eb");
    this.cursor.setAttribute("stroke", "#fff");
    this.cursor.setAttribute("stroke-width", "1.2");
    this.cursor.setAttribute("pointer-events", "none");
    this.cursor.style.display = "none";
    this.body.addEventListener("click", (e) => {
      const guid = (e.target as Element | null)?.closest?.("[data-guid]")?.getAttribute("data-guid");
      if (guid) { this.highlight(guid); this.d.onPick?.(guid); }
    });
    this.el.append(bar, this.body);
  }

  /** DISC-poché: colour the linework by discipline. Off by default — see the toggle above. */
  private byDiscipline = false;

  private params(): string {
    return planParams(this.d.activeStorey(), 100, this.byDiscipline).toString();
  }

  private levelLabel(): string {
    const s = this.d.activeStorey();
    return `${s ?? "whole model"} · ${this.zoomPct}%`;
  }

  private applyZoom(): void {
    const svg = this.body.querySelector("svg");
    if (svg) svg.setAttribute("width", `${this.zoomPct}%`);
    const lbl = this.el.querySelector<HTMLElement>(".plan-pane-level");
    if (lbl) lbl.textContent = this.levelLabel();
  }

  /** SYNC-SELECT, 3D → plan: light every loop of `guid` (null clears). Keeps the choice across
   *  refetches, and scrolls the first lit loop into view so the pane answers "where is it?". */
  highlight(guid: string | null): void {
    this.sel = guid;
    if (!this.open) return;
    const lit = syncPlanHighlight(this.body, guid);
    if (lit > 0) {
      this.body.querySelector<SVGElement>(`polyline[data-guid="${CSS.escape(guid!)}"]`)
        ?.scrollIntoView({ block: "center", inline: "center" });
    }
  }

  /** Fetch the cut if it changed (or `force`). Never throws — a failed drawing must not break the
   *  viewer, and an empty pane with a message beats a blank pane that looks like an empty model. */
  async refresh(force = false): Promise<void> {
    if (!this.open) return;
    const pid = this.d.projectId();
    const lbl = this.el.querySelector<HTMLElement>(".plan-pane-level");
    if (lbl) lbl.textContent = this.levelLabel();
    if (!pid) { this.body.innerHTML = ""; return; }
    const next = { storey: this.d.activeStorey(), scale: 100 };
    if (!force && !needsRefetch(this.last, next)) return;
    this.last = next;
    try {
      // Bearer headers, NO `credentials: "include"` — matching every other GET the client makes.
      // The credentialed form silently required `Access-Control-Allow-Credentials` from the API,
      // which it never sends, so this exact fetch hard-failed cross-origin (ERR_FAILED, caught and
      // rendered as "No plan for this level yet") from the day the pane shipped — unobserved,
      // because the pane's toggle button was never appended to the rail either.
      const res = await fetch(this.d.url(`/projects/${pid}/drawings/plan.svg?${this.params()}`),
                              { headers: this.d.headers?.() ?? {} });
      if (!res.ok) throw new Error(`plan ${res.status}`);
      const svg = await res.text();
      // The SVG is server-generated from our own geometry, not user content; it is inserted as
      // markup because that is what it is. It carries no scripts — the generator emits paths, text
      // and style only.
      this.body.innerHTML = svg;
      const el = this.body.querySelector("svg");
      if (el) { el.setAttribute("width", `${this.zoomPct}%`); el.removeAttribute("height"); }
      addHitTargets(this.body);
      syncPlanHighlight(this.body, this.sel);      // a storey change must not lose the selection
      this.attachCursor();
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

  /**
   * R36-VIEWER-SUBAPP ④ — the plan IS the canvas, or it is hidden.
   *
   * **`"side"` is gone (v0.3.1047).** It was the original 38% strip beside the model — the layout
   * this item replaced, because a plan occupying a third of the screen is a *slice* of the model
   * rather than a peer of it. The mode switch has rendered it since v0.3.918 and **nothing outside
   * the tests had called it since**; `specPane.dock` already declared `"full" | "hidden"`, so this
   * signature was the odd one out. A second, unreachable way to arrange the canvas is exactly what
   * a mode switch exists to prevent, and leaving it live invites it back by accident.
   *
   * Deliberately not a second visibility flag either: `CanvasModeSwitch` is the single owner, and
   * `toggle()` routes through it. Two independent controls over one element is how you get "both
   * visible" and "neither visible" states that nothing forbids.
   */
  dock(style: "full" | "hidden"): void {
    this.open = style !== "hidden";
    this.el.style.display = this.open ? "flex" : "none";
    this.el.style.width = this.open ? "100%" : "";
    this.el.style.left = this.open ? "0" : "";
    if (this.open) void this.refresh(true);
  }

  get isOpen(): boolean { return this.open; }

  /**
   * R38-SYNC-VIEW cursor — 3D pointer → plan. `pt` is viewer ground (Y-up). `null` hides the
   * mark (pointer left the canvas, or the drawing has no transform yet).
   */
  showGroundCursor(pt: { x: number; z: number } | null): void {
    if (!this.open || !pt) { this.cursor.style.display = "none"; return; }
    const t = readPlanTransform(this.body);
    if (!t) { this.cursor.style.display = "none"; return; }
    const { x, y } = groundToPlan(pt);
    const { px, py } = worldToPixel(t, x, y);
    this.cursor.setAttribute("cx", String(px));
    this.cursor.setAttribute("cy", String(py));
    this.cursor.style.display = "";
  }

  private attachCursor(): void {
    const svg = this.body.querySelector("svg");
    if (!svg) return;
    this.cursor.style.display = "none";
    svg.appendChild(this.cursor);
  }
}
