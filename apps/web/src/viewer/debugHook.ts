/**
 * The viewer used to dump the renderer, the Fragments loader, THREE, and `openFile` onto
 * `window.__viewer` for automated preview tests. That assignment is unconditional, so a production
 * build shipped the same surface a debugger uses.
 *
 * Production callers (`sheetGuid`, the Cost/Deal rooms) only need `selectByGuid` /
 * `selectByGuids` — IFC GlobalId in, selection out. Everything else is a DEV affordance.
 *
 * `installTakeoffHook` is the same rule for `__takeoff`: a preview-eval driver, not a product API.
 */

export const VIEWER_HOOK_PROD_KEYS = ["selectByGuid", "selectByGuids"] as const;

export const VIEWER_HOOK_DEV_KEYS = [
  ...VIEWER_HOOK_PROD_KEYS,
  "viewer",
  "loader",
  "fitToModels",
  "openFile",
  "referenceModels",
  "THREE",
] as const;

export type ViewerHookProd = {
  selectByGuid: (guid: string, fit?: boolean) => void;
  selectByGuids: (guids: string[], fit?: boolean) => void | Promise<void>;
};

export type ViewerHookDev = ViewerHookProd & {
  viewer?: unknown;
  loader?: unknown;
  fitToModels?: unknown;
  openFile?: unknown;
  referenceModels?: unknown;
  THREE?: unknown;
};

type HookTarget = { __viewer?: unknown; __takeoff?: unknown };

function isDev(explicit?: boolean): boolean {
  return explicit ?? import.meta.env.DEV === true;
}

/** Attach the selection hook. Extra debug fields only land when `dev` is true. */
export function installViewerHook(api: ViewerHookDev, opts: { dev?: boolean } = {}): void {
  const hook: Record<string, unknown> = {
    selectByGuid: api.selectByGuid,
    selectByGuids: api.selectByGuids,
  };
  if (isDev(opts.dev)) {
    for (const k of VIEWER_HOOK_DEV_KEYS) {
      if (k === "selectByGuid" || k === "selectByGuids") continue;
      if (k in api) hook[k] = api[k as keyof ViewerHookDev];
    }
  }
  (window as unknown as HookTarget).__viewer = hook;
}

/** Preview-eval takeoff driver. Absent in production — there is no product caller. */
export function installTakeoffHook(
  api: Record<string, unknown>,
  opts: { dev?: boolean } = {},
): void {
  const w = window as unknown as HookTarget;
  if (!isDev(opts.dev)) {
    delete w.__takeoff;
    return;
  }
  w.__takeoff = api;
}
