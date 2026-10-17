/** MODELOPT-DARK — model-option BRANCHES: snapshot, list, switch, diff, drop.
 *
 *  Route group `/projects/{pid}/model/options*`. Five routes, a `model_options` engine tested end
 *  to end in `services/api/test_model_options.py`, storage, an index, and integration with the undo
 *  stack — **and not one reference anywhere in `apps/web/src`** before this file. A developer could
 *  branch a massing as "Scheme A — steel frame", switch between branches undoably, and diff them
 *  only by calling the API by hand.
 *
 *  **Only ONE of the five was counted as dark.** `test_route_reachability.py` froze
 *  `/model/options/{slug}/activate` and could not see the other four: its rule fires when a route's
 *  last static segment appears nowhere in the web source, and `options` and `diff` appear all over
 *  it, so they sit in that gate's own documented false-negative class — the same three-way split
 *  CLASSIFY-DARK paid for, where one capability's parts each read as somebody else's gap.
 *
 *  **Not a duplicate of `designOptions.ts`.** `model_options`'s header draws the line itself:
 *  *"The metrics-comparison module (`design_options.py`) compares numbers; THIS module carries the
 *  actual model files."* The register's economics reached a screen; the branches reached nothing.
 *
 *  A mixin and its own file rather than lines in `client.ts`, for the reason the size ratchet in
 *  `services/api/test_file_sizes.py` states in as many words — "a new endpoint added straight to
 *  `client.ts` will fail this, and that friction is the point."
 */
import { HttpCore } from "./httpCore";
import type { ModelOptionActivated, ModelOptionDiff, ModelOptionList,
  ModelOptionBranch } from "./model";

type Ctor<T> = new (...args: any[]) => T;

export function withModelOptions<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class ModelOptions extends Base {
  /** The project's option branches, newest first, with the byte-identical one flagged `current`. */
  modelOptionList(pid: string) {
    return this.json<ModelOptionList>(`/projects/${pid}/model/options`);
  }

  /** Branch the current model under a name. Re-using a name OVERWRITES that branch head — it is a
   *  head, not an archive, and the edit history keeps the archaeology. */
  modelOptionSnapshot(pid: string, name: string, note?: string) {
    return this.json<ModelOptionBranch>(`/projects/${pid}/model/options`,
      { method: "POST", body: JSON.stringify(note == null ? { name } : { name, note }) });
  }

  /** Switch the project to a branch. Goes through the same edit-history push as any edit, so the
   *  switch itself is ONE undo step, and republishes the viewer geometry unless told not to. */
  modelOptionActivate(pid: string, slug: string, publish = true) {
    return this.json<ModelOptionActivated>(
      `/projects/${pid}/model/options/${encodeURIComponent(slug)}/activate`,
      { method: "POST", body: JSON.stringify({ publish }) });
  }

  /** What separates the current model from a branch. The GUID lists are capped at 100 and the
   *  counts are not — read `added_count` / `removed_count` for totals. */
  modelOptionDiff(pid: string, slug: string) {
    return this.json<ModelOptionDiff>(
      `/projects/${pid}/model/options/${encodeURIComponent(slug)}/diff`);
  }

  /** Drop a branch. The edit history is untouched; `deleted` is false if it was already gone. */
  modelOptionDelete(pid: string, slug: string) {
    return this.json<{ deleted: boolean }>(
      `/projects/${pid}/model/options/${encodeURIComponent(slug)}`, { method: "DELETE" });
  }
  };
}
