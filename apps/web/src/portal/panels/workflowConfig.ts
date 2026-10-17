import type { WorkflowTransition } from "../../api/types";
import { escapeHtml as esc, toast } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * WFE-3 — per-project workflow overrides, made reachable (WORKFLOW-DARK).
 *
 * `services/api/src/aec_api/workflow_config.py` exists because module workflows ship as `module.json`
 * defaults that are *"sensible for most jobs, wrong for some"*: one owner wants a second approval
 * before a change order executes, another runs submittals without a consultant review. An override
 * rewires which of the module's **declared** states connect — it may never invent new ones.
 *
 * **All three routes had no client method**, so the whole capability was server-only: the effective
 * workflow, the override, and the reset.
 *
 * ### The refusal is the capability, and it had never reached a user
 *
 * `validate()` counts the live records each change would trap and `save()` **refuses** rather than
 * warning:
 *
 * > a stranded record looks identical to a record nobody has got to yet, so it goes unnoticed for as
 * > long as anyone is willing to wait.
 *
 * That is a 422 naming the states and the counts, and it is why `saveProjectWorkflow`'s message is
 * rendered **verbatim** here. The real-world shape of the bug it prevents is a submittal sitting in
 * review for three weeks because somebody removed the only transition out.
 *
 * ### The rules below MIRROR the server, and the server stays the authority
 *
 * `strandedStates`, `duplicatePairs` and `undeclaredStates` reproduce `_norm` and `_reachability` so
 * the editor can mark a problem before the round trip — the same reason `clausePlaybook.ts` mirrors
 * the red-line rule. The mirror is a convenience; the save is the decision, and a disagreement
 * between them is the server's to win. `workflowMirror.test.ts` reads `workflow_config.py` off disk
 * and asserts the three rules are still spelled there, so a mirror cannot outlive what it mirrors.
 *
 * ### Why this screen
 *
 * A workflow override is module METADATA and this is the module-metadata panel, which already holds
 * `ctx.mods` — so the picker needs no extra fetch, and the graph above it answers the neighbouring
 * question of how the modules wire to each other.
 */

export interface WorkflowWire {
  module: string;
  overridden: boolean;
  states: string[];
  initial: string | null;
  transitions: WorkflowTransition[];
  shipped_transitions: WorkflowTransition[];
  record_counts: Record<string, number>;
}

/** States with no transition out, EXCLUDING the ones the shipped workflow also treats as terminal —
 *  *"a genuinely terminal state SHOULD have no exit"* — and only where records actually sit.
 *
 *  All three conditions are the server's, in the server's order. Dropping the shipped-terminal
 *  exclusion would warn about every `closed` state in the product; dropping the record count would
 *  warn about a legal workflow nobody is standing in. */
export function strandedStates(w: WorkflowWire, transitions: readonly WorkflowTransition[]
                               ): Record<string, number> {
  const hasExit = new Set(transitions.map((t) => t.from));
  const shippedExit = new Set(w.shipped_transitions.map((t) => t.from));
  const out: Record<string, number> = {};
  for (const s of w.states) {
    if (hasExit.has(s)) continue;
    if (!shippedExit.has(s)) continue;             // terminal by design, not by this edit
    const n = w.record_counts[s] ?? 0;
    if (n > 0) out[s] = n;
  }
  return out;
}

/** `(from, action)` pairs declared twice. The server refuses them because *"the engine would pick one
 *  arbitrarily"* — which is a worse outcome than a refusal, since both look like a working workflow. */
export function duplicatePairs(transitions: readonly WorkflowTransition[]): string[] {
  const seen = new Set<string>();
  const dup = new Set<string>();
  for (const t of transitions) {
    const k = `${(t.from ?? "").trim()} + ${(t.action ?? "").trim()}`;
    if (seen.has(k)) dup.add(k); else seen.add(k);
  }
  return [...dup].sort();
}

/** States a transition names that the module does not declare. An override may rewire the states a
 *  module HAS, never invent new ones. */
export function undeclaredStates(w: WorkflowWire,
                                 transitions: readonly WorkflowTransition[]): string[] {
  const declared = new Set(w.states);
  const bad = new Set<string>();
  for (const t of transitions) {
    for (const s of [t.from, t.to]) {
      const v = (s ?? "").trim();
      if (v && !declared.has(v)) bad.add(v);
    }
  }
  return [...bad].sort();
}

/** States unreachable from the initial one under this transition list — a mirror of `_reachability`.
 *  Reported, never refused: the server reports it too, because a state that already holds records got
 *  there under the old workflow and that is the operator's call. */
export function unreachableStates(w: WorkflowWire,
                                  transitions: readonly WorkflowTransition[]): string[] {
  const edges = new Map<string, string[]>();
  for (const t of transitions) {
    if (!edges.has(t.from)) edges.set(t.from, []);
    edges.get(t.from)!.push(t.to);
  }
  const seen = new Set<string>();
  const stack = w.initial ? [w.initial] : [];
  while (stack.length) {
    const s = stack.pop()!;
    if (seen.has(s)) continue;
    seen.add(s);
    stack.push(...(edges.get(s) ?? []));
  }
  return w.states.filter((s) => !seen.has(s));
}

