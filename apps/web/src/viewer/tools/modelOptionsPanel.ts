import { type ApiClient } from "../../api/client";

/**
 * MODELOPT-DARK — the door to model-option branches, which had none.
 *
 * `POST /model/options` (snapshot a named branch), `GET /model/options` (list, flagging the one
 * byte-identical to the working model), `POST /model/options/{slug}/activate` (switch, as one undo
 * step, republishing the viewer), `GET /model/options/{slug}/diff` and
 * `DELETE /model/options/{slug}`. Five routes, an engine tested end to end in
 * `services/api/test_model_options.py`, storage, an index, undo integration — and **no reference
 * anywhere in `apps/web/src`**.
 *
 * **Only one of the five was counted.** `services/api/test_route_reachability.py` froze
 * `activate`; the other four sit in that gate's documented false-negative class, because its rule
 * fires when a route's last static segment appears nowhere in the web source and `options` /
 * `diff` appear all over it. *One capability's parts, each reading as somebody else's gap.*
 *
 * ## Why this file exists rather than a builder in `app.ts`
 *
 * `apps/web/src/viewer/app.ts` is at **exactly** its `services/api/test_file_sizes.py` pin, so an
 * import plus a builder entry plus an `order` key is lines it does not have. The established
 * remedy is the one `repairPanel.ts` and `projectSetupPanel.ts` took: export a `*Button()` and let
 * an existing section append it. Branching a model is authoring, so `authoringSection.ts` is where
 * the ratchet was pointing anyway — the same argument the locks builder in that file makes.
 *
 * The export is named `*Button` and its call sits INSIDE the append, because
 * `apps/web/src/viewer/sectionButtonsWired.test.ts` asks exactly that of an exported builder: a
 * button held in a local and never appended is the silent-inert failure that gate is named for.
 */

export interface ModelOptionsDeps {
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  api: ApiClient;
  pid: string;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
  waitForPublish: (pid: string, onTick?: (s: string, elapsed: string | null) => void) => Promise<string>;
  loadProjectModel: () => Promise<boolean>;
}

export function modelBranchesButton(d: ModelOptionsDeps): HTMLButtonElement {
  const btn = d.toolBtn2("🌿 Model branches (snapshot · switch · diff)", () => { void open(); });
  const out = document.createElement("div");
  out.className = "meta";
  out.style.cssText = "margin-top:6px;font-size:11px";
  btn.insertAdjacentElement("afterend", out);

  async function open(): Promise<void> {
    out.textContent = "loading branches…";
    // Deferred for the bundle budget: `viewer/tools/*` is the eager shell chunk and this panel put
    // it at exactly 225.0 KB of 225. See `modelOptionsView.ts` for why the whole body went rather
    // than just the rendering.
    const { renderBranches } = await import("./modelOptionsView");
    await renderBranches(out, d);
  }
  return btn;
}
