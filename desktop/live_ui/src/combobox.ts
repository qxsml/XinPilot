/** Editable combobox suggestions and repeated-choice interaction. */
import { send } from "./bridge";
import { el } from "./dom";
import { render } from "./render";
import { choices, data, nodes, runtime } from "./state";
import { ViewNode } from "./types";

export function closeChoices() {
  runtime.choicesEpoch++;
  if (runtime.choicesID)
    nodes.get(runtime.choicesID)?.setAttribute("aria-expanded", "false");
  runtime.choicesID = "";
  choices.hidden = true;
  choices.replaceChildren();
}

export function paintChoices(id: string, filter = "") {
  const input = nodes.get(id) as HTMLInputElement,
    d = data.get(id);
  if (!input?.isConnected || !d || d.disabled) {
    closeChoices();
    return;
  }
  choices.replaceChildren();
  for (const value of d.values || []) {
    const text = String(value);
    if (filter && !text.toLowerCase().includes(filter.toLowerCase())) continue;
    const option = el("button", "combo-option", text) as HTMLButtonElement;
    option.type = "button";
    option.setAttribute("role", "option");
    option.setAttribute("aria-selected", String(text === input.value));
    option.onmousedown = (e) => e.preventDefault();
    option.onclick = () => {
      input.value = text;
      closeChoices();
      input.focus();
      void send({ action: "value", id, value: text, selection: true });
    };
    option.onkeydown = (e) => {
      if (e.key === "Escape") {
        closeChoices();
        input.focus();
      } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const next =
          e.key === "ArrowDown"
            ? option.nextElementSibling
            : option.previousElementSibling;
        (next as HTMLElement | null)?.focus();
      } else if (e.key === "Tab") closeChoices();
    };
    choices.append(option);
  }
  if (!choices.childElementCount)
    choices.append(el("div", "combo-empty", "No matching choices"));
  const rect = input.getBoundingClientRect(),
    height = Math.min(240, choices.childElementCount * 34 + 8);
  choices.style.left =
    Math.max(
      4,
      Math.min(rect.left, innerWidth - Math.max(rect.width, 180) - 4),
    ) + "px";
  choices.style.width = Math.max(rect.width, 180) + "px";
  choices.style.top =
    (rect.bottom + height > innerHeight
      ? Math.max(4, rect.top - height)
      : rect.bottom) + "px";
}

export async function openChoices(id: string, keyboard = false) {
  if (data.get(id)?.disabled) return;
  closeChoices();
  runtime.choicesID = id;
  const epoch = runtime.choicesEpoch;
  await send({ action: "post", id });
  if (runtime.choicesID !== id || epoch !== runtime.choicesEpoch) return;
  const state = await pywebview.api.snapshot();
  if (runtime.choicesID !== id || epoch !== runtime.choicesEpoch) return;
  render(state);
  if (!nodes.get(id)?.isConnected || data.get(id)?.disabled) {
    closeChoices();
    return;
  }
  choices.hidden = false;
  nodes.get(id)?.setAttribute("aria-expanded", "true");
  paintChoices(id);
  if (keyboard)
    (choices.querySelector("button") as HTMLElement | null)?.focus();
}

export function editableCombo(input: HTMLInputElement, d: ViewNode) {
  input.classList.add("editable-combo");
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-expanded", String(runtime.choicesID === d.id));
  input.setAttribute("aria-autocomplete", "list");
  let arrow = input.parentElement!.querySelector<HTMLButtonElement>(
    `.combo-arrow[data-owner="${d.id}"]`,
  );
  if (!arrow) {
    arrow = el("button", "combo-arrow", "\u25be") as HTMLButtonElement;
    arrow.type = "button";
    arrow.dataset.owner = d.id;
    arrow.setAttribute("aria-label", "Show all choices");
    arrow.onmousedown = (e) => e.preventDefault();
    arrow.onclick = () => {
      if (runtime.choicesID === d.id) closeChoices();
      else {
        input.focus();
        void openChoices(d.id);
      }
    };
    input.parentElement!.append(arrow);
  }
  arrow.disabled = !!d.disabled;
  arrow.title = d.tooltip || "Show all choices";
  arrow.style.left = d.x + d.width - 26 + "px";
  arrow.style.top = d.y + "px";
  arrow.style.height = d.height + "px";
}
