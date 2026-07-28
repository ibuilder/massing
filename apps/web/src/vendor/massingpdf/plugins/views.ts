/**
 * Saved views and split view.
 *
 * Two navigation features the spec asks for that are easy to skip and immediately missed. A saved
 * view is how a reviewer says "here is the condition I'm talking about" — a page, a zoom, a
 * position, and the markup filter that was active — so a colleague opening it sees the same thing
 * rather than a sheet and a hunt.
 *
 * Split view puts two sheets side by side, which is the actual shape of most coordination work:
 * a plan against its detail, a drawing against its spec section, this revision against the last.
 */
import { definePlugin } from "../core/plugin";
import { activate, refreshRovingTabstops, rovingFocus } from "../core/a11y";
import { Viewer } from "../core/viewer";
import type { SavedView } from "../core/types";

export interface ViewsOptions {
  promptText?: (title: string, initial?: string) => Promise<string | null>;
  side?: "left" | "right";
  /** Allow the split pane. */
  split?: boolean;
}

export function viewsPlugin(options: ViewsOptions = {}) {
  const ask = options.promptText ?? (async (t: string, i = "") => globalThis.prompt?.(t, i) ?? null);

  return definePlugin({
    id: "views",
    order: 58,
    setup(ctx) {
      let split: SplitPane | null = null;
      ctx.onCleanup(() => split?.destroy());

      ctx.registerAction({
        id: "views.save", label: "Save this view", icon: "★", group: "view",
        enabled: (v) => Boolean(v.doc),
        async run(v) {
          const sheet = v.store.sheet(v.page);
          const suggested = sheet?.number ? `${sheet.number} — ` : "";
          const name = await ask("Name this view", suggested);
          if (!name?.trim()) return;
          v.store.addView({
            name: name.trim(),
            page: v.page,
            zoom: v.zoom,
            center: centreOf(v),
            rotation: v.rotation,
            author: v.author,
            filter: v.store.getFilter(),
          });
          v.bus.emit("notice", { level: "success", message: `Saved “${name.trim()}”.` });
        },
      });

      if (options.split !== false) {
        ctx.registerAction({
          id: "views.split", label: "Split view", icon: "⊟", group: "view",
          enabled: (v) => Boolean(v.doc),
          async run(v) {
            if (split) { split.destroy(); split = null; return; }
            try {
              split = await openSplit(v);
            } catch (e) {
              v.bus.emit("notice", { level: "error", message: `Split view failed: ${(e as Error).message}` });
            }
          },
        });
      }

      ctx.registerPanel({
        id: "views", title: "Saved views", side: options.side ?? "right", order: 45,
        mount: (host, v) => mountViews(host, v),
      });
    },
  });
}

/** Where the viewport is centred, in page space. */
function centreOf(v: Viewer): { x: number; y: number } {
  const s = v.el.scroll;
  const wrap = v.el.pages.querySelector<HTMLElement>(`.mpdf-page-wrap[data-page="${v.page}"]`);
  if (!wrap) return { x: 0, y: 0 };
  return {
    x: (s.scrollLeft + s.clientWidth / 2 - wrap.offsetLeft) / v.zoom,
    y: (s.scrollTop + s.clientHeight / 2 - wrap.offsetTop) / v.zoom,
  };
}

/** Restore a saved view: page, rotation, zoom, position, and the filter that was active. */
export async function applyView(v: Viewer, view: SavedView): Promise<void> {
  if (view.rotation !== v.rotation) await v.rotate(view.rotation - v.rotation);
  await v.goToPage(view.page);
  await v.setZoom(view.zoom);
  if (view.filter) v.store.setFilter(view.filter);

  const wrap = v.el.pages.querySelector<HTMLElement>(`.mpdf-page-wrap[data-page="${view.page}"]`);
  if (!wrap) return;
  const s = v.el.scroll;
  s.scrollLeft = wrap.offsetLeft + view.center.x * v.zoom - s.clientWidth / 2;
  s.scrollTop = wrap.offsetTop + view.center.y * v.zoom - s.clientHeight / 2;
}

