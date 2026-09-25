#!/usr/bin/env node
/**
 * Regenerate `src/api/schema.d.ts` from the FastAPI app — reading the SERVER, never a file.
 *
 * WHY THIS SCRIPT EXISTS — the generator's input was a file nobody tracked
 *     `package.json` used to run, literally:
 *
 *         openapi-typescript src/api/openapi.json -o src/api/schema.d.ts
 *
 *     and `apps/web/.gitignore` ignores `src/api/openapi.json`. So the one documented way to
 *     "regenerate the types" read an **untracked** intermediate: on a fresh clone the command fails
 *     outright (no input), and on a machine that has one it regenerates from whatever dump happens to
 *     be sitting there — which may predate the routes you just added. **It succeeds, prints a green
 *     tick, and produces the same stale file.** *"Regenerate the types" did not mean "read the
 *     server", and nothing said so.*
 *
 *     Measured 2026-09-25: the committed `schema.d.ts` declared **500** of the **947** paths the app
 *     serves, missing 448 across 165 of 203 path groups. That file and the `.gitignore` line hiding
 *     its input were last written in the SAME commit (`8432a88`, 2026-09-11), and the API has *fewer*
 *     route decorators today (1016) than it had then (1022) — so drift cannot explain the gap. **The
 *     types were already half the API on the day they were generated**, which is why the roadmap
 *     entry naming this "SCHEMA-STALE" was itself wrong: stale implies it was once right, and a
 *     stale-sounding name sends the next reader to re-run the generator, the one action that does not
 *     fix it.
 *
 * WHAT CHANGED
 *     The spec is dumped from `aec_api.main:app` into a file under the OS temp directory, generated
 *     from, and deleted. There is **no persistent input to be stale**, so the failure mode above is
 *     not merely discouraged, it is unreachable: if the app cannot be imported this exits non-zero
 *     with Python's own traceback, rather than quietly falling back to a dump on disk.
 *
 * THE AUTHORITY IS A TEST, NOT THIS SCRIPT
 *     `services/api/test_schema_types_agree.py` asserts every live `(path, method)` is declared in
 *     the committed `schema.d.ts`. A generator can only be run; a gate fails. This script exists so
 *     that running it means something — the gate is what makes not running it visible.
 */
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const WEB = resolve(import.meta.dirname, "..");
const REPO = resolve(WEB, "..", "..");
const API = join(REPO, "services", "api");

/** The venv interpreter for `services/api`, on either OS — never a bare `python`. */
function venvPython() {
  const candidates = [
    join(API, ".venv", "bin", "python"),
    join(API, ".venv", "Scripts", "python.exe"),
  ];
  for (const p of candidates) if (existsSync(p)) return p;
  console.error(
    `gen:api-types — no interpreter at any of:\n  ${candidates.join("\n  ")}\n` +
      `Create it first: the backend venv is what holds fastapi/ifcopenshell, and a bare \`python\`\n` +
      `off PATH is the resolution mistake \`check-vite-version.mjs\` documents for vite.`,
  );
  process.exit(1);
}

const DUMP = [
  "import json,sys",
  "from aec_api.main import app",
  "sys.stdout.write(json.dumps(app.openapi()))",
].join("\n");

const py = venvPython();
const spec = spawnSync(py, ["-c", DUMP], {
  cwd: API,
  encoding: "utf-8",
  maxBuffer: 64 * 1024 * 1024,
  env: { ...process.env, PYTHONPATH: ["src", join("..", "data", "src")].join(process.platform === "win32" ? ";" : ":") },
});
if (spec.status !== 0) {
  console.error(spec.stderr || "gen:api-types — the app could not be imported");
  process.exit(spec.status ?? 1);
}

// Sanity-check the dump BEFORE overwriting a committed file: a truncated or empty spec would
// otherwise generate a valid-looking `schema.d.ts` that declares nothing.
let parsed;
try {
  parsed = JSON.parse(spec.stdout);
} catch (e) {
  console.error(`gen:api-types — the spec dump is not JSON (${String(e)})`);
  process.exit(1);
}
const paths = Object.keys(parsed?.paths ?? {});
if (paths.length < 100) {
  console.error(
    `gen:api-types — the app reports only ${paths.length} paths, which is not a plausible spec for ` +
      `this API. Refusing to overwrite src/api/schema.d.ts from it.`,
  );
  process.exit(1);
}

/** `openapi-typescript`'s CLI, wherever npm hoisted it — root or nested under apps/web. */
function generatorCli() {
  const candidates = [
    join(REPO, "node_modules", "openapi-typescript", "bin", "cli.js"),
    join(WEB, "node_modules", "openapi-typescript", "bin", "cli.js"),
  ];
  for (const p of candidates) if (existsSync(p)) return p;
  console.error(
    `gen:api-types — openapi-typescript is not installed at either:\n  ${candidates.join("\n  ")}`,
  );
  process.exit(1);
}

// Sort `paths` before generating. FastAPI emits them in ROUTE REGISTRATION order, so including a
// router earlier shuffles thousands of lines and the diff of a one-route change is unreviewable —
// which is a large part of why "regenerating churned 38,231 lines" became a reason not to regenerate.
// Key order carries no meaning in an OpenAPI document, so sorting costs nothing and makes the next
// regeneration a diff somebody will actually read.
parsed.paths = Object.fromEntries([...Object.entries(parsed.paths)].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)));

const tmp = mkdtempSync(join(tmpdir(), "massing-openapi-"));
const specFile = join(tmp, "openapi.json");
const out = join(WEB, "src", "api", "schema.d.ts");
try {
  writeFileSync(specFile, JSON.stringify(parsed));
  const gen = spawnSync(process.execPath, [generatorCli(), specFile, "-o", out], {
    cwd: WEB,
    stdio: "inherit",
  });
  if (gen.status !== 0) process.exit(gen.status ?? 1);
} finally {
  rmSync(tmp, { recursive: true, force: true });
}
console.log(`gen:api-types — ${paths.length} paths from the live app → src/api/schema.d.ts`);
