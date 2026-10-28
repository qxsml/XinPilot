"use strict";
(() => {
  // desktop/live_ui/src/dom.ts
  function anchorPoint(anchor = "center") {
    return {
      x: ["w", "nw", "sw"].includes(anchor) ? 0 : ["e", "ne", "se"].includes(anchor) ? 1 : 0.5,
      y: ["n", "nw", "ne"].includes(anchor) ? 0 : ["s", "sw", "se"].includes(anchor) ? 1 : 0.5
    };
  }
  function el(tag, cls = "", text = "") {
    const e = document.createElement(tag);
    e.className = cls;
    e.textContent = text;
    return e;
  }
  function paintFont(element, f = {}) {
    if (f.family) element.style.fontFamily = f.family;
    if (f.pixels) element.style.fontSize = f.pixels + "px";
    element.style.fontWeight = f.weight === "bold" ? "700" : "400";
    element.style.fontStyle = f.slant === "italic" ? "italic" : "normal";
  }
  function place(e, d) {
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

  // desktop/live_ui/src/state.ts
  var runtime = {
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
    edits: Promise.resolve(),
    choicesID: "",
    choicesEpoch: 0
  };
  var nodes = /* @__PURE__ */ new Map();
  var data = /* @__PURE__ */ new Map();
  var assets = {};
  var windows = /* @__PURE__ */ new Map();
  var app = document.querySelector("#app");
  var notice = document.querySelector("#notice");
  var savedViews = /* @__PURE__ */ new Map();
  var NS = "http://www.w3.org/2000/svg";
  var activeActions = /* @__PURE__ */ new Set();
  var busy = el("div", "busy-status");
  busy.setAttribute("role", "status");
  busy.setAttribute("aria-live", "polite");
  document.body.append(busy);
  var choices = el("div", "combo-choices");
  choices.setAttribute("role", "listbox");
  choices.hidden = true;
  document.body.append(choices);

  // desktop/live_ui/src/bridge.ts
  function error(e) {
    if (runtime.finished) return;
    notice.textContent = String(e?.stack || e?.message || e);
  }
  function send(event) {
    const run = async () => {
      if (runtime.finished) return;
      const key = event.action === "invoke" ? event.id : "";
      if (key && activeActions.has(key)) return;
      let timer;
      if (key) {
        activeActions.add(key);
        nodes.get(key)?.setAttribute("aria-busy", "true");
        timer = window.setTimeout(() => {
          busy.textContent = "Working…";
          busy.classList.add("visible");
        }, 450);
      }
      runtime.inFlight++;
      try {
        const result = await pywebview.api.event(event);
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
  function pointer(id, sequence, event, item) {
    const node = nodes.get(id), rect = node?.getBoundingClientRect();
    const x = event && rect ? event.clientX - rect.left : 0, y = event && rect ? event.clientY - rect.top : 0;
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
      state: event ? (event.shiftKey ? 1 : 0) | (event.ctrlKey ? 4 : 0) | (event.buttons & 1 ? 256 : 0) | (event.buttons & 2 ? 1024 : 0) : 0,
      delta: event instanceof WheelEvent ? event.deltaY > 0 ? -120 : 120 : 0
    });
  }

  // desktop/live_ui/src/canvas.ts
  function canvas(node, d) {
    const signature = JSON.stringify([d.items, d.origin, d.width, d.height]);
    if (node.dataset.canvas === signature) return;
    node.dataset.canvas = signature;
    node.querySelector(":scope > svg")?.remove();
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute(
      "viewBox",
      `${d.origin[0]} ${d.origin[1]} ${d.width} ${d.height}`
    );
    svg.setAttribute("preserveAspectRatio", "none");
    svg.style.position = "absolute";
    svg.style.inset = "0";
    node.prepend(svg);
    for (const item of d.items) {
      const c = item.coords, p = item.props;
      let shape;
      const attr = (s, k, v) => s.setAttribute(k, String(v));
      if (item.type === "rectangle") {
        shape = document.createElementNS(NS, "rect");
        attr(shape, "x", Math.min(c[0], c[2]));
        attr(shape, "y", Math.min(c[1], c[3]));
        attr(shape, "width", Math.abs(c[2] - c[0]));
        attr(shape, "height", Math.abs(c[3] - c[1]));
      } else if (item.type === "oval") {
        shape = document.createElementNS(NS, "ellipse");
        attr(shape, "cx", (c[0] + c[2]) / 2);
        attr(shape, "cy", (c[1] + c[3]) / 2);
        attr(shape, "rx", Math.abs(c[2] - c[0]) / 2);
        attr(shape, "ry", Math.abs(c[3] - c[1]) / 2);
      } else if (item.type === "arc") {
        shape = document.createElementNS(NS, "path");
        const cx = (c[0] + c[2]) / 2, cy = (c[1] + c[3]) / 2, rx = Math.abs(c[2] - c[0]) / 2, ry = Math.abs(c[3] - c[1]) / 2, start = Number(p.start) * Math.PI / 180, extent = Number(p.extent), end = start + extent * Math.PI / 180;
        const x = cx + rx * Math.cos(start), y = cy - ry * Math.sin(start), ex = cx + rx * Math.cos(end), ey = cy - ry * Math.sin(end);
        attr(
          shape,
          "d",
          `M ${x} ${y} A ${rx} ${ry} 0 ${Math.abs(extent) > 180 ? 1 : 0} ${extent > 0 ? 0 : 1} ${ex} ${ey}` + (p.style === "pieslice" ? ` L ${cx} ${cy} Z` : p.style === "chord" ? " Z" : "")
        );
      } else if (item.type === "line" || item.type === "polygon") {
        shape = document.createElementNS(
          NS,
          item.type === "line" ? "polyline" : "polygon"
        );
        attr(
          shape,
          "points",
          c.reduce((out, v, i) => {
            if (i % 2 === 0) out.push(`${v},${c[i + 1]}`);
            return out;
          }, []).join(" ")
        );
      } else if (item.type === "text") {
        shape = document.createElementNS(NS, "text");
        attr(shape, "x", c[0]);
        attr(shape, "y", c[1]);
        paintFont(shape, p.font);
        attr(
          shape,
          "text-anchor",
          anchorPoint(p.anchor).x === 0 ? "start" : anchorPoint(p.anchor).x === 1 ? "end" : "middle"
        );
        attr(
          shape,
          "dominant-baseline",
          anchorPoint(p.anchor).y === 0 ? "hanging" : anchorPoint(p.anchor).y === 1 ? "auto" : "central"
        );
        const lines = String(p.text || "").split("\n");
        lines.forEach((line, i) => {
          const t = document.createElementNS(NS, "tspan");
          attr(t, "x", c[0]);
          attr(t, "dy", i ? (p.font?.pixels || 13) * 1.2 : 0);
          t.textContent = line;
          shape.append(t);
        });
        if (Number(p.angle))
          attr(shape, "transform", `rotate(${-Number(p.angle)} ${c[0]} ${c[1]})`);
      } else if (item.type === "image") {
        if (!assets[p.image]) continue;
        shape = document.createElementNS(NS, "image");
        shape.setAttribute("href", assets[p.image]);
        const probe = new Image();
        probe.src = assets[p.image];
        const width = p.image_width || probe.width, height = p.image_height || probe.height;
        attr(shape, "width", width);
        attr(shape, "height", height);
        attr(shape, "x", c[0] - anchorPoint(p.anchor).x * width);
        attr(shape, "y", c[1] - anchorPoint(p.anchor).y * height);
      } else continue;
      if (item.type !== "image") {
        attr(shape, "fill", p.fill || "none");
        if (item.type === "line") {
          attr(shape, "stroke", p.fill || "#223a4b");
          attr(shape, "fill", "none");
        } else if (item.type !== "text")
          attr(shape, "stroke", p.outline || "none");
        attr(shape, "stroke-width", p.width || 1);
        if (p.dash) attr(shape, "stroke-dasharray", p.dash);
      }
      svg.append(shape);
    }
  }

  // desktop/live_ui/src/dialogs.ts
  function prompts(d) {
    if (!d) {
      document.querySelector("#prompt").replaceChildren();
      runtime.promptID = "";
      return;
    }
    if (runtime.promptID === d.id) return;
    runtime.promptID = d.id;
    const host = document.querySelector("#prompt");
    host.replaceChildren();
    const veil = el("div", "prompt-overlay"), box = el("div", "prompt-box");
    box.append(
      el("h2", "", d.title || "XinPilot"),
      el("p", "", d.message || "Choose a file in the system dialog.")
    );
    veil.append(box);
    host.append(veil);
    if (d.kind.startsWith("askopen") || ["asksaveasfilename", "askdirectory"].includes(d.kind)) {
      runtime.inFlight++;
      void pywebview.api.file_dialog(d.id).catch(error).finally(() => runtime.inFlight--);
      return;
    }
    let input;
    if (["askstring", "askinteger", "askfloat"].includes(d.kind)) {
      input = document.createElement("input");
      input.value = String(d.initialvalue ?? "");
      input.type = d.show ? "password" : d.kind === "askstring" ? "text" : "number";
      if (d.minvalue !== void 0) input.min = String(d.minvalue);
      if (d.maxvalue !== void 0) input.max = String(d.maxvalue);
      box.append(input);
      input.focus();
    }
    const footer = el("div", "prompt-actions");
    box.append(footer);
    let answered = false;
    const answer = (value) => {
      if (answered) return;
      answered = true;
      footer.querySelectorAll("button").forEach((b) => b.disabled = true);
      if (input) input.disabled = true;
      void send({ action: "answer", id: d.id, value });
    };
    let choices2 = [["OK", "ok"]];
    if (d.kind === "askyesno")
      choices2 = [
        ["No", false],
        ["Yes", true]
      ];
    if (d.kind === "askyesnocancel")
      choices2 = [
        ["Cancel", null],
        ["No", false],
        ["Yes", true]
      ];
    if (d.kind === "askquestion")
      choices2 = [
        ["No", "no"],
        ["Yes", "yes"]
      ];
    if (d.kind === "askokcancel")
      choices2 = [
        ["Cancel", false],
        ["OK", true]
      ];
    if (d.kind === "askretrycancel")
      choices2 = [
        ["Cancel", false],
        ["Retry", true]
      ];
    if (input)
      choices2 = [
        ["Cancel", null],
        ["OK", "__input"]
      ];
    for (const [label, value] of choices2) {
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
  function decorateWindow(pane, id) {
    const header = pane.querySelector(".window-title"), close = header.querySelector("button");
    close.title = "Close window";
    close.setAttribute("aria-label", "Close window");
    const expand = document.createElement("button");
    expand.textContent = "⛶";
    expand.title = "Expand window";
    expand.setAttribute("aria-label", "Expand window");
    header.insertBefore(expand, close);
    expand.onclick = () => {
      const current = data.get(id);
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
        height: expanded ? Number(pane.dataset.restoreHeight) : innerHeight - 70
      });
    };
    header.onpointerdown = (e) => {
      if (e.target.closest("button")) return;
      header.setPointerCapture(e.pointerId);
      const rect = pane.getBoundingClientRect(), x = e.clientX, y = e.clientY;
      header.onpointermove = (m) => {
        if (!m.buttons) return;
        pane.dataset.userX = String(
          Math.max(
            4,
            Math.min(
              innerWidth - pane.offsetWidth - 4,
              rect.left + m.clientX - x
            )
          )
        );
        pane.dataset.userY = String(
          Math.max(4, Math.min(innerHeight - 40, rect.top + m.clientY - y))
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
      const x = e.clientX, y = e.clientY, d = data.get(id);
      let last = 0;
      const resize = (m) => {
        pane.dataset.expanded = "0";
        void send({
          action: "window_size",
          id,
          width: Math.min(innerWidth - 42, d.width + m.clientX - x),
          height: Math.min(innerHeight - 70, d.height + m.clientY - y)
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

  // desktop/live_ui/src/tree.ts
  function renderTree(node, d) {
    const hash = JSON.stringify([d.columns, d.rows, d.values, d.rowheight]);
    if (node.dataset.tree !== hash) {
      const oldX = node.scrollLeft, oldY = node.scrollTop;
      node.dataset.tree = hash;
      node.replaceChildren();
      node.tabIndex = 0;
      const table = document.createElement("table");
      const isList = d.kind === "Listbox";
      let rows = d.rows || d.values.map((v, i) => ({
        id: String(i),
        values: [v],
        style: {}
      }));
      if (!isList) {
        const head = document.createElement("thead"), tr = document.createElement("tr");
        for (const col of d.columns) {
          const th = document.createElement("th");
          th.textContent = col.text;
          th.title = col.text;
          th.style.width = col.width + "px";
          th.style.height = (d.rowheight || 25) + "px";
          th.onclick = () => {
            if (performance.now() - Number(th.dataset.resized || 0) > 250)
              void send({ action: "heading", id: d.id, column: col.id });
          };
          const grip = el("span", "column-grip");
          grip.title = "Drag to resize column";
          grip.onpointerdown = (e) => {
            e.stopPropagation();
            e.preventDefault();
            grip.setPointerCapture(e.pointerId);
            const start = e.clientX, width = col.width;
            grip.onpointermove = (m) => {
              if (!m.buttons) return;
              th.style.width = Math.max(40, width + m.clientX - start) + "px";
            };
            grip.onpointerup = (m) => {
              th.dataset.resized = String(performance.now());
              grip.releasePointerCapture(m.pointerId);
              void send({
                action: "column_size",
                id: d.id,
                column: col.id,
                width: Math.max(40, width + m.clientX - start)
              });
            };
          };
          grip.onclick = (e) => e.stopPropagation();
          th.append(grip);
          tr.append(th);
        }
        head.append(tr);
        table.append(head);
        table.style.width = d.columns.reduce((n, c) => n + c.width, 0) + "px";
      }
      const body = document.createElement("tbody");
      rows.forEach((row, index) => {
        const tr = document.createElement("tr");
        tr.dataset.item = row.id;
        tr.style.height = (d.rowheight || Math.max(22, d.style.font.pixels + 7)) + "px";
        tr.classList.toggle(
          "selected",
          d.selected.map(String).includes(String(row.id))
        );
        row.values.forEach((value, i) => {
          const td = document.createElement("td");
          td.textContent = String(value);
          td.title = String(value);
          td.style.textAlign = d.columns?.[i]?.anchor === "e" ? "right" : d.columns?.[i]?.anchor === "center" ? "center" : "left";
          if (row.style?.background)
            td.style.backgroundColor = row.style.background;
          if (row.style?.foreground) td.style.color = row.style.foreground;
          if (i === 0 && row.depth)
            td.style.paddingLeft = 4 + row.depth * 14 + "px";
          if (i === 0 && row.branch) {
            const expand = document.createElement("button");
            expand.textContent = row.open ? "▾" : "▸";
            expand.onclick = (e) => {
              e.stopPropagation();
              void send({
                action: "expand",
                id: d.id,
                item: row.id,
                open: !row.open
              });
            };
            td.prepend(expand);
          }
          if (i === 0 && row.image && assets[row.image]) {
            const image = document.createElement("img");
            image.src = assets[row.image];
            td.prepend(image);
          }
          tr.append(td);
        });
        tr.onclick = (e) => {
          node.focus({ preventScroll: true });
          let ids = [String(row.id)];
          const selected = (data.get(d.id).selected || []).map(String);
          if (d.multiple && e.ctrlKey)
            ids = selected.includes(String(row.id)) ? selected.filter((v) => v !== String(row.id)) : [...selected, String(row.id)];
          else if (d.multiple && e.shiftKey) {
            const anchor = Number(node.dataset.anchor || index);
            ids = rows.slice(Math.min(anchor, index), Math.max(anchor, index) + 1).map((r) => String(r.id));
          } else node.dataset.anchor = String(index);
          void send({ action: "selection", id: d.id, items: ids });
        };
        tr.ondblclick = (e) => void pointer(d.id, "<Double-Button-1>", e, row.id);
        tr.oncontextmenu = (e) => {
          e.preventDefault();
          void pointer(d.id, "<Button-3>", e, row.id);
        };
        body.append(tr);
      });
      table.append(body);
      node.append(table);
      node.scrollLeft = oldX;
      node.scrollTop = oldY;
      node.onkeydown = (e) => {
        if (e.key === "Delete") void pointer(d.id, "<Delete>");
        if (e.ctrlKey && ["c", "v"].includes(e.key.toLowerCase())) {
          e.preventDefault();
          void pointer(
            d.id,
            e.key.toLowerCase() === "c" ? "<Control-c>" : "<Control-v>"
          );
        }
      };
      node.onscroll = () => {
        if (node.dataset.syncing) return;
        const height2 = Math.max(
          1,
          rows.length * (d.rowheight || Math.max(22, d.style.font.pixels + 7))
        );
        void send({
          action: "scroll",
          id: d.id,
          axis: "y",
          position: node.scrollTop / height2
        });
        void send({
          action: "scroll",
          id: d.id,
          axis: "x",
          position: node.scrollLeft / Math.max(1, node.scrollWidth)
        });
      };
    }
    for (const row of node.querySelectorAll("tbody tr"))
      row.classList.toggle(
        "selected",
        (d.selected || []).map(String).includes(row.dataset.item)
      );
    const height = Math.max(
      1,
      (d.rows?.length || d.values?.length || 0) * (d.rowheight || Math.max(22, d.style.font.pixels + 7))
    );
    const y = (d.yview?.[0] || 0) * height, x = (d.xview?.[0] || 0) * node.scrollWidth;
    if (Math.abs(node.scrollTop - y) > 3 || Math.abs(node.scrollLeft - x) > 3) {
      node.dataset.syncing = "1";
      node.scrollTop = y;
      node.scrollLeft = x;
      setTimeout(() => delete node.dataset.syncing, 30);
    }
  }

  // desktop/live_ui/src/widgets.ts
  var frameKinds = /* @__PURE__ */ new Set([
    "Tk",
    "Toplevel",
    "Frame",
    "TFrame",
    "Labelframe",
    "TLabelframe",
    "Panedwindow",
    "TPanedwindow",
    "Notebook",
    "TNotebook"
  ]);
  function create(d) {
    let node;
    if (frameKinds.has(d.kind))
      node = el(
        "div",
        "widget frame" + (d.kind.toLowerCase().includes("labelframe") ? " group" : "")
      );
    else if (["Button", "TButton", "Menubutton", "TMenubutton"].includes(d.kind)) {
      node = el("button", "widget");
      node.onclick = () => {
        const current = data.get(d.id);
        if (current.kind.includes("Menubutton")) {
          const r = node.getBoundingClientRect();
          void send({ action: "menu", id: d.id, x: r.left, y: r.bottom });
        } else void send({ action: "invoke", id: d.id });
      };
    } else if (["Checkbutton", "TCheckbutton", "Radiobutton", "TRadiobutton"].includes(
      d.kind
    )) {
      node = el("label", "widget check");
      const input = document.createElement("input");
      input.type = d.kind.includes("Radio") ? "radio" : "checkbox";
      input.onchange = () => void send({ action: "invoke", id: d.id });
      node.append(input, el("span"));
    } else if (["Entry", "TEntry", "Spinbox", "TSpinbox", "TCombobox"].includes(d.kind)) {
      node = document.createElement(
        d.kind === "TCombobox" && d.readonly ? "select" : "input"
      );
      node.className = "widget";
      const input = node;
      input.oninput = () => {
        if (node.tagName !== "SELECT")
          void send({
            action: "value",
            id: d.id,
            value: input.value,
            selection: false
          });
        if (runtime.choicesID === d.id) paintChoices(d.id, input.value);
      };
      input.onchange = () => void send({
        action: "value",
        id: d.id,
        value: input.value,
        selection: node.tagName === "SELECT"
      });
      input.onfocus = () => {
        void pointer(d.id, "<FocusIn>");
        if (d.kind === "TCombobox") void send({ action: "post", id: d.id });
      };
      input.onblur = () => void pointer(d.id, "<FocusOut>");
      input.onkeydown = (e) => {
        if (d.kind === "TCombobox" && !data.get(d.id)?.readonly && e.key === "ArrowDown") {
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
      const input = node;
      input.oninput = () => void send({ action: "value", id: d.id, value: input.value });
      input.onblur = () => void pointer(d.id, "<FocusOut>");
      input.onfocus = () => void pointer(d.id, "<FocusIn>");
    } else if (["Treeview", "Listbox"].includes(d.kind))
      node = el("div", "widget tree");
    else if (d.kind === "Canvas") {
      node = el("div", "widget canvas");
      node.onpointerdown = (e) => {
        if (e.target.closest(".widget") !== node) return;
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
        if (e.target.closest(".widget") !== node) return;
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
      const range = node;
      range.type = "range";
      range.className = "widget scrollbar";
      range.min = "0";
      range.max = "1";
      range.step = ".001";
      range.oninput = () => void send(
        d.kind.includes("Scrollbar") ? { action: "scroll", id: d.id, position: Number(range.value) } : { action: "value", id: d.id, value: Number(range.value) }
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
      (e) => void pointer(d.id, "<Enter>", e)
    );
    node.addEventListener(
      "mouseleave",
      (e) => void pointer(d.id, "<Leave>", e)
    );
    return node;
  }
  function textImage(node, d) {
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
    const text = d.kind === "TLabel" && d.text === "No Tecan, manual, or pushed transfer rows available." ? "No transfers to display." : d.text;
    if (text && (!hasImage || d.compound !== "none"))
      node.append(el("span", "", text));
    node.style.flexDirection = d.compound === "top" ? "column" : d.compound === "bottom" ? "column-reverse" : d.compound === "right" ? "row-reverse" : "row";
    if (node instanceof HTMLButtonElement) {
      node.setAttribute("aria-label", d.text);
      if (hasImage) node.title = d.tooltip || d.text;
    }
  }
  function renderNode(d, parent, seen) {
    seen.add(d.id);
    data.set(d.id, d);
    let node = nodes.get(d.id);
    if (node && d.kind === "TCombobox" && node.tagName === "SELECT" !== !!d.readonly) {
      node.remove();
      nodes.delete(d.id);
      node = void 0;
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
          node.scrollLeft = view.x;
          node.scrollTop = view.y;
        });
    }
    place(node, d);
    node.classList.toggle("map-emphasis", !!d.emphasized);
    if (node instanceof HTMLButtonElement || node instanceof HTMLInputElement || node instanceof HTMLSelectElement || node instanceof HTMLTextAreaElement)
      node.disabled = !!d.disabled;
    if ([
      "Label",
      "TLabel",
      "Message",
      "Button",
      "TButton",
      "Menubutton",
      "TMenubutton"
    ].includes(d.kind)) {
      textImage(node, d);
      node.style.justifyContent = anchorPoint(d.style.anchor).x === 0 ? "flex-start" : anchorPoint(d.style.anchor).x === 1 ? "flex-end" : "center";
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
    if (["Checkbutton", "TCheckbutton", "Radiobutton", "TRadiobutton"].includes(
      d.kind
    )) {
      const input = node.querySelector("input");
      input.checked = !!d.selected;
      input.disabled = !!d.disabled;
      const span = node.querySelector("span");
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
    if (node instanceof HTMLInputElement || node instanceof HTMLTextAreaElement || node instanceof HTMLSelectElement) {
      if (d.kind === "TCombobox" && node instanceof HTMLSelectElement) {
        const values = JSON.stringify([
          d.values,
          d.values.includes(d.value) ? "" : d.value
        ]);
        if (node.dataset.options !== values) {
          node.dataset.options = values;
          node.replaceChildren();
          for (const v of d.values.includes(d.value) || !d.value ? d.values : [d.value, ...d.values]) {
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
      if ((document.activeElement !== node || node instanceof HTMLTextAreaElement && d.disabled) && d.value !== void 0 && node.value !== String(d.value)) {
        const x = node.scrollLeft, y = node.scrollTop, follow = node instanceof HTMLTextAreaElement && d.disabled && y + node.clientHeight >= node.scrollHeight - 5;
        node.value = String(d.value);
        node.scrollLeft = x;
        node.scrollTop = follow ? node.scrollHeight : y;
      }
      if (node instanceof HTMLInputElement && ["Entry", "TEntry"].includes(d.kind)) {
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
      if (tabs.dataset.hash !== hash) {
        tabs.dataset.hash = hash;
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
              ry: e.isTrusted ? (e.clientY - r.top) / r.height : 0.5
            });
          };
          tabs.append(b);
        }
      }
      tabs.style.height = Math.max(24, d.children[0]?.y || 30) + "px";
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
      const range = node;
      range.classList.toggle("vertical", d.orient === "vertical");
      range.value = String(d.range?.[0] || 0);
      range.max = String(
        Math.max(1e-3, 1 - (d.range?.[1] || 1) + (d.range?.[0] || 0))
      );
      range.disabled = d.range?.[0] === 0 && d.range?.[1] === 1;
    }
    if (d.kind.includes("Scale")) {
      const range = node;
      range.min = String(d.from);
      range.max = String(d.to);
      range.classList.toggle("vertical", d.orient === "vertical");
    }
    if (d.kind.includes("Progressbar")) {
      node.classList.toggle("indeterminate", d.mode === "indeterminate");
      node.firstChild.style.width = Math.min(100, 100 * d.value / d.maximum) + "%";
    }
    if (d.kind.toLowerCase().includes("panedwindow")) {
      const panes = d.children.slice(0, -1);
      for (const h of node.querySelectorAll(":scope > .sash"))
        if (Number(h.dataset.index) >= panes.length) h.remove();
      panes.forEach((child, index) => {
        let h = node.querySelector(
          `:scope > .sash[data-index="${index}"]`
        );
        if (!h) {
          h = el("div", "sash");
          h.dataset.index = String(index);
          h.title = "Drag to resize panels";
          node.append(h);
        }
        const handle = h, vertical = d.orient === "vertical";
        handle.style.cssText = `position:absolute;z-index:5;cursor:${vertical ? "row-resize" : "col-resize"};left:${vertical ? "0px" : child.x + child.width - 2 + "px"};top:${vertical ? child.y + child.height - 2 + "px" : "0px"};width:${vertical ? "100%" : "7px"};height:${vertical ? "7px" : "100%"};`;
        handle.onpointerdown = (e) => {
          handle.setPointerCapture(e.pointerId);
          handle.classList.add("dragging");
          let last = 0;
          handle.onpointermove = (m) => {
            if (!m.buttons || performance.now() - last < 40) return;
            last = performance.now();
            const r = node.getBoundingClientRect();
            void send({
              action: "sash",
              id: d.id,
              index,
              position: vertical ? m.clientY - r.top : m.clientX - r.left
            });
          };
          handle.onpointerup = (m) => {
            handle.releasePointerCapture(m.pointerId);
            handle.classList.remove("dragging");
            const r = node.getBoundingClientRect();
            void send({
              action: "sash",
              id: d.id,
              index,
              position: vertical ? m.clientY - r.top : m.clientX - r.left
            });
          };
        };
      });
    }
    for (const child of d.children) renderNode(child, node, seen);
    return node;
  }

  // desktop/live_ui/src/render.ts
  function render(s) {
    Object.assign(assets, s.assets);
    const seen = /* @__PURE__ */ new Set(), seenWindows = /* @__PURE__ */ new Set();
    const host = document.querySelector("#windows");
    host.querySelectorAll(":scope > .veil").forEach((n) => n.remove());
    for (const [index, w] of s.windows.entries()) {
      if (index === 0) {
        renderNode({ ...w, x: 0, y: 0 }, app, seen);
        continue;
      }
      seenWindows.add(w.id);
      let pane = windows.get(w.id);
      if (!pane) {
        pane = el("div", "toplevel");
        pane.dataset.window = w.id;
        const title = el("div", "window-title"), close = document.createElement("button");
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
        pane.style.left = Math.max(
          4,
          Math.min(
            innerWidth - pane.offsetWidth - 4,
            Number(pane.dataset.userX)
          )
        ) + "px";
      if (pane.dataset.userY)
        pane.style.top = Math.max(
          4,
          Math.min(
            innerHeight - pane.offsetHeight - 4,
            Number(pane.dataset.userY)
          )
        ) + "px";
      pane.classList.toggle("tooltip-window", !!w.tooltip);
      if (w.tooltip) {
        pane.style.width = w.width + "px";
        pane.style.height = w.height + "px";
        pane.style.left = Math.max(
          4,
          Math.min(innerWidth - w.width - 4, runtime.lastPointer.x + 12)
        ) + "px";
        pane.style.top = Math.max(
          4,
          Math.min(innerHeight - w.height - 4, runtime.lastPointer.y + 18)
        ) + "px";
      }
      pane.querySelector(".window-title span").textContent = w.title || "XinPilot";
      const surface = renderNode(
        { ...w, x: 0, y: 0 },
        pane.querySelector(".window-body"),
        seen
      );
      if (w.title?.startsWith("Peak inspection")) {
        surface.classList.add("peak-surface");
        const actions = w.children.find(
          (c) => c.children.some((b) => b.text === "Assign as product")
        );
        if (actions) {
          const footer = nodes.get(actions.id);
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
      const host2 = document.querySelector("#menus");
      host2.replaceChildren();
      if (s.menu) {
        const menu = el("div", "menu");
        menu.style.left = Math.min(
          innerWidth - 230,
          Math.max(4, s.menu.x || runtime.lastPointer.x)
        ) + "px";
        menu.style.top = Math.min(
          innerHeight - 300,
          Math.max(4, s.menu.y || runtime.lastPointer.y)
        ) + "px";
        for (const item of s.menu.entries) {
          if (item.kind === "separator") {
            menu.append(document.createElement("hr"));
            continue;
          }
          const b = document.createElement("button");
          b.textContent = item.text + (item.kind === "cascade" ? " ▸" : "");
          b.disabled = item.disabled;
          b.onclick = () => void send({
            action: "menu",
            id: s.menu.widget,
            index: item.index,
            x: runtime.lastPointer.x + 180,
            y: runtime.lastPointer.y
          });
          menu.append(b);
        }
        host2.append(menu);
      }
    }
    prompts(s.dialog);
    if (s.errors.length) notice.textContent = s.errors.join("\n");
    else if (runtime.initial) {
      notice.textContent = "";
      runtime.initial = false;
    }
  }

  // desktop/live_ui/src/combobox.ts
  function closeChoices() {
    runtime.choicesEpoch++;
    if (runtime.choicesID)
      nodes.get(runtime.choicesID)?.setAttribute("aria-expanded", "false");
    runtime.choicesID = "";
    choices.hidden = true;
    choices.replaceChildren();
  }
  function paintChoices(id, filter = "") {
    const input = nodes.get(id), d = data.get(id);
    if (!input?.isConnected || !d || d.disabled) {
      closeChoices();
      return;
    }
    choices.replaceChildren();
    for (const value of d.values || []) {
      const text = String(value);
      if (filter && !text.toLowerCase().includes(filter.toLowerCase())) continue;
      const option = el("button", "combo-option", text);
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
          const next = e.key === "ArrowDown" ? option.nextElementSibling : option.previousElementSibling;
          next?.focus();
        } else if (e.key === "Tab") closeChoices();
      };
      choices.append(option);
    }
    if (!choices.childElementCount)
      choices.append(el("div", "combo-empty", "No matching choices"));
    const rect = input.getBoundingClientRect(), height = Math.min(240, choices.childElementCount * 34 + 8);
    choices.style.left = Math.max(
      4,
      Math.min(rect.left, innerWidth - Math.max(rect.width, 180) - 4)
    ) + "px";
    choices.style.width = Math.max(rect.width, 180) + "px";
    choices.style.top = (rect.bottom + height > innerHeight ? Math.max(4, rect.top - height) : rect.bottom) + "px";
  }
  async function openChoices(id, keyboard = false) {
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
      choices.querySelector("button")?.focus();
  }
  function editableCombo(input, d) {
    input.classList.add("editable-combo");
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-expanded", String(runtime.choicesID === d.id));
    input.setAttribute("aria-autocomplete", "list");
    let arrow = input.parentElement.querySelector(
      `.combo-arrow[data-owner="${d.id}"]`
    );
    if (!arrow) {
      arrow = el("button", "combo-arrow", "▾");
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
      input.parentElement.append(arrow);
    }
    arrow.disabled = !!d.disabled;
    arrow.title = d.tooltip || "Show all choices";
    arrow.style.left = d.x + d.width - 26 + "px";
    arrow.style.top = d.y + "px";
    arrow.style.height = d.height + "px";
  }

  // desktop/live_ui/src/startup.ts
  async function poll() {
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
              height: innerHeight - 70
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
    if (!e.target.closest(".menu") && document.querySelector(".menu"))
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
    if (runtime.choicesID && !choices.contains(e.target) && e.target !== nodes.get(runtime.choicesID) && !e.target.closest(".combo-arrow"))
      closeChoices();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Tab" || e.key === "Escape") closeChoices();
  });
  window.addEventListener("resize", closeChoices);
  setInterval(() => {
    for (const arrow of document.querySelectorAll(".combo-arrow")) {
      const owner = nodes.get(arrow.dataset.owner);
      if (!owner?.isConnected || !(owner instanceof HTMLInputElement))
        arrow.remove();
    }
    if (runtime.choicesID && (!nodes.get(runtime.choicesID)?.isConnected || data.get(runtime.choicesID)?.disabled))
      closeChoices();
  }, 160);

  // desktop/live_ui/src/diagnostics.ts
  Object.defineProperties(globalThis, {
    nodes: { configurable: true, get: () => nodes },
    data: { configurable: true, get: () => data },
    assets: { configurable: true, get: () => assets },
    windows: { configurable: true, get: () => windows },
    app: { configurable: true, get: () => app },
    notice: { configurable: true, get: () => notice },
    savedViews: { configurable: true, get: () => savedViews },
    NS: { configurable: true, get: () => NS },
    activeActions: { configurable: true, get: () => activeActions },
    busy: { configurable: true, get: () => busy },
    choices: { configurable: true, get: () => choices },
    anchorPoint: { configurable: true, get: () => anchorPoint },
    el: { configurable: true, get: () => el },
    paintFont: { configurable: true, get: () => paintFont },
    place: { configurable: true, get: () => place },
    error: { configurable: true, get: () => error },
    send: { configurable: true, get: () => send },
    pointer: { configurable: true, get: () => pointer },
    frameKinds: { configurable: true, get: () => frameKinds },
    create: { configurable: true, get: () => create },
    textImage: { configurable: true, get: () => textImage },
    renderNode: { configurable: true, get: () => renderNode },
    renderTree: { configurable: true, get: () => renderTree },
    canvas: { configurable: true, get: () => canvas },
    prompts: { configurable: true, get: () => prompts },
    decorateWindow: { configurable: true, get: () => decorateWindow },
    render: { configurable: true, get: () => render },
    closeChoices: { configurable: true, get: () => closeChoices },
    paintChoices: { configurable: true, get: () => paintChoices },
    openChoices: { configurable: true, get: () => openChoices },
    editableCombo: { configurable: true, get: () => editableCombo },
    poll: { configurable: true, get: () => poll },
    finished: {
      configurable: true,
      get: () => runtime.finished,
      set: (value) => {
        runtime.finished = value;
      }
    },
    inFlight: {
      configurable: true,
      get: () => runtime.inFlight,
      set: (value) => {
        runtime.inFlight = value;
      }
    },
    pressedLabel: {
      configurable: true,
      get: () => runtime.pressedLabel,
      set: (value) => {
        runtime.pressedLabel = value;
      }
    },
    polling: {
      configurable: true,
      get: () => runtime.polling,
      set: (value) => {
        runtime.polling = value;
      }
    },
    ready: {
      configurable: true,
      get: () => runtime.ready,
      set: (value) => {
        runtime.ready = value;
      }
    },
    lastPointer: {
      configurable: true,
      get: () => runtime.lastPointer,
      set: (value) => {
        runtime.lastPointer = value;
      }
    },
    promptID: {
      configurable: true,
      get: () => runtime.promptID,
      set: (value) => {
        runtime.promptID = value;
      }
    },
    menuHash: {
      configurable: true,
      get: () => runtime.menuHash,
      set: (value) => {
        runtime.menuHash = value;
      }
    },
    lastSize: {
      configurable: true,
      get: () => runtime.lastSize,
      set: (value) => {
        runtime.lastSize = value;
      }
    },
    initial: {
      configurable: true,
      get: () => runtime.initial,
      set: (value) => {
        runtime.initial = value;
      }
    },
    edits: {
      configurable: true,
      get: () => runtime.edits,
      set: (value) => {
        runtime.edits = value;
      }
    },
    choicesID: {
      configurable: true,
      get: () => runtime.choicesID,
      set: (value) => {
        runtime.choicesID = value;
      }
    },
    choicesEpoch: {
      configurable: true,
      get: () => runtime.choicesEpoch,
      set: (value) => {
        runtime.choicesEpoch = value;
      }
    }
  });
})();
