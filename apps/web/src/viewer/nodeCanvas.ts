/** AUTH-VS — visual node authoring canvas.
 *
 *  A draggable node-graph editor over the server's recipe-graph engine (`POST /projects/{pid}/edit/graph`).
 *  Drop recipe nodes, wire one node's output into another's input, and run the whole graph as a single
 *  GUID-stable authoring pass. Each node carries a params JSON; reference an upstream node's created GUID
 *  with `{"$from": "<node id>"}` (wiring two ports inserts that reference for you). No dependencies —
 *  plain DOM + one SVG layer for the edges, themed with the app's CSS variables.
 */

type Graph = { nodes: { id: string; recipe: string; params: Record<string, unknown> }[];
               edges: { from: string; to: string }[] };
type RunResult = { node_count: number; order: string[]; outputs: Record<string, unknown> };

interface NodeCanvasOpts {
  recipes: string[];
  runGraph: (graph: Graph) => Promise<RunResult>;
  notify: (message: string, kind?: "error" | "info" | "success") => void;
}

interface CanvasNode {
  id: string; recipe: string; x: number; y: number;
  el: HTMLElement; paramsInput: HTMLTextAreaElement;
}

// a few sensible starter params per recipe so a fresh node is runnable, not blank
const STARTER: Record<string, Record<string, unknown>> = {
  add_wall: { start: [0, 0], end: [5, 0], height: 3, thickness: 0.2 },
  add_column: { point: [0, 0], height: 3, width: 0.4, depth: 0.4 },
  add_beam: { start: [0, 0], end: [5, 0], width: 0.3, depth: 0.5 },
  add_slab: { points: [[0, 0], [5, 0], [5, 4], [0, 4]], thickness: 0.2 },
  add_base_plate: { column_guid: { $from: "n1" }, width: 0.5 },
  add_curtain_wall: { start: [0, 0], end: [6, 0], height: 3.5 },
  derive_analytical: {},
};

