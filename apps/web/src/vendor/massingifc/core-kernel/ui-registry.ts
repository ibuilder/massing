import { toDisposable, type Disposable } from "./disposable.js";

/**
 * Where a contribution attaches. Open-ended by design: a host shell is free to invent its own
 * points (`"status-bar"`, `"viewport-gizmo"`) without a kernel change.
 */
export type UIContributionPoint =
  | "panel"
  | "toolbar"
  | "context-menu"
  | "overlay"
  | "inspector"
  // eslint-disable-next-line @typescript-eslint/ban-types -- preserves literal autocomplete
  | (string & {});

export interface UIMountContext<THost = unknown> {
  readonly host: THost;
  readonly contributionId: string;
}

/** Attach a contribution to a host-provided surface, returning a teardown for the host to call. */
export type UIMount<THost = unknown> = (context: UIMountContext<THost>) => Disposable | void;

/**
 * A UI contribution.
 *
 * Note there is no DOM type anywhere in this file. The kernel must stay usable from a desktop
 * shell, a test harness, or a headless server-side session, so the host surface is generic and the
 * web shell narrows `THost` to `HTMLElement` at its own boundary.
 */
export interface UIContribution<THost = unknown> {
  readonly id: string;
  readonly point: UIContributionPoint;
  readonly title?: string;
  readonly icon?: string;
  /** Logical bucket within a point, e.g. a toolbar section. */
  readonly group?: string;
  /** Ascending sort key. Ties break on `id` so ordering is stable across sessions. */
  readonly order?: number;
  /** Host-interpreted hint, e.g. `"left"`, `"right"`, `"bottom"`, `"modal"`. */
  readonly placement?: string;
  /** Command run on activation. Keeps UI declarative and routes actions through the command bus. */
  readonly commandId?: string;
  /** Visibility predicate evaluated against host-supplied context. */
  readonly when?: (context: Readonly<Record<string, unknown>>) => boolean;
  readonly mount?: UIMount<THost>;
  readonly pluginId?: string;
}

/**
 * Registry of UI contributions.
 *
 * The kernel stores and orders descriptors; it never renders. That split is what lets the same
 * plugin contribute to a web shell and a desktop shell without knowing which one it is running in.
 */
export class UIExtensionRegistry<THost = unknown> {
  readonly #byPoint = new Map<string, UIContribution<THost>[]>();
  readonly #listeners = new Set<(point: string) => void>();

  register(contribution: UIContribution<THost>): Disposable {
    const list = this.#byPoint.get(contribution.point) ?? [];
    list.push(contribution);
    list.sort(
      (a, b) => (a.order ?? 0) - (b.order ?? 0) || a.id.localeCompare(b.id),
    );
    this.#byPoint.set(contribution.point, list);
    this.#notify(contribution.point);

    return toDisposable(() => {
      const current = this.#byPoint.get(contribution.point);
      if (!current) return;
      const index = current.indexOf(contribution);
      if (index >= 0) current.splice(index, 1);
      if (current.length === 0) this.#byPoint.delete(contribution.point);
      this.#notify(contribution.point);
    });
  }

  registerAll(contributions: readonly UIContribution<THost>[]): Disposable {
    const subscriptions = contributions.map((contribution) => this.register(contribution));
    return toDisposable(() => {
      for (const subscription of subscriptions) subscription.dispose();
    });
  }

  /** Everything registered at a point, in sort order, regardless of visibility. */
  byPoint(point: UIContributionPoint): readonly UIContribution<THost>[] {
    return this.#byPoint.get(point) ?? [];
  }

  /**
   * Contributions at a point whose `when` predicate passes.
   *
   * A predicate that throws hides the contribution rather than propagating: a plugin with a broken
   * visibility rule should lose its own button, not break the toolbar for everyone else.
   */
  visible(
    point: UIContributionPoint,
    context: Readonly<Record<string, unknown>> = {},
  ): readonly UIContribution<THost>[] {
    return this.byPoint(point).filter((contribution) => {
      if (!contribution.when) return true;
      try {
        return contribution.when(context);
      } catch {
        return false;
      }
    });
  }

  points(): readonly string[] {
    return [...this.#byPoint.keys()];
  }

  onDidChange(listener: (point: string) => void): Disposable {
    this.#listeners.add(listener);
    return toDisposable(() => void this.#listeners.delete(listener));
  }

  #notify(point: string): void {
    for (const listener of [...this.#listeners]) {
      try {
        listener(point);
      } catch {
        // Ignore: a failing observer must not corrupt the registry.
      }
    }
  }
}
