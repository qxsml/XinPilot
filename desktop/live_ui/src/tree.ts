/** Table rendering, stable selection, column resizing and scrolling. */
import { pointer, send } from "./bridge";
import { el } from "./dom";
import { assets, data } from "./state";
import { Info, ViewNode } from "./types";

export function renderTree(node: HTMLElement, d: ViewNode) {
  const hash = JSON.stringify([d.columns, d.rows, d.values, d.rowheight]);
  if (node.dataset.tree !== hash) {
    const oldX = node.scrollLeft,
      oldY = node.scrollTop;
    node.dataset.tree = hash;
    node.replaceChildren();
    node.tabIndex = 0;
    const table = document.createElement("table");
    const isList = d.kind === "Listbox";
    let rows: Info[] =
      d.rows ||
      d.values.map((v: string, i: number) => ({
        id: String(i),
        values: [v],
        style: {},
      }));
    if (!isList) {
      const head = document.createElement("thead"),
        tr = document.createElement("tr");
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
          const start = e.clientX,
            width = col.width;
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
              width: Math.max(40, width + m.clientX - start),
            });
          };
        };
        grip.onclick = (e) => e.stopPropagation();
        th.append(grip);
        tr.append(th);
      }
      head.append(tr);
      table.append(head);
      table.style.width =
        d.columns.reduce((n: number, c: Info) => n + c.width, 0) + "px";
    }
    const body = document.createElement("tbody");
    rows.forEach((row, index) => {
      const tr = document.createElement("tr");
      tr.dataset.item = row.id;
      tr.style.height =
        (d.rowheight || Math.max(22, d.style.font.pixels + 7)) + "px";
      tr.classList.toggle(
        "selected",
        d.selected.map(String).includes(String(row.id)),
      );
      row.values.forEach((value: any, i: number) => {
        const td = document.createElement("td");
        td.textContent = String(value);
        td.title = String(value);
        td.style.textAlign =
          d.columns?.[i]?.anchor === "e"
            ? "right"
            : d.columns?.[i]?.anchor === "center"
              ? "center"
              : "left";
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
              open: !row.open,
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
        const selected = (data.get(d.id)!.selected || []).map(String);
        if (d.multiple && e.ctrlKey)
          ids = selected.includes(String(row.id))
            ? selected.filter((v: string) => v !== String(row.id))
            : [...selected, String(row.id)];
        else if (d.multiple && e.shiftKey) {
          const anchor = Number(node.dataset.anchor || index);
          ids = rows
            .slice(Math.min(anchor, index), Math.max(anchor, index) + 1)
            .map((r) => String(r.id));
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
          e.key.toLowerCase() === "c" ? "<Control-c>" : "<Control-v>",
        );
      }
    };
    node.onscroll = () => {
      if (node.dataset.syncing) return;
      const height = Math.max(
        1,
        rows.length * (d.rowheight || Math.max(22, d.style.font.pixels + 7)),
      );
      void send({
        action: "scroll",
        id: d.id,
        axis: "y",
        position: node.scrollTop / height,
      });
      void send({
        action: "scroll",
        id: d.id,
        axis: "x",
        position: node.scrollLeft / Math.max(1, node.scrollWidth),
      });
    };
  }
  for (const row of node.querySelectorAll<HTMLTableRowElement>("tbody tr"))
    row.classList.toggle(
      "selected",
      (d.selected || []).map(String).includes(row.dataset.item!),
    );
  const height = Math.max(
    1,
    (d.rows?.length || d.values?.length || 0) *
      (d.rowheight || Math.max(22, d.style.font.pixels + 7)),
  );
  const y = (d.yview?.[0] || 0) * height,
    x = (d.xview?.[0] || 0) * node.scrollWidth;
  if (Math.abs(node.scrollTop - y) > 3 || Math.abs(node.scrollLeft - x) > 3) {
    node.dataset.syncing = "1";
    node.scrollTop = y;
    node.scrollLeft = x;
    setTimeout(() => delete node.dataset.syncing, 30);
  }
}
