/** Document-control file manager, plus ISO 19650 CDE / BEP / information requirements.
 *
 *  SCALE-SEAM ⑱ took `/projects/{pid}/documents`. SCALE-SEAM ㉛ adds the six methods that answer
 *  *is the information container (CDE) and its requirement flow in order?* — BEP, CDE status,
 *  the requirements register / cascade / delivery plan, and ISO 19650-6 exchange acceptance.
 *  They span `/bep`, `/cde` and `/info-requirements`. `aiReadiness` sat inside that run in
 *  `client.ts` and did **not** come: it is an AI scorecard, not a CDE question. **That
 *  characterisation is what moved it**: SCALE-SEAM ⓾ took it to `apps/web/src/api/ai.ts`,
 *  where `ai.ts`'s own header had declined it on route grounds. It is no longer in
 *  `client.ts`.
 *  Composed through the existing `withDocuments` wrapper — no extra `withX()` on `ApiClient`.
 *
 *  SCALE-SEAM ㊾ adds the report catalog — *what can we print from this project?* List plus
 *  the generated PDF/XLSX URL. They sat next to licence in `client.ts` and did **not** go
 *  with licence (that is the deployment plan, not a project document).
 *
 *  SCALE-SEAM ❿ adds closeout analytics — *is turnover actually closing?* Punchlist,
 *  commissioning, warranties, O&M. Safety sat below and did **not** come.
 *
 *  SCALE-SEAM (83) adds the commissioning loop — *is commissioning closing, and in detail?*
 *  Seed, the system × phase matrix, the per-system turnover dossier. They belong here because
 *  `closeoutSummary`, which ❿ brought in, already returns a `commissioning` ROLLUP
 *  (`cx_count` / `passed` / `failed` / `conditional`) — these three are the detail behind that
 *  number, the same rollup-and-detail pair as `procurementLevel` / `bidLevelingDetail` at ⓽.
 *  `cxSeed` is a POST that creates records; it came anyway, because separating a seeder from the
 *  only two readers of what it seeds is the split (82) refused when it kept `namingAudit` with
 *  "namingConventions". (Plain quotes: NAMING-UNREAD deleted that method — the audit carries the
 *  conventions itself — so the precedent stands and the method does not.)
 *
 *  SCALE-SEAM ⓺ adds the issuance gate — *can this package go out?* `preflight`. Hero upload sat beside it and did **not** come.
 */
