/** WAIVER-FLAT — a conditional release and no release at all rendered byte-identically.
 *
 *  `payapp.reconcile` decides, per vendor, whether the money paid out is RELEASED. It publishes
 *  three states and the lien-exposure card read none of them:
 *
 *  | | `paid` | `waived_unconditional` | `waived_conditional` | `exposure` | `status` |
 *  |---|---|---|---|---|---|
 *  | B | 200,000 | 0 | **200,000** | 200,000 | `conditional_only` |
 *  | C | 200,000 | 0 | 0 | 200,000 | `no_waiver` |
 *
 *  Measured against a live server. The card rendered Vendor / Paid / Unconditional waived /
 *  Exposure, so **B and C came out as the same row** — `200,000 / 0 / 200,000`, both in
 *  `--status-crit` — while B holds a signed release for the full amount and C holds nothing. On a
 *  lien screen those are two different decisions: chase a signature, or withhold the next payment.
 *
 *  ## It was declared and unread, which is the worse half
 *
 *  `status` and `waived_conditional` were both on the client type already. Nothing was wrong with
 *  the engine, nothing was wrong with the declaration, and no gate in this tree could see it:
 *  `apps/web/src/api/deadFieldTyped.test.ts` builds its population from exported INTERFACE
 *  declarations under `api/`, and this response was declared inline in the `this.json<{…}>` type
 *  argument — along with 562 of 706 call sites (DEADFIELD-INLINE holds the measurement). *Naming
 *  the response type is what makes it auditable*, which is why this item names it.
 *
 *  `services/api/test_payapp.py` had already asserted `status == "conditional_only"` on a $100k
 *  exposure. The engine was proven right; its fixture simply never had a `no_waiver` vendor beside
 *  it, so the pair that renders identically was never both present in one response.
 *
 *  ## The money split is FINER than the status, deliberately
 *
 *  `status` is `conditional_only` only when the conditional waivers cover the whole exposure. A
 *  vendor with $200k exposed and a $50k conditional waiver is `no_waiver` — correct as a verdict,
 *  and it still leaves $50k conditionally covered. So the headline splits the total as
 *  `Σ min(exposure, waived_conditional)` against the remainder, which is the pair of numbers a GC
 *  acts on, and the per-vendor rows carry the engine's verdict beside it. Two derivations of one
 *  quantity, reported separately rather than one standing in for the other.
 *
 *  ## And the horizon the COI card asserted was a constant
 *
 *  The same panel printed `expiring ≤30d` as literal text beside an unread `soon_days`. The one
 *  caller passes the default, so the label is true today and is a restatement of a parameter
 *  rather than a reading of the answer — the same shape as the re-spelled response types
 *  `apps/web/src/api/noRespelledShapes.test.ts` refuses.
 */
import type { CoiExpiry, LienExposure, LienVendor } from "../../api/counterpartyRisk";

export type Tone = "" | "good" | "warn" | "crit";

/** Literal, not `var(--status-${tone})` — a custom property built at runtime resolves to nothing
 *  and is dropped in silence (`apps/web/src/shell/cssVars.test.ts` holds that line). */
export const TONE_CSS: Record<Tone, string> = {
  "": "",
  good: "var(--status-good)",
  warn: "var(--status-warn)",
  crit: "var(--status-crit)",
};

/** The engine's three security states, named. The `meaning` is what the colour alone cannot say,
 *  and the difference between the second and third is the whole item. */
export const SECURITY: Record<LienVendor["status"], {
  label: string; tone: Tone; meaning: string;
}> = {
  clear: {
    label: "released",
    tone: "good",
    meaning: "an unconditional waiver covers everything paid",
  },
  conditional_only: {
    label: "conditional only",
    tone: "warn",
    meaning: "a conditional release is on file and takes effect once the payment clears — "
      + "paperwork pending, not an unsecured balance",
  },
  no_waiver: {
    label: "NO WAIVER",
    tone: "crit",
    meaning: "paid with no release of any kind on file",
  },
};

/** The runtime fallback for a status this build has never heard of.
 *
 *  `LienVendor["status"]` is a closed union, so TypeScript believes `SECURITY[v.status]` cannot be
 *  `undefined` — and a server that grows a fourth state would make that belief false, turning a
 *  missing column into `Cannot read properties of undefined` and taking the whole card down. *A
 *  narrowed type is a claim about a program on the other side of the wire*, so the lookup goes
 *  through here: an unknown state renders as itself, in the worst tone, which is the safe
 *  direction on a lien screen. */
function security(status: string): { label: string; tone: Tone; meaning: string } {
  return SECURITY[status as LienVendor["status"]]
    ?? { label: status || "unknown", tone: "crit",
         meaning: `this build does not know the release state "${status}" — treat it as unreleased `
           + `until somebody checks` };
}