const tkey = (t: WorkflowTransition) => `${t.from}|${t.action}|${t.to}`;

/** What this override changes against the shipped workflow, so a reader can see the EDIT rather than
 *  the result — the question "what did I change" has no other answer on this screen. */
export function diffVsShipped(w: WorkflowWire, transitions: readonly WorkflowTransition[]
                              ): { added: string[]; removed: string[] } {
  const now = new Set(transitions.map(tkey));
  const was = new Set(w.shipped_transitions.map(tkey));
  return {
    added: [...now].filter((k) => !was.has(k)).sort(),
    removed: [...was].filter((k) => !now.has(k)).sort(),
  };
}

export function renderWorkflowConfig(ctx: PanelContext, host: HTMLElement, pid: string): void {
  const withWorkflow = ctx.mods.filter((m) => (m.workflow?.states ?? []).length > 1);
  host.innerHTML = "";
  const intro = document.createElement("div"); intro.className = "meta";
  intro.style.marginBottom = "6px";
  intro.textContent = "Rewire which of a module's declared states connect, for this project only. "
    + "An override may not invent states, and it is refused outright when it would leave records "
    + "sitting in a state with no way out — a stranded record looks exactly like one nobody has got "
    + "to yet. Admin only.";
  host.appendChild(intro);

  if (!withWorkflow.length) {
    host.insertAdjacentHTML("beforeend",
      `<div class="meta">No module with a multi-state workflow is loaded.</div>`);
    return;
  }

  const bar = document.createElement("div");
  bar.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:6px";
  const pick = document.createElement("select"); pick.className = "portal-filter";
  pick.setAttribute("aria-label", "Module whose workflow to override");
  for (const m of withWorkflow) {
    const o = document.createElement("option"); o.value = m.key; o.textContent = m.name;
    pick.appendChild(o);
  }
  const badge = document.createElement("span"); badge.className = "meta";
  const reset = document.createElement("button"); reset.className = "selset-del";
  reset.textContent = "↺ reset to shipped";
  reset.title = "Drop this project's override and return to the module's shipped workflow";
  bar.append(pick, badge, reset);
  const body = document.createElement("div");
  const foot = document.createElement("div"); foot.style.marginTop = "8px";
  const save = document.createElement("button"); save.className = "tool-btn on";
  save.textContent = "Save workflow";
  const msg = document.createElement("div"); msg.className = "meta"; msg.style.marginTop = "6px";
  msg.setAttribute("role", "status");
  foot.appendChild(save);
  host.append(bar, body, foot, msg);

  let wire: WorkflowWire | null = null;
  let draft: WorkflowTransition[] = [];

  const load = async () => {
    body.innerHTML = `<div class="meta">reading the workflow…</div>`;
    msg.textContent = "";
    try {
      wire = await ctx.host.api.projectWorkflow(pid, pick.value) as WorkflowWire;
      // SPREAD, not rebuilt: `party` and `requires` are stored on a transition and this editor does
      // not author either, so a fresh object would delete them from every transition touched — the
      // AUTHORITY-SUPERSEDE shape, where the loss is proportional to how much was edited.
      draft = wire.transitions.map((t) => ({ ...t }));
      paint();
    } catch (e) {
      body.innerHTML = `<div class="meta">Workflow unavailable: ${esc((e as Error).message)}</div>`;
    }
  };

  const paint = () => {
    const w = wire;
    if (!w) return;
    badge.textContent = w.overridden ? "· overridden for this project" : "· shipped workflow";
    badge.style.color = w.overridden ? "var(--status-warn)" : "";
    reset.style.display = w.overridden ? "" : "none";
    body.innerHTML = "";

    // The states, WITH their record counts — the constraint, which the route hands over for exactly
    // this reason: "that is what constrains any change you make".
    const states = document.createElement("div"); states.className = "meta";
    states.style.margin = "2px 0 6px";
    states.innerHTML = "States: " + w.states.map((s) => {
      const n = w.record_counts[s] ?? 0;
      return `<b>${esc(s)}</b>${s === w.initial ? " (initial)" : ""}`
        + (n ? ` <span style="color:var(--status-warn)">· ${n} record(s) here</span>` : "");
    }).join(" · ");
    body.appendChild(states);

    draft.forEach((t, i) => {
      const row = document.createElement("div");
      row.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:3px 0";
      const sel = (value: string, set: (v: string) => void) => {
        const el = document.createElement("select"); el.className = "portal-filter";
        el.style.cssText = "font-size:12px";
        for (const s of w.states) {
          const o = document.createElement("option"); o.value = s; o.textContent = s;
          el.appendChild(o);
        }
        // `select.value` after appending, never `option.selected` in the loop — see the measured
        // note in panels/clausePlaybook.ts.
        el.value = value;
        el.onchange = () => { set(el.value); paint(); };
        return el;
      };
      const act = document.createElement("input"); act.className = "portal-filter";
      act.value = t.action ?? ""; act.placeholder = "action"; act.maxLength = 40;
      act.style.cssText = "flex:0 0 150px;font-size:12px";
      act.oninput = () => { t.action = act.value; };
      const del = document.createElement("button"); del.className = "selset-del";
      del.textContent = "✕";
      del.onclick = () => { draft.splice(i, 1); paint(); };
      row.append(sel(t.from, (v) => { t.from = v; }),
                 Object.assign(document.createElement("span"), { className: "meta", textContent: "—" }),
                 act,
                 Object.assign(document.createElement("span"), { className: "meta", textContent: "→" }),
                 sel(t.to, (v) => { t.to = v; }), del);
      if ((t.party ?? []).length || (t as { requires?: string[] }).requires?.length) {
        const keep = document.createElement("span"); keep.className = "meta"; keep.style.opacity = ".8";
        keep.textContent = "carried through: "
          + [(t.party ?? []).join("/"), ((t as { requires?: string[] }).requires ?? []).join("/")]
            .filter(Boolean).join(" · ");
        row.appendChild(keep);
      }
      body.appendChild(row);
    });

    const add = document.createElement("button"); add.className = "tool-btn";
    add.textContent = "＋ transition";
    add.onclick = () => {
      draft.push({ from: w.initial ?? w.states[0]!, to: w.states[w.states.length - 1]!,
                   action: "", party: [] });
      paint();
    };
    body.appendChild(add);

    // The problems, mirrored from the server so they are visible BEFORE the round trip.
    const probs: string[] = [];
    const stranded = strandedStates(w, draft);
    if (Object.keys(stranded).length) {
      probs.push("⛔ would strand live records: "
        + Object.entries(stranded).map(([s, n]) => `${n} in “${s}”`).join(", ")
        + " — add a transition out of those states, or move the records first");
    }
    for (const d of duplicatePairs(draft)) probs.push(`⛔ duplicate transition ${d}`);
    for (const u of undeclaredStates(w, draft)) probs.push(`⛔ ${u} is not a state this module declares`);
    const unreach = unreachableStates(w, draft)
      .filter((s) => (w.record_counts[s] ?? 0) === 0);
    const unreachHeld = unreachableStates(w, draft)
      .filter((s) => (w.record_counts[s] ?? 0) > 0);
    if (probs.length) {
      const box = document.createElement("div"); box.className = "meta";
      box.style.cssText = "margin-top:6px;color:var(--status-crit)";
      box.innerHTML = probs.map((x) => `<div>${esc(x)}</div>`).join("");
      body.appendChild(box);
    }
    // Reported, not refused — the server reports these too, for the operator to decide.
    if (unreach.length || unreachHeld.length) {
      const note = document.createElement("div"); note.className = "meta";
      note.style.cssText = "margin-top:4px;color:var(--status-warn)";
      note.textContent = [
        unreach.length ? `unreachable from “${w.initial}”: ${unreach.join(", ")}` : "",
        unreachHeld.length
          ? `unreachable but still holding records: ${unreachHeld.join(", ")} — they got there under `
            + "the old workflow, which is legal and yours to decide about"
          : "",
      ].filter(Boolean).join(" · ");
      body.appendChild(note);
    }

    const d = diffVsShipped(w, draft);
    const diff = document.createElement("div"); diff.className = "meta";
    diff.style.cssText = "margin-top:6px;opacity:.85";
    diff.textContent = d.added.length || d.removed.length
      ? `vs shipped: ${d.added.length} added, ${d.removed.length} removed`
        + (d.removed.length ? ` (removed: ${d.removed.join("; ")})` : "")
      : "identical to the shipped workflow";
    body.appendChild(diff);
  };

  pick.onchange = () => void load();
  reset.onclick = async () => {
    reset.disabled = true;
    try {
      await ctx.host.api.resetProjectWorkflow(pid, pick.value);
      toast("Override dropped — back to the shipped workflow", "success");
      await load();
    } catch (e) { msg.textContent = `Reset failed: ${(e as Error).message}`; }
    reset.disabled = false;
  };
  save.onclick = async () => {
    if (!draft.length) { msg.textContent = "A workflow needs at least one transition."; return; }
    save.disabled = true; msg.textContent = "saving…";
    try {
      const res = await ctx.host.api.saveProjectWorkflow(pid, pick.value, draft);
      msg.textContent = `Saved ${res.saved} transition(s).`;
      toast("Workflow override saved", "success");
      await load();
    } catch (e) {
      // VERBATIM. The 422 names the states and the counts — "2 in 'review'" — and that is the whole
      // content of the refusal this capability exists for. "Save failed" would throw it away.
      msg.textContent = `Refused: ${(e as Error).message}`;
    } finally {
      save.disabled = false;
    }
  };
  void load();
}
