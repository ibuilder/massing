import type { ApiClient } from "../../api/client";
import { escapeHtml as esc } from "../../ui/feedback";

/**
 * Model → field layout, and the as-installed round-trip BACK (LAYOUT-RENUMBER).
 *
 * The export half moved here out of `qaSection.ts`, which sits on an exact size pin with no
 * headroom — and the import half is the reason the move was worth making. That panel has always
 * ended with the sentence *"stake/print these, shoot the as-installed positions with a total
 * station, then upload that CSV to verify deviation by point number"*, and **there was no upload.**
 * `layoutVerify` was frozen in `apps/web/src/api/clientCallers.test.ts` as called by nothing, so the
 * round-trip the copy promises stopped at the download.
 *
 * ## Two things the server had to be fixed for first
 *
 * `services/api/test_layout_renumber.py` has the detail. In short: the setout number is `P1..` in
 * export order, so it is a POSITION, and verifying by it compares a shot against whatever element
 * happens to hold that number in the export you verify against — measured, on two exports of one
 * model, as two fabricated deviations of a full grid bay with the real 100 mm displacement nowhere
 * in the output. The GlobalId was in the exported Description the whole time. And an unmatched file
 * used to return `checked: 0, out_of_tolerance: [], max_deviation_m: 0.0`, which is
 * character-for-character a perfect as-built.
 *
 * ## So this screen sends the Description column, and reads the coverage
 *
 * The parse is the first place the same defect could re-enter: a line this module cannot read is
 * COUNTED, never dropped, because a half-read survey file that reports no deviations is the defect
 * one layer earlier than the one the server just had.
 */
export type LayoutPoints = Awaited<ReturnType<ApiClient["layoutPoints"]>>;
export type LayoutVerify = Awaited<ReturnType<ApiClient["layoutVerify"]>>;
export type MeasuredShot = { number: string; e: number; n: number; z: number; description?: string };

export interface LayoutDeps {
  api: ApiClient;
  pid: string;
  container: HTMLElement;
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  // The host's own signatures, not idealised ones: `withLoading` resolves `undefined` when the task
  // throws, and `resultNote`'s kind is a union. Widening either here is a compile error at the call
  // site in `qaSection.ts`, which is the parity gate for this extraction — see that file's header
  // on why `tsc` and not the suite.
  withLoading: <T>(host: HTMLElement, label: string, fn: () => Promise<T>) => Promise<T | undefined>;
  toast: (msg: string, kind?: "info" | "success" | "error") => void;
  showResult: (title: string, render: (body: HTMLElement) => void) => void;
  resultNote: (html: string, kind?: "" | "ok" | "warn" | "bad") => HTMLElement;
  kvTable: (rows: { k: string; v: string }[]) => HTMLElement;
  setOut: (text: string) => void;
}

/** One CSV line → cells, quote-aware. The Description can contain a comma (an element name). */
export function splitCsvLine(line: string, delimiter = ","): string[] {
  const out: string[] = [];
  let cur = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]!;
    if (quoted) {
      if (ch === '"') {
        if (line[i + 1] === '"') { cur += '"'; i++; } else { quoted = false; }
      } else { cur += ch; }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === delimiter) {
      out.push(cur); cur = "";
    } else { cur += ch; }
  }
  out.push(cur);
  return out;
}

export interface ParsedCsv {
  rows: MeasuredShot[];
  /** Lines that carried content and could not be read as a shot. NEVER silently dropped. */
  skipped: number;
  skippedLines: number[];
  /** How the columns were resolved — a named header, or an assumed positional order. */
  basis: "header" | "assumed PENZD" | "assumed PNEZD";
  /** True when the file carried the exporter's Description column, i.e. the GlobalIds. */
  hasDescription: boolean;
}

const NUM = /^-?\d+(\.\d+)?([eE][-+]?\d+)?$/;

