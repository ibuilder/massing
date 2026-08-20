/** Project AI: risk summary, ask, RFI triage/draft, estimate, natural-language authoring.
 *
 *  SCALE-SEAM ㉑. Route-group `/projects/{pid}/ai`, taken out of `client.ts` by the route
 *  each method calls. Six methods in **five** regions — risk-summary next to licence,
 *  ask next to pull-plan, triage/estimate next to convert, author next to fabrication
 *  recipes, draft-rfi next to phasing. `aiReadiness` is `/ai-readiness` and stays.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it.
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
  };
}
