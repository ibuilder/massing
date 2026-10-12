import type { NoticeItem, NoticeRegister } from "../../api/contracts";
import { noProjectHtml } from "../../ui/empty";
import { escapeHtml as esc, toast } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * NOTICE-CLOCK-DARK — the contractual notice register, its clause library and its letter drafter all
 * shipped, and no screen reached any of them.
 *
 * A contract gives you a fixed number of days to notify the other party of an event before you lose
 * the right to be paid or given time for it. `notice_clock` counts those days from the field record
 * already in the platform, and it is one of the most careful engines in the tree: its header
 * enumerates three counting traps, it refuses to pick a contract family, it reports `indeterminate`
 * and names the missing field rather than substituting a date — *"a claimant told the bar has fallen
 * abandons a claim that was live"* — and it says whether a holiday list was supplied for every
 * business-day count.
 *
 * **Every one of those refusals is a thing a screen can throw away**, which is what this module
 * exists not to do:
 *
 *  - **No family adopted → render the reason, never an empty table.** `items: []` with
 *    `adopted: false` and `items: []` with nothing due look identical, and one of them means
 *    "nothing has been computed at all".
 *  - **The coverage comes before the counts.** NOTICE-CLOCK-TRUNC: the register used to be computed
 *    over the OLDEST 500 records of each source, so "0 expired" could be a statement about the
 *    wrong half of the project. `complete` is what makes the number mean anything, so it is read
 *    first.
 *  - **`indeterminate` is never folded into `open`.** They are opposite: one is a clock running,
 *    the other is a clock nobody can start, and the fix is a missing field this panel names.
 *  - **A business-day count with no holiday list is short by every public holiday**, and the engine
 *    flags it per item. Nothing else in the app would have shown that flag.
 *  - **An override is a what-if**, computed under a family other than the executed contract, and is
 *    labelled as one.
 */

export interface RegisterNote {
  kind: "no-family" | "override" | "coverage" | "holidays" | "verify";
  headline: string;
  detail: string;
  tone: "ok" | "warn" | "bad" | "";
}

/**
 * Everything about this register the reader has to know BEFORE the numbers, in reading order.
 *
 * A list rather than one reading, because the conditions are independent: a register can be a
 * what-if AND incomplete AND computed without a holiday list. Collapsing them to the worst one
 * would drop two facts a reader needs.
 *
 * The `no-family` case returns alone — with nothing adopted there are no numbers to qualify, and
 * stacking a coverage note under it would imply there was a register to be incomplete.
 */
export function registerNotes(reg: NoticeRegister): RegisterNote[] {
  if (!reg.adopted) {
    return [{
      kind: "no-family", tone: "warn",
      headline: "No contract family is adopted for this project, so nothing has been computed.",
      detail: reg.why || "Notice periods are contract terms and cannot be inferred. Adopt one on "
        + "the prime contract record, having verified it against the executed contract.",
    }];
  }
  const out: RegisterNote[] = [];
  if (reg.override) {
    out.push({
      kind: "override", tone: "warn",
      headline: `Computed under ${reg.override.family}, which is NOT the adopted family.`,
      detail: reg.override.note,
    });
  }
  if (reg.complete === false) {
    out.push({
      kind: "coverage", tone: "warn",
      headline: "Part of the field record was not scanned, so this register is incomplete.",
      detail: (reg.coverage || "") + " Any deadline arising from a record outside that range is "
        + "absent from the counts below — an empty register is not the same as nothing due.",
    });
  }
  // The engine sets this per clock. A business-day count with no holiday list is short by every
  // public holiday in the period, which moves a deadline EARLIER than reported.
  const shortDays = reg.items.filter((i) => i.holidays_supplied === false).length;
  if (shortDays) {
    out.push({
      kind: "holidays", tone: "warn",
      headline: `${shortDays} clock(s) counted business days with no holiday list supplied.`,
      detail: "Every public holiday in the period is a day this count did not add, so the real "
        + "deadline is EARLIER than the one shown. Pass the project's holidays to count them.",
    });
  }
  if (reg.verify) {
    out.push({ kind: "verify", tone: "", headline: "Verify every provision against the executed "
      + "contract.", detail: reg.verify });
  }
  return out;
}

/** The order the register is read in, and the engine's own ranking — not alphabetical. */
export const STATUS_ORDER = ["expired", "due_soon", "open", "indeterminate", "no_clause"] as const;

