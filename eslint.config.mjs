// ESLint (flat config) for the repository-root `scripts/` directory.
//
// `apps/web/eslint.config.js` already lints `scripts/**/*.mjs` — but relative to ITS base path, so it
// reaches `apps/web/scripts/` and structurally cannot reach this one. Pointing it here fails with
// "was not found by the project service": a flat config cannot lint above its own directory.
//
// So the repo root had a `scripts/` directory that no ESLint config covered, and it holds
// `check-fragments-version.mjs` — a program CI runs to gate the build (the fragments/web-ifc pin, and
// as of v0.3.1097 the shared Node base image). **The source that gates the build was, again, the
// source nobody linted.**
//
// That is verbatim the finding PR #219 recorded about `apps/web/scripts/` on 2026-08-06, one
// directory up and NINETEEN DAYS later. Its note is worth re-reading rather than paraphrasing: the
// directory was ignored "rather than a decision anyone made about linting build scripts" — an
// accident of configuration that reads, from the outside, exactly like a choice.
//
// Type-aware parsing is off for the same reason it is off in that block: these are standalone Node
// programs run by `node scripts/x.mjs`, not part of any TypeScript compilation unit.
import js from "@eslint/js";
import globals from "globals";

export default [
  // Everything not explicitly selected below is ignored. `js.configs.recommended` carries no `files`
  // of its own, so applied at top level it lints EVERY file ESLint can reach — which here meant
  // `services/api/.venv/lib/python3.12/site-packages/coverage/htmlfiles/coverage_html.js`, third-party
  // browser JS vendored inside a Python virtualenv, reported with hundreds of `no-undef` errors for
  // `localStorage` and `setTimeout`. A config whose population is "whatever is on disk" finds other
  // people's files; its rules are scoped to the globs below instead.
  {
    ignores: ["**/node_modules/**", "**/.venv/**", "**/site-packages/**", "**/dist/**",
              "apps/**", "docs/**", ".claude/**"],
  },
  {
    // `services/converter/src/**` is here for the same reason as `scripts/` and was found the same
    // way: enumerating every tracked `.mjs`/`.js` outside `apps/web` turned up four files, one in
    // `scripts/` and three that ARE the converter service — `cli.mjs`, `ifcToFrag.mjs`,
    // `rvtToIfc.mjs`. The IFC→Fragments conversion is a non-negotiable at the top of CLAUDE.md, and
    // nothing had ever linted it.
    //
    // Which makes the converter the least-covered corner of this repository, in two independent ways
    // discovered hours apart: **its image was built by no CI job (v0.3.1098) and its source was read
    // by no linter.** Neither fact caused the other; both are the same absence of coverage, and the
    // second was found only because fixing the first prompted the question "what else is uncovered?"
    // `eslint.config.mjs` lints ITSELF. It is tracked JavaScript like any other, and leaving it out
    // would make this file the one piece of JavaScript in the repository exempt from the rule it
    // exists to enforce. `lintCoverage.test.ts` caught the omission on its first CI run — see the
    // note there about why a local run did not.
    files: ["eslint.config.mjs",
            "scripts/**/*.mjs", "scripts/**/*.js",
            "services/converter/src/**/*.mjs", "services/converter/src/**/*.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: { ...globals.node },
    },
    rules: {
      ...js.configs.recommended.rules,
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
    },
  },
];
