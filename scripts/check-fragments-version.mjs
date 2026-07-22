// B1 — single-source guard for the @thatopen/fragments + web-ifc pair.
//
// The client parser version in apps/web/package.json IS the source of truth: the server-side .frag
// producers (services/api/Dockerfile, services/converter/Dockerfile) must emit fragments the client can
// parse, so their pinned versions have to match. Nothing enforced that before — this check fails CI on
// drift (the exact coupling landmine CLAUDE.md calls out).
//
// Matches both literal (`@thatopen/fragments@3.4.5`) and ARG (`FRAGMENTS_VERSION=3.4.5`) forms.
import { readFileSync } from "node:fs";

const ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"); // win-safe
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

const pkg = JSON.parse(read("apps/web/package.json"));
const truth = {
  "@thatopen/fragments": pkg.dependencies["@thatopen/fragments"],
  "web-ifc": pkg.dependencies["web-ifc"],
};

const DOCKERFILES = ["services/api/Dockerfile", "services/converter/Dockerfile"];
const extract = (text, dep, argName) => {
  const lit = text.match(new RegExp(`${dep.replace(/[/]/g, "\\/")}@([0-9][^\\s"']*)`));
  const arg = text.match(new RegExp(`${argName}=([0-9][^\\s"']*)`));
  return (lit && lit[1]) || (arg && arg[1]) || null;
};

const problems = [];
for (const df of DOCKERFILES) {
  const text = read(df);
  for (const [dep, argName] of [["@thatopen/fragments", "FRAGMENTS_VERSION"], ["web-ifc", "WEBIFC_VERSION"]]) {
    const got = extract(text, dep, argName);
    if (got == null) {
      problems.push(`${df}: could not find a ${dep} version (literal or ${argName})`);
    } else if (got !== truth[dep]) {
      problems.push(`${df}: ${dep}@${got} != apps/web/package.json ${dep}@${truth[dep]}`);
    }
  }
}

// B1b — the wider @thatopen suite + three must move TOGETHER, deliberately. The pins below are the
// verified-working tuple (exact versions, no ^): bumping any one package without re-verifying the set
// is exactly the coupling landmine CLAUDE.md warns about, so CI fails until this record is updated in
// the same commit as the bump — a conscious act, not an accident. (The suite is intentionally at mixed
// patch levels; equality between packages is NOT the invariant, the recorded tuple is.)
const KNOWN_GOOD = {
  "@thatopen/components": "3.4.6",
  "@thatopen/components-front": "3.4.3",
  "@thatopen/ui": "3.4.10",
  "@thatopen/fragments": "3.4.6",
  "three": "0.185.1",
  "web-ifc": "0.0.77",
};
for (const [dep, want] of Object.entries(KNOWN_GOOD)) {
  const got = pkg.dependencies[dep];
  if (got !== want) {
    problems.push(`apps/web/package.json: ${dep}@${got} != recorded known-good ${want} — if this bump is `
      + "deliberate, re-verify the viewer (load a model, author, section) and update KNOWN_GOOD in "
      + "scripts/check-fragments-version.mjs in the same commit");
  }
}

void ROOT;
if (problems.length) {
  console.error("✗ @thatopen/fragments · web-ifc version drift:\n  " + problems.join("\n  "));
  console.error(`\n  source of truth (apps/web/package.json): fragments@${truth["@thatopen/fragments"]} · web-ifc@${truth["web-ifc"]}`);
  process.exit(1);
}
console.log(`✓ fragments@${truth["@thatopen/fragments"]} · web-ifc@${truth["web-ifc"]} — client + both Dockerfiles agree`);
