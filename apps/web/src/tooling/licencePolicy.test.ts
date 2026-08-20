import { readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * The licence classifier, and the false positive it almost shipped with.
 *
 * R41-LICENCE-GATE exists because a scan found repositories whose actual LICENSE differs from their
 * README or badge. So the gate must read the **file**, and the classifier that reads it is the part
 * that can be confidently wrong.
 *
 * **It was.** The first draft tested licence names in precedence order, GPL before MPL, and reported
 * three contradictions — one of them `web-ifc`, a core dependency, "declared MPL-2.0 but actually
 * GPL". That is false: `web-ifc/LICENSE.md` opens with "Mozilla Public License Version 2.0", and
 * **MPL-2.0 defines "Secondary License" by naming the GNU GPL, LGPL and AGPL**, so every MPL-2.0
 * file contains the string "GNU General Public License". The matcher fired on a definition.
 *
 * The fix is a different rule rather than a longer exclusion list: **the earliest title wins**, since
 * a licence names itself at the top and every later mention is prose about a different licence.
 * These tests pin that, because the next person to add a licence to the table will reach for
 * precedence ordering — it is the obvious design, and it is wrong here.
 */

const SCRIPTS = join(process.cwd(), "scripts");

type Policy = {
  classify: (t: string) => string;
  declaredFamily: (d: string | null) => string;
  isDualWithPermissive: (d: string | null) => boolean;
  verdict: (p: { name: string; declared: string | null; licenceText: string | null; licenceFile: string | null }) =>
    { status: string; effective: string; reason: string };
};

async function policy(): Promise<Policy> {
  return (await import(/* @vite-ignore */ pathToFileURL(join(SCRIPTS, "licencePolicy.mjs")).href)) as Policy;
}

/** The opening of the real MPL-2.0, including the clause that caused the false positive. */
const MPL_2_0 = `Mozilla Public License Version 2.0
==================================

1. Definitions
--------------

1.13. "Secondary License"
    means either the GNU General Public License, Version 2.0, the GNU
    Lesser General Public License, Version 2.1, the GNU Affero General
    Public License, Version 3.0, or any later versions of those licenses.
`;

const GPL_3 = `                    GNU GENERAL PUBLIC LICENSE
                       Version 3, 29 June 2007

 Copyright (C) 2007 Free Software Foundation, Inc.
`;

const MIT = `MIT License

Copyright (c) 2024 Somebody

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
`;

/** Opening of CC0 1.0 Universal — the title type-fest and our family packs use. */
const CC0 = `CC0 1.0 Universal

Statement of Purpose

The laws of most jurisdictions throughout the world automatically confer
exclusive Copyright and Related Rights (defined below) upon the creator
`;

describe("licence classification reads the title, not any mention", () => {
  it("classifies MPL-2.0 as MPL even though its text names the GPL three times", async () => {
    const { classify } = await policy();
    // The regression that matters. A precedence-ordered matcher returns "GPL" here and indicts a
    // core dependency.
    expect(MPL_2_0).toContain("GNU General Public License");   // the trap is really present
    expect(classify(MPL_2_0)).toBe("MPL");
  });

  it("still classifies an actual GPL file as GPL", async () => {
    // The other half: fixing the false positive must not blind the gate to the real thing.
    const { classify } = await policy();
    expect(classify(GPL_3)).toBe("GPL");
  });

  it("classifies MIT and reports UNKNOWN rather than guessing", async () => {
    const { classify } = await policy();
    expect(classify(MIT)).toBe("MIT");
    expect(classify("Copyright 2020 someone. All rights reserved."))
      .toBe("UNKNOWN");
  });

  it("classifies CC0 1.0 Universal as CC0, not UNKNOWN", async () => {
    // type-fest ships this title; without it the npm gate counted CC0 as unclassified.
    const { classify, declaredFamily, verdict } = await policy();
    expect(classify(CC0)).toBe("CC0");
    expect(declaredFamily("CC0-1.0")).toBe("PERMISSIVE-OTHER");
    expect(verdict({ name: "type-fest", declared: "CC0-1.0", licenceText: CC0, licenceFile: "license" }).status)
      .toBe("OK");
  });

  it("matches the real web-ifc licence file on disk, not a fixture of it", async () => {
    // Assert against the artefact the gate actually reads. A fixture can agree with the classifier
    // while the real file differs — the same reason a round-trip through your own writer proves
    // nothing.
    const { classify, declaredFamily } = await policy();
    const dir = join(process.cwd(), "..", "..", "node_modules", "web-ifc");
    let text: string;
    try {
      text = readFileSync(join(dir, "LICENSE.md"), "utf8");
    } catch {
      return;  // hoisted elsewhere (a worktree); the fixture cases above still pin the behaviour
    }
    expect(classify(text), "web-ifc is MPL-2.0; classifying it GPL indicts a core dependency").toBe("MPL");
    expect(declaredFamily("MPL-2.0")).toBe("MPL");
  });
});

describe("licence policy", () => {
  it("fails a forbidden licence and names why", async () => {
    const { verdict } = await policy();
    const v = verdict({ name: "bad-dep", declared: "AGPL-3.0", licenceText: null, licenceFile: null });
    expect(v.status).toBe("FORBIDDEN");
    expect(v.reason).toContain("AGPL");
  });

  it("catches the badge-vs-file case this gate exists for", async () => {
    // Declared permissive, file says GPL. Nothing that reads only metadata can see this.
    const { verdict } = await policy();
    const v = verdict({ name: "liar", declared: "MIT", licenceText: GPL_3, licenceFile: "LICENSE" });
    expect(v.status).toBe("CONTRADICTION");
    expect(v.reason).toContain("declares MIT");
    expect(v.reason).toContain("GPL");
  });

  it("accepts a dual licence that offers a permissive option", async () => {
    // jszip declares "(MIT OR GPL-3.0-or-later)" and ships the MIT text. Without this it reads as a
    // GPL dependency and the gate is permanently red on a package that is fine.
    const { verdict, isDualWithPermissive } = await policy();
    expect(isDualWithPermissive("(MIT OR GPL-3.0-or-later)")).toBe(true);
    expect(verdict({ name: "jszip", declared: "(MIT OR GPL-3.0-or-later)", licenceText: MIT, licenceFile: "LICENSE" }).status)
      .toBe("OK");
  });

  it("reports weak copyleft rather than failing it", async () => {
    // ifcopenshell and web-ifc live here. Collapsing "disallowed" into "worth a look" makes the gate
    // either useless or permanently red, and a permanently red gate gets switched off.
    const { verdict } = await policy();
    expect(verdict({ name: "web-ifc", declared: "MPL-2.0", licenceText: MPL_2_0, licenceFile: "LICENSE.md" }).status)
      .toBe("REPORT");
  });
});
