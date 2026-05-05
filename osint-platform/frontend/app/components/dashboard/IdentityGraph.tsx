"use client";
import cytoscape, { type Core, type ElementDefinition, type StylesheetStyle } from "cytoscape";
import coseBilkent from "cytoscape-cose-bilkent";
import { useEffect, useRef, useState } from "react";
import type { Finding, FindingType } from "../../lib/types";
import { GlassCard, CardHeader } from "../ui/GlassCard";
import { TYPE_COLOR } from "../../lib/format";

cytoscape.use(coseBilkent as unknown as cytoscape.Ext);

interface Props {
  findings: Finding[];
  seedKey?: string | null;
  graphEdges?: Array<{ from: string; to: string; reason?: string; signal?: string }>;
}

// Stylesheet — neon nodes, color-by-type, verified ring + pulse
function buildStyle(seedKey: string | null): StylesheetStyle[] {
  return [
    {
      selector: "node",
      style: {
        "background-color": (ele: cytoscape.NodeSingular) =>
          TYPE_COLOR[(ele.data("type") as FindingType) || "person"] || "#22d3ee",
        "background-opacity": 0.18,
        "border-color": (ele: cytoscape.NodeSingular) =>
          TYPE_COLOR[(ele.data("type") as FindingType) || "person"] || "#22d3ee",
        "border-width": 2,
        "border-opacity": 0.9,
        label: "data(label)",
        color: "#e2e8f0",
        "font-family": "JetBrains Mono, ui-monospace, monospace",
        "font-size": 11,
        "text-margin-y": 14,
        "text-valign": "bottom",
        "text-halign": "center",
        "text-background-color": "#05070b",
        "text-background-opacity": 0.85,
        "text-background-padding": "3px",
        "text-background-shape": "roundrectangle",
        "text-border-color": "rgba(34,211,238,0.18)",
        "text-border-opacity": 1,
        "text-border-width": 1,
        width:  (ele: cytoscape.NodeSingular) => Math.max(20, Math.min(46, 16 + (ele.data("confidence") || 0) / 5)),
        height: (ele: cytoscape.NodeSingular) => Math.max(20, Math.min(46, 16 + (ele.data("confidence") || 0) / 5)),
        "transition-property": "background-opacity, border-width",
        "transition-duration": 200,
      },
    },
    {
      selector: "node[verified = 'true']",
      style: {
        "border-width": 3,
        "background-opacity": 0.32,
      },
    },
    {
      selector: `node[id = "${seedKey ?? "__none__"}"]`,
      style: {
        shape: "diamond",
        width: 56, height: 56,
        "border-color": "#22d3ee",
        "background-color": "#22d3ee",
        "background-opacity": 0.4,
      },
    },
    {
      selector: "node:selected",
      style: {
        "border-color": "#22d3ee",
        "border-width": 4,
      },
    },
    {
      selector: "edge",
      style: {
        width: 1.4,
        "line-color": "rgba(34,211,238,0.22)",
        "curve-style": "bezier",
        "target-arrow-shape": "triangle",
        "target-arrow-color": "rgba(34,211,238,0.35)",
        "arrow-scale": 0.8,
        opacity: 0.85,
        "transition-property": "line-color, opacity",
        "transition-duration": 200,
        // Hovering / selecting an edge shows its reason inline
        label: "data(signal)",
        color: "rgba(167,139,250,0.85)",
        "font-family": "JetBrains Mono, ui-monospace, monospace",
        "font-size": 9,
        "text-background-color": "#05070b",
        "text-background-opacity": 0.85,
        "text-background-padding": "2px",
        "text-background-shape": "roundrectangle",
        "text-opacity": 0,
      },
    },
    {
      selector: "edge:selected, edge.hover",
      style: {
        "line-color": "#22d3ee",
        "target-arrow-color": "#22d3ee",
        opacity: 1,
        "text-opacity": 1,
      } as cytoscape.Css.Edge,
    },
    {
      selector: "edge:selected",
      style: { "line-color": "#22d3ee", "target-arrow-color": "#22d3ee", opacity: 1 },
    },
  ];
}

