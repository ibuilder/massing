import { describe, expect, it, vi } from "vitest";
import { EventBus } from "./events.js";

interface TestEvents {
  ping: { n: number };
  other: string;
}

describe("EventBus", () => {
  it("delivers to every subscriber", () => {
    const bus = new EventBus<TestEvents>();
    const a = vi.fn();
    const b = vi.fn();
    bus.on("ping", a);
    bus.on("ping", b);

    const report = bus.emit("ping", { n: 1 });

    expect(a).toHaveBeenCalledWith({ n: 1 });
    expect(b).toHaveBeenCalledWith({ n: 1 });
    expect(report.delivered).toBe(2);
    expect(report.errors).toHaveLength(0);
  });

  it("stops delivering once disposed", () => {
    const bus = new EventBus<TestEvents>();
    const handler = vi.fn();
    bus.on("ping", handler).dispose();

    bus.emit("ping", { n: 1 });
    expect(handler).not.toHaveBeenCalled();
  });

  it("delivers a `once` subscription exactly once", () => {
    const bus = new EventBus<TestEvents>();
    const handler = vi.fn();
    bus.once("ping", handler);

    bus.emit("ping", { n: 1 });
    bus.emit("ping", { n: 2 });

    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("isolates a throwing subscriber from the others and from the emitter", () => {
    const bus = new EventBus<TestEvents>();
    const after = vi.fn();
    bus.on("ping", () => {
      throw new Error("plugin blew up");
    });
    bus.on("ping", after);

    // The whole no-plugin-can-crash-the-host guarantee rests on this not propagating.
    const report = bus.emit("ping", { n: 1 });

    expect(after).toHaveBeenCalledOnce();
    expect(report.errors).toHaveLength(1);
    expect(report.errors[0]?.message).toContain("plugin blew up");
    expect(report.delivered).toBe(1);
  });

  it("does not deliver to a handler subscribed during the same emit", () => {
    const bus = new EventBus<TestEvents>();
    const late = vi.fn();
    bus.on("ping", () => {
      bus.on("ping", late);
    });

    bus.emit("ping", { n: 1 });

    // Without a snapshot this either delivers to `late` or skips an existing handler, depending on
    // iteration order — both are bugs that only show up under load.
    expect(late).not.toHaveBeenCalled();
    bus.emit("ping", { n: 2 });
    expect(late).toHaveBeenCalledOnce();
  });

  it("still delivers to remaining handlers when one unsubscribes mid-emit", () => {
    const bus = new EventBus<TestEvents>();
    const second = vi.fn();
    const first = bus.on("ping", () => first.dispose());
    bus.on("ping", second);

    bus.emit("ping", { n: 1 });
    expect(second).toHaveBeenCalledOnce();
  });

  it("routes every topic to observers without letting them affect delivery", () => {
    const bus = new EventBus<TestEvents>();
    const seen: string[] = [];
    bus.observe((type) => {
      seen.push(type);
      throw new Error("observer failure is not the emitter's problem");
    });
    const handler = vi.fn();
    bus.on("ping", handler);

    const report = bus.emit("ping", { n: 1 });

    expect(seen).toEqual(["ping"]);
    expect(handler).toHaveBeenCalledOnce();
    expect(report.errors).toHaveLength(0);
  });

  it("tracks listener counts and clears them", () => {
    const bus = new EventBus<TestEvents>();
    bus.on("ping", () => {});
    expect(bus.listenerCount("ping")).toBe(1);

    bus.clear();
    expect(bus.listenerCount("ping")).toBe(0);
  });
});