/**
 * Parse a total-station points file.
 *
 * **The column order is read from the header when there is one and ASSUMED otherwise, and which of
 * those happened is reported.** PENZD and PNEZD differ only in whether Easting or Northing comes
 * second, so assuming the wrong one swaps every coordinate pair and produces plausible deviations in
 * the wrong direction. `basis` exists so the screen can say which it used, rather than the user
 * discovering it from the numbers.
 *
 * The delimiter is sniffed between comma and tab because `to_penzd_csv` offers both.
 */
export function parseSetoutCsv(text: string, assume: "PENZD" | "PNEZD" = "PENZD"): ParsedCsv {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const first = lines.find((l) => l.trim()) ?? "";
  const delimiter = first.includes("\t") && !first.includes(",") ? "\t" : ",";
  const head = splitCsvLine(first, delimiter).map((c) => c.trim().toLowerCase());
  // A HEADER ROW IS ONE WHOSE COORDINATE CELLS ARE NOT NUMBERS, whatever words it contains.
  //
  // The first draft was `some cell starts with "east"/"north" && not every cell is a number`, and
  // this module's own test killed it: a headerless file whose Description reads "Easting pier"
  // satisfies both halves, so the one real shot in the file was consumed as a header and the parse
  // returned zero rows — a survey silently read as empty, which is the defect this module exists to
  // close, in the line that decides what to read. *A row whose coordinates are numbers is data.*
  const numericAt = (i: number) => NUM.test(head[i] ?? "");
  const named = head.some((c) => c.startsWith("east") || c.startsWith("north"))
    && !numericAt(1) && !numericAt(2) && !numericAt(3);
  const idx = (names: string[], fallback: number) => {
    if (!named) return fallback;
    const i = head.findIndex((c) => names.some((n) => c.startsWith(n)));
    return i < 0 ? fallback : i;
  };
  const order = assume === "PNEZD" ? ["p", "n", "e", "z", "d"] : ["p", "e", "n", "z", "d"];
  const col = {
    p: idx(["point", "number", "pt", "no"], order.indexOf("p")),
    e: idx(["east", "e"], order.indexOf("e")),
    n: idx(["north", "n"], order.indexOf("n")),
    z: idx(["elev", "z", "height"], order.indexOf("z")),
    d: idx(["desc", "note", "code"], order.indexOf("d")),
  };
  const rows: MeasuredShot[] = [];
  const skippedLines: number[] = [];
  lines.forEach((line, i) => {
    if (!line.trim()) return;                       // a blank line is not a dropped shot
    if (named && i === lines.indexOf(first)) return;
    const c = splitCsvLine(line, delimiter);
    const num = (c[col.p] ?? "").trim();
    const desc = (c[col.d] ?? "").trim();
    // AN EMPTY CELL IS NOT A ZERO, and `Number("")` is `0` — so the obvious spelling of this check
    // read a missing Easting as the survey origin and a line of prose as a shot at (0,0,0). Caught
    // by this module's own tests, which is the only reason it is not shipping: *the
    // empty-versus-absent confusion, inside the parser written to stop a survey file being read
    // halfway.* `coord` returns NaN for an absent cell so the finite check can refuse it.
    const coord = (raw: string | undefined) => {
      const t = (raw ?? "").trim();
      return t === "" ? Number.NaN : Number(t);
    };
    const e = coord(c[col.e]);
    const n = coord(c[col.n]);
    const z = coord(c[col.z]);
    // A shot needs a key and three finite coordinates. Anything else is COUNTED, because a survey
    // file read halfway that reports no deviations is the defect this module exists to close.
    if ((!num && !desc) || ![e, n, z].every((v) => Number.isFinite(v))) {
      skippedLines.push(i + 1);
      return;
    }
    rows.push(desc ? { number: num, e, n, z, description: desc } : { number: num, e, n, z });
  });
  return {
    rows, skipped: skippedLines.length, skippedLines: skippedLines.slice(0, 20),
    basis: named ? "header" : (assume === "PNEZD" ? "assumed PNEZD" : "assumed PENZD"),
    hasDescription: rows.some((r) => !!r.description),
  };
}

