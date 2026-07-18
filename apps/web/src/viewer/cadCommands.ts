// CADCMD — a deterministic CAD command grammar over the GUID-stable edit recipes.
//
// Every drafter already knows the AutoCAD command grammar: a short verb, optional single-letter alias,
// space-separated arguments, spacebar to repeat the last command. This parses that grammar into a recipe
// call the viewer applies — instant and offline (no LLM roundtrip), the complement to the AI command bar.
// The parser is pure (no DOM, no network) so it's exhaustively unit-tested; the viewer supplies only the
// input, history, and the apply/reload wiring.

export interface CadRecipeStep { recipe: string; params: Record<string, unknown> }
export type CadParse =
  | { kind: "recipe"; steps: CadRecipeStep[]; echo: string }
  | { kind: "info"; text: string }
  | { kind: "error"; text: string };

interface CadCommand {
  name: string;
  aliases: string[];
  usage: string;
  summary: string;
  build(args: string[]): CadParse;
}

/**
 * Parse a point token into an absolute [x,y] tuple (meters). Supports the AutoCAD coordinate grammar:
 *  · `x,y` (or `x,y,z`, z ignored) — absolute cartesian;
 *  · `d<a`  — absolute **polar**: distance d at angle a° (CCW from +X/east), measured from the origin;
 *  · `@dx,dy` — **relative** cartesian: offset from `prev` (the previous point in the command);
 *  · `@d<a`  — relative polar: distance d at angle a° from `prev`.
 * `prev` is the previously-resolved point in the same command (walls/beams/slabs chain), defaulting to the
 * origin — so `WALL 0,0 @5<0` draws 5 m east and `SLAB 0,0 @4<0 @4<90 @4<180` walks a square.
 */
function point(tok: string | undefined, prev?: [number, number]): [number, number] | null {
  if (!tok) return null;
  const rel = tok.startsWith("@");
  const body = rel ? tok.slice(1) : tok;
  const base: [number, number] = rel ? (prev ?? [0, 0]) : [0, 0];
  if (body.includes("<")) {                                   // polar: distance<angle°
    const [ds, as] = body.split("<");
    const d = Number(ds), ang = Number(as);
    if (!Number.isFinite(d) || !Number.isFinite(ang)) return null;
    const r = (ang * Math.PI) / 180;
    return [base[0] + d * Math.cos(r), base[1] + d * Math.sin(r)];
  }
  const parts = body.split(",").map((s) => Number(s.trim()));
  if (parts.length < 2 || parts.some((n) => !Number.isFinite(n))) return null;
  return [base[0] + parts[0]!, base[1] + parts[1]!];
}

function num(tok: string | undefined, fallback: number): number {
  if (tok === undefined || tok === "") return fallback;
  const n = Number(tok);
  return Number.isFinite(n) ? n : NaN;
}

const err = (usage: string, why: string): CadParse => ({ kind: "error", text: `${why}. Usage: ${usage}` });

