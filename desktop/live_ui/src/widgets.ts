/** Widget creation and incremental updates; delegates tables and plots. */
import { pointer, send } from "./bridge";
import { canvas } from "./canvas";
import {
  closeChoices,
  editableCombo,
  openChoices,
  paintChoices,
} from "./combobox";
import { anchorPoint, el, place } from "./dom";
import { assets, data, nodes, runtime, savedViews } from "./state";
import { renderTree } from "./tree";
import { ViewNode } from "./types";

export const frameKinds = new Set([
  "Tk",
  "Toplevel",
  "Frame",
  "TFrame",
  "Labelframe",
  "TLabelframe",
  "Panedwindow",
  "TPanedwindow",
  "Notebook",
  "TNotebook",
]);

export function create(d: ViewNode) {
  let node: HTMLElement;
  if (frameKinds.has(d.kind))
    node = el(
      "div",
      "widget frame" +
        (d.kind.toLowerCase().includes("labelframe") ? " group" : ""),
    );
  else if (
    ["Button", "TButton", "Menubutton", "TMenubutton"].includes(d.kind)
  ) {
    node = el("button", "widget");
    node.onclick = () => {
      const current = data.get(d.id)!;
      if (current.kind.includes("Menubutton")) {
        const r = node.getBoundingClientRect();
        void send({ action: "menu", id: d.id, x: r.left, y: r.bottom });
      } else void send({ action: "invoke", id: d.id });
    };
  } else if (
    ["Checkbutton", "TCheckbutton", "Radiobutton", "TRadiobutton"].includes(
      d.kind,
    )
  ) {
    node = el("label", "widget check");
    const input = document.createElement("input");
    input.type = d.kind.includes("Radio") ? "radio" : "checkbox";
    input.onchange = () => void send({ action: "invoke", id: d.id });
    node.append(input, el("span"));
  } else if (
    ["Entry", "TEntry", "Spinbox", "TSpinbox", "TCombobox"].includes(d.kind)
  ) {
    node = document.createElement(
      d.kind === "TCombobox" && d.readonly ? "select" : "input",
    );
    node.className = "widget";
    const input = node as HTMLInputElement;
    input.oninput = () => {
      if (node.tagName !== "SELECT")
        void send({
          action: "value",
          id: d.id,
          value: input.value,
          selection: false,
        });
      if (runtime.choicesID === d.id) paintChoices(d.id, input.value);
    };
    input.onchange = () =>
      void send({
        action: "value",
        id: d.id,
        value: input.value,
        selection: node.tagName === "SELECT",
      });
    input.onfocus = () => {
      void pointer(d.id, "<FocusIn>");
      if (d.kind === "TCombobox") void send({ action: "post", id: d.id });
    };
    input.onblur = () => void pointer(d.id, "<FocusOut>");
    input.onkeydown = (e) => {
      if (
        d.kind === "TCombobox" &&
        !data.get(d.id)?.readonly &&
        e.key === "ArrowDown"
      ) {
        e.preventDefault();
        void openChoices(d.id, true);
        return;
      }
      if (e.key === "Escape") closeChoices();
      if (e.key === "Enter") void pointer(d.id, "<Return>");
      if (e.key === "Escape") void pointer(d.id, "<Escape>");
    };
  } else if (d.kind === "Text") {
    node = el("textarea", "widget");
    const input = node as HTMLTextAreaElement;
    input.oninput = () =>
      void send({ action: "value", id: d.id, value: input.value });
    input.onblur = () => void pointer(d.id, "<FocusOut>");
    input.onfocus = () => void pointer(d.id, "<FocusIn>");
  } else if (["Treeview", "Listbox"].includes(d.kind))
    node = el("div", "widget tree");
  else if (d.kind === "Canvas") {
    node = el("div", "widget canvas");
    node.onpointerdown = (e) => {
      if ((e.target as Element).closest(".widget") !== node) return;
      e.preventDefault();
      node.setPointerCapture(e.pointerId);
      void pointer(d.id, e.button === 2 ? "<Button-3>" : "<Button-1>", e);
    };
    node.onpointerup = (e) => {
      if (node.hasPointerCapture(e.pointerId)) {
        node.releasePointerCapture(e.pointerId);
        void pointer(d.id, "<ButtonRelease-1>", e);
      }
    };
    node.onpointermove = (e) => {
      if ((e.target as Element).closest(".widget") !== node) return;
      if (e.buttons === 1) void pointer(d.id, "<B1-Motion>", e);
      else if (performance.now() - Number(node.dataset.motion || 0) > 90) {
        node.dataset.motion = String(performance.now());
        void pointer(d.id, "<Motion>", e);
      }
    };
    node.onwheel = (e) => {
      e.preventDefault();
      void pointer(d.id, "<MouseWheel>", e);
    };
    node.oncontextmenu = (e) => e.preventDefault();
  } else if (["Scrollbar", "TScrollbar", "Scale", "TScale"].includes(d.kind)) {
    node = document.createElement("input");
    const range = node as HTMLInputElement;
    range.type = "range";
    range.className = "widget scrollbar";
    range.min = "0";
    range.max = "1";
    range.step = ".001";
    range.oninput = () =>
      void send(
        d.kind.includes("Scrollbar")
          ? { action: "scroll", id: d.id, position: Number(range.value) }
          : { action: "value", id: d.id, value: Number(range.value) },
      );
  } else if (["Progressbar", "TProgressbar"].includes(d.kind)) {
    node = el("div", "widget progress");
    node.append(el("div"));
  } else if (["Separator", "TSeparator"].includes(d.kind)) {
    node = el("div", "widget");
    node.style.backgroundColor = "#bdceda";
  } else if (["Label", "TLabel", "Message"].includes(d.kind)) {
    node = el("div", "widget label");
    node.onmousedown = (e) => {
      if (e.button === 0) {
        runtime.pressedLabel = d.id;
        void pointer(d.id, "<Button-1>", e);
      }
    };
    node.onmousemove = (e) => {
      if (e.buttons === 1) void pointer(d.id, "<B1-Motion>", e);
    };
    node.ondblclick = (e) => void pointer(d.id, "<Double-Button-1>", e);
    node.oncontextmenu = (e) => {
      e.preventDefault();
      void pointer(d.id, "<Button-3>", e);
    };
  } else {
    node = el("div", "widget unsupported", "Unsupported control: " + d.kind);
  }
  node.addEventListener(
    "mouseenter",
    (e) => void pointer(d.id, "<Enter>", e as MouseEvent),
  );
  node.addEventListener(
    "mouseleave",
    (e) => void pointer(d.id, "<Leave>", e as MouseEvent),
  );
  return node;
}