export interface VerifyReading {
  kind: "unmatched" | "partial" | "complete";
  headline: string;
  detail: string;
  tone: "ok" | "warn" | "bad" | "";
}

/**
 * What the verify result means, coverage FIRST.
 *
 * `comparable === false` is answered before anything about tolerance, because that is the state the
 * engine could not distinguish from a clean as-built until this week. A positional match is called
 * out even when everything is in tolerance: the comparison happened, and it happened against a key
 * that is only valid for one export.
 */
export function verifyReading(v: LayoutVerify, parsed?: ParsedCsv): VerifyReading {
  const bad = v.out_of_tolerance.length;
  const mm = (m: number) => `${Math.round(m * 1000)} mm`;
  if (!v.comparable) {
    return {
      kind: "unmatched", tone: "bad",
      headline: `NOTHING MATCHED — none of the ${v.shots_supplied} shot(s) line up with any of the`
        + ` ${v.design_points} design point(s).`,
      detail: "This is not a clean as-built: no comparison was made at all. The usual cause is a"
        + " file from a different export or a different level — the Description column carries each"
        + " point's GlobalId, so keep it and the match survives a re-export."
        + (parsed && !parsed.hasDescription
          ? " This file had no Description column, so only the point numbers were available to"
            + " match on, and those are assigned per export." : ""),
    };
  }
  const posn = v.matched_on_number
    ? ` ${v.matched_on_number} matched by point number only, which is a position in one export`
      + " rather than an element."
    : "";
  const head = bad
    ? `${bad} point(s) out of tolerance — worst ${mm(v.max_deviation_m)} against ${mm(v.tolerance_m)}.`
    : `All ${v.checked} compared point(s) are within ${mm(v.tolerance_m)}.`;
  if (v.unshot || v.unmatched_shots) {
    return {
      kind: "partial", tone: bad ? "bad" : "warn",
      headline: head,
      detail: `${v.checked} of ${v.design_points} design point(s) were shot (${v.coverage_pct}%)`
        + `${v.unshot ? `; ${v.unshot} never were` : ""}`
        + `${v.unmatched_shots ? `; ${v.unmatched_shots} supplied shot(s) matched no design point` : ""}.`
        + ` So "${bad ? "out of tolerance" : "within tolerance"}" is a statement about the`
        + ` ${v.checked} that were compared, not about the setout.${posn}`,
    };
  }
  return {
    kind: "complete", tone: bad ? "bad" : "ok",
    headline: head,
    detail: `Every one of the ${v.design_points} design point(s) was shot and matched.${posn}`,
  };
}

/** The supporting counts — both sides of the join, so neither can hide. */
export function verifyRows(v: LayoutVerify, parsed?: ParsedCsv): { k: string; v: string }[] {
  const rows = [
    { k: "Design setout points", v: String(v.design_points) },
    { k: "Shots supplied", v: String(v.shots_supplied) },
    { k: "Compared", v: `${v.checked} (${v.coverage_pct}%)` },
    { k: "Matched by GlobalId", v: String(v.matched_on_guid) },
    { k: "Matched by number only", v: String(v.matched_on_number) },
    { k: "Design points never shot", v: String(v.unshot) },
    { k: "Shots matching no point", v: String(v.unmatched_shots) },
    { k: "Within tolerance", v: `${v.in_tolerance} of ${v.checked}` },
  ];
  if (parsed) {
    rows.splice(2, 0, { k: "Columns read from", v: parsed.basis });
    if (parsed.skipped) {
      rows.splice(3, 0, { k: "File lines unreadable",
                          v: `${parsed.skipped} (line ${parsed.skippedLines.join(", ")})` });
    }
  }
  return rows;
}

