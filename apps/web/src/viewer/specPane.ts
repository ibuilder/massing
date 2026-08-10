/**
 * R36-VIEWER-SUBAPP — the Specs canvas: the project manual as a surface, not a modal.
 *
 * WHY THIS UNBLOCKS TWO THINGS AT ONCE
 * ------------------------------------
 * The mode switch shipped with Specs deliberately unregistered, because the spec book existed only
 * as a `showResult` modal and a tab that shows nothing is worse than a missing tab. This is the
 * surface that lets the third mode exist — and it is also the "pick an element, see the spec section"
 * half of slice 5, because the manual already carries the element GUIDs per section.
 *
 * THE LINK WAS ALREADY SERVED AND NOBODY COULD SEE IT
 * --------------------------------------------------
 * `specmanual.py` has emitted `"elements": [{guid, name, ifc_class}]` per section since it shipped.
 * The client's `specManual` return type simply did not declare the field, so no caller could reach
 * it and the section↔element link looked like work that had not been done. Mirror image of the
 * sheet-params defect two releases ago: there the client SENT keys the route ignores, here it
 * IGNORED keys the route sends. Both are the same failure — a contract believed rather than read.
 *
 * THE CAP IS REAL AND IS SHOWN, NOT SWALLOWED
 * -------------------------------------------
 * The server caps `elements` at **50 per section** while `element_count` reports the true total. So
 * for a section with 400 elements, this pane can answer "which section is this element in" for 50 of
 * them and genuinely cannot for the other 350. A pane that quietly failed to highlight would read as
 * "that element has no spec section", which is a different and wrong statement — so `sectionForGuid`
 * distinguishes *not found* from *beyond the cap*, and the UI says which.
 */

import type { SpecDivision, SpecManual, SpecSection } from "../api/types";

export type { SpecDivision, SpecManual, SpecSection };

/** What the server caps `elements` at, per section. Mirrors `specmanual.py`. */
export const ELEMENTS_PER_SECTION_CAP = 50;

export type SectionLookup =
  | { found: SpecSection }
  /** No section lists this guid, and every section's list is complete — so it truly has no section. */
  | { found: null; truncated: false }
  /** No section lists it, but at least one section's list was cut off — so we cannot actually tell. */
  | { found: null; truncated: true };

/**
 * Which section covers this element.
 *
 * Returns the *reason* for a miss, not just the miss. "No spec section" and "I cannot see far enough
 * to say" are different answers and only one of them is a fact about the model.
 */
export function sectionForGuid(manual: SpecManual, guid: string | null): SectionLookup {
  if (!guid) return { found: null, truncated: false };
  let truncated = false;
  for (const div of manual.divisions) {
    for (const sec of div.sections) {
      if (sec.elements.some((e) => e.guid === guid)) return { found: sec };
      if (sec.element_count > sec.elements.length) truncated = true;
    }
  }
  return { found: null, truncated };
}

/** A stable DOM id for a section, so highlighting can find it without holding node references. */
export function sectionDomId(code: string): string {
  return `spec-sec-${code.replace(/[^A-Za-z0-9]+/g, "-")}`;
}

export interface SpecPaneDeps {
  /** Fetches the manual. Injected so the pane is testable without a network or an ApiClient. */
  load: () => Promise<SpecManual>;
  notify: (msg: string, kind: "info" | "success" | "error") => void;
  /** Clicking an element inside a section selects it in the model. */
  onPick?: (guid: string) => void;
}

export class SpecPane {
  readonly el: HTMLElement;
  private readonly body: HTMLElement;
  private manual: SpecManual | null = null;
  private sel: string | null = null;
  private open = false;
  private loading = false;

  constructor(private readonly d: SpecPaneDeps) {
    this.el = document.createElement("div");
    this.el.className = "spec-pane";
    this.el.style.cssText = "position:absolute;inset:0;display:none;flex-direction:column;"
      + "background:var(--panel,#0f172a);z-index:4";

    const bar = document.createElement("div");
    bar.style.cssText = "display:flex;align-items:center;gap:6px;padding:5px 8px;font-size:12px;"
      + "border-bottom:1px solid var(--line,#1e293b);flex:0 0 auto";
    const title = document.createElement("span");
    title.textContent = "Project manual"; title.style.fontWeight = "600";
    const sub = document.createElement("span");
    sub.className = "spec-pane-sub"; sub.style.cssText = "color:var(--muted,#94a3b8);flex:1";
    bar.append(title, sub);

    this.body = document.createElement("div");
    this.body.style.cssText = "flex:1;overflow:auto;padding:10px 12px;font-size:12px";
    this.el.append(bar, this.body);
  }

  get isOpen(): boolean { return this.open; }

  /** The canvas, or not. Mirrors `PlanPane.dock` so the mode switch treats them alike. */
  dock(style: "full" | "hidden"): void {
    this.open = style === "full";
    this.el.style.display = this.open ? "flex" : "none";
    if (this.open) void this.refresh();
  }

