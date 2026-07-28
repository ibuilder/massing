/**
 * Issue pins — the field workflow.
 *
 * A pin is a located issue, not a note that happens to have coordinates. It carries a number, an
 * assignee, a due date and a status, it can be promoted to an RFI/punch item in the host system,
 * and it maps cleanly onto a BCF topic so it round-trips with the coordination tools rather than
 * dying inside the PDF.
 */
import { definePlugin } from "../core/plugin";
import { activate, refreshRovingTabstops, rovingFocus } from "../core/a11y";
import { STATUS_COLORS } from "../core/types";
import type { Annotation, AnnotStatus } from "../core/types";
import type { Viewer } from "../core/viewer";

/** The issue fields a pin carries beyond the base annotation record. */
export interface IssueFields {
  /** Sequential, per document. Rendered in the pin badge. */
  pinNumber?: number;
  assignee?: string;
  dueDate?: string;               // ISO date
  /** Punch / RFI / observation / deficiency / safety — drives the host's workflow routing. */
  issueType?: string;
  /** Host's own reference once promoted, e.g. `RFI-014`. */
  ref?: string;
}

export interface PinOptions {
  /** Issue types offered when creating a pin. */
  types?: string[];
  /** Ask for the pin's description. Defaults to `window.prompt`. */
  promptText?: (title: string, initial?: string) => Promise<string | null>;
  /**
   * Push a pin into the host's issue system. Return the created issue's id and human ref; the pin
   * is then linked and shown as promoted. Throwing surfaces as an error notice.
   */
  promote?: (annot: Annotation, viewer: Viewer) => Promise<{ issueId: string; ref?: string }>;
  /** Notify the host that a pin's status changed, e.g. to mirror it onto the linked issue. */
  onStatusChange?: (annot: Annotation, status: AnnotStatus) => void | Promise<void>;
}

export const DEFAULT_ISSUE_TYPES = [
  "Observation", "Punch item", "RFI", "Deficiency", "Safety", "Coordination", "Preservation note",
];

export function pinsPlugin(options: PinOptions = {}) {
  const ask = options.promptText ?? (async (t: string, i = "") => globalThis.prompt?.(t, i) ?? null);
  const types = options.types ?? DEFAULT_ISSUE_TYPES;

  return definePlugin({
    id: "pins",
    order: 40,
    setup(ctx) {
      const { viewer } = ctx;

      /** Next pin number: max existing + 1, so deleting a pin never causes a reused number. */
      const nextNumber = (): number =>
        viewer.store.all().reduce((n, a) => {
          const v = a.ext?.["pinNumber"];
          return a.kind === "pin" && typeof v === "number" ? Math.max(n, v) : n;
        }, 0) + 1;

      ctx.registerTool({
        id: "pin", label: "Issue pin", icon: "📍", kind: "pin", input: "click", group: "review",
        shortcut: "p", sticky: true,
        async create({ points, page }) {
          const body = await ask("Issue description");
          if (body === null) return null;
          return {
            kind: "pin", points, page,
            subject: body.trim() || `Issue ${nextNumber()}`,
            note: body.trim(),
            status: "open" as AnnotStatus,
            priority: "normal",
            ext: { pinNumber: nextNumber(), issueType: types[0] } satisfies IssueFields & Record<string, unknown>,
          };
        },
      });

      ctx.registerAction({
        id: "pins.promote", label: "Promote to issue", icon: "⤴", group: "review",
        enabled: (v) => v.store.selected().some((a) => a.kind === "pin" && !a.links?.issueId),
        async run(v) {
          if (!options.promote) {
            v.bus.emit("notice", { level: "warn", message: "No issue system connected — configure `promote` on the pins plugin." });
            return;
          }
          const targets = v.store.selected().filter((a) => a.kind === "pin" && !a.links?.issueId);
          for (const a of targets) {
            try {
              const { issueId, ref } = await options.promote(a, v);
              v.store.update(a.id, {
                links: { ...a.links, issueId },
                ext: { ...a.ext, ...(ref ? { ref } : {}) },
              });
              v.bus.emit("notice", { level: "success", message: `${ref ?? "Issue"} created from pin ${a.ext?.["pinNumber"] ?? ""}`.trim() });
            } catch (e) {
              v.bus.emit("notice", { level: "error", message: `Promote failed: ${(e as Error).message}` });
            }
          }
        },
      });

      ctx.registerAction({
        id: "pins.status", label: "Set status", icon: "◑", group: "review",
        enabled: (v) => v.store.selectedIds().length > 0,
        async run(v) {
          const all = Object.keys(STATUS_COLORS) as AnnotStatus[];
          const answer = await ask(`Status\n\n${all.map((s, i) => `${i + 1}. ${s}`).join("\n")}`, "1");
          if (!answer) return;
          const n = Number(answer.trim());
          const status = (Number.isInteger(n) && all[n - 1]) || all.find((s) => s === answer.trim().toLowerCase());
          if (!status) return;
          for (const a of v.store.selected()) {
            v.store.update(a.id, { status });
            await options.onStatusChange?.(a, status);
          }
        },
      });

      ctx.registerPanel({
        id: "issues", title: "Issues", side: "right", order: 10,
        mount: (host, v) => mountIssues(host, v, ask, types, options),
      });

      // Renumber after a delete so the badge sequence stays contiguous on screen. The *record* keeps
      // its id — only the display number moves, so a promoted issue's reference never shifts.
      ctx.bus.on("annot:removed", ({ annot }) => {
        if (annot.kind !== "pin") return;
        const pins = viewer.store.all().filter((a) => a.kind === "pin" && !a.links?.issueId);
        const patches = pins
          .map((a, i) => ({ a, want: i + 1 }))
          .filter(({ a, want }) => a.ext?.["pinNumber"] !== want)
          .map(({ a, want }) => ({ id: a.id, patch: { ext: { ...a.ext, pinNumber: want } } }));
        if (patches.length) viewer.store.updateMany(patches);
      });
    },
  });
}

