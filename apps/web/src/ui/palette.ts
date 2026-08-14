/**
 * Command palette (Cmd/Ctrl-K) — the fast way to reach any workspace, module, tool, or record.
 * Dependency-free: a dimmed overlay with a search box, fuzzy-ranked static commands, plus an
 * optional async provider (record search). Keyboard-first: ↑/↓ to move, Enter to run, Esc to close,
 * the same shortcut toggles it. Matches the app's dark theme via CSS variables.
 *
 * **R24-CMDK-GROUPS (v0.3.779).** The audit's move 01 asks for results grouped by *verb / record /
 * element / report*, "never a flat list", and ranked by what you last did. `Command.group` had been
 * declared on this interface since the palette shipped and **`paint()` never read it** — the grouping
 * was designed and left unwired, so 130-plus modules, six workspaces and every record hit arrived as
 * one undifferentiated column.
 *
 * Two decisions worth stating, because both were the cheap way out:
 *
 * * **The group is inferred when a caller does not supply one.** `inferGroup()` derives it from the
 *   existing `hint` ("Workspace" → *Go to*, "Action" → *Do*, …). That means grouping improves for
 *   every existing call site without editing any of them — and a caller that knows better can still
 *   say so explicitly. The alternative, requiring `group` everywhere, would have made this change
 *   touch a file another session is editing, for no gain.
 * * **Recency is per-command, not per-group.** Boosting a whole group because you used one thing in
 *   it makes the ranking feel arbitrary; boosting the twenty commands you actually ran makes ⌘K
 *   converge on your own working set, which is the entire claim behind "ranked by your last 20
 *   actions".
 */
import { escapeHtml } from "./feedback";

export interface Command {
  id: string;
  label: string;
  hint?: string;                 // right-aligned context (e.g. "Module", "Go to", section)
  /** Result section. Omitted → inferred from `hint`; see `inferGroup`. */
  group?: string;
  run: () => void;
}

/**
 * Section order — the audit's grouping, read top-down the way the question is asked.
 *
 * *Do* leads because a verb is the only kind of result that changes something; navigation sits below
 * it because arriving somewhere is the slow way to do the same job. Anything unrecognised sorts after
 * these, alphabetically, rather than being forced into a bucket it does not belong in.
 */
export const GROUP_ORDER = ["Do", "Records", "Elements", "Reports", "Modules", "Go to"] as const;

/** Where an explicit-group-less command belongs, from the `hint` its caller already sets. */
export function inferGroup(hint?: string): string {
  const h = (hint ?? "").toLowerCase();
  if (h === "workspace") return "Go to";
  if (h === "action") return "Do";
  if (h === "record") return "Records";
  if (h === "element") return "Elements";
  if (h === "report") return "Reports";
  return "Modules";              // the long tail: every module carries its section as the hint
}

export const groupOf = (c: Command): string => c.group ?? inferGroup(c.hint);

/** Position in `GROUP_ORDER`; unknown groups sort after all known ones. */
export function groupRank(group: string): number {
  const i = (GROUP_ORDER as readonly string[]).indexOf(group);
  return i < 0 ? GROUP_ORDER.length : i;
}

const RECENT_KEY = "cmdk-recent";
const RECENT_MAX = 20;

/** The last commands actually run, newest first. Survives reload; degrades to [] without storage. */
export function readRecentCommands(): string[] {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]") as string[]; }
  catch { return []; }
}

