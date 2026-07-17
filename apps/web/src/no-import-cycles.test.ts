// DEV-2 (REL-8) web half: import-cycle guard — no *runtime* circular imports among the app's own
// modules. Mirrors the backend `test_import_cycles.py`. `import type` / `export type` are excluded because
// TypeScript erases them at compile time (they emit no runtime import and cannot form a runtime cycle) —
// the one "cycle" in the portal is exactly that: the PanelContext ⇄ PortalHost type seam. A genuine
// runtime cycle (module A eval depends on B whose eval depends on A) is what breaks at load time; this
// fails the build with the exact cycle path so it can't regress. Pure Node fs — no new dependency.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SRC = dirname(fileURLToPath(import.meta.url));

function listModules(root: string): string[] {
  const out: string[] = [];
  const walk = (d: string) => {
    for (const e of readdirSync(d)) {
      const p = join(d, e);
      if (statSync(p).isDirectory()) walk(p);
      else if (/\.(ts|tsx)$/.test(e) && !/\.d\.ts$/.test(e) && !/\.(test|spec)\.tsx?$/.test(e)) out.push(p);
    }
  };
  walk(root);
  return out;
}

const norm = (p: string) => relative(SRC, p).split("\\").join("/").replace(/\.(ts|tsx)$/, "");

function buildGraph(): { edges: Map<string, Set<string>>; count: number } {
  const files = listModules(SRC);
  const known = new Set(files.map(norm));
  const resolveSpec = (from: string, spec: string): string | null => {
    if (!spec.startsWith(".")) return null;                 // bare/package import — not first-party
    const base = resolve(dirname(from), spec);
    const r = relative(SRC, base).split("\\").join("/").replace(/\.(ts|tsx)$/, "");
    if (known.has(r)) return r;
    if (known.has(`${r}/index`)) return `${r}/index`;
    return null;
  };
  // RUNTIME imports only — skip `import type …` / `export type …` (erased by tsc). A mixed
  // `import { type A, b }` still emits a runtime binding for `b`, so it is (correctly) counted.
  const impRe = /^\s*import\s+(?!type\s)(?:[^'"]*\s+from\s+)?['"]([^'"]+)['"]/gm;
  const expRe = /^\s*export\s+(?!type\s)(?:\*|\{[^}]*\})\s+from\s+['"]([^'"]+)['"]/gm;
  const edges = new Map<string, Set<string>>();
  let count = 0;
  for (const f of files) {
    const src = readFileSync(f, "utf8");
    const key = norm(f);
    const out = new Set<string>();
    for (const re of [impRe, expRe]) {
      re.lastIndex = 0;
      let m: RegExpExecArray | null;
      while ((m = re.exec(src))) {
        const spec = m[1];
        if (!spec) continue;
        const t = resolveSpec(f, spec);
        if (t && t !== key) out.add(t);
      }
    }
    edges.set(key, out);
    count += out.size;
  }
  return { edges, count };
}

/** Tarjan strongly-connected components; any component with >1 node (or a self-loop) is a cycle. */
function findCycles(edges: Map<string, Set<string>>): string[][] {
  let idx = 0;
  const index = new Map<string, number>();
  const low = new Map<string, number>();
  const onStack = new Map<string, boolean>();
  const stack: string[] = [];
  const cycles: string[][] = [];
  const strongconnect = (v: string) => {
    index.set(v, idx);
    low.set(v, idx);
    idx++;
    stack.push(v);
    onStack.set(v, true);
    for (const w of edges.get(v) ?? []) {
      if (!index.has(w)) {
        strongconnect(w);
        low.set(v, Math.min(low.get(v)!, low.get(w)!));
      } else if (onStack.get(w)) {
        low.set(v, Math.min(low.get(v)!, index.get(w)!));
      }
    }
    if (low.get(v) === index.get(v)) {
      const comp: string[] = [];
      for (;;) {
        const w = stack.pop()!;
        onStack.set(w, false);
        comp.push(w);
        if (w === v) break;
      }
      if (comp.length > 1 || (edges.get(v)?.has(v) ?? false)) cycles.push(comp.sort());
    }
  };
  for (const v of edges.keys()) if (!index.has(v)) strongconnect(v);
  return cycles;
}

describe("web import-cycle guard", () => {
  it("has no runtime circular imports among first-party modules", () => {
    const { edges, count } = buildGraph();
    expect(edges.size).toBeGreaterThan(50); // sanity: discovery actually found the app
    expect(count).toBeGreaterThan(50);
    const cycles = findCycles(edges);
    if (cycles.length) {
      const detail = cycles.map((c) => `  CYCLE: ${c.join(" -> ")}`).join("\n");
      throw new Error(`${cycles.length} runtime import cycle(s) found:\n${detail}`);
    }
    expect(cycles).toEqual([]);
  });

  it("detects a synthetic cycle (self-test of the SCC algorithm)", () => {
    const e = new Map<string, Set<string>>([
      ["a", new Set(["b"])],
      ["b", new Set(["c"])],
      ["c", new Set(["a"])],
      ["d", new Set(["d"])],
      ["e", new Set(["a"])],
    ]);
    const cycles = findCycles(e).map((c) => c.join(","));
    expect(cycles).toContain("a,b,c");
    expect(cycles).toContain("d");
    expect(cycles).not.toContain("e");
  });
});
