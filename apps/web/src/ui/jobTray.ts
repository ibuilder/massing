/**
 * R24-JOB-TRAY — heavy work you can walk away from.
 *
 * The audit's finding 04: *"convert, reindex and republish are background work with foreground UI"* —
 * anything that can take a minute must be leaveable, resumable and visible from anywhere, or people
 * sit and watch it, or navigate away and lose the thread.
 *
 * **It was never a missing engine.** `services/api/src/aec_api/routers/jobs.py` has offered enqueue /
 * poll / list / artifact for a long time, over a durable queue with crash recovery and seven
 * registered kinds. What was missing is that `grep -rn "/jobs" apps/web/src` returned **nothing** —
 * no client had ever called one. Every gate measured the queue; none measured the path to it. So this
 * module is wiring, and it is small on purpose.
 *
 * Four rules the rendering carries, each of which is a way a status list normally goes wrong:
 *
 * * **The badge counts only what is still moving.** `queued + running`, never the total. A badge that
 *   includes yesterday's finished exports is a number you cannot act on, and the same reasoning
 *   already governs the room badges in the spine.
 * * **A failure does not scroll away.** Errors sort to the top with the active jobs and stay until
 *   dismissed. The default sort — newest first — is exactly what buries the one row that needed a
 *   human, because the failure is usually older than the three jobs that succeeded after it.
 * * **Polling stops when nothing is moving.** At rest the tray makes no requests at all. Five SSE
 *   handlers once polled the DB inside `async def gen()` and blocked the event loop for every client;
 *   a tray that polls a finished queue forever is the same mistake with a nicer face.
 * * **There is no cancel button.** The server has no cancel. A control that cannot do what it says is
 *   worse than an absent one — the same reason a disabled control here states its reason rather than
 *   disappearing.
 *
 * Styling is inline rather than in `style.css`, following `ui/palette.ts`: the tray is one
 * self-contained overlay and keeping it out of the global sheet means it cannot drift with the shell.
 */
import type { Job, JobState } from "../api/types";

/**
 * Human labels for the registered kinds (`jobs.py:294-300`).
 *
 * An unregistered kind renders its raw name rather than a guess — a plugin can register a kind in one
 * line, and inventing a friendly label for something we do not know about is how a UI starts lying.
 */
const KIND_LABEL: Record<string, string> = {
  echo: "Echo (test job)",
  cobie_export: "COBie export",
  compiled_set_pdf: "Compiled drawing set",
  model_export: "Model export",
  clash_detect: "Clash detection",
  escalation_scan: "Escalation scan",
  model_ci: "Model CI report",
};

export function jobLabel(kind: string): string {
  return KIND_LABEL[kind] ?? kind;
}

/** Jobs that are still going to change on their own. The only ones worth a badge, or a poll. */
export function isActive(j: Job): boolean {
  return j.state === "queued" || j.state === "running";
}

/** The badge number: what is still moving. Zero means the tray has nothing to announce. */
export function activeCount(jobs: readonly Job[]): number {
  return jobs.filter(isActive).length;
}

/**
 * Sort for display: **needs-a-human first**, then still-moving, then finished newest-first.
 *
 * Errors outrank running jobs deliberately. A failed COBie export from ten minutes ago is the only
 * row on the list that requires a decision; under a plain newest-first sort it sinks below every job
 * that succeeded after it, which is precisely when nobody notices it failed.
 */
const RANK: Record<JobState, number> = { error: 0, running: 1, queued: 2, done: 3 };

export function sortJobs(jobs: readonly Job[]): Job[] {
  return [...jobs].sort((a, b) => {
    const r = (RANK[a.state] ?? 9) - (RANK[b.state] ?? 9);
    if (r !== 0) return r;
    return String(b.created_at ?? "").localeCompare(String(a.created_at ?? ""));
  });
}

/** `2026-07-29T14:26:00Z` → ms, or null. A row with an unparseable stamp shows no time, not `NaN`. */
function ms(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? null : t;
}

/** `95s` → "1m 35s". Seconds below a minute, because the point of the tray is the long ones. */
export function humanDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

/**
 * Elapsed for a running job, total for a finished one, `""` when there is nothing honest to say.
 *
 * A queued job shows no timer: the elapsed time since it was *created* is not work being done, and
 * showing it makes a busy queue look like a slow job.
 */
export function jobElapsed(j: Job, now: number = Date.now()): string {
  const start = ms(j.started_at);
  if (start === null) return "";
  const end = ms(j.finished_at) ?? now;
  return humanDuration((end - start) / 1000);
}

/** The one-line status under the job name. Errors say what went wrong, truncated to stay one line. */
export function jobSummary(j: Job): string {
  if (j.state === "error") return j.error ? j.error.slice(0, 140) : "failed";
  if (j.state === "queued") return "queued";
  if (j.state === "running") return "running";
  return "done";
}

