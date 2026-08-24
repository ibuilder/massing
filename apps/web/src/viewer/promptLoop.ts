// The interactive half of the CAD command line — CADCMD shipped in v0.3.430, this is the half it
// never had. (The R29 research ring's finding was that the gap in this product is authoring FEEL
// rather than authoring features; this is one of those. It is not a roadmap item — there is no
// open entry for it — so nothing here closes anything.)
//
// `cadCommands.ts` parses a COMPLETE line: `WALL 0,0 5,0 3`. That is the whole grammar a drafter who
// already knows what they want needs, and it is exhaustively unit-tested. What it cannot do is the
// thing every CAD program does — arm a verb and then ASK: "Specify start point:", "Specify end point:",
// taking a click or a typed coordinate for each. Today, typing `WALL` on its own is an error message.
//
// ## Why a pure reducer
//
// The obvious implementation is a tangle of viewport handlers over mutable state — a `pendingPoints`
// array here, an `armed` flag there, a `waitingFor` string somewhere else. It works, and it cannot be
// tested without a renderer, so in practice it never is, and every later fix risks a regression nobody
// can see. `step(state, event) -> state` is pure, so the whole interactive flow is testable with
// nothing mocked: no DOM, no viewport, no kernel, no clock.
//
// The design is adapted from the prompt loop in the MIT-licensed "@massing/commands" package, evaluated
// 2026-08-23 (see CLAUDE.md). The facade itself was declined — its load path assumes browser-side IFC
// tessellation, against this repo's non-negotiables — but this shape was the one genuinely new idea in
// it. It is reimplemented against our own command table rather than copied: their reducer accumulates a
// typed argument bag, and ours accumulates TOKENS, for the reason below.
//
// ## Tokens, not values — and that is the point
//
// The loop collects the same `string[]` that `parseCadCommand` already accepts, and `toLine()` hands it
// back as an ordinary command line. So the interactive path and the typed path converge on ONE parser:
// every coordinate form (`x,y`, `d<a`, `@dx,dy`, `@d<a`), every default and every validation message is
// shared by construction. A second parser "for the interactive case" is how two paths drift until a
// recorded macro replays differently from the clicks that recorded it.
//
// ## Snapping happens BEFORE the reducer
//
// A `pick` event carries an already-snapped point. Snapping has to be frame-immediate — a reducer
// round-trip per mouse-move would be visible — and keeping it outside means the same event sequence
// always yields the same state, which is what makes a recorded sequence a reliable regression test.
//
// ## A bad token does NOT cancel the command
//
// It sets `error` and leaves the cursor where it was. Losing three placed points to one typo is the
// most annoying failure a CAD tool has, and a tool that disarms on bad input teaches people not to type.

import { cadCommandArgs, type CadArg } from "./cadCommands";

export type PromptEvent =
  /** Typed on the command line. */
  | { readonly t: "token"; readonly text: string }
  /** A point picked in the viewport — ALREADY snapped and constrained. */
  | { readonly t: "pick"; readonly at: readonly [number, number] }
  /** Enter / double-click: finish a variadic argument, or skip a remaining optional one. */
  | { readonly t: "accept" }
  /** Backspace: give back the last collected value. */
  | { readonly t: "back" }
  | { readonly t: "cancel" };

export type PromptStatus = "collecting" | "ready" | "cancelled";

export interface PromptState {
  /** Canonical command name, alias already resolved. */
  readonly command: string;
  /** Collected argument tokens, in the order `build()` expects them. */
  readonly tokens: readonly string[];
  /** Index into the command's argument specs. */
  readonly cursor: number;
  /** What the command line shows, e.g. `Specify next point or press Enter to close [3 placed]`. */
  readonly prompt: string;
  readonly status: PromptStatus;
  /** Last parse failure. Shown inline, and non-fatal — see the header. */
  readonly error?: string;
}

/** How many values the variadic argument at `cursor` has taken so far. */
function variadicCount(s: PromptState, args: readonly CadArg[]): number {
  // Every argument before a variadic one contributes exactly one token, so the remainder is its own.
  let fixed = 0;
  for (let i = 0; i < s.cursor && i < args.length; i++) if (!args[i]?.variadic) fixed += 1;
  return Math.max(0, s.tokens.length - fixed);
}

function render(s: PromptState, args: readonly CadArg[]): string {
  const a = args[s.cursor];
  if (!a) return "";
  if (a.variadic) {
    const n = variadicCount(s, args);
    const need = a.min ?? 1;
    return n < need ? `${a.prompt} [${n} of ${need}]`
                    : `${a.prompt} or press Enter to close [${n} placed]`;
  }
  return a.optional ? `${a.prompt} <${a.def ?? ""}>` : a.prompt;
}

