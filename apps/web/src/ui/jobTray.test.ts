import { describe, expect, it, vi } from "vitest";

import type { Job, JobState } from "../api/types";
import {
  activeCount, createJobPoller, hasArtifact, humanDuration, isActive, jobElapsed,
  deliverySummary, jobLabel, jobSummary, mountJobTray, renderJobTray, sortJobs,
} from "./jobTray";

/**
 * The job tray.
 *
 * Its failure mode is not a wrong pixel — it is a queue that *looks* calm. Every assertion below is
 * about one of the four ways a status list quietly stops telling the truth: a badge that counts
 * things nobody can act on, a failure that sorts beneath later successes, a poller that either never
 * stops or never restarts, and a completion announced twice.
 */

const J = (over: Partial<Job> = {}): Job => ({
  id: over.id ?? "j1",
  kind: "cobie_export",
  project_id: "p1",
  state: "queued" as JobState,
  params: {},
  result: null,
  error: null,
  actor: "me",
  created_at: "2026-07-29T10:00:00Z",
  started_at: null,
  finished_at: null,
  ...over,
});

describe("the badge counts what is still moving", () => {
  it("queued and running count; done and error do not", () => {
    const jobs = [
      J({ id: "a", state: "queued" }), J({ id: "b", state: "running" }),
      J({ id: "c", state: "done" }), J({ id: "d", state: "error" }),
    ];
    expect(activeCount(jobs)).toBe(2);
    expect(jobs.filter(isActive).map((j) => j.id)).toEqual(["a", "b"]);
  });

  it("an idle queue announces nothing", () => {
    expect(activeCount([J({ state: "done" }), J({ id: "z", state: "done" })])).toBe(0);
  });
});

describe("a failure does not sort away under later successes", () => {
  it("an OLD error outranks NEWER completed jobs", () => {
    const order = sortJobs([
      J({ id: "new-done", state: "done", created_at: "2026-07-29T12:00:00Z" }),
      J({ id: "old-error", state: "error", created_at: "2026-07-29T09:00:00Z", error: "boom" }),
      J({ id: "newer-done", state: "done", created_at: "2026-07-29T13:00:00Z" }),
    ]).map((j) => j.id);
    // Newest-first — the obvious sort — would put old-error last, which is when nobody sees it.
    expect(order[0]).toBe("old-error");
  });

  it("errors, then running, then queued, then finished newest-first", () => {
    const order = sortJobs([
      J({ id: "done-old", state: "done", created_at: "2026-07-29T08:00:00Z" }),
      J({ id: "queued", state: "queued" }),
      J({ id: "done-new", state: "done", created_at: "2026-07-29T14:00:00Z" }),
      J({ id: "running", state: "running" }),
      J({ id: "error", state: "error" }),
    ]).map((j) => j.id);
    expect(order).toEqual(["error", "running", "queued", "done-new", "done-old"]);
  });
});

describe("times say only what is true", () => {
  it("a queued job shows no timer — waiting is not work being done", () => {
    expect(jobElapsed(J({ state: "queued" }))).toBe("");
  });

  it("a running job shows elapsed against now; a finished one shows its total", () => {
    const now = Date.parse("2026-07-29T10:01:35Z");
    expect(jobElapsed(J({ state: "running", started_at: "2026-07-29T10:00:00Z" }), now)).toBe("1m 35s");
    expect(jobElapsed(J({
      state: "done", started_at: "2026-07-29T10:00:00Z", finished_at: "2026-07-29T10:00:12Z",
    }), now)).toBe("12s");
  });

  it("an unparseable stamp shows nothing rather than NaN", () => {
    expect(jobElapsed(J({ state: "running", started_at: "not-a-date" }))).toBe("");
  });

  it("durations read in the units a person waits in", () => {
    expect(humanDuration(9)).toBe("9s");
    expect(humanDuration(60)).toBe("1m 0s");
    expect(humanDuration(3725)).toBe("1h 2m");
  });
});

