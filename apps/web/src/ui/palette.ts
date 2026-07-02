/**
 * Command palette (Cmd/Ctrl-K) — the fast way to reach any workspace, module, tool, or record.
 * Dependency-free: a dimmed overlay with a search box, fuzzy-ranked static commands, plus an
 * optional async provider (record search). Keyboard-first: ↑/↓ to move, Enter to run, Esc to close,
 * the same shortcut toggles it. Matches the app's dark theme via CSS variables.
 */
import { escapeHtml } from "./feedback";

export interface Command {
  id: string;
  label: string;
  hint?: string;                 // right-aligned context (e.g. "Module", "Go to", section)
  group?: string;
  run: () => void;
}

/** Subsequence fuzzy score: all query chars must appear in order; earlier/contiguous = higher. */
function fuzzy(q: string, text: string): number {
  if (!q) return 1;
  const t = text.toLowerCase();
  let ti = 0, score = 0, streak = 0;
  for (const ch of q.toLowerCase()) {
    const i = t.indexOf(ch, ti);
    if (i < 0) return -1;
    streak = i === ti ? streak + 2 : 0;             // reward contiguous runs
    score += 1 + streak - Math.min(i - ti, 3) * 0.1; // mild penalty for gaps
    ti = i + 1;
  }
  if (t.startsWith(q.toLowerCase())) score += 5;     // strong prefix boost
  return score;
}

export function initCommandPalette(opts: {
  commands: () => Command[];
  search?: (q: string) => Promise<Command[]>;
}): { open: () => void } {
  let ov: HTMLDivElement | null = null;

  const open = () => {
    if (ov) return;
    const prevFocus = document.activeElement as HTMLElement | null;
    ov = document.createElement("div");
    ov.className = "cmdk-ov";
    ov.style.cssText = "position:fixed;inset:0;z-index:240;background:#0009;display:flex;align-items:flex-start;justify-content:center;padding-top:12vh";
    const box = document.createElement("div");
    box.style.cssText = "background:var(--panel);border:1px solid var(--line);border-radius:12px;width:min(620px,92vw);max-height:70vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 20px 60px #000a";
    const input = document.createElement("input");
    input.type = "text"; input.placeholder = "Search commands, modules, records…"; input.setAttribute("aria-label", "Command palette");
    input.style.cssText = "border:0;border-bottom:1px solid var(--line);background:transparent;color:var(--fg,inherit);padding:14px 16px;font-size:15px;outline:none";
    const list = document.createElement("div");
    list.style.cssText = "overflow:auto;padding:6px";
    box.append(input, list); ov.append(box); document.body.appendChild(ov);

    let items: Command[] = [];
    let active = 0;
    let searchSeq = 0;

    const rankStatic = (q: string): Command[] => {
      const cmds = opts.commands();
      if (!q) return cmds.slice(0, 40);
      return cmds.map((c) => ({ c, s: Math.max(fuzzy(q, c.label), fuzzy(q, c.hint ?? "") - 2) }))
        .filter((x) => x.s > 0).sort((a, b) => b.s - a.s).slice(0, 30).map((x) => x.c);
    };

    const paint = () => {
      list.innerHTML = "";
      if (!items.length) { list.innerHTML = `<div class="meta" style="padding:12px">No matches</div>`; return; }
      items.forEach((c, i) => {
        const row = document.createElement("button");
        row.className = "cmdk-row" + (i === active ? " on" : "");
        row.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:10px;width:100%;text-align:left;border:0;background:"
          + (i === active ? "var(--accent,#3b82f6)22" : "transparent") + ";color:inherit;padding:9px 12px;border-radius:7px;cursor:pointer;font-size:13px";
        row.innerHTML = `<span>${escapeHtml(c.label)}</span>` + (c.hint ? `<span class="meta" style="font-size:11px;opacity:.7">${escapeHtml(c.hint)}</span>` : "");
        row.onmousemove = () => { if (active !== i) { active = i; paint(); } };
        row.onclick = () => choose(i);
        list.appendChild(row);
      });
      list.children[active]?.scrollIntoView({ block: "nearest" });
    };

    const refresh = () => {
      const q = input.value.trim();
      items = rankStatic(q); active = 0; paint();
      if (opts.search && q.length >= 2) {
        const seq = ++searchSeq;
        void opts.search(q).then((extra) => {
          if (seq !== searchSeq || !ov) return;                // stale (user kept typing / closed)
          const have = new Set(items.map((c) => c.id));
          items = items.concat(extra.filter((c) => !have.has(c.id))); paint();
        }).catch(() => {});
      }
    };

    const close = () => { ov?.remove(); ov = null; prevFocus?.focus?.(); };
    const choose = (i: number) => { const c = items[i]; if (!c) return; close(); c.run(); };

    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); active = Math.min(active + 1, items.length - 1); paint(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); active = Math.max(active - 1, 0); paint(); }
      else if (e.key === "Enter") { e.preventDefault(); choose(active); }
      else if (e.key === "Escape") { e.preventDefault(); close(); }
    });
    input.addEventListener("input", refresh);
    ov.addEventListener("mousedown", (e) => { if (e.target === ov) close(); });
    refresh(); input.focus();
  };

  const toggle = () => (ov ? (ov.remove(), (ov = null)) : open());
  window.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) { e.preventDefault(); toggle(); }
  });
  return { open };   // let a visible header affordance open the palette (discoverability)
}
