import type { ModuleGraph } from "../../api/client";
import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * Module-relations graph — visualise how the config-driven modules wire together. Nodes are modules,
 * edges are cross-module links (reference fields solid, rollup fields dashed). A circular layout laid
 * out by workspace/section, node radius by in-degree (how referenced a module is), so hubs like the
 * cost code stand out. A workspace filter tames the ~180-node full graph.
 */

const WS_COLORS: Record<string, string> = {
  construction: "#4a8cff", developer: "#33b27a", design: "#b083d6", operations: "#e0a23a", "": "#8a8f98",
};

function graphSvg(g: ModuleGraph): string {
  const W = 760, H = 620, cx = W / 2, cy = H / 2, R = Math.min(W, H) / 2 - 70;
  const nodes = [...g.nodes].sort((a, b) =>
    (a.workspace || "").localeCompare(b.workspace || "") || (a.section || "").localeCompare(b.section || "") || a.key.localeCompare(b.key));
  const n = nodes.length || 1;
  const pos = new Map<string, { x: number; y: number }>();
  nodes.forEach((nd, i) => {
    const ang = (i / n) * Math.PI * 2 - Math.PI / 2;
    pos.set(nd.key, { x: cx + R * Math.cos(ang), y: cy + R * Math.sin(ang) });
  });
  const parts: string[] = [`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" font-family="system-ui,sans-serif">`];
  // edges first (under the nodes), curved toward the centre so the hub structure reads
  for (const e of g.edges) {
    const a = pos.get(e.source), b = pos.get(e.target);
    if (!a || !b) continue;
    const dash = e.kind === "rollup" ? ' stroke-dasharray="3 3"' : "";
    const mx = (a.x + b.x) / 2 + (cx - (a.x + b.x) / 2) * 0.35;
    const my = (a.y + b.y) / 2 + (cy - (a.y + b.y) / 2) * 0.35;
    parts.push(`<path d="M${a.x.toFixed(1)},${a.y.toFixed(1)} Q${mx.toFixed(1)},${my.toFixed(1)} ${b.x.toFixed(1)},${b.y.toFixed(1)}" `
      + `fill="none" stroke="#c8ccd4" stroke-width="0.8" opacity="0.5"${dash}/>`);
  }
  // nodes
  for (const nd of nodes) {
    const p = pos.get(nd.key)!;
    const r = 3 + Math.min(10, nd.in_degree * 1.2);
    const col = WS_COLORS[nd.workspace] || WS_COLORS[""];
    parts.push(`<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${r.toFixed(1)}" fill="${col}" opacity="0.9">`
      + `<title>${esc(nd.label)} (${nd.key}) · ${nd.workspace || "—"} · ←${nd.in_degree} →${nd.out_degree}</title></circle>`);
    // label only the hubs (in-degree ≥ 3) to keep the ring legible
    if (nd.in_degree >= 3) {
      const lx = p.x + (p.x - cx) * 0.08, ly = p.y + (p.y - cy) * 0.08;
      const anchor = p.x < cx ? "end" : "start";
      parts.push(`<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" font-size="9" fill="#555" text-anchor="${anchor}">${esc(nd.label)}</text>`);
    }
  }
  parts.push("</svg>");
  return parts.join("");
}

export async function renderModuleGraph(ctx: PanelContext) {
  const root = ctx.root; root.innerHTML = "";
  root.appendChild(ctx.bar("🕸 Module Relations", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));

  const intro = document.createElement("div"); intro.className = "meta"; intro.style.marginBottom = "8px";
  intro.textContent = "How the config-driven modules wire together: each node is a module, each edge a "
    + "cross-module link (reference fields solid, rollup fields dashed). Node size = how often a module is "
    + "referenced. Filter by workspace to declutter; hover a node for its links.";
  root.appendChild(intro);

  const controls = document.createElement("div"); controls.style.cssText = "display:flex;gap:8px;align-items:center;margin-bottom:6px";
  const sel = document.createElement("select"); sel.className = "portal-filter";
  sel.innerHTML = `<option value="">All workspaces</option>`
    + ["construction", "developer", "design", "operations"].map((w) => `<option value="${w}">${w}</option>`).join("");
  controls.appendChild(Object.assign(document.createElement("span"), { className: "meta", textContent: "Workspace:" }));
  controls.appendChild(sel);
  const summary = document.createElement("span"); summary.className = "meta";
  controls.appendChild(summary);
  root.appendChild(controls);

  const chart = document.createElement("div"); chart.style.overflowX = "auto";
  chart.innerHTML = `<div class="meta">loading graph…</div>`;
  root.appendChild(chart);
  const hubs = document.createElement("div"); hubs.style.marginTop = "6px";
  root.appendChild(hubs);

  const load = async () => {
    chart.innerHTML = `<div class="meta">loading graph…</div>`;
    try {
      const g = await ctx.host.api.modulesGraph(sel.value || undefined);
      summary.textContent = `${g.node_count} modules · ${g.edge_count} links · ${g.orphan_count} unlinked`;
      chart.innerHTML = graphSvg(g);
      hubs.innerHTML = `<div class="meta">Most-referenced hubs: `
        + g.most_referenced.slice(0, 6).map((h) => `<b>${esc(h.label)}</b> (${h.in_degree})`).join(" · ") + `</div>`;
    } catch (e) { chart.innerHTML = `<div class="meta">Graph unavailable: ${(e as Error).message}</div>`; }
  };
  sel.onchange = () => void load();
  void load();
}