/** `done` **and** the handler parked something downloadable. Artifact kinds set `artifact_key`. */
export function hasArtifact(j: Job): boolean {
  return j.state === "done" && !!(j.result && typeof j.result === "object"
    && (j.result as Record<string, unknown>)["artifact_key"]);
}

const STATE_COLOR: Record<JobState, string> = {
  queued: "var(--muted)",
  running: "var(--status-warn)",
  done: "var(--status-good)",
  error: "var(--status-crit)",
};

export interface JobTrayOpts {
  /** Absolute href for a finished job's artifact. Omitted → no download affordance is offered. */
  artifactUrl?: (j: Job) => string;
  /** Remove a finished/failed row from view. Client-side only — the server keeps its history. */
  onDismiss?: (j: Job) => void;
}

/**
 * Render the job list into `host`, replacing its contents.
 *
 * An empty queue renders one explanatory line rather than nothing: an empty panel and a broken panel
 * look identical, and this one is reached from a badge that just said zero.
 */
export function renderJobTray(host: HTMLElement, jobs: readonly Job[], opts: JobTrayOpts = {}): void {
  host.innerHTML = "";

  if (!jobs.length) {
    const empty = document.createElement("div");
    empty.className = "meta";
    empty.style.cssText = "padding:14px;font-size:12px;line-height:1.5";
    // Names the mechanism, not just the absence — the empty-state rule from R24-EMPTY-GUIDE.
    empty.textContent = "No background jobs. Exports, compiled drawing sets and clash runs queue here, "
      + "and keep running if you close this.";
    host.appendChild(empty);
    return;
  }

  for (const j of sortJobs(jobs)) {
    const row = document.createElement("div");
    row.className = "jt-row";
    row.style.cssText = "display:flex;gap:10px;align-items:flex-start;padding:9px 12px;"
      + "border-bottom:1px solid var(--line)";

    const dot = document.createElement("span");
    dot.style.cssText = `flex:0 0 8px;height:8px;margin-top:5px;border-radius:50%;background:${STATE_COLOR[j.state] ?? "var(--muted)"}`;
    // The dot is decorative; the state is already in the text below, so it is hidden from AT rather
    // than given a redundant label.
    dot.setAttribute("aria-hidden", "true");

    const body = document.createElement("div");
    body.style.cssText = "flex:1 1 auto;min-width:0";

    const title = document.createElement("div");
    title.style.cssText = "font-size:13px";
    title.textContent = jobLabel(j.kind);          // textContent: `kind` can come from a plugin

    const sub = document.createElement("div");
    sub.className = "meta";
    sub.style.cssText = "font-size:11px;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap";
    const elapsed = jobElapsed(j);
    sub.textContent = jobSummary(j) + (elapsed ? ` · ${elapsed}` : "");
    if (j.state === "error" && j.error) sub.title = j.error;   // full text without breaking the line

    body.append(title, sub);
    row.append(dot, body);

    if (opts.artifactUrl && hasArtifact(j)) {
      const a = document.createElement("a");
      a.href = opts.artifactUrl(j);
      a.textContent = "Download";
      a.style.cssText = "font-size:11px;flex:0 0 auto";
      a.setAttribute("download", "");
      row.appendChild(a);
    }

    // Only finished rows can be dismissed. Hiding a running job would leave work in flight with no
    // way back to it, which is the exact failure the tray exists to fix.
    if (opts.onDismiss && !isActive(j)) {
      const x = document.createElement("button");
      x.type = "button";
      x.textContent = "×";
      x.setAttribute("aria-label", `Dismiss ${jobLabel(j.kind)}`);
      x.style.cssText = "flex:0 0 auto;border:0;background:transparent;color:var(--muted);cursor:pointer;font-size:14px;line-height:1";
      x.addEventListener("click", () => opts.onDismiss!(j));
      row.appendChild(x);
    }

    host.appendChild(row);
  }
}

export interface PollerOpts {
  /** Fetch the current list. Rejections are swallowed — a dropped poll is not a user-facing event. */
  fetch: () => Promise<Job[]>;
  /** Called after every successful fetch, with the list and the active count. */
  onUpdate: (jobs: Job[], active: number) => void;
  /** Called once per job that reaches `done`/`error` while the poller is watching it. */
  onSettled?: (j: Job) => void;
  /** Poll period while something is active. */
  intervalMs?: number;
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (h: unknown) => void;
}

/**
 * Poll while work is in flight; **stop completely when it is not**.
 *
 * `refresh()` reschedules itself only when the list it just received still contains an active job,
 * so an idle project costs zero requests. Anything that enqueues work calls `poke()` to restart the
 * loop — the same shape as the server's own `_WAKE` event, which nudges the worker rather than
 * letting it wait out a poll interval.
 *
 * `onSettled` fires on the transition, not on the state: polling a finished job repeatedly must not
 * re-announce it, or a tray left open all afternoon becomes a notification generator.
 */