const COMMANDS: CadCommand[] = [
  {
    name: "WALL", aliases: ["W"], usage: "WALL x1,y1 x2,y2 [height]",
    summary: "draw a wall between two XY points (m); optional height (default 3)",
    build(a) {
      const s = point(a[0]); const e = point(a[1], s ?? undefined);
      if (!s || !e) return err(this.usage, "need two points, e.g. WALL 0,0 5,0 (or WALL 0,0 @5<0)");
      const h = num(a[2], 3);
      if (!Number.isFinite(h) || h <= 0) return err(this.usage, "height must be a positive number");
      return { kind: "recipe", steps: [{ recipe: "add_wall", params: { start: s, end: e, height: h } }],
        echo: `wall ${a[0]}→${a[1]} h=${h}` };
    },
  },
  {
    name: "COLUMN", aliases: ["C", "COL"], usage: "COLUMN x,y [height] [width]",
    summary: "place a column at an XY point (m); optional height (3) and square width (0.4)",
    build(a) {
      const p = point(a[0]);
      if (!p) return err(this.usage, "need a point, e.g. COLUMN 2,2");
      const h = num(a[1], 3); const w = num(a[2], 0.4);
      if (!Number.isFinite(h) || !Number.isFinite(w)) return err(this.usage, "height/width must be numbers");
      return { kind: "recipe", steps: [{ recipe: "add_column", params: { point: p, height: h, width: w, depth: w } }],
        echo: `column ${a[0]} h=${h} ${w}×${w}` };
    },
  },
  {
    name: "BEAM", aliases: ["B"], usage: "BEAM x1,y1 x2,y2 [width] [depth]",
    summary: "draw a beam between two XY points (m); optional width (0.3) and depth (0.5)",
    build(a) {
      const s = point(a[0]); const e = point(a[1], s ?? undefined);
      if (!s || !e) return err(this.usage, "need two points, e.g. BEAM 0,0 6,0");
      const w = num(a[2], 0.3); const d = num(a[3], 0.5);
      if (!Number.isFinite(w) || !Number.isFinite(d)) return err(this.usage, "width/depth must be numbers");
      return { kind: "recipe", steps: [{ recipe: "add_beam", params: { start: s, end: e, width: w, depth: d } }],
        echo: `beam ${a[0]}→${a[1]} ${w}×${d}` };
    },
  },
  {
    name: "SLAB", aliases: ["S"], usage: "SLAB x1,y1 x2,y2 x3,y3 [… xn,yn] [thickness]",
    summary: "draw a slab from ≥3 boundary points (m); a trailing bare number is the thickness (0.2)",
    build(a) {
      // a trailing bare number (no comma, not a polar d<a) is the thickness; the rest are points
      let thickness = 0.2;
      let toks = a;
      const last = a[a.length - 1];
      if (last !== undefined && !last.includes(",") && !last.includes("<")) {
        const t = Number(last);
        if (!Number.isFinite(t) || t <= 0) return err(this.usage, "thickness must be a positive number");
        thickness = t; toks = a.slice(0, -1);
      }
      const pts: [number, number][] = [];
      for (const tok of toks) {                         // walk points, chaining relative/polar to the previous
        const p = point(tok, pts[pts.length - 1]);
        if (p === null) return err(this.usage, "need ≥3 XY points");
        pts.push(p);
      }
      if (pts.length < 3) return err(this.usage, "need ≥3 XY points");
      return { kind: "recipe", steps: [{ recipe: "add_slab", params: { points: pts, thickness } }],
        echo: `slab ${pts.length} pts t=${thickness}` };
    },
  },
  {
    name: "LEVEL", aliases: ["LVL"], usage: "LEVEL <name> <elevation-m>",
    summary: "add a building storey/level at an elevation (m)",
    build(a) {
      const name = a[0];
      const elev = num(a[1], NaN);
      if (!name || !Number.isFinite(elev)) return err(this.usage, "need a name and an elevation, e.g. LEVEL L2 3.5");
      return { kind: "recipe", steps: [{ recipe: "add_storey", params: { name, elevation: elev } }],
        echo: `level ${name} @ ${elev}m` };
    },
  },
  {
    name: "SPACE", aliases: ["SP"], usage: "SPACE [rooms-per-storey]",
    summary: "auto-generate IfcSpace rooms per storey (default 4)",
    build(a) {
      const n = num(a[0], 4);
      if (!Number.isFinite(n) || n < 1) return err(this.usage, "rooms-per-storey must be ≥1");
      return { kind: "recipe", steps: [{ recipe: "add_spaces", params: { rooms_per_storey: Math.round(n) } }],
        echo: `spaces ×${Math.round(n)}/storey` };
    },
  },
];

const BY_TOKEN = new Map<string, CadCommand>();
for (const c of COMMANDS) {
  BY_TOKEN.set(c.name, c);
  for (const al of c.aliases) BY_TOKEN.set(al, c);
}

/** The public command list (for the help panel + autocomplete). */
export function cadCommandList(): { name: string; aliases: string[]; usage: string; summary: string }[] {
  return COMMANDS.map((c) => ({ name: c.name, aliases: c.aliases, usage: c.usage, summary: c.summary }));
}

function helpText(): string {
  return "Commands (aliases): " + COMMANDS.map((c) => `${c.name}${c.aliases.length ? " (" + c.aliases.join("/") + ")" : ""}`).join(", ")
    + ". Points: x,y absolute · @dx,dy relative · d<a or @d<a polar (angle° CCW from east). "
    + "Type HELP <cmd> for usage. Space repeats the last command.";
}

/**
 * Parse one CAD command line. Case-insensitive verb; args are space-separated. Returns a recipe plan,
 * an info message (help), or an error with usage. `HELP`/`?` lists commands; `HELP WALL` shows one usage.
 */
export function parseCadCommand(line: string): CadParse {
  const trimmed = (line || "").trim();
  if (!trimmed) return { kind: "error", text: "empty command — type HELP for the list" };
  const tokens = trimmed.split(/\s+/);
  const verb = tokens[0]!.toUpperCase();
  if (verb === "HELP" || verb === "?") {
    const which = tokens[1]?.toUpperCase();
    if (which) {
      const c = BY_TOKEN.get(which);
      return c ? { kind: "info", text: `${c.name} — ${c.summary}. Usage: ${c.usage}` }
        : { kind: "error", text: `unknown command '${which}'. ${helpText()}` };
    }
    return { kind: "info", text: helpText() };
  }
  const cmd = BY_TOKEN.get(verb);
  if (!cmd) return { kind: "error", text: `unknown command '${verb}'. Type HELP for the list.` };
  return cmd.build(tokens.slice(1));
}