function mountViews(host: HTMLElement, v: Viewer): () => void {
  const list = document.createElement("div");
  list.setAttribute("role", "list");
  list.setAttribute("aria-label", "Saved views");
  list.className = "mpdf-list";
  host.appendChild(list);

  const render = () => {
    const views = v.store.savedViews();
    list.innerHTML = "";
    queueMicrotask(() => refreshRovingTabstops(list, '[role="button"]'));
    if (!views.length) {
      const p = document.createElement("p");
      p.className = "mpdf-empty";
      p.textContent = "No saved views. Save one to return to a sheet at the same zoom, position and filter — or to hand a colleague the exact condition you mean.";
      list.appendChild(p);
      return;
    }
    for (const view of views) {
      const row = document.createElement("article");
      row.className = "mpdf-row";

      const main = document.createElement("div");
      main.className = "mpdf-row-main";
      const title = document.createElement("div");
      title.className = "mpdf-row-title";
      title.textContent = view.name;
      const meta = document.createElement("div");
      meta.className = "mpdf-row-meta";
      meta.textContent = [
        v.store.sheet(view.page)?.number ?? `p.${view.page}`,
        `${Math.round(view.zoom * 100)}%`,
        view.rotation ? `${view.rotation}°` : null,
        view.author,
      ].filter(Boolean).join(" · ");
      main.append(title, meta);

      const del = document.createElement("button");
      del.type = "button";
      del.className = "mpdf-icon-btn";
      del.textContent = "✕";
      del.title = "Delete this view";
      del.onclick = (e) => { e.stopPropagation(); v.store.removeView(view.id); render(); };

      row.append(main, del);
      activate(row, () => void applyView(v, view), { label: `Apply saved view ${view.name}`, roving: true });
      list.appendChild(row);
    }
  };

  const offs = [v.on("view:saved", render), v.on("doc:loaded", render)];
  render();
  const stopRoving = rovingFocus(list, '[role="button"]');
  return () => { offs.forEach((off) => off()); stopRoving(); };
}

// ---- split view ------------------------------------------------------------

interface SplitPane { destroy(): void }

/**
 * A second, read-only viewer beside the first.
 *
 * Read-only on purpose: two editable panes over one markup store raises questions about which pane
 * owns a gesture that are not worth answering for a comparison surface. It shares the store, so
 * markups made on the left appear on the right immediately.
 */
async function openSplit(primary: Viewer): Promise<SplitPane> {
  const body = primary.el.body;
  const host = document.createElement("div");
  host.className = "mpdf-split";

  const bar = document.createElement("div");
  bar.className = "mpdf-split-bar";
  const label = document.createElement("span");
  label.className = "mpdf-split-label";
  const pageInput = document.createElement("input");
  pageInput.type = "number";
  pageInput.className = "mpdf-page-input";
  pageInput.min = "1";
  pageInput.max = String(primary.numPages);
  pageInput.value = String(Math.min(primary.page + 1, primary.numPages));
  const close = document.createElement("button");
  close.type = "button";
  close.className = "mpdf-icon-btn";
  close.textContent = "✕";
  close.title = "Close split view";
  bar.append(label, pageInput, close);

  const mount = document.createElement("div");
  mount.className = "mpdf-split-body";
  host.append(bar, mount);
  body.appendChild(host);

  // The pdf.js worker is already configured — the primary viewer could not have loaded otherwise.
  if (!primary.doc) throw new Error("no document open");

  const secondary = new Viewer({
    container: mount,
    readOnly: true,
    textLayer: false,
    initialZoom: "fit-page",
    author: primary.author,
  });
  // Same bytes, a separate pdf.js document: two viewers must not share a page proxy, because each
  // drives its own render queue and cancelling one would cancel the other's tiles.
  await secondary.load({ url: URL.createObjectURL(new Blob([primary.doc.bytes.slice(0) as BlobPart], { type: "application/pdf" })), name: primary.doc.name });
  await secondary.goToPage(Number(pageInput.value));

  const syncLabel = () => {
    const meta = primary.store.sheet(secondary.page);
    label.textContent = meta?.number ? `${meta.number} — ${meta.title ?? ""}`.trim() : `Page ${secondary.page}`;
  };
  syncLabel();

  pageInput.onchange = () => void secondary.goToPage(Number(pageInput.value)).then(syncLabel);
  const offPage = secondary.on("page:changed", () => { pageInput.value = String(secondary.page); syncLabel(); });

  // Mirror markups into the second pane so both sides show the same review state.
  const mirror = () => { secondary.store.reset(primary.store.all(), { undoable: false }); secondary.redraw(); };
  const offs = [
    primary.on("annot:added", mirror), primary.on("annot:updated", mirror),
    primary.on("annot:removed", mirror), primary.on("annot:reset", mirror),
  ];
  mirror();

  const destroy = () => {
    offPage();
    offs.forEach((off) => off());
    secondary.destroy();
    host.remove();
  };
  close.onclick = destroy;
  return { destroy };
}
