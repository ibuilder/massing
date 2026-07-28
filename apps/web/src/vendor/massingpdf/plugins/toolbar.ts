/**
 * The default chrome: toolbar, page controls, zoom controls and a status bar.
 *
 * Deliberately a *plugin*. A host that wants its own UI drops this one and drives `viewer.setTool`,
 * `viewer.runAction` and the registries directly — the kernel never assumes this file exists.
 */
import { definePlugin } from "../core/plugin";
import { formatCalibration } from "../core/units";
import type { ActionDef, ToolDef } from "../core/plugin";
import type { Viewer } from "../core/viewer";

export interface ToolbarOptions {
  /** Group order; unknown groups are appended in registration order. */
  groups?: string[];
  /** Show the status bar. */
  status?: boolean;
  /** Render notices as transient banners in the status bar. Off if the host has its own toasts. */
  notices?: boolean;
}

const DEFAULT_GROUPS = ["view", "markup", "measure", "review", "compare", "io"];

export function toolbarPlugin(options: ToolbarOptions = {}) {
  return definePlugin({
    id: "toolbar",
    // Last, so every other plugin's tools and actions are registered before the bar is built.
    order: 900,
    setup(ctx) {
      const { viewer } = ctx;
      const bar = viewer.el.toolbar;

      // --- view controls, owned by the toolbar itself -----------------------
      ctx.registerAction({ id: "view.prev", label: "Previous page", icon: "‹", group: "view", run: (v) => v.goToPage(v.page - 1) });
      ctx.registerAction({ id: "view.next", label: "Next page", icon: "›", group: "view", run: (v) => v.goToPage(v.page + 1) });
      ctx.registerAction({ id: "view.zoomOut", label: "Zoom out", icon: "−", group: "view", run: (v) => v.zoomOut() });
      ctx.registerAction({ id: "view.zoomIn", label: "Zoom in", icon: "+", group: "view", run: (v) => v.zoomIn() });
      ctx.registerAction({ id: "view.fitWidth", label: "Fit width", icon: "↔", group: "view", run: (v) => v.fitWidth() });
      ctx.registerAction({ id: "view.fitPage", label: "Fit page", icon: "⤢", group: "view", run: (v) => v.fitPage() });
      ctx.registerAction({ id: "view.rotate", label: "Rotate", icon: "⟳", group: "view", run: (v) => v.rotate(90) });
      ctx.registerAction({
        id: "view.select", label: "Select", icon: "⬉", group: "view", shortcut: "v",
        run: (v) => v.setTool(null),
      });
      ctx.registerAction({
        id: "edit.undo", label: "Undo", icon: "↶", group: "view",
        enabled: (v) => v.store.canUndo, run: (v) => v.store.undo(),
      });
      ctx.registerAction({
        id: "edit.redo", label: "Redo", icon: "↷", group: "view",
        enabled: (v) => v.store.canRedo, run: (v) => v.store.redo(),
      });
      ctx.registerAction({
        id: "edit.delete", label: "Delete", icon: "🗑", group: "view",
        enabled: (v) => v.store.selectedIds().length > 0,
        run: (v) => { v.store.removeSelected(); },
      });

      const build = () => renderBar(bar, viewer, options);
      // Rebuild on anything that changes a button's state; cheap enough to do wholesale.
      for (const ev of ["tool:changed", "annot:selected", "annot:added", "annot:removed", "annot:reset", "doc:loaded"] as const) {
        ctx.bus.on(ev, build);
      }
      build();

      if (options.status !== false) mountStatus(ctx.viewer, options);
    },
  });
}

