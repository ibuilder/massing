import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  FIELD_MODE_KEY, applyFieldMode, honourFieldQuery, mountFieldChrome, readFieldMode,
  setFieldMode, shouldOpenCaptureHome, syncStripText,
} from "./fieldMode";

beforeEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.fieldMode;
  document.getElementById("field-mode-toggle")?.remove();
  document.getElementById("field-sync-strip")?.remove();
});

afterEach(() => {
  document.getElementById("field-mode-toggle")?.remove();
  document.getElementById("field-sync-strip")?.remove();
});

describe("field mode flag", () => {
  it("is off until stored as 1", () => {
    expect(readFieldMode()).toBe(false);
    setFieldMode(true);
    expect(readFieldMode()).toBe(true);
    expect(document.documentElement.dataset.fieldMode).toBe("1");
    setFieldMode(false);
    expect(document.documentElement.dataset.fieldMode).toBe("0");
  });

  it("honours ?field=1 / ?field=0 and ignores an unrelated query", () => {
    expect(honourFieldQuery("?capture=1")).toBeNull();
    expect(localStorage.getItem(FIELD_MODE_KEY)).toBeNull();
    expect(honourFieldQuery("?field=1")).toBe(true);
    expect(readFieldMode()).toBe(true);
    expect(honourFieldQuery("?field=0")).toBe(false);
    expect(readFieldMode()).toBe(false);
  });

  it("applyFieldMode writes the dataset even when storage is empty", () => {
    applyFieldMode();
    expect(document.documentElement.dataset.fieldMode).toBe("0");
  });
});

describe("sync strip copy", () => {
  it("empty online is a sentence, not a blank", () => {
    expect(syncStripText(0, true)).toBe("Queue empty — all caught up");
  });

  it("names Offline when the radio is down, including an empty queue", () => {
    expect(syncStripText(0, false)).toBe("Offline · queue empty");
    expect(syncStripText(3, false)).toBe("Offline · 3 waiting to sync");
  });

  it("counts waiting work when online", () => {
    expect(syncStripText(2, true)).toBe("2 waiting to sync");
  });
});

describe("field chrome", () => {
  it("toggle turns the mode on and the strip becomes visible with queue copy", () => {
    const onOpenQueue = vi.fn();
    mountFieldChrome({ queueCount: () => 2, onOpenQueue });
    const toggle = document.getElementById("field-mode-toggle") as HTMLButtonElement;
    const strip = document.getElementById("field-sync-strip") as HTMLButtonElement;
    expect(toggle.textContent).toBe("Field");
    expect(strip.hidden).toBe(true);

    toggle.click();
    expect(readFieldMode()).toBe(true);
    expect(document.documentElement.dataset.fieldMode).toBe("1");
    expect(toggle.textContent).toBe("Office");
    expect(strip.hidden).toBe(false);
    expect(strip.textContent).toBe("2 waiting to sync");
    expect(strip.getAttribute("aria-live")).toBe("polite");

    strip.click();
    expect(onOpenQueue).toHaveBeenCalledTimes(1);
  });

  it("does not duplicate chrome on a second mount", () => {
    mountFieldChrome({ queueCount: () => 0, onOpenQueue: () => undefined });
    mountFieldChrome({ queueCount: () => 0, onOpenQueue: () => undefined });
    expect(document.querySelectorAll("#field-mode-toggle")).toHaveLength(1);
    expect(document.querySelectorAll("#field-sync-strip")).toHaveLength(1);
  });
});

describe("capture-first landing", () => {
  it("needs both field mode and a project — otherwise the sheet would only toast", () => {
    expect(shouldOpenCaptureHome(true, "p1")).toBe(true);
    expect(shouldOpenCaptureHome(true, null)).toBe(false);
    expect(shouldOpenCaptureHome(false, "p1")).toBe(false);
  });

  it("notifies when the mode flips so capture can become the landing", () => {
    const onFieldModeChange = vi.fn();
    mountFieldChrome({ queueCount: () => 0, onOpenQueue: () => undefined, onFieldModeChange });
    (document.getElementById("field-mode-toggle") as HTMLButtonElement).click();
    expect(onFieldModeChange).toHaveBeenCalledWith(true);
  });
});

describe("fieldMode.css stays off the accent contract", () => {
  const css = readFileSync(join(process.cwd(), "src", "field", "fieldMode.css"), "utf8");

  it("does not paint text or background with --accent (that list lives in style.css)", () => {
    expect(css).not.toMatch(/(?:color|background(?:-color)?)\s*:[^;]*var\(--accent\)/);
  });

  it("asks for 56 px targets on field chrome, and those rules beat the FAB's inline 52 px", () => {
    expect(css).toMatch(/#field-fab[\s\S]*width:\s*56px\s*!important/);
    expect(css).toMatch(/#field-fab[\s\S]*bottom:\s*72px\s*!important/);
    expect(css).toMatch(/min-height:\s*56px/);
  });

  it("hides the seven-room tablist in field mode so capture is the home, not a spine overlay", () => {
    expect(css).toMatch(/html\[data-field-mode="1"\]\s+#workspaces\s*\{[^}]*display:\s*none\s*!important/);
  });
});
