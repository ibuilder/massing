import type { ApiClient } from "../../api/client";
import { escapeHtml as esc, withLoading } from "../../ui/feedback";
import { kvTable, resultNote, showResult } from "../../ui/result";

/**
 * CITED-ASK-DARK — the answer whose every claim traces to the GUIDs it came from, and nothing called
 * it.
 *
 * `/projects/{pid}/answer/cited-query` runs a QUERY-DSL selector over the property index and returns
 * a **CitedAnswer**: prose, plus per-claim citations (IFC GUID / document+revision+sheet / record ref
 * / rule id), a `coverage` fraction, `fully_cited`, the INDICES of any uncited claims,
 * `source_types`, `matched`/`truncated`, and `conflicts` — two sources disagreeing about one target,
 * with both values and each one's provenance. The route's own docstring calls it *"the first producer
 * of the provenance contract shared by the AI command bar / RFI-QA / KG answers"*, and
 * `apps/web/src/api/clientCallers.test.ts` froze its client method as called by nothing.
 *
 * **What it is NOT, because the first reading of it here was wrong.** It looked like the cited
 * upgrade to the shipped Project assistant, which is a tidy story and false: the route takes a
 * **selector**, not a question, and 422s on anything else. `askProject` is the natural-language door
 * and degrades to a computed snapshot with no API key. They are different tools, and merging them
 * would have replaced a working NL box with a selector box. *A plausible framing is the expensive
 * kind of wrong, because nothing about it looks like a mistake.*
 *
 * ## Three things the render has to carry
 *
 * **① A claim cites a SAMPLE of what it is about.** `cited_query` takes `sample: int = 25` and the
 * route never overrides it, so a claim reading *"1,438 element(s) match"* carries 25 citations. The
 * count and the provenance are different sizes, which is TRUNC-COUNTED with the page on the evidence
 * side. Detected by comparing a claim's citations against `matched` rather than against the cap,
 * because a rule keyed on the number 25 stops being true the day somebody passes `sample`.
 *
 * **② `fully_cited` is a verdict and an EMPTY answer scores perfectly.** `build()` computes
 * `coverage = len(cited)/len(claims) if claims else 1.0` with `fully_cited = not uncited`, so zero
 * claims come back `coverage: 1.0, fully_cited: true` and the server's own note says *"fully
 * cited."* **Measured reach: not reachable through this route** — `cited_query` always emits at
 * least the match claim — but `build` is the shared contract and `rfi_qa.py` is already a second
 * caller, so it is a trap for the next producer rather than a shipped bug. The reading refuses it
 * anyway, because the consumer of a shared contract has to be right for every producer and this one
 * costs a branch.
 *
 * **③ A conflict is the sharpest thing in the response and the easiest to drop.** Two sources
 * disagreeing about one target is the question this product exists to answer; an answer that renders
 * the prose and swallows the conflict states one side of a disagreement as fact.
 */
export type CitedAnswer = Awaited<ReturnType<ApiClient["citedQuery"]>>;
type Claim = CitedAnswer["claims"][number];
type CitationRef = Claim["citations"][number];

export interface CitationReading {
  /** `none` — no claims, so the server's 100% is about nothing. `conflict` — sources disagree.
   *  `uncited` — some claim rests on nothing. `partial` — cited, but over sampled evidence.
   *  `cited` — every claim backed, nothing sampled away. */
  kind: "none" | "conflict" | "uncited" | "partial" | "cited";
  headline: string;
  detail: string;
  tone: "ok" | "warn" | "bad" | "";
}

/** Claims that cite fewer elements than they are about — see ① above. */
export function sampledClaims(a: CitedAnswer): number[] {
  return a.claims
    .map((c, i) => (c.citations.length && c.citations.length < a.matched ? i : -1))
    .filter((i) => i >= 0);
}

/**
 * The reading, in plain text — `escapeHtml` is applied at the render and every string here may carry
 * a document title or a property value.
 *
 * Ordered by what changes the reader's action: a disagreement between sources outranks a coverage
 * gap, which outranks evidence that was sampled.
 */
export function citationReading(a: CitedAnswer): CitationReading {
  const n = a.claims.length;
  if (!n) {
    return {
      kind: "none", tone: "",
      headline: "No claims",
      detail: "the query produced nothing to cite, so the 100% coverage the response reports is "
        + "about an empty answer rather than a sourced one.",
    };
  }
  const pct = `${Math.round(a.coverage * 1000) / 10}%`;
  const cited = `${n} claim(s) · ${pct} cited · ${a.citation_count} citation(s)`;
  if (a.conflicts.length) {
    return {
      kind: "conflict", tone: "bad",
      headline: `${a.conflicts.length} source conflict(s)`,
      detail: `${cited} — but sources DISAGREE about `
        + `${a.conflicts.map((c) => c.target).join(", ")}. Both values are below with their `
        + "provenance; the answer above states one of them.",
    };
  }
  if (a.uncited_claims.length) {
    const which = a.uncited_claims.map((i) => a.claims[i]?.text).filter(Boolean);
    return {
      kind: "uncited", tone: "warn",
      headline: `${a.uncited_claims.length} of ${n} claim(s) rest on nothing`,
      detail: `${cited}. Uncited: ${which.join(" / ")}`,
    };
  }
  const sampled = sampledClaims(a);
  if (sampled.length || a.truncated) {
    return {
      kind: "partial", tone: "warn",
      headline: `Every claim is cited, over SAMPLED evidence`,
      detail: `${cited} — but ${a.truncated ? "the selector's own result was truncated, and " : ""}`
        + `${sampled.length} claim(s) cite fewer elements than they are about `
        + `(${a.matched} matched). The provenance is a sample, not the set.`,
    };
  }
  return {
    kind: "cited", tone: "ok",
    headline: "Fully cited",
    detail: `${cited}, and every claim's provenance covers the ${a.matched} element(s) it is about.`,
  };
}

