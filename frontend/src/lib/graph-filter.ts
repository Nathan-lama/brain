import { NodeOut, FlatEdge } from "@/hooks/use-graph-api";

export interface FilterOptions {
  selectedDomains?: Set<string> | null;
  focusNodeId?: string | null;
  focusDepth?: number;
}

export function filterGraph(
  nodes: NodeOut[],
  edges: FlatEdge[],
  options: FilterOptions
) {
  const { selectedDomains, focusNodeId, focusDepth = 1 } = options;

  // 1. Build scheme structures
  const schemeIncidentNodes = new Map<string, Set<string>>();
  const nodeIncidentSchemes = new Map<string, Set<string>>();

  // Extract all unique schemes
  const allSchemes = new Set<string>();

  for (const edge of edges) {
    const sId = edge.scheme_id;
    allSchemes.add(sId);

    if (!schemeIncidentNodes.has(sId)) {
      schemeIncidentNodes.set(sId, new Set<string>());
    }
    schemeIncidentNodes.get(sId)!.add(edge.source);
    schemeIncidentNodes.get(sId)!.add(edge.target);

    for (const nId of [edge.source, edge.target]) {
      if (!nodeIncidentSchemes.has(nId)) {
        nodeIncidentSchemes.set(nId, new Set<string>());
      }
      nodeIncidentSchemes.get(nId)!.add(sId);
    }
  }

  // 2. Compute Domain Filter visibility
  const domainVisibleNodes = new Set<string>();
  const domainVisibleSchemes = new Set<string>();

  if (selectedDomains && selectedDomains.size > 0) {
    for (const node of nodes) {
      if (selectedDomains.has(node.domain)) {
        domainVisibleNodes.add(node.id);
      }
    }
    for (const sId of allSchemes) {
      const incident = schemeIncidentNodes.get(sId);
      if (incident) {
        let allVisible = true;
        for (const nId of incident) {
          if (!domainVisibleNodes.has(nId)) {
            allVisible = false;
            break;
          }
        }
        if (allVisible) {
          domainVisibleSchemes.add(sId);
        }
      }
    }
  } else {
    // If no domain filter is selected, all nodes and schemes are visible under domain filter
    for (const node of nodes) {
      domainVisibleNodes.add(node.id);
    }
    for (const sId of allSchemes) {
      domainVisibleSchemes.add(sId);
    }
  }

  // 3. Compute Focus View Filter visibility
  if (focusNodeId) {
    const focusVisibleNodes = new Set<string>();
    const focusVisibleSchemes = new Set<string>();

    // Verify if focus node exists
    const hasFocusNode = nodes.some(n => n.id === focusNodeId);
    if (hasFocusNode) {
      const visitedNodes = new Set<string>([focusNodeId]);
      const queue: { nodeId: string; depth: number }[] = [{ nodeId: focusNodeId, depth: 0 }];

      while (queue.length > 0) {
        const curr = queue.shift()!;
        focusVisibleNodes.add(curr.nodeId);

        if (curr.depth < focusDepth) {
          const touchingSchemes = nodeIncidentSchemes.get(curr.nodeId);
          if (touchingSchemes) {
            for (const sId of touchingSchemes) {
              focusVisibleSchemes.add(sId);
              const incident = schemeIncidentNodes.get(sId);
              if (incident) {
                for (const vId of incident) {
                  if (!visitedNodes.has(vId)) {
                    visitedNodes.add(vId);
                    queue.push({ nodeId: vId, depth: curr.depth + 1 });
                  }
                }
              }
            }
          }
        }
      }
    }

    // 4. Compute Intersection
    const finalVisibleNodes = new Set<string>();
    const finalVisibleSchemes = new Set<string>();

    for (const nId of domainVisibleNodes) {
      if (focusVisibleNodes.has(nId)) {
        finalVisibleNodes.add(nId);
      }
    }
    for (const sId of domainVisibleSchemes) {
      if (focusVisibleSchemes.has(sId)) {
        finalVisibleSchemes.add(sId);
      }
    }

    return {
      visibleNodeIds: finalVisibleNodes,
      visibleSchemeIds: finalVisibleSchemes,
    };
  }

  // No focus filter active: return domain filtered sets
  return {
    visibleNodeIds: domainVisibleNodes,
    visibleSchemeIds: domainVisibleSchemes,
  };
}
