import type { ModuleDef } from "../api/client";
import type { PortalHost } from "./portal";

/**
 * The slice of `PortalUI` that a feature panel needs. Panels are extracted from portal.ts into
 * portal/panels/* as free `render*(ctx)` functions; PortalUI builds a `PanelContext` (see
 * `panelCtx()`) that forwards to its own state/methods, so the panels stay decoupled from the
 * class internals. This is the same "extract cohesive features into their own files" idiom the
 * viewer uses (gis.ts, solar.ts, …).
 */
export interface PanelContext {
  /** The portal content pane every panel renders into. */
  readonly root: HTMLElement;
  /** Host bridge (api, projectId, selection, status…). */
  readonly host: PortalHost;
  /** Loaded module definitions. */
  readonly mods: ModuleDef[];
  /** Currently-open nav key; panels set it when they take over / clear it on back. */
  activeKey: string | null;
  /** The panel header bar (title + back button). */
  bar(title: string, back: () => void): HTMLElement;
  /** Rebuild the left nav rail (call after activeKey changes). */
  buildNav(): void;
  /** Return to the portal dashboard. */
  renderHome(): Promise<void>;
  /** Open a module's list/CRUD view in the content pane. */
  openModule(m: ModuleDef, filter?: { q?: string; state?: string; offset?: number }): Promise<void>;
  /** Jump to a first-class portal destination by its `__key__` (SPRINT MB deep-links). */
  navigate(key: string): void;
}