function renderBar(bar: HTMLElement, v: Viewer, options: ToolbarOptions): void {
  bar.innerHTML = "";
  const order = options.groups ?? DEFAULT_GROUPS;
  const buckets = new Map<string, (ToolDef | ActionDef)[]>();
  for (const item of [...v.actionList, ...v.toolList]) {
    const g = item.group ?? "markup";
    if (!buckets.has(g)) buckets.set(g, []);
    buckets.get(g)!.push(item);
  }
  const groups = [...order.filter((g) => buckets.has(g)), ...[...buckets.keys()].filter((g) => !order.includes(g))];

  for (const g of groups) {
    const wrap = document.createElement("div");
    wrap.className = "mpdf-tb-group";
    wrap.dataset.group = g;
    wrap.setAttribute("role", "group");
    wrap.setAttribute("aria-label", g);
    for (const item of buckets.get(g)!) {
      const isTool = "input" in item;
      const b = document.createElement("button");
      b.type = "button";
      b.className = "mpdf-tb-btn";
      b.textContent = item.icon ?? item.label;
      b.title = item.shortcut ? `${item.label} (${item.shortcut})` : item.label;
      // The visible label is usually a single glyph, which reads as the emoji's own name or as
      // nothing at all. `title` is not a reliable accessible name; `aria-label` is.
      b.setAttribute("aria-label", item.shortcut ? `${item.label} (shortcut ${item.shortcut})` : item.label);
      b.dataset.id = item.id;
      if (isTool) {
        const armed = v.activeTool?.id === item.id;
        if (armed) b.classList.add("is-active");
        // A tool is a toggle, and "is-active" is a colour change — invisible to a reader.
        b.setAttribute("aria-pressed", String(armed));
        b.onclick = () => v.setTool(v.activeTool?.id === item.id ? null : item.id);
      } else {
        const action = item as ActionDef;
        if (action.enabled && !action.enabled(v)) b.disabled = true;
        b.onclick = () => void v.runAction(action.id);
      }
      wrap.appendChild(b);
    }
    bar.appendChild(wrap);
  }

  // Page indicator, right-aligned.
  const spacer = document.createElement("div");
  spacer.className = "mpdf-tb-spacer";
  bar.appendChild(spacer);

  const pageBox = document.createElement("div");
  pageBox.className = "mpdf-tb-page";
  const input = document.createElement("input");
  input.className = "mpdf-page-input";
  input.type = "number";
  input.min = "1";
  input.max = String(v.numPages || 1);
  input.value = String(v.page);
  input.onchange = () => void v.goToPage(Number(input.value));
  const total = document.createElement("span");
  total.className = "mpdf-tb-total";
  total.textContent = `/ ${v.numPages || 0}`;
  pageBox.append(input, total);
  bar.appendChild(pageBox);

  const off = v.on("page:changed", ({ page }) => { input.value = String(page); });
  // The next rebuild discards this element, so drop the listener with it.
  const observer = new MutationObserver(() => { if (!pageBox.isConnected) { off(); observer.disconnect(); } });
  observer.observe(bar, { childList: true });
}

/** Zoom, scale, selection count, and a transient notice slot. */
function mountStatus(v: Viewer, options: ToolbarOptions): void {
  const bar = v.el.status;
  bar.innerHTML = "";
  const left = document.createElement("div");
  left.className = "mpdf-status-left";
  const right = document.createElement("div");
  right.className = "mpdf-status-right";
  const notice = document.createElement("div");
  notice.className = "mpdf-notice";
  bar.append(left, notice, right);

  const render = () => {
    const cal = v.store.calibration(v.page);
    const sel = v.store.selectedIds().length;
    left.textContent = [
      v.doc?.name,
      `Page ${v.page} of ${v.numPages}`,
      formatCalibration(cal),
    ].filter(Boolean).join("  ·  ");
    right.textContent = [
      sel ? `${sel} selected` : null,
      `${v.store.size} markup${v.store.size === 1 ? "" : "s"}`,
      `${Math.round(v.zoom * 100)}%`,
    ].filter(Boolean).join("  ·  ");
  };

  for (const ev of ["view:changed", "page:changed", "annot:selected", "annot:added", "annot:removed", "annot:reset", "calibration:changed", "doc:loaded"] as const) {
    v.on(ev, render);
  }
  render();

  if (options.notices !== false) {
    let timer: ReturnType<typeof setTimeout> | undefined;
    v.on("notice", ({ level, message }) => {
      notice.textContent = message;
      notice.dataset.level = level;
      notice.classList.add("is-shown");
      clearTimeout(timer);
      timer = setTimeout(() => notice.classList.remove("is-shown"), level === "error" ? 8000 : 4000);
    });
  }
}