describe("labels and artifacts do not guess", () => {
  it("a registered kind gets its name; an unknown kind renders raw, not a fabricated label", () => {
    expect(jobLabel("compiled_set_pdf")).toBe("Compiled drawing set");
    expect(jobLabel("report_package")).toBe("Report package");
    expect(jobLabel("some_plugin_kind")).toBe("some_plugin_kind");
  });

  it("only a done job WITH an artifact_key offers a download", () => {
    expect(hasArtifact(J({ state: "done", result: { artifact_key: "k/1.pdf" } }))).toBe(true);
    expect(hasArtifact(J({ state: "done", result: {} }))).toBe(false);
    expect(hasArtifact(J({ state: "running", result: { artifact_key: "k/1.pdf" } }))).toBe(false);
  });

  it("an error row carries the server's message", () => {
    expect(jobSummary(J({ state: "error", error: "ifcopenshell: no such entity" })))
      .toBe("ifcopenshell: no such entity");
    expect(jobSummary(J({ state: "error" }))).toBe("failed");
  });
});

describe("rendering", () => {
  it("an empty queue explains the mechanism instead of rendering blank", () => {
    const host = document.createElement("div");
    renderJobTray(host, []);
    expect(host.textContent).toContain("No background jobs");
    // The load-bearing half: it says the work SURVIVES leaving, which is the whole point of a tray.
    expect(host.textContent).toContain("keep running if you close this");
  });

  it("a running job cannot be dismissed; a finished one can", () => {
    const host = document.createElement("div");
    renderJobTray(host, [J({ id: "r", state: "running" }), J({ id: "d", state: "done" })],
      { onDismiss: () => {} });
    expect(host.querySelectorAll("button[aria-label^='Dismiss']").length).toBe(1);
  });

  it("a download appears only when there is something to download", () => {
    const host = document.createElement("div");
    renderJobTray(host, [
      J({ id: "a", state: "done", result: { artifact_key: "k" } }),
      J({ id: "b", state: "done", result: {} }),
    ], { artifactUrl: (j) => `/x/${j.id}` });
    const links = [...host.querySelectorAll("a")];
    expect(links.length).toBe(1);
    expect(links[0]!.getAttribute("href")).toBe("/x/a");
  });

  /**
   * The Download `href`, which is a different sink class from everything else here.
   *
   * `textContent` does not cover it, and `innerHtmlGuard.test.ts` does not either — that ratchet
   * watches interpolation into `.innerHTML`, and this is an attribute assignment. A `javascript:`
   * URL contains nothing to escape, so an escape-based defence sees a clean string. Every gate in
   * the repo would pass.
   *
   * It is safe today because `artifactUrl` *builds* a fixed path from an id. These assertions are
   * about the day it stops doing that.
   */
  it("neutralises a hostile artifact URL instead of trusting the caller", () => {
    const host = document.createElement("div");
    renderJobTray(host, [J({ state: "done", result: { artifact_key: "k" } })], {
      artifactUrl: () => "javascript:alert(1)",
    });
    expect(host.querySelector("a")!.getAttribute("href")).toBe("#");
  });

  it("leaves a legitimate URL byte-for-byte alone, query string included", () => {
    const host = document.createElement("div");
    const url = "/projects/p1/jobs/j1/artifact?v=2&inline=true";
    renderJobTray(host, [J({ state: "done", result: { artifact_key: "k" } })], { artifactUrl: () => url });
    // The assertion that catches somebody "fixing" this with `safeUrl`, which HTML-escapes and would
    // turn `&inline` into `&amp;inline` — a broken link that still looks defended.
    expect(host.querySelector("a")!.getAttribute("href")).toBe(url);
  });

  it("a plugin-supplied kind is written as text, never as markup", () => {
    const host = document.createElement("div");
    renderJobTray(host, [J({ kind: "<img src=x onerror=alert(1)>" })]);
    expect(host.querySelector("img")).toBeNull();
    expect(host.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});

describe("the poller stops at rest and restarts on demand", () => {
  /** A hand-driven clock: nothing here waits on real time. */
  const clock = () => {
    let pending: (() => void) | null = null;
    return {
      setTimer: (fn: () => void) => { pending = fn; return 1; },
      clearTimer: () => { pending = null; },
      tick: async () => { const f = pending; pending = null; f?.(); await Promise.resolve(); },
      get scheduled() { return pending !== null; },
    };
  };

  it("makes no further requests once nothing is active", async () => {
    const c = clock();
    const fetch = vi.fn().mockResolvedValue([J({ state: "done" })]);
    const p = createJobPoller({ fetch, onUpdate: () => {}, ...c });
    await p.poke();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(c.scheduled).toBe(false);          // an idle project costs zero requests
  });

  it("keeps polling while a job is running", async () => {
    const c = clock();
    const fetch = vi.fn().mockResolvedValue([J({ state: "running" })]);
    const p = createJobPoller({ fetch, onUpdate: () => {}, ...c });
    await p.poke();
    expect(c.scheduled).toBe(true);
    await c.tick();
    expect(fetch).toHaveBeenCalledTimes(2);
    p.stop();
  });

  it("a failed request retries instead of killing the loop", async () => {
    const c = clock();
    const fetch = vi.fn().mockRejectedValue(new Error("offline"));
    const p = createJobPoller({ fetch, onUpdate: () => {}, ...c });
    await p.poke();
    // A dropped poll is not a user-facing event, but it must not be a terminal one either.
    expect(c.scheduled).toBe(true);
    p.stop();
  });

  it("stop() is final — a queued tick after it does nothing", async () => {
    const c = clock();
    const fetch = vi.fn().mockResolvedValue([J({ state: "running" })]);
    const p = createJobPoller({ fetch, onUpdate: () => {}, ...c });
    await p.poke();
    p.stop();
    await c.tick();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("announces a completion ONCE, however many times it is polled afterwards", async () => {
    const c = clock();
    const settled = vi.fn();
    let state: JobState = "running";
    const fetch = vi.fn(() => Promise.resolve([J({ id: "x", state })]));
    const p = createJobPoller({ fetch, onUpdate: () => {}, onSettled: settled, ...c });

    await p.poke();                       // seen running
    state = "done";
    await c.tick();                       // transition → announce
    expect(settled).toHaveBeenCalledTimes(1);

    await p.poke();                       // still done → must not re-announce
    await p.poke();
    expect(settled).toHaveBeenCalledTimes(1);
  });

  it("does not announce a job that was already finished when the tray opened", async () => {
    const c = clock();
    const settled = vi.fn();
    const p = createJobPoller({
      fetch: () => Promise.resolve([J({ state: "done" })]), onUpdate: () => {}, onSettled: settled, ...c,
    });
    await p.poke();
    // Otherwise opening the tray fires a burst of notifications for last week's exports.
    expect(settled).not.toHaveBeenCalled();
  });
});

/**
 * The mount — i.e. **the path to the feature**, which is the half this repo keeps shipping without.
 *
 * A tray that renders perfectly and is never reachable is indistinguishable from one that was never
 * built, and `renderJobTray` passing its own tests says nothing about whether anything calls it.
 */
describe("the tray is actually reachable", () => {
  const mount = (jobs: Job[]) => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const m = mountJobTray({ host, fetch: () => Promise.resolve(jobs) });
    return { host, m, btn: () => host.querySelector<HTMLButtonElement>("#jobs-btn")! };
  };

  it("stays hidden when there is nothing to say — no permanent zero in the header", async () => {
    const { m, btn } = mount([]);
    await m.poke();
    expect(btn().hidden).toBe(true);
  });

  it("appears after a poke when the project has jobs, and badges only the ACTIVE ones", async () => {
    const { m, btn } = mount([J({ id: "a", state: "running" }), J({ id: "b", state: "done" })]);
    expect(btn().hidden).toBe(true);        // nothing has been fetched yet
    await m.poke();
    expect(btn().hidden).toBe(false);
    expect(btn().textContent).toBe("⚙ 1"); // two jobs, one moving
  });

  it("shows the gear with no number once everything has settled", async () => {
    const { m, btn } = mount([J({ state: "done" })]);
    await m.poke();
    expect(btn().textContent).toBe("⚙");
  });

  it("opening the panel renders the rows and marks itself expanded", async () => {
    const { host, m, btn } = mount([J({ kind: "model_export", state: "running" })]);
    await m.poke();
    btn().click();
    expect(btn().getAttribute("aria-expanded")).toBe("true");
    expect(host.textContent).toContain("Model export");
  });

  it("Escape closes it, like every other overlay in the app", async () => {
    const { m, btn } = mount([J({ state: "running" })]);
    await m.poke();
    btn().click();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(btn().getAttribute("aria-expanded")).toBe("false");
  });

  /**
   * R24-REPORTS-BY-MOMENT — the send affordance is gated on there being a file, exactly like the
   * download link beside it. Asserted rather than assumed because the two gates are written
   * separately, and a "Send" on a running job offers to mail something that does not exist yet.
   */
  it("offers Send only on rows that actually have an artifact", () => {
    const host = document.createElement("div");
    const sent: string[] = [];
    renderJobTray(host, [
      J({ id: "running", state: "running" }),
      J({ id: "noart", state: "done", result: {} }),
      J({ id: "ready", state: "done", result: { artifact_key: "k" } }),
    ], { onSend: (j) => sent.push(j.id) });

    const buttons = [...host.querySelectorAll("button")].filter((b) => b.textContent === "Send");
    expect(buttons.length).toBe(1);
    buttons[0]!.click();
    expect(sent).toEqual(["ready"]);
  });

  /** Omitting `onSend` must offer no button at all — the same contract `artifactUrl` already has,
   *  so a host that cannot deliver does not show a control that would throw. */
  it("offers no Send affordance when onSend is omitted", () => {
    const host = document.createElement("div");
    renderJobTray(host, [J({ state: "done", result: { artifact_key: "k" } })], {});
    expect([...host.querySelectorAll("button")].some((b) => b.textContent === "Send")).toBe(false);
  });
});

/**
 * A scheduled delivery has no audience at the moment it happens.
 *
 * A person clicking **Send** sees the per-recipient result in the response. A routine firing on its
 * cadence has nobody watching, so the only place the outcome can surface is the row — and an owner
 * package that quietly did not send looks exactly like one that did. These assert the row says.
 */
describe("a scheduled delivery is visible on the row that did it", () => {
  const withDelivery = (delivery: unknown) =>
    J({ state: "done", result: { artifact_key: "k", delivery } });

  it("says nothing at all when no delivery was asked for", () => {
    expect(jobSummary(J({ state: "done", result: { artifact_key: "k" } }))).toBe("done");
    expect(deliverySummary(J({ state: "done", result: null }))).toBe("");
  });

  it("reports a clean send by how many actually went", () => {
    expect(jobSummary(withDelivery({ recipients: 2, results: { sent: ["a@x", "b@x"] } })))
      .toBe("done · emailed 2");
  });

  it("NAMES the states that are not `sent`, because they need different fixes", () => {
    // `disabled` means no SMTP is configured; `error` means it is and the send failed. Collapsing
    // them into "some failed" would hide which one somebody is looking at.
    expect(jobSummary(withDelivery({ results: { sent: ["a@x"], disabled: ["b@x"], error: ["c@x"] } })))
      .toBe("done · emailed 1 of 3 (1 disabled, 1 error)");
  });

  it("surfaces a refusal and a thrown failure distinctly", () => {
    expect(jobSummary(withDelivery({ refused: "at least one recipient is required", status: 422 })))
      .toBe("done · not sent: at least one recipient is required");
    expect(jobSummary(withDelivery({ error: "OSError: smtp unreachable" })))
      .toBe("done · send failed: OSError: smtp unreachable");
  });

  it("stays `done` throughout — a bounced address is not a failed job", () => {
    // The same rule the server applies: it leaves the job `done` and records the problem here,
    // because the artifact exists either way and re-running the report is the wrong repair.
    for (const d of [{ error: "x" }, { refused: "y" }, { results: { error: ["a@x"] } }]) {
      expect(jobSummary(withDelivery(d)).startsWith("done")).toBe(true);
    }
  });

  it("ignores a malformed delivery record rather than rendering junk", () => {
    expect(jobSummary(withDelivery("not-an-object"))).toBe("done");
    expect(jobSummary(withDelivery({ results: {} }))).toBe("done");
  });
});
