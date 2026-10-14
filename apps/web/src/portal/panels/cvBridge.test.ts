import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CvBridgeStatus } from "../../api/types";
import { bridgeNote, contractRows, endpointRows, renderCvBridge } from "./cvBridge";
import type { PanelContext } from "../panelContext";

const ST: CvBridgeStatus = {
  feature: "cv_progress_bridge",
  enabled: false,
  note: "Computer-vision % complete from site photos is an external, feature-flagged bridge.",
  contract: { activity: "schedule_activity id OR name", percent: "0–100" },
  batch_contract: { estimates: "[ {activity, percent}, … ]" },
  reference_adapter: "docs/cv-bridge.md",
};

function ctxFor(st: CvBridgeStatus | Error): { ctx: PanelContext; calls: string[] } {
  const calls: string[] = [];
  const api = {
    cvProgressStatus: vi.fn(async (pid: string) => {
      calls.push(pid);
      if (st instanceof Error) throw st;
      return st;
    }),
  };
  return { ctx: { host: { api } } as unknown as PanelContext, calls };
}

/** An ATTACHED slot — the state the real caller appends before awaiting. */
function slot(): HTMLElement {
  const el = document.createElement("div");
  document.body.appendChild(el);
  return el;
}

beforeEach(() => { document.body.innerHTML = ""; });

describe("bridgeNote", () => {
  it("names the flag and refuses to imply any number when the bridge is off", () => {
    const n = bridgeNote(ST);
    expect(n.kind).toBe("warn");
    expect(n.html).toContain("NOT ENABLED");
    expect(n.html).toContain("AEC_CV_BRIDGE");
    // the whole point of the disabled state: nothing is invented
    expect(n.html).toMatch(/fabricated/);
  });

  it("says estimates are written to the activity when it is on", () => {
    const n = bridgeNote({ ...ST, enabled: true });
    expect(n.kind).toBe("ok");
    expect(n.html).toContain("ENABLED");
    expect(n.html).toContain("percent");
  });
});

describe("contractRows", () => {
  it("turns the engine's contract into rows", () => {
    expect(contractRows(ST)).toEqual([
      { field: "activity", meaning: "schedule_activity id OR name" },
      { field: "percent", meaning: "0–100" },
    ]);
  });

  it("survives a response with no contract at all rather than throwing in a panel", () => {
    expect(contractRows({ ...ST, contract: undefined as unknown as Record<string, string> })).toEqual([]);
  });
});

describe("endpointRows", () => {
  it("builds both doors for the project, and says which one a sweep uses", () => {
    const rows = endpointRows("P1");
    expect(rows.map((r) => r.path)).toEqual([
      "/projects/P1/cv-progress/ingest",
      "/projects/P1/cv-progress/ingest-batch",
    ]);
    expect(rows[1]?.use).toContain("sweep");
    expect(rows.every((r) => r.method === "POST")).toBe(true);
  });
});

describe("renderCvBridge", () => {
  it("writes the flag, both endpoints and the contract into an attached slot", async () => {
    const host = slot();
    const { ctx, calls } = ctxFor(ST);
    await renderCvBridge(ctx, host, "P1");
    expect(calls).toEqual(["P1"]);
    expect(host.textContent).toContain("NOT ENABLED");
    expect(host.querySelectorAll("tbody tr")).toHaveLength(2);
    expect(host.textContent).toContain("/projects/P1/cv-progress/ingest-batch");
    expect(host.textContent).toContain("schedule_activity id OR name");
    expect(host.textContent).toContain("docs/cv-bridge.md");
  });

  it("names the sweep contract separately from the single-estimate one", async () => {
    const host = slot();
    await renderCvBridge(ctxFor(ST).ctx, host, "P1");
    expect(host.textContent).toContain("estimates");
    expect(host.textContent).toContain("A sweep");
  });

  it("writes NOTHING into a slot that left the document while the fetch was in flight", async () => {
    // PR #527's hazard, which this panel file records: `ctx.root` belongs to whichever panel
    // rendered last, so a late write has to check that its own slot is still attached.
    const host = document.createElement("div");          // deliberately NOT appended
    await renderCvBridge(ctxFor(ST).ctx, host, "P1");
    expect(host.innerHTML).toBe("");
  });

  it("stays silent when the status call fails — the bridge state is informational", async () => {
    const host = slot();
    await expect(renderCvBridge(ctxFor(new Error("503")).ctx, host, "P1")).resolves.toBeUndefined();
    expect(host.innerHTML).toBe("");
  });

  it("escapes a contract value, which is server text rendered through innerHTML", async () => {
    const host = slot();
    const nasty = { ...ST, contract: { activity: "<img src=x onerror=alert(1)>" } };
    await renderCvBridge(ctxFor(nasty).ctx, host, "P1");
    expect(host.querySelector("img")).toBeNull();
    expect(host.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});
