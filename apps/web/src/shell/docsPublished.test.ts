import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join, relative, resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * `docs/` is two things at once, and that is the whole problem this file guards.
 *
 * It is the documentation source **and** the GitHub Pages web root: `pages.yml` runs
 * `cp -r docs/. _site/`, so anything committed under `docs/` becomes a page on massing.build. On
 * 2026-07-29 that meant eleven superseded internal audits, four unbuilt plans, and a 264 KB
 * completed-roadmap were all being served to strangers beside the user guide, with nothing in the URL
 * or the page to say which was which. A visitor who found `security-audit-2026-07.md` or
 * `module-room-audit.md` had no way to know they were reading a working note from a month ago.
 *
 * The fix was `docs/internal/` plus one `rm -rf _site/internal` line. This test exists because that
 * line is invisible: nothing about adding `docs/internal/foo.md` tells you whether the fence still
 * holds, and nothing about deleting the `rm -rf` breaks a build. The failure mode is silent
 * publication, which is the kind you find out about from outside.
 *
 * Deliberately **not** an allowlist of published filenames. A hand-kept list of "the good docs" is the
 * thing that rots — it passes forever while the directory drifts away from it. These assertions read
 * the workflow and the documents' own self-description instead, so a new internal note is caught by
 * what it says about itself rather than by whether someone remembered to add it to a list.
 */

// process.cwd() is apps/web under vitest — matching docsCurrent.test.ts.
const REPO = resolve(process.cwd(), "..", "..");
const DOCS = resolve(REPO, "docs");
const INTERNAL = join(DOCS, "internal");

function read(abs: string): string {
  return readFileSync(abs, "utf8");
}

/** Every `.md` under `docs/`, as repo-relative POSIX paths. */
function allDocs(dir: string = DOCS): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const abs = join(dir, entry);
    if (statSync(abs).isDirectory()) out.push(...allDocs(abs));
    else if (entry.endsWith(".md")) out.push(relative(REPO, abs).split("\\").join("/"));
  }
  return out;
}

const DOC_PATHS = allDocs();
const isInternal = (p: string) => p.startsWith("docs/internal/");

describe("the Pages workflow fences internal notes off the published site", () => {
  const WORKFLOW = read(resolve(REPO, ".github/workflows/pages.yml"));

  it("the workflow loaded — otherwise every assertion here is vacuous", () => {
    expect(WORKFLOW.length).toBeGreaterThan(500);
    expect(WORKFLOW).toContain("cp -r docs/. _site/");
  });

  it("strips _site/internal after copying docs in", () => {
    // Order matters: stripping before the copy does nothing at all, and would read as protection.
    //
    // Matched as a LIVE line, not with indexOf over the whole file. The first version of this used
    // `WORKFLOW.indexOf("rm -rf _site/internal")`, and commenting the command out — `# rm -rf
    // _site/internal`, which is exactly how a fence gets disabled during debugging — left the string
    // present and the test green. A gate that cannot tell a command from a comment about that command
    // is not watching the thing it names. Verified by mutation: commenting the line now fails here.
    const lines = WORKFLOW.split("\n").map((l) => l.trim());
    const liveIdx = (needle: string) =>
      lines.findIndex((l) => !l.startsWith("#") && l.includes(needle));

    const copy = liveIdx("cp -r docs/. _site/");
    const strip = liveIdx("rm -rf _site/internal");
    expect(copy, "pages.yml no longer copies docs into _site — this whole file is vacuous")
      .toBeGreaterThan(-1);
    expect(strip, "pages.yml has no LIVE `rm -rf _site/internal` — internal notes are being published")
      .toBeGreaterThan(-1);
    expect(strip, "the strip runs before the copy, so it removes nothing").toBeGreaterThan(copy);
  });
});

