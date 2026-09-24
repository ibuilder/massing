/**
 * What happens when somebody clicks a register pin on the model.
 *
 * **The behaviour this implements was already written down — in the code, as done.**
 * `apps/web/src/pins/pins.ts::load` branches topic-versus-record and its docstring says the branch
 * exists because *"a topic restores a saved viewpoint, a record opens its register row"*. The
 * record arm selected the element, set a status line, and stopped: the user got a highlight and no
 * way to reach the record the pin stands for. *A comment describing a branch's purpose is a claim
 * about behaviour, and this one had been false since the branch was written.*
 *
 * It is not a regression from PIN-ONE-CALL — measured against `git show 312c5aec^`, the old
 * `ModulePin` handler did the same two acts and no more. The review that raised it read it as one,
 * which is why the roadmap entry carries the correction: *a gap first described as a regression
 * gets fixed against the wrong baseline and its real age is lost.*
 *
 * **Why this is a module and not three lines in `app.ts`.** The roadmap filed it as needing a UX
 * decision — a new tab, a side panel or a route change — on the strength of a grep over
 * `apps/web/src/viewer/app.ts` finding no opener. There is no opener THERE; `main.ts` has had one
 * since the command palette shipped, and jumps to a record through it whenever a search hit is
 * chosen. *A grep bounded by one directory answers a question about that directory, and the
 * conclusion drawn was about the application.* So the decision was already made, consistently,
 * elsewhere: this reuses it rather than inventing a second answer.
 *
 * The opener arrives as a dependency rather than an import, because the viewer must not reach into
 * the portal: that coupling is exactly what the MassingViewer extraction has to unpick, and a
 * callback on `ViewerCtx` is a seam that survives the swap.
 */
import type { ResolvedPin } from "../api/types";

export interface PinOpenDeps {
  selectByGuid: (guid: string, fit?: boolean) => Promise<void>;
  setStatus: (m: string) => void;
  /**
   * Jump to a register record. **Required, not optional.** An optional opener would let the wire be
   * dropped and leave the old do-nothing behaviour behind, reported by no test and visible only to
   * a user clicking a pin — which is how this sat unimplemented for as long as it did. A missing
   * wire is now a compile error.
   */
  openRecord: (moduleKey: string, id: string) => void;
}

/** The status line: the pin's own identity, unchanged from what the handler always showed. */
export function describePin(p: ResolvedPin): string {
  return `${p.guid} · ${p.source_name}${p.status ? ` · ${p.status}` : ""}`;
}

/**
 * Select the element the pin sits on, say what the pin is, then open its record.
 *
 * Selection happens FIRST and deliberately: navigating away leaves the highlight in place, so
 * coming back to the Model workspace finds the element still selected. That is the answer to
 * "does 3D selection follow the user there" — it stays where it was, which costs nothing and is
 * what a user returning to check the geometry expects.
 *
 * `element_guid` is nullable on a pin (a record can be placed in space without being tied to an
 * element), so the selection is conditional and the navigation is not. Identity is the IFC
 * GlobalId throughout — never a viewer id, which does not survive a reload or a re-tessellation.
 */
export async function handleRecordPinClick(p: ResolvedPin, deps: PinOpenDeps): Promise<void> {
  // **Selection is best effort; the jump is not.** `selectByGuid` reaches the Fragments worker and
  // can reject — a stalled worker, a model that has been unloaded, a GlobalId in a federated model
  // that is no longer shown. The caller is a DOM `onclick` that does not hold this promise, so a
  // rejection would be an unhandled rejection AND would lose a record jump that was never in doubt:
  // the record id came from the pin, not from the scene. *A failure in the optional half must not
  // take the half the user asked for with it.* Raised in review on PR #577.
  //
  // It is reported rather than swallowed. An empty catch would leave a user looking at an
  // unhighlighted model with no account of why, and *a judgement a person cannot see is worse than
  // one that is occasionally wrong* — the lesson R24-FIELD-MODE ⑤ paid for.
  let selected = true;
  if (p.element_guid) {
    try {
      await deps.selectByGuid(p.element_guid, true);
    } catch {
      selected = false;
    }
  }
  deps.setStatus(describePin(p) + (selected ? "" : " · could not highlight the element"));
  // `pins.ts` routes topics to the viewpoint-restore arm, so this should not see one. If a future
  // change sends one here, selecting and reporting is right and opening is not: `source` would be
  // the literal "topic", which is not a module key, and `openRecordByKey` would look up a module
  // that does not exist. *A guard against a caller that cannot currently exist is cheap; a lookup
  // on a value that is not a key of that space is a silent nothing.*
  if (p.source === "topic") return;
  deps.openRecord(p.source, p.id);
}