export function noteCommandRun(id: string): void {
  try {
    const next = [id, ...readRecentCommands().filter((x) => x !== id)].slice(0, RECENT_MAX);
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch { /* private mode / no storage — ranking degrades, the palette still works */ }
}

/**
 * Recency bonus: newest run is worth the most, the twentieth almost nothing.
 *
 * Capped below the prefix-match boost on purpose. What you typed must always beat what you happen to
 * have run before — a palette that overrides an exact match with a habit is one you stop trusting.
 */
export function recencyBoost(id: string, recent: readonly string[]): number {
  const i = recent.indexOf(id);
  return i < 0 ? 0 : 4 * (1 - i / RECENT_MAX);
}

/** Group, then score, then label — a stable order so the list never reshuffles under the cursor. */
export function orderForDisplay(scored: { c: Command; s: number }[]): Command[] {
  return [...scored].sort((a, b) => {
    const g = groupRank(groupOf(a.c)) - groupRank(groupOf(b.c));
    if (g !== 0) return g;
    if (b.s !== a.s) return b.s - a.s;
    return a.c.label.localeCompare(b.c.label);
  }).map((x) => x.c);
}

/**
 * Cap **per group**, not just overall.
 *
 * Caught in the browser rather than in a test, which is the only reason it is here: grouping alone
 * made the palette *worse*. `Go to` sorts last by design — arriving somewhere is the slow way to do a
 * job — and with 130-plus modules ahead of it, a flat 40-row cap cut every workspace off the list.
 * The palette gained sections and quietly lost navigation.
 *
 * So the cap has to be per section. A palette is a shortcut, not a browser: eight of a kind is
 * already more than anyone reads before retyping, and reserving room for the sections below is worth
 * more than the ninth module.
 */
export function takePerGroup(cmds: readonly Command[], perGroup: number, total: number): Command[] {
  const seen = new Map<string, number>();
  const out: Command[] = [];
  for (const c of cmds) {
    if (out.length >= total) break;
    const g = groupOf(c);
    const n = seen.get(g) ?? 0;
    if (n >= perGroup) continue;
    seen.set(g, n + 1);
    out.push(c);
  }
  return out;
}

/**
 * Fold late-arriving async results into the already-grouped list, **re-sorted by section**.
 *
 * The defect this replaces was invisible in the code and obvious on screen. `refresh()` did
 * `items = items.concat(extra)`, so a record hit — group *Records*, which sorts second — landed
 * underneath *Modules* and *Go to*, under a **second** `RECORDS` heading further down the list. The
 * grouping was a property of the first paint only, and the section that the async provider exists to
 * fill was the one it could never reach. Adding two more async sections (Elements, Reports) would
 * have made it three duplicate headings instead of one.
 *
 * The sort key is the group rank *alone*, and `Array#sort` is stable per spec (ES2019), so each
 * side's own ranking survives inside its section. Re-scoring here would discard the async provider's
 * relevance order, which is the only ordering information it has — the palette does not know why the
 * server ranked one record above another.
 *
 * `pinned` rows bypass the cap entirely and are appended last: see `askFallback`.
 */
export function mergeResults(
  base: readonly Command[],
  extra: readonly Command[],
  opts: { perGroup?: number; total?: number; pinned?: readonly Command[] } = {},
): Command[] {
  const { perGroup = 8, total = 40, pinned = [] } = opts;
  const seen = new Set<string>();
  const all: Command[] = [];
  for (const c of [...base, ...extra]) {
    if (seen.has(c.id)) continue;
    seen.add(c.id);
    all.push(c);
  }
  const capped = takePerGroup(
    [...all].sort((a, b) => groupRank(groupOf(a)) - groupRank(groupOf(b))),
    perGroup, total,
  );
  const have = new Set(capped.map((c) => c.id));
  return capped.concat(pinned.filter((p) => !have.has(p.id)));
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
  /**
   * Always-last row for a non-empty query — appended after the per-section cap, so it is the one
   * result that cannot be trimmed away. Return `null` to offer nothing.
   */
  fallback?: (q: string) => Command | null;
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
      const recent = readRecentCommands();
      // Empty query: what you last did, in group order. The old behaviour — the first 40 commands in
      // registration order — meant opening the palette always showed the same six workspaces first,
      // whatever you had actually been doing.
      if (!q) return takePerGroup(orderForDisplay(cmds.map((c) => ({ c, s: recencyBoost(c.id, recent) }))), 8, 40);
      return takePerGroup(orderForDisplay(
        cmds.map((c) => ({
          c,
          s: Math.max(fuzzy(q, c.label), fuzzy(q, c.hint ?? "") - 2) + recencyBoost(c.id, recent),
        })).filter((x) => x.s > 0),
      ), 8, 30);
    };

    /** Row elements in `items` order — headers are interleaved into the list, so the DOM index and
     *  the selection index are not the same number. Keeping them apart is what stops ↑/↓ from
     *  "landing" on a heading. */
    let rows: HTMLElement[] = [];

    const paint = () => {
      list.innerHTML = "";
      rows = [];
      if (!items.length) { list.innerHTML = `<div class="meta" style="padding:12px">No matches</div>`; return; }
      let lastGroup: string | null = null;
      items.forEach((c, i) => {
        const g = groupOf(c);
        if (g !== lastGroup) {
          lastGroup = g;
          const h = document.createElement("div");
          h.className = "meta";
          h.style.cssText = "padding:8px 12px 4px;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;opacity:.6";
          h.textContent = g;                       // textContent: a module section reaches this
          list.appendChild(h);
        }
        const row = document.createElement("button");
        row.className = "cmdk-row" + (i === active ? " on" : "");
        row.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:10px;width:100%;text-align:left;border:0;background:"
          + (i === active ? "var(--accent,#3b82f6)22" : "transparent") + ";color:inherit;padding:9px 12px;border-radius:7px;cursor:pointer;font-size:13px";
        row.innerHTML = `<span>${escapeHtml(c.label)}</span>` + (c.hint ? `<span class="meta" style="font-size:11px;opacity:.7">${escapeHtml(c.hint)}</span>` : "");
        row.onmousemove = () => { if (active !== i) { active = i; paint(); } };
        row.onclick = () => choose(i);
        list.appendChild(row);
        rows.push(row);
      });
      rows[active]?.scrollIntoView({ block: "nearest" });
    };

    const refresh = () => {
      const q = input.value.trim();
      const fb = q ? opts.fallback?.(q) ?? null : null;
      const pinned = fb ? [fb] : [];
      // `base` is kept, not `items`, so a second async result merges against the ranked static list
      // rather than against a list that already has the first async batch folded into it — otherwise
      // the per-section cap would be applied twice and drop rows on the second keystroke.
      const base = rankStatic(q);
      items = mergeResults(base, [], { pinned }); active = 0; paint();
      if (opts.search && q.length >= 2) {
        const seq = ++searchSeq;
        void opts.search(q).then((extra) => {
          if (seq !== searchSeq || !ov) return;                // stale (user kept typing / closed)
          items = mergeResults(base, extra, { pinned }); paint();
        }).catch(() => {});
      }
    };

    const close = () => { ov?.remove(); ov = null; prevFocus?.focus?.(); };
    // Note the run BEFORE closing: `run()` can navigate, and a recency write that races a route
    // change is a recency write that sometimes does not happen.
    const choose = (i: number) => { const c = items[i]; if (!c) return; noteCommandRun(c.id); close(); c.run(); };

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