/**
 * `ready` means COMMITTABLE, not closed.
 *
 * Every required argument is present, so the command can be committed at any moment — trailing optional
 * arguments do not hold it open, because `build()` supplies their defaults and making someone press
 * Enter past "Width <0.2>" to draw a wall is the difference between a tool that feels quick and one that
 * feels like a form.
 *
 * But it must still ACCEPT input: `SLAB … accept` is ready the instant the outline closes, and the very
 * next thing a user may type is the thickness. The first version of this froze the state at `ready` and
 * silently dropped that token — the command committed at the default and the typed value vanished with
 * no error, which is the worst of the three possible failures. Only `cancelled`, or a command whose
 * arguments are all consumed, stops taking events.
 */
function settle(s: PromptState, args: readonly CadArg[]): PromptState {
  if (s.status === "cancelled") return s;
  let look = s.cursor;
  while (look < args.length && args[look]?.optional) look++;
  const status = look >= args.length ? ("ready" as const) : ("collecting" as const);
  return { ...s, status, prompt: s.cursor >= args.length ? "" : render(s, args) };
}

/** Arm a command. Null when the verb is unknown or carries no interactive spec. */
export function begin(verb: string): PromptState | null {
  const found = cadCommandArgs(verb);
  if (!found) return null;
  const s: PromptState = { command: found.name, tokens: [], cursor: 0, prompt: "", status: "collecting" };
  return settle(s, found.args);
}

/**
 * Advance by one event. Pure.
 *
 * A `ready` state STILL TAKES EVENTS — it means committable, not closed, so a trailing optional value
 * can still be typed. Only `cancelled`, or a command whose arguments are all consumed, ignores them, and
 * it ignores rather than throws: a stray event after completion is ordinary — a pointer-up arriving
 * after the click that finished the command — and an exception there would be a crash caused by
 * ordinary use.
 */
export function step(s: PromptState, e: PromptEvent): PromptState {
  if (s.status === "cancelled") return s;
  const found = cadCommandArgs(s.command);
  if (!found) return s;
  const args = found.args;

  // Cancel is handled BEFORE the consumed-arguments guard. A command with every argument collected is
  // still uncommitted, and Escape on it means abandon — the first version fell through the guard below
  // and ignored the keypress, so the only way out of a finished-but-uncommitted command was to commit
  // it. Caught by the test that asserts cancel-then-token stays cancelled.
  if (e.t === "cancel") return { ...s, status: "cancelled", prompt: "", error: undefined };

  const a = args[s.cursor];
  if (!a) return s;                       // every argument consumed — nothing left to collect

  if (e.t === "back") {
    if (!s.tokens.length) return { ...s, error: undefined };
    const tokens = s.tokens.slice(0, -1);
    // Stepping back inside a variadic argument stays on it; otherwise return to the previous argument.
    const cursor = a.variadic && variadicCount(s, args) > 0 ? s.cursor : Math.max(0, s.cursor - 1);
    return settle({ ...s, tokens, cursor, error: undefined }, args);
  }

  if (e.t === "accept") {
    if (a.variadic) {
      const n = variadicCount(s, args);
      const need = a.min ?? 1;
      if (n < need) return { ...s, error: `${a.prompt.toLowerCase()}: need at least ${need}, have ${n}` };
      return settle({ ...s, cursor: s.cursor + 1, error: undefined }, args);
    }
    // Accept on a REQUIRED argument is not a skip. Skipping would hand `build()` a missing value and
    // produce a parse error attributed to the wrong argument.
    if (!a.optional) return { ...s, error: `${a.prompt.toLowerCase()} is required` };
    return settle({ ...s, cursor: s.cursor + 1, error: undefined }, args);
  }

  // --- a value arrives ---------------------------------------------------------------------------
  const text = e.t === "pick" ? `${round(e.at[0])},${round(e.at[1])}` : e.text.trim();
  if (!text) return { ...s, error: undefined };

  if (e.t === "pick" && a.kind !== "point") {
    return { ...s, error: `${a.prompt.toLowerCase()} is not a point — type a value` };
  }
  // Numbers are checked here because the message can name the ARGUMENT. `build()` would reject it too,
  // but only after the whole line is assembled, by which point the user has lost the other values.
  if (e.t === "token" && a.kind === "number" && !Number.isFinite(Number(text))) {
    return { ...s, error: `${a.prompt.toLowerCase()}: "${text}" is not a number` };
  }

  const tokens = [...s.tokens, text];
  const advanced: PromptState = a.variadic
    ? { ...s, tokens, error: undefined }                    // stay on the variadic argument
    : { ...s, tokens, cursor: s.cursor + 1, error: undefined };
  return settle(advanced, args);
}

/** Metres, to the millimetre — a picked point carries float noise that renders as `2.0000000000000004`. */
function round(n: number): string {
  return String(Math.round(n * 1000) / 1000);
}

/**
 * The single crossing from interactivity into the existing parser.
 *
 * Throws on a state that is not `ready`, because building a line from a half-collected command would put
 * a partial edit into the undo history and the audit log, and the failure would surface later and
 * somewhere else as a recipe that cannot be replayed.
 */
export function toLine(s: PromptState): string {
  if (s.status !== "ready") throw new Error(`prompt loop is ${s.status}, not ready`);
  return [s.command, ...s.tokens].join(" ");
}