/** `min(exposure, conditional waivers)` per vendor — what a conditional release actually covers. */
function conditionallyCovered(v: LienVendor): number {
  return Math.min(v.exposure, v.waived_conditional);
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

/** The split behind `total_lien_exposure`, which the card printed as one number.
 *
 *  Summed across every vendor rather than only the ones with a `conditional_only` verdict, because
 *  a partial conditional waiver covers part of an exposure the verdict still calls `no_waiver`. */
export function exposureSplit(r: LienExposure): { covered: number; unsecured: number } {
  const covered = round2(r.vendors.reduce((s, v) => s + conditionallyCovered(v), 0));
  return { covered, unsecured: round2(r.total_lien_exposure - covered) };
}

/** The exposure headline: how much, how much of it is only conditionally released, and over how
 *  many vendors of how many on the register.
 *
 *  `money` is injected rather than imported so this module formats nothing — the panel already
 *  owns a currency formatter and `apps/web/src/ui/charts.test.ts` bans a second one. */
export function exposureHeadline(r: LienExposure, money: (n: number) => string): {
  text: string; tone: Tone;
} {
  const exposed = r.vendors.filter((v) => v.exposure > 0);
  if (!exposed.length) {
    return r.vendor_count === 0
      ? { tone: "", text: "No vendor invoices or lien waivers registered yet." }
      : { tone: "good",
          text: `No lien exposure across ${r.vendor_count} vendor(s) — everything paid is `
            + `released by an unconditional waiver.` };
  }
  const { covered, unsecured } = exposureSplit(r);
  const scope = `across ${exposed.length} of ${r.vendor_count} vendor(s)`;
  if (covered > 0) {
    return {
      tone: unsecured > 0 ? "crit" : "warn",
      text: `${money(r.total_lien_exposure)} exposed ${scope} — ${money(unsecured)} with no `
        + `release on file and ${money(covered)} released only CONDITIONALLY.`,
    };
  }
  return {
    tone: "crit",
    text: `${money(r.total_lien_exposure)} exposed ${scope}, none of it released by any waiver.`,
  };
}

/** Why the split is not the same question as the per-vendor verdict. Shown only when the two could
 *  disagree — i.e. when something is conditionally covered but the verdict says `no_waiver`. */
export function splitBasisNote(r: LienExposure): string | null {
  const partial = r.vendors.filter(
    (v) => v.status === "no_waiver" && conditionallyCovered(v) > 0);
  if (!partial.length) return null;
  const names = partial.map((v) => v.vendor).join(", ");
  return `${partial.length} vendor(s) read NO WAIVER and still have part of the exposure `
    + `conditionally covered (${names}) — the verdict needs the conditional waivers to cover the `
    + `WHOLE balance, while the money split counts whatever they do cover.`;
}

/** One row per vendor carrying exposure, worst security first, with the conditional column the
 *  card never had and the engine's verdict spelled out. */
export function securityRows(r: LienExposure): {
  vendor: string; paid: number; unconditional: number; conditional: number; exposure: number;
  security: string; tone: Tone;
}[] {
  const rank: Record<LienVendor["status"], number> = {
    no_waiver: 0, conditional_only: 1, clear: 2,
  };
  // An unknown state sorts WITH the unreleased ones rather than off the end of the table.
  const at = (v: LienVendor) => rank[v.status] ?? -1;
  return r.vendors
    .filter((v) => v.exposure > 0)
    .slice()
    .sort((a, b) => at(a) - at(b) || b.exposure - a.exposure)
    .map((v) => ({
      vendor: v.vendor,
      paid: v.paid,
      unconditional: v.waived_unconditional,
      conditional: v.waived_conditional,
      exposure: v.exposure,
      security: security(v.status).label,
      tone: security(v.status).tone,
    }));
}

/** The vendors with no exposure, and the two DIFFERENT reasons they have none.
 *
 *  The card filtered both out identically. A vendor released by an unconditional waiver is
 *  finished; a vendor who has simply not been paid yet is exposure that has not happened. The
 *  engine calls both `clear`, which is right for a lien verdict and wrong as a summary. */
export function settledNote(r: LienExposure): string | null {
  const settled = r.vendors.filter((v) => v.exposure <= 0);
  if (!settled.length) return null;
  const released = settled.filter((v) => v.paid > 0).length;
  const unpaid = settled.length - released;
  const parts = [
    released ? `${released} released by an unconditional waiver` : "",
    unpaid ? `${unpaid} not yet paid, so nothing to release` : "",
  ].filter(Boolean);
  return `${settled.length} vendor(s) carry no exposure: ${parts.join(" · ")}.`;
}

/** The engine's own instruction, which it only sends when there is something to do. */
export function exposureInstruction(r: LienExposure): string | null {
  return r.message || null;
}

/** The COI line, reading the horizon the server actually used instead of restating the default. */
export function coiHorizonLine(r: CoiExpiry): string {
  return `${r.expired_count} expired · ${r.expiring_count} expiring within ${r.soon_days} day(s)`;
}

/** One COI row. `days` is negative for an already-expired certificate, so it is shown as an age
 *  rather than a countdown — `(-14d)` reads as a typo. `carrier` is who you telephone. */
export function coiRows(r: CoiExpiry): {
  kind: string; vendor: string; coverage: string; carrier: string; expires: string; age: string;
  tone: Tone;
}[] {
  const row = (x: CoiExpiry["expired"][number], expired: boolean) => ({
    kind: expired ? "EXPIRED" : "soon",
    vendor: x.vendor || "(no vendor)",
    coverage: x.coverage_type || "—",
    carrier: x.carrier || "—",
    expires: x.expires,
    age: expired ? `${Math.abs(x.days)}d ago` : `in ${x.days}d`,
    tone: (expired ? "crit" : "warn") as Tone,
  });
  return [...r.expired.map((x) => row(x, true)),
          ...r.expiring_soon.map((x) => row(x, false))];
}
