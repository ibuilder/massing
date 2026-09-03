/** Project AI: risk summary, ask, RFI triage/draft, estimate, natural-language authoring.
 *
 *  SCALE-SEAM ㉑. Route-group `/projects/{pid}/ai`, taken out of `client.ts` by the route
 *  each method calls. Six methods in **five** regions — risk-summary next to licence,
 *  ask next to pull-plan, triage/estimate next to convert, author next to fabrication
 *  recipes, draft-rfi next to phasing. `aiReadiness` is `/ai-readiness` and stays.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it.
 *
 *  SCALE-SEAM ❷ adds the two cited-question doors — *what does a cited question return?*
 *  `askModel` (`/ask`) and `askProject` (`/assistant`). They are not `/ai` routes.
 *  `uploadVerificationPhoto` and `preflight` stayed.
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

export function withAi<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Ai extends Base {
  /** AI/rules risk summary over a project's dashboard. */
  riskSummary(pid: string) {
    return this.json<{ headline: string; risks: { level: string; text: string }[]; source: string; ai_enabled: boolean }>(
      `/projects/${pid}/ai/risk-summary`);
  }
  /** Ask a natural-language question about the project; grounded on a live snapshot. */
  aiAsk(pid: string, question: string) {
    return this.json<{ answer: string; source: string; ai_enabled: boolean; snapshot?: unknown }>(
      `/projects/${pid}/ai/ask`, { method: "POST", body: JSON.stringify({ question }) });
  }
  /** Triage an RFI (AI): category / discipline / urgency / ball-in-court + a draft response. */
  triageRfi(pid: string, rid: string) {
    return this.json<{ ai_enabled: boolean; source: string; discipline: string; category: string;
      urgency: string; ball_in_court: string; draft_response: string }>(
      `/projects/${pid}/ai/triage-rfi`, { method: "POST", body: JSON.stringify({ rid }) });
  }
  /** Draft a Bill of Quantities from a plain-text project description (AI; stub without a key). */
  aiEstimate(pid: string, description: string) {
    return this.json<{ lines: { description: string; quantity: number; unit: string; rate: number; amount?: number; division?: string }[];
      total?: number; source: string; ai_enabled: boolean; message?: string }>(
      `/projects/${pid}/ai/estimate`, { method: "POST", body: JSON.stringify({ description }) });
  }
  /** Natural-language authoring: interpret a plain-English instruction into a validated plan of
   *  {recipe, params} (no execution — apply each step via editIfc after the user confirms). */
  aiAuthor(pid: string, text: string, context: { selected_guids?: string[]; active_storey?: string } = {}) {
    return this.json<{ source: string; needs_clarification: string | null;
      plan: { recipe: string; params: Record<string, unknown>; summary?: string; ok: boolean; destructive: boolean; errors: string[] }[] }>(
      `/projects/${pid}/ai/author`, { method: "POST", body: JSON.stringify({ text, context }) });
  }
  /** AI-draft an RFI from an element's context (Claude when keyed, else a template draft). */
  draftRfi(pid: string, element: unknown, note?: string) {
    return this.json<{ ai_enabled: boolean; subject: string; question: string; discipline: string; suggested_priority: string; source: string }>(
      `/projects/${pid}/ai/draft-rfi`, { method: "POST", body: JSON.stringify({ element, note }) });
  }
  /** Named agent packs over existing tools, plus the per-run audit for this project. */
  agentPacks(pid: string) {
    return this.json<{
      packs: { key: string; label: string; purpose: string; tool_count: number;
        writes: boolean; write_tools: string[] }[];
      pack_count: number; read_only_count: number;
      runs: { ts: string | null; actor: string; tool: string | null; pack: string | null; ok: boolean | null }[];
      run_count: number; failure_count: number;
    }>(`/projects/${pid}/agent-packs`);
  }

  /** askModel — a plain-English question about the model, grounded in the property-index snapshot. */
  askModel(pid: string, question: string) {
    return this.json<{ answer?: string; snapshot?: unknown; source: string }>(
      `/projects/${pid}/ask`, { method: "POST", body: JSON.stringify({ question }) });
  }
  /** askProject — a question about the whole project (modules/schedule/budget/risk). */
  askProject(pid: string, question: string) {
    return this.json<{ answer?: string; snapshot?: unknown; source: string }>(
      `/projects/${pid}/assistant`, { method: "POST", body: JSON.stringify({ question }) });
  }

  // SCALE-SEAM ⓽ — *draft this document for me from a file or some text?* The three
  // `/projects/{pid}/draft/{kind}` doors and their shared multipart helper.
  private async draftPost<T>(pid: string, kind: string, fields: Record<string, string | File | undefined>) {
    const fd = new FormData();
    for (const [k, v] of Object.entries(fields)) if (v != null) fd.append(k, v);
    const res = await fetch(this.url(`/projects/${pid}/draft/${kind}`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error(`Draft ${kind} -> ${res.status}`);
    return res.json() as Promise<T>;
  }
  /** Draft an RFI from a short note (+ optional source PDF/text) — editable before you create it. */
  aiDraftRfi(pid: string, opts: { note?: string; file?: File; text?: string }) {
    return this.draftPost<{ subject: string; question: string; discipline: string; spec_section?: string;
      priority: string; suggested_assignee?: string; background?: string;
      citations?: { page: number; snippet?: string }[]; source: string; message?: string }>(
      pid, "rfi", { note: opts.note, file: opts.file, text: opts.text });
  }
  /** Summarize an uploaded submittal package (title / spec / type / key + missing items). */
  draftSubmittalSummary(pid: string, opts: { file?: File; text?: string }) {
    return this.draftPost<{ title: string; spec_section?: string; type?: string; summary: string;
      key_items?: string[]; missing_or_review?: string[];
      citations?: { page: number }[]; source: string; message?: string }>(
      pid, "submittal-summary", { file: opts.file, text: opts.text });
  }
  /** Draft a trade scope of work (inclusions / exclusions / clarifications) from a plan/spec set. */
  draftScope(pid: string, trade: string, opts: { file?: File; text?: string }) {
    return this.draftPost<{ trade: string; inclusions: string[]; exclusions: string[];
      clarifications: string[]; spec_sections?: string[];
      citations?: { page: number }[]; source: string; message?: string }>(
      pid, "scope", { trade, file: opts.file, text: opts.text });
  }
  };
}
