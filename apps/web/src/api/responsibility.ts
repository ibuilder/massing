/** Responsibility matrix — who is accountable for what on this project?
 *
 *  SCALE-SEAM (89), second slice from the 117 methods above the STAYING banner.
 *
 *  Four methods, and the backend agrees exactly: `aec_api/routers/responsibility.py` holds these
 *  four routes and nothing else. A 1:1 correspondence with a router is the strongest corroboration
 *  available for a grouping, and it is checked here rather than assumed — the same evidence that
 *  settled (88)'s operate-phase cluster.
 *
 *  `responsibilityMatrix` assembles and validates the RACI/DACI grid, `responsibilityTemplates`
 *  lists the starter grids, `setResponsibilityConfig` fixes the role columns and the mode, and
 *  `applyResponsibilityTemplate` seeds rows from one.
 *
 *  ### Why NOT `modules.ts`, which owns the records these rows are stored in
 *
 *  That router's own docstring says it plainly: *"Rows themselves are ordinary `responsibility`
 *  module records, so create/edit/delete of individual cells goes through the generic /modules
 *  CRUD."* Same storage, and `modules.ts` is where that CRUD lives — so adjacency argues for
 *  filing them there.
 *
 *  It is the wrong seam, because **storage is a HOW.** A caller reaching for `modules.ts` wants
 *  records of some module type; a caller reaching for these wants to know who is Accountable for a
 *  task and to seed a grid that has none. (85) rejected "they are all multipart uploads" for being
 *  a mechanism rather than a question, and "they are all module records" is the same shape of
 *  answer one layer down.
 *
 *  Four methods is a small file, and that is fine: `risk.ts`, `dealMemory.ts` and `assetRights.ts`
 *  hold two each, `designOptions.ts` and `library.ts` three. Sizing a mixin to feel substantial is
 *  not a reason to put a method somewhere it does not answer.
 *
 *  A mixin, so every call site resolves unchanged; `api/surface.test.ts` is what proves it.
 */
import { HttpCore } from "./httpCore";
import type { ResponsibilityMatrix } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withResponsibility<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Responsibility extends Base {
  responsibilityMatrix(pid: string) {
    return this.json<ResponsibilityMatrix>(`/projects/${pid}/responsibility`);
  }
  responsibilityTemplates(pid: string) {
    return this.json<{ templates: { key: string; name: string; description: string; rows: number }[] }>(
      `/projects/${pid}/responsibility/templates`);
  }
  setResponsibilityConfig(pid: string, roles: string[], mode: "RACI" | "DACI") {
    return this.json<{ roles: string[]; mode: string }>(`/projects/${pid}/responsibility/config`, {
      method: "PUT", body: JSON.stringify({ roles, mode }) });
  }
  applyResponsibilityTemplate(pid: string, key: string, mode: "RACI" | "DACI") {
    return this.json<{ applied: string; created: number; mode: string }>(
      `/projects/${pid}/responsibility/apply-template`, {
        method: "POST", body: JSON.stringify({ key, mode }) });
  }
  };
}