/** One citation, in the terms of its own source type — a GUID and a sheet are not interchangeable. */
export function citeLabel(c: CitationRef): string {
  switch (c.source_type) {
    case "ifc":
      return `IFC ${(c.guid ?? "?").slice(0, 8)}${c.revision ? ` @${c.revision}` : ""}`;
    case "doc":
      return `doc ${c.document_id ?? "?"}${c.sheet ? ` sheet ${c.sheet}` : ""}`
        + `${c.page != null ? ` p.${c.page}` : ""}${c.revision ? ` rev ${c.revision}` : ""}`;
    case "record":
      return `record ${c.record_ref ?? "?"}`;
    case "rule":
      return `rule ${c.rule_id ?? "?"}`;
    default:
      return String(c.source_type);
  }
}

/** One row per claim: what it says, what backs it, and whether that is all of what it is about. */
export function claimRows(a: CitedAnswer): { k: string; v: string; strong?: boolean }[] {
  const uncited = new Set(a.uncited_claims);
  const sampled = new Set(sampledClaims(a));
  return a.claims.map((c, i) => ({
    k: c.text,
    v: uncited.has(i)
      ? "NO citation — this claim rests on nothing"
      : `${c.citations.length} citation(s): ${c.citations.slice(0, 4).map(citeLabel).join(", ")}`
        + (c.citations.length > 4 ? ` +${c.citations.length - 4} more` : "")
        + (sampled.has(i) ? ` — a SAMPLE of the ${a.matched} it is about` : "")
        + (typeof c.confidence === "number" ? ` · confidence ${c.confidence}` : ""),
    strong: uncited.has(i),
  }));
}

/** Each conflict as one line naming both values and where each came from. */
export function conflictLines(a: CitedAnswer): string[] {
  return a.conflicts.map((c) =>
    `${c.target}: ${c.values.join(" vs ")} — `
    + c.claims.map((cl) => `${String(cl.value)} per ${cl.citations.map(citeLabel).join(", ") || "nothing"}`)
        .join(" / "));
}

export interface CitedAnswerDeps {
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  api: ApiClient;
  pid: string;
  container: HTMLElement;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
}

/**
 * Named `*Button` and inlined into its caller's append — the convention
 * `sectionButtonsWired.test.ts` derives its population from, and the one mutation that survived
 * MACRO-DARK's first pass.
 */
export function citedAnswerButton(d: CitedAnswerDeps): HTMLButtonElement {
  const btn = d.toolBtn2("📎 Cited answer (provenance for a selector)", () => {
    showResult("Cited answer — every claim traces to its source", (body) => {
      body.appendChild(resultNote("Ask the model a QUERY-DSL question and get the answer <b>with the "
        + "GUIDs, documents, records and rules each claim rests on</b>. Add a property to break the "
        + "match down by its values. Combine terms with <b>&amp;</b>: "
        + "<code>IfcWall &amp; storey=L3</code>.", ""));
      const row = document.createElement("div");
      row.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:6px 0";
      const sel = document.createElement("input");
      sel.className = "portal-filter";
      sel.style.cssText = "flex:1 1 220px;min-width:0;font-size:12px";
      sel.placeholder = "IfcWall & storey=L3"; sel.value = "IfcWall";
      const prop = document.createElement("input");
      prop.className = "portal-filter";
      prop.style.cssText = "flex:0 1 190px;min-width:0;font-size:12px";
      prop.placeholder = "Pset_WallCommon.FireRating (optional)";
      const run = document.createElement("button");
      run.className = "mini-btn on"; run.textContent = "Ask";
      row.append(sel, prop, run);
      const out = document.createElement("div"); out.style.marginTop = "6px";
      body.append(row, out);

      const exec = () => withLoading(d.container, "Tracing every claim to its source", async () => {
        const q = sel.value.trim();
        if (!q) { d.notify("enter a selector first", "info"); return; }
        out.replaceChildren();
        let a: CitedAnswer;
        try { a = await d.api.citedQuery(d.pid, q, prop.value.trim() || undefined); }
        catch (e) { out.appendChild(resultNote(esc((e as Error).message), "bad")); return; }
        const r = citationReading(a);
        // The ANSWER first — it is what was asked for — then what it rests on, because a reader who
        // stops after the prose must at least have seen the verdict beside it.
        out.appendChild(resultNote(`<b>${esc(a.answer || "(no answer)")}</b>`, ""));
        out.appendChild(resultNote(`<b>${esc(r.headline)}</b> — ${esc(r.detail)}`, r.tone));
        for (const line of conflictLines(a)) {
          out.appendChild(resultNote(`⚠ ${esc(line)}`, "bad"));
        }
        if (a.claims.length) out.appendChild(kvTable(claimRows(a)));
        const types = Object.entries(a.source_types);
        if (types.length) {
          out.appendChild(resultNote(`Sources: ${types.map(([t, n]) => `${esc(t)} ${n}`).join(" · ")}`,
                                     ""));
        }
        out.appendChild(resultNote(esc(a.note), ""));
      });
      run.onclick = () => void exec();
      sel.onkeydown = (e) => { if (e.key === "Enter") void exec(); };
      prop.onkeydown = (e) => { if (e.key === "Enter") void exec(); };
      sel.focus();
    });
  });
  btn.title = "Answer a QUERY-DSL question with the provenance of every claim — IFC GUIDs, documents "
    + "with their revision, records and rules — plus what the answer does NOT cite and where two "
    + "sources disagree.";
  return btn;
}
