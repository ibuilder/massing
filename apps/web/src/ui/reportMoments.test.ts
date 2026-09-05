import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  type CatalogEntry, type ReportMoment, REPORT_MOMENTS, missingReportIds, packageJobParams, resolveMoment,
  unclaimedReports,
} from "./reportMoments";

/**
 * R24-REPORTS-BY-MOMENT.
 *
 * The moments are a routing layer over a catalog that lives in **Python**. That is the whole risk: a
 * report renamed in `reports.py` costs nothing at build time, costs nothing at runtime, and quietly
 * shortens a package on the Friday it is due. The load-bearing assertion here is therefore not that
 * the moments are well-chosen — taste is not testable — but that **every id they name is still
 * served**, checked against `reports.py` itself rather than against a copy of it.
 *
 * Same technique as `shell/roomNames.test.ts`, for the same reason: two tables encoding one fact
 * drift, and this repo has the scars.
 */

const REPORTS_PY = resolve(__dirname, "../../../../services/api/src/aec_api/reports.py");

/** `"executive": ("Executive Summary", "Health"),` → the catalog the API serves. */
/** Memoised for the same reason as `emptyGuide.test.ts`: repeated reads of a large source file were
 *  measurable contention in the parallel suite. */
let _cat: CatalogEntry[] | null = null;

function pythonCatalog(): CatalogEntry[] {
  if (_cat) return _cat;
  const src = readFileSync(REPORTS_PY, "utf8");
  const start = src.indexOf("REPORTS: dict");
  expect(start, "could not find the REPORTS table — reports.py was restructured").toBeGreaterThan(-1);
  const block = src.slice(start, src.indexOf("\n}", start));
  return (_cat = [...block.matchAll(/^\s*"([a-z0-9_]+)":\s*\(\s*"([^"]+)",\s*"([^"]+)"\s*\)/gm)]
    .map((m) => ({ id: m[1]!, name: m[2]!, group: m[3]! })));
}

describe("the catalog can actually be read from reports.py", () => {
  it("parses a plausible number of reports and groups", () => {
    // Guards the regex itself: if reports.py changes shape this fails here, loudly, rather than
    // returning an empty catalog and making every assertion below vacuously pass.
    const cat = pythonCatalog();
    expect(cat.length).toBeGreaterThan(40);
    expect(new Set(cat.map((r) => r.group)).size).toBeGreaterThan(8);
    expect(cat.find((r) => r.id === "executive")?.name).toBe("Executive Summary");
  });
});

describe("every moment names reports that exist", () => {
  /**
   * **This is a cross-lane tripwire, so its failure message has to be an instruction.**
   *
   * A backend rename fails a *web* test. That is the whole value — a renamed report id is otherwise
   * free at build, free at runtime, and shows up as a package one row shorter on the Friday it is
   * due. But it also means the red suite lands in front of whoever is holding the **backend** lane,
   * and "why is the web suite failing at me" is a bad first five minutes. The message therefore names
   * the file, the ids, the file to edit, and why it matters — the same reason `test_module_rooms` and
   * `test_reachable` should say what to do rather than only what is wrong.
   */
  it("no moment references a report the server does not serve", () => {
    const missing = missingReportIds(REPORT_MOMENTS, pythonCatalog());
    expect(missing, missing.length
      ? `reports.py no longer defines: ${missing.join(", ")}.\n`
        + "If a report was renamed there, update REPORT_MOMENTS in apps/web/src/ui/reportMoments.ts "
        + "to match. This is not a web defect — a report package that silently loses a row still "
        + "looks complete to the person assembling it."
      : "").toEqual([]);
  });

  it("reports the gap rather than throwing, so the Report Center still opens", () => {
    const cat: CatalogEntry[] = [{ id: "cost", name: "Cost Report", group: "Cost" }];
    const moments = [{ id: "m", label: "M", occasion: "o", reports: ["cost", "gone", "also_gone"] }];
    expect(missingReportIds(moments, cat)).toEqual(["also_gone", "gone"]);
    // …and the moment still resolves to what does exist.
    expect(resolveMoment(moments[0]!, cat).map((r) => r.id)).toEqual(["cost"]);
  });
});

