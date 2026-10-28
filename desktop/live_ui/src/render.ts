/** Apply a controller snapshot and reconcile window/widget lifetimes. */
import { send } from "./bridge";
import { decorateWindow, prompts } from "./dialogs";
import { el } from "./dom";
import {
  app,
  assets,
  data,
  nodes,
  notice,
  runtime,
  savedViews,
  windows,
} from "./state";
import { State } from "./types";
import { renderNode } from "./widgets";

export function render(s: State) {
  Object.assign(assets, s.assets);
  const seen = new Set<string>(),
    seenWindows = new Set<string>();
  const host = document.querySelector("#windows")!;
  host.querySelectorAll(":scope > .veil").forEach((n) => n.remove());
  for (const [index, w] of s.windows.entries()) {
    if (index === 0) {
      renderNode({ ...w, x: 0, y: 0 }, app as HTMLElement, seen);
      continue;
    }
    seenWindows.add(w.id);
    let pane = windows.get(w.id);
    if (!pane) {
      pane = el("div", "toplevel");
      pane.dataset.window = w.id;
      const title = el("div", "window-title"),
        close = document.createElement("button");
      close.textContent = "×";
      close.onclick = () => void send({ action: "close", id: w.id });
      title.append(el("span"), close);
      pane.append(title, el("div", "window-body"));
      decorateWindow(pane, w.id);
      windows.set(w.id, pane);
      host.append(pane);
    }
    if (w.modal) {
      const veil = el("div", "veil");
      veil.style.zIndex = String(100 + index * 2);
      host.append(veil);
    }
    pane.style.zIndex = String(101 + index * 2);
    pane.style.width = Math.min(w.width + 2, innerWidth - 24) + "px";
    pane.style.height = Math.min(w.height + 34, innerHeight - 24) + "px";
    pane.style.left = Math.max(12, (innerWidth - w.width) / 2) + "px";
    pane.style.top = Math.max(12, (innerHeight - w.height - 34) / 2) + "px";
    if (pane.dataset.userX)
      pane.style.left =
        Math.max(
          4,
          Math.min(
            innerWidth - pane.offsetWidth - 4,
            Number(pane.dataset.userX),
          ),
        ) + "px";
    if (pane.dataset.userY)
      pane.style.top =
        Math.max(
          4,
          Math.min(
            innerHeight - pane.offsetHeight - 4,
            Number(pane.dataset.userY),
          ),
        ) + "px";
    pane.classList.toggle("tooltip-window", !!w.tooltip);
    if (w.tooltip) {
      pane.style.width = w.width + "px";
      pane.style.height = w.height + "px";
      pane.style.left =
        Math.max(
          4,
          Math.min(innerWidth - w.width - 4, runtime.lastPointer.x + 12),
        ) + "px";
      pane.style.top =
        Math.max(
          4,
          Math.min(innerHeight - w.height - 4, runtime.lastPointer.y + 18),
        ) + "px";
    }
    pane.querySelector(".window-title span")!.textContent =
      w.title || "XinPilot";
    const surface = renderNode(
      { ...w, x: 0, y: 0 },
      pane.querySelector(".window-body") as HTMLElement,
      seen,
    );
    if (w.title?.startsWith("Peak inspection")) {
      surface.classList.add("peak-surface");
      const actions = w.children.find((c) =>
        c.children.some((b) => b.text === "Assign as product"),
      );
      if (actions) {
        const footer = nodes.get(actions.id)!;
        footer.classList.add("peak-actions");
        footer.style.marginTop = actions.y + "px";
      }
    }
  }
  for (const [id, pane] of windows)
    if (!seenWindows.has(id)) {
      pane.remove();
      windows.delete(id);
    }
  for (const [id, node] of nodes)
    if (!seen.has(id)) {
      savedViews.set(id, { x: node.scrollLeft, y: node.scrollTop });
      node.remove();
      nodes.delete(id);
      data.delete(id);
    }
  const hash = JSON.stringify(s.menu);
  if (runtime.menuHash !== hash) {
    runtime.menuHash = hash;
    const host = document.querySelector("#menus")!;
    host.replaceChildren();
    if (s.menu) {
      const menu = el("div", "menu");
      menu.style.left =
        Math.min(
          innerWidth - 230,
          Math.max(4, s.menu.x || runtime.lastPointer.x),
        ) + "px";
      menu.style.top =
        Math.min(
          innerHeight - 300,
          Math.max(4, s.menu.y || runtime.lastPointer.y),
        ) + "px";
      for (const item of s.menu.entries) {
        if (item.kind === "separator") {
          menu.append(document.createElement("hr"));
          continue;
        }
        const b = document.createElement("button");
        b.textContent = item.text + (item.kind === "cascade" ? " ▸" : "");
        b.disabled = item.disabled;
        b.onclick = () =>
          void send({
            action: "menu",
            id: s.menu!.widget,
            index: item.index,
            x: runtime.lastPointer.x + 180,
            y: runtime.lastPointer.y,
          });
        menu.append(b);
      }
      host.append(menu);
    }
  }
  prompts(s.dialog);
  if (s.errors.length) notice.textContent = s.errors.join("\n");
  else if (runtime.initial) {
    notice.textContent = "";
    runtime.initial = false;
  }
}