function findingsToElements(
  findings: Finding[],
  graphEdges?: Array<{ from: string; to: string; reason?: string; signal?: string }>,
): ElementDefinition[] {
  const nodes: ElementDefinition[] = [];
  const edges: ElementDefinition[] = [];
  const ids = new Set<string>();

  for (const f of findings) {
    if (f.confidence < 25) continue;
    if (ids.has(f.key)) continue;
    ids.add(f.key);
    nodes.push({
      data: {
        id: f.key,
        label: f.value.length > 26 ? f.value.slice(0, 25) + "…" : f.value,
        type: f.type,
        confidence: f.confidence,
        verified: f.verified ? "true" : "false",
      },
    });
  }

  // Prefer the engine's edge ledger (carries the reason). Fall back to
  // walking related_to if the response doesn't include it (legacy).
  const edgeSeen = new Set<string>();
  if (graphEdges && graphEdges.length) {
    for (const e of graphEdges) {
      if (!ids.has(e.from) || !ids.has(e.to)) continue;
      const pair = [e.from, e.to].sort().join("::");
      if (edgeSeen.has(pair)) continue;
      edgeSeen.add(pair);
      edges.push({
        data: {
          id: `e-${pair}`, source: e.from, target: e.to,
          reason: e.reason || "", signal: e.signal || "",
        },
      });
    }
  } else {
    for (const f of findings) {
      if (!ids.has(f.key)) continue;
      for (const other of f.related_to) {
        if (!ids.has(other)) continue;
        const pair = [f.key, other].sort().join("::");
        if (edgeSeen.has(pair)) continue;
        edgeSeen.add(pair);
        edges.push({ data: { id: `e-${pair}`, source: f.key, target: other, reason: "", signal: "" } });
      }
    }
  }
  return [...nodes, ...edges];
}

export function IdentityGraph({ findings, seedKey, graphEdges }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [edgeTip, setEdgeTip] = useState<{ x: number; y: number; reason: string; signal: string } | null>(null);

  // Init once
  useEffect(() => {
    if (!container.current) return;
    cyRef.current = cytoscape({
      container: container.current,
      elements: findingsToElements(findings, graphEdges),
      style: buildStyle(seedKey ?? null),
      layout: { name: "cose-bilkent", animate: "end", randomize: true, nodeRepulsion: 9000, idealEdgeLength: 110 } as cytoscape.LayoutOptions,
      wheelSensitivity: 0.2,
      minZoom: 0.3,
      maxZoom: 2.4,
    });
    const cy = cyRef.current;
    cy.on("mouseover", "edge", (evt) => {
      const e = evt.target;
      e.addClass("hover");
      const pos = evt.renderedPosition || { x: 0, y: 0 };
      setEdgeTip({
        x: pos.x, y: pos.y,
        signal: e.data("signal") || "linked",
        reason: e.data("reason") || "(no recorded reason)",
      });
    });
    cy.on("mouseout", "edge", (evt) => {
      evt.target.removeClass("hover");
      setEdgeTip(null);
    });
    return () => { cyRef.current?.destroy(); cyRef.current = null; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Update graph when findings change
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.batch(() => {
      cy.elements().remove();
      cy.add(findingsToElements(findings, graphEdges));
      cy.style(buildStyle(seedKey ?? null));
    });
    cy.layout({ name: "cose-bilkent", animate: "end", randomize: false } as cytoscape.LayoutOptions).run();
  }, [findings, seedKey, graphEdges]);

  // Pulse animation on verified nodes (re-runs every 2s)
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const id = window.setInterval(() => {
      cy.nodes("[verified = 'true']").forEach((n) => {
        n.animate({ style: { "background-opacity": 0.55 } }, { duration: 350 });
        n.animate({ style: { "background-opacity": 0.32 } }, { duration: 700 });
      });
    }, 2200);
    return () => window.clearInterval(id);
  }, [findings]);

  return (
    <GlassCard padding={false} id="graph" className="h-full">
      <div className="px-5 pt-5">
        <CardHeader
          title="Identity Graph"
          hint="cross-identity correlation"
          action={
            <div className="flex items-center gap-2 text-[10px] font-mono text-slate-500">
              <span>drag · scroll to zoom · click to inspect</span>
              <button className="btn-ghost" onClick={() => cyRef.current?.fit(undefined, 50)}>fit</button>
            </div>
          }
        />
      </div>
      <div ref={container} className="cy-canvas h-[500px] rounded-b-2xl relative">
        {edgeTip && (
          <div
            className="pointer-events-none absolute z-10 px-2 py-1.5 rounded-md
                       glass-strong text-[11px] font-mono max-w-xs shadow-glow"
            style={{
              left: Math.min(Math.max(edgeTip.x + 10, 8), 580),
              top:  Math.min(Math.max(edgeTip.y + 10, 8), 460),
            }}
          >
            <div className="text-accent2 uppercase tracking-widest text-[9px] mb-0.5">
              {edgeTip.signal}
            </div>
            <div className="text-slate-200 leading-snug">{edgeTip.reason}</div>
          </div>
        )}
      </div>
    </GlassCard>
  );
}
