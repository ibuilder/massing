/**
 * Where the vendored packages resolve — defined **once**.
 *
 * The vendored packages (`src/vendor/massingifc`, `src/vendor/massingpdf`) are copied verbatim from
 * their upstream repos, which
 * means its cross-package imports say `@massingifc/core-kernel` rather than a relative path. Three
 * tools need to be told what that means: `tsc` (via `paths` in tsconfig.json), the app build (Vite)
 * and the tests (Vitest).
 *
 * Three copies of one fact is the drift shape this codebase keeps paying for — a viewport-preset
 * list kept in two places silently served a *different* layout than the one requested. So the map
 * lives here, Vite and Vitest import it, and `src/kernel/ties.test.ts` asserts that tsconfig.json's
 * `paths` still agrees with it. tsconfig cannot import TypeScript, so that one copy is unavoidable —
 * but an unavoidable copy that is *asserted* is not the same as one that is merely hoped for.
 */
import { fileURLToPath } from "node:url";

const here = (p: string) => fileURLToPath(new URL(p, import.meta.url));

/** Package name → the file it resolves to, relative to this directory. */
export const VENDOR_ENTRIES: Readonly<Record<string, string>> = {
  "@massingifc/core-kernel": "./src/vendor/massingifc/core-kernel/index.ts",
  "@massingifc/plugin-sdk": "./src/vendor/massingifc/plugin-sdk/index.ts",
  "@massingifc/project-schema": "./src/vendor/massingifc/project-schema/index.ts",
  "@massingcloud/pdf-viewer": "./src/vendor/massingpdf/index.ts",
};

/** The same map as absolute paths, which is what Vite and Vitest want. */
export const vendorAlias: Record<string, string> = Object.fromEntries(
  Object.entries(VENDOR_ENTRIES).map(([name, rel]) => [name, here(rel)]),
);
