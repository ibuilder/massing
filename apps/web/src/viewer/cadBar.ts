// The CAD command line — extracted from `app.ts` (R39-DECOMP-VIEWER) and given an interactive mode.
//
// Two ways to drive the same six commands, over the same GUID-stable edit recipes:
//
//   TYPED     `WALL 0,0 5,0 3` — the whole line at once, for a drafter who knows what they want.
//   PROMPTED  `WALL` — arms the command, which then ASKS: "Specify start point:", "Specify end point:".
//
// The prompted path is new: before this, a bare `WALL` was an error message telling you the usage and
// making you retype the verb. Both paths end in `parseCadCommand`, because `promptLoop`
// collects TOKENS and hands back an ordinary command line — so there is exactly one grammar, one set of
// defaults and one set of validation messages, and a prompted wall cannot drift from a typed one.
//
// Extracted rather than added in place because `app.ts` is at its per-file size ratchet with no
// headroom, and a command line is a self-contained surface: it needs the recipe applier and the
// reload, nothing else about the viewer.

import { escapeHtml, withLoading } from "../ui/feedback";
import { parseCadCommand } from "./cadCommands";
import { begin, step, toLine, type PromptEvent, type PromptState } from "./promptLoop";

export interface CadBarDeps {
  /** Where the bar mounts. */
  readonly host: HTMLElement;
  /** Element the loading overlay covers while a recipe is applied. */
  readonly container: HTMLElement;
  readonly applyRecipe: (recipe: string, params: Record<string, unknown>, last: boolean) => Promise<unknown>;
  readonly waitForPublish: () => Promise<string>;
  readonly reload: () => Promise<boolean>;
  readonly reloadPins: () => Promise<void>;
  readonly clearDrafts: () => void;
  readonly notify: (message: string, kind?: "info" | "success" | "error") => void;
}

/**
 * Mount the bar. Returns a `pick` feed so the viewport can answer a point prompt with a click.
 *
 * `pick` reports whether it CONSUMED the click. The caller is a click handler that also selects and
 * measures, and a feed that returned void would force it to guess: treating every click as consumed
 * breaks selection whenever the bar is mounted, and treating none as consumed makes the prompt
 * unclickable. Only the bar knows whether a command is currently asking for a point.
 */
