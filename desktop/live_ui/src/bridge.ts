/** Ordered bridge calls, busy feedback and pointer-event translation. */
import { activeActions, busy, nodes, notice, runtime } from "./state";
import { Info } from "./types";

export function error(e: any) {
  if (runtime.finished) return;
  notice.textContent = String(e?.stack || e?.message || e);
}

export function send(event: Info) {
  const run = async () => {
    if (runtime.finished) return;
    const key = event.action === "invoke" ? event.id : "";
    if (key && activeActions.has(key)) return;
    let timer: number | undefined;
    if (key) {
      activeActions.add(key);
      nodes.get(key)?.setAttribute("aria-busy", "true");
      timer = window.setTimeout(() => {
        busy.textContent = "Working\u2026";
        busy.classList.add("visible");
      }, 450);
    }
    runtime.inFlight++;
    try {
      const result = (await pywebview.api.event(event)) as any;
      if (result?.closed) {
        runtime.finished = true;
        runtime.ready = false;
      }
      return result;
    } catch (e) {
      error(e);
    } finally {
      runtime.inFlight--;
      if (timer) clearTimeout(timer);
      if (key) {
        activeActions.delete(key);
        nodes.get(key)?.removeAttribute("aria-busy");
        if (!activeActions.size) {
          busy.textContent = "";
          busy.classList.remove("visible");
        }
      }
    }
  };
  if (event.action === "value") {
    runtime.edits = runtime.edits.then(run);
    return runtime.edits;
  }
  return event.action === "answer" ? run() : runtime.edits.then(run);
}

export function pointer(
  id: string,
  sequence: string,
  event?: MouseEvent | WheelEvent,
  item?: string,
) {
  const node = nodes.get(id),
    rect = node?.getBoundingClientRect();
  const x = event && rect ? event.clientX - rect.left : 0,
    y = event && rect ? event.clientY - rect.top : 0;
  if (event) runtime.lastPointer = { x: event.clientX, y: event.clientY };
  return send({
    action: "pointer",
    id,
    sequence,
    x: Math.round(x),
    y: Math.round(y),
    rootx: runtime.lastPointer.x,
    rooty: runtime.lastPointer.y,
    item,
    state: event
      ? (event.shiftKey ? 1 : 0) |
        (event.ctrlKey ? 4 : 0) |
        (event.buttons & 1 ? 256 : 0) |
        (event.buttons & 2 ? 1024 : 0)
      : 0,
    delta: event instanceof WheelEvent ? (event.deltaY > 0 ? -120 : 120) : 0,
  });
}
