/**
 * R24-EMPTY-GUIDE ② — an empty register says where its rows come from.
 *
 * The audit's finding 14: blank projects were hardened for *robustness*, not for *guidance*. Running
 * with no data is a genuine strength here and the app does it everywhere; the miss is that an empty
 * module currently reads:
 *
 *     No RFIs yet
 *     Use “+ New” to create the first one.
 *
 * which is mechanically true and answers the wrong question. "+ New" is visible three inches away —
 * the user can see *how*. What they cannot see is **what this register is for and where its rows
 * normally arrive from**, and for most registers the answer is not "somebody types one". An RFI
 * answers against a drawing. A submittal is driven by a spec section. A punch item is captured on a
 * phone, in the field, by someone who is not looking at this screen.
 *
 * That is the difference between a blank slate and a dead end, and it is the audit's own example.
 *
 * **Guidance is curated, never generated.** There are 133 modules and this table covers the ones
 * whose upstream is a real, standard workflow fact — not a guess. Everything else keeps the generic
 * line, because a plausible-sounding invented workflow is worse than an honest generic one: it is a
 * confident wrong answer in a place the user has no way to check. Same rule the spine applies to an
 * unroomed module, and the same reason `resolve()` must not fabricate a coverage number.
 *
 * `emptyGuide.test.ts` asserts every key here is a real module directory under
 * `services/api/modules/`, so a renamed or removed module fails the build rather than leaving
 * guidance pointing at a register that no longer exists. Two of the keys in the first draft of this
 * table (`change_order`, `pay_app`) did not exist — they are `change_event` and `owner_invoice`.
 * The check earned itself before it was written.
 */

export interface EmptyGuide {
  /** What this register is for, in one clause. Not a definition — a reason to have one. */
  what: string;
  /** Where rows normally come from. The sentence that turns a dead end into a next step. */
  from: string;
}

export const EMPTY_GUIDES: Record<string, EmptyGuide> = {
  // ── Engineering: questions and approvals against the documents ────────────────────────────────
  rfi: {
    what: "An RFI is a question asked against a drawing or spec, with the clock running.",
    from: "Raise one from a drawing, or from an element in the model.",
  },
  submittal: {
    what: "A submittal proves a product matches what the specification asked for.",
    from: "Driven by spec sections — import a spec set and the register builds from it.",
  },
  spec_section: {
    what: "Spec sections are what submittals and quality checks are measured against.",
    from: "Import a specification, or generate one from the model's materials.",
  },
  asi: {
    what: "An ASI is the architect issuing a clarification that changes the documents.",
    from: "Usually follows an RFI answer that changed something.",
  },

  // ── Field: captured where the work is, not at a desk ──────────────────────────────────────────
  punchlist: {
    what: "Punch items are the defects found on a walk, before handover.",
    from: "Captured on a phone in the field — photo, location, trade.",
  },
  observation: {
    what: "A safety observation records what someone saw, before it becomes an incident.",
    from: "Captured in the field, in seconds, usually one-handed.",
  },
  daily_report: {
    what: "The daily report is the contemporaneous record — weather, manpower, what happened.",
    from: "Filed each day from the field; it is also the evidence a delay claim rests on.",
  },
  inspection: {
    what: "Inspections check the built work against the design before it is covered up.",
    from: "Scheduled against activities, or raised when a trade calls for one.",
  },
  ncr: {
    what: "An NCR records work that does not conform, and what was decided about it.",
    from: "Usually raised from a failed inspection or a rejected submittal.",
  },
  delivery: {
    what: "Deliveries are what arrived on site, when — the other half of a schedule.",
    from: "Logged on receipt, or driven by a purchase commitment's dates.",
  },

  // ── Money: nothing here is typed first; it all derives from something ─────────────────────────
  budget: {
    what: "The budget is the plan every cost report is measured against.",
    from: "Built from an estimate, or imported from a cost-loaded schedule of values.",
  },
  change_event: {
    what: "A change event is something that happened that may cost money or time.",
    from: "Raised from an RFI answer, a field condition, or an owner request — before it is priced.",
  },
  commitment: {
    what: "A commitment is money you have promised to a subcontractor or supplier.",
    from: "Created when a subcontract or purchase order is awarded from buyout.",
  },
  owner_invoice: {
    what: "An owner invoice is the money you are asking for this period.",
    from: "Built from the schedule of values and verified progress, not typed by hand.",
  },
  cost_code: {
    what: "Cost codes are how quantities in the model become money in the ledger.",
    from: "Imported from your firm's standard, or derived from the estimate.",
  },

  // ── Documents and the model ───────────────────────────────────────────────────────────────────
  drawing: {
    what: "Drawings are what the field builds from, and what RFIs are asked against.",
    from: "Generate a set from the model, or import an issued PDF set.",
  },
  drawing_set: {
    what: "A set is a group of sheets issued together, at a revision.",
    from: "Created when sheets are issued — the register is the issuance history.",
  },
  as_built: {
    what: "As-builts record what was actually built, where it differs from the design.",
    from: "Derived from field verification against the model, at LOD 500.",
  },

  // ── Planning and risk ─────────────────────────────────────────────────────────────────────────
  risk: {
    what: "The risk register is what could go wrong, priced and owned.",
    from: "Seeded from the project type and the estimate's assumptions.",
  },
  assumption: {
    what: "Assumptions and clarifications are what the price did and did not include.",
    from: "Written during estimating — they are what a scope dispute is settled against.",
  },
  lessons_learned: {
    what: "Lessons learned are what the next project should not repeat.",
    from: "Captured at closeout, and from NCRs and change events along the way.",
  },
  meeting: {
    what: "Meeting minutes are where decisions and action items get their date.",
    from: "Recorded per meeting; action items flow into the work queue.",
  },
  action_item: {
    what: "Action items are the things somebody owes somebody, with a date.",
    from: "Mostly generated from meetings — they rarely start life here.",
  },
};

/** Guidance for a module, or `null` when none is curated — never a generated one. */
export function emptyGuideFor(key: string): EmptyGuide | null {
  return EMPTY_GUIDES[key] ?? null;
}

/**
 * The hint line under "No X yet".
 *
 * Falls back to the previous generic copy when nothing is curated, so this can never make a module
 * worse — the guidance is strictly additive.
 */
export function emptyHint(key: string): string {
  const g = emptyGuideFor(key);
  return g ? `${g.what} ${g.from}` : "Use “+ New” to create the first one.";
}
