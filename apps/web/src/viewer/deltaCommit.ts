/**
 * R42-COMMIT-DELTA — an authored edit keeps the geometry it already converted, instead of throwing
 * it away and re-deriving the whole model.
 *
 * WHAT THE OLD PATH DID. `authorAndReload` committed with `publish=true`, waited for a full
 * reconvert, then called `loadProjectModel()` — which `disposeAll()`s every model and reloads. So
 * the one-element fragment `edit-preview` had *already produced and already displayed* was
 * discarded, and the same wall was re-derived inside the whole-model convert. Measured on a
 * 1,000-element project: **1.70 s to produce the new element, 37.39 s to re-derive everything.**
 *
 * WHAT THIS DOES INSTEAD. The preview fragment is PROMOTED to an authoritative delta and kept. The
 * base `.frag` stays at the previous publish until somebody consolidates. Nothing new is needed
 * from the loader — it has held N models keyed by id since it shipped.
 *
 * ── THE PART THAT IS NOT AN OPTIMISATION ──────────────────────────────────────────────────────
 * This creates a genuinely PARTIAL state, in TWO stages. The rendered base geometry is one publish
 * behind until somebody consolidates — that is the whole point. And for a few seconds after each
 * commit the element is in the scene but not yet in the property index, because the index is rebuilt
 * whole and the commit only kicks that off. Both are surfaced, in words, with the consequence named:
 * a silent delta state would be the same defect as `available: false` rendered as zero, moved into
 * the viewport.
 *
 * The store is deliberately dumb and synchronous: it is the *record* of what is pending, not the
 * thing that decides. Every rule about when to go delta lives at the call site, where the fallback
 * to a full publish also lives — because an edit with NO preview fragment has no geometry to keep,
 * and going delta there would show the user nothing at all.
 */

/** One authored-but-unconsolidated edit, keyed by the viewer model id holding its geometry. */
export type DeltaEntry = {
  /** The loader model id — `disposeOne(modelId)` is the only way to take this off screen. */
  modelId: string;
  /** What the user did, in their words ("Wall", "Door") — shown when they ask what is pending. */
  label: string;
  /** The element's GlobalId, which the commit forces the real element to adopt so this fragment and
   *  the model are the same element. Absent when the preview gave none. */
  guid?: string;
};

/**
 * The pending set.
 *
 * A `Map` keyed by `modelId` rather than an array, because the id is what the loader disposes by
 * and duplicates would leak GPU geometry. Re-adding the same id REPLACES rather than appends: the
 * alternative is two records pointing at one model, and disposing it once would leave the other
 * claiming geometry that is gone.
 */
export class DeltaStore {
  private readonly items = new Map<string, DeltaEntry>();

  /**
   * How many reindexes are in flight.
   *
   * The served property index is rebuilt WHOLE, so between promoting a delta and the reindex
   * finishing the element is in the scene but not in the index — every GUID-keyed reader (selection,
   * LOD, QTO, pins) misses it. That window is short and it is real, and this codebase's recurring
   * defect is exactly the short real window that nothing says out loud. A count rather than a flag
   * because two quick edits overlap, and a boolean would clear on the first one's return while the
   * second was still running.
   */
  private inFlight = 0;

  add(entry: DeltaEntry): void {
    this.items.set(entry.modelId, entry);
  }

  /** Bracket a reindex. Returns the new in-flight count so a caller can repaint on any change. */
  indexing(delta: 1 | -1): number {
    this.inFlight = Math.max(0, this.inFlight + delta);
    return this.inFlight;
  }

  get reindexing(): boolean {
    return this.inFlight > 0;
  }

  remove(modelId: string): boolean {
    return this.items.delete(modelId);
  }

  get count(): number {
    return this.items.size;
  }

  /** Insertion-ordered, which is authoring order — the order somebody would undo in. */
  entries(): DeltaEntry[] {
    return [...this.items.values()];
  }

  ids(): string[] {
    return [...this.items.keys()];
  }

  clear(): void {
    this.items.clear();
  }
}

/**
 * What the indicator says. Pure, so the honest-state rule is testable rather than asserted.
 *
 * The zero case is NOT the empty string. "Nothing pending" and "we are not tracking" would then
 * render identically, and a reader could not tell a consolidated model from a broken indicator —
 * which is precisely the confusion the visible-partial-state decision was made to avoid.
 */
