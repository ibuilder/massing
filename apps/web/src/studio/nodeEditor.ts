/**
 * Studio — a visual computational node graph (M4), the front-end for the server's Dynamo/Hypar-style
 * compute engine (`/compute/nodes`, `/compute/graph`). Drag nodes from the palette onto the canvas,
 * wire an output port into an input port (click a source dot, then a target dot), and Run to execute
 * the graph server-side in dependency order — zoning → structure → schedule → cost → yield, no code.
 *
 * Wiring is click-to-connect (not drag) so it's robust + keyboard/headless-testable; edges render as
 * SVG bezier curves in a layer under the nodes and re-flow as nodes move. The graph persists to
 * localStorage so a session survives reloads.
 */
import type { ApiClient, ComputeGraph, ComputeNodeSpec } from "../api/client";

interface GNode { id: string; type: string; x: number; y: number; params: Record<string, number | string>; results?: Record<string, unknown>; }
interface GEdge { from: string; from_port: string; to: string; to_port: string; }

const STORE = "studio-graph-v1";

export class NodeEditor {
  private specs = new Map<string, ComputeNodeSpec>();
  private nodes: GNode[] = [];
  private edges: GEdge[] = [];
  private seq = 0;
  private pending: { node: string; port: string } | null = null;
  private content!: HTMLElement;
  private svg!: SVGSVGElement;
  private status!: HTMLElement;
  private mounted = false;

  constructor(private root: HTMLElement, private api: ApiClient, private setStatus?: (s: string) => void) {}

  /** Lazily build the UI + load the node palette (idempotent — safe to call on every workspace open). */
  async mount(): Promise<void> {
    if (this.mounted) return;
    this.mounted = true;
    this.root.classList.add("studio");
    this.root.innerHTML = `
      <div class="studio-bar">
        <strong>Studio — computational graph</strong>
        <span class="meta">click an output ● then an input ○ to wire · drag a node by its title</span>
        <span style="flex:1"></span>
        <button id="studio-sample" class="btn-secondary">Load example</button>
        <button id="studio-clear" class="btn-secondary">Clear</button>
        <button id="studio-run" class="btn-primary">▶ Run</button>
      </div>
      <div class="studio-body">
        <div class="studio-palette" id="studio-palette"></div>
        <div class="studio-canvas" id="studio-canvas">
          <div class="studio-content" id="studio-content">
            <svg id="studio-edges" class="studio-edges"></svg>
          </div>
        </div>
      </div>
      <div class="studio-status meta" id="studio-status">No palette loaded.</div>`;
    this.content = this.root.querySelector("#studio-content")!;
    this.svg = this.root.querySelector("#studio-edges") as unknown as SVGSVGElement;
    this.status = this.root.querySelector("#studio-status")!;

    this.root.querySelector("#studio-run")!.addEventListener("click", () => void this.run());
    this.root.querySelector("#studio-clear")!.addEventListener("click", () => this.clear());
    this.root.querySelector("#studio-sample")!.addEventListener("click", () => this.loadExample());
    this.root.querySelector("#studio-canvas")!.addEventListener("click", (e) => {
      if (e.target === e.currentTarget || (e.target as HTMLElement).id === "studio-content") this.cancelWire();
    });

    try {
      const { nodes } = await this.api.computeNodes();
      for (const n of nodes) this.specs.set(n.key, n);
      this.buildPalette(nodes);
      this.restore();
      this.render();
      this.setMsg(`${nodes.length} node types available.`);
    } catch {
      this.render();   // show the empty-canvas hint ("connect the API")
      this.setMsg("Compute palette unavailable (API offline).");
    }
  }

  private buildPalette(nodes: ComputeNodeSpec[]): void {
    const pal = this.root.querySelector("#studio-palette")!;
    const byCat: Record<string, ComputeNodeSpec[]> = {};
    for (const n of nodes) (byCat[n.category] ||= []).push(n);
    pal.innerHTML = "";
    for (const [cat, items] of Object.entries(byCat)) {
      const h = document.createElement("div"); h.className = "studio-pal-cat"; h.textContent = cat;
      pal.appendChild(h);
      for (const spec of items) {
        const b = document.createElement("button");
        b.className = "studio-pal-node"; b.textContent = spec.label; b.title = spec.doc || spec.key;
        b.addEventListener("click", () => this.addNode(spec.key));
        pal.appendChild(b);
      }
    }
  }

  private addNode(type: string, x?: number, y?: number): GNode {
    const spec = this.specs.get(type)!;
    const id = `n${++this.seq}`;
    const params: Record<string, number | string> = {};
    for (const inp of spec.inputs) if (inp.default !== null) params[inp.name] = inp.default;
    // place new nodes within the current scroll viewport (so they're visible) + a small cascade
    const cv = this.root.querySelector<HTMLElement>("#studio-canvas");
    const ox = cv ? cv.scrollLeft : 0, oy = cv ? cv.scrollTop : 0;
    const step = (this.nodes.length % 6) * 28;
    const node: GNode = { id, type, x: x ?? ox + 30 + step, y: y ?? oy + 30 + step, params };
    this.nodes.push(node);
    this.persist(); this.render();
    return node;
  }

