import type { ApiClient } from "../../api/client";
import { enqueueAndWait } from "../../api/waitForJob";
import { kvTable, resultNote, showResult } from "../../ui/result";
import { toast } from "../../ui/feedback";
import type { SelectionSets } from "../selectionSets";
import type { ModelIdMap } from "../modelIds";

/**
 * R24-RUNS-INBOX — IDS validation as a queued run, out of `qaSection.ts` so that file's size
 * ratchet does not admit the enqueue wiring as growth. The control LABEL stays in qaSection so
 * `toolsSplit.test.ts` still sees it inside the `qa` builder.
 */
export async function runIdsValidate(opts: {
  api: ApiClient;
  pid: string;
  out: HTMLElement;
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  selectMap: (ids: ModelIdMap, opts?: { fit?: boolean }) => Promise<void>;
  sets: SelectionSets;
}): Promise<void> {
  const { api, pid, out, toolBtn2, selectMap, sets } = opts;
  const r = await enqueueAndWait(api, pid, "ids_validate") as {
    status: string; summary: { passed: number; failed: number };
    specifications: { status: string; name: string; passed: number; applicable: number;
      failed_guids: string[] }[];
  };
  out.textContent = `IDS ${r.status.toUpperCase()} — ${r.summary.passed}/${r.summary.passed + r.summary.failed}`;
  toast(`IDS ${r.status.toUpperCase()} — ${r.summary.passed} pass / ${r.summary.failed} fail`, r.status === "pass" ? "success" : "error");
  const failing = r.specifications.flatMap((s) => s.failed_guids);
  showResult("IDS validation", (body) => {
    body.appendChild(resultNote(`<b>IDS: ${r.status.toUpperCase()}</b> — ${r.summary.passed} pass / ${r.summary.failed} fail`, r.status === "pass" ? "ok" : "bad"));
    body.appendChild(kvTable(r.specifications.map((s) => ({
      k: `${s.status === "pass" ? "✓" : "✗"} ${s.name}`, v: `${s.passed}/${s.applicable}` }))));
    if (failing.length) {
      const hl = toolBtn2(`Highlight ${failing.length} failures in 3D`, async () => { await selectMap(await sets.fromGuids(failing), { fit: true }); });
      body.appendChild(hl);
    }
  });
}

