import { describe, expect, it } from "vitest";

import { liveDisplay } from "./liveState";

describe("liveDisplay — one mapping for every live-stream indicator", () => {
  it("only a refusal is actionable", () => {
    expect(liveDisplay("connected").retryable).toBe(false);
    expect(liveDisplay("connecting").retryable).toBe(false);
    expect(liveDisplay("reconnecting").retryable).toBe(false);
    expect(liveDisplay("refused", "no access").retryable).toBe(true);
  });

  it("a refusal is the only crit tone, and connecting is not green", () => {
    expect(liveDisplay("refused", "no access").tone).toBe("--status-crit");
    // The defect slice ⑦ fixed was a GREEN dot reading "live" over a dead stream, so the state
    // before the first frame must not borrow that colour.
    expect(liveDisplay("connecting").tone).toBe("--status-warn");
    expect(liveDisplay("connected").tone).toBe("--status-good");
  });

  it("THE POINT: an EMPTY reason still reads as a refusal", () => {
    // The sixth and seventh corrections of this on this branch were both `||` or truthiness checks
    // on a value whose type is `string | undefined`. An empty reason means the server refused and
    // did not say why — not that it did not refuse.
    for (const why of ["", "   "]) {
      const d = liveDisplay("refused", why);
      expect(d.retryable, `empty reason ${JSON.stringify(why)} is still a refusal`).toBe(true);
      expect(d.tone).toBe("--status-crit");
      expect(d.text).toContain("refused by the server");
      expect(d.text, "and never renders as a dangling dash").not.toMatch(/—\s*\./);
    }
  });

  it("an ABSENT reason reads the same way as an empty one", () => {
    expect(liveDisplay("refused").text).toContain("refused by the server");
  });

  it("a given reason is carried verbatim, not summarised away", () => {
    expect(liveDisplay("refused", "you were removed from this project").text)
      .toBe("Live updates stopped — you were removed from this project.");
  });

  it("the subject names what stops, because each screen loses something different", () => {
    expect(liveDisplay("refused", "gone", "Live markup").text).toMatch(/^Live markup stopped/);
    expect(liveDisplay("refused", "gone", "Live model updates").text)
      .toMatch(/^Live model updates stopped/);
  });

  it("the text is plain prose — a server reason must never need escaping here", () => {
    // It goes into a text node at every call site; this pins the contract so a future caller using
    // innerHTML is a change to THIS file's promise rather than a quiet XSS.
    const d = liveDisplay("refused", "<img src=x onerror=alert(1)>");
    expect(d.text).toContain("<img src=x onerror=alert(1)>");
  });
});
