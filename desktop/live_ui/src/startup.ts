/** Application polling and document-level event listeners. */
import { error, pointer, send } from "./bridge";
import { closeChoices } from "./combobox";
import { render } from "./render";
import { choices, data, nodes, runtime, windows } from "./state";

export async function poll() {
  if (!runtime.ready || runtime.polling) return;
  runtime.polling = true;
  try {
    const size = innerWidth + "x" + innerHeight;
    if (size !== runtime.lastSize) {
      runtime.lastSize = size;
      await send({ action: "resize", width: innerWidth, height: innerHeight });
      for (const [id, pane] of windows)
        if (pane.dataset.expanded === "1")
          await send({
            action: "window_size",
            id,
            width: innerWidth - 42,
            height: innerHeight - 70,
          });
    }
    const s = await pywebview.api.snapshot();
    if (s.closed) {
      runtime.finished = true;
      runtime.ready = false;
      return;
    }
    render(s);
  } catch (e) {
    error(e);
  } finally {
    runtime.polling = false;
  }
}

document.addEventListener("mousedown", (e) => {
  if (
    !(e.target as HTMLElement).closest(".menu") &&
    document.querySelector(".menu")
  )
    void send({ action: "dismiss_menu" });
});

window.addEventListener("pywebviewready", () => {
  runtime.ready = true;
  void poll();
  setInterval(() => void poll(), 160);
});

document.addEventListener("mouseup", (e) => {
  if (runtime.pressedLabel) {
    void pointer(runtime.pressedLabel, "<ButtonRelease-1>", e);
    runtime.pressedLabel = "";
  }
});

document.addEventListener("mousedown", (e) => {
  if (
    runtime.choicesID &&
    !choices.contains(e.target as Node) &&
    e.target !== nodes.get(runtime.choicesID) &&
    !(e.target as HTMLElement).closest(".combo-arrow")
  )
    closeChoices();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Tab" || e.key === "Escape") closeChoices();
});

window.addEventListener("resize", closeChoices);

setInterval(() => {
  for (const arrow of document.querySelectorAll<HTMLElement>(".combo-arrow")) {
    const owner = nodes.get(arrow.dataset.owner!);
    if (!owner?.isConnected || !(owner instanceof HTMLInputElement))
      arrow.remove();
  }
  if (
    runtime.choicesID &&
    (!nodes.get(runtime.choicesID)?.isConnected ||
      data.get(runtime.choicesID)?.disabled)
  )
    closeChoices();
}, 160);
