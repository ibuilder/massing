/**
 * R26-TOOLBAR — applies `toolbarLayout` to the floating viewer toolbar.
 *
 * The buttons are created where they always were, by the modules that own their behaviour; this only
 * decides which are *visible as labeled verbs* and which fold into **More**. Keeping it a layout pass
 * rather than a rewrite of 25 call sites is deliberate: the risky part of a toolbar change is losing
 * a tool, and a pass that only ever moves nodes between two containers cannot drop one.
 *
 * `data-unlaid` is the honesty valve. A button the layout table does not describe still appears —
 * under More, tagged — because a tool that quietly vanishes from a toolbar looks exactly like one
 * that was deliberately removed, and the next person to notice is a user who needed it.
 */
import { icon } from "../ui/icons";
import { CLOSE_POPUPS, closeMenus } from "../ui/menus";
import { GROUP_LABELS, type ToolContext, TOOLS, describe, iconFor, primaryTitles, specFor, unlaidTitles } from "./toolbarLayout";

export interface ToolbarView {
  /** Re-lay the bar for a new context (selection gained/lost, capability changed). */
  update(ctx: ToolContext): void;
  /** Titles the table did not describe — empty in a correct build. */
  unlaid(): string[];
}

const MORE_TITLE = "More tools";

/**
 * Take over `host`, splitting its `.tool-btn` children into a labeled primary row and a More menu.
 * Buttons keep their identity, handlers and `data-cap` gating — only their parent changes.
 */
export function installToolbarView(host: HTMLElement): ToolbarView {
  const buttons = [...host.querySelectorAll<HTMLButtonElement>(".tool-btn")];
  // The dividers were separating a row of 25 glyphs. Labeled verbs plus a menu do that job now, and
  // leaving them behind would draw lines between groups that no longer sit together.
  host.querySelectorAll(".tool-sep").forEach((s) => s.remove());

  const byTitle = new Map<string, HTMLButtonElement>();
  for (const b of buttons) {
    const t = b.getAttribute("title") || "";
    if (t && !byTitle.has(t)) byTitle.set(t, b);
    b.dataset.glyph = b.textContent || "";
  }
  const registered = [...byTitle.keys()];
  const unlaid = unlaidTitles(registered);

  const bar = document.createElement("div");
  bar.className = "vt-primary";
  const moreBtn = document.createElement("button");
  moreBtn.className = "tool-btn vt-more";
  moreBtn.type = "button";
  moreBtn.setAttribute("aria-haspopup", "true");
  moreBtn.setAttribute("aria-expanded", "false");
  moreBtn.title = MORE_TITLE;
  moreBtn.textContent = "More ▾";
  const menu = document.createElement("div");
  menu.className = "vt-menu";
  menu.hidden = true;

  host.replaceChildren(bar, moreBtn, menu);

  const setOpen = (open: boolean) => {
    menu.hidden = !open;
    moreBtn.setAttribute("aria-expanded", String(open));
    moreBtn.classList.toggle("on", open);
  };
  moreBtn.onclick = (e) => {
    e.stopPropagation();
    const opening = menu.hidden;
    // Opening dismisses every other popup first. Without this the More menu stacked on top of an
    // open Open/Save panel, two dropdowns over the model with neither yielding.
    if (opening) closeMenus(menu);
    setOpen(opening);
  };
  // ...and the reverse: another popup opening closes this one.
  window.addEventListener(CLOSE_POPUPS, (e) => {
    if ((e as CustomEvent<{ keep?: Element }>).detail?.keep !== menu) setOpen(false);
  });
  // Clicking a tool inside More runs it and closes the menu: a menu that stays open after you have
  // chosen from it covers the very model you just acted on.
  menu.addEventListener("click", (e) => {
    if ((e.target as HTMLElement).closest(".tool-btn")) setOpen(false);
  });
  document.addEventListener("click", (e) => {
    if (!menu.hidden && !host.contains(e.target as Node)) setOpen(false);
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !menu.hidden) setOpen(false); });

  function labelFor(b: HTMLButtonElement, text: string | null) {
    // A mark stays: it is what a returning user recognises, and dropping it would make the relabelled
    // bar unfamiliar to everyone who had learned the old one. Which mark depends on what we have —
    // the vendored line icon when `TOOL_ICON` names one, the original emoji glyph when it does not.
    //
    // The fallback is not a nicety. Half a bar of crisp line icons beside half a bar of emoji is
    // ugly but READABLE; a blank square is a tool the user can no longer find. And R26-ICONS's own
    // test asserts every laid-out label resolves, so the fallback should stay unreached — if it ever
    // fires, `data-glyph-fallback` on the button says which tool fell through rather than leaving
    // the mismatch to be noticed by eye.
    b.replaceChildren();
    const name = text ? iconFor(text) : null;
    const svg = name ? icon(name, 16) : null;
    if (svg) {
      svg.classList.add("vt-icon");              // `icon()` already sets aria-hidden and currentColor
      b.append(svg);
      delete b.dataset.glyphFallback;
    } else {
      const g = document.createElement("span");
      g.className = "vt-glyph"; g.textContent = b.dataset.glyph || "";
      b.append(g);
      if (text) b.dataset.glyphFallback = name ?? "unmapped";
    }
    if (text) {
      const l = document.createElement("span");
      l.className = "vt-label"; l.textContent = text;
      b.append(l);
    }
    b.classList.toggle("icon-btn", !text);
  }

  function update(ctx: ToolContext) {
    const primary = primaryTitles(ctx, registered);
    const primarySet = new Set(primary);

    bar.replaceChildren();
    for (const title of primary) {
      const b = byTitle.get(title)!;
      labelFor(b, specFor(title)!.label);
      bar.append(b);
    }

    menu.replaceChildren();
    for (const [group, heading] of GROUP_LABELS) {
      const inGroup = TOOLS
        .filter((s) => s.group === group && !primarySet.has(s.title) && byTitle.has(s.title));
      if (!inGroup.length) continue;
      menu.append(section(heading, inGroup.map((s) => {
        const b = byTitle.get(s.title)!;
        labelFor(b, s.label);
        b.classList.add("vt-row");
        const d = describe(s);
        if (d) {
          const note = document.createElement("span");
          note.className = "vt-note"; note.textContent = d;
          b.append(note);
        }
        return b;
      })));
    }
    if (unlaid.length) {
      // Reported, not hidden — see the module docstring.
      menu.dataset.unlaid = String(unlaid.length);
      menu.append(section("Unlisted", unlaid.map((t) => {
        const b = byTitle.get(t)!;
        labelFor(b, t.split(" — ")[0] ?? t);
        b.classList.add("vt-row");
        return b;
      })));
    }
  }

  function section(heading: string, rows: HTMLElement[]): HTMLElement {
    const s = document.createElement("div");
    s.className = "vt-group";
    const h = document.createElement("div");
    h.className = "vt-group-h"; h.textContent = heading;
    s.append(h, ...rows);
    return s;
  }

  return { update, unlaid: () => unlaid };
}
