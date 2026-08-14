/**
 * R45 — the four scheduling methods, on a screen.
 *
 * Each of these took three gates to ship honestly, and the sequence is worth recording because it is
 * the same question asked at four depths:
 *
 * 1. `test_vendor_reachable` — is the vendored *module* reached from the API at all?
 * 2. `test_reachable` — is that module behind a *route*?
 * 3. `test_route_reachability` — does a *client method* call that route?
 * 4. `clientCallers.test.ts` — does a *screen* call that client method?
 *
 * Every one of them caught something. A module behind no route, a route no client calls and a client
 * method no screen calls are all indistinguishable from a shipped feature when read from the inside,
 * and each layer only sees its own hop. This file is the fourth hop.
 *
 * **The rendering rule, shared by all four: read `available` before reading any number.** Every one of
 * these engines can be asked a question it cannot answer — a project with no locations, a schedule
 * with a logic loop, a levelling run with no crew caps — and every one returns `available: false` with
 * a reason rather than a zero. Rendering the zero is how "we could not measure" becomes "this is
 * terrible" on somebody's screen.
 */
import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

type Row = { label: string; value: string; hint?: string };

function card(title: string, sub: string): HTMLElement {
  const c = document.createElement("div");
  c.className = "dash-card";
  c.style.cssText = "margin:6px 0";
  c.innerHTML = `<div class="section-title">${esc(title)}</div><div class="meta">${esc(sub)}</div>`;
  return c;
}

/** A result block. `available: false` renders the reason and NO numbers — never a plausible zero. */
function render(host: HTMLElement, out: { available: boolean; reason?: string }, rows: Row[]): void {
  host.innerHTML = "";
  if (!out.available) {
    const why = document.createElement("div");
    why.className = "meta";
    why.dataset.unavailable = "1";
    why.style.cssText = "padding:6px 0;line-height:1.45";
    // textContent: the reason is composed server-side and names user data (a location, a trade).
    why.textContent = out.reason || "Not available for this project.";
    host.appendChild(why);
    return;
  }
  const grid = document.createElement("div");
  grid.style.cssText = "display:flex;flex-wrap:wrap;gap:14px;margin:4px 0";
  for (const r of rows) {
    const cell = document.createElement("div");
    cell.style.cssText = "min-width:120px";
    const v = document.createElement("div");
    v.style.cssText = "font-size:18px;font-weight:700;font-variant-numeric:tabular-nums";
    v.textContent = r.value;
    const l = document.createElement("div");
    l.className = "meta"; l.style.fontSize = "11px";
    l.textContent = r.label;
    cell.append(v, l);
    if (r.hint) { const h = document.createElement("div"); h.className = "meta"; h.style.fontSize = "10.5px"; h.textContent = r.hint; cell.appendChild(h); }
    grid.appendChild(cell);
  }
  host.appendChild(grid);
}

function runner(host: HTMLElement, label: string, go: () => Promise<void>): HTMLButtonElement {
  const b = document.createElement("button");
  b.className = "tool-btn";
  b.textContent = label;
  b.onclick = async () => {
    b.disabled = true; host.textContent = "Running…";
    try { await go(); } catch (e) { host.textContent = `failed: ${(e as Error).message}`; }
    finally { b.disabled = false; }
  };
  return b;
}

