/** DOM construction, geometry and font helpers. */
import { Info, ViewNode } from "./types";

export function anchorPoint(anchor: string = "center") {
  return {
    x: ["w", "nw", "sw"].includes(anchor)
      ? 0
      : ["e", "ne", "se"].includes(anchor)
        ? 1
        : 0.5,
    y: ["n", "nw", "ne"].includes(anchor)
      ? 0
      : ["s", "sw", "se"].includes(anchor)
        ? 1
        : 0.5,
  };
}

export function el(tag: string, cls = "", text = "") {
  const e = document.createElement(tag);
  e.className = cls;
  e.textContent = text;
  return e;
}

export function paintFont(element: HTMLElement | SVGElement, f: Info = {}) {
  if (f.family) element.style.fontFamily = f.family;
  if (f.pixels) element.style.fontSize = f.pixels + "px";
  element.style.fontWeight = f.weight === "bold" ? "700" : "400";
  element.style.fontStyle = f.slant === "italic" ? "italic" : "normal";
}

export function place(e: HTMLElement, d: ViewNode) {
  e.style.left = d.x + "px";
  e.style.top = d.y + "px";
  e.style.width = Math.max(1, d.width) + "px";
  e.style.height = Math.max(1, d.height) + "px";
  paintFont(e, d.style.font);
  if (d.style.foreground) e.style.color = d.style.foreground;
  if (d.style.background && d.kind !== "TEntry" && d.kind !== "TCombobox")
    e.style.backgroundColor = d.style.background;
  if (["groove", "ridge", "sunken", "raised", "solid"].includes(d.style.relief))
    e.style.border = "1px solid #a9becd";
  e.dataset.kind = d.kind;
  e.dataset.widget = d.id;
  e.title = d.tooltip || "";
}
