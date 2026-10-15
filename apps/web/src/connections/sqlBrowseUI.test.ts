/** @vitest-environment happy-dom */
/**
 * SQL-CAP, through the real door.
 *
 * `browseConnection` is not exported, so this drives the modal the way a user does: open the
 * Data-connections admin modal, click **Browse** on a SQL connection, then run a query. Testing the
 * reading module on its own would have left the defect exactly where it was — the module is new and
 * the caption was built inline, so the only assertion that proves the wiring is one that reads the
 * DOM after a click.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { openConnectionsModal } from "./connectionsUI";
import type { ApiClient } from "../api/client";
import type { SqlQueryResponse } from "../api/connections";

const tick = () => new Promise((r) => setTimeout(r, 0));

function apiWith(q: (sql: string, limit: number) => SqlQueryResponse) {
  const connectionQuery = vi.fn(async (_id: string, sql: string, limit: number) => q(sql, limit));
  return {
    api: {
      connections: async () => ({ types: ["postgres"], connections: [
        { id: "c1", name: "App DB", type: "local", builtin: true, status: null },
      ] }),
      connectionTables: async () => ({ kind: "sql", tables: ["big"] }),
      connectionQuery,
    } as unknown as ApiClient,
    connectionQuery,
  };
}

/** Open the modal and click Browse, returning the browse card. */
async function openBrowse(api: ApiClient) {
  openConnectionsModal(api, () => "p1");
  await tick();
  const browse = [...document.querySelectorAll("button")].find((b) => b.textContent === "Browse");
  expect(browse, "the local connection offers a Browse button").toBeTruthy();
  browse!.click();
  await tick();
}

function runButton(): HTMLButtonElement {
  const b = [...document.querySelectorAll("button")].find((x) => x.textContent === "Run");
  expect(b, "the browse card has a Run button").toBeTruthy();
  return b as HTMLButtonElement;
}

function captionText(): string {
  // The count line is the one `.meta` div carrying a row count sentence.
  const metas = [...document.querySelectorAll("div.meta")].map((d) => d.textContent ?? "");
  return metas.find((t) => /row/.test(t) && /cap|whole result/.test(t)) ?? metas.join(" | ");
}

afterEach(() => { document.body.innerHTML = ""; vi.restoreAllMocks(); });

describe("SQL console — the row cap is reported", () => {
  it("says a truncated read is a sample, not a total", async () => {
    const { api } = apiWith(() => ({
      columns: ["id"], rows: Array.from({ length: 200 }, (_, i) => [i + 1]),
      row_count: 200, limit: 200, truncated: true,
    }));
    await openBrowse(api);
    const sql = document.querySelector("textarea") as HTMLTextAreaElement;
    sql.value = "SELECT * FROM big";
    runButton().click();
    await tick();
    const caption = captionText();
    expect(caption).toContain("200 rows shown");
    expect(caption).toContain("LONGER than the 200-row cap");
    expect(caption).toContain("sample, not a total");
  });

  it("does NOT call a complete read at the cap a sample", async () => {
    // The 200-row table. Same row_count and limit as the case above; only `truncated` differs, and
    // before the server reported it these two responses were byte-identical.
    const { api } = apiWith(() => ({
      columns: ["id"], rows: Array.from({ length: 200 }, (_, i) => [i + 1]),
      row_count: 200, limit: 200, truncated: false,
    }));
    await openBrowse(api);
    runButton();
    const sql = document.querySelector("textarea") as HTMLTextAreaElement;
    sql.value = "SELECT * FROM exact200";
    runButton().click();
    await tick();
    expect(captionText()).toBe("200 rows — the whole result (under the 200-row cap).");
  });

  it("asks the server for the SELECTED cap, not a hardcoded 200", async () => {
    const { api, connectionQuery } = apiWith(() => ({
      columns: ["id"], rows: [[1]], row_count: 1, limit: 1000, truncated: false,
    }));
    await openBrowse(api);
    const sel = [...document.querySelectorAll("select")]
      .find((s) => [...s.options].some((o) => o.value === "1000"));
    expect(sel, "the browse card offers a row-cap selector").toBeTruthy();
    sel!.value = "1000";
    const sql = document.querySelector("textarea") as HTMLTextAreaElement;
    sql.value = "SELECT * FROM big";
    runButton().click();
    await tick();
    expect(connectionQuery).toHaveBeenCalledWith("c1", "SELECT * FROM big", 1000);
  });

  it("renders a refusal as a refusal, never as a table that matched nothing", async () => {
    const { api } = apiWith(() => ({ error: "only SELECT / WITH queries are allowed" }));
    await openBrowse(api);
    const sql = document.querySelector("textarea") as HTMLTextAreaElement;
    sql.value = "DELETE FROM big";
    runButton().click();
    await tick();
    expect(document.body.textContent).toContain("Query not run: only SELECT / WITH queries are allowed");
    expect(document.body.textContent).toContain("says nothing about the table");
    expect(document.querySelectorAll("table.portal-table").length).toBe(0);
  });

  it("keeps an empty result distinct from a failed one", async () => {
    const { api } = apiWith(() => ({ columns: ["id"], rows: [], row_count: 0, limit: 200, truncated: false }));
    await openBrowse(api);
    const sql = document.querySelector("textarea") as HTMLTextAreaElement;
    sql.value = "SELECT * FROM big WHERE 0";
    runButton().click();
    await tick();
    expect(document.body.textContent).toContain("matched no rows");
    expect(document.body.textContent).not.toContain("Query not run");
    // the header still shows what the query would have returned
    expect(document.querySelectorAll("table.portal-table th").length).toBe(1);
  });

  it("a table-preview click runs the unbounded select and still reports the cap", async () => {
    // `SELECT * FROM "<table>"` is the default path through this screen and the query most likely
    // to exceed the cap — the case the bare count hid.
    const { api, connectionQuery } = apiWith(() => ({
      columns: ["id"], rows: Array.from({ length: 200 }, (_, i) => [i + 1]),
      row_count: 200, limit: 200, truncated: true,
    }));
    await openBrowse(api);
    const tableBtn = [...document.querySelectorAll("button")].find((b) => b.textContent === "big");
    expect(tableBtn, "the table list offers a preview button").toBeTruthy();
    tableBtn!.click();
    await tick();
    expect(connectionQuery).toHaveBeenCalledWith("c1", 'SELECT * FROM "big"', 200);
    expect(captionText()).toContain("sample, not a total");
  });
});