export function openNodeCanvas(opts: NodeCanvasOpts): void {
  const nodes: CanvasNode[] = [];
  const edges: { from: string; to: string }[] = [];
  let seq = 0;
  let wiringFrom: string | null = null;         // node id whose output port was clicked first

  const overlay = document.createElement("div");
  overlay.className = "nodecanvas-overlay";
  overlay.style.cssText = "position:fixed;inset:0;z-index:60;background:rgba(0,0,0,.55);display:flex;"
    + "align-items:center;justify-content:center";
  const card = document.createElement("div");
  card.setAttribute("role", "dialog"); card.setAttribute("aria-modal", "true");
  card.setAttribute("aria-label", "Visual node authoring");
  card.style.cssText = "width:min(1000px,94vw);height:min(680px,90vh);display:flex;flex-direction:column;"
    + "background:var(--panel,#0f172a);color:var(--fg,#e2e8f0);border:1px solid var(--border,#334155);"
    + "border-radius:12px;overflow:hidden;box-shadow:0 12px 48px rgba(0,0,0,.5)";

  // header
  const head = document.createElement("div");
  head.style.cssText = "display:flex;align-items:center;gap:10px;padding:8px 12px;border-bottom:1px solid var(--border,#334155)";
  head.innerHTML = "<strong>🕸 Visual node authoring</strong>"
    + "<span style='font-size:11px;opacity:.7'>Drop recipes · drag to move · click an output ● then an input ○ to wire · Run</span>";
  const spacer = document.createElement("div"); spacer.style.flex = "1";
  const runBtn = document.createElement("button"); runBtn.className = "tool-btn"; runBtn.textContent = "▶ Run graph";
  runBtn.style.cssText = "font-size:12px;padding:4px 12px";
  const closeBtn = document.createElement("button"); closeBtn.className = "tool-btn"; closeBtn.textContent = "✕";
  closeBtn.setAttribute("aria-label", "Close"); closeBtn.style.cssText = "font-size:12px;padding:4px 8px";
  head.append(spacer, runBtn, closeBtn);

  // palette
  const palette = document.createElement("div");
  palette.style.cssText = "display:flex;flex-wrap:wrap;gap:4px;padding:6px 12px;border-bottom:1px solid var(--border,#334155)";
  for (const r of opts.recipes) {
    const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = "＋ " + r;
    b.style.cssText = "font-size:10.5px;padding:2px 8px";
    b.onclick = () => addNode(r);
    palette.appendChild(b);
  }

  // canvas + SVG edge layer
  const canvas = document.createElement("div");
  canvas.className = "nodecanvas";
  canvas.style.cssText = "position:relative;flex:1;overflow:hidden;background:"
    + "radial-gradient(circle, rgba(148,163,184,.18) 1px, transparent 1px);background-size:22px 22px";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", "100%"); svg.setAttribute("height", "100%");
  svg.style.cssText = "position:absolute;inset:0;pointer-events:none";
  canvas.appendChild(svg);

  const status = document.createElement("div");
  status.style.cssText = "padding:6px 12px;border-top:1px solid var(--border,#334155);font-size:11px;min-height:18px;opacity:.85";
  status.textContent = "Empty graph — add a recipe node from the palette to begin.";

  card.append(head, palette, canvas, status);
  overlay.appendChild(card);

  function close() { overlay.remove(); document.removeEventListener("keydown", onKey); }
  function onKey(e: KeyboardEvent) { if (e.key === "Escape") close(); }
  closeBtn.onclick = close;
  overlay.onclick = (e) => { if (e.target === overlay) close(); };
  document.addEventListener("keydown", onKey);

  function redrawEdges() {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    for (const e of edges) {
      const a = nodes.find((n) => n.id === e.from), b = nodes.find((n) => n.id === e.to);
      if (!a || !b) continue;
      const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
      const x1 = a.x + 168, y1 = a.y + 22, x2 = b.x, y2 = b.y + 22;    // out port → in port
      const mx = (x1 + x2) / 2;
      line.setAttribute("d", `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`);
      line.setAttribute("fill", "none");
      line.setAttribute("stroke", "var(--accent,#4a8cff)");
      line.setAttribute("stroke-width", "2");
      svg.appendChild(line);
    }
  }

  function setStatus(msg: string) { status.textContent = msg; }

  function addNode(recipe: string) {
    seq += 1;
    const id = "n" + seq;
    const x = 30 + (nodes.length % 4) * 190, y = 30 + Math.floor(nodes.length / 4) * 120;
    const el = document.createElement("div");
    el.className = "nc-node";
    el.style.cssText = `position:absolute;left:${x}px;top:${y}px;width:168px;`
      + "background:var(--panel-2,#1e293b);border:1px solid var(--border,#334155);border-radius:8px;"
      + "box-shadow:0 2px 8px rgba(0,0,0,.3);font-size:11px;user-select:none";
    const bar = document.createElement("div");
    bar.style.cssText = "display:flex;align-items:center;gap:4px;padding:4px 6px;cursor:grab;"
      + "background:var(--accent-weak,#233047);border-radius:8px 8px 0 0";
    bar.innerHTML = `<span style="font-weight:600">${id}</span><span style="opacity:.75">${recipe}</span>`;
    const del = document.createElement("button"); del.textContent = "✕"; del.title = "Remove node";
    del.style.cssText = "margin-left:auto;background:none;border:none;color:inherit;cursor:pointer;font-size:11px";
    del.onclick = (ev) => { ev.stopPropagation(); removeNode(id); };
    bar.appendChild(del);
    const paramsInput = document.createElement("textarea");
    paramsInput.value = JSON.stringify(STARTER[recipe] ?? {}, null, 0);
    paramsInput.spellcheck = false;
    paramsInput.setAttribute("aria-label", `${id} params (JSON)`);
    paramsInput.style.cssText = "width:100%;box-sizing:border-box;height:38px;resize:none;font-size:10px;"
      + "font-family:ui-monospace,monospace;border:none;border-top:1px solid var(--border,#334155);"
      + "background:transparent;color:inherit;padding:3px 6px";
    // ports
    const inPort = document.createElement("div"); inPort.title = "Input — click after an output to wire";
    inPort.style.cssText = "position:absolute;left:-7px;top:15px;width:13px;height:13px;border-radius:50%;"
      + "background:var(--panel,#0f172a);border:2px solid var(--accent,#4a8cff);cursor:pointer";
    inPort.onclick = () => wireTo(id);
    const outPort = document.createElement("div"); outPort.title = "Output — click, then click an input to wire";
    outPort.style.cssText = "position:absolute;right:-7px;top:15px;width:13px;height:13px;border-radius:50%;"
      + "background:var(--accent,#4a8cff);border:2px solid var(--panel,#0f172a);cursor:pointer";
    outPort.onclick = () => { wiringFrom = id; setStatus(`Wiring from ${id} — click another node's input ○ to connect.`); };
    el.append(bar, paramsInput, inPort, outPort);
    canvas.appendChild(el);

    const node: CanvasNode = { id, recipe, x, y, el, paramsInput };
    nodes.push(node);
    makeDraggable(node, bar);
    setStatus(`${nodes.length} node(s). Wire outputs → inputs, then Run.`);
    redrawEdges();
  }

  function removeNode(id: string) {
    const i = nodes.findIndex((n) => n.id === id);
    if (i < 0) return;
    nodes[i]!.el.remove();
    nodes.splice(i, 1);
    for (let k = edges.length - 1; k >= 0; k--) if (edges[k]!.from === id || edges[k]!.to === id) edges.splice(k, 1);
    redrawEdges();
    setStatus(`${nodes.length} node(s).`);
  }

  function wireTo(toId: string) {
    if (!wiringFrom || wiringFrom === toId) { wiringFrom = null; return; }
    const from = wiringFrom; wiringFrom = null;
    if (edges.some((e) => e.from === from && e.to === toId)) { setStatus("Already wired."); return; }
    edges.push({ from, to: toId });
    // inject the upstream reference into the target's params so the run actually threads the GUID:
    // fill the first param whose value is null/"" or a {$from} placeholder, else add `ref`.
    try {
      const p = JSON.parse(nodes.find((n) => n.id === toId)!.paramsInput.value || "{}") as Record<string, unknown>;
      const slot = Object.keys(p).find((k) => {
        const v = p[k];
        return v == null || v === "" || (typeof v === "object" && v !== null && "$from" in (v as object));
      });
      p[slot ?? "ref"] = { $from: from };
      nodes.find((n) => n.id === toId)!.paramsInput.value = JSON.stringify(p, null, 0);
    } catch { /* leave params as-is; the edge still orders the run */ }
    redrawEdges();
    setStatus(`Wired ${from} → ${toId}. Reference it in params as {"$from":"${from}"}.`);
  }

  function makeDraggable(node: CanvasNode, handle: HTMLElement) {
    let sx = 0, sy = 0, ox = 0, oy = 0, dragging = false;
    handle.addEventListener("mousedown", (e) => {
      dragging = true; sx = e.clientX; sy = e.clientY; ox = node.x; oy = node.y;
      handle.style.cursor = "grabbing"; e.preventDefault();
    });
    window.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      node.x = Math.max(0, ox + (e.clientX - sx)); node.y = Math.max(0, oy + (e.clientY - sy));
      node.el.style.left = node.x + "px"; node.el.style.top = node.y + "px";
      redrawEdges();
    });
    window.addEventListener("mouseup", () => { if (dragging) { dragging = false; handle.style.cursor = "grab"; } });
  }

  runBtn.onclick = async () => {
    if (!nodes.length) { setStatus("Add at least one node first."); return; }
    let graph: Graph;
    try {
      graph = { nodes: nodes.map((n) => ({ id: n.id, recipe: n.recipe,
        params: JSON.parse(n.paramsInput.value || "{}") as Record<string, unknown> })), edges };
    } catch { setStatus("⚠ A node's params is not valid JSON — fix it and re-run."); return; }
    runBtn.disabled = true; setStatus("Running the graph…");
    try {
      const r = await opts.runGraph(graph);
      setStatus(`✓ Ran ${r.node_count} node(s): ${r.order.join(" → ")}.`);
      opts.notify(`Node graph ran — ${r.node_count} node(s) authored`, "success");
    } catch (e) {
      setStatus("⚠ " + (e as Error).message);
      opts.notify((e as Error).message, "error");
    } finally { runBtn.disabled = false; }
  };

  document.body.appendChild(overlay);
  runBtn.focus();
}