  private removeNode(id: string): void {
    this.nodes = this.nodes.filter((n) => n.id !== id);
    this.edges = this.edges.filter((e) => e.from !== id && e.to !== id);
    this.persist(); this.render();
  }

  // --- wiring (click output ● then input ○) ----------------------------------
  private onPortClick(node: string, port: string, kind: "in" | "out"): void {
    if (kind === "out") { this.pending = { node, port }; this.setMsg(`wiring from ${node}.${port} → click an input ○`); this.render(); return; }
    if (!this.pending) { this.setMsg("click an output ● first, then an input ○"); return; }
    if (this.pending.node === node) { this.setMsg("can't wire a node to itself"); return; }
    // one source per input port: drop any existing edge into this target port
    this.edges = this.edges.filter((e) => !(e.to === node && e.to_port === port));
    this.edges.push({ from: this.pending.node, from_port: this.pending.port, to: node, to_port: port });
    this.pending = null; this.persist(); this.render();
    this.setMsg("wired.");
  }
  private cancelWire(): void { if (this.pending) { this.pending = null; this.render(); } }

  // --- render ----------------------------------------------------------------
  private render(): void {
    // nodes (rebuild; keep the SVG element)
    [...this.content.querySelectorAll(".studio-node")].forEach((n) => n.remove());
    const canvas = this.root.querySelector(".studio-canvas")!;
    canvas.querySelector(".studio-empty")?.remove();
    if (!this.nodes.length) {                          // guidance when the canvas is empty (pinned to viewport)
      const hint = document.createElement("div");
      hint.className = "studio-empty";
      hint.innerHTML = this.specs.size
        ? `<span>Click a node in the palette to add it, then wire an output ● into an input ○ and press <b>▶ Run</b>.<br><br>New here? Try <b>Load example</b>.</span>`
        : `<span>Compute palette unavailable — connect the API to use Studio.</span>`;
      canvas.appendChild(hint);
    }
    for (const node of this.nodes) this.content.appendChild(this.renderNode(node));
    this.renderEdges();
  }

  private renderNode(node: GNode): HTMLElement {
    const spec = this.specs.get(node.type)!;
    const el = document.createElement("div");
    el.className = "studio-node"; el.style.left = `${node.x}px`; el.style.top = `${node.y}px`;
    el.dataset.id = node.id;
    const head = document.createElement("div"); head.className = "studio-node-head";
    head.innerHTML = `<span>${spec.label}</span>`;
    const del = document.createElement("button"); del.className = "studio-x"; del.textContent = "✕"; del.title = "Delete node";
    del.addEventListener("click", (e) => { e.stopPropagation(); this.removeNode(node.id); });
    head.appendChild(del);
    this.makeDraggable(head, node);
    el.appendChild(head);

    // inputs (port ○ + label + editable param)
    for (const inp of spec.inputs) {
      const row = document.createElement("div"); row.className = "studio-row";
      const dot = this.portDot(node.id, inp.name, "in");
      const wired = this.edges.some((e) => e.to === node.id && e.to_port === inp.name);
      const label = document.createElement("label"); label.className = "studio-port-label"; label.textContent = inp.name;
      const field = document.createElement("input");
      field.type = "number"; field.className = "studio-field"; field.value = String(node.params[inp.name] ?? "");
      field.disabled = wired; field.title = wired ? "driven by a wired input" : "parameter";
      field.addEventListener("change", () => { node.params[inp.name] = field.value === "" ? "" : Number(field.value); this.persist(); });
      row.append(dot, label, field);
      el.appendChild(row);
    }
    // outputs (value + name + port ●)
    for (const out of spec.outputs) {
      const row = document.createElement("div"); row.className = "studio-row studio-row-out";
      const val = document.createElement("span"); val.className = "studio-out-val";
      const r = node.results?.[out];
      val.textContent = r === undefined ? "" : fmt(r);
      const name = document.createElement("span"); name.className = "studio-port-label";
      name.textContent = out;
      const dot = this.portDot(node.id, out, "out");
      row.append(val, name, dot);
      el.appendChild(row);
    }
    return el;
  }

  private portDot(node: string, port: string, kind: "in" | "out"): HTMLElement {
    const d = document.createElement("span");
    d.className = `studio-dot studio-dot-${kind}`;
    d.id = `dot-${node}-${kind}-${port}`;
    if (this.pending && kind === "out" && this.pending.node === node && this.pending.port === port) d.classList.add("active");
    d.addEventListener("click", (e) => { e.stopPropagation(); this.onPortClick(node, port, kind); });
    return d;
  }

