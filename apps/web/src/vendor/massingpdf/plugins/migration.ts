/**
 * Slip-sheet markup migration.
 *
 * When a sheet is re-issued, the markups on it are the most valuable thing on the page and the
 * thing every viewer loses. Carrying them forward blindly is worse than losing them — a comment
 * that says "verify this dimension" sitting on top of a dimension that has since changed is
 * actively misleading.
 *
 * So migration is a three-way decision per markup, not a copy: the geometry still matches (`ok`),
 * it moved with the sheet and was relocated (`shifted`), the drawing under it changed and a human
 * must look (`orphan`), or the content it referenced is gone (`obsolete`). Everything lands in a
 * review queue with an audit trail rather than being silently applied.
 */
import { definePlugin } from "../core/plugin";
import { activate } from "../core/a11y";
import { comparePages, type CompareResult } from "./compare";
import { PdfDocument, type PdfSource } from "../core/document";
import { bbox, boxesOverlap } from "../core/geometry";
import type { Annotation, Box, Pt } from "../core/types";
import type { Viewer } from "../core/viewer";

export type MigrationVerdict = "ok" | "shifted" | "orphan" | "obsolete";

export interface MigrationProposal {
  annot: Annotation;
  verdict: MigrationVerdict;
  /** Translation applied, in page points — after `scale`. */
  offset: { x: number; y: number };
  /** Uniform scale applied about the page origin, for a sheet re-plotted to another size. */
  scale: number;
  /** Why the verdict — shown in the queue so a reviewer isn't guessing. */
  reason: string;
  /** How much of the markup's footprint overlaps a detected change, 0..1. */
  changeOverlap: number;
}

export interface MigrationOptions {
  /** Load the incoming (new) revision. Defaults to a file picker. */
  loadRevision?: (viewer: Viewer) => Promise<PdfSource | null>;
  /** Above this fraction of overlap with a changed region, a markup is flagged rather than moved. */
  orphanThreshold?: number;
  /** New revision label stamped onto migrated markups. */
  revision?: string;
}

/**
 * Decide what happens to each markup, given the alignment and change regions from a compare.
 *
 * `previous` here is the sheet the markups were drawn on; `result` describes the *new* sheet
 * relative to it, so the offset moves a markup from old coordinates into new ones.
 */
export function planMigration(
  annots: readonly Annotation[],
  result: CompareResult,
  page: number,
  orphanThreshold = 0.25,
): MigrationProposal[] {
  // Compare aligns the previous sheet onto the current one as `scale` then shift, so a point P on
  // the old sheet lands at `P * scale − result.offset` on the new one. `|| 0` normalises the `-0`
  // that negating a zero produces, which would otherwise reach stored records and every export.
  const scale = result.scale || 1;
  const offset = { x: -result.offset.x || 0, y: -result.offset.y || 0 };
  const moved = Math.hypot(offset.x, offset.y) > 0.5 || Math.abs(scale - 1) > 1e-4;

  return annots.filter((a) => a.page === page).map((annot) => {
    // Overlap is measured against where the markup *will land*, not where it currently is.
    const landing = bbox(migrate(annot.points, scale, offset));
    const overlap = changeOverlap(landing, result.regions);

    let verdict: MigrationVerdict;
    let reason: string;
    if (overlap >= orphanThreshold) {
      verdict = "orphan";
      reason = `${Math.round(overlap * 100)}% of this markup sits over drawing that changed — re-place or re-word it.`;
    } else if (moved) {
      verdict = "shifted";
      reason = Math.abs(scale - 1) > 1e-4
        ? `Sheet re-plotted at ${(scale * 100).toFixed(1)}% and offset ${offset.x.toFixed(1)}, ${offset.y.toFixed(1)} pt; markup rescaled and relocated to match.`
        : `Sheet origin moved ${offset.x.toFixed(1)}, ${offset.y.toFixed(1)} pt; markup relocated to match.`;
    } else {
      verdict = "ok";
      reason = "Drawing underneath is unchanged.";
    }
    return { annot, verdict, offset, scale, reason, changeOverlap: overlap };
  });
}

/** Apply the alignment to a markup's geometry: scale about the page origin, then translate. */
export function migrate(points: readonly Pt[], scale: number, offset: { x: number; y: number }): Pt[] {
  return points.map((p) => ({ x: p.x * scale + offset.x, y: p.y * scale + offset.y }));
}