/** The issue list: filterable, click-to-locate, status at a glance. */
function mountIssues(
  host: HTMLElement,
  v: Viewer,
  ask: (title: string, initial?: string) => Promise<string | null>,
  types: string[],
  options: PinOptions,
): () => void {
  const bar = document.createElement("div");
  bar.className = "mpdf-issues-bar";
  const select = document.createElement("select");
  select.className = "mpdf-select";
  for (const [value, label] of [["", "All statuses"], ...Object.keys(STATUS_COLORS).map((s) => [s, s])] as [string, string][]) {
    const o = document.createElement("option");
    o.value = value; o.textContent = label;
    select.appendChild(o);
  }
  bar.appendChild(select);
  const list = document.createElement("div");
  list.setAttribute("role", "listbox");
  list.setAttribute("aria-label", "Issue pins");
  list.className = "mpdf-issues-list";
  host.append(bar, list);

  const render = () => {
    const want = select.value;
    const pins = v.store.all()
      .filter((a) => a.kind === "pin" && (!want || a.status === want))
      .sort((a, b) => Number(a.ext?.["pinNumber"] ?? 0) - Number(b.ext?.["pinNumber"] ?? 0));
    list.innerHTML = "";
    if (!pins.length) {
      const p = document.createElement("p");
      p.className = "mpdf-empty";
      p.textContent = want ? `No ${want} issues.` : "No issues pinned yet.";
      list.appendChild(p);
      return;
    }
    for (const a of pins) {
      const row = document.createElement("article");
      row.className = "mpdf-issue";
      if (v.store.isSelected(a.id)) row.classList.add("is-selected");

      const badge = document.createElement("span");
      badge.className = "mpdf-issue-badge";
      badge.style.background = a.style?.color ?? STATUS_COLORS[a.status];
      badge.textContent = String(a.ext?.["pinNumber"] ?? "•");

      const main = document.createElement("div");
      main.className = "mpdf-issue-main";
      const title = document.createElement("div");
      title.className = "mpdf-issue-title";
      title.textContent = a.subject || a.note || "(no description)";
      const meta = document.createElement("div");
      meta.className = "mpdf-issue-meta";
      const ref = a.ext?.["ref"];
      meta.textContent = [
        `p.${a.page}`,
        a.status,
        a.ext?.["issueType"],
        a.author,
        typeof ref === "string" ? ref : null,
      ].filter(Boolean).join(" · ");
      main.append(title, meta);

      const tools = document.createElement("div");
      tools.className = "mpdf-issue-tools";
      const edit = iconButton("✎", "Edit description", async () => {
        const next = await ask("Issue description", a.note ?? a.subject ?? "");
        if (next === null) return;
        v.store.update(a.id, { note: next.trim(), subject: next.trim() });
      });
      const cycle = iconButton("◑", "Cycle status", async () => {
        const order: AnnotStatus[] = ["open", "in_review", "resolved", "accepted"];
        const next = order[(order.indexOf(a.status) + 1) % order.length]!;
        v.store.update(a.id, { status: next });
        await options.onStatusChange?.(a, next);
      });
      const del = iconButton("✕", "Delete pin", () => { v.store.remove(a.id); });
      tools.append(edit, cycle, del);

      row.append(badge, main, tools);
      activate(row, (e) => {
        if ((e.target as HTMLElement).closest("button")) return;
        v.store.select(a.id);
        void v.goToAnnotation(a, { zoom: false });
      }, { role: "option", selected: v.store.isSelected(a.id), label: pinLabel(a), roving: true });
      list.appendChild(row);
    }
    refreshRovingTabstops(list, '[role="option"]');
    void types;
  };

  select.onchange = render;
  const offs = [
    v.on("annot:added", render), v.on("annot:updated", render),
    v.on("annot:removed", render), v.on("annot:reset", render), v.on("annot:selected", render),
  ];
  render();
  const stopRoving = rovingFocus(list, '[role="option"]');
  return () => { offs.forEach((off) => off()); stopRoving(); };
}

/**
 * What a screen reader says for a pin row.
 *
 * The visible row leans on a coloured badge for status and priority, which conveys nothing to a
 * reader and nothing to anyone who cannot distinguish the colours.
 */
function pinLabel(a: Annotation): string {
  const parts = [`Pin on page ${a.page}`, a.status.replace("_", " ")];
  if (a.priority) parts.push(`${a.priority} priority`);
  if (a.subject) parts.push(a.subject);
  return parts.join(", ");
}

function iconButton(glyph: string, title: string, onClick: () => void | Promise<void>): HTMLButtonElement {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "mpdf-icon-btn";
  b.textContent = glyph;
  b.title = title;
  b.onclick = (e) => { e.stopPropagation(); void onClick(); };
  return b;
}