  private renderEdges(): void {
    const crect = this.content.getBoundingClientRect();
    const center = (id: string) => {
      const el = document.getElementById(id); if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: r.left + r.width / 2 - crect.left, y: r.top + r.height / 2 - crect.top };
    };
    let paths = "";
    for (let i = 0; i < this.edges.length; i++) {
      const e = this.edges[i];
      if (!e) continue;
      const a = center(`dot-${e.from}-out-${e.from_port}`), b = center(`dot-${e.to}-in-${e.to_port}`);
      if (!a || !b) continue;
      const dx = Math.max(40, Math.abs(b.x - a.x) * 0.5);
      paths += `<path d="M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}" `
        + `class="studio-edge" data-i="${i}" />`;
    }
    this.svg.innerHTML = paths;
    this.svg.querySelectorAll<SVGPathElement>(".studio-edge").forEach((p) => {
      p.addEventListener("click", () => { this.edges.splice(Number(p.dataset.i), 1); this.persist(); this.render(); });
    });
  }

  private makeDraggable(handle: HTMLElement, node: GNode): void {
    // pointer events → works for mouse AND touch (PWA/tablet); setPointerCapture keeps the drag
    // even if the pointer outruns the node.
    handle.addEventListener("pointerdown", (e) => {
      if ((e.target as HTMLElement).classList.contains("studio-x")) return;
      e.preventDefault();
      handle.setPointerCapture?.(e.pointerId);
      const sx = e.clientX, sy = e.clientY, ox = node.x, oy = node.y;
      const move = (ev: PointerEvent) => {
        node.x = Math.max(0, ox + (ev.clientX - sx)); node.y = Math.max(0, oy + (ev.clientY - sy));
        const el = this.content.querySelector<HTMLElement>(`.studio-node[data-id="${node.id}"]`);
        if (el) { el.style.left = `${node.x}px`; el.style.top = `${node.y}px`; }
        this.renderEdges();
      };
      const up = () => { handle.removeEventListener("pointermove", move); handle.removeEventListener("pointerup", up); this.persist(); };
      handle.addEventListener("pointermove", move); handle.addEventListener("pointerup", up);
    });
  }

  // --- run / persistence -----------------------------------------------------
  private toGraph(): ComputeGraph {
    return {
      nodes: this.nodes.map((n) => ({ id: n.id, type: n.type, params: n.params })),
      edges: this.edges.map((e) => ({ from: e.from, from_port: e.from_port, to: e.to, to_port: e.to_port })),
    };
  }

  async run(): Promise<void> {
    if (!this.nodes.length) { this.setMsg("add a node first"); return; }
    this.setMsg("running…");
    try {
      const res = await this.api.runGraph(this.toGraph());
      for (const n of this.nodes) n.results = res.results[n.id];
      this.render();
      this.setMsg(`ran ${res.node_count} node(s) · order: ${res.order.join(" → ")}`);
    } catch (err) {
      this.setMsg(`run failed: ${(err as Error).message}`);
    }
  }

  private clear(): void { this.nodes = []; this.edges = []; this.pending = null; this.seq = 0; this.persist(); this.render(); this.setMsg("cleared."); }

  /** A ready-made zoning → cost → yield chain so the value is obvious on first open. */
  private loadExample(): void {
    if (!this.specs.has("zoning_massing")) { this.setMsg("palette not loaded"); return; }
    this.clear();
    const z = this.addNode("zoning_massing", 40, 60);
    const c = this.addNode("cost_from_gfa", 360, 60);
    const y = this.addNode("yield_on_cost", 680, 60);
    this.edges.push(
      { from: z.id, from_port: "buildable_gfa_sf", to: c.id, to_port: "buildable_gfa_sf" },
      { from: z.id, from_port: "units", to: y.id, to_port: "units" },
      { from: c.id, from_port: "total_cost", to: y.id, to_port: "total_cost" },
    );
    this.persist(); this.render();
    this.setMsg("example loaded — press Run.");
  }

  private persist(): void {
    try { localStorage.setItem(STORE, JSON.stringify({ nodes: this.nodes, edges: this.edges, seq: this.seq })); } catch { /* quota */ }
  }
  private restore(): void {
    try {
      const raw = localStorage.getItem(STORE); if (!raw) return;
      const s = JSON.parse(raw);
      this.nodes = (s.nodes || []).filter((n: GNode) => this.specs.has(n.type));
      this.edges = s.edges || []; this.seq = s.seq || this.nodes.length;
    } catch { /* ignore corrupt state */ }
  }

  private setMsg(s: string): void { if (this.status) this.status.textContent = s; this.setStatus?.(`studio: ${s}`); }
}

function fmt(v: unknown): string {
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString() : (Math.abs(v) < 1 ? v.toFixed(4) : v.toLocaleString(undefined, { maximumFractionDigits: 2 }));
  return String(v);
}