/**
 * The rail button: export the setout, and verify a survey against it.
 *
 * Named `*Button` and the handler is inlined into the append below, because
 * `apps/web/src/viewer/tools/sectionButtonsWired.test.ts` derives its population from that shape.
 */
export function layoutButton(d: LayoutDeps): HTMLButtonElement {
  return d.toolBtn2("📍 Field layout (points CSV / DXF · verify as-built)", () =>
    d.withLoading(d.container, "Extracting layout setout points", async () => {
      let r: LayoutPoints;
      try { r = await d.api.layoutPoints(d.pid); }
      catch { d.toast("Field layout needs a source IFC with columns/grids", "error"); return; }
      d.setOut(`${r.count} setout points`);
      d.toast(r.count ? `${r.count} layout points ready to stake` : "no setout points found",
              r.count ? "info" : "success");
      d.showResult("Model → field layout", (body) => {
        body.appendChild(d.resultNote(`<b>${r.count}</b> georeferenced setout points (grids + column/`
          + "footing/opening/wall) — E/N/Z with the IFC GlobalId in each Description, ready for total "
          + "stations, marking robots and floor printers.", r.count ? "ok" : "bad"));
        if (Object.keys(r.by_class).length) {
          body.appendChild(d.kvTable(Object.entries(r.by_class)
            .map(([k, v]) => ({ k: k.replace("Ifc", ""), v: String(v) }))));
        }
        const dl = (label: string, href: string) => {
          const a = document.createElement("a");
          a.className = "file-btn"; a.textContent = label; a.href = href;
          a.target = "_blank"; a.rel = "noopener"; a.style.marginRight = "6px";
          return a;
        };
        const row = document.createElement("div"); row.style.margin = "8px 0";
        row.append(dl("⬇ PENZD CSV", d.api.layoutCsvUrl(d.pid, "PENZD")),
                   dl("⬇ PNEZD CSV", d.api.layoutCsvUrl(d.pid, "PNEZD")),
                   dl("⬇ DXF (printers)", d.api.layoutDxfUrl(d.pid)));
        body.appendChild(row);
        body.appendChild(d.resultNote("Field round-trip: stake or print these, shoot the as-installed "
          + "positions with a total station, then upload that file below. <b>Keep the Description "
          + "column</b> — it carries each point's GlobalId, which is what makes the match survive a "
          + "re-export.", "ok"));
        // THE UPLOAD, which the sentence above has promised since the panel shipped.
        const pick = document.createElement("input");
        pick.type = "file"; pick.accept = ".csv,.txt,text/csv"; pick.style.marginTop = "6px";
        pick.setAttribute("aria-label", "As-installed survey points file");
        const outBox = document.createElement("div"); outBox.style.marginTop = "6px";
        pick.onchange = async () => {
          const file = pick.files?.[0];
          if (!file) return;
          outBox.replaceChildren();
          const parsed = parseSetoutCsv(await file.text());
          if (!parsed.rows.length) {
            outBox.appendChild(d.resultNote(`Could not read a single shot from ${esc(file.name)} — `
              + `${parsed.skipped} line(s) were unreadable. Expected Point, Easting, Northing, `
              + "Elevation and Description columns.", "bad"));
            return;
          }
          let v: LayoutVerify;
          try { v = await d.api.layoutVerify(d.pid, parsed.rows); }
          catch (e) { outBox.appendChild(d.resultNote(esc((e as Error).message), "bad")); return; }
          const read = verifyReading(v, parsed);
          outBox.appendChild(d.resultNote(`<b>${esc(read.headline)}</b>`, read.tone));
          outBox.appendChild(d.resultNote(esc(read.detail), ""));
          outBox.appendChild(d.kvTable(verifyRows(v, parsed)));
          d.setOut(read.kind === "unmatched" ? "survey matched nothing"
                                             : `${v.out_of_tolerance.length} out of tolerance`);
        };
        body.append(pick, outBox);
      });
    }));
}
