/** Readable analysis results — a roomy modal for output that used to be crammed into the
 *  narrow tool rail (cost / energy / MEP / IDS / clash). Themed with the app's CSS variables;
 *  no dependencies. Pair the trigger button (in the rail) with a one-line status; the full,
 *  scannable result opens here. */

let host: HTMLElement | null = null;

function close() {
  host?.remove();
  host = null;
  document.removeEventListener("keydown", onKey);
}
function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") close();
}

/** Open a result modal titled `title`; `render` fills the scrollable body. Replaces any open one. */
export function showResult(title: string, render: (body: HTMLElement) => void): void {
  close();
  host = document.createElement("div");
  host.className = "result-overlay";
  const card = document.createElement("div");
  card.className = "result-card";
  const head = document.createElement("div");
  head.className = "result-head";
  head.innerHTML = `<strong>${title}</strong>`;
  const x = document.createElement("button");
  x.className = "result-close"; x.textContent = "✕"; x.title = "Close (Esc)"; x.onclick = close;
  head.appendChild(x);
  const body = document.createElement("div");
  body.className = "result-body";
  card.append(head, body);
  host.appendChild(card);
  host.onclick = (e) => { if (e.target === host) close(); };
  document.addEventListener("keydown", onKey);
  document.body.appendChild(host);
  render(body);
}

/** Key/value table — e.g. a cost roll-up. `bar` (0..1) draws a proportional fill behind the value. */
export function kvTable(rows: { k: string; v: string; bar?: number; strong?: boolean }[]): HTMLElement {
  const t = document.createElement("table");
  t.className = "result-table";
  for (const r of rows) {
    const tr = document.createElement("tr");
    if (r.strong) tr.className = "strong";
    const k = document.createElement("td"); k.className = "k"; k.textContent = r.k;
    const v = document.createElement("td"); v.className = "v"; v.textContent = r.v;
    if (r.bar != null) {
      const pct = Math.max(0, Math.min(1, r.bar)) * 100;
      v.style.background = `linear-gradient(to right, rgba(74,140,255,.22) ${pct}%, transparent ${pct}%)`;
    }
    tr.append(k, v); t.appendChild(tr);
  }
  return t;
}

/** Compact metric grid — e.g. energy EUI / loads / areas. */
export function metricGrid(items: { label: string; value: string; sub?: string }[]): HTMLElement {
  const g = document.createElement("div");
  g.className = "result-metrics";
  for (const m of items) {
    const cell = document.createElement("div");
    cell.className = "result-metric";
    cell.innerHTML = `<div class="mv">${m.value}</div><div class="ml">${m.label}</div>` +
      (m.sub ? `<div class="ms">${m.sub}</div>` : "");
    g.appendChild(cell);
  }
  return g;
}

/** A status/section line in the result body. */
export function resultNote(html: string, kind: "ok" | "bad" | "" = ""): HTMLElement {
  const d = document.createElement("div");
  d.className = `result-note ${kind}`.trim();
  d.innerHTML = html;
  return d;
}
