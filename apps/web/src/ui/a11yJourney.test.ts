/**
 * R39-A11Y-JOURNEYS ② — a journey is Tab → operate → land, not an aria attribute.
 *
 * Each room is mounted from the renderer that actually ships (briefs, work queue, room tabs).
 * jsdom does not walk the browser tab order; we walk the same focusable set `result.ts` / `modal.ts`
 * use, which is the claim the product makes about what a keyboard can reach.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ModuleDef } from "../api/types";
import type { PanelContext } from "../portal/panelContext";
import { renderCostBrief } from "../portal/panels/costBrief";
import { renderDealBrief } from "../portal/panels/dealBrief";
import { renderOperateBrief } from "../portal/panels/operateBrief";
import { renderPlanningBrief } from "../portal/panels/planningBrief";
import { renderScheduleBrief } from "../portal/panels/scheduleBrief";
import { renderWorkQueue } from "../portal/panels/workQueue";
import { buildRoomTabs, renderRoomTabs } from "../shell/roomTabs";
import { ROOM_IDS } from "../shell/spine";
import {
  ROOM_PRIMARY, focusIsSane, operate, tabReach, type RoomId,
} from "./a11yJourney";

function mod(key: string): ModuleDef {
  return {
    key, name: key, section: "x", icon: "•", pinnable: false, fields: [],
    workflow: { initial: "open", states: ["open"], transitions: [] },
  };
}

function land(root: HTMLElement, name: string): void {
  const pane = document.createElement("div");
  pane.dataset.landed = name;
  pane.setAttribute("role", "region");
  pane.setAttribute("aria-label", name);
  const inp = document.createElement("input");
  inp.setAttribute("aria-label", `Search ${name}`);
  pane.appendChild(inp);
  root.appendChild(pane);
  inp.focus();
}

function ctx(api: Record<string, unknown>, mods: ModuleDef[]): PanelContext {
  const root = document.createElement("div");
  const host: PanelContext = {
    root,
    host: { projectId: () => "p1", api } as unknown as PanelContext["host"],
    mods,
    activeKey: null,
    bar: (title) => {
      const bar = document.createElement("div");
      const back = document.createElement("button");
      back.type = "button";
      back.textContent = "←";
      const t = document.createElement("strong");
      t.textContent = title;
      bar.append(back, t);
      return bar;
    },
    buildNav: () => undefined,
    renderHome: async () => undefined,
    openModule: async (m) => { land(root, m.key); },
    navigate: (key) => { land(root, key); },
    hasDest: () => true,
  };
  return host;
}

function rates() {
  return {
    rfi: { total: 4, open: 1, overdue: 0, overdue_pct: 0, avg_turnaround_days: 3 },
    submittal: { total: 2, open: 1, overdue: 0, overdue_pct: 0, avg_turnaround_days: 5 },
  };
}

async function mountRoom(room: RoomId): Promise<HTMLElement> {
  const chrome = document.createElement("div");
  document.body.appendChild(chrome);
  const tabs = document.createElement("div");
  chrome.appendChild(tabs);
  renderRoomTabs(tabs, buildRoomTabs(), room, (id) => {
    const t = tabs.querySelector<HTMLElement>(`[data-room="${id}"]`);
    t?.focus();
  });
  const pane = document.createElement("div");
  chrome.appendChild(pane);

  if (room === "design") return chrome;

  if (room === "planning") {
    const host = ctx({
      benchmarkResponseRates: vi.fn().mockResolvedValue(rates()),
      benchmarkCosts: vi.fn().mockResolvedValue({ cost_codes: [], code_count: 0, min_samples: 3 }),
    }, [mod("rfi")]);
    pane.appendChild(await renderPlanningBrief(host));
    return chrome;
  }
  if (room === "cost") {
    const host = ctx({
      gmpBudget: vi.fn().mockResolvedValue({
        gmp: { contract_value: 1, computed: 1 },
        totals: { budget: 1 },
        completion: { eac: 1, projected_over_under: 0 },
        buyout: { packages: 1, bought_out: 0, budget: 1, awarded: 0, savings: 0 },
      }),
      projectPulse: vi.fn().mockResolvedValue({ cost: { unpricedChanges: 0, exposurePct: 0 } }),
    }, [mod("budget")]);
    pane.appendChild(await renderCostBrief(host));
    return chrome;
  }
  if (room === "schedule") {
    const host = ctx({
      scheduleLookahead: vi.fn().mockResolvedValue({ count: 0, weeks_detail: [] }),
      scheduleAlerts: vi.fn().mockResolvedValue({ alerts: [], counts: { high: 0, medium: 0, low: 0 } }),
      scheduleVariance: vi.fn().mockResolvedValue({
        captured_at: "2026-08-18", baseline_count: 0,
        summary: { slipped: 0, max_slip_days: 0 }, activities: [],
      }),
    }, [mod("schedule_activity")]);
    pane.appendChild(await renderScheduleBrief(host));
    return chrome;
  }
  if (room === "deal") {
    const host = ctx({
      projectPulse: vi.fn().mockResolvedValue({ deal: { irrPct: 14, band: [12, 18] } }),
      diligenceReadiness: vi.fn().mockResolvedValue({
        go: true,
        due_diligence: { total: 1, cleared: 1, flagged: 0 },
        entitlements: { pending: 0, approved: 1, denied: 0, total: 1 },
      }),
      masterBuilderBrief: vi.fn().mockResolvedValue({
        steps: [{ n: 1, key: "place", title: "Place", dest: "__land__", status: "gap", gaps: [] }],
      }),
    }, []);
    pane.appendChild(await renderDealBrief(host));
    return chrome;
  }
  if (room === "operate") {
    const host = ctx({
      cmmsKpis: vi.fn().mockResolvedValue({
        total: 1, open: 1, completed: 0, overdue: 0, pm_compliance_pct: 90, mttr_days: 2,
      }),
      fcaIndex: vi.fn().mockResolvedValue({
        elements: 1, open_deficiencies: 0, fci_pct: 4, band: "good", note: "",
      }),
    }, [mod("work_order")]);
    pane.appendChild(await renderOperateBrief(host));
    return chrome;
  }
  const host = ctx({
    workQueue: vi.fn().mockResolvedValue({
      total: 1, actionable: 1, no_action: 0,
      buckets: [{
        key: "today", label: "Today", means: "due today", count: 1,
        items: [{
          module: "rfi", module_name: "RFIs", icon: "R", id: "1", ref: "RFI-1",
          title: "Clash", state: "open", assignee: "you", reason: "assigned",
          due: "2026-08-19", bucket: "today", actions: [], blocked_actions: [],
        }],
      }],
    }),
  }, [mod("rfi")]);
  pane.appendChild(host.root);
  await renderWorkQueue(host);
  return chrome;
}

afterEach(() => { document.body.innerHTML = ""; });

describe("R39-A11Y-JOURNEYS ② — one primary per room", () => {
  it("names every room exactly once", () => {
    expect(Object.keys(ROOM_PRIMARY).sort()).toEqual([...ROOM_IDS].sort());
  });

  it.each([...ROOM_IDS])("%s: Tab reaches the primary, operating it lands focus", async (room) => {
    const chrome = await mountRoom(room);
    const primary = chrome.querySelector<HTMLElement>(ROOM_PRIMARY[room].selector);
    expect(primary, `${room} has no ${ROOM_PRIMARY[room].selector}`).toBeTruthy();
    expect(chrome.querySelectorAll("[data-room-primary]").length, `${room} must have one primary`)
      .toBe(room === "design" ? 0 : 1);
    expect(tabReach(chrome, primary!)).toBe(true);
    operate(primary!);
    expect(focusIsSane(chrome), `${room} dropped focus onto ${document.activeElement?.nodeName}`)
      .toBe(true);
  });

  it("an empty work queue still has a keyboard primary", async () => {
    const chrome = document.createElement("div");
    document.body.appendChild(chrome);
    const host = ctx({
      workQueue: vi.fn().mockResolvedValue({
        total: 0, actionable: 0, no_action: 0, buckets: [],
      }),
    }, []);
    chrome.appendChild(host.root);
    await renderWorkQueue(host);
    const primary = chrome.querySelector<HTMLElement>(ROOM_PRIMARY.work.selector);
    expect(primary?.textContent).toBe("Refresh queue");
    expect(tabReach(chrome, primary!)).toBe(true);
    operate(primary!);
    expect(focusIsSane(chrome)).toBe(true);
  });
});
