import { defineConfig } from "vitest/config";

import { vendorAlias } from "./vendorAlias";

// Standalone from vite.config.ts so the PWA/coi plugins don't run under test. happy-dom gives
// the unit tests a lightweight DOM + localStorage without a real browser.
export default defineConfig({
  // Same alias the app build uses, from the same source — see vendorAlias.ts.
  resolve: { alias: { ...vendorAlias } },
  test: {
    environment: "happy-dom",
    include: ["src/**/*.test.ts"],
    globals: true,
  },
});
