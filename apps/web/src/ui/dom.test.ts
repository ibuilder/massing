import { describe, expect, it } from "vitest";
import { clear, el, frag, readForm } from "./dom";

describe("el", () => {
  it("sets class, text, and children", () => {
    const node = el("div", { class: "row" }, [el("span", { text: "hi" })]);
    expect(node.tagName).toBe("DIV");
    expect(node.className).toBe("row");
    expect(node.querySelector("span")?.textContent).toBe("hi");
  });

  it("assigns unknown props as element properties (onclick, type, disabled)", () => {
    let clicked = 0;
    const btn = el("button", { type: "button", onclick: () => clicked++ });
    expect(btn.type).toBe("button");
    btn.click();
    expect(clicked).toBe(1);
    // disabled is assigned as a property too (a disabled button won't dispatch click — browser rule)
    expect(el("button", { disabled: true }).disabled).toBe(true);
  });

  it("supports string and object styles + dataset", () => {
    const a = el("div", { style: "width:100%" });
    expect(a.style.width).toBe("100%");
    const b = el("div", { style: { color: "red" }, dataset: { key: "k1" } });
    expect(b.style.color).toBe("red");
    expect(b.dataset.key).toBe("k1");
  });

  it("skips null/undefined props", () => {
    const node = el("div", { class: undefined, title: null as unknown as string });
    expect(node.className).toBe("");
    expect(node.getAttribute("title")).toBeNull();
  });
});

describe("frag + clear", () => {
  it("frag batches nodes and strings", () => {
    const f = frag(el("i"), "x", el("b"));
    expect(f.childNodes.length).toBe(3);
  });
  it("clear removes all children", () => {
    const box = el("div", {}, [el("span"), el("span")]);
    expect(box.children.length).toBe(2);
    clear(box);
    expect(box.children.length).toBe(0);
  });
});

describe("readForm", () => {
  it("reads named controls into a typed object; checkbox -> on/empty", () => {
    const form = el("form", {}, [
      el("input", { name: "title", value: "Roof" }),
      el("input", { name: "done", type: "checkbox", checked: true }),
      el("input", { name: "note", value: "" }),
    ]);
    const v = readForm<{ title: string; done: string; note: string }>(form);
    expect(v.title).toBe("Roof");
    expect(v.done).toBe("on");
    expect(v.note).toBe("");
  });
});
