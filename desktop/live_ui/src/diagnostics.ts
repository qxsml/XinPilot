/** Stable diagnostic surface for existing host shutdown and GUI checks. */
import * as bridge from "./bridge";
import * as canvas from "./canvas";
import * as combobox from "./combobox";
import * as dialogs from "./dialogs";
import * as dom from "./dom";
import * as render from "./render";
import * as startup from "./startup";
import * as state from "./state";
import * as tree from "./tree";
import * as widgets from "./widgets";
import { runtime } from "./state";

Object.defineProperties(globalThis, {
  nodes: { configurable: true, get: () => state.nodes },
  data: { configurable: true, get: () => state.data },
  assets: { configurable: true, get: () => state.assets },
  windows: { configurable: true, get: () => state.windows },
  app: { configurable: true, get: () => state.app },
  notice: { configurable: true, get: () => state.notice },
  savedViews: { configurable: true, get: () => state.savedViews },
  NS: { configurable: true, get: () => state.NS },
  activeActions: { configurable: true, get: () => state.activeActions },
  busy: { configurable: true, get: () => state.busy },
  choices: { configurable: true, get: () => state.choices },
  anchorPoint: { configurable: true, get: () => dom.anchorPoint },
  el: { configurable: true, get: () => dom.el },
  paintFont: { configurable: true, get: () => dom.paintFont },
  place: { configurable: true, get: () => dom.place },
  error: { configurable: true, get: () => bridge.error },
  send: { configurable: true, get: () => bridge.send },
  pointer: { configurable: true, get: () => bridge.pointer },
  frameKinds: { configurable: true, get: () => widgets.frameKinds },
  create: { configurable: true, get: () => widgets.create },
  textImage: { configurable: true, get: () => widgets.textImage },
  renderNode: { configurable: true, get: () => widgets.renderNode },
  renderTree: { configurable: true, get: () => tree.renderTree },
  canvas: { configurable: true, get: () => canvas.canvas },
  prompts: { configurable: true, get: () => dialogs.prompts },
  decorateWindow: { configurable: true, get: () => dialogs.decorateWindow },
  render: { configurable: true, get: () => render.render },
  closeChoices: { configurable: true, get: () => combobox.closeChoices },
  paintChoices: { configurable: true, get: () => combobox.paintChoices },
  openChoices: { configurable: true, get: () => combobox.openChoices },
  editableCombo: { configurable: true, get: () => combobox.editableCombo },
  poll: { configurable: true, get: () => startup.poll },
  finished: {
    configurable: true,
    get: () => runtime.finished,
    set: (value: typeof runtime.finished) => {
      runtime.finished = value;
    },
  },
  inFlight: {
    configurable: true,
    get: () => runtime.inFlight,
    set: (value: typeof runtime.inFlight) => {
      runtime.inFlight = value;
    },
  },
  pressedLabel: {
    configurable: true,
    get: () => runtime.pressedLabel,
    set: (value: typeof runtime.pressedLabel) => {
      runtime.pressedLabel = value;
    },
  },
  polling: {
    configurable: true,
    get: () => runtime.polling,
    set: (value: typeof runtime.polling) => {
      runtime.polling = value;
    },
  },
  ready: {
    configurable: true,
    get: () => runtime.ready,
    set: (value: typeof runtime.ready) => {
      runtime.ready = value;
    },
  },
  lastPointer: {
    configurable: true,
    get: () => runtime.lastPointer,
    set: (value: typeof runtime.lastPointer) => {
      runtime.lastPointer = value;
    },
  },
  promptID: {
    configurable: true,
    get: () => runtime.promptID,
    set: (value: typeof runtime.promptID) => {
      runtime.promptID = value;
    },
  },
  menuHash: {
    configurable: true,
    get: () => runtime.menuHash,
    set: (value: typeof runtime.menuHash) => {
      runtime.menuHash = value;
    },
  },
  lastSize: {
    configurable: true,
    get: () => runtime.lastSize,
    set: (value: typeof runtime.lastSize) => {
      runtime.lastSize = value;
    },
  },
  initial: {
    configurable: true,
    get: () => runtime.initial,
    set: (value: typeof runtime.initial) => {
      runtime.initial = value;
    },
  },
  edits: {
    configurable: true,
    get: () => runtime.edits,
    set: (value: typeof runtime.edits) => {
      runtime.edits = value;
    },
  },
  choicesID: {
    configurable: true,
    get: () => runtime.choicesID,
    set: (value: typeof runtime.choicesID) => {
      runtime.choicesID = value;
    },
  },
  choicesEpoch: {
    configurable: true,
    get: () => runtime.choicesEpoch,
    set: (value: typeof runtime.choicesEpoch) => {
      runtime.choicesEpoch = value;
    },
  },
});