export function createJobPoller(opts: PollerOpts) {
  const interval = opts.intervalMs ?? 2500;
  const setT = opts.setTimer ?? ((fn, ms2) => setTimeout(fn, ms2));
  const clearT = opts.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>));

  let handle: unknown = null;
  let stopped = false;
  const seenActive = new Set<string>();

  const clear = () => { if (handle !== null) { clearT(handle); handle = null; } };

  const refresh = async (): Promise<void> => {
    if (stopped) return;
    let jobs: Job[];
    try { jobs = await opts.fetch(); } catch { return schedule(); }
    if (stopped) return;

    for (const j of jobs) {
      if (isActive(j)) seenActive.add(j.id);
      else if (seenActive.delete(j.id)) opts.onSettled?.(j);
    }
    const active = activeCount(jobs);
    opts.onUpdate(jobs, active);
    if (active > 0) schedule();
  };

  function schedule(): void {
    if (stopped) return;
    clear();
    handle = setT(() => { handle = null; void refresh(); }, interval);
  }

  return {
    /** Fetch now, and keep polling for as long as something is moving. */
    poke: () => { clear(); return refresh(); },
    /** Stop for good. Safe to call twice. */
    stop: () => { stopped = true; clear(); },
    get polling() { return handle !== null; },
  };
}

// ── the header mount ────────────────────────────────────────────────────────────────────────────

export interface JobTrayMount {
  /** Re-check the queue now — call after enqueuing work, so the badge does not wait out a poll. */
  poke: () => void;
  stop: () => void;
}

/**
 * Put the tray in the header: a button with a live count, and a panel under it.
 *
 * The button **hides itself when the queue is empty**, rather than sitting there as a permanent zero.
 * The vitals strip earned its place on every screen by always carrying six real numbers; a job
 * control has nothing to say most of the time, and chrome that is usually meaningless is chrome
 * people stop reading.
 *
 * One honest limitation, stated because the alternative is a badge that lies by omission: a job
 * enqueued by *another* user does not appear until the next `poke()` or until this client enqueues
 * something itself. The server has no push channel for jobs — the SSE feed carries records, not queue
 * transitions — so a background poll would be inventing a guarantee the backend does not offer.
 */
export function mountJobTray(opts: {
  host: HTMLElement;
  fetch: () => Promise<Job[]>;
  artifactUrl?: (j: Job) => string;
  onSettled?: (j: Job) => void;
}): JobTrayMount {
  const btn = document.createElement("button");
  btn.id = "jobs-btn";
  btn.className = "tool-btn";
  btn.type = "button";
  btn.hidden = true;
  btn.setAttribute("aria-expanded", "false");

  const panel = document.createElement("div");
  panel.hidden = true;
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Background jobs");
  panel.style.cssText = "position:absolute;top:100%;right:0;z-index:200;width:min(380px,92vw);"
    + "max-height:60vh;overflow:auto;background:var(--panel);border:1px solid var(--line);"
    + "border-radius:10px;box-shadow:0 18px 48px #0009";

  const wrap = document.createElement("div");
  wrap.style.cssText = "position:relative;display:inline-flex";
  wrap.append(btn, panel);
  opts.host.appendChild(wrap);

  let jobs: Job[] = [];
  const dismissed = new Set<string>();
  const visible = () => jobs.filter((j) => !dismissed.has(j.id));

  const draw = () => {
    const shown = visible();
    const active = activeCount(shown);
    btn.hidden = shown.length === 0;
    btn.title = active
      ? `${active} background job${active === 1 ? "" : "s"} running — you can leave this open or close it`
      : "Background jobs";
    // Pure DOM: no innerHTML on a path that renders server-supplied job kinds.
    btn.textContent = active ? `⚙ ${active}` : "⚙";
    if (!panel.hidden) renderJobTray(panel, shown, {
      artifactUrl: opts.artifactUrl,
      onDismiss: (j) => { dismissed.add(j.id); draw(); },
    });
  };

  const poller = createJobPoller({
    fetch: opts.fetch,
    onUpdate: (list) => { jobs = list; draw(); },
    onSettled: opts.onSettled,
  });

  const setOpen = (open: boolean) => {
    panel.hidden = !open;
    btn.setAttribute("aria-expanded", String(open));
    if (open) { draw(); void poller.poke(); }
  };

  btn.addEventListener("click", () => setOpen(panel.hidden));
  // Close on outside click and on Escape — the same two exits the command palette gives.
  document.addEventListener("click", (e) => {
    if (!panel.hidden && !wrap.contains(e.target as Node)) setOpen(false);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !panel.hidden) setOpen(false);
  });

  return { poke: () => void poller.poke(), stop: () => poller.stop() };
}
