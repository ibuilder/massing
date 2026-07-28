/**
 * Historical and preservation mode.
 *
 * Archival drawings are treated as first-class here rather than as an awkward edge case, because
 * the work they support — restoration, adaptive reuse, measured survey, heritage documentation —
 * has the same shape as construction review but different truth conditions.
 *
 * The load-bearing idea is *uncertainty*. A dimension read off a medium-resolution scan of a
 * century-old drawing is not the same claim as one read off a CAD export, and a system that records
 * both identically is quietly lying. So markups here carry a confidence tag, and the ones that are
 * uncertain look uncertain on the sheet.
 */
import { definePlugin } from "../core/plugin";
import type { Provenance } from "../core/types";
import type { Viewer } from "../core/viewer";

export type Confidence = NonNullable<Provenance["confidence"]>;

export const CONFIDENCE_LEVELS: Confidence[] = ["certain", "probable", "uncertain", "illegible"];

/** How each confidence level reads on the sheet: less certain, more broken up. */
const CONFIDENCE_DASH: Record<Confidence, number[] | undefined> = {
  certain: undefined,
  probable: [6, 3],
  uncertain: [3, 3],
  illegible: [1, 3],
};

const CONFIDENCE_OPACITY: Record<Confidence, number> = {
  certain: 1, probable: 0.9, uncertain: 0.75, illegible: 0.55,
};

export interface HistoricalOptions {
  /** Project-wide provenance applied to new markups — archive, collection, scan resolution. */
  defaults?: Provenance;
  promptText?: (title: string, initial?: string) => Promise<string | null>;
  side?: "left" | "right";
}

/** Legibility adjustments applied to the raster. CSS filters — non-destructive and instant. */
export interface ImageAdjustments {
  contrast: number;
  brightness: number;
  invert: boolean;
  grayscale: boolean;
}

const NEUTRAL: ImageAdjustments = { contrast: 1, brightness: 1, invert: false, grayscale: false };

const filterCss = (a: ImageAdjustments): string => {
  const parts: string[] = [];
  if (a.contrast !== 1) parts.push(`contrast(${a.contrast})`);
  if (a.brightness !== 1) parts.push(`brightness(${a.brightness})`);
  if (a.invert) parts.push("invert(1)");
  if (a.grayscale) parts.push("grayscale(1)");
  return parts.join(" ") || "none";
};