/** What fraction of a markup's footprint intersects a changed region. */
function changeOverlap(box: Box, regions: readonly Box[]): number {
  const area = box.w * box.h;
  // A pin or a count has no area, so an intersection with it also has none — computing a ratio
  // would always yield zero and quietly wave every point markup through. Containment is the right
  // question for these: is the thing it points at inside a region that changed?
  if (area < 4) return regions.some((r) => boxesOverlap(box, r)) ? 1 : 0;

  let covered = 0;
  for (const r of regions) {
    if (!boxesOverlap(box, r)) continue;
    const w = Math.min(box.x + box.w, r.x + r.w) - Math.max(box.x, r.x);
    const h = Math.min(box.y + box.h, r.y + r.h) - Math.max(box.y, r.y);
    if (w > 0 && h > 0) covered += w * h;
  }
  return Math.min(1, covered / area);
}

export function migrationPlugin(options: MigrationOptions = {}) {
  return definePlugin({
    id: "migration",
    order: 65,
    setup(ctx) {
      let proposals: MigrationProposal[] = [];
      let incoming: PdfDocument | null = null;
      let notify: (() => void) | null = null;

      ctx.onCleanup(() => incoming?.destroy());

      const analyse = async (v: Viewer): Promise<void> => {
        const src = options.loadRevision ? await options.loadRevision(v) : await pickFile();
        if (!src) return;
        if (!v.doc) {
          v.bus.emit("notice", { level: "error", message: "Open the current sheet first." });
          return;
        }
        v.bus.emit("notice", { level: "info", message: "Comparing revisions…" });
        try {
          incoming?.destroy();
          incoming = await PdfDocument.load(src);
          await incoming.primeInfo();

          // The open document holds the markups (the old revision); `incoming` is the new sheet.
          const page = v.page;
          const result = await comparePages(incoming, v.doc, Math.min(page, incoming.numPages), page);
          proposals = planMigration(v.store.all(), result, page, options.orphanThreshold ?? 0.25);

          const counts = tally(proposals);
          v.bus.emit("notice", {
            level: counts.orphan ? "warn" : "success",
            message: `${proposals.length} markups: ${counts.ok} unchanged, ${counts.shifted} relocated, ${counts.orphan} need review.`,
          });
          notify?.();
        } catch (e) {
          v.bus.emit("notice", { level: "error", message: `Migration failed: ${(e as Error).message}` });
        }
      };

      ctx.registerAction({
        id: "migration.analyse", label: "Slip-sheet: compare and plan", icon: "⇄", group: "compare",
        run: analyse,
      });

      /** Swap the document for the new revision and carry the accepted markups across. */
      ctx.registerAction({
        id: "migration.apply", label: "Apply migration", icon: "✓", group: "compare",
        enabled: () => proposals.length > 0 && incoming !== null,
        async run(v) {
          if (!incoming || !proposals.length) return;
          const accepted = proposals.filter((p) => p.verdict !== "obsolete");
          const rev = options.revision;
          const priorRev = v.store.sheet(v.page)?.revision;

          // Load the new sheet, keeping the markups, then relocate them in place.
          const bytes = incoming.bytes.slice(0);
          const name = incoming.name;
          await v.load({ url: URL.createObjectURL(new Blob([bytes as BlobPart], { type: "application/pdf" })), name }, { keepMarkups: true });

          v.store.updateMany(accepted.map((p) => ({
            id: p.annot.id,
            patch: {
              points: p.verdict === "shifted" ? migrate(p.annot.points, p.scale, p.offset) : p.annot.points,
              // An orphan keeps its geometry but is forced back into review — it must not read as
              // an accepted comment on a drawing that moved underneath it.
              ...(p.verdict === "orphan" ? { status: "in_review" as const } : {}),
              revision: {
                ...p.annot.revision,
                ...(rev ? { rev } : {}),
                ...(priorRev ? { carriedFrom: priorRev } : {}),
                migration: p.verdict,
                migratedBy: v.author,
                migratedAt: new Date().toISOString(),
              },
            },
          })));

          const counts = tally(proposals);
          v.bus.emit("notice", {
            level: "success",
            message: `Carried ${accepted.length} markups onto ${name}. ${counts.orphan} flagged for review.`,
          });
          proposals = [];
          notify?.();
          v.redraw();
        },
      });

      ctx.registerAction({
        id: "migration.discard", label: "Discard migration plan", icon: "✕", group: "compare",
        enabled: () => proposals.length > 0,
        run(v) { proposals = []; notify?.(); v.redraw(); },
      });

      ctx.registerPanel({
        id: "migration", title: "Slip-sheet review", side: "right", order: 15,
        mount: (host, v) => {
          const dispose = mountQueue(host, v, () => proposals, analyse);
          notify = dispose.refresh;
          return () => { notify = null; dispose.off(); };
        },
      });

      ctx.viewer.migration = {
        proposals: () => proposals,
        analyse: (v: Viewer) => analyse(v),
      };
    },
  });
}

