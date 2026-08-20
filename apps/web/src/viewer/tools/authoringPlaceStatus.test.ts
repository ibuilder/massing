import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = readFileSync(resolve(process.cwd(), "src/viewer/tools/authoringSection.ts"), "utf8");

describe("Place reports the publish pipeline", () => {
  it("passes onTick into waitForPublish, the same path Republish already had", () => {
    // Without the second argument the Place button sits on "converting…" for the whole convert.
    const place = SRC.slice(SRC.indexOf("⊕ Place selected family"));
    const end = place.indexOf("Import IFC families");
    const body = end === -1 ? place : place.slice(0, end);
    expect(body).toMatch(/waitForPublish\(pid,\s*\(s\)/);
  });
});
