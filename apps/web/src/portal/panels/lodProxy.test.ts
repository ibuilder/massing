import { describe, it, expect } from "vitest";
import { proxyOffer, proxyConfirm, proxySummary } from "./lodProxy";

describe("proxyOffer — the button is absent with a reason, not offered-and-refused", () => {
  it("offers when there is a real saving", () => {
    expect(proxyOffer({ status: "ok", proxied: ["IfcWall"], pct_saved: 47 }).can).toBe(true);
  });

  it("declines with the server's OWN reason when the plan carries one", () => {
    const g = proxyOffer({ status: "skip", reason: "no meshable geometry" });
    expect(g.can).toBe(false);
    expect(g.why).toBe("no meshable geometry");
  });

  it("declines when nothing is worth proxying", () => {
    expect(proxyOffer({ status: "ok", proxied: [], pct_saved: 0 }).why).toContain("nothing in this model");
  });

  it("declines a ZERO or negative saving — a proxy that saves nothing costs more than it returns", () => {
    // The server would refuse this anyway. Offering the button first is the shape this panel avoids.
    expect(proxyOffer({ status: "ok", proxied: ["IfcWall"], pct_saved: 0 }).can).toBe(false);
    expect(proxyOffer({ status: "ok", proxied: ["IfcWall"], pct_saved: null }).can).toBe(false);
  });
});

describe("proxyConfirm", () => {
  it("says the model is NOT changed, and that the boxes are stand-ins", () => {
    // The server stamps every box with an AEC_LOD pset for exactly this reason: "a stand-in mistaken
    // for real geometry is worse than no stand-in". The confirmation has to say so too, because the
    // person clicking is the one who might later measure it.
    const c = proxyConfirm({ status: "ok", proxied: ["IfcWall", "IfcSlab"], pct_saved: 47 });
    expect(c).toContain("2 classes");
    expect(c).toContain("47%");
    expect(c).toContain("SEPARATE file");
    expect(c).toContain("must not be measured");
  });
  it("singularises one class", () => {
    expect(proxyConfirm({ status: "ok", proxied: ["IfcWall"], pct_saved: 5 })).toContain("1 class,");
  });
});

describe("proxySummary", () => {
  it("reports a REFUSAL as a refusal, with the reason and what was not written", () => {
    // `stored: false` is a 200 from the server. Rendering it as success is precisely how "a
    // successful export of nothing gets believed" — the server's own words.
    const s = proxySummary({ written: false, stored: false, reason: "no storeys carry geometry" });
    expect(s).toContain("No proxy was stored");
    expect(s).toContain("no storeys carry geometry");
    expect(s).toContain("Nothing was written");
  });

  it("reports a success with both counts and what still has to happen", () => {
    const s = proxySummary({ written: true, stored: true, elements_replaced: 812, storeys_proxied: 6 });
    expect(s).toContain("812 elements replaced across 6 storeys");
    expect(s).toContain("needs converting");
  });

  it("falls back without inventing a number when the counts are absent", () => {
    expect(proxySummary({ written: true, stored: true })).toContain("0 elements replaced across 0 storeys");
  });
});
