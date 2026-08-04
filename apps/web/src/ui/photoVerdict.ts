/**
 * R22-PHOTO-CV — turning the photo-upload response into something a person can act on.
 *
 * `POST /projects/{pid}/verification/{guid}/photo` answers three questions at once, and they are not
 * equally trustworthy:
 *
 *   - **quality** — a property of the image itself. Safe in both directions.
 *   - **change**  — a screening signal only. `near_identical` is a strong claim; a high
 *                   `change_score` is not, because a camera move scores higher than most real change.
 *   - **detected** — object counts, present only where a model is configured.
 *
 * The server is careful to state its own confidence; this is where that care survives into the UI or
 * gets thrown away. The rule followed here: **never render a number without the qualifier the server
 * attached to it.** A bare "78% changed" would be believed, and it should not be.
 *
 * Kept as a pure function over the response so it is testable without a DOM, a network or a model —
 * the display logic is where the misrepresentation would happen, so it is the part worth asserting.
 */

/** The shape `upload_photo` returns. Fields are optional because older servers predate them. */
export interface PhotoUploadResult {
  guid?: string;
  has_photo?: boolean;
  quality?: {
    analysed?: boolean;
    usable?: boolean | null;
    reasons?: string[];
    sharpness?: number;
    width?: number;
    height?: number;
  } | null;
  change?: {
    change_score?: number;
    near_identical?: boolean;
    changed_cells?: number;
    total_cells?: number;
    confidence?: string;
  } | null;
  detected?: {
    available?: boolean;
    ran?: boolean;
    reasons?: string[];
    summary?: { people?: number; vehicles?: number; total?: number };
  } | null;
}

export type VerdictTone = "ok" | "warn" | "info";

export interface VerdictLine {
  tone: VerdictTone;
  text: string;
  /** True when the line is asking the person to do something while they can still do it. */
  actionable?: boolean;
}

/**
 * Lines to show after an upload, most actionable first.
 *
 * **Order is the whole design.** A retake prompt is worth showing only while the person is still
 * standing in front of the thing they photographed, so an unusable-photo warning outranks every
 * interesting-but-idle statistic. Everything else is reported in descending order of how much it
 * should change what they do next.
 */
export function photoVerdict(r: PhotoUploadResult): VerdictLine[] {
  const out: VerdictLine[] = [];
  const q = r.quality;

  if (q && q.analysed === false) {
    // Stored but unreadable — HEIC on a server without pillow-heif is the common case. Say that the
    // photo was KEPT, or the person will reasonably assume it was rejected and shoot it again.
    out.push({ tone: "warn", text: q.reasons?.[0] ?? "photo could not be read; it was kept anyway" });
  } else if (q && q.usable === false) {
    // The one moment a retake is cheap is right now.
    const why = (q.reasons ?? []).join("; ");
    out.push({ tone: "warn", actionable: true, text: `Retake if you can — ${why || "photo is unusable"}` });
  } else if (q && q.usable === true) {
    out.push({ tone: "ok", text: "Photo looks usable" });
  }

  const d = r.detected;
  if (d?.ran && d.summary) {
    const p = d.summary.people ?? 0;
    const v = d.summary.vehicles ?? 0;
    if (p || v) {
      const bits: string[] = [];
      if (p) bits.push(`${p} ${p === 1 ? "person" : "people"}`);
      if (v) bits.push(`${v} ${v === 1 ? "vehicle" : "vehicles"}`);
      out.push({ tone: "info", text: `In frame: ${bits.join(", ")}` });
    }
  }

  const c = r.change;
  if (c) {
    if (c.near_identical) {
      // The trustworthy direction, and genuinely useful: it retires "has anything happened here?".
      out.push({ tone: "info", text: "Same as the previous photo — nothing has changed here" });
    } else if (typeof c.change_score === "number") {
      // NOT rendered as a bare percentage. The server says this is screening-only, and dropping that
      // qualifier is exactly how a soft signal becomes a hard claim in someone's head.
      const pct = Math.round(c.change_score * 100);
      out.push({ tone: "info", text: `Differs from the previous photo (${pct}% — worth a look, not a conclusion)` });
    }
  }

  return out;
}

/** One-line summary for a status bar, or "" when there is nothing worth saying. */
export function photoVerdictSummary(r: PhotoUploadResult): string {
  return photoVerdict(r)[0]?.text ?? "";
}
