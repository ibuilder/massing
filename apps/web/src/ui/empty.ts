/**
 * Demo-aware "no project" empty states. The GitHub Pages build (`VITE_PAGES`) is **viewer-only** —
 * there's no backend, so the GC portal / drawings / finance can't load records there. Saying "pick a
 * project" is misleading in that build (there are none); instead we explain it's the viewer demo and
 * point at what *does* work (3D samples via Open ▾) + the full app. In the real app (backend present)
 * we give an actionable "create or open a project" hint.
 */
const IS_DEMO = !!import.meta.env.VITE_PAGES;
const DOWNLOAD = "https://massing.build/#download";

/** HTML for a "no project open" panel, tailored to demo vs full app. `tool` names the feature
 *  (e.g. "the GC portal", "drawings") so the copy reads naturally. */
export function noProjectHtml(tool: string): string {
  if (IS_DEMO) {
    return `<div class="empty-state">${tool} runs in the full app`
      + `<span class="es-hint">This is the <b>viewer-only web demo</b> — open a 3D sample from `
      + `<b>Open&nbsp;▾</b> to explore a model. ${tool[0].toUpperCase() + tool.slice(1)}, with live `
      + `records, runs in the free desktop app or a self-hosted stack.</span>`
      + `<a class="ref-link" href="${DOWNLOAD}" target="_blank" rel="noopener">Get the app →</a></div>`;
  }
  return `<div class="empty-state">No project open`
    + `<span class="es-hint">Create one with <b>＋ New</b> in the top bar (or pick an existing `
    + `project), then ${tool} loads here.</span></div>`;
}