export function historicalPlugin(options: HistoricalOptions = {}) {
  const ask = options.promptText ?? (async (t: string, i = "") => globalThis.prompt?.(t, i) ?? null);

  return definePlugin({
    id: "historical",
    order: 70,
    setup(ctx) {
      const adjustments: ImageAdjustments = { ...NEUTRAL };

      const applyFilter = (v: Viewer) => {
        const css = filterCss(adjustments);
        // Applied to the raster only — filtering the markup layer too would wash out the redlines
        // and, with invert on, turn a red cloud cyan.
        for (const page of v.el.pages.querySelectorAll<HTMLElement>(".mpdf-page")) page.style.filter = css;
      };
      // Re-apply after a re-raster, or a freshly painted tile shows up unfiltered.
      ctx.bus.on("page:rendered", () => applyFilter(ctx.viewer));

      // --- legibility -------------------------------------------------------
      ctx.registerAction({
        id: "historical.invert", label: "Invert (read a negative)", icon: "◐", group: "archive",
        run(v) {
          adjustments.invert = !adjustments.invert;
          applyFilter(v);
          v.bus.emit("notice", { level: "info", message: `Invert ${adjustments.invert ? "on" : "off"}.` });
        },
      });
      ctx.registerAction({
        id: "historical.contrast", label: "Boost contrast", icon: "◑", group: "archive",
        run(v) {
          // Cycle rather than prompt: on a faint dyeline you want to try a few settings fast.
          adjustments.contrast = adjustments.contrast >= 2.5 ? 1 : Math.round((adjustments.contrast + 0.5) * 10) / 10;
          applyFilter(v);
          v.bus.emit("notice", { level: "info", message: `Contrast ${adjustments.contrast.toFixed(1)}×` });
        },
      });
      ctx.registerAction({
        id: "historical.reset", label: "Reset image adjustments", icon: "⊘", group: "archive",
        enabled: () => filterCss(adjustments) !== "none",
        run(v) { Object.assign(adjustments, NEUTRAL); applyFilter(v); },
      });

      // --- uncertainty ------------------------------------------------------
      ctx.registerAction({
        id: "historical.confidence", label: "Set confidence", icon: "?", group: "archive",
        enabled: (v) => v.store.selectedIds().length > 0,
        async run(v) {
          const answer = await ask(
            `Confidence\n\n${CONFIDENCE_LEVELS.map((c, i) => `${i + 1}. ${c}`).join("\n")}`, "1",
          );
          if (!answer) return;
          const n = Number(answer.trim());
          const level = (Number.isInteger(n) && CONFIDENCE_LEVELS[n - 1])
            || CONFIDENCE_LEVELS.find((c) => c === answer.trim().toLowerCase());
          if (!level) return;
          v.store.updateMany(v.store.selected().map((a) => ({
            id: a.id,
            patch: {
              provenance: { ...options.defaults, ...a.provenance, confidence: level },
              // The style change is the point: an uncertain reading must not look like a fact.
              style: { ...a.style, opacity: CONFIDENCE_OPACITY[level], dash: CONFIDENCE_DASH[level] },
            },
          })));
          v.bus.emit("notice", { level: "success", message: `Marked ${level}.` });
        },
      });

      ctx.registerAction({
        id: "historical.transcribe", label: "Transcribe handwriting", icon: "✍", group: "archive",
        enabled: (v) => v.store.selectedIds().length === 1,
        async run(v) {
          const [a] = v.store.selected();
          if (!a) return;
          const existing = a.provenance?.transcript ?? "";
          const text = await ask("Transcription of the handwritten note", existing);
          if (text === null) return;
          v.store.update(a.id, {
            provenance: { ...options.defaults, ...a.provenance, transcript: text.trim() || undefined },
          });
        },
      });

      // New markups inherit the project's provenance defaults, so an archive package doesn't need
      // the fields re-entered on every note.
      if (options.defaults) {
        ctx.bus.on("annot:added", ({ annot }) => {
          if (annot.provenance) return;
          ctx.store.update(annot.id, { provenance: { ...options.defaults } }, { undoable: false });
        });
      }

      // --- tracing overlay ---------------------------------------------------
      let tracing: TracingOverlay | null = null;
      ctx.onCleanup(() => tracing?.destroy());

      ctx.registerAction({
        id: "historical.trace", label: "Tracing overlay", icon: "⧉", group: "archive",
        enabled: (v) => Boolean(v.doc),
        async run(v) {
          if (tracing) { tracing.destroy(); tracing = null; return; }
          const file = await pickImage();
          if (!file) return;
          try {
            tracing = mountTracing(v, file);
          } catch (e) {
            v.bus.emit("notice", { level: "error", message: `Tracing overlay failed: ${(e as Error).message}` });
          }
        },
      });

      ctx.registerPanel({
        id: "provenance", title: "Provenance", side: options.side ?? "right", order: 40,
        mount: (host, v) => mountProvenance(host, v, ask, options),
      });

      ctx.viewer.historical = {
        adjustments: () => ({ ...adjustments }),
        setAdjustments(next) {
          Object.assign(adjustments, next);
          applyFilter(ctx.viewer);
        },
      };
    },
  });
}

