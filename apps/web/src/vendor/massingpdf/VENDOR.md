# Vendored: `@massingcloud/pdf-viewer`

`MassingCloud/massing-pdf` at commit `65e9011457fcc464d1e5f58e13441dc05e0bf15e` (2026-07-27). **MIT.**

## Why vendored rather than depended on

It is not published to npm. Until it is, a dependency would mean a git URL in `package.json` — which
pins nothing reproducibly, cannot be hash-locked, and fails a hermetic build. Copying costs nothing
here: its only external imports are `pdfjs-dist` and `pdf-lib`, both of which this app already
depends on, so vendoring adds **no new dependency**.

Same treatment as `massingifc`: verbatim copy, resolved through the single alias map in
`apps/web/vendorAlias.ts`, and **no local patches**. A patch here would fork us from upstream
silently; anything wrong goes upstream as an issue and comes back on the next re-sync.

## Local deviations from upstream — NONE

Upstream `*.test.ts` files are excluded from the copy (they are run in that repo, not this one).

## Re-syncing

```
git clone https://github.com/MassingCloud/massing-pdf   # or fetch an existing clone
cp -r massing-pdf/src/* apps/web/src/vendor/massingpdf/
find apps/web/src/vendor/massingpdf -name '*.test.ts' -delete
```
then update the SHA above and run `npm run typecheck && npx vitest run src/vendor src/drawings`.

## What it is

A construction drawing review engine: PDF viewing, AEC markup, calibrated takeoff, issue pinning,
revision compare, XFDF/BCF interchange, behind a small plugin kernel. 46 files / ~12.3k lines against
our `drawings/pdfTakeoff.ts` (~423 lines), and the difference is not size — it models a markup as a
**record** (who, which sheet revision, which discipline, what it measures, which spec clause, which
IFC object, what review status) rather than as ink with a comment attached. Rendering is one
projection of that record; XFDF, BCF, CSV and a flattened PDF are others.

**Adoption is incremental and not yet started.** This commit vendors and wires it; `pdfTakeoff.ts`
still owns the takeoff flow. Replacing it is a separate, testable step — landing 12k lines and
re-pointing the UI in one move would make a regression impossible to bisect.

## Open upstream

- [#9](https://github.com/MassingCloud/massing-pdf/issues/9) — a competitor product name in public
  metadata, including an npm keyword. Cosmetic, but the keyword is indexed once published.
