/** One owner for renderer maps and transient interface session state. */
import { el } from "./dom";
import { ViewNode } from "./types";

export const runtime = {
  finished: false,
  inFlight: 0,
  pressedLabel: "",
  polling: false,
  ready: false,
  lastPointer: { x: 20, y: 20 },
  promptID: "",
  menuHash: "",
  lastSize: "",
  initial: true,
  edits: Promise.resolve() as Promise<any>,
  choicesID: "",
  choicesEpoch: 0,
};

export const nodes = new Map<string, HTMLElement>(),
  data = new Map<string, ViewNode>(),
  assets: Record<string, string> = {},
  windows = new Map<string, HTMLElement>();

export const app = document.querySelector("#app")!,
  notice = document.querySelector("#notice")!;

export const savedViews = new Map<
  string,
  {
    x: number;
    y: number;
  }
>();

export const NS = "http://www.w3.org/2000/svg";

export const activeActions = new Set<string>();

export const busy = el("div", "busy-status");

busy.setAttribute("role", "status");

busy.setAttribute("aria-live", "polite");

document.body.append(busy);

export const choices = el("div", "combo-choices");

choices.setAttribute("role", "listbox");

choices.hidden = true;

document.body.append(choices);