import { HttpCore, HttpError } from "./httpCore";
import type { CxMatrix, DocFile, DocFolderNode, DocumentsHealth, InfoRequirementsCascade,
  ModuleRecord, NamingAudit, NamingCheck, PreflightGate } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withDocuments<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Documents extends Base {
  // --- Document control / file manager (F1-F6) ---------------------------------
  documentsTree(pid: string) {
    return this.json<{ project: string; total_files: number; required_gaps: string[];
      nodes: DocFolderNode[] }>(`/projects/${pid}/documents/tree`);
  }
  documentsFolder(pid: string, path: string, superseded = false) {
    const q = `?path=${encodeURIComponent(path)}${superseded ? "&superseded=true" : ""}`;
    return this.json<{ folder: string; owner_role: string | null; valid_folder: boolean;
      count: number; files: DocFile[] }>(`/projects/${pid}/documents/folder${q}`);
  }
  documentsByRole(pid: string, role: string) {
    return this.json<{ role: string; count: number; folders: DocFolderNode[] }>(
      `/projects/${pid}/documents/by-role?role=${encodeURIComponent(role)}`);
  }
  /** Document-control health: naming, required-folder coverage, revision control, CDE spread, and
   *  the documents filed outside the standard taxonomy.
   *
   *  DOCHEALTH-VACUOUS. The inline type this replaces left out `orphans` and `note`, and declared
   *  `required_missing` and `by_cde_state` that the only caller never rendered — so a strip printing
   *  `required coverage 18.2%` had the missing nine folders in hand and threw them away. */
  documentsHealth(pid: string) {
    return this.json<DocumentsHealth>(`/projects/${pid}/documents/health`);
  }
  documentsPhaseGaps(pid: string, phase: string) {
    return this.json<{ phase: string; missing: number;
      /** `bool(items) and not missing` — it REQUIRES a recognised phase. It used to be
       *  `not missing` over a checklist that is EMPTY for a phase the server does not know, so
       *  `?phase=NONSENSE` answered `true`. */
      complete: boolean;
      /** False when the phase is not one the checklist covers. Declared so a derivation over
       *  declarations can see it — `services/api/test_verdict_coverage.py` reads this as
       *  `complete`'s coverage, and a consumer rendering the verdict without it is reported bare. */
      known_phase: boolean;
      known_phases: string[];
      /** The refusal, with the known phases named, so a caller can fix the call from it alone. */
      refused: string | null;
      items: { folder: string; description: string; present: boolean }[] }>(
      `/projects/${pid}/documents/phase-gaps?phase=${encodeURIComponent(phase)}`);
  }
  async uploadDocument(pid: string, path: string, file: File,
      meta: { title?: string; discipline?: string; doc_type?: string; cde_state?: string } = {}) {
    const fd = new FormData();
    fd.append("path", path); fd.append("file", file);
    for (const [k, v] of Object.entries(meta)) if (v) fd.append(k, v);
    const res = await fetch(this.url(`/projects/${pid}/documents/upload`),
      { method: "POST", headers: this.authHeaders(), body: fd });
    if (!res.ok) throw new HttpError((await res.text()) || `upload failed (${res.status})`, res.status);
    return res.json() as Promise<{ entry: DocFile; naming: { valid: boolean; issues: string[] };
      superseded: string | null }>;
  }
  async moveDocument(pid: string, fid: string, path: string) {
    const fd = new FormData(); fd.append("path", path);
    const res = await fetch(this.url(`/projects/${pid}/documents/${fid}/move`),
      { method: "POST", headers: this.authHeaders(), body: fd });
    if (!res.ok) throw new HttpError((await res.text()) || `move failed (${res.status})`, res.status);
    return res.json() as Promise<DocFile>;
  }
  deleteDocument(pid: string, fid: string, hard = false) {
    return this.json<{ deleted: string }>(`/projects/${pid}/documents/${fid}${hard ? "?hard=true" : ""}`,
      { method: "DELETE" });
  }
  documentDownloadUrl(pid: string, fid: string) {
    return this.url(`/projects/${pid}/documents/${fid}/download`);
  }
  /** Filed revisions of the authored model (newest first), including superseded ones. */
  modelHistory(pid: string) {
    return this.json<{
      folder: string; count: number; model_present: boolean;
      revisions: { title?: string; revision?: string; cde_state?: string; id?: string }[];
    }>(`/projects/${pid}/documents/model-history`);
  }
  /** File the current source IFC into `12_Model/IFC` as a revision (explicit act, not on every edit). */
  async fileModel(pid: string, title = "Federated Model") {
    const fd = new FormData();
    fd.append("title", title);
    const res = await fetch(this.url(`/projects/${pid}/documents/file-model`),
      { method: "POST", headers: this.authHeaders(), body: fd });
    if (!res.ok) throw new HttpError((await res.text()) || `file model failed (${res.status})`, res.status);
    return res.json() as Promise<Record<string, unknown>>;
  }

  /** bep — BIM Execution Plan generated from the project's live config (always current). */
  bep(pid: string) {
    return this.json<{
      project: { id: string; name: string; has_model: boolean } | null;
      sections: { id: string; title: string; configured: boolean; summary: string;
        items: { k: string; v: string }[] }[];
      completeness: { configured: number; total: number; pct: number }; note: string;
    }>(`/projects/${pid}/bep`);
  }
  /** cdeStatus — CDE container counts by state and suitability. */
  cdeStatus(pid: string) {
    return this.json<{ total: number; by_state: Record<string, number>;
      by_suitability: Record<string, number>;
      discipline: { revision_control_pct: number | null; approval_status_pct: number | null;
        metadata_completeness_pct: number | null; published: number; archived: number };
      note: string }>(`/projects/${pid}/cde/status`);
  }
  /** infoRequirementsRegister — OIR/PIR/AIR/EIR coverage of the requirements register. */
  infoRequirementsRegister(pid: string) {
    return this.json<{ total: number;
      by_type: Record<string, { total: number; issued: number; draft: number; superseded: number }>;
      core_coverage: { required: string[]; missing: string[]; complete: boolean }; note: string }>(
      `/projects/${pid}/info-requirements/register`);
  }
  /** ISO 19650 requirement flow-down (OIR→PIR/AIR→EIR→MIDP/TIDP) via each record's derives_from,
   *  with cascade health: orphans that don't trace up, dangling parent references, and links
   *  pointing the wrong way.
   *
   *  CASCADE-DARK. The inline type this replaces declared seven keys and left out the two that ARE
   *  the cascade — `nodes` and `children` — so the tree was unreachable from any TypeScript and a
   *  card named "Requirement flow-down" could only print its summary statistics. */
  infoRequirementsCascade(pid: string) {
    return this.json<InfoRequirementsCascade>(`/projects/${pid}/info-requirements/cascade`);
  }
  /** MIDP/TIDP delivery plan — requirements vs programme dates, overdue/due-soon, LOIN coverage. */
  infoRequirementsDeliveryPlan(pid: string) {
    type Item = { id: string; ref: string | null; title: string | null; type: string;
      due_date: string | null; status: string; has_loin: boolean };
    return this.json<{ total: number; overdue: number; due_soon: number; loin_coverage_pct: number | null;
      next_deliverable: Item | null;
      by_month: { month: string; total: number; issued: number; overdue: number }[];
      items: Item[]; note: string }>(
      `/projects/${pid}/info-requirements/delivery-plan`);
  }
  /** ISO 19650-6 exchange acceptance — non-WIP containers vs completeness/suitability/auth/traceability. */
  cdeExchangeAcceptance(pid: string) {
    return this.json<{ reviewed: number; accepted: number; nonconforming_count: number; acceptable: boolean;
      criteria_pct: { completeness: number | null; suitability: number | null; authorization: number | null; traceability: number | null };
      nonconforming: { id: string; ref: string | null; title: string | null; state: string; failed: string[] }[]; note: string }>(
      `/projects/${pid}/cde/exchange-acceptance`);
  }

  /** reports — catalog of available reports (id, name, group). */
  reports() {
    return this.json<{ reports: { id: string; name: string; group: string }[] }>(`/reports`);
  }
  /** reportUrl — generated report download; fmt = pdf | xlsx. */
  reportUrl(pid: string, report: string, fmt: "pdf" | "xlsx") {
    return this.url(`/projects/${pid}/reports/${report}.${fmt}`);
  }

  /** closeoutSummary — punchlist, commissioning, warranties, O&M. */
  closeoutSummary(pid: string) {
    return this.json<{
      punchlist: { punch_count: number; verified_count: number; open_count: number;
        overdue_count: number; complete_pct: number | null; open_cost: number;
        ball_in_court: Record<string, number>; by_trade: Record<string, number>;
        rows: Record<string, unknown>[] };
      /**
       * CX-CELL-FLAT: `by_result`, `by_test_type` and `by_state` were served and not declared.
       * They are where the third state and the unphased test are already named — `by_result`
       * buckets `(pending)` and any free-form value, `by_test_type` buckets `(unspecified)` — and
       * `pass_rate` is taken over `passed + failed + conditional`, so it is a rate over DECIDED
       * tests, not over `cx_count`. The matrix one method down had none of this.
       */
      commissioning: { cx_count: number; passed: number; failed: number; conditional: number;
        accepted: number; pass_rate: number | null; by_result: Record<string, number>;
        by_test_type: Record<string, number>; by_state: Record<string, number> };
      certificates: { cert_count: number; by_type: Record<string, number> };
      /**
       * EXPIRY-UNDATED: `no_expiry` and `rows` were SERVED and not declared, so the one number
       * that says "these were not evaluated" was dropped at this boundary — invisible to the
       * compiler, the linter and every audit built on these interfaces. `responseUndeclared.test.ts`
       * could not catch it either: its server half reads routes that RETURN A DICT LITERAL, and
       * `closeout_summary` returns `closeout_engine.closeout_summary(...)`, so the route is not in
       * its population at all. *A gate scoped by the shape of the return statement cannot see a
       * route that delegates.*
       */
      warranties: { warranty_count: number; active: number; expired: number; expiring_soon: number;
        no_expiry: number; by_type: Record<string, number>;
        rows: { ref?: string; name?: string; vendor?: string; warranty_type: string;
          expires?: string; status: string }[] };
      om_manuals: { om_count: number; accepted: number; accepted_pct: number | null };
    }>(`/projects/${pid}/closeout/summary`);
  }

  // --- Commissioning (CX-1): the detail behind closeoutSummary's `commissioning` rollup ---
  /** Seed asset_register from the model's equipment classes (GUID-deduped) + phase-typed
   *  commissioning checklists with MEP FPT expected values. */
  cxSeed(pid: string, checklists = true) {
    return this.json<{ model_scored: boolean; created: number; skipped_existing: number;
      capped?: boolean; note?: string;
      checklists?: { created: number; capped?: boolean } }>(
      `/projects/${pid}/cx/seed${checklists ? "" : "?checklists=false"}`, { method: "POST" });
  }
  /** The system × phase completion matrix.
   *
   *  CX-CELL-FLAT. The response is declared as `CxMatrix` rather than inline because an inline
   *  `this.json<{…}>` type argument is outside `apps/web/src/api/deadFieldTyped.test.ts`'s
   *  population — which is how the missing `conditional` survived here while `closeoutSummary`,
   *  twenty lines up in this same class, declared it on the ROLLUP over the same module.
   */
  cxMatrix(pid: string) {
    return this.json<CxMatrix>(`/projects/${pid}/cx/matrix`);
  }
  /** The per-system turnover dossier. */
  cxDossier(pid: string, system: string) {
    return this.json<{ system: string; asset_count: number; test_count: number; accepted: number;
      complete_pct: number; open_punch_mentions: number;
      assets: { ref?: string; name?: string; tag?: string; location?: string; guid?: string }[];
      tests: Record<string, { ref?: string; asset?: string; state?: string; result?: string;
        date?: string; cx_agent?: string; deficiencies?: string }[]>;
      expected_values: Record<string, unknown>; note?: string }>(
      `/projects/${pid}/cx/dossier?system=${encodeURIComponent(system)}`);
  }
  /** The pre-flight issuance gate — PASS/HOLD verdict + checklist, every check deep-linked. */
  preflight(pid: string) {
    return this.json<PreflightGate>(`/projects/${pid}/preflight`);
  }

  // SCALE-SEAM (81) — *is this project ready for substantial completion, and certify it?*
  // Sits with `closeoutSummary`, which ❿ brought in under *is turnover actually closing?*
  // Readiness and the G704 certificate are the same question one step further on.
  turnoverReadiness(pid: string) {
    return this.json<{ punch: { count: number; verified: number; open: number;
      complete_pct: number | null; overdue: number; open_cost: number };
      punch_list_prepared: boolean; latest_model_version: number | null;
      ready_for_substantial_completion: boolean }>(`/projects/${pid}/turnover/readiness`);
  }
  /** Turnover status — readiness, the substantial-completion record if one exists, and whether the record model is locked. */
  turnoverStatus(pid: string) {
    return this.json<{ readiness: { ready_for_substantial_completion: boolean };
      substantial_completion: { ref: string; record_model_version: number | null; signed_by: string[] } | null;
      record_model_locked: boolean }>(`/projects/${pid}/turnover/status`);
  }
  /** Issue the substantial-completion certificate (architect / owner / contractor signatories, occupancy date). */
  turnoverCertify(pid: string, certRid: string, architect: string, owner?: string, contractor?: string, occupancyDate?: string) {
    return this.json<{ certificate: ModuleRecord; readiness: unknown }>(
      `/projects/${pid}/turnover/certify`, { method: "POST",
      body: JSON.stringify({ cert_rid: certRid, architect, owner, contractor, occupancy_date: occupancyDate }) });
  }
  /** URL of the AIA G704 substantial-completion certificate PDF for one certificate record. */
  g704Url(pid: string, certRid: string) {
    return this.url(`/projects/${pid}/contracts/completion_certificate/${certRid}/document.pdf?doc=g704`);
  }

  // SCALE-SEAM (82) — *how well does this project follow its own naming rules?* It arrived here as
  // a pair with "namingConventions", which (82) declined to split off because the two answered one
  // question about one subject. **NAMING-UNREAD deleted the other half instead**: `audit()` returns
  // `conventions()` — the same object, byte-identical, measured — so a second route for it is a
  // strict subset of this one, and `services/api/test_route_reachability.py` already holds the rule
  // that *a route whose payload is a strict subset of another route's is not a second capability*.
  // The card was fetching the basis from that route with `.catch(() => null)` beside the audit it
  // belongs to, which made the convention optional while the percentage it qualifies was not.
  namingAudit(pid: string) {
    return this.json<NamingAudit>(`/projects/${pid}/naming/audit`);
  }
  /** Check ONE name against the convention, without touching a register — the fix loop for a
   *  violation row, and a check to run before filing a container or numbering a sheet.
   *
   *  `/naming/validate` sat in `UNREACHABLE_ROUTES` with no client method at all: the audit could
   *  tell a reader that `New file (2).pdf` is wrong and the product had no way to tell them whether
   *  the name they were about to use instead is right. */
  namingValidate(pid: string, name: string, kind: "container" | "sheet" = "container") {
    return this.json<NamingCheck>(`/projects/${pid}/naming/validate`
      + `?name=${encodeURIComponent(name)}&kind=${kind}`);
  }
  };
}