export function mountCadBar(d: CadBarDeps): { pick: (at: readonly [number, number]) => boolean } {
  const wrap = document.createElement("div");
  wrap.style.cssText = "display:flex;gap:4px;margin-bottom:4px";
  const input = document.createElement("input");
  input.type = "text"; input.className = "portal-filter";
  input.style.cssText = "flex:1;font-family:var(--mono)";
  input.placeholder = "⌨ CAD command — e.g. WALL 0,0 5,0 3, or just WALL  ·  type HELP";
  input.setAttribute("aria-label", "CAD command line");
  const status = document.createElement("div");
  status.className = "meta"; status.style.cssText = "min-height:14px;margin:-2px 0 6px 2px";

  const history: string[] = [];
  let histIdx = -1;
  let last = "";
  /** Non-null while a command is collecting its arguments. */
  let prompt: PromptState | null = null;

  const warn = (t: string) => { status.innerHTML = `<span style="color:var(--status-warn)">${escapeHtml(t)}</span>`; };
  const crit = (t: string) => { status.innerHTML = `<span style="color:var(--status-crit)">${escapeHtml(t)}</span>`; };

  /** Show the current prompt and any non-fatal error beside it. */
  function showPrompt() {
    if (!prompt) return;
    const head = prompt.status === "ready" && !prompt.prompt
      ? `${prompt.command} ready — press Enter to apply`
      : `${prompt.command}: ${prompt.prompt}`;
    status.innerHTML = prompt.error
      ? `${escapeHtml(head)} <span style="color:var(--status-warn)">— ${escapeHtml(prompt.error)}</span>`
      : escapeHtml(head);
    input.placeholder = prompt.prompt || "Enter to apply · Esc to cancel";
  }

  function endPrompt() {
    prompt = null;
    input.placeholder = "⌨ CAD command — e.g. WALL 0,0 5,0 3, or just WALL  ·  type HELP";
  }

  async function applyLine(line: string) {
    const parsed = parseCadCommand(line);
    if (parsed.kind === "info") { status.textContent = parsed.text; return; }
    if (parsed.kind === "error") { warn(parsed.text); return; }
    history.push(line); histIdx = history.length; last = line;
    input.value = ""; status.textContent = `applying ${parsed.echo}…`;
    await withLoading(d.container, `authoring ${parsed.echo} + republishing`, async () => {
      try {
        for (let i = 0; i < parsed.steps.length; i++) {
          const s = parsed.steps[i]!;
          await d.applyRecipe(s.recipe, s.params, i === parsed.steps.length - 1);
        }
        const state = await d.waitForPublish();
        if (state === "done") {
          const shown = await d.reload();
          d.clearDrafts();
          await d.reloadPins();
          status.textContent = `✓ ${parsed.echo}${shown ? " — shown" : ""}`;
          d.notify(`${parsed.echo} applied`, "success");
        } else {
          status.textContent = `authored — publish ${state}`;
          d.notify(`authored — publish ${state}`, state === "error" ? "error" : "info");
        }
      } catch (err) {
        crit((err as Error).message);
        d.notify(`${parsed.echo} failed: ${escapeHtml((err as Error).message)}`, "error");
      }
    });
  }

  /**
   * Feed one event into an armed command, applying it once there is nothing left to ask.
   *
   * "Ready" alone is NOT the trigger. A wall is ready the moment its two points are in, but its height
   * is still to come — committing there would apply the default and swallow the value the user was
   * about to type. So the command applies only when every argument has been supplied or skipped, which
   * is exactly when the prompt goes empty. Enter advances; Enter with nothing left to ask applies.
   */
  function advance(e: PromptEvent) {
    if (!prompt) return;
    prompt = step(prompt, e);
    if (prompt.status === "cancelled") { endPrompt(); status.textContent = "cancelled"; return; }
    if (prompt.status === "ready" && !prompt.prompt && !prompt.error) {
      const line = toLine(prompt);
      endPrompt();
      void applyLine(line);
      return;
    }
    showPrompt();
  }

  async function run() {
    const text = input.value.trim();

    // --- inside an armed command --------------------------------------------------------------
    if (prompt) {
      input.value = "";
      // Enter on an empty line means "that is all": close a variadic argument, skip an optional one,
      // and — once nothing is left to ask — apply.
      advance(text ? { t: "token", text } : { t: "accept" });
      return;
    }

    if (!text) { if (last) input.value = last; return; }   // empty Enter recalls the last command

    // --- a bare verb arms the interactive loop -------------------------------------------------
    // Only when the line is a single word: `WALL 0,0` is a typed line that happens to be incomplete,
    // and `parseCadCommand` already explains what is missing better than a prompt would.
    if (!text.includes(" ")) {
      const armed = begin(text);
      if (armed) {
        prompt = armed;
        input.value = "";
        showPrompt();
        return;
      }
    }
    await applyLine(text);
  }

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); void run(); return; }
    if (e.key === "Escape") {
      e.preventDefault();
      if (prompt) { advance({ t: "cancel" }); return; }
      input.value = ""; status.textContent = "";
      return;
    }
    // Backspace on an empty line gives back the last collected value rather than doing nothing.
    if (e.key === "Backspace" && prompt && input.value === "") { e.preventDefault(); advance({ t: "back" }); return; }
    if (prompt) return;                       // history and repeat belong to the typed path only
    if (e.key === " " && input.value === "" && last) { e.preventDefault(); input.value = last; return; }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (history.length) { histIdx = Math.max(0, histIdx - 1); input.value = history[histIdx] || ""; }
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (histIdx < history.length - 1) { histIdx++; input.value = history[histIdx] || ""; }
      else { histIdx = history.length; input.value = ""; }
    }
  });

  const go = document.createElement("button");
  go.className = "mini-btn"; go.textContent = "↵"; go.title = "Run CAD command";
  go.onclick = () => void run();
  wrap.append(input, go);
  d.host.appendChild(wrap);
  d.host.appendChild(status);

  return {
    /**
     * A point picked in the viewport, already snapped. Ignored unless a command is asking for one —
     * a click while nothing is armed is a selection, not an argument.
     */
    pick: (at) => {
      if (!prompt) return false;              // nothing armed — the click is a selection
      advance({ t: "pick", at });
      return true;
    },
  };
}
