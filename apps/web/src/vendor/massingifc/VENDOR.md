# Vendored: `MassingCloud/massingifc`

`core-kernel`, `plugin-sdk` and `project-schema`, copied **verbatim** from
`MassingCloud/massingifc` at commit `93606570374133ebea30e31405893929e0416e2e` (2026-07-27).
MIT licensed — see `LICENSE` in this directory.

## Why vendored rather than depended upon

Originally because `massingifc` was **private** while this repo is public — installing from a private
repo needs a token in CI, which breaks forks and contradicts the offline/deterministic build
constraint. **That reason is gone: the kernel repo went public on 2026-07-27.** Vendoring continues
for now because these three packages have **zero runtime dependencies**, no `node:` builtins and no
DOM references, so the copy costs nothing and keeps the build hermetic without either a registry
publish or a submodule. Moving to a real dependency is tracked on the roadmap — it needs the packages
published somewhere npm can reach, which is a separate decision, not a code change.

## Re-syncing

## Local deviations from upstream — NONE

There were two, both reported and both now fixed upstream and dropped on the first re-sync:
`commands.ts`'s dead `ok` import, and `createUuidIdFactory` falling back to `Math.random()`
(CodeQL `js/insecure-randomness`, high). See
[PR #5](https://github.com/MassingCloud/massingifc/pull/5).

Upstream's own `*.test.ts` files are **excluded from `tsc`** (`exclude` in `tsconfig.json`) but are
still **run by Vitest**. Eight of them fail our typecheck for a reason that is not a defect —
`interface TestEvents` does not satisfy `EventMap = Record<string, unknown>`, because a TS
`interface` has no implicit index signature where a `type` alias does. Upstream never sees this since
its build does not typecheck its test files. Judging someone else's tests by our compiler flags would
force a fork for no benefit; running them is what actually proves the vendored copy behaves.

The files are otherwise **unmodified**, deliberately — no local edits, so a refresh is a copy rather than a
merge. Cross-package imports (`@massingifc/core-kernel`) resolve through `paths` in `tsconfig.json`
and `resolve.alias` in `vite.config.ts`; nothing here was rewritten to relative paths.

```bash
git clone https://github.com/MassingCloud/massingifc.git /tmp/massingifc
for p in core-kernel plugin-sdk project-schema; do
  cp /tmp/massingifc/packages/$p/src/*.ts apps/web/src/vendor/massingifc/$p/
done
# then update the SHA above and run: npm run typecheck && npx vitest run src/vendor
```

Upstream's own test files are kept and run by our vitest. They are the check that the vendored copy
still behaves — a vendored library nobody exercises is a fork you have not noticed yet.

## Upstream issues — all four closed

[#1](https://github.com/MassingCloud/massingifc/issues/1) `evaluateExpression` inherited-property
lookup · [#2](https://github.com/MassingCloud/massingifc/issues/2) container extension ·
[#3](https://github.com/MassingCloud/massingifc/issues/3) caret ranges on `@thatopen/*` ·
[#4](https://github.com/MassingCloud/massingifc/issues/4) the `Math.random()` id fallback plus a dead
import. All fixed in [PR #5](https://github.com/MassingCloud/massingifc/pull/5) and carried in the
commit pinned above. `src/kernel/ties.test.ts` pinned #2 as an assertion of the *wrong* state that
would fail when it was fixed — and it did, on this re-sync, which is exactly what that pattern is for.