describe("the moments are moments, not groups renamed", () => {
  it("each names an occasion — who is asking and when", () => {
    for (const m of REPORT_MOMENTS) {
      expect(m.occasion.length, `${m.id} has no occasion`).toBeGreaterThan(20);
      expect(m.reports.length, `${m.id} is too thin to be a package`).toBeGreaterThan(3);
    }
  });

  it("ids and labels are unique", () => {
    expect(new Set(REPORT_MOMENTS.map((m) => m.id)).size).toBe(REPORT_MOMENTS.length);
    expect(new Set(REPORT_MOMENTS.map((m) => m.label)).size).toBe(REPORT_MOMENTS.length);
  });

  it("no moment repeats a report within itself", () => {
    for (const m of REPORT_MOMENTS) {
      expect(new Set(m.reports).size, `${m.id} lists a report twice`).toBe(m.reports.length);
    }
  });

  /**
   * The assertion that proves this is a routing layer rather than a second taxonomy.
   *
   * If every report belonged to exactly one moment we would have rebuilt the noun catalog with
   * friendlier headings — which is the failure mode the audit warns about. Overlap is the *point*:
   * `verified_progress` is evidence in a lender draw, in a monthly package and at closeout, and the
   * group taxonomy can only file it once.
   */
  it("reports are shared across moments, because occasions overlap", () => {
    const counts = new Map<string, number>();
    for (const m of REPORT_MOMENTS) for (const id of m.reports) counts.set(id, (counts.get(id) ?? 0) + 1);
    const shared = [...counts.values()].filter((n) => n > 1).length;
    expect(shared).toBeGreaterThan(3);
    expect(counts.get("verified_progress")).toBeGreaterThan(1);
  });
});

describe("the long tail is visible rather than pretended away", () => {
  it("reports claimed by no moment can be listed", () => {
    const tail = unclaimedReports(REPORT_MOMENTS, pythonCatalog());
    // Not a failure — 56 reports and seven occasions means a tail by design, and the noun groups
    // still hold every one. This asserts the QUESTION is answerable, which is what makes a badly
    // named or never-due report findable later.
    expect(Array.isArray(tail)).toBe(true);
    expect(tail.length).toBeLessThan(pythonCatalog().length);
  });
});

describe("assembling a package does not invent reports", () => {
  it("the job params are the moment's own ids, in order", () => {
    const m = REPORT_MOMENTS[0]!;
    expect(packageJobParams(m)).toEqual({ moment_id: m.id, reports: m.reports });
  });
});

/**
 * **The moments now live in Python, and this table is a mirror of that one.**
 *
 * They were authored here and resolved here, which worked for a person clicking a button in the
 * Report Center and could never work for a *schedule*: `routines_run.run_due` had no way to turn
 * "the owner's monthly package" into a `reports[]` list, because the only table saying what that
 * package contains was in a browser bundle. So `report_moments.py` owns it, and `reportCenter.ts`
 * keeps rendering from the literal above rather than growing a second await on its load path.
 *
 * Two copies of one fact is the thing this repository has scars from — which is why it is bound the
 * same way the catalog above is, by reading the other language's source rather than a copy of it.
 * The check is **exact and ordered**: ids, order, labels, occasions and report lists. Order matters
 * because it is assembly order for the PDF, and a package whose sections come out shuffled is a
 * package somebody has to re-read.
 *
 * The single-source alternative — delete this literal, fetch the moments from the API — stays open
 * and is recorded in `report_moments.py`. It is a Report Center change, not a scheduler one.
 */
const MOMENTS_PY = resolve(__dirname, "../../../../services/api/src/aec_api/report_moments.py");

function pythonMoments(): ReportMoment[] {
  const src = readFileSync(MOMENTS_PY, "utf8");
  const start = src.indexOf("MOMENTS: dict");
  expect(start, "could not find the MOMENTS table — report_moments.py was restructured")
    .toBeGreaterThan(-1);
  const block = src.slice(start, src.indexOf("\n}", start));
  return [...block.matchAll(/"([a-z0-9_]+)":\s*\(\s*"([^"]*)",\s*"([^"]*)",\s*\[([^\]]*)\]\s*\)/g)]
    .map((m) => ({
      id: m[1]!, label: m[2]!, occasion: m[3]!,
      reports: [...m[4]!.matchAll(/"([a-z0-9_]+)"/g)].map((r) => r[1]!),
    }));
}

describe("the moments agree with the server's copy", () => {
  it("parses a plausible table, so the comparison below cannot pass vacuously", () => {
    // Same guard as the catalog parser: a restructured Python literal must fail HERE, loudly,
    // rather than yielding an empty list that makes every id match nothing and every check green.
    const py = pythonMoments();
    expect(py.length).toBeGreaterThan(4);
    expect(py.every((m) => m.reports.length > 0)).toBe(true);
  });

  it("id, order, label, occasion and reports are identical on both sides", () => {
    // A cross-lane tripwire, so the message has to be an instruction: this is a WEB test that a
    // BACKEND edit can turn red.
    expect(
      pythonMoments(),
      "the moments differ between apps/web/src/ui/reportMoments.ts and "
      + "services/api/src/aec_api/report_moments.py. They are one table with two homes: Python is "
      + "the one a scheduled routine reads, this file is the one the Report Center renders. Edit "
      + "both, in the same commit.",
    ).toEqual(REPORT_MOMENTS.map((m) => ({
      id: m.id, label: m.label, occasion: m.occasion, reports: m.reports,
    })));
  });
});