  /**
   * Remember the selection and, if the manual is rendered, reveal its section.
   *
   * Stores the guid even while hidden — the same property that makes the plan's cross-mode selection
   * work, and for the same reason: the identity is a GlobalId, so it survives the DOM not existing.
   */
  highlight(guid: string | null): void {
    this.sel = guid;
    if (this.open && this.manual) this.applyHighlight();
  }

  private applyHighlight(): void {
    for (const el of Array.from(this.body.querySelectorAll<HTMLElement>("[data-spec-code]"))) {
      el.classList.remove("on");
      el.style.outline = "";
    }
    if (!this.manual || !this.sel) return;
    const hit = sectionForGuid(this.manual, this.sel);
    const sub = this.el.querySelector<HTMLElement>(".spec-pane-sub");
    if (!hit.found) {
      if (sub) {
        sub.textContent = hit.truncated
          ? "selected element is not in the first 50 of any section — the manual lists a capped sample"
          : "selected element has no spec section";
      }
      return;
    }
    const node = this.body.querySelector<HTMLElement>(`#${CSS.escape(sectionDomId(hit.found.code))}`);
    if (node) {
      node.classList.add("on");
      node.style.outline = "2px solid #2563eb";
      node.scrollIntoView({ block: "center" });
    }
    if (sub) sub.textContent = `§ ${hit.found.code} — ${hit.found.title}`;
  }

  async refresh(): Promise<void> {
    if (!this.open || this.loading) return;
    this.loading = true;
    try {
      this.manual = await this.d.load();
      this.render();
      this.applyHighlight();
    } catch (e) {
      this.body.textContent = "";
      const p = document.createElement("div");
      p.style.cssText = "padding:10px;color:var(--muted,#94a3b8)";
      p.textContent = `Could not assemble the project manual — ${(e as Error).message}`;
      this.body.appendChild(p);
    } finally {
      this.loading = false;
    }
  }

  private render(): void {
    const man = this.manual!;
    this.body.textContent = "";
    const sub = this.el.querySelector<HTMLElement>(".spec-pane-sub");
    if (sub) sub.textContent = `${man.division_count} division(s) · ${man.section_count} section(s)`;

    if (!man.section_count) {
      const p = document.createElement("div");
      p.style.cssText = "padding:10px;color:var(--muted,#94a3b8)";
      p.textContent = "No MasterFormat-classified elements yet — classify elements in the Detailing "
        + "tool to seed the manual.";
      this.body.appendChild(p);
      return;
    }

    for (const div of man.divisions) {
      const h = document.createElement("div");
      h.style.cssText = "font-weight:600;margin:12px 0 4px;letter-spacing:.02em";
      h.textContent = `DIVISION ${div.division} — ${div.title}`;
      this.body.appendChild(h);

      for (const sec of div.sections) {
        const card = document.createElement("div");
        card.dataset.specCode = sec.code;
        card.id = sectionDomId(sec.code);
        card.style.cssText = "border:1px solid var(--line,#1e293b);border-radius:6px;padding:8px;"
          + "margin:0 0 6px";

        const st = document.createElement("div");
        st.style.fontWeight = "600";
        st.textContent = `§ ${sec.code} — ${sec.title}`;
        card.appendChild(st);

        const meta = document.createElement("div");
        meta.style.cssText = "color:var(--muted,#94a3b8);margin:2px 0 6px";
        // Say the cap out loud where it applies. A shorter list that reads as the whole list is the
        // failure mode; `element_count` is the truth.
        meta.textContent = sec.element_count > sec.elements.length
          ? `${sec.element_count} element(s) — listing the first ${sec.elements.length}`
          : `${sec.element_count} element(s)`;
        card.appendChild(meta);

        for (const [label, text] of [
          ["Part 1 — General", sec.part1_general],
          ["Part 2 — Products", sec.part2_products.join(", ")],
          ["Part 3 — Execution", sec.part3_execution.join("; ")],
        ] as const) {
          const row = document.createElement("div");
          row.style.margin = "3px 0";
          const b = document.createElement("b"); b.textContent = `${label}: `;
          row.append(b, document.createTextNode(text));
          card.appendChild(row);
        }

        if (sec.elements.length) {
          const list = document.createElement("div");
          list.style.cssText = "display:flex;flex-wrap:wrap;gap:4px;margin-top:6px";
          for (const e of sec.elements) {
            const chip = document.createElement("button");
            chip.type = "button";
            chip.className = "mini-btn";
            chip.dataset.guid = e.guid ?? "";
            chip.textContent = `${e.name} · ${e.ifc_class.replace(/^Ifc/, "")}`;
            chip.onclick = () => { if (e.guid) this.d.onPick?.(e.guid); };
            list.appendChild(chip);
          }
          card.appendChild(list);
        }
        this.body.appendChild(card);
      }
    }
  }
}