/** Provenance for the selected markup, plus the transcription panel. */
function mountProvenance(
  host: HTMLElement,
  v: Viewer,
  ask: (title: string, initial?: string) => Promise<string | null>,
  options: HistoricalOptions,
): () => void {
  const body = document.createElement("div");
  body.className = "mpdf-provenance";
  host.appendChild(body);

  const field = (label: string, value: string | undefined, onEdit: (next: string) => void) => {
    const row = document.createElement("div");
    row.className = "mpdf-prov-row";
    const key = document.createElement("span");
    key.className = "mpdf-prov-key";
    key.textContent = label;
    const val = document.createElement("button");
    val.type = "button";
    val.className = "mpdf-prov-val";
    val.textContent = value || "—";
    if (!value) val.classList.add("is-empty");
    val.onclick = async () => {
      const next = await ask(label, value ?? "");
      if (next !== null) onEdit(next.trim());
    };
    row.append(key, val);
    return row;
  };

  const render = () => {
    body.innerHTML = "";
    const selected = v.store.selected();
    if (selected.length !== 1) {
      const p = document.createElement("p");
      p.className = "mpdf-empty";
      p.textContent = selected.length
        ? `${selected.length} markups selected — select one to edit its provenance.`
        : "Select a markup to record where it came from and how certain the reading is.";
      body.appendChild(p);
      return;
    }
    const a = selected[0]!;
    const prov: Provenance = { ...options.defaults, ...a.provenance };
    const patch = (next: Partial<Provenance>) =>
      v.store.update(a.id, { provenance: { ...prov, ...next } });

    body.append(
      field("Archive", prov.archive, (x) => patch({ archive: x || undefined })),
      field("Collection", prov.collection, (x) => patch({ collection: x || undefined })),
      field("Source ref", prov.sourceRef, (x) => patch({ sourceRef: x || undefined })),
      field("Architect", prov.architect, (x) => patch({ architect: x || undefined })),
      field("Drawn", prov.drawnDate, (x) => patch({ drawnDate: x || undefined })),
      field("Scan DPI", prov.scanDpi ? String(prov.scanDpi) : undefined, (x) => {
        const n = Number(x);
        patch({ scanDpi: Number.isFinite(n) && n > 0 ? n : undefined });
      }),
    );

    // Confidence as a chip row — it's the field people actually change.
    const conf = document.createElement("div");
    conf.className = "mpdf-chip-group";
    const label = document.createElement("span");
    label.className = "mpdf-chip-label";
    label.textContent = "Confidence";
    conf.appendChild(label);
    for (const level of CONFIDENCE_LEVELS) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "mpdf-chip" + (prov.confidence === level ? " is-on" : "");
      b.textContent = level;
      b.onclick = () => {
        v.store.update(a.id, {
          provenance: { ...prov, confidence: level },
          style: { ...a.style, opacity: CONFIDENCE_OPACITY[level], dash: CONFIDENCE_DASH[level] },
        });
      };
      conf.appendChild(b);
    }
    body.appendChild(conf);

    if (prov.transcript) {
      const t = document.createElement("blockquote");
      t.className = "mpdf-transcript";
      t.textContent = prov.transcript;
      body.appendChild(t);
    }
  };

  const offs = [
    v.on("annot:selected", render), v.on("annot:updated", render), v.on("annot:reset", render),
  ];
  render();
  return () => offs.forEach((off) => off());
}

// ---- tracing overlay -------------------------------------------------------

interface TracingOverlay { destroy(): void }

/**
 * Lay a scanned original over the current sheet at adjustable opacity, so a redraw can be traced
 * against it.
 *
 * Distinct from compare's difference view, which answers "what changed" between two issues. This
 * answers "does my redraw match the original", which needs the source to stay put and stay
 * translucent while you draw on top of it — so it sits *under* the annotation overlay, ignores
 * pointer events entirely, and is positioned in page space so it tracks zoom and scroll for free.
 */
function mountTracing(v: Viewer, file: File): TracingOverlay {
  const wrap = v.el.pages.querySelector<HTMLElement>(`.mpdf-page-wrap[data-page="${v.page}"]`);
  if (!wrap) throw new Error(`page ${v.page} is not on screen`);

  const url = URL.createObjectURL(file);
  const img = document.createElement("img");
  img.className = "mpdf-tracing";
  img.src = url;
  img.alt = "Tracing source";
  img.style.cssText =
    "position:absolute;inset:0;width:100%;height:100%;object-fit:contain;" +
    "pointer-events:none;z-index:2;opacity:0.5;";
  wrap.appendChild(img);

  const controls = document.createElement("div");
  controls.className = "mpdf-tracing-controls";
  const label = document.createElement("span");
  label.textContent = "Tracing 50%";
  const slider = document.createElement("input");
  slider.type = "range";
  slider.min = "0";
  slider.max = "100";
  slider.value = "50";
  slider.oninput = () => {
    img.style.opacity = String(Number(slider.value) / 100);
    label.textContent = `Tracing ${slider.value}%`;
  };
  const close = document.createElement("button");
  close.type = "button";
  close.className = "mpdf-icon-btn";
  close.textContent = "✕";
  close.title = "Remove the tracing overlay";
  controls.append(label, slider, close);
  v.el.root.appendChild(controls);

  const destroy = () => {
    img.remove();
    controls.remove();
    URL.revokeObjectURL(url);
  };
  close.onclick = destroy;
  return { destroy };
}

function pickImage(): Promise<File | null> {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.onchange = () => resolve(input.files?.[0] ?? null);
    input.oncancel = () => resolve(null);
    input.click();
  });
}

declare module "../core/viewer" {
  interface Viewer {
    /** Present once the historical plugin is installed. */
    historical?: {
      adjustments(): ImageAdjustments;
      setAdjustments(next: Partial<ImageAdjustments>): void;
    };
  }
}