export function textImage(node: HTMLElement, d: ViewNode) {
  const key = d.text + "|" + d.image + "|" + d.compound;
  if (node.dataset.content === key) return;
  node.dataset.content = key;
  node.replaceChildren();
  const hasImage = !!(d.image && assets[d.image]);
  if (hasImage) {
    const image = document.createElement("img");
    image.src = assets[d.image];
    image.alt = "";
    node.append(image);
  }
  const text =
    d.kind === "TLabel" &&
    d.text === "No Tecan, manual, or pushed transfer rows available."
      ? "No transfers to display."
      : d.text;
  if (text && (!hasImage || d.compound !== "none"))
    node.append(el("span", "", text));
  node.style.flexDirection =
    d.compound === "top"
      ? "column"
      : d.compound === "bottom"
        ? "column-reverse"
        : d.compound === "right"
          ? "row-reverse"
          : "row";
  if (node instanceof HTMLButtonElement) {
    node.setAttribute("aria-label", d.text);
    if (hasImage) node.title = d.tooltip || d.text;
  }
}

export function renderNode(
  d: ViewNode,
  parent: HTMLElement,
  seen: Set<string>,
) {
  seen.add(d.id);
  data.set(d.id, d);
  let node = nodes.get(d.id);
  if (
    node &&
    d.kind === "TCombobox" &&
    (node.tagName === "SELECT") !== !!d.readonly
  ) {
    node.remove();
    nodes.delete(d.id);
    node = undefined;
  }
  if (!node) {
    node = create(d);
    nodes.set(d.id, node);
  }
  if (node === parent || node.contains(parent))
    throw new Error(`Layout cycle ${d.id} into ${parent.dataset.widget}`);
  if (node.parentElement !== parent) {
    parent.append(node);
    const view = savedViews.get(d.id);
    if (view)
      requestAnimationFrame(() => {
        node!.scrollLeft = view.x;
        node!.scrollTop = view.y;
      });
  }
  place(node, d);
  node.classList.toggle("map-emphasis", !!d.emphasized);
  if (
    node instanceof HTMLButtonElement ||
    node instanceof HTMLInputElement ||
    node instanceof HTMLSelectElement ||
    node instanceof HTMLTextAreaElement
  )
    node.disabled = !!d.disabled;
  if (
    [
      "Label",
      "TLabel",
      "Message",
      "Button",
      "TButton",
      "Menubutton",
      "TMenubutton",
    ].includes(d.kind)
  ) {
    textImage(node, d);
    node.style.justifyContent =
      anchorPoint(d.style.anchor).x === 0
        ? "flex-start"
        : anchorPoint(d.style.anchor).x === 1
          ? "flex-end"
          : "center";
    node.style.textAlign = d.style.justify || "left";
    if (node.classList.contains("label")) {
      node.style.whiteSpace = Number(d.style.wrap) > 0 ? "pre-wrap" : "pre";
      const span = node.querySelector("span");
      if (span) {
        span.style.overflow = "hidden";
        span.style.textOverflow = "ellipsis";
      }
      if (!node.title) node.title = d.text;
    }
  }
  if (
    ["Checkbutton", "TCheckbutton", "Radiobutton", "TRadiobutton"].includes(
      d.kind,
    )
  ) {
    const input = node.querySelector("input")!;
    input.checked = !!d.selected;
    input.disabled = !!d.disabled;
    const span = node.querySelector("span")!;
    const icon = !!(d.image && assets[d.image]);
    node.classList.toggle("icon-toggle", icon);
    span.textContent = icon && d.compound === "none" ? "" : d.text;
    let img = node.querySelector("img");
    if (icon) {
      if (!img) {
        img = document.createElement("img");
        img.alt = "";
        node.insertBefore(img, span);
      }
      img.src = assets[d.image];
      node.title = d.tooltip || d.text;
      input.setAttribute("aria-label", d.text);
      node.classList.toggle("selected", !!d.selected);
    } else img?.remove();
  }
  if (
    node instanceof HTMLInputElement ||
    node instanceof HTMLTextAreaElement ||
    node instanceof HTMLSelectElement
  ) {
    if (d.kind === "TCombobox" && node instanceof HTMLSelectElement) {
      const values = JSON.stringify([
        d.values,
        d.values.includes(d.value) ? "" : d.value,
      ]);
      if (node.dataset.options !== values) {
        node.dataset.options = values;
        node.replaceChildren();
        for (const v of d.values.includes(d.value) || !d.value
          ? d.values
          : [d.value, ...d.values]) {
          const option = document.createElement("option");
          option.value = String(v);
          option.textContent = String(v);
          node.append(option);
        }
        node.value = String(d.value ?? "");
      }
    }
    if (d.kind === "TCombobox" && node instanceof HTMLInputElement)
      editableCombo(node, d);
    if (d.kind.includes("Spinbox") && node instanceof HTMLInputElement) {
      node.type = "number";
      node.min = String(d.minimum);
      node.max = String(d.maximum);
      node.step = String(d.increment || 1);
    }
    if (
      (document.activeElement !== node ||
        (node instanceof HTMLTextAreaElement && d.disabled)) &&
      d.value !== undefined &&
      node.value !== String(d.value)
    ) {
      const x = node.scrollLeft,
        y = node.scrollTop,
        follow =
          node instanceof HTMLTextAreaElement &&
          d.disabled &&
          y + node.clientHeight >= node.scrollHeight - 5;
      node.value = String(d.value);
      node.scrollLeft = x;
      node.scrollTop = follow ? node.scrollHeight : y;
    }
    if (
      node instanceof HTMLInputElement &&
      ["Entry", "TEntry"].includes(d.kind)
    ) {
      node.readOnly = !!d.readonly;
      node.type = d.show ? "password" : "text";
    }
    if (node instanceof HTMLTextAreaElement) {
      node.wrap = d.wrap === "none" ? "off" : "soft";
      node.readOnly = !!d.disabled;
      node.disabled = false;
    }
  }
  if (d.kind.toLowerCase().includes("notebook")) {
    let tabs = node.querySelector(":scope > .tabs");
    if (!tabs) {
      tabs = el("div", "tabs");
      node.prepend(tabs);
    }
    const hash = JSON.stringify([d.tabs, d.selected]);
    if ((tabs as HTMLElement).dataset.hash !== hash) {
      (tabs as HTMLElement).dataset.hash = hash;
      tabs.replaceChildren();
      for (const t of d.tabs) {
        if (t.state === "hidden") continue;
        const b = document.createElement("button");
        b.textContent = t.text;
        b.setAttribute("aria-label", t.label || t.text);
        if (t.image && assets[t.image]) {
          const icon = document.createElement("img");
          icon.src = assets[t.image];
          b.prepend(icon);
          b.classList.add("with-icon");
        }
        b.classList.toggle("active", t.id === d.selected);
        b.disabled = t.state === "disabled";
        b.onclick = (e) => {
          const r = b.getBoundingClientRect();
          void send({
            action: "tab",
            id: d.id,
            tab: t.id,
            rx: e.isTrusted ? (e.clientX - r.left) / r.width : 0.5,
            ry: e.isTrusted ? (e.clientY - r.top) / r.height : 0.5,
          });
        };
        tabs.append(b);
      }
    }
    (tabs as HTMLElement).style.height =
      Math.max(24, d.children[0]?.y || 30) + "px";
  }
  if (d.kind.toLowerCase().includes("labelframe")) {
    let title = node.querySelector(":scope > .group-title");
    if (d.labelwidget) {
      title?.remove();
    } else {
      if (!title) {
        title = el("span", "group-title");
        node.prepend(title);
      }
      title.textContent = d.text;
    }
  }
  if (d.kind === "Treeview" || d.kind === "Listbox") renderTree(node, d);
  if (d.kind === "Canvas") canvas(node, d);
  if (d.kind.includes("Scrollbar")) {
    const range = node as HTMLInputElement;
    range.classList.toggle("vertical", d.orient === "vertical");
    range.value = String(d.range?.[0] || 0);
    range.max = String(
      Math.max(0.001, 1 - (d.range?.[1] || 1) + (d.range?.[0] || 0)),
    );
    range.disabled = d.range?.[0] === 0 && d.range?.[1] === 1;
  }
  if (d.kind.includes("Scale")) {
    const range = node as HTMLInputElement;
    range.min = String(d.from);
    range.max = String(d.to);
    range.classList.toggle("vertical", d.orient === "vertical");
  }
  if (d.kind.includes("Progressbar")) {
    node.classList.toggle("indeterminate", d.mode === "indeterminate");
    (node.firstChild as HTMLElement).style.width =
      Math.min(100, (100 * d.value) / d.maximum) + "%";
  }
  if (d.kind.toLowerCase().includes("panedwindow")) {
    const panes = d.children.slice(0, -1);
    for (const h of node.querySelectorAll<HTMLElement>(":scope > .sash"))
      if (Number(h.dataset.index) >= panes.length) h.remove();
    panes.forEach((child, index) => {
      let h = node!.querySelector<HTMLElement>(
        `:scope > .sash[data-index="${index}"]`,
      );
      if (!h) {
        h = el("div", "sash");
        h.dataset.index = String(index);
        h.title = "Drag to resize panels";
        node!.append(h);
      }
      const handle = h,
        vertical = d.orient === "vertical";
      handle.style.cssText = `position:absolute;z-index:5;cursor:${vertical ? "row-resize" : "col-resize"};left:${vertical ? "0px" : child.x + child.width - 2 + "px"};top:${vertical ? child.y + child.height - 2 + "px" : "0px"};width:${vertical ? "100%" : "7px"};height:${vertical ? "7px" : "100%"};`;
      handle.onpointerdown = (e) => {
        handle.setPointerCapture(e.pointerId);
        handle.classList.add("dragging");
        let last = 0;
        handle.onpointermove = (m) => {
          if (!m.buttons || performance.now() - last < 40) return;
          last = performance.now();
          const r = node!.getBoundingClientRect();
          void send({
            action: "sash",
            id: d.id,
            index,
            position: vertical ? m.clientY - r.top : m.clientX - r.left,
          });
        };
        handle.onpointerup = (m) => {
          handle.releasePointerCapture(m.pointerId);
          handle.classList.remove("dragging");
          const r = node!.getBoundingClientRect();
          void send({
            action: "sash",
            id: d.id,
            index,
            position: vertical ? m.clientY - r.top : m.clientX - r.left,
          });
        };
      };
    });
  }
  for (const child of d.children) renderNode(child, node, seen);
  return node;
}