export function deltaStatusText(count: number, reindexing = false): string {
  if (count <= 0) return reindexing ? "Updating model data…" : "Model geometry is up to date.";
  const n = count === 1 ? "1 edit" : `${count} edits`;
  const it = count === 1 ? "it" : "them";
  // The data half is stated as a CLAIM about the index, and it is only true once the reindex has
  // landed. The roadmap's second hazard for this feature is precisely that the delta's element is in
  // the scene before it is in the index — so while that is running, say so rather than promise it.
  const data = reindexing
    ? "Model data is still updating — searches and quantities may not see the newest edits yet"
    : "The data is current";
  return `${n} authored — geometry not yet rebuilt. ${data}; the shapes on screen `
    + `are from the last rebuild plus ${it}.`;
}

/** Short form for a button/badge, where the long sentence does not fit. */
export function deltaBadge(count: number): string {
  return count <= 0 ? "✓ up to date" : `⟳ Rebuild (${count})`;
}

export type DeltaIndicator = {
  el: HTMLElement;
  /** Re-read the store and repaint. Called after every add and after a consolidate. */
  refresh: () => void;
};

/**
 * The rail control: one line of status plus the action that resolves it.
 *
 * `onConsolidate` is passed in rather than performed here — consolidating means a full publish and
 * a model reload, which belong to the caller that owns those. This module knows what is pending and
 * how to say so, and deliberately nothing else.
 */
export function deltaIndicator(store: DeltaStore, onConsolidate: () => void | Promise<void>): DeltaIndicator {
  const el = document.createElement("div");
  el.style.cssText = "display:flex;flex-direction:column;gap:4px";
  const text = document.createElement("div");
  text.className = "meta";
  const btn = document.createElement("button");
  btn.className = "mini-btn";
  btn.title = "Rebuild the whole model so the base geometry matches the data";
  el.append(text, btn);

  const refresh = () => {
    const n = store.count;
    text.textContent = deltaStatusText(n, store.reindexing);
    btn.textContent = deltaBadge(n);
    btn.disabled = n <= 0;
    // The row is always present, even at zero. A control that appears only when something is wrong
    // teaches people that its absence means nothing is being watched — and here its absence would
    // be indistinguishable from a rail that failed to build it.
    el.style.opacity = n > 0 ? "1" : "0.65";
  };

  btn.onclick = () => void (async () => {
    btn.disabled = true;
    try {
      await onConsolidate();
    } finally {
      refresh();          // whatever happened, the button must reflect the store, not the attempt
    }
  })();

  refresh();
  return { el, refresh };
}

/**
 * Everything the commit path touches that lives in the viewer, named one by one.
 *
 * This exists so the DECISION — delta or full publish, and what happens on each failure — is out of
 * `app.ts` and under test. Inside `authorAndReload` it was unreachable by any suite: it needs a
 * loader, a fragment server, a project and a running convert. As nine named functions it needs none
 * of them, and the branch that matters (a preview exists ⇒ keep the geometry) is three lines to
 * assert instead of an integration environment to build.
 */
export type DeltaDeps = {
  store: DeltaStore;
  /** Repaint the rail. Separate from `store` because the rail may not be built yet. */
  refresh: () => void;
  editIfc: (recipe: string, params: Record<string, unknown>, publish: boolean,
            wantGuid?: string) => Promise<unknown>;
  publish: (reconvert: boolean) => Promise<unknown>;
  /** Poll to a terminal publish state ("done" | "error" | …). */
  awaitPublish: () => Promise<string>;
  /** Reload the base model; resolves true when something was shown. */
  reloadModel: () => Promise<boolean>;
  reloadPins: () => Promise<unknown>;
  dispose: (modelId: string) => Promise<unknown>;
  clearDraft: () => void;
  markFailed: () => void;
  notify: (m: string, kind?: "info" | "success" | "error") => void;
};

export type CommitOutcome = { applied: boolean; refused: boolean };

