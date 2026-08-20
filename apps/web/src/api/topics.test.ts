import { describe, expect, it } from "vitest";

import { ApiClient } from "./client";

const api = new ApiClient("http://localhost:0");

describe("the topics client", () => {
  it("exposes create, viewpoints, board, timeline, and comments", () => {
    for (const k of ["createTopic", "viewpoints", "addViewpoint", "topicsBoard",
                     "topicTimeline", "topicComments", "addTopicComment"]) {
      expect(typeof (api as unknown as Record<string, unknown>)[k], k).toBe("function");
    }
  });

  it("arrived as a mixin, so client.ts did not grow", async () => {
    const mod = await import("./topics");
    expect(typeof mod.withTopics).toBe("function");
  });
});
