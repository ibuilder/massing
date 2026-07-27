# Vendored: `MassingCloud/massingifc`

`core-kernel`, `plugin-sdk` and `project-schema`, copied **verbatim** from
`MassingCloud/massingifc` at commit `3da57cb314641f2848f18ebc3dd155ad81096916` (2026-07-27).
MIT licensed — see `LICENSE` in this directory.

## Why vendored rather than depended upon

`massingifc` is a **private** repository and `ibuilder/massing` is **public**. An `npm install` from
a private repo needs a token in CI, which breaks forks and contradicts the offline/deterministic
build constraint this project holds. These three packages have **zero runtime dependencies**, no
`node:` builtins and no DOM references, so vendoring the TypeScript source costs nothing and keeps
the build hermetic. (Same reasoning as the vendored Lucide icons.)

## Re-syncing

## Local deviations from upstream — exactly one

`core-kernel/commands.ts` line 4: the unused `ok` import is removed. It is genuinely dead upstream
(every other `ok` in that file is `.ok` **property access** on a `Result`, not the constructor), and
this project compiles with `noUnusedLocals` while upstream does not. Reported as upstream #4; delete
this note when the fix lands and the next re-sync will be clean again.

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

## Open upstream issues that affect us

- [#1](https://github.com/MassingCloud/massingifc/issues/1) — `evaluateExpression` resolves inherited
  property names and yields `NaN` instead of refusing. In `estimating-5d`, **not** vendored here.
- [#2](https://github.com/MassingCloud/massingifc/issues/2) — the container adapter is coded against
  `.mmproj`; we write `.mass` (see `services/api/src/aec_api/bundle.py`). Affects `core-kernel`,
  which **is** vendored. `containerFormatTies` in `src/kernel/ties.test.ts` pins the disagreement so
  it cannot be forgotten.
- [#3](https://github.com/MassingCloud/massingifc/issues/3) — caret ranges on `@thatopen/*`. In
  `viewer-thatopen`, not vendored; we keep our own pinned pair.