const tally = (list: readonly MigrationProposal[]) => ({
  ok: list.filter((p) => p.verdict === "ok").length,
  shifted: list.filter((p) => p.verdict === "shifted").length,
  orphan: list.filter((p) => p.verdict === "orphan").length,
  obsolete: list.filter((p) => p.verdict === "obsolete").length,
});

const VERDICT_COLOR: Record<MigrationVerdict, string> = {
  ok: "#33d17a", shifted: "#4a8cff", orphan: "#d8a200", obsolete: "#5c6670",
};

function mountQueue(
  host: HTMLElement,
  v: Viewer,
  get: () => MigrationProposal[],
  analyse: (v: Viewer) => Promise<void>,
): { off: () => void; refresh: () => void } {
  const summary = document.createElement("div");
  summary.className = "mpdf-list-summary";
  const list = document.createElement("div");
  list.className = "mpdf-list";
  host.append(summary, list);

  const render = () => {
    const proposals = get();
    list.innerHTML = "";
    if (!proposals.length) {
      summary.textContent = "";
      const p = document.createElement("p");
      p.className = "mpdf-empty";
      p.textContent = "Compare this sheet against its new revision to see which markups carry forward, which moved, and which need re-placing.";
      const b = document.createElement("button");
      b.type = "button";
      b.className = "mpdf-chest-tool";
      b.textContent = "Load the new revision…";
      b.onclick = () => void analyse(v);
      list.append(p, b);
      return;
    }

    const counts = tally(proposals);
    summary.textContent = `${counts.ok} unchanged · ${counts.shifted} relocated · ${counts.orphan} need review`;

    // Orphans first — they are the only ones that need a decision.
    const order: MigrationVerdict[] = ["orphan", "shifted", "ok", "obsolete"];
    for (const p of [...proposals].sort((a, b) => order.indexOf(a.verdict) - order.indexOf(b.verdict))) {
      const row = document.createElement("article");
      row.className = "mpdf-row";

      const swatch = document.createElement("span");
      swatch.className = "mpdf-row-swatch";
      swatch.style.background = VERDICT_COLOR[p.verdict];
      swatch.title = p.verdict;

      const main = document.createElement("div");
      main.className = "mpdf-row-main";
      const title = document.createElement("div");
      title.className = "mpdf-row-title";
      title.textContent = p.annot.subject || p.annot.text || p.annot.note || p.annot.kind;
      const meta = document.createElement("div");
      meta.className = "mpdf-row-meta";
      meta.textContent = `${p.verdict} · ${p.annot.kind} · p.${p.annot.page}`;
      const why = document.createElement("div");
      why.className = "mpdf-row-note";
      why.textContent = p.reason;
      main.append(title, meta, why);

      const tools = document.createElement("div");
      tools.className = "mpdf-issue-tools";
      const drop = document.createElement("button");
      drop.type = "button";
      drop.className = "mpdf-icon-btn";
      drop.textContent = "✕";
      drop.title = "Mark obsolete — do not carry this markup forward";
      drop.onclick = (e) => {
        e.stopPropagation();
        p.verdict = "obsolete";
        render();
      };
      tools.appendChild(drop);

      row.append(swatch, main, tools);
      activate(row, () => {
        v.store.select(p.annot.id);
        void v.goToAnnotation(p.annot, { zoom: false });
      }, {
        // Every row had the same constant label, which both hid the title and reason and made the
        // list a run of identical announcements.
        label: `${p.annot.kind} on page ${p.annot.page}${p.annot.subject ? `: ${p.annot.subject}` : ""} — ${p.reason}`,
        roving: true,
      });
      list.appendChild(row);
    }
  };

  render();
  const offs = [v.on("annot:reset", render), v.on("doc:loaded", render)];
  return { off: () => offs.forEach((o) => o()), refresh: render };
}

function pickFile(): Promise<File | null> {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".pdf,application/pdf";
    input.onchange = () => resolve(input.files?.[0] ?? null);
    input.oncancel = () => resolve(null);
    input.click();
  });
}

declare module "../core/viewer" {
  interface Viewer {
    /** Present once the migration plugin is installed. */
    migration?: {
      proposals(): MigrationProposal[];
      analyse(viewer: Viewer): Promise<void>;
    };
  }
}
