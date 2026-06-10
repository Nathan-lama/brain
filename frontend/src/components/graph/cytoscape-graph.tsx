"use client";

import React, { useEffect, useRef } from "react";
import cytoscape from "cytoscape";
import dagre from "cytoscape-dagre";

if (typeof window !== "undefined") {
  try {
    cytoscape.use(dagre);
  } catch (e) {
    // Avoid double register warnings in hot reload
  }
}

interface CytoscapeGraphProps {
  nodes: any[];
  edges: any[];
  layoutType: string;
  onNodeClick: (nodeId: string) => void;
  onEdgeClick?: (edgeId: string) => void;
}

export function CytoscapeGraph({ nodes, edges, layoutType, onNodeClick, onEdgeClick }: CytoscapeGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const cyNodes = nodes.map((n) => ({
      data: {
        id: n.id,
        label: n.text.length > 35 ? n.text.substring(0, 35) + "..." : n.text,
        type: n.type,
        confidence: n.confidence,
        domain: n.domain,
        isTension: n.isTension,
      },
    }));

    const cyEdges = edges.map((e) => ({
      data: {
        id: e.id,
        source: e.source,
        target: e.target,
        relation: e.relation,
        strength: e.strength,
      },
    }));

    const cy = cytoscape({
      container: containerRef.current,
      elements: [...cyNodes, ...cyEdges],
      boxSelectionEnabled: false,
      autoungrabify: false,
      style: [
        {
          selector: "node",
          style: {
            "background-color": (ele: any) => {
              const type = ele.data("type");
              if (type === "normatif_conclusion") return "#ec4899"; // Pink
              if (type === "normatif_position") return "#a855f7"; // Purple
              if (type === "pont_normatif") return "#f59e0b"; // Amber
              if (type === "descriptif") return "#6366f1"; // Indigo
              if (type === "empirique") return "#10b981"; // Emerald
              return "#64748b"; // Slate
            },
            label: "data(label)",
            color: "#f8fafc",
            "font-family": "var(--font-sans), sans-serif",
            "font-size": "9px",
            "font-weight": "bold",
            "text-valign": "center",
            "text-halign": "center",
            "text-wrap": "wrap",
            "text-max-width": "110px",
            width: (ele: any) => (ele.data("type") === "pont_normatif" ? "64px" : "120px"),
            height: (ele: any) => (ele.data("type") === "pont_normatif" ? "64px" : "60px"),
            shape: (ele: any) => (ele.data("type") === "pont_normatif" ? "diamond" : "round-rectangle"),
            "border-width": (ele: any) => ele.data("isTension") ? "3px" : "1.5px",
            "border-color": (ele: any) => ele.data("isTension") ? "#ef4444" : "#1e293b",
          },
        },
        {
          selector: "edge",
          style: {
            width: (ele: any) => {
              const str = ele.data("strength");
              if (str === "deductif") return 4.0;
              if (str === "defaisable_fort") return 2.5;
              return 1.5;
            },
            "line-style": (ele: any) => {
              const str = ele.data("strength");
              if (str === "defaisable_faible") return "dashed";
              return "solid";
            },
            "line-color": (ele: any) => {
              const rel = ele.data("relation");
              if (rel === "soutient") return "#10b981";
              if (rel === "contredit") return "#ef4444";
              if (rel === "implique") return "#3b82f6";
              return "#6b7280";
            },
            "target-arrow-color": (ele: any) => {
              const rel = ele.data("relation");
              if (rel === "soutient") return "#10b981";
              if (rel === "contredit") return "#ef4444";
              if (rel === "implique") return "#3b82f6";
              return "#6b7280";
            },
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(relation)",
            "font-size": "8px",
            "font-weight": "bold",
            color: "#94a3b8",
            "text-background-opacity": 0.9,
            "text-background-color": "#090d16",
            "text-background-padding": "4px",
            "text-background-shape": "roundrectangle",
            "text-margin-y": -5,
          },
        },
        {
          selector: "node:selected",
          style: {
            "border-width": "3px",
            "border-color": "#6366f1",
          },
        },
      ],
    });

    cyRef.current = cy;

    cy.on("tap", "node", (evt: any) => {
      const node = evt.target;
      onNodeClick(node.id());
    });

    cy.on("tap", "edge", (evt: any) => {
      const edge = evt.target;
      onEdgeClick?.(edge.id());
    });

    return () => {
      if (cyRef.current) {
        cyRef.current.destroy();
      }
    };
  }, [nodes, edges]);

  useEffect(() => {
    if (!cyRef.current) return;
    const layout = cyRef.current.layout({
      name: layoutType,
      animate: true,
      animationDuration: 400,
      fit: true,
      padding: 60,
      nodeDimensionsIncludeLabels: true,
      // dagre options
      nodeSep: 60,
      edgeSep: 40,
      rankSep: 120,
      rankDir: "LR", // Left-to-Right layout fits arguments beautifully
    } as any);
    layout.run();
  }, [layoutType, nodes, edges]);

  return (
    <div
      ref={containerRef}
      className="w-full h-full bg-slate-950/20 backdrop-blur-xl rounded-2xl border border-slate-900 shadow-inner"
    />
  );
}
