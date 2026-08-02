/**
 * A29-UNDO-LOCAL — undo the STROKE, not the commit.
 *
 * The server versions every commit (edit_undo republishes), which is the right answer to "undo the
 * wall I authored" and the wrong answer to "undo my last click": popping one mis-clicked point of an
 * in-progress polyline must not cost a republish — and before this, it cost the whole draft, because
 * Escape was the only eraser.
 *
 * Scope, exactly as the roadmap bounds it: the in-progress draft only. The history clears on commit
 * and on disarm, and the server's history remains the record — nothing here survives the draft it
 * belongs to.
 *
 * The class mutates the CALLER's points array in place rather than owning a copy: `armPts` is read
 * by the inference/snap flow on every click, and a second array holding "the same" points is the
 * two-answers-to-one-question shape this repo keeps paying for.
 */
export class DraftPointHistory<T> {
  private redoStack: T[] = [];

  /** A new click invalidates the redo branch — redo after a divergent click would splice a point
   *  from an abandoned timeline into the middle of the current one. */
  noteAdded(): void { this.redoStack = []; }

  /** Pop the last point (LIFO) onto the redo stack. Null when there is nothing to undo. */
  undo(points: T[]): T | null {
    const p = points.pop();
    if (p === undefined) return null;
    this.redoStack.push(p);
    return p;
  }

  /** Restore the most recently undone point. Null when the redo branch is empty or was invalidated. */
  redo(points: T[]): T | null {
    const p = this.redoStack.pop();
    if (p === undefined) return null;
    points.push(p);
    return p;
  }

  /** Commit or disarm — the draft is over, both directions of its history go with it. */
  clear(): void { this.redoStack = []; }

  get redoDepth(): number { return this.redoStack.length; }
}
