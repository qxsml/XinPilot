/** Modal prompts and resizable secondary windows. */
import { error, send } from "./bridge";
import { el } from "./dom";
import { data, runtime } from "./state";
import { Info } from "./types";

export function prompts(d?: Info) {
  if (!d) {
    document.querySelector("#prompt")!.replaceChildren();
    runtime.promptID = "";
    return;
  }
  if (runtime.promptID === d.id) return;
  runtime.promptID = d.id;
  const host = document.querySelector("#prompt")!;
  host.replaceChildren();
  const veil = el("div", "prompt-overlay"),
    box = el("div", "prompt-box");
  box.append(
    el("h2", "", d.title || "XinPilot"),
    el("p", "", d.message || "Choose a file in the system dialog."),
  );
  veil.append(box);
  host.append(veil);
  if (
    d.kind.startsWith("askopen") ||
    ["asksaveasfilename", "askdirectory"].includes(d.kind)
  ) {
    runtime.inFlight++;
    void pywebview.api
      .file_dialog(d.id)
      .catch(error)
      .finally(() => runtime.inFlight--);
    return;
  }
  let input: HTMLInputElement | undefined;
  if (["askstring", "askinteger", "askfloat"].includes(d.kind)) {
    input = document.createElement("input");
    input.value = String(d.initialvalue ?? "");
    input.type = d.show
      ? "password"
      : d.kind === "askstring"
        ? "text"
        : "number";
    if (d.minvalue !== undefined) input.min = String(d.minvalue);
    if (d.maxvalue !== undefined) input.max = String(d.maxvalue);
    box.append(input);
    input.focus();
  }
  const footer = el("div", "prompt-actions");
  box.append(footer);
  let answered = false;
  const answer = (value: any) => {
    if (answered) return;
    answered = true;
    footer.querySelectorAll("button").forEach((b) => (b.disabled = true));
    if (input) input.disabled = true;
    void send({ action: "answer", id: d.id, value });
  };
  let choices: Array<[string, any]> = [["OK", "ok"]];
  if (d.kind === "askyesno")
    choices = [
      ["No", false],
      ["Yes", true],
    ];
  if (d.kind === "askyesnocancel")
    choices = [
      ["Cancel", null],
      ["No", false],
      ["Yes", true],
    ];
  if (d.kind === "askquestion")
    choices = [
      ["No", "no"],
      ["Yes", "yes"],
    ];
  if (d.kind === "askokcancel")
    choices = [
      ["Cancel", false],
      ["OK", true],
    ];
  if (d.kind === "askretrycancel")
    choices = [
      ["Cancel", false],
      ["Retry", true],
    ];
  if (input)
    choices = [
      ["Cancel", null],
      ["OK", "__input"],
    ];
  for (const [label, value] of choices) {
    const b = document.createElement("button");
    b.textContent = label;
    b.onclick = () => {
      if (value === "__input" && input && !input.checkValidity()) {
        input.reportValidity();
        return;
      }
      answer(value === "__input" ? input?.value : value);
    };
    footer.append(b);
  }
}

export function decorateWindow(pane: HTMLElement, id: string) {
  const header = pane.querySelector<HTMLElement>(".window-title")!,
    close = header.querySelector("button")!;
  close.title = "Close window";
  close.setAttribute("aria-label", "Close window");
  const expand = document.createElement("button");
  expand.textContent = "\u26f6";
  expand.title = "Expand window";
  expand.setAttribute("aria-label", "Expand window");
  header.insertBefore(expand, close);
  expand.onclick = () => {
    const current = data.get(id)!;
    const expanded = pane.dataset.expanded === "1";
    if (!expanded) {
      pane.dataset.restoreWidth = String(current.width);
      pane.dataset.restoreHeight = String(current.height);
    }
    pane.dataset.expanded = expanded ? "0" : "1";
    delete pane.dataset.userX;
    delete pane.dataset.userY;
    expand.title = expanded ? "Expand window" : "Restore window size";
    expand.setAttribute("aria-label", expand.title);
    void send({
      action: "window_size",
      id,
      width: expanded ? Number(pane.dataset.restoreWidth) : innerWidth - 42,
      height: expanded ? Number(pane.dataset.restoreHeight) : innerHeight - 70,
    });
  };
  header.onpointerdown = (e) => {
    if ((e.target as Element).closest("button")) return;
    header.setPointerCapture(e.pointerId);
    const rect = pane.getBoundingClientRect(),
      x = e.clientX,
      y = e.clientY;
    header.onpointermove = (m) => {
      if (!m.buttons) return;
      pane.dataset.userX = String(
        Math.max(
          4,
          Math.min(
            innerWidth - pane.offsetWidth - 4,
            rect.left + m.clientX - x,
          ),
        ),
      );
      pane.dataset.userY = String(
        Math.max(4, Math.min(innerHeight - 40, rect.top + m.clientY - y)),
      );
      pane.style.left = pane.dataset.userX + "px";
      pane.style.top = pane.dataset.userY + "px";
    };
    header.onpointerup = (m) => header.releasePointerCapture(m.pointerId);
  };
  const grip = el("div", "window-resizer");
  grip.title = "Drag to resize window";
  pane.append(grip);
  grip.onpointerdown = (e) => {
    grip.setPointerCapture(e.pointerId);
    const x = e.clientX,
      y = e.clientY,
      d = data.get(id)!;
    let last = 0;
    const resize = (m: PointerEvent) => {
      pane.dataset.expanded = "0";
      void send({
        action: "window_size",
        id,
        width: Math.min(innerWidth - 42, d.width + m.clientX - x),
        height: Math.min(innerHeight - 70, d.height + m.clientY - y),
      });
    };
    grip.onpointermove = (m) => {
      if (m.buttons && performance.now() - last > 60) {
        last = performance.now();
        resize(m);
      }
    };
    grip.onpointerup = (m) => {
      grip.releasePointerCapture(m.pointerId);
      resize(m);
    };
  };
}
