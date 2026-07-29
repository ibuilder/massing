import { describe, expect, it } from "vitest";

/**
 * MASS-FOR-EVERY-MODEL — opening a model must produce a **container**, not a mesh.
 *
 * Opening an IFC with no project used to fall straight through to "view only": something you can
 * orbit, and nothing else. No quantities, no estimate, no schedule, nothing to pin an RFI to, and
 * nothing kept when the tab closed — the viewer this product exists not to be. The server was
 * reachable the whole time; the code simply had nowhere to put the model and gave up.
 *
 * These are source assertions rather than a behavioural harness because `openIfc` sits behind a
 * fifteen-member deps seam and a real DOM. That is a genuine limit, so they are written to fail on
 * the ways this specific defect comes back — the branch disappearing, or the write happening without
 * asking — not merely on the words being present.
 */
async function fileIOSource(): Promise<string> {
  const mod = await import("./fileIO.ts?raw");
  const src = (mod as { default: string }).default;
  expect(typeof src, "?raw did not resolve — every assertion below would be vacuous").toBe("string");
  expect(src.length).toBeGreaterThan(1000);
  return src;
}

/** The body of `openIfc`, so the assertions cannot be satisfied by unrelated code elsewhere. */
async function openIfcBody(): Promise<string> {
  const src = await fileIOSource();
  const start = src.indexOf("async function openIfc");
  expect(start, "openIfc not found — this file was restructured").toBeGreaterThan(-1);
  const next = src.indexOf("\n  async function ", start + 10);
  return src.slice(start, next > -1 ? next : undefined);
}

describe("opening a model yields a project, not a loose mesh", () => {
  it("offers a container when the backend is reachable but no project is open", async () => {
    const body = await openIfcBody();
    expect(body, "the connected-but-project-less branch is the whole fix")
      .toMatch(/d\.connected\(\)\s*&&\s*!pid/);
    expect(body, "it must actually create one").toMatch(/createProject\(/);
  });

  it("ASKS before writing a project into the user's database", async () => {
    const body = await openIfcBody();
    const ask = body.indexOf("confirmModal");
    const write = body.indexOf("createProject(");
    expect(ask, "no confirmation before creating a project").toBeGreaterThan(-1);
    // Order matters, not just presence: creating a row unasked is the same unconsented side effect
    // the sample picker refuses to commit (see library.test.ts, "OPENS the picker rather than
    // auto-importing"). A confirm that runs after the write is decoration.
    expect(ask, "consent must precede the write").toBeLessThan(write);
  });

  it("still degrades honestly when there is genuinely nowhere to put it", async () => {
    const body = await openIfcBody();
    // Offline, or the user declined: view-only is correct. What it must not do is claim a project.
    expect(body).toMatch(/!d\.connected\(\)\s*\|\|\s*!pid/);
    expect(body, "the two cases read differently — offline is not the same as declined")
      .toMatch(/offline/i);
  });

  it("lands in the new project once it is ready, rather than leaving it orphaned", async () => {
    const src = await fileIOSource();
    // A container created and never entered is worse than none: the model publishes into a project
    // the user is not in, and the UI still shows the loose mesh.
    expect(src).toMatch(/enterProject/);
    const body = await openIfcBody();
    expect(body, "entered only when we made it — never yanking the user out of their own project")
      .toMatch(/created\s*&&|if \(created\)/);
  });
});
