import { describe, it, expect } from "vitest";
import { filterGraph } from "./graph-filter";
import { NodeOut, FlatEdge } from "@/hooks/use-graph-api";

const fixtureNodes: NodeOut[] = [
  { id: "A", type: "descriptif", domain: "alpha", text: "Node A", weight: 1, created_at: "", updated_at: "" },
  { id: "B", type: "descriptif", domain: "alpha", text: "Node B", weight: 1, created_at: "", updated_at: "" },
  { id: "C", type: "descriptif", domain: "beta", text: "Node C", weight: 1, created_at: "", updated_at: "" },
  { id: "D", type: "descriptif", domain: "beta", text: "Node D", weight: 1, created_at: "", updated_at: "" }
];

const fixtureEdges: FlatEdge[] = [
  // S1: A -> B
  { id: "e1", source: "A", target: "B", relation: "soutient", scheme_id: "S1" },
  // S2: B x C
  { id: "e2", source: "B", target: "C", relation: "contredit", scheme_id: "S2" },
  // S3: C and D -> B
  { id: "e3", source: "C", target: "B", relation: "soutient", scheme_id: "S3" },
  { id: "e4", source: "D", target: "B", relation: "soutient", scheme_id: "S3" }
];

describe("Graph Filtering pure functions", () => {
  it("1. filtre domaines={alpha} -> visibles : A, B, S1", () => {
    const result = filterGraph(fixtureNodes, fixtureEdges, {
      selectedDomains: new Set(["alpha"])
    });
    expect(result.visibleNodeIds).toEqual(new Set(["A", "B"]));
    expect(result.visibleSchemeIds).toEqual(new Set(["S1"]));
  });

  it("2. filtre domaines={alpha, beta} -> tout visible", () => {
    const result = filterGraph(fixtureNodes, fixtureEdges, {
      selectedDomains: new Set(["alpha", "beta"])
    });
    expect(result.visibleNodeIds).toEqual(new Set(["A", "B", "C", "D"]));
    expect(result.visibleSchemeIds).toEqual(new Set(["S1", "S2", "S3"]));
  });

  it("3. focus sur B, profondeur 1, tous domaines -> tout visible", () => {
    const result = filterGraph(fixtureNodes, fixtureEdges, {
      focusNodeId: "B",
      focusDepth: 1
    });
    expect(result.visibleNodeIds).toEqual(new Set(["A", "B", "C", "D"]));
    expect(result.visibleSchemeIds).toEqual(new Set(["S1", "S2", "S3"]));
  });

  it("4. focus sur A, profondeur 1, tous domaines -> A, S1, B", () => {
    const result = filterGraph(fixtureNodes, fixtureEdges, {
      focusNodeId: "A",
      focusDepth: 1
    });
    expect(result.visibleNodeIds).toEqual(new Set(["A", "B"]));
    expect(result.visibleSchemeIds).toEqual(new Set(["S1"]));
  });

  it("5. focus sur A, profondeur 1, domaines={alpha} -> A, S1, B", () => {
    const result = filterGraph(fixtureNodes, fixtureEdges, {
      focusNodeId: "A",
      focusDepth: 1,
      selectedDomains: new Set(["alpha"])
    });
    expect(result.visibleNodeIds).toEqual(new Set(["A", "B"]));
    expect(result.visibleSchemeIds).toEqual(new Set(["S1"]));
  });

  it("6. focus sur A, profondeur 2 -> tout", () => {
    const result = filterGraph(fixtureNodes, fixtureEdges, {
      focusNodeId: "A",
      focusDepth: 2
    });
    expect(result.visibleNodeIds).toEqual(new Set(["A", "B", "C", "D"]));
    expect(result.visibleSchemeIds).toEqual(new Set(["S1", "S2", "S3"]));
  });

  it("7. compteur masques pour le cas 1 : 4 elements caches (C, D, S2, S3)", () => {
    const result = filterGraph(fixtureNodes, fixtureEdges, {
      selectedDomains: new Set(["alpha"])
    });
    
    // We compute hidden items count.
    // Total nodes = 4, Total schemes = 3 (S1, S2, S3)
    // Hidden nodes = 4 - result.visibleNodeIds.size = 4 - 2 = 2 (C, D)
    // Hidden schemes = 3 - result.visibleSchemeIds.size = 3 - 1 = 2 (S2, S3)
    // Total hidden = 4
    const hiddenNodesCount = fixtureNodes.length - result.visibleNodeIds.size;
    
    // To count total schemes, we extract all unique scheme_ids from fixtureEdges
    const uniqueSchemes = new Set(fixtureEdges.map(e => e.scheme_id));
    const hiddenSchemesCount = uniqueSchemes.size - result.visibleSchemeIds.size;
    const totalHidden = hiddenNodesCount + hiddenSchemesCount;
    
    expect(totalHidden).toBe(4);
  });
});