describe("internal notes live under docs/internal/", () => {
  it("the fence is not empty — a passing check over zero files proves nothing", () => {
    expect(DOC_PATHS.length).toBeGreaterThan(20);
    expect(DOC_PATHS.filter(isInternal).length).toBeGreaterThan(5);
  });

  it("docs/internal/ explains itself", () => {
    // Without this, the directory is just an unexplained hole in the site.
    expect(DOC_PATHS).toContain("docs/internal/README.md");
    expect(read(join(INTERNAL, "README.md"))).toMatch(/not part of the published documentation/i);
  });

  it("every internal note is accounted for in the internal index", () => {
    /**
     * `internal/README.md` carries a table saying what each note was and what superseded it — which is
     * the only thing that stops the directory becoming a pile nobody dares delete from. That table is
     * hand-written, so it is exactly the kind of list that passes review while drifting from the
     * directory beside it. Asserted as a **set difference against the real files**, not as a count:
     * a count agrees with itself forever, and drops a file the moment two changes cancel out.
     */
    const index = read(join(INTERNAL, "README.md"));
    const undocumented = DOC_PATHS
      .filter((p) => isInternal(p) && !p.endsWith("internal/README.md"))
      .map((p) => p.split("/").pop()!)
      .filter((name) => !index.includes(`\`${name}\``));
    expect(undocumented, `add these to docs/internal/README.md: ${undocumented.join(", ")}`).toEqual([]);
  });

  it("every name the internal index cites still exists", () => {
    /**
     * The mirror of the check above, and the half that was missing. That one asks "is every file in
     * the index?"; without this one, nothing asks "is every index entry a real file?".
     *
     * A dead entry is worse than a missing one, which is why it earns its own assertion rather than
     * being left to tidiness: the index is the thing people read to decide whether a note still
     * matters, so a row pointing at a deleted file reads exactly like a live one. This repo has
     * recorded the same shape twice already — an `AUTHORISING` name with no referent silently becomes
     * an approved gate the day something reuses it, and `test_claude_md_gates` exists because
     * backticked paths in the docs drifted from the tree.
     *
     * Currently zero, so this starts green and can only be tripped by a future deletion that leaves
     * its row behind.
     */
    const index = read(join(INTERNAL, "README.md"));
    const real = new Set(
      DOC_PATHS.filter(isInternal).map((p) => p.split("/").pop()!),
    );
    // Compare BASENAMES on both sides. `real` is basenames, so a legitimate path-qualified
    // cross-reference — `docs/security/threat-model.md` — was flagged as dangling purely for being
    // written with its directory. Found by writing exactly such a reference and watching this fail:
    // a gate whose first real-world encounter is a false positive is one people learn to work around.
    const cited = [...index.matchAll(/`([^`]+\.md)`/g)].map((m) => m[1]!.split("/").pop()!);
    const dangling = [...new Set(cited)].filter((name) => !real.has(name));
    expect(
      dangling,
      `these are cited in docs/internal/README.md but no such file exists: ${dangling.join(", ")}`,
    ).toEqual([]);
  });

  /**
   * The content-driven half. A doc that calls itself superseded, or a point-in-time audit, or says
   * nothing is built yet, is a working note by its own admission — so it does not belong on the public
   * site regardless of who filed it where. This catches the next one without anyone maintaining a list.
   */
  it("no self-declared superseded or not-yet-built doc sits where Pages would publish it", () => {
    // `/—\s*superseded/` was the first attempt and it missed `status.md`, whose banner read
    // "— **long** superseded". Matching the word anywhere in the opening is the version that holds:
    // the qualifier a writer chooses is not something a gate can enumerate.
    const markers = [
      /point-in-time (?:audit|snapshot)/i,
      /\bsuperseded\b/i,
      /\bNothing here is built yet\b/i,
    ];
    const leaked = DOC_PATHS.filter((p) => {
      if (isInternal(p)) return false;
      // Only the opening matters: roadmap.md discusses superseded items throughout its body.
      const head = read(resolve(REPO, p)).split("\n").slice(0, 12).join("\n");
      return markers.some((m) => m.test(head));
    });
    expect(leaked, `these declare themselves working notes but would be published: ${leaked.join(", ")}`)
      .toEqual([]);
  });
});

describe("every relative link in the documentation resolves", () => {
  /**
   * Added after reorganising `docs/` broke **34** relative links in one commit — every archived audit
   * moved two directories deeper, so its `](roadmap.md)` silently became a 404, and
   * `roadmap-completed.md` kept pointing at four files that had moved out from under it.
   *
   * Nothing caught it. A broken link in a markdown file does not fail a build, does not fail a
   * typecheck, and looks completely fine in a diff — you find it when a reader clicks it. This walks
   * the tree instead, which takes milliseconds and is the only way the next reorganisation gets caught
   * on the same day it happens.
   */
  const ROOT_DOCS = ["README.md", "CONTRIBUTING.md", "SECURITY.md", "LICENSE-NOTES.md", "CLAUDE.md"];
  const ALL = [...DOC_PATHS, ...ROOT_DOCS];

  it("there is a corpus to check", () => {
    expect(ALL.length).toBeGreaterThan(30);
  });

  for (const rel of ALL) {
    it(`${rel} has no dead relative links`, () => {
      const text = read(resolve(REPO, rel));
      const base = resolve(REPO, rel, "..");
      const dead: string[] = [];
      for (const m of text.matchAll(/\[[^\]]*\]\(([^)\s]+)\)/g)) {
        const href = m[1]!;
        if (/^(?:https?:|mailto:|#|\/\/)/.test(href)) continue;
        const target = href.split("#")[0]!;
        if (!target) continue;
        if (!existsSync(resolve(base, decodeURIComponent(target)))) dead.push(href);
      }
      expect([...new Set(dead)], `${rel} links to files that do not exist`).toEqual([]);
    });
  }
});

describe("the published site does not link into the fence", () => {
  /**
   * The failure this prevents is a 404 on the marketing site. `index.html` linked
   * `design-audit.md` relatively; once that file moved under `internal/` the relative link pointed at
   * a path Pages no longer serves. Internal notes are still readable — via the repo — so the fix is an
   * absolute GitHub URL, which is the pattern `index.html` already used for `gc-portal.md`.
   */
  const HTML = readdirSync(DOCS).filter((f) => f.endsWith(".html"));

  it("there are pages to check", () => {
    expect(HTML.length).toBeGreaterThan(0);
  });

  for (const page of HTML) {
    it(`${page} has no relative link into internal/`, () => {
      const text = read(join(DOCS, page));
      const bad = [...text.matchAll(/(?:href|src)="([^"]+)"/g)]
        .map((m) => m[1]!)
        .filter((h) => !/^https?:|^\/\//.test(h) && h.includes("internal/"));
      expect(bad, `${page} links to unpublished paths: ${bad.join(", ")}`).toEqual([]);
    });
  }
});

describe("a backticked source file in a published doc actually exists", () => {
  /**
   * `CLAUDE.md` states the rule — "Backticks are therefore reserved for files that exist" — and
   * enforces it for its own citations via `services/api/test_claude_md_gates.py`. Nothing enforced it
   * for the docs a *reader* sees, and on 2026-08-13 three had rotted:
   *
   *   README.md                   `entitlements.py`          -> the tier seam is `tiers.py`
   *   docs/reference/architecture.md  `test_no_competitors.py`   -> `test_no_comparative_names.py`
   *   docs/reference/architecture.md  `check_file_sizes.py`      -> `test_file_sizes.py`
   *
   * The last two are the sharp lesson. **Both are names CLAUDE.md holds up as examples of files that
   * never existed** — and they were copied out of that warning into a reference table as though they
   * were citations. A cautionary example and a citation look identical once the surrounding sentence
   * is gone, which is exactly why the rule needs a gate rather than a paragraph.
   *
   * Matched on basename, not path, because docs cite `rooms.py` far more often than
   * `services/api/src/aec_api/rooms.py` and requiring full paths would be answered by deleting the
   * backticks. Generated artefacts and third-party config are excluded by name below — each is a file
   * that legitimately does not live in this repo.
   */
  const EXTERNAL = new Set([
    "claude_desktop_config.json", // Claude Desktop's own config, on the user's machine
    "latest.json",                // emitted by tauri-action at release time
    "props.json",                 // a MinIO object, not a repo file
    "package.json",               // ambiguous: many, and always real
    "tsconfig.json",
  ]);

  const TRACKED = new Set(
    execFileSync("git", ["ls-files"], { cwd: REPO, encoding: "utf8" })
      .split("\n")
      .filter(Boolean),
  );
  const BASENAMES = new Set([...TRACKED].map((p) => p.split("/").pop()!));

  const PUBLISHED = DOC_PATHS.filter((p) => !isInternal(p) && !p.includes("roadmap"))
    .concat(["README.md"]);

  it("has a corpus and a file list — either being empty makes this vacuous", () => {
    expect(TRACKED.size).toBeGreaterThan(500);
    expect(PUBLISHED.length).toBeGreaterThan(10);
  });

  it("cites no source file that is not in the repo", () => {
    const CITE = /`([A-Za-z0-9_.-]+\.(?:py|ts|tsx|json|yml|yaml|toml|sh))`/g;
    const bad: string[] = [];
    for (const rel of PUBLISHED) {
      const text = readFileSync(resolve(REPO, rel), "utf8");
      for (const m of text.matchAll(CITE)) {
        const name = m[1]!;
        if (EXTERNAL.has(name) || BASENAMES.has(name)) continue;
        bad.push(`${rel}: \`${name}\``);
      }
    }
    expect(
      [...new Set(bad)],
      "these docs cite files that do not exist — fix the name or drop the backticks",
    ).toEqual([]);
  });
});