const STATUS_META: Record<string, { icon: string; label: string; tone: "ok" | "warn" | "bad" | "" }> = {
  expired: { icon: "⛔", label: "period elapsed", tone: "bad" },
  due_soon: { icon: "⚠️", label: "due soon", tone: "warn" },
  open: { icon: "🕒", label: "running", tone: "ok" },
  // NOT a milder "open". A clock nobody can start is a different situation from one with time left,
  // and the engine refuses to substitute a date precisely so this stays visible.
  indeterminate: { icon: "❓", label: "cannot be counted", tone: "warn" },
  no_clause: { icon: "➖", label: "no provision in this library", tone: "" },
};

export function statusMeta(status: string) {
  return STATUS_META[status] || { icon: "•", label: status, tone: "" as const };
}

/** `[status, count]` in reading order, including only what is present. */
export function statusCounts(reg: NoticeRegister): [string, number][] {
  const seen = new Set(STATUS_ORDER as readonly string[]);
  const rows: [string, number][] = STATUS_ORDER
    .map((s) => [s, reg.counts[s] || 0] as [string, number]).filter(([, n]) => n > 0);
  // A status the engine grows that this module does not know about is appended rather than dropped.
  for (const [k, n] of Object.entries(reg.counts)) if (!seen.has(k) && n > 0) rows.push([k, n]);
  return rows;
}

/** One row's worth of what a reader needs: what happened, under which clause, and by when. */
export function itemLine(i: NoticeItem): string {
  const m = statusMeta(i.status);
  const ev = i.event;
  const when = i.due_on ? ` · due ${i.due_on}` : "";
  const left = i.days_remaining == null ? "" : ` · ${i.days_remaining} day(s) left`;
  const cl = i.clause ? ` · ${i.clause.reference} (${i.clause.days} ${i.clause.basis})` : "";
  const basis = ev.date_basis && ev.date_basis !== "occurred"
    // `reported` means the date is when somebody wrote it down, not when it happened — the engine
    // labels it and a screen that hides the label presents a proxy as a fact.
    ? ` · date is when it was ${ev.date_basis}, not when it occurred`
    : "";
  return `${m.icon} <b>${esc(ev.type.replace(/_/g, " "))}</b> ${esc(ev.date)}`
    + `${esc(cl)}${esc(when)}${esc(left)} — ${esc(m.label)}${esc(basis)}`
    + (i.missing?.length ? ` · missing: <b>${esc(i.missing.join(", "))}</b>` : "")
    + (i.why ? `<br><span class="meta">${esc(i.why)}</span>` : "")
    + (i.clause?.citation ? `<br><span class="meta">${esc(i.clause.citation)}</span>` : "");
}

/**
 * The register, the clause library it was measured against, and a letter per item.
 *
 * A portal panel, so it is lazily imported and costs the eager shell nothing — which matters: the
 * shell is within a kilobyte of its budget, and this screen is three fetches and a table.
 */
