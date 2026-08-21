import { describe, expect, it, vi } from "vitest";

import { fetchArrayBufferWithProgress, withLoading } from "./feedback";
import { JobStillRunning } from "../api/waitForJob";
import type { Job } from "../api/types";

const overlayShown = () =>
  !!document.querySelector(".loading-overlay")?.classList.contains("show");

// Mirrors viewer/app.ts loadProjectModel(): stream the project's model.frag, but fail open to the
// "no model" state (returning false) whenever there's no loadable geometry — a 404, an empty body,
// or a payload the Fragments parser rejects. A metadata-only project (property index uploaded, no
// .frag published) must clear the "loading model" overlay and let the portal mount, exactly like a
// brand-new project does — never spin forever.
async function loadProjectModelSim(
  container: HTMLElement,
  loadFragments: (b: ArrayBuffer) => Promise<void>,
): Promise<boolean> {
  return (
    (await withLoading(container, "loading model", async () => {
      let buffer: ArrayBuffer;
      try {
        buffer = await fetchArrayBufferWithProgress("/projects/x/model.frag", {}, () => {});
      } catch {
        return false; // 404 — no published model
      }
      if (buffer.byteLength === 0) return false; // empty body — no geometry
      try {
        await loadFragments(buffer);
      } catch {
        return false; // corrupt / non-.frag bytes
      }
      return true;
    })) ?? false
  );
}

describe("viewer model auto-load: graceful no-geometry handling", () => {
  it("fetchArrayBufferWithProgress rejects on a 404", async () => {
    vi.stubGlobal("fetch", async () => new Response("not found", { status: 404 }));
    await expect(
      fetchArrayBufferWithProgress("/projects/x/model.frag", {}, () => {}),
    ).rejects.toThrow(/404/);
    vi.unstubAllGlobals();
  });

  it("clears the overlay when model.frag 404s (metadata-only project)", async () => {
    vi.stubGlobal("fetch", async () => new Response("not found", { status: 404 }));
    const container = document.createElement("div");
    document.body.appendChild(container);
    const loaded = await loadProjectModelSim(container, async () => {
      throw new Error("loadFragments must not be called on a 404");
    });
    expect(loaded).toBe(false);
    expect(overlayShown()).toBe(false);
    vi.unstubAllGlobals();
  });

  it("clears the overlay on an empty 200 body without invoking the Fragments parser", async () => {
    vi.stubGlobal("fetch", async () => new Response(new ArrayBuffer(0), { status: 200 }));
    const container = document.createElement("div");
    document.body.appendChild(container);
    let parserCalled = false;
    const loaded = await loadProjectModelSim(container, async () => {
      parserCalled = true;
    });
    expect(loaded).toBe(false);
    expect(parserCalled).toBe(false); // empty body must not reach the (potentially hanging) worker
    expect(overlayShown()).toBe(false);
    vi.unstubAllGlobals();
  });

  it("clears the overlay when the payload is not a valid .frag (parser rejects)", async () => {
    // e.g. a proxy that rewrites 404 → 200 HTML: non-empty bytes reach the parser, which rejects.
    vi.stubGlobal("fetch", async () => new Response("<!doctype html>…", { status: 200 }));
    const container = document.createElement("div");
    document.body.appendChild(container);
    const loaded = await loadProjectModelSim(container, async () => {
      throw new Error("not a fragments file");
    });
    expect(loaded).toBe(false);
    expect(overlayShown()).toBe(false);
    vi.unstubAllGlobals();
  });

  it("loads and reports success when a real .frag is served", async () => {
    vi.stubGlobal("fetch", async () => new Response(new Uint8Array([1, 2, 3, 4]), { status: 200 }));
    const container = document.createElement("div");
    document.body.appendChild(container);
    const loaded = await loadProjectModelSim(container, async () => {
      /* parser succeeds */
    });
    expect(loaded).toBe(true);
    expect(overlayShown()).toBe(false);
    vi.unstubAllGlobals();
  });
});

describe("withLoading — a still-running job is not a failed task", () => {
  it("toasts info and does not say the label failed", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const job = {
      id: "j1", kind: "ids_validate", project_id: "p1", state: "running",
      params: null, result: null, error: null, actor: null,
      created_at: null, started_at: null, finished_at: null,
    } as Job;
    await withLoading(container, "Queueing IDS", async () => {
      throw new JobStillRunning("ids_validate", job);
    });
    const text = [...document.querySelectorAll(".toast")]
      .map((el) => el.textContent || "").join(" ");
    expect(text).toMatch(/still running — watch the job tray/);
    expect(text).not.toMatch(/Queueing IDS failed/);
  });
});