export function renderScheduleMethods(ctx: PanelContext): HTMLElement {
  const pid = ctx.host.projectId()!;
  const api = ctx.host.api;
  const wrap = document.createElement("div");

  // ── DCMA 14-point ────────────────────────────────────────────────────────────────────────────
  const hc = card("Schedule quality — DCMA 14-point",
    "The industry's shared definition of whether a schedule is trustworthy. Checks that could not "
    + "run are excluded from the score, so a clean schedule reads 100 over its runnable checks.");
  const hOut = document.createElement("div");
  hc.appendChild(runner(hOut, "▶ Assess", async () => {
    const r = await api.scheduleHealth(pid);
    render(hOut, r, r.available ? [
      { label: "grade", value: r.grade ?? "—" },
      { label: "score", value: r.score === null ? "—" : `${r.score}` , hint: `${r.assessed} checks run` },
      { label: "failed", value: `${r.failed}` },
      { label: "skipped", value: `${r.skipped}`, hint: "excluded from the score" },
    ] : []);
    if (r.available) {
      const fails = r.checks.filter((c) => c.status === "fail");
      if (fails.length) {
        const ul = document.createElement("div"); ul.className = "meta"; ul.style.marginTop = "4px";
        for (const c of fails) {
          const li = document.createElement("div");
          li.textContent = `${c.number}. ${c.name} — ${c.detail}`;
          ul.appendChild(li);
        }
        hOut.appendChild(ul);
      }
    }
  }));
  hc.appendChild(hOut); wrap.appendChild(hc);

  // ── Line of balance ──────────────────────────────────────────────────────────────────────────
  const fc = card("Flowline — line of balance",
    "Where each crew is, and whether anyone is in anyone's way. CPM cannot express crew continuity: "
    + "its earliest-start pass is exactly what fragments a gang into work-a-floor-then-wait.");
  const fOut = document.createElement("div");
  fc.appendChild(runner(fOut, "▶ Compute flowline", async () => {
    const r = await api.scheduleFlowline(pid);
    const cost = Object.entries(r.continuity_cost_days ?? {});
    const worst = cost.sort((a, b) => b[1] - a[1])[0];
    render(fOut, r, r.available ? [
      { label: "duration", value: `${r.duration_days}d` },
      { label: "locations", value: `${r.locations.length}` },
      { label: "trades", value: `${r.trades.length}` },
      { label: "continuity cost", value: worst ? `${worst[1]}d` : "0d",
        hint: worst ? `worst: ${worst[0]}` : "no crew was pushed" },
    ] : []);
  }));
  fc.appendChild(fOut); wrap.appendChild(fc);

  // ── Takt ─────────────────────────────────────────────────────────────────────────────────────
  const tc = card("Takt train — a fixed rhythm",
    "Not the same method as the flowline. Every wagon occupies one zone for exactly one takt, so "
    + "(wagons + zones − 1) takts is knowable before the work is estimated. Paid for in idle capacity.");
  const tOut = document.createElement("div");
  tc.appendChild(runner(tOut, "▶ Build train", async () => {
    const r = await api.scheduleTaktTrain(pid);
    const u = Object.values(r.utilisation ?? {});
    const lowest = u.length ? Math.min(...u) : null;
    render(tOut, r, r.available ? [
      { label: "takt", value: `${r.takt_days}d`, hint: `min ${r.minimum_takt_days}d — set by ${r.minimum_takt_set_by}` },
      { label: "duration", value: `${r.duration_days}d`, hint: `${r.takt_count} takts` },
      { label: "lowest utilisation", value: lowest === null ? "—" : `${Math.round(lowest * 100)}%`,
        hint: "capacity paid for and not worked" },
      { label: "overloaded", value: `${r.overloaded.length}` },
    ] : []);
  }));
  tc.appendChild(tOut); wrap.appendChild(tc);

  // ── Levelling ────────────────────────────────────────────────────────────────────────────────
  const lc = card("Resource levelling",
    "Deterministic: the same input always gives the same answer, so a planner can follow the "
    + "placements by hand and defend them. Advisory — nothing is written.");
  const capIn = document.createElement("input");
  capIn.type = "text"; capIn.placeholder = 'crew caps, e.g. Carpentry=8, Electrical=4';
  capIn.className = "tool-btn";
  capIn.style.cssText = "min-width:260px;text-align:left;cursor:text";
  const horizon = document.createElement("select");
  horizon.className = "tool-btn";
  const HORIZONS: ReadonlyArray<readonly [string, string]> = [
    ["within_float", "keep the finish"], ["extend_finish", "allow a later finish"]];
  for (const [v, t] of HORIZONS) {
    const o = document.createElement("option"); o.value = v; o.textContent = t; horizon.appendChild(o);
  }
  const lOut = document.createElement("div");
  const lRow = document.createElement("div");
  lRow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:4px 0";
  lRow.append(capIn, horizon, runner(lOut, "▶ Level", async () => {
    // `Trade=8, Other=4` -> {Trade: 8, Other: 4}. Parsed here rather than server-side because a
    // malformed cap should be a visible client error, not a silent empty object the API refuses.
    const caps: Record<string, number> = {};
    for (const part of capIn.value.split(",")) {
      const [k, v] = part.split("=");
      const n = Number((v ?? "").trim());
      if (k?.trim() && Number.isFinite(n) && n > 0) caps[k.trim()] = n;
    }
    const r = await api.scheduleLevel(pid, caps,
      horizon.value as "within_float" | "extend_finish");
    render(lOut, r, r.available ? [
      { label: "moves", value: `${r.move_count}` },
      { label: "unresolved", value: `${r.unresolved_count}`,
        hint: r.horizon === "within_float" ? "the horizon would not allow a fix" : "" },
      { label: "finish moves", value: `${r.finish_moved_days}d` },
    ] : []);
  }));
  lc.append(lRow, lOut); wrap.appendChild(lc);

  return wrap;
}