export async function renderNoticeClock(ctx: PanelContext): Promise<void> {
  const root = ctx.root; root.innerHTML = "";
  const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
  root.appendChild(ctx.bar("⏱ Notice clock (contractual deadlines)", () => {
    // Back to where this was opened from, when that screen can be rebuilt — `renderScheduleViews`
    // needs the module definition, so a project without the schedule module goes home instead of
    // to a panel that cannot render. A back button that does nothing is worse than one that
    // overshoots.
    const m = ctx.mods.find((x) => x.key === "schedule_activity");
    if (m) {
      void (async () => { await (await import("./schedule")).renderScheduleViews(ctx, m); })();
      return;
    }
    ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav();
  }));
  const api = ctx.host.api;
  const pid = ctx.host.projectId();
  if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Notice clock")); return; }

  const intro = el("div", "meta"); intro.style.marginBottom = "8px";
  intro.textContent = "A contract gives you a fixed number of days to notify the other party of an "
    + "event before the right to time or money for it is lost. These are the triggering events "
    + "already in the field record — daily reports, change events, RFIs — counted under the notice "
    + "provisions of the contract family this project has adopted. It is a diary, not advice.";
  root.appendChild(intro);

  const slot = el("div"); root.appendChild(slot);
  slot.innerHTML = `<div class="meta">reading the field record…</div>`;

  let reg: NoticeRegister;
  try {
    reg = await api.notices(pid);
  } catch (e) {
    slot.innerHTML = `<div class="meta">could not read the notice register: `
      + `${esc((e as Error).message)}</div>`;
    return;
  }
  if (!slot.isConnected) return;        // the reader moved on while this was in flight
  slot.innerHTML = "";

  // The qualifications come first, always — "0 expired" over a subset of the field record, or under
  // a contract the project is not on, is the defect this whole item is about.
  for (const n of registerNotes(reg)) {
    const card = el("div", "dash-card");
    card.style.cssText = "margin-bottom:8px"
      + (n.tone === "warn" ? ";border-left:3px solid var(--status-warn)"
         : n.tone === "bad" ? ";border-left:3px solid var(--status-crit)" : "");
    const h = el("div"); h.innerHTML = "<b></b>";
    (h.firstElementChild as HTMLElement).textContent = n.headline;
    const d = el("div", "meta"); d.style.marginTop = "2px"; d.textContent = n.detail;
    card.append(h, d); slot.appendChild(card);
  }
  if (!reg.adopted) return;             // nothing computed; the note above is the whole answer

  const head = el("div", "dash-card"); head.style.marginBottom = "8px";
  const counts = statusCounts(reg);
  head.innerHTML = `<div><b>${esc(reg.family_label || reg.family || "")}</b> `
    + `<span class="meta">as of ${esc(reg.as_of || "")} · ${esc(reg.calendar || "")}</span></div>`
    + `<div style="margin-top:4px">`
    + (counts.length
        // `esc(String(n))` on a number, because `apps/web/src/ui/innerHtmlGuard.test.ts` refuses a
        // bare destructured binding in an innerHTML template with no baseline to grandfather into —
        // and its reason is right: the identity of the sink is the binding NAME, which does not
        // move when a caller starts passing something other than a count through it.
        ? counts.map(([s, n]) => `${statusMeta(s).icon} <b>${esc(String(n))}</b> `
            + `${esc(statusMeta(s).label)}`).join(" · ")
        : `<span class="meta">no triggering events found in the field record</span>`)
    + `</div>`
    + `<div class="meta" style="margin-top:2px">${esc(reg.coverage || "")}</div>`;
  slot.appendChild(head);

  const draftBox = el("div"); draftBox.style.cssText = "display:none;margin-bottom:8px";
  slot.appendChild(draftBox);

  for (const i of reg.items) {
    const row = el("div", "dash-card"); row.style.cssText = "margin-bottom:6px";
    const line = el("div"); line.innerHTML = itemLine(i);
    row.appendChild(line);
    if (i.clause) {
      const btn = el("button") as HTMLButtonElement;
      btn.className = "mini-btn"; btn.textContent = "✉ Draft notice";
      btn.style.marginTop = "4px";
      btn.title = "Generate the notice letter for this event under this clause";
      btn.onclick = () => void (async () => {
        btn.disabled = true;
        try {
          const d = await api.draftNotice(pid, i);
          draftBox.style.display = "";
          draftBox.innerHTML = `<div class="dash-card"><div><b>${esc(d.subject)}</b></div>`
            + `<div class="meta" style="margin-top:2px">${esc(d.clause || "")} `
            + `${esc(d.citation || "")}${d.due_on ? ` · due ${esc(d.due_on)}` : ""}</div>`
            + (d.warning ? `<div class="meta" style="margin-top:2px">${esc(d.warning)}</div>` : "")
            + `<pre style="white-space:pre-wrap;font-size:11.5px;margin-top:6px">`
            + `${esc(d.body)}</pre></div>`;
          draftBox.scrollIntoView({ block: "nearest" });
        } catch (e) {
          toast(`draft failed: ${(e as Error).message}`, "error");
        } finally { btn.disabled = false; }
      })();
      row.appendChild(btn);
    }
    slot.appendChild(row);
  }

  // The library, on demand: it is the words the numbers above came from, and a reader who doubts a
  // date needs the clause rather than another count.
  const libCard = el("div", "dash-card"); libCard.style.marginTop = "8px";
  libCard.innerHTML = `<div><b>📜 Notice provisions in this library</b></div>`
    + `<div class="meta" style="margin-top:2px">The standard provisions of the unamended forms, `
    + `with citations — starting points to verify, not law.</div>`;
  const libBtn = el("button") as HTMLButtonElement;
  libBtn.className = "mini-btn"; libBtn.textContent = "Show clauses";
  libBtn.style.marginTop = "6px";
  const libBody = el("div"); libBody.style.marginTop = "6px";
  libBtn.onclick = () => void (async () => {
    libBtn.disabled = true;
    try {
      const L = await api.noticeClauses(pid, reg.adopted_family ? { family: reg.adopted_family } : {});
      libBody.innerHTML = L.clauses.map((cl) =>
        `<div style="margin:4px 0"><b>${esc(cl.reference)}</b> — ${cl.days} ${esc(cl.basis)} from `
        + `${esc(cl.starts_on)} · ${esc(cl.consequence.replace(/_/g, " "))}`
        + `<br><span class="meta">${esc(cl.citation)}</span></div>`).join("")
        || `<div class="meta">no provisions in this library for that family</div>`;
    } catch (e) {
      libBody.innerHTML = `<div class="meta">${esc((e as Error).message)}</div>`;
    } finally { libBtn.disabled = false; }
  })();
  libCard.append(libBtn, libBody);
  slot.appendChild(libCard);
}