export function deltaCommitter(d: DeltaDeps) {
  /** Every background reindex started but not yet finished — see `settled()`. */
  const running = new Set<Promise<void>>();

  /**
   * Rebuild the property index without reconverting geometry, in the background.
   *
   * Not awaited by `commit`, because the edit is already durable on disk and a failed reindex must
   * not present as a failed author. But it IS bracketed and counted: `publish` resolves when the job
   * is ACCEPTED, not when it is done, so the honest end of the window is the poll to a terminal
   * state. Until then the element is in the scene and not in the index, and the indicator says so
   * instead of claiming the data is current.
   */
  function reindex(): void {
    d.store.indexing(1);
    d.refresh();
    const p = (async () => {
      try { await d.publish(false); await d.awaitPublish(); } catch { /* the edit stands regardless */ }
      d.store.indexing(-1);
      d.refresh();
    })();
    running.add(p);
    void p.then(() => running.delete(p));
  }

  /**
   * Resolve once no reindex is in flight.
   *
   * For callers that need the index to be current before they read it — an export, a takeoff, a
   * schedule — rather than merely current-ish. Also what a test awaits instead of guessing at timers.
   */
  async function settled(): Promise<void> {
    while (running.size) await Promise.all([...running]);
  }

  /**
   * Drop a preview fragment AND its delta record together.
   *
   * They must go together: by the time a late failure runs this, the fragment may already have been
   * promoted, and a record naming disposed geometry is worse than no record — the rail would keep
   * asking for a rebuild of something that is no longer on screen.
   */
  const drop = async (previewId: string | null) => {
    if (!previewId) return;
    if (d.store.remove(previewId)) d.refresh();
    await d.dispose(previewId).catch(() => {});
  };

  /**
   * Author one recipe and put its result on screen.
   *
   * WITH a preview fragment we already have this element's real geometry, so committing does not
   * need a whole-model reconvert: author without publishing, promote the fragment to a delta, and
   * reindex only. The base `.frag` stays one publish behind until somebody rebuilds — which the rail
   * says in words, because a partial state that renders like a complete one is the defect this
   * codebase keeps finding.
   *
   * WITHOUT one there is no geometry to keep, so that path still does the full publish. Going delta
   * there would leave the user looking at a model missing the thing they just drew, which is worse
   * than waiting.
   */
  async function commit(recipe: string, params: Record<string, unknown>, label: string,
                        previewId: string | null, previewGuid?: string): Promise<CommitOutcome> {
    const outcome: CommitOutcome = { applied: false, refused: false };
    try {
      if (previewId) {
        // The GUID is the whole point of keeping this fragment: without it the shape on screen and
        // the element in the model are two different elements, and every GUID-keyed reader misses
        // the one the user just drew. Measured live before the fix — preview 33a6…, committed 0POI….
        await d.editIfc(recipe, params, false, previewGuid);
        d.store.add({ modelId: previewId, label, guid: previewGuid });
        d.clearDraft();                 // it is on the record now — the amber draft marker goes
        d.refresh();
        outcome.applied = true;
        reindex();
        d.notify(`${label} applied — rebuild pending`, "success");
      } else {
        await d.editIfc(recipe, params, true);
        d.notify(`${label} authored — converting…`, "info");
        const state = await d.awaitPublish();
        if (state === "done") {
          const shown = await d.reloadModel();
          // This path RECONVERTED, so it rebuilt the pending edits too — they were authored with
          // `publish=false` but they are in the IFC, and the convert reads the IFC. Leaving them in
          // the store would strand the rail on "N edits not yet rebuilt" forever, while
          // `reloadModel`'s disposeAll had already reclaimed the very geometry those records name.
          d.store.clear();
          d.refresh();
          d.clearDraft();
          d.notify(`${label} applied${shown ? " — shown" : ""}`, "success");
          outcome.applied = true;
        } else {
          await drop(previewId);
          d.markFailed();
          d.notify(`${label} authored — publish ${state}`, state === "error" ? "error" : "info");
        }
      }
      await d.reloadPins();
    } catch (err) {
      // A29: a failed placement keeps its marker, turned red — a toast says something failed, the
      // marker says WHERE. The next draft action clears it (fromParams handles that).
      d.markFailed();
      await drop(previewId);
      outcome.refused = true;
      d.notify(`${label} failed: ${(err as Error).message}`, "error");
    }
    return outcome;
  }

  /**
   * Rebuild the base geometry so it matches the data.
   *
   * The deltas are cleared only AFTER the new base has loaded. Clearing first would blink the
   * elements off screen, and on a failed publish would leave the user with neither the delta nor the
   * rebuild — the one state in which the deltas are the only correct geometry they have.
   */
  async function consolidate(): Promise<void> {
    try {
      await d.publish(true);
      const st = await d.awaitPublish();
      if (st !== "done") { d.notify(`rebuild ${st}`, st === "error" ? "error" : "info"); return; }
      await d.reloadModel();          // disposeAll() reclaims the delta models with everything else
      d.store.clear();
      d.refresh();
      await d.reloadPins();
      d.notify("geometry rebuilt", "success");
    } catch (e) {
      d.notify(`rebuild failed: ${(e as Error).message}`, "error");
    }
  }

  return { commit, consolidate, settled };
}
