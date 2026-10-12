/**
 * NEGATED-VERDICT, the round-trip screen — extracted from `qaSection.ts` because the size ratchet
 * in `services/api/test_file_sizes.py` refused the growth, which is the pin working exactly as its
 * comment says it should: *a ratchet refuses a change until an extraction pays for it.* Giving the
 * reading a pure function and the card a lazy module pays for ten lines with forty.
 *
 * **What the extraction is really for.** `roundtrip.compare` returned
 * `fidelity_ok: not missing and not added and not changed` — unconditionally `True` over an empty
 * snapshot, so a model carrying no `IfcProduct` reported LOSSLESS. The result card rendered
 * `element_count` in its own sentence ("all 0 elements survived"), which a reader can at least
 * catch; the **status line prints the bare verdict**, where `round-trip clean` was the whole of the
 * answer. The engine now requires `bool(before)` and reports `nothing_compared`, so there are three
 * states — and three states in a ternary chain inside a render is a thing to assert, not to read.
 */

/** As `GET /projects/{pid}/model/roundtrip` returns it. Declared here rather than cast inline: a
 *  re-spelled shape is a field no derivation over declarations can see, which is how CLASH-TRUNC's
 *  `truncated` went unread for months. `apps/web/src/api/noRespelledShapes.test.ts` pins that
 *  tree-wide, so this is a type ALIAS of the client's own declaration, never a copy of it. */
export type RoundtripReport = Awaited<ReturnType<
  import("../../api/client").ApiClient["modelRoundtrip"]>>;

export interface RoundtripReading {
  kind: "unrun" | "lossless" | "lossy";
  /** The status line — the one place the verdict appears with no count beside it. */
  status: string;
  html: string;
  tone: "ok" | "bad" | "";
}

/**
 * The three states, and which `false` you have.
 *
 * `unrun` ranks first and is toned as neither a pass nor a finding: nothing was compared, so the
 * absence of discrepancies is a fact about the input. *A verdict over an empty population is not a
 * clean result; it is an unrun one.*
 */
export function roundtripReading(r: RoundtripReport): RoundtripReading {
  const n = r.counts.missing + r.counts.added + r.counts.changed;
  if (r.nothing_compared) {
    return { kind: "unrun", tone: "", status: "nothing to round-trip",
             html: "<b>Nothing was compared</b> — this model carries no IfcProduct or "
                 + "IfcTypeProduct, so serialise → re-parse proved nothing. This is not a lossless "
                 + "result; it is an unrun one." };
  }
  if (r.fidelity_ok) {
    return { kind: "lossless", tone: "ok", status: "round-trip clean",
             html: `<b>Lossless</b> — all ${r.element_count} elements survived serialise → re-parse `
                 + "with GUID, class, name, containment, type and psets intact." };
  }
  return { kind: "lossy", tone: "bad", status: `${n} discrepancy(ies)`,
           html: `<b>Not lossless</b> — ${r.counts.missing} missing · ${r.counts.added} added · `
               + `${r.counts.changed} changed, of ${r.element_count} elements.` };
}

/** The GUID groups worth selecting in 3D, in the order they matter.
 *
 *  MISSING leads: an element that does not survive our own export is data loss, and GUID stability
 *  is what every edit recipe and every pin in this product depends on. Groups with nothing in them
 *  are dropped rather than rendered empty. */
export function roundtripGroups(r: RoundtripReport): { label: string; guids: string[] }[] {
  return [{ label: "Missing after round-trip", guids: r.missing },
          { label: "Appeared after round-trip", guids: r.added }]
    .filter((g) => g.guids.length);
}

/** Longest GUID run handed to a selection call. */
export const SELECT_CAP = 200;

export interface RoundtripCardDeps {
  showResult: (title: string, render: (body: HTMLElement) => void) => void;
  resultNote: (html: string, kind?: "ok" | "warn" | "bad" | "") => HTMLElement;
  kvTable: (rows: { k: string; v: string }[]) => HTMLElement;
  esc: (v: unknown) => string;
  select: (guids: string[]) => void | Promise<void>;
}

export function renderRoundtripCard(r: RoundtripReport, d: RoundtripCardDeps): void {
  const reading = roundtripReading(r);
  d.showResult("Round-trip fidelity", (body) => {
    body.appendChild(d.resultNote(reading.html, reading.tone));
    for (const group of roundtripGroups(r)) {
      const row = document.createElement("div");
      row.className = "meta"; row.style.cssText = "margin-top:4px;cursor:pointer";
      row.innerHTML = `<b>${d.esc(group.label)}</b>: ${d.esc(group.guids.length)}`;
      row.title = "Select these elements";
      row.onclick = () => { void d.select(group.guids.slice(0, SELECT_CAP)); };
      body.appendChild(row);
    }
    if (r.changed.length) {
      body.appendChild(d.resultNote("<b>Changed</b> — survived, but an aspect differs:", ""));
      body.appendChild(d.kvTable(r.changed.slice(0, 50).map((c) => ({
        k: d.esc(c.class), v: d.esc(c.aspects.join(", ")),
      }))));
    }
  });
}
