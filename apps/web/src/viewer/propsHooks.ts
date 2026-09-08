import type { ApiClient } from "../api/client";
import type { ElementEffectiveProps } from "../api/model";
import type { PropsEditHooks } from "./propsView";

/**
 * PROP-OVERRIDE — the properties panel's wiring to the API, out of `app.ts`.
 *
 * ## Why this module exists
 *
 * `app.ts` sits exactly on its `services/api/test_file_sizes.py` pin, whose remedy is extraction and
 * never headroom, and the panel needed two things it did not have: a THIRD edit hook, and a second
 * read. Taking the hook factory out with them is what makes this an extraction rather than a move —
 * and the three hooks belong together on the merits, being the panel's whole write surface.
 *
 * ## The defect this was written for
 *
 * `set_element_pset` — writing an occurrence-level property override — has shipped in the viewer all
 * along. `reset_prop_to_type`, which drops that override so the type's value shows through again,
 * sat in `authoring_matrix.UNREACHED`: implemented, covered by `services/api/test_instance_props.py`,
 * reachable from nothing. **A one-way door with the return trip built and tested.**
 *
 * The read half was darker still, and no reachability gate could have found it.
 * `GET /projects/{pid}/model/element/{guid}/effective-props` computes, per property, whether the
 * value is the type's or an instance override, and what the override shadows — its own docstring
 * calls it *"the properties panel's type-vs-instance answer"*. The route had a caller and the client
 * method had a caller, so every reach check was satisfied; the ONE caller was the dimensional-lock
 * solver, which reads `.value` for numbers and drops `source`, `overridden` and `type_value`. *A
 * route with no caller is caught by a gate. A PAYLOAD WITH NO READER is caught by nobody.*
 */
export interface PropsWiringDeps {
  api: ApiClient;
  pid: string;
  guid: string;
  /** Re-render from a fresh server read after an applied edit. Every hook below ends here rather
   *  than patching the DOM it just changed: the recipe republishes, and what the panel shows next
   *  has to be what the model now says, not what we asked it to become. */
  reload: () => Promise<void>;
}

/** The panel's three write actions. Each applies a server recipe, republishes, then re-reads. */
export function propsEditHooks(d: PropsWiringDeps): PropsEditHooks {
  const edit = async (recipe: string, params: Record<string, unknown>) => {
    await d.api.editIfc(d.pid, recipe, { guid: d.guid, ...params }, true);
    await d.reload();
  };
  return {
    setProp: (pset, prop, value, dtype) => edit("set_element_pset", { pset, prop, value, dtype }),
    classify: (system, code, name) => edit("set_classification", { system, code, name }),
    // AUTH: the undo for setProp. The panel only offers it where `overridden` is true, which is
    // exactly when the recipe has a type value to fall back to — it refuses otherwise.
    resetProp: (pset, prop) => edit("reset_prop_to_type", { pset, prop }),
  };
}

/**
 * Read which of an element's values are instance overrides. **`null` means the read FAILED**, and
 * the panel renders that differently from "not asked" — see `buildElementProps`.
 *
 * Swallowing the error to `undefined` would make a failed read indistinguishable from an element
 * with no overrides, and the panel would then quietly assert that nothing is overridden. That is
 * the same shape as the defect this whole module is here to fix, so the failure is kept nameable.
 */
export async function readEffectiveProps(api: ApiClient, pid: string,
                                         guid: string): Promise<ElementEffectiveProps | null> {
  try { return await api.elementEffectiveProps(pid, guid); }
  catch { return null; }
}
