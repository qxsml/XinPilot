/** Scientific and well-map SVG rendering with pointer translation. */
import { anchorPoint, paintFont } from "./dom";
import { NS, assets } from "./state";
import { ViewNode } from "./types";

export function canvas(node: HTMLElement, d: ViewNode) {
  const signature = JSON.stringify([d.items, d.origin, d.width, d.height]);
  if (node.dataset.canvas === signature) return;
  node.dataset.canvas = signature;
  node.querySelector(":scope > svg")?.remove();
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute(
    "viewBox",
    `${d.origin[0]} ${d.origin[1]} ${d.width} ${d.height}`,
  );
  svg.setAttribute("preserveAspectRatio", "none");
  svg.style.position = "absolute";
  svg.style.inset = "0";
  node.prepend(svg);
  for (const item of d.items) {
    const c = item.coords,
      p = item.props;
    let shape: SVGElement;
    const attr = (s: SVGElement, k: string, v: any) =>
      s.setAttribute(k, String(v));
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
      const cx = (c[0] + c[2]) / 2,
        cy = (c[1] + c[3]) / 2,
        rx = Math.abs(c[2] - c[0]) / 2,
        ry = Math.abs(c[3] - c[1]) / 2,
        start = (Number(p.start) * Math.PI) / 180,
        extent = Number(p.extent),
        end = start + (extent * Math.PI) / 180;
      const x = cx + rx * Math.cos(start),
        y = cy - ry * Math.sin(start),
        ex = cx + rx * Math.cos(end),
        ey = cy - ry * Math.sin(end);
      attr(
        shape,
        "d",
        `M ${x} ${y} A ${rx} ${ry} 0 ${Math.abs(extent) > 180 ? 1 : 0} ${extent > 0 ? 0 : 1} ${ex} ${ey}` +
          (p.style === "pieslice"
            ? ` L ${cx} ${cy} Z`
            : p.style === "chord"
              ? " Z"
              : ""),
      );
    } else if (item.type === "line" || item.type === "polygon") {
      shape = document.createElementNS(
        NS,
        item.type === "line" ? "polyline" : "polygon",
      );
      attr(
        shape,
        "points",
        c
          .reduce((out: string[], v: number, i: number) => {
            if (i % 2 === 0) out.push(`${v},${c[i + 1]}`);
            return out;
          }, [])
          .join(" "),
      );
    } else if (item.type === "text") {
      shape = document.createElementNS(NS, "text");
      attr(shape, "x", c[0]);
      attr(shape, "y", c[1]);
      paintFont(shape, p.font);
      attr(
        shape,
        "text-anchor",
        anchorPoint(p.anchor).x === 0
          ? "start"
          : anchorPoint(p.anchor).x === 1
            ? "end"
            : "middle",
      );
      attr(
        shape,
        "dominant-baseline",
        anchorPoint(p.anchor).y === 0
          ? "hanging"
          : anchorPoint(p.anchor).y === 1
            ? "auto"
            : "central",
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
      const width = p.image_width || probe.width,
        height = p.image_height || probe.height;
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
