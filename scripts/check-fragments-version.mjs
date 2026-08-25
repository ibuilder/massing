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
//
// TUPLE UPDATED 2026-08-08 (PR #231). Re-verified live before touching this record, because the
// whole value of the pin is that nobody moves it without looking:
//   * a 5-element project renders 5 meshes; a 154-element project renders 82 meshes / 473,088
//     triangles — the counts TRACK the model rather than merely being non-zero
//   * the section box takes the renderer from 0 to 6 clipping planes with localClipping enabled
//   * `selectByGuid` resolves without throwing; zero console errors across both loads
//   * `npm run typecheck` and the real Vite 8 / rolldown `npm run build` both clean in the primary
//     clone (a worktree resolves a DIFFERENT Vite and would not have proven this)
// NOT re-verified: authoring a new element end-to-end. Recorded here rather than implied, since
// this comment is the only evidence a later reader will have of what "verified" covered.
const KNOWN_GOOD = {
  "@thatopen/components": "3.4.8",
  "@thatopen/components-front": "3.4.4",
  "@thatopen/ui": "3.4.10",
  "@thatopen/fragments": "3.4.7",
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

// B1c — the Node BASE IMAGE, which the two checks above stop one line short of.
//
// Every `FROM node:` in the product must name the same tag AND the same digest. The two checks above
// gate the fragments/web-ifc ARGs across services/api/Dockerfile and services/converter/Dockerfile —
// and the base image sits directly above those ARGs, ungated.
//
// It drifted, and the trail is instructive. Dependabot raised both converter images to node:25-slim
// together (#117 services/api, #116 services/converter); both merged 2026-07-31. Four days later the
// api one was put back to 24-slim in an unrelated release, with a comment stating the reason — 25 is
// an EOL major with no security patches, and both manifests declare `engines.node >= 24` while CI
// runs 24. That comment then said "one Node runtime across the product", which was false as it was
// written: services/converter/Dockerfile was still on 25-slim, and stayed there for 25 days while
// Dependabot re-proposed the same bump (#227, closed).
//
// **A reason applied to some of the files it argues about is the shape this repository keeps
// finding** — the same "one rule, some of the doors" as the SSO domain allowlist (PR #339) and the
// three unguarded sign-in doors (v0.3.1093). A decision recorded in a comment protects the file the
// comment is in.
//
// Digest equality is part of the claim, not pedantry: `node:24-slim` is a moving tag, so two files
// naming it without the same digest can still build two different images.
const NODE_DOCKERFILES = ["services/api/Dockerfile", "services/converter/Dockerfile", "apps/web/Dockerfile"];
const bases = NODE_DOCKERFILES.map((df) => {
  const m = read(df).match(/^FROM (node:\S+)/m);
  return { df, base: m && m[1] };
});
const missing = bases.filter((b) => !b.base);
if (missing.length) {
  // Loud rather than skipped: a Dockerfile that stops naming a node base must not silently shrink
  // this check's population to the files that still agree.
  problems.push(...missing.map((b) => `${b.df}: no \`FROM node:...\` line found — if this image no `
    + "longer builds on Node, drop it from NODE_DOCKERFILES in the same commit"));
} else {
  const distinct = [...new Set(bases.map((b) => b.base))];
  if (distinct.length > 1) {
    problems.push("the Node base image differs across Dockerfiles — one runtime across the product:\n    "
      + bases.map((b) => `${b.df}: ${b.base}`).join("\n    "));
  }
}

void ROOT;
if (problems.length) {
  console.error("✗ @thatopen/fragments · web-ifc version drift:\n  " + problems.join("\n  "));
  console.error(`\n  source of truth (apps/web/package.json): fragments@${truth["@thatopen/fragments"]} · web-ifc@${truth["web-ifc"]}`);
  process.exit(1);
}
console.log(`✓ fragments@${truth["@thatopen/fragments"]} · web-ifc@${truth["web-ifc"]} — client + both Dockerfiles agree`);
console.log(`✓ ${bases[0].base} — all ${bases.length} Dockerfiles share one Node base image`);