describe("every endpoint the docs document actually exists", () => {
  /**
   * `README.md` documented `GET /projects/{id}/codecheck/occupancy`. There is no such route — the
   * endpoint is `/codecheck/egress`, whose own docstring reads *"COMPUTED occupancy load (IBC 1004) +
   * egress capacity (IBC 1005)"*. A reader following the README got a 404 on the one call the line
   * existed to describe. Nothing caught it: the path is not a file, so the citation gate above cannot
   * see it, and no test reads prose.
   *
   * **The matcher is the interesting part, and the first two versions were unusable.** A naive
   * string compare reported 22 unmatched claims of which 21 were the checker's fault:
   *
   *   - `POST /test-fit/{compare,optimize}` — brace shorthand for two routes, truncated at the comma.
   *   - `POST /wp-json/massing-sso/v1/token` — WordPress, not this API.
   *   - `GET /projects/{pid}/modules/rfi` — correct: `rfi` is a value of the declared `{key}` segment.
   *
   * A gate with a 95% false-positive rate does not get fixed, it gets deleted — so it matches
   * segment-wise, letting a declared `{param}` absorb a literal, and skips brace-shorthand and
   * non-API hosts explicitly rather than by accident. At 982 declared routes and 169 documented
   * claims it now reports zero, and reverting the `occupancy` typo fails it.
   */
  const ROUTES: Array<[string, string[]]> = [];
  {
    const dir = resolve(REPO, "services/api/src/aec_api/routers");
    const files = readdirSync(dir).filter((f) => f.endsWith(".py"))
      .map((f) => join(dir, f))
      .concat([resolve(REPO, "services/api/src/aec_api/main.py")]);
    for (const f of files) {
      if (!existsSync(f)) continue;
      const src = readFileSync(f, "utf8");
      for (const m of src.matchAll(/@\w+\.(get|post|put|patch|delete)\(\s*["']([^"']+)/g)) {
        ROUTES.push([m[1]!.toUpperCase(), m[2]!.split("/").filter(Boolean)]);
      }
    }
  }

  /**
   * A DECLARED `{param}` absorbs any literal — that is what a path parameter means, and it is why
   * `GET /projects/{pid}/modules/rfi` is correct.
   *
   * A DOC-side `{id}` must NOT absorb a declared literal, and getting that backwards made the first
   * version of this gate match everything. With both sides permissive, the generic register route
   * `projects/{pid}/modules/{key}/{rid}` — three wildcards in four segments — matched
   * `projects/{id}/codecheck/occupancy`, the very defect this file was written for. The gate passed
   * its own mutation test at 0 failures and I nearly shipped it.
   */
  const segMatch = (r: string[], d: string[]) =>
    r.length === d.length && r.every((rs, i) => (rs.startsWith("{") ? true : rs === d[i]));

  /**
   * The tail rule exists because docs legitimately abbreviate: `GET /budget/cashflow` for
   * `/projects/{pid}/budget/cashflow`. It must ANCHOR ON A LITERAL, and that took three attempts.
   *
   * The register route `/projects/{pid}/modules/{key}/{rid}` ends in two consecutive wildcards, so an
   * unanchored tail rule matched *any* two-segment path — `/authoring/invented-thing` included. Every
   * loosening of this matcher was punished by that one route, which is the useful lesson: a route
   * table with wildcard-heavy generics will absorb a sloppy matcher silently.
   */
  const known = (verb: string, segs: string[]) =>
    ROUTES.some(([v, r]) => {
      if (v !== verb) return false;
      if (segMatch(r, segs)) return true;
      if (r.length <= segs.length) return false;
      const tail = r.slice(-segs.length);
      return !tail[0]!.startsWith("{") && segMatch(tail, segs);
    });

  it("parsed a plausible route table — otherwise this passes vacuously", () => {
    expect(ROUTES.length, `parsed ${ROUTES.length} routes`).toBeGreaterThan(300);
  });

  it("documents no endpoint the API does not declare", () => {
    // Brace-shorthand (`{a,b}`) and non-API hosts are not claims about this API's route table.
    const SKIP = /\{[^}]*[,|][^}]*\}|\/wp-json\//;
    const bad: string[] = [];
    for (const rel of DOC_PATHS.filter((p) => !isInternal(p) && !p.includes("roadmap")).concat(["README.md"])) {
      const text = readFileSync(resolve(REPO, rel), "utf8");
      for (const m of text.matchAll(/\b(GET|POST|PUT|PATCH|DELETE)\s+(\/[a-zA-Z0-9/{},|_.-]+)/g)) {
        const raw = m[2]!;
        if (SKIP.test(raw)) continue;
        if (known(m[1]!, raw.split("/").filter(Boolean))) continue;
        bad.push(`${rel}: ${m[1]} ${raw}`);
      }
    }
    expect([...new Set(bad)], "documented endpoints with no matching route").toEqual([]);
  });
});
