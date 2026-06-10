"use client";

import React, { useState, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ReactFlow, Controls, Background, MarkerType } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { 
  useGraph, 
  useNode, 
  useRelated, 
  NodeType, 
  NodeOut,
  useTensions, 
  useResolveTension, 
  TensionOut,
  useEvents,
  useSnapshots,
  useSnapshotDiff,
  useRestoreSnapshot,
  useCreateSnapshot,
  TensionDiffOut,
  useSolve,
  useSolveAlternatives,
  SolveResponse,
  useDomains,
  useCreateDomain,
  useUpdateDomain,
  useDeleteDomain,
  useGenerateNote,
  useSensitivity,
  useDeleteNode,
  useUpdateNode,
  useDeleteEdge,
  useUpdateSchemeNode,
  SchemeStrength,
  useHumeValidation,
  useCommitmentDerivation,
  RelatedNodeResponse,
  NodeNeighbor,
} from "@/hooks/use-graph-api";
import { CustomGraphNode, CustomDomainGroupNode, getTierInfo } from "@/components/graph/custom-node";
import { CytoscapeGraph } from "@/components/graph/cytoscape-graph";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import {
  Brain,
  Layers,
  SlidersHorizontal,
  ChevronRight,
  Sparkles,
  Link,
  BookOpen,
  ArrowLeft,
  Info,
  AlertTriangle,
  Plus,
  RefreshCw,
  Zap,
  Trash2,
} from "lucide-react";
import LinkNext from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Custom node type registry for React Flow
const nodeTypes = {
  custom: CustomGraphNode,
  domainGroup: CustomDomainGroupNode,
};

// Layout positioning helper for React Flow
function layoutReactFlowNodes(nodes: NodeOut[]) {
  const columns: Record<string, number> = {
    descriptif: 0,
    empirique: 0,
    definitionnel: 1,
    pont_normatif: 1,
    normatif_position: 2,
    normatif_conclusion: 2,
  };

  const colWidth = 360;
  const rowHeight = 200;

  // Group nodes by their assigned column
  const groups: Record<number, NodeOut[]> = { 0: [], 1: [], 2: [] };
  nodes.forEach((node) => {
    const col = columns[node.type] ?? 0;
    groups[col].push(node);
  });

  return nodes.map((node) => {
    const col = columns[node.type] ?? 0;
    const list = groups[col];
    const index = list.findIndex((n) => n.id === node.id);

    // Calculate vertical offset to center the column
    const totalHeight = list.length * rowHeight;
    const yOffset = -totalHeight / 2 + 100;

    return {
      id: node.id,
      type: "custom",
      data: node,
      position: {
        x: col * colWidth + 50,
        y: yOffset + index * rowHeight,
      },
    };
  });
}

const RELATION_COLORS = {
  soutient: "#10b981", // Green
  contredit: "#ef4444", // Red
  implique: "#3b82f6", // Blue
  presuppose: "#6b7280", // Gray
};

export default function GraphPage() {
  const queryClient = useQueryClient();
  const [viewMode, setViewMode] = useState<"edition" | "exploration">("edition");
  const [cytoscapeLayout, setCytoscapeLayout] = useState<string>("dagre");
  const [selectedDomain, setSelectedDomain] = useState<string>("");
  const [selectedType, setSelectedType] = useState<NodeType | "">("");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState<boolean>(false);

  // Selected edge/relation state
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [edgePanelOpen, setEdgePanelOpen] = useState<boolean>(false);

  // Deletion mutations
  const deleteNodeMutation = useDeleteNode();
  const updateNodeMutation = useUpdateNode();
  const deleteEdgeMutation = useDeleteEdge();
  const updateSchemeNodeMutation = useUpdateSchemeNode();

  // Tab management (graph vs historique vs societe)
  const [activeTab, setActiveTab] = useState<"graph" | "historique" | "societe">("graph");
  const [diffDialogOpen, setDiffDialogOpen] = useState<boolean>(false);
  const [diffData, setDiffData] = useState<TensionDiffOut | null>(null);

  // Snapshot comparison selection
  const [compareFromId, setCompareFromId] = useState<string | null>(null);
  const [compareToId, setCompareToId] = useState<string | null>(null);
  const [comparisonDialogOpen, setComparisonDialogOpen] = useState<boolean>(false);

  // Create Snapshot label input
  const [newSnapshotLabel, setNewSnapshotLabel] = useState<string>("");

  // 1. Fetch graph data with current filters
  const { data: graphData, isLoading: graphLoading } = useGraph(
    selectedDomain || undefined,
    selectedType || undefined
  );

  // Snapshot comparison diff hook
  const { data: snapshotDiff, isLoading: snapshotDiffLoading } = useSnapshotDiff(compareFromId, compareToId);

  // 1b. Tensions detection states & hooks
  const [tensionsPanelOpen, setTensionsPanelOpen] = useState<boolean>(false);
  const [resolveDialogOpen, setResolveDialogOpen] = useState<boolean>(false);
  const [resolvingTension, setResolvingTension] = useState<TensionOut | null>(null);
  const [arbitrageNode, setArbitrageNode] = useState<NodeOut | null>(null);
  const [arbitrageDialogOpen, setArbitrageDialogOpen] = useState<boolean>(false);

  // Prompt 10 states
  const [domainManagerOpen, setDomainManagerOpen] = useState<boolean>(false);
  const [noteModalOpen, setNoteModalOpen] = useState<boolean>(false);
  const [generatedNoteText, setGeneratedNoteText] = useState<string>("");
  const [newDomainName, setNewDomainName] = useState<string>("");
  const [newDomainParentId, setNewDomainParentId] = useState<string>("");
  const [importExportDialogOpen, setImportExportDialogOpen] = useState<boolean>(false);
  const [importFormat, setImportFormat] = useState<"native" | "aif" | "sadface">("native");
  const [importPayloadText, setImportPayloadText] = useState<string>("");
  const [importError, setImportError] = useState<string>("");

  const { data: tensions } = useTensions();
  const { data: humeValidation } = useHumeValidation();
  const [humeViolationsExpanded, setHumeViolationsExpanded] = useState<boolean>(false);
  const { data: commitmentDerivation } = useCommitmentDerivation();
  const { data: sensitivity } = useSensitivity();
  const resolveTensionMutation = useResolveTension();

  // Prompt 10 hooks
  const { data: domains } = useDomains();
  const createDomainMutation = useCreateDomain();
  const updateDomainMutation = useUpdateDomain();
  const deleteDomainMutation = useDeleteDomain();
  const generateNoteMutation = useGenerateNote();

  // Versioning & Snapshot hooks
  const { data: events, isLoading: eventsLoading } = useEvents();
  const { data: snapshots, isLoading: snapshotsLoading } = useSnapshots();
  const restoreSnapshotMutation = useRestoreSnapshot();
  const createSnapshotMutation = useCreateSnapshot();

  // Solve / Coherence states
  const [isCoherenceActive, setIsCoherenceActive] = useState<boolean>(false);
  const [selectedSolutionIndex, setSelectedSolutionIndex] = useState<number>(0); // 0 = baseline (optimal), 1..3 = alternatives
  const [solveResult, setSolveResult] = useState<SolveResponse | null>(null);

  const solveMutation = useSolve();
  const { data: alternativesData, refetch: refetchAlternatives } = useSolveAlternatives(3);

  // Automatically re-solve coherence when graphData changes
  React.useEffect(() => {
    solveMutation.mutate(undefined, {
      onSuccess: (res) => {
        setSolveResult(res);
        if (isCoherenceActive) {
          refetchAlternatives();
        }
      }
    });
  }, [graphData, isCoherenceActive, solveMutation, refetchAlternatives]);

  const activeViolatedConstraints = useMemo(() => {
    if (!isCoherenceActive) return [];
    if (selectedSolutionIndex === 0) {
      return solveResult?.violated_constraints || [];
    } else {
      const alt = alternativesData?.find((a) => a.solution_index === selectedSolutionIndex);
      return alt?.violated_constraints || [];
    }
  }, [isCoherenceActive, selectedSolutionIndex, solveResult, alternativesData]);

  const activeArbitratedTensions = useMemo(() => {
    if (!isCoherenceActive) return [];
    if (selectedSolutionIndex === 0) {
      return solveResult?.arbitrated_tensions || [];
    } else {
      const alt = alternativesData?.find((a) => a.solution_index === selectedSolutionIndex);
      return alt?.arbitrated_tensions || [];
    }
  }, [isCoherenceActive, selectedSolutionIndex, solveResult, alternativesData]);

  const effectiveTensions = useMemo(() => {
    return tensions || [];
  }, [tensions]);

  const activeTensionsCount = useMemo(() => {
    const activeResult = selectedSolutionIndex === 0
      ? solveResult
      : alternativesData?.find((a) => a.solution_index === selectedSolutionIndex);
      
    if (!activeResult) return null;
    
    if (activeResult.incoherence_score === 0) {
      return 0;
    }
    return activeResult.violated_constraints?.length || 0;
  }, [selectedSolutionIndex, solveResult, alternativesData]);

  const tensionNodeIds = useMemo(() => {
    const ids = new Set<string>();
    if (isCoherenceActive) {
      const currentIncoherence = selectedSolutionIndex === 0
        ? (solveResult?.incoherence_score || 0)
        : (alternativesData?.find((a) => a.solution_index === selectedSolutionIndex)?.incoherence_score || 0);
      if (currentIncoherence === 0) {
        return ids;
      }
      activeViolatedConstraints.forEach((vc) => {
        vc.node_refs.forEach((ref) => ids.add(ref.id));
      });
    } else {
      if (!solveResult || solveResult.incoherence_score === 0) {
        return ids;
      }
      const baselineViolations = solveResult.violated_constraints || [];
      baselineViolations.forEach((vc) => {
        vc.node_refs.forEach((ref) => ids.add(ref.id));
      });
    }
    return ids;
  }, [isCoherenceActive, selectedSolutionIndex, solveResult, alternativesData, activeViolatedConstraints]);

  // Get accepted/rejected sets based on selection
  const currentAcceptedIds = useMemo(() => {
    if (!isCoherenceActive) return new Set<string>();
    if (selectedSolutionIndex === 0) {
      return new Set<string>(solveResult?.accepted || []);
    }
    const alt = alternativesData?.find(a => a.solution_index === selectedSolutionIndex);
    return new Set<string>(alt?.accepted || []);
  }, [isCoherenceActive, selectedSolutionIndex, solveResult, alternativesData]);

  const currentRejectedIds = useMemo(() => {
    if (!isCoherenceActive) return new Set<string>();
    if (selectedSolutionIndex === 0) {
      return new Set<string>(solveResult?.rejected || []);
    }
    const alt = alternativesData?.find(a => a.solution_index === selectedSolutionIndex);
    return new Set<string>(alt?.rejected || []);
  }, [isCoherenceActive, selectedSolutionIndex, solveResult, alternativesData]);

  // Differs with respect to baseline (solution_index = 0)
  const currentDiffIds = useMemo(() => {
    if (!isCoherenceActive || selectedSolutionIndex === 0) return new Set<string>();
    const alt = alternativesData?.find(a => a.solution_index === selectedSolutionIndex);
    if (!alt) return new Set<string>();
    const differsAccepted = alt.differs_accepted || [];
    const differsRejected = alt.differs_rejected || [];
    return new Set<string>([...differsAccepted, ...differsRejected]);
  }, [isCoherenceActive, selectedSolutionIndex, alternativesData]);

  // 2. Fetch selected node details
  const { data: nodeDetails, isLoading: detailsLoading } = useNode(selectedNodeId);

  const activeCoherence = useMemo(() => {
    if (!nodeDetails?.node) return null;
    if (!isCoherenceActive) return null;
    if (currentAcceptedIds.has(nodeDetails.node.id)) return "accepted";
    if (tensionNodeIds.has(nodeDetails.node.id)) return "tension_inevitable";
    return "rejete_arbitre";
  }, [nodeDetails, isCoherenceActive, currentAcceptedIds, tensionNodeIds]);

  // 3. Fetch semantic suggestions for selected node
  const { data: relatedClaims, isLoading: relatedLoading } = useRelated(selectedNodeId, 5);

  // Selected edge details
  const selectedEdge = useMemo(() => {
    if (!selectedEdgeId || !graphData?.edges) return null;
    return graphData.edges.find((e) => e.id === selectedEdgeId) || null;
  }, [selectedEdgeId, graphData]);

  const edgeSourceNode = useMemo(() => {
    if (!selectedEdge || !graphData?.nodes) return null;
    return graphData.nodes.find((n) => n.id === selectedEdge.source) || null;
  }, [selectedEdge, graphData]);

  const edgeTargetNode = useMemo(() => {
    if (!selectedEdge || !graphData?.nodes) return null;
    return graphData.nodes.find((n) => n.id === selectedEdge.target) || null;
  }, [selectedEdge, graphData]);

  // Extract unique domains for the filter dropdown
  const allDomains = useMemo(() => {
    if (!graphData?.nodes) return [];
    return Array.from(new Set(graphData.nodes.map((n) => n.domain)));
  }, [graphData]);

  // Map backend edges to React Flow elements
  const reactFlowEdges = useMemo(() => {
    if (!graphData?.edges) return [];
    return graphData.edges.map((e) => {
      const color =
        RELATION_COLORS[e.relation as keyof typeof RELATION_COLORS] || RELATION_COLORS.presuppose;
      
      let strokeWidth = 3;
      let strokeDasharray = undefined;

      if (e.relation === "soutient") {
        if (e.strength === "deductif") {
          strokeWidth = 5.0;
        } else if (e.strength === "defaisable_fort") {
          strokeWidth = 3.0;
        } else if (e.strength === "defaisable_faible") {
          strokeWidth = 1.5;
          strokeDasharray = "5 5";
        } else {
          // fallback
          strokeWidth = 1.5;
          strokeDasharray = "5 5";
        }
      }

      return {
        id: e.id,
        source: e.source,
        target: e.target,
        style: {
          stroke: color,
          strokeWidth: strokeWidth,
          strokeDasharray: strokeDasharray,
        },
        animated: e.relation === "soutient" || e.relation === "implique",
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: color,
          width: 15,
          height: 15,
        },
      };
    });
  }, [graphData]);

  // Layout and map backend nodes for React Flow
  const reactFlowNodes = useMemo(() => {
    if (!graphData?.nodes) return [];
    const laidOut = layoutReactFlowNodes(graphData.nodes);
    return laidOut.map((n) => {
      const isAccepted = currentAcceptedIds.has(n.id);
      const isRejected = currentRejectedIds.has(n.id);
      const isTension = tensionNodeIds.has(n.id);

      let coherence = n.data?.coherence;
      if (isCoherenceActive) {
        if (isAccepted) {
          coherence = "accepted";
        } else if (isTension) {
          coherence = "tension_inevitable";
        } else {
          coherence = "rejete_arbitre";
        }
      }

      const derivationItem = commitmentDerivation?.results.find((r) => r.node_id === n.id);
      const overcommitted = derivationItem?.overcommitted ?? false;
      const gap = derivationItem?.gap ?? null;

      return {
        ...n,
        data: {
          ...n.data,
          coherence,
          isTension,
          isCoherenceActive,
          isAccepted,
          isRejected,
          isDiff: currentDiffIds.has(n.id),
          overcommitted,
          gap,
        },
      };
    });
  }, [graphData, tensionNodeIds, isCoherenceActive, currentAcceptedIds, currentRejectedIds, currentDiffIds, commitmentDerivation]);

  const cytoscapeNodes = useMemo(() => {
    if (!graphData?.nodes) return [];
    return graphData.nodes.map((n) => {
      const isAccepted = currentAcceptedIds.has(n.id);
      const isRejected = currentRejectedIds.has(n.id);
      const isTension = tensionNodeIds.has(n.id);

      let coherence = n.coherence;
      if (isCoherenceActive) {
        if (isAccepted) {
          coherence = "accepted";
        } else if (isTension) {
          coherence = "tension_inevitable";
        } else {
          coherence = "rejete_arbitre";
        }
      }

      return {
        ...n,
        coherence,
        isTension,
        isCoherenceActive,
        isAccepted,
        isRejected,
        isDiff: currentDiffIds.has(n.id),
      };
    });
  }, [graphData, tensionNodeIds, isCoherenceActive, currentAcceptedIds, currentRejectedIds, currentDiffIds]);

  // Layout and group nodes for the "Société" tab (parent/child group nodes)
  const domainGroups = useMemo(() => {
    if (!graphData?.nodes || !domains) return [];
    const uniqueDomains = Array.from(new Set(graphData.nodes.map((n) => n.domain)));

    interface DomainGroupNode {
      id: string;
      type: string;
      data: { label: string };
      position: { x: number; y: number };
      style: { width: number; height: number };
    }

    const groups: DomainGroupNode[] = [];
    uniqueDomains.forEach((domName, domIdx) => {
      const domNodes = graphData.nodes.filter((n) => n.domain === domName);
      if (domNodes.length === 0) return;

      const domObj = domains.find((d) => d.name === domName);
      const domId = domObj?.id || domName;

      const width = 300;
      const height = 40 + domNodes.length * 190 + 30;

      const col = domIdx % 3;
      const row = Math.floor(domIdx / 3);

      groups.push({
        id: domId,
        type: "domainGroup",
        data: { label: domName },
        position: { x: col * 360 + 50, y: row * 600 + 50 },
        style: { width, height },
      });
    });
    return groups;
  }, [graphData, domains]);

  const societeNodes = useMemo(() => {
    if (!graphData?.nodes || !domains) return [];
    return graphData.nodes.map((n) => {
      const domObj = domains.find((d) => d.name === n.domain);
      const parentId = domObj?.id || n.domain;

      const domNodes = graphData.nodes.filter((dn) => dn.domain === n.domain);
      const index = domNodes.findIndex((dn) => dn.id === n.id);

      const isAccepted = currentAcceptedIds.has(n.id);
      const isRejected = currentRejectedIds.has(n.id);
      const isTension = tensionNodeIds.has(n.id);

      let coherence = n.coherence;
      if (isCoherenceActive) {
        if (isAccepted) {
          coherence = "accepted";
        } else if (isTension) {
          coherence = "tension_inevitable";
        } else {
          coherence = "rejete_arbitre";
        }
      }

      const derivationItem = commitmentDerivation?.results.find((r) => r.node_id === n.id);
      const overcommitted = derivationItem?.overcommitted ?? false;
      const gap = derivationItem?.gap ?? null;

      return {
        id: n.id,
        type: "custom",
        data: {
          ...n,
          coherence,
          isTension,
          isCoherenceActive,
          isAccepted,
          isRejected,
          isDiff: currentDiffIds.has(n.id),
          overcommitted,
          gap,
        },
        parentId,
        extent: "parent" as const,
        position: { x: 20, y: 40 + index * 190 },
      };
    });
  }, [graphData, domains, tensionNodeIds, isCoherenceActive, currentAcceptedIds, currentRejectedIds, currentDiffIds, commitmentDerivation]);

  const allSocieteNodes = useMemo(() => [...domainGroups, ...societeNodes], [domainGroups, societeNodes]);

  const handleNodeClick = (nodeId: string) => {
    setSelectedNodeId(nodeId);
    setPanelOpen(true);
  };

  const handleEdgeClick = (edgeId: string) => {
    setSelectedEdgeId(edgeId);
    setEdgePanelOpen(true);
  };

  const handleDeleteNode = async (nodeId: string) => {
    if (window.confirm("Voulez-vous vraiment supprimer cette thèse ? Cette action supprimera également toutes les relations qui y sont connectées.")) {
      try {
        await deleteNodeMutation.mutateAsync(nodeId);
        setPanelOpen(false);
        setSelectedNodeId(null);
      } catch (err) {
        alert("Erreur lors de la suppression de la thèse : " + (err as Error).message);
      }
    }
  };

  const handleDeleteEdge = async (schemeId: string) => {
    if (window.confirm("Voulez-vous vraiment supprimer cette relation ?")) {
      try {
        await deleteEdgeMutation.mutateAsync(schemeId);
        setEdgePanelOpen(false);
        setSelectedEdgeId(null);
      } catch (err) {
        alert("Erreur lors de la suppression de la relation : " + (err as Error).message);
      }
    }
  };

  const handleUpdateSchemeStrength = async (schemeId: string, strength: SchemeStrength) => {
    try {
      await updateSchemeNodeMutation.mutateAsync({ id: schemeId, payload: { strength } });
    } catch (err) {
      alert("Erreur lors de la modification de la force de l'inférence : " + (err as Error).message);
    }
  };

  const handleSuggestionClick = (nodeId: string) => {
    setSelectedNodeId(nodeId);
  };

  // Render Historique Tab Content
  const renderHistoriqueView = () => {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 text-slate-100">
        {/* Left Side: Snapshots (5 cols) */}
        <div className="lg:col-span-5 space-y-6">
          <div className="bg-slate-900/40 border border-slate-900 rounded-2xl p-5 space-y-4">
            <h3 className="font-heading font-bold text-base text-slate-100 flex items-center gap-2">
              📸 Belief Snapshots
            </h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Enregistrez l&apos;état actuel de votre Second Brain pour pouvoir le comparer ou y revenir à tout moment.
            </p>
            
            {/* Create Snapshot Form */}
            <div className="flex gap-2 pt-2">
              <input
                type="text"
                value={newSnapshotLabel}
                onChange={(e) => setNewSnapshotLabel(e.target.value)}
                placeholder="Nom du snapshot (ex: Version Seed)"
                className="flex-1 bg-slate-950 border border-slate-800 text-xs rounded-xl px-3.5 py-2.5 text-slate-200 outline-none focus:border-indigo-500 transition-colors"
              />
              <Button
                onClick={async () => {
                  if (!newSnapshotLabel.trim()) return;
                  try {
                    await createSnapshotMutation.mutateAsync(newSnapshotLabel);
                    setNewSnapshotLabel("");
                  } catch (e) {
                    console.error(e);
                  }
                }}
                disabled={createSnapshotMutation.isPending}
                className="bg-indigo-600 hover:bg-indigo-500 hover:border-indigo-500/50 text-white rounded-xl text-xs font-semibold px-4 cursor-pointer flex items-center gap-1.5 h-10 border border-transparent"
              >
                <Plus className="w-4 h-4" />
                <span>Créer</span>
              </Button>
            </div>
          </div>

          {/* Snapshots Timeline List */}
          <div className="space-y-3">
            <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
              Snapshots Enregistrés
            </h4>
            
            {snapshotsLoading ? (
              <div className="flex items-center gap-2 text-slate-500 text-xs py-4">
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Chargement des snapshots...</span>
              </div>
            ) : !snapshots || snapshots.length === 0 ? (
              <p className="text-xs text-slate-500 italic py-4">Aucun snapshot créé pour le moment.</p>
            ) : (
              <div className="space-y-3">
                {snapshots.map((snap) => {
                  const isFrom = compareFromId === snap.id;
                  const isTo = compareToId === snap.id;
                  return (
                    <div
                      key={snap.id}
                      className="p-4 rounded-xl border border-slate-900 bg-slate-900/20 flex flex-col justify-between gap-4 sm:flex-row sm:items-center"
                    >
                      <div className="space-y-1">
                        <span className="text-xs font-bold text-slate-200 block">{snap.label}</span>
                        <span className="text-[10px] text-slate-500">
                          Créé le {new Date(snap.created_at).toLocaleString()}
                        </span>
                      </div>
                      
                      <div className="flex flex-wrap gap-2">
                        {/* Compare Toggles */}
                        <Button
                          onClick={() => {
                            if (isFrom) {
                              setCompareFromId(null);
                            } else {
                              setCompareFromId(snap.id);
                            }
                          }}
                          className={`text-[10px] font-semibold px-2.5 py-1.5 rounded-lg border cursor-pointer h-8 ${
                            isFrom
                              ? "bg-indigo-600 text-white border-indigo-500"
                              : "bg-slate-900 text-slate-300 border-slate-800 hover:text-white"
                          }`}
                        >
                          De (From)
                        </Button>
                        <Button
                          onClick={() => {
                            if (isTo) {
                              setCompareToId(null);
                            } else {
                              setCompareToId(snap.id);
                            }
                          }}
                          className={`text-[10px] font-semibold px-2.5 py-1.5 rounded-lg border cursor-pointer h-8 ${
                            isTo
                              ? "bg-indigo-600 text-white border-indigo-500"
                              : "bg-slate-900 text-slate-300 border-slate-800 hover:text-white"
                          }`}
                        >
                          Vers (To)
                        </Button>

                        {/* Restore Button */}
                        <Button
                          onClick={async () => {
                            if (confirm(`Restaurer le graphe à l'état "${snap.label}" ?`)) {
                              await restoreSnapshotMutation.mutateAsync(snap.id);
                            }
                          }}
                          disabled={restoreSnapshotMutation.isPending}
                          className="bg-emerald-950/20 border border-emerald-800/30 hover:border-emerald-500/50 text-emerald-400 text-[10px] font-bold rounded-lg px-2.5 py-1.5 cursor-pointer h-8"
                        >
                          Restaurer
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Compare Trigger Card */}
            {compareFromId && compareToId && (
              <div className="mt-4 p-4 rounded-xl bg-indigo-950/10 border border-indigo-500/30 flex items-center justify-between gap-4">
                <span className="text-xs text-indigo-300 font-semibold">
                  Comparer {snapshots?.find(s => s.id === compareFromId)?.label} ➜ {snapshots?.find(s => s.id === compareToId)?.label}
                </span>
                <Button
                  onClick={() => setComparisonDialogOpen(true)}
                  className="bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold rounded-lg px-3.5 py-2 cursor-pointer flex items-center gap-1"
                >
                  <span>Lancer le Diff</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* Right Side: Event Logs Timeline (7 cols) */}
        <div className="lg:col-span-7 space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="font-heading font-bold text-base text-slate-100 flex items-center gap-2">
              📜 Journal d&apos;Événements (Git-like)
            </h3>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-900 border border-slate-800 text-slate-400 font-bold uppercase tracking-wider">
              Append-Only
            </span>
          </div>

          <div className="space-y-4 max-h-[600px] overflow-y-auto pr-2">
            {eventsLoading ? (
              <div className="flex items-center gap-2 text-slate-500 text-xs py-4">
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Chargement des événements...</span>
              </div>
            ) : !events || events.length === 0 ? (
              <p className="text-xs text-slate-500 italic py-4">Aucun événement loggé dans l&apos;historique.</p>
            ) : (
              <div className="relative border-l border-slate-800/80 ml-3 pl-6 space-y-5">
                {events.map((event) => {
                  let opColor = "text-indigo-400 bg-indigo-950/40 border-indigo-900/30";
                  const opText = event.op.toUpperCase();
                  if (event.op === "create") {
                    opColor = "text-emerald-400 bg-emerald-950/40 border-emerald-900/30";
                  } else if (event.op === "delete") {
                    opColor = "text-rose-400 bg-rose-950/40 border-rose-900/30";
                  }
                  
                  const targetEntity = event.after || event.before || {};
                  const titleText = targetEntity.text || targetEntity.scheme || `Lien ${targetEntity.role || ""}`;

                  return (
                    <div key={event.id} className="relative group">
                      {/* Timeline dot */}
                      <span className="absolute -left-[30px] top-1.5 flex h-2.5 w-2.5 items-center justify-center rounded-full bg-slate-800 ring-4 ring-slate-950 group-hover:bg-indigo-500 transition-colors" />
                      
                      <div className="p-4 rounded-xl border border-slate-900/80 bg-slate-900/10 hover:border-slate-800 hover:bg-slate-900/20 transition-all space-y-3">
                        <div className="flex flex-wrap items-center justify-between gap-2 text-[10px]">
                          <div className="flex items-center gap-2">
                            <span className={`font-mono font-bold px-2 py-0.5 rounded border ${opColor}`}>
                              {opText}
                            </span>
                            <span className="text-slate-500 font-bold uppercase tracking-wider">
                              {event.entity_type}
                            </span>
                          </div>
                          <span className="text-slate-500">
                            {new Date(event.created_at).toLocaleString()}
                          </span>
                        </div>

                        <div className="space-y-1.5">
                          <span className="text-xs font-semibold text-slate-200 block line-clamp-1 leading-relaxed">
                            {titleText}
                          </span>
                          
                          {/* Diff changes details */}
                          {event.op === "update" && event.before && event.after && (
                            <div className="text-[10px] text-slate-400 font-mono space-y-0.5 bg-slate-950/40 p-2 rounded-lg border border-slate-900/40">
                              {(event.before.tier !== event.after.tier || event.before.confidence !== event.after.confidence) && (
                                <div>
                                  <span className="text-rose-400 font-semibold">- Tier: {getTierInfo(event.before.tier, (event.before.weight || event.before.confidence) ?? undefined).label}</span>
                                  <span className="text-emerald-400 font-semibold block">+ Tier: {getTierInfo(event.after.tier, (event.after.weight || event.after.confidence) ?? undefined).label}</span>
                                </div>
                              )}
                              {event.before.metadata?.paradoxe_assume !== event.after.metadata?.paradoxe_assume && (
                                <div>
                                  <span className="text-rose-400 font-semibold">- Paradoxe: {String(!!event.before.metadata?.paradoxe_assume)}</span>
                                  <span className="text-emerald-400 font-semibold block">+ Paradoxe: {String(!!event.after.metadata?.paradoxe_assume)}</span>
                                </div>
                              )}
                              {event.before.text !== event.after.text && (
                                <div>
                                  <span className="text-rose-400 font-semibold block truncate">- Texte: &quot;{event.before.text}&quot;</span>
                                  <span className="text-emerald-400 font-semibold block truncate">+ Texte: &quot;{event.after.text}&quot;</span>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  // Snapshot Diff Component (embedded inside page.tsx or as modal)
  const renderSnapshotDiffModal = () => {
    const diff = snapshotDiff;
    const isLoading = snapshotDiffLoading;

    if (!comparisonDialogOpen) return null;

    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-4">
        <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 shadow-2xl space-y-5 flex flex-col max-h-[85vh]">
          <div>
            <h4 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              📊 Comparaison de croyances (Beliefs Diff)
            </h4>
            <p className="text-slate-400 text-xs mt-1">
              Comparaison structurelle et logique des croyances.
            </p>
          </div>

          <div className="flex-1 overflow-y-auto space-y-4 pr-1 text-slate-300">
            {isLoading ? (
              <div className="flex flex-col items-center justify-center py-12 gap-2 text-slate-500">
                <RefreshCw className="animate-spin w-8 h-8 text-indigo-500" />
                <span className="text-xs font-semibold">Calcul du diff en mémoire...</span>
              </div>
            ) : !diff ? (
              <p className="text-xs text-slate-500">Aucune donnée de comparaison disponible.</p>
            ) : (
              <div className="space-y-4">
                {/* Structural Claims Changes */}
                <div className="space-y-2.5">
                  <h5 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
                    Changements Structurels (Claims)
                  </h5>
                  
                  {/* Added Claims */}
                  {diff.claims_ajoutes.length > 0 && (
                    <div className="p-3.5 rounded-xl border border-emerald-900/30 bg-emerald-950/5 text-xs">
                      <span className="font-bold text-emerald-400 block mb-1">Ajoutés (+{diff.claims_ajoutes.length})</span>
                      <ul className="list-disc list-inside space-y-1 text-slate-300">
                        {diff.claims_ajoutes.map(c => (
                          <li key={c.id} className="text-[11px] truncate">
                            {c.text} <span className="text-slate-500 font-bold">({c.domain})</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Deleted Claims */}
                  {diff.claims_supprimes.length > 0 && (
                    <div className="p-3.5 rounded-xl border border-rose-900/30 bg-rose-950/5 text-xs">
                      <span className="font-bold text-rose-400 block mb-1">Supprimés (-{diff.claims_supprimes.length})</span>
                      <ul className="list-disc list-inside space-y-1 text-slate-300">
                        {diff.claims_supprimes.map(c => (
                          <li key={c.id} className="text-[11px] truncate">
                            {c.text}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Modified Claims */}
                  {diff.claims_modifies.length > 0 && (
                    <div className="p-3.5 rounded-xl border border-blue-900/30 bg-blue-950/5 text-xs">
                      <span className="font-bold text-blue-400 block mb-1">Modifiés ({diff.claims_modifies.length})</span>
                      <ul className="list-disc list-inside space-y-1 text-slate-300">
                        {diff.claims_modifies.map(c => (
                          <li key={c.id} className="text-[11px] truncate">
                            {c.text} <span className="text-slate-500 font-bold">({getTierInfo(c.tier ?? undefined, c.weight ?? undefined).label})</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {diff.claims_ajoutes.length === 0 && diff.claims_supprimes.length === 0 && diff.claims_modifies.length === 0 && (
                    <p className="text-xs text-slate-500 italic">Aucune modification structurelle sur les claims.</p>
                  )}
                </div>

                {/* Edges Changes */}
                <div className="space-y-2.5">
                  <h5 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
                    Changements de Liaisons (Edges)
                  </h5>
                  {diff.edges_ajoutes.length > 0 && (
                    <div className="text-xs text-emerald-400 font-medium">
                      + {diff.edges_ajoutes.length} nouvelles relations créées
                    </div>
                  )}
                  {diff.edges_supprimes.length > 0 && (
                    <div className="text-xs text-rose-400 font-medium">
                      - {diff.edges_supprimes.length} relations supprimées
                    </div>
                  )}
                  {diff.edges_ajoutes.length === 0 && diff.edges_supprimes.length === 0 && (
                    <p className="text-xs text-slate-500 italic">Aucune modification de liaison.</p>
                  )}
                </div>

                {/* Delta of Tensions */}
                <div className="space-y-2.5">
                  <h5 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
                    Changements Logiques (Tensions)
                  </h5>
                  {/* Tensions Resolues */}
                  {diff.tensions_resolues.length > 0 && (
                    <div className="p-3.5 rounded-xl border border-emerald-900/30 bg-emerald-950/5 text-xs">
                      <span className="font-bold text-emerald-400 block mb-1">Tensions Résolues ({diff.tensions_resolues.length})</span>
                      <ul className="list-disc list-inside space-y-1 text-slate-300">
                        {diff.tensions_resolues.map(t => (
                          <li key={t.id} className="text-[11px] truncate">
                            {t.type === "conflit_direct" ? "Conflit Direct" : "Cycle Incohérent"} : {t.claims.map(c => c.text).join(" VS ")}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Tensions Nouvelles */}
                  {diff.tensions_nouvelles.length > 0 && (
                    <div className="p-3.5 rounded-xl border border-amber-900/30 bg-amber-950/5 text-xs">
                      <span className="font-bold text-amber-400 block mb-1">Nouvelles Tensions Apparues ({diff.tensions_nouvelles.length})</span>
                      <ul className="list-disc list-inside space-y-1 text-slate-300">
                        {diff.tensions_nouvelles.map(t => (
                          <li key={t.id} className="text-[11px] truncate">
                            {t.type === "conflit_direct" ? "Conflit Direct" : "Cycle Incohérent"} : {t.claims.map(c => c.text).join(" VS ")}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {diff.tensions_resolues.length === 0 && diff.tensions_nouvelles.length === 0 && (
                    <p className="text-xs text-slate-500 italic">Aucune tension résolue ou créée.</p>
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="flex justify-between items-center pt-3 border-t border-slate-800">
            <Button
              onClick={() => {
                setCompareFromId(null);
                setCompareToId(null);
                setComparisonDialogOpen(false);
              }}
              className="bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-800 px-4 py-2 rounded-lg text-xs"
            >
              Réinitialiser la sélection
            </Button>
            <Button
              onClick={() => setComparisonDialogOpen(false)}
              className="bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2 rounded-lg text-xs font-semibold cursor-pointer border border-transparent h-9"
            >
              Fermer
            </Button>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="relative min-h-screen w-full bg-slate-950 text-slate-100 flex flex-col justify-between selection:bg-indigo-500 selection:text-white">
      {/* Background gradients */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(99,102,241,0.04),transparent_50%),radial-gradient(circle_at_bottom_left,rgba(168,85,247,0.03),transparent_50%)] pointer-events-none" />

      {/* Top Navbar */}
      <header className="border-b border-slate-900 bg-slate-950/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <LinkNext href="/">
              <Button
                variant="ghost"
                size="icon-sm"
                className="text-slate-400 hover:text-slate-200 cursor-pointer"
              >
                <ArrowLeft className="w-4 h-4" />
              </Button>
            </LinkNext>
            <div className="flex items-center gap-2.5">
              <div className="relative flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 shadow-md shadow-indigo-500/20">
                <Brain className="w-4.5 h-4.5 text-white" />
              </div>
              <span className="font-semibold tracking-tight text-base bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-200 to-slate-400">
                Graphe de Cohérence
              </span>
            </div>
          </div>

          {/* View Toggles & Layout Options */}
          <div className="flex items-center gap-3 animate-fade-in">
            {/* Indication d'Equilibre Reflechi */}
            <Button
              onClick={() => setTensionsPanelOpen(true)}
              variant="ghost"
              className={`flex items-center gap-1.5 rounded-lg text-xs font-semibold px-3 py-1.5 border transition-all cursor-pointer h-9 ${
                activeTensionsCount === null
                  ? "bg-slate-900 border-slate-800 text-slate-400 hover:bg-slate-800"
                  : activeTensionsCount > 0
                    ? "bg-red-950/20 border-red-500/30 text-red-400 hover:bg-red-900/30 hover:border-red-400/50"
                    : "bg-emerald-950/20 border-emerald-500/30 text-emerald-400 hover:bg-emerald-900/30 hover:border-emerald-400/50"
              }`}
            >
              {activeTensionsCount === null ? (
                <span className="text-slate-400 text-xs">—</span>
              ) : activeTensionsCount > 0 ? (
                <AlertTriangle className="w-3.5 h-3.5 animate-pulse" />
              ) : (
                <span className="text-sm">⚖️</span>
              )}
              <span>Tensions : {activeTensionsCount !== null ? activeTensionsCount : "—"}</span>
            </Button>

            <div
              className={`flex items-center gap-1.5 rounded-lg text-xs font-semibold px-3 py-1.5 border transition-all h-9 ${
                commitmentDerivation && commitmentDerivation.count_overcommitted > 0
                  ? "bg-amber-950/20 border-amber-500/30 text-amber-400"
                  : "bg-slate-900 border-slate-800 text-slate-400"
              }`}
            >
              {commitmentDerivation && commitmentDerivation.count_overcommitted > 0 ? (
                <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
              ) : (
                <span className="text-slate-400 text-xs">—</span>
              )}
              <span>Sur-engagements : {commitmentDerivation ? commitmentDerivation.count_overcommitted : "—"}</span>
            </div>

            {/* Mode Cohérence Toggle Button */}
            <Button
              onClick={async () => {
                if (!isCoherenceActive) {
                  try {
                    const res = await solveMutation.mutateAsync();
                    setSolveResult(res);
                    setIsCoherenceActive(true);
                    setSelectedSolutionIndex(0);
                    setActiveTab("graph");
                    refetchAlternatives();
                  } catch (err) {
                    console.error("Solver error:", err);
                  }
                } else {
                  setIsCoherenceActive(false);
                }
              }}
              variant="outline"
              className={`flex items-center gap-1.5 rounded-lg text-xs font-semibold px-3 py-1.5 border transition-all cursor-pointer h-9 ${
                isCoherenceActive
                  ? "bg-indigo-600 border-indigo-500 text-white hover:bg-indigo-500 hover:text-white"
                  : "bg-slate-900 border-slate-800 text-slate-300 hover:text-white"
              }`}
            >
              <span>⚖️ Cohérence</span>
            </Button>

            {/* Causal Network Link Button */}
            <LinkNext href="/causal">
              <Button
                variant="outline"
                className="flex items-center gap-1.5 rounded-lg text-xs font-semibold px-3 py-1.5 border border-slate-800 bg-slate-900 text-slate-300 hover:text-white cursor-pointer h-9"
              >
                <Zap className="w-3.5 h-3.5 text-purple-400" />
                <span>Réseau Causal</span>
              </Button>
            </LinkNext>

            {/* Export / Import Button */}
            <Button
              onClick={() => {
                setImportPayloadText("");
                setImportError("");
                setImportExportDialogOpen(true);
              }}
              variant="outline"
              className="flex items-center gap-1.5 rounded-lg text-xs font-semibold px-3 py-1.5 border border-slate-800 bg-slate-900 text-slate-300 hover:text-white cursor-pointer h-9"
            >
              <span>Import/Export</span>
            </Button>

            {/* Note de Synthese Button */}
            <Button
              onClick={() => {
                setGeneratedNoteText("");
                setNoteModalOpen(true);
              }}
              variant="outline"
              className="flex items-center gap-1.5 rounded-lg text-xs font-semibold px-3 py-1.5 border border-slate-800 bg-slate-900 text-slate-300 hover:text-white cursor-pointer h-9"
            >
              <span>Générer Note</span>
            </Button>

            {/* Gestionnaire de Domaines Button */}
            <Button
              onClick={() => setDomainManagerOpen(true)}
              variant="outline"
              className="flex items-center gap-1.5 rounded-lg text-xs font-semibold px-3 py-1.5 border border-slate-800 bg-slate-900 text-slate-300 hover:text-white cursor-pointer h-9"
            >
              <span>Branches (Domaines)</span>
            </Button>

            <div className="flex items-center p-0.5 rounded-lg bg-slate-900 border border-slate-800 text-xs">
              <button
                onClick={() => {
                  setActiveTab("graph");
                  setViewMode("edition");
                }}
                className={`px-3 py-1.5 rounded-md font-medium transition-colors cursor-pointer ${
                  activeTab === "graph" && viewMode === "edition"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Édition (React Flow)
              </button>
              <button
                onClick={() => {
                  setActiveTab("graph");
                  setViewMode("exploration");
                }}
                className={`px-3 py-1.5 rounded-md font-medium transition-colors cursor-pointer ${
                  activeTab === "graph" && viewMode === "exploration"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Exploration (Cytoscape)
              </button>
              <button
                onClick={() => setActiveTab("societe")}
                className={`px-3 py-1.5 rounded-md font-medium transition-colors cursor-pointer ${
                  activeTab === "societe"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Société (Clusters)
              </button>
              <button
                onClick={() => setActiveTab("historique")}
                className={`px-3 py-1.5 rounded-md font-medium transition-colors cursor-pointer ${
                  activeTab === "historique"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Historique (Snapshot/Events)
              </button>
            </div>

            {activeTab === "graph" && viewMode === "exploration" && (
              <div className="flex items-center gap-2 border-l border-slate-800 pl-3">
                <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                  Layout:
                </span>
                <select
                  value={cytoscapeLayout}
                  onChange={(e) => setCytoscapeLayout(e.target.value)}
                  className="bg-slate-900 border border-slate-800 text-slate-300 text-xs rounded-lg px-2.5 py-1.5 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 outline-none"
                >
                  <option value="dagre">Hiérarchique (Dagre)</option>
                  <option value="cose">Force-Directed (Cose)</option>
                  <option value="concentric">Concentrique</option>
                </select>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Control Bar & Filters (hidden on Historique tab) */}
      {(activeTab === "graph" || activeTab === "societe") && (
        <section className="border-b border-slate-900 bg-slate-950/40 backdrop-blur-xs py-3 px-6">
          <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap items-center gap-4">
              <div className="flex items-center gap-2 text-slate-400 text-xs font-semibold uppercase tracking-wider">
                <SlidersHorizontal className="w-3.5 h-3.5 text-indigo-400" />
                Filtres :
              </div>

              {/* Domain Filter */}
              <select
                value={selectedDomain}
                onChange={(e) => setSelectedDomain(e.target.value)}
                className="bg-slate-900 border border-slate-800 text-slate-300 text-xs rounded-lg px-3 py-1.5 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 outline-none min-w-36"
              >
                <option value="">Tous les Domaines</option>
                {allDomains.map((dom) => (
                  <option key={dom} value={dom}>
                    {dom.charAt(0).toUpperCase() + dom.slice(1)}
                  </option>
                ))}
              </select>

              {/* Type Filter */}
              <select
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value as NodeType | "")}
                className="bg-slate-900 border border-slate-800 text-slate-300 text-xs rounded-lg px-3 py-1.5 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 outline-none min-w-36"
              >
                <option value="">Tous les Types</option>
                <option value="descriptif">Descriptif</option>
                <option value="empirique">Empirique</option>
                <option value="normatif_position">Normatif Position</option>
                <option value="normatif_conclusion">Normatif Conclusion</option>
                <option value="pont_normatif">Pont Normatif</option>
                <option value="definitionnel">Définitionnel</option>
              </select>
            </div>

            {/* Legend */}
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-[10px] text-slate-400 font-semibold bg-slate-900/40 border border-slate-800/60 rounded-xl px-4 py-2">
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded bg-emerald-500 inline-block" />
                <span>Soutient</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded bg-rose-500 inline-block" />
                <span>Contredit</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded bg-blue-500 inline-block" />
                <span>Implique</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded bg-slate-500 inline-block" />
                <span>Présuppose</span>
              </div>
              <div className="border-l border-slate-800 pl-4 flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 bg-amber-500/20 border border-amber-500 rotate-45 inline-block" />
                <span className="text-amber-400">Pont Normatif</span>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Main Viewport */}
      <main className={`flex-1 w-full ${activeTab === "historique" ? "overflow-y-auto py-8 px-6 max-w-7xl mx-auto space-y-8" : "h-[calc(100vh-10rem)] relative overflow-hidden"}`}>
        {activeTab === "historique" ? (
          renderHistoriqueView()
        ) : graphLoading ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-slate-950/80 backdrop-blur-xs z-10">
            <span className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500" />
            <span className="text-slate-400 text-xs font-semibold uppercase tracking-wider">
              Chargement du Graphe...
            </span>
          </div>
        ) : graphData?.nodes.length === 0 ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-slate-500 z-10">
            <Info className="w-8 h-8 text-slate-600 mb-1" />
            <span className="font-semibold text-sm">Aucun élément ne correspond aux filtres.</span>
            <span className="text-xs">Modifiez les filtres de domaine ou de type.</span>
          </div>
        ) : activeTab === "societe" ? (
          <div className="absolute inset-0">
            <ReactFlow
              nodes={allSocieteNodes}
              edges={reactFlowEdges}
              nodeTypes={nodeTypes}
              fitView
              onNodeClick={(_, node) => {
                if (node.type !== "domainGroup") {
                  handleNodeClick(node.id);
                }
              }}
              onEdgeClick={(_, edge) => handleEdgeClick(edge.id)}
              minZoom={0.2}
              maxZoom={1.5}
            >
              <Background color="#1e293b" gap={20} size={1} />
              <Controls className="!bg-slate-900 !border-slate-800 !text-slate-300" />
            </ReactFlow>
          </div>
        ) : viewMode === "edition" ? (
          <div className="absolute inset-0">
            <ReactFlow
              nodes={reactFlowNodes}
              edges={reactFlowEdges}
              nodeTypes={nodeTypes}
              fitView
              onNodeClick={(_, node) => handleNodeClick(node.id)}
              onEdgeClick={(_, edge) => handleEdgeClick(edge.id)}
              minZoom={0.2}
              maxZoom={1.5}
            >
              <Background color="#1e293b" gap={20} size={1} />
              <Controls className="!bg-slate-900 !border-slate-800 !text-slate-300" />
            </ReactFlow>
          </div>
        ) : (
          <div className="absolute inset-0 p-6">
            <CytoscapeGraph
              nodes={cytoscapeNodes}
              edges={graphData?.edges || []}
              layoutType={cytoscapeLayout}
              onNodeClick={handleNodeClick}
              onEdgeClick={handleEdgeClick}
            />
          </div>
        )}

        {/* Floating Coherence Panel */}
        {activeTab === "graph" && isCoherenceActive && solveResult && (
          <div className="absolute right-6 top-6 bottom-6 w-96 bg-slate-950/90 backdrop-blur-md border border-slate-900 rounded-2xl p-5 shadow-2xl flex flex-col justify-between z-40 overflow-hidden">
            {/* Header */}
            <div className="border-b border-slate-900 pb-4 mb-4">
              <h3 className="text-sm font-bold text-slate-100 flex items-center gap-1.5">
                ⚖️ Solveur de Cohérence
              </h3>
              <p className="text-[10px] text-slate-400 mt-1 leading-relaxed">
                Le solveur MAX-SAT CP-SAT optimise la cohérence logique globale de vos croyances en arbitrant les conflits.
              </p>
            </div>

            {/* Scrollable Content */}
            <div className="flex-1 overflow-y-auto space-y-4 pr-1">
              {/* Hume's Law Warning Banner */}
              {humeValidation && humeValidation.count > 0 && (
                <div className="p-3 bg-amber-950/20 border border-amber-500/20 rounded-xl space-y-2 text-xs">
                  <button
                    onClick={() => setHumeViolationsExpanded(!humeViolationsExpanded)}
                    className="flex items-center justify-between w-full text-amber-400 font-semibold cursor-pointer hover:text-amber-300 outline-none text-[11px]"
                  >
                    <span className="flex items-center gap-1.5">
                      <AlertTriangle className="w-3.5 h-3.5 animate-pulse text-amber-500" />
                      <span>⚠ {humeValidation.count} inférence(s) violent la loi de Hume</span>
                    </span>
                    <span className="text-[10px] opacity-80">
                      {humeViolationsExpanded ? "Masquer" : "Afficher"}
                    </span>
                  </button>
                  {humeViolationsExpanded && (
                    <div className="mt-2 space-y-2 pl-2 border-l border-amber-500/30 max-h-40 overflow-y-auto text-[10px]">
                      {humeValidation.violations.map((violation) => (
                        <div key={violation.scheme_id} className="text-slate-300 space-y-0.5">
                          <div className="font-semibold">
                            Conclusion : <span className="text-amber-400 font-bold">[{violation.conclusion.label_court}]</span>
                          </div>
                          <div className="text-[9px] text-slate-400">
                            ID: <span className="select-all font-mono text-slate-500">{violation.scheme_id}</span>
                          </div>
                          <div className="text-[9px] text-slate-400 pl-2">
                            Prémisses : {violation.premises.map(p => `[${p.label_court}]`).join(", ") || "Aucune"}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Alternatives Selector */}
              <div className="space-y-2">
                <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
                  Configurations de Résolution
                </h4>
                <div className="grid grid-cols-2 gap-2">
                  {/* Solution #0 (Baseline / Optimal) */}
                  <button
                    onClick={() => setSelectedSolutionIndex(0)}
                    className={`p-2.5 rounded-xl border text-left transition-all cursor-pointer ${
                      selectedSolutionIndex === 0
                        ? "bg-indigo-600/20 border-indigo-500 text-indigo-200"
                        : "bg-slate-900/50 border-slate-900 text-slate-400 hover:border-slate-800"
                    }`}
                  >
                    <span className="text-[10px] font-bold block">Baseline (Optimal)</span>
                    <span className="text-[9px] opacity-80 block mt-0.5">Incohérence: {solveResult.incoherence_score}</span>
                  </button>

                  {/* Alternatives */}
                  {alternativesData?.map((alt) => (
                    <button
                      key={alt.solution_index ?? 0}
                      onClick={() => setSelectedSolutionIndex(alt.solution_index ?? 0)}
                      className={`p-2.5 rounded-xl border text-left transition-all cursor-pointer ${
                        selectedSolutionIndex === alt.solution_index
                          ? "bg-indigo-600/20 border-indigo-500 text-indigo-200"
                          : "bg-slate-900/50 border-slate-900 text-slate-400 hover:border-slate-800"
                      }`}
                    >
                      <span className="text-[10px] font-bold block">Alternative #{alt.solution_index}</span>
                      <span className="text-[9px] opacity-80 block mt-0.5">Incohérence: {alt.incoherence_score}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Tensions section */}
              <div className="space-y-2.5">
                <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest flex items-center justify-between">
                  <span>
                    {selectedSolutionIndex === 0
                      ? `Tensions Inévitables (${activeViolatedConstraints.length})`
                      : `Tensions Assumées par cet Arbitrage (${activeViolatedConstraints.length})`}
                  </span>
                  <span className="text-[9px] text-slate-500 bg-slate-900 border border-slate-850 px-2 py-0.5 rounded font-normal uppercase tracking-normal">
                    Poids Soft Violés
                  </span>
                </h4>

                {activeViolatedConstraints.length === 0 ? (
                  <div className="p-4 bg-slate-900/20 border border-slate-900 rounded-xl text-center text-slate-500 text-xs italic">
                    Aucune tension logique violée dans cette configuration.
                  </div>
                ) : (
                  <div className="space-y-2.5">
                    {activeViolatedConstraints.map((vc) => {
                      let titleText = "Conflit Co-accepté";
                      if (vc.kind === "inference") {
                        if (vc.cost === 5.0) titleText = "Inférence DÉDUCTIVE violée";
                        else if (vc.cost === 2.0) titleText = "Inférence défaisable fort violée";
                        else if (vc.cost === 1.0) titleText = "Inférence défaisable faible violée";
                        else titleText = `Inférence violée (coût ${vc.cost})`;
                      }
                      
                      return (
                        <div key={vc.constraint_id} className="p-3 bg-red-950/10 border border-red-500/10 rounded-xl space-y-2 text-xs">
                          <div className="flex items-center justify-between text-[10px] text-red-400 font-semibold">
                            <span>{titleText}</span>
                            <span className="bg-red-950/50 border border-red-900/30 px-1.5 py-0.5 rounded">
                              Coût: {vc.cost}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-300 leading-relaxed font-medium">
                            {vc.detail}
                          </p>
                          <details className="mt-2 text-[10px] text-slate-400 cursor-pointer">
                            <summary className="hover:text-slate-300">Voir les propositions complètes</summary>
                            <div className="mt-1.5 space-y-1 pl-2 border-l border-slate-800">
                              {vc.node_refs.map((ref) => (
                                <div key={ref.id} className="text-[10px]">
                                  <span className="font-bold text-slate-300">[{ref.label_court}]</span>: {ref.texte}
                                </div>
                              ))}
                            </div>
                          </details>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Arbitrages effectués section */}
              <div className="space-y-2.5 pt-2 border-t border-slate-900/60">
                <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest flex items-center justify-between">
                  <span>Arbitrages Effectués ({activeArbitratedTensions.length})</span>
                  <span className="text-[9px] text-slate-500 bg-slate-900 border border-slate-850 px-2 py-0.5 rounded font-normal uppercase tracking-normal">
                    Conflits Résolus
                  </span>
                </h4>

                {activeArbitratedTensions.length === 0 ? (
                  <div className="p-4 bg-slate-900/20 border border-slate-900 rounded-xl text-center text-slate-500 text-xs italic">
                    Aucun arbitrage de conflit effectué.
                  </div>
                ) : (
                  <div className="space-y-2.5">
                    {selectedSolutionIndex > 0 && (
                      <div className="p-3 bg-indigo-950/10 border border-indigo-500/10 rounded-xl text-[11px] text-indigo-300 leading-relaxed">
                        Cette alternative choisit des arbitrages différents de la baseline pour les conflits ci-dessous.
                      </div>
                    )}
                    {activeArbitratedTensions.map((t) => (
                      <div key={t.id} className="p-3 bg-slate-900/40 border border-slate-900 rounded-xl space-y-1.5 text-xs">
                        <div className="flex items-center justify-between text-[10px] text-slate-400 font-semibold">
                          <span>Arbitrage Conflit</span>
                          <span>Enjeu: {t.stake_label} ({t.stake_rank})</span>
                        </div>
                        <div className="space-y-1">
                          <div className="text-[11px] text-emerald-400 font-medium">
                            ✔ Gardé : <span className="font-bold">[{t.kept_node.label_court}]</span> {t.kept_node.texte}
                          </div>
                          <div className="text-[11px] text-slate-400">
                            ❌ Écarté : <span className="font-bold">[{t.discarded_node.label_court}]</span> {t.discarded_node.texte}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Footer with stats */}
            <div className="border-t border-slate-900 pt-4 mt-4 flex justify-between items-center text-[10px] text-slate-500">
              <span>Nœuds acceptés: {currentAcceptedIds.size}</span>
              <span>Nœuds rejetés: {currentRejectedIds.size}</span>
            </div>
          </div>
        )}
      </main>

      {/* Node Details Panel (Sheet) */}
      <Sheet open={panelOpen} onOpenChange={setPanelOpen}>
        <SheetContent className="bg-slate-950/95 backdrop-blur-md border-l border-slate-900 text-slate-100 sm:max-w-md w-full shadow-2xl p-0 flex flex-col justify-between">
          {detailsLoading ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-2.5">
              <span className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-500" />
              <span className="text-xs text-slate-500 font-semibold uppercase tracking-wider">
                Chargement des détails...
              </span>
            </div>
          ) : !nodeDetails?.node ? (
            <div className="flex-1 flex items-center justify-center text-slate-500">
              Sélectionnez un claim pour voir les détails.
            </div>
          ) : (
            <div className="flex-1 flex flex-col overflow-y-auto">
              <SheetHeader className="border-b border-slate-900 p-6">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[9px] px-2 py-0.5 rounded-full bg-indigo-950/40 border border-indigo-800/40 text-indigo-400 font-bold uppercase tracking-wider">
                    {nodeDetails.node.type.replace("_", " ")}
                  </span>
                  <span className="text-[9px] px-2 py-0.5 rounded-full bg-slate-900 border border-slate-800 text-slate-400 font-bold uppercase tracking-wider">
                    {nodeDetails.node.domain}
                  </span>
                </div>
                <SheetTitle className="text-slate-100 font-heading text-lg font-semibold leading-snug">
                  Détails du Claim
                </SheetTitle>
                <SheetDescription className="text-slate-400 text-xs">
                  ID: {nodeDetails.node.id}
                </SheetDescription>
              </SheetHeader>

              {/* Main Sheet Body */}
              <div className="p-6 space-y-6 flex-1">
                {/* Node Text Block */}
                <div className="space-y-2">
                  <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest flex items-center gap-1">
                    <BookOpen className="w-3.5 h-3.5 text-indigo-500" />
                    Énoncé / Proposition
                  </h4>
                  <p className="text-slate-200 text-sm font-semibold leading-relaxed p-4 rounded-xl bg-slate-900/50 border border-slate-900 shadow-inner">
                    {nodeDetails.node.text}
                  </p>
                </div>

                {/* Node Attributes */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-3.5 rounded-xl bg-slate-900/30 border border-slate-900/80 flex flex-col justify-between">
                    <span className="text-[9px] text-slate-500 font-bold uppercase tracking-wider block mb-1">
                      {["descriptif", "empirique", "definitionnel"].includes(nodeDetails.node.type) ? "Crédence" : "Engagement"}
                    </span>
                    <select
                      value={nodeDetails.node.tier || "moyen"}
                      onChange={async (e) => {
                        const newTier = e.target.value;
                        try {
                          await updateNodeMutation.mutateAsync({
                            id: nodeDetails.node.id,
                            payload: { tier: newTier }
                          });
                        } catch (err) {
                          console.error("Failed to update node tier:", err);
                        }
                      }}
                      className="bg-slate-950 border border-slate-800 text-xs rounded-lg px-2.5 py-1 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-slate-200 font-bold mt-1"
                    >
                      <option value="speculatif">Spéculatif</option>
                      <option value="faible">Faible</option>
                      <option value="moyen">Moyen</option>
                      <option value="fort">Fort</option>
                      <option value="certain">Certain</option>
                    </select>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-900/30 border border-slate-900/80">
                    <span className="text-[9px] text-slate-500 font-bold uppercase tracking-wider block mb-1">
                      Importé le
                    </span>
                    <span className="text-xs font-semibold text-slate-400">
                      {new Date(nodeDetails.node.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>

                {/* Dérivation de l'Engagement Section */}
                {(() => {
                  const derivationInfo = commitmentDerivation?.results.find((r) => r.node_id === nodeDetails.node.id);
                  if (!derivationInfo) return null;
                  return (
                    <div className={`p-4 rounded-xl space-y-3 border ${
                      derivationInfo.overcommitted 
                        ? "bg-amber-950/20 border-amber-500/30 text-amber-400" 
                        : "bg-slate-900/20 border-slate-900 text-slate-300"
                    }`}>
                      <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider">
                        <span>Dérivation de l&apos;Engagement</span>
                        {derivationInfo.overcommitted && (
                          <span className="bg-amber-500/20 border border-amber-500/40 text-amber-400 px-1.5 py-0.5 rounded font-bold uppercase tracking-normal animate-pulse">
                            Sur-engagement (+{derivationInfo.gap})
                          </span>
                        )}
                        {derivationInfo.undercommitted && (
                          <span className="bg-blue-500/10 border border-blue-500/30 text-blue-400 px-1.5 py-0.5 rounded font-bold uppercase tracking-normal">
                            Sous-engagement
                          </span>
                        )}
                        {derivationInfo.cycle_detected && (
                          <span className="bg-red-500/20 border border-red-500/40 text-red-400 px-1.5 py-0.5 rounded font-bold uppercase tracking-normal">
                            Cycle détecté
                          </span>
                        )}
                      </div>
                      
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div>
                          <span className="text-[10px] text-slate-500 block uppercase font-medium">Palier Manuel</span>
                          <span className="font-semibold text-slate-200 capitalize">
                            {derivationInfo.manual_tier || "moyen"} (rang: {derivationInfo.manual_rank})
                          </span>
                        </div>
                        <div>
                          <span className="text-[10px] text-slate-500 block uppercase font-medium">Palier Dérivé</span>
                          <span className="font-semibold text-slate-200 capitalize">
                            {derivationInfo.derived_tier_label ? `${derivationInfo.derived_tier_label} (rang: ${derivationInfo.derived_rank})` : "—"}
                          </span>
                        </div>
                      </div>

                      {derivationInfo.contributing_scheme_id && (
                        <div className="text-xs pt-2 border-t border-slate-800/40">
                          <span className="text-[10px] text-slate-500 block uppercase font-medium">Inférence contributrice</span>
                          <span className="font-mono text-[10px] text-slate-400">
                            {derivationInfo.contributing_scheme_id}
                          </span>
                        </div>
                      )}
                    </div>
                  );
                })()}

                {/* Arbitrage Logique */}
                {activeCoherence === "rejete_arbitre" && (
                  <div className="p-4 rounded-xl bg-slate-900/20 border border-slate-900 space-y-3">
                    <div className="flex items-center justify-between text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                      <span>Arbitrage Logique</span>
                      <span className="bg-slate-900 border border-slate-850 px-1.5 py-0.5 rounded font-normal uppercase tracking-normal">Optionnel</span>
                    </div>
                    <p className="text-xs text-slate-400 leading-relaxed">
                      Cette thèse a été écartée par le solveur pour optimiser la cohérence globale de votre système.
                    </p>
                    <Button
                      onClick={() => {
                        setArbitrageNode(nodeDetails.node);
                        setArbitrageDialogOpen(true);
                      }}
                      className="w-full bg-indigo-600/10 hover:bg-indigo-600/20 text-indigo-400 border border-indigo-500/20 hover:border-indigo-500/40 rounded-lg text-xs py-1.5 transition-colors cursor-pointer h-8"
                    >
                      Choisir d&apos;accepter cette thèse
                    </Button>
                  </div>
                )}

                {/* Neighbors List */}
                <div className="space-y-3">
                  <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest flex items-center gap-1.5">
                    <Layers className="w-3.5 h-3.5 text-indigo-500" />
                    Claims Voisins ({nodeDetails.neighbors.length})
                  </h4>
                  {nodeDetails.neighbors.length === 0 ? (
                    <p className="text-slate-500 text-xs">Aucune liaison directe pour ce claim.</p>
                  ) : (
                    <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                      {nodeDetails.neighbors.map((nb: NodeNeighbor, idx: number) => {
                        const relColor =
                          RELATION_COLORS[nb.relation as keyof typeof RELATION_COLORS] ||
                          RELATION_COLORS.presuppose;
                        return (
                          <div
                            key={idx}
                            onClick={() => handleSuggestionClick(nb.node.id)}
                            className="p-3 rounded-xl border border-slate-900 bg-slate-900/20 hover:border-slate-800 hover:bg-slate-900/40 transition-all cursor-pointer flex flex-col gap-1.5 group"
                          >
                            <div className="flex items-center justify-between text-[10px]">
                              <span
                                className="font-semibold uppercase tracking-wider px-2 py-0.5 rounded"
                                style={{ backgroundColor: `${relColor}15`, color: relColor }}
                              >
                                {nb.relation}
                              </span>
                              <span className="text-slate-500 flex items-center gap-1">
                                {nb.direction === "incoming" ? "Prémisse / Source" : "Conséquence / Cible"}
                                <ChevronRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
                              </span>
                            </div>
                            <p className="text-slate-300 font-semibold text-xs leading-snug line-clamp-2">
                              {nb.node.text}
                            </p>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Semantic Suggestions */}
                <div className="space-y-3 pt-2">
                  <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                      Suggestions de Liens (pgvector)
                    </span>
                    <span className="text-[9px] text-slate-500 bg-slate-900 px-2 py-0.5 rounded font-normal uppercase tracking-normal">
                      cosinus &gt; 0.92
                    </span>
                  </h4>

                  {relatedLoading ? (
                    <div className="flex items-center gap-2 text-slate-500 text-xs">
                      <span className="animate-spin rounded-full h-3 w-3 border-b border-purple-400" />
                      <span>Recherche de claims proches...</span>
                    </div>
                  ) : !relatedClaims || relatedClaims.length === 0 ? (
                    <p className="text-slate-500 text-xs">Aucune suggestion sémantique disponible.</p>
                  ) : (
                    <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                      {relatedClaims.map((rc: RelatedNodeResponse) => (
                        <div
                          key={rc.node.id}
                          onClick={() => handleSuggestionClick(rc.node.id)}
                          className="p-3 rounded-xl border border-slate-900 bg-slate-900/10 hover:border-slate-800 hover:bg-slate-900/30 transition-all cursor-pointer flex flex-col gap-1.5 group"
                        >
                          <div className="flex items-center justify-between text-[10px]">
                            <span className="text-purple-400 font-bold flex items-center gap-1">
                              <Link className="w-3 h-3" />
                              Lien Suggéré
                            </span>
                            <span className="text-emerald-400 font-bold bg-emerald-950/20 px-1.5 py-0.5 rounded">
                              Similarité: {Math.round(rc.similarity * 100)}%
                            </span>
                          </div>
                          <p className="text-slate-300 font-semibold text-xs leading-snug line-clamp-2">
                            {rc.node.text}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              
              {/* Footer with Delete Button */}
              <div className="p-6 border-t border-slate-900 bg-slate-950 flex items-center justify-end">
                <Button
                  variant="destructive"
                  onClick={() => handleDeleteNode(nodeDetails.node.id)}
                  disabled={deleteNodeMutation.isPending}
                  className="w-full flex items-center justify-center gap-2 hover:bg-red-600 transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                  Supprimer la thèse
                </Button>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>

      {/* Arbitrage Resolution Dialog */}
      {arbitrageDialogOpen && arbitrageNode && (() => {
        const matchingAlt = alternativesData?.find(alt => alt.accepted.includes(arbitrageNode.id));
        const claimsToDrop = (() => {
          if (!matchingAlt || !solveResult || !graphData) return [];
          const baselineAccepted = new Set(solveResult.accepted);
          const altRejected = new Set(matchingAlt.rejected);
          const idsToDrop = [...baselineAccepted].filter(id => altRejected.has(id));
          return graphData.nodes.filter(n => idsToDrop.includes(n.id));
        })();

        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-4 animate-fade-in">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-5 relative">
              <div>
                <h4 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                  ⚖️ Choix d&apos;Arbitrage alternatif
                </h4>
                <p className="text-slate-400 text-xs mt-1">
                  Analyse des répercussions logiques si vous choisissez d&apos;accepter cette thèse.
                </p>
              </div>

              <div className="space-y-4">
                <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-900 text-xs space-y-2">
                  <span className="text-[10px] text-indigo-400 font-bold uppercase tracking-wider block">Thèse à intégrer :</span>
                  <p className="text-slate-200 font-semibold leading-relaxed">
                    &quot;{arbitrageNode.text}&quot;
                  </p>
                </div>

                {matchingAlt ? (
                  <div className="space-y-3">
                    <p className="text-xs text-slate-300 leading-relaxed">
                      Tu peux choisir d&apos;accepter cette thèse. Cependant, pour maintenir la cohérence, **il faudra lâcher :**
                    </p>
                    <div className="p-3.5 rounded-xl bg-red-950/10 border border-red-500/20 space-y-2 max-h-36 overflow-y-auto">
                      {claimsToDrop.map((c) => (
                        <div key={c.id} className="text-[11px] text-red-200/90 font-medium leading-relaxed">
                          • {c.text}
                        </div>
                      ))}
                    </div>
                    <Button
                      onClick={() => {
                        setSelectedSolutionIndex(matchingAlt.solution_index ?? 0);
                        setArbitrageDialogOpen(false);
                        setArbitrageNode(null);
                        setPanelOpen(false);
                      }}
                      className="w-full bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold py-2.5 cursor-pointer h-10 flex items-center justify-center gap-1.5"
                    >
                      <Sparkles className="w-4 h-4" />
                      <span>Appliquer la configuration Alternative #{matchingAlt.solution_index}</span>
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-3 text-xs text-slate-400 leading-relaxed bg-slate-950/40 p-3.5 rounded-xl border border-slate-900">
                    <p>
                      Aucune des solutions alternatives optimales calculées ne permet d&apos;accepter cette thèse directement.
                    </p>
                    <p className="font-semibold text-indigo-400 mt-2">
                      💡 Astuce :
                    </p>
                    <p>
                      Pour forcer le système à accepter cette proposition, augmentez son niveau de Crédence/Engagement (dans le menu déroulant sur la droite). Cela forcera le solveur à réordonner toutes ses priorités.
                    </p>
                  </div>
                )}
              </div>

              <div className="flex justify-end pt-2 border-t border-slate-800">
                <Button
                  onClick={() => {
                    setArbitrageDialogOpen(false);
                    setArbitrageNode(null);
                  }}
                  className="bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-800 px-4 py-2 rounded-lg text-xs"
                >
                  Fermer
                </Button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* Edge Details Panel (Sheet) */}
      <Sheet open={edgePanelOpen} onOpenChange={setEdgePanelOpen}>
        <SheetContent className="bg-slate-950/95 backdrop-blur-md border-l border-slate-900 text-slate-100 sm:max-w-md w-full shadow-2xl p-0 flex flex-col justify-between">
          {!selectedEdge ? (
            <div className="flex-1 flex items-center justify-center text-slate-500">
              Sélectionnez une relation pour voir les détails.
            </div>
          ) : (
            <div className="flex-1 flex flex-col overflow-y-auto">
              <SheetHeader className="border-b border-slate-900 p-6">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[9px] px-2 py-0.5 rounded-full bg-emerald-950/40 border border-emerald-800/40 text-emerald-400 font-bold uppercase tracking-wider">
                    Relation Logique
                  </span>
                  {humeValidation && humeValidation.violations.some(v => v.scheme_id === selectedEdge.scheme_id) && (
                    <span className="text-[9px] px-2 py-0.5 rounded-full bg-red-950/40 border border-red-800/40 text-red-400 font-bold uppercase tracking-wider animate-pulse">
                      VIOLE LA LOI DE HUME
                    </span>
                  )}
                </div>
                <SheetTitle className="text-slate-100 font-heading text-lg font-semibold leading-snug">
                  Détails de la Relation
                </SheetTitle>
                <SheetDescription className="text-slate-400 text-xs">
                  Schéma ID: {selectedEdge.scheme_id}
                </SheetDescription>
              </SheetHeader>

              {/* Main Sheet Body */}
              <div className="p-6 space-y-6 flex-1">
                {/* Relation Type */}
                <div className="space-y-2">
                  <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest flex items-center gap-1">
                    Type de Relation
                  </h4>
                  <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-900 shadow-inner flex items-center gap-2">
                    <span
                      className="font-bold uppercase tracking-wider px-2.5 py-0.5 rounded text-xs"
                      style={{
                        backgroundColor: `${RELATION_COLORS[selectedEdge.relation as keyof typeof RELATION_COLORS] || RELATION_COLORS.presuppose}15`,
                        color: RELATION_COLORS[selectedEdge.relation as keyof typeof RELATION_COLORS] || RELATION_COLORS.presuppose
                      }}
                    >
                      {selectedEdge.relation}
                    </span>
                  </div>
                </div>

                {/* Inference Strength */}
                {selectedEdge.relation === "soutient" && (
                  <div className="space-y-2">
                    <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
                      Force de l&apos;Inférence (Poids de Schéma)
                    </h4>
                    <select
                      value={selectedEdge.strength || "defaisable_faible"}
                      onChange={(e) => handleUpdateSchemeStrength(selectedEdge.scheme_id, e.target.value as SchemeStrength)}
                      className="w-full bg-slate-900 border border-slate-800 text-slate-200 text-xs rounded-xl px-4 py-3 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 outline-none"
                    >
                      <option value="deductif">Déductif (coût 5.0)</option>
                      <option value="defaisable_fort">Défaisable Fort (coût 2.0)</option>
                      <option value="defaisable_faible">Défaisable Faible (coût 1.0)</option>
                    </select>
                  </div>
                )}

                {/* Source Node Text */}
                <div className="space-y-2">
                  <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
                    Source (Prémisse / Antécédent)
                  </h4>
                  {edgeSourceNode ? (
                    <div
                      onClick={() => {
                        setSelectedNodeId(edgeSourceNode.id);
                        setPanelOpen(true);
                        setEdgePanelOpen(false);
                      }}
                      className="p-4 rounded-xl bg-slate-900/30 hover:bg-slate-900/50 border border-slate-900 shadow-inner cursor-pointer transition-all hover:border-slate-800 group"
                    >
                      <p className="text-slate-200 text-sm font-semibold leading-relaxed line-clamp-4">
                        {edgeSourceNode.text}
                      </p>
                      <span className="text-[9px] mt-2 block text-indigo-400 font-bold uppercase tracking-wider group-hover:underline">
                        Voir les détails du Claim &rarr;
                      </span>
                    </div>
                  ) : (
                    <p className="text-slate-500 text-xs italic">Nœud source introuvable ou supprimé.</p>
                  )}
                </div>

                {/* Target Node Text */}
                <div className="space-y-2">
                  <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
                    Cible (Conclusion / Conséquence)
                  </h4>
                  {edgeTargetNode ? (
                    <div
                      onClick={() => {
                        setSelectedNodeId(edgeTargetNode.id);
                        setPanelOpen(true);
                        setEdgePanelOpen(false);
                      }}
                      className="p-4 rounded-xl bg-slate-900/30 hover:bg-slate-900/50 border border-slate-900 shadow-inner cursor-pointer transition-all hover:border-slate-800 group"
                    >
                      <p className="text-slate-200 text-sm font-semibold leading-relaxed line-clamp-4">
                        {edgeTargetNode.text}
                      </p>
                      <span className="text-[9px] mt-2 block text-indigo-400 font-bold uppercase tracking-wider group-hover:underline">
                        Voir les détails du Claim &rarr;
                      </span>
                    </div>
                  ) : (
                    <p className="text-slate-500 text-xs italic">Nœud cible introuvable ou supprimé.</p>
                  )}
                </div>
              </div>

              {/* Footer with Delete Relation Button */}
              <div className="p-6 border-t border-slate-900 bg-slate-950 flex items-center justify-end">
                <Button
                  variant="destructive"
                  onClick={() => handleDeleteEdge(selectedEdge.scheme_id)}
                  disabled={deleteEdgeMutation.isPending}
                  className="w-full flex items-center justify-center gap-2 hover:bg-red-600 transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                  Supprimer la relation
                </Button>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>

      {/* Tensions List Panel (Sheet) */}
      <Sheet open={tensionsPanelOpen} onOpenChange={setTensionsPanelOpen}>
        <SheetContent className="bg-slate-950/95 backdrop-blur-md border-l border-slate-900 text-slate-100 sm:max-w-md w-full shadow-2xl p-0 flex flex-col justify-between">
          <SheetHeader className="border-b border-slate-900 p-6">
            <SheetTitle className="text-slate-100 font-heading text-lg font-semibold flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-red-500" />
              Détecteur de Tensions
            </SheetTitle>
            <SheetDescription className="text-slate-400 text-xs">
              Incohérences et contradictions logiques détectées dans votre système de croyances.
            </SheetDescription>
          </SheetHeader>

          <div className="p-6 space-y-6 flex-1 overflow-y-auto">
            {!effectiveTensions || effectiveTensions.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center text-slate-500">
                <Info className="w-8 h-8 text-slate-600 mb-2" />
                <p className="font-semibold text-sm">Graphe Cohérent !</p>
                <p className="text-xs max-w-[240px] mt-1">Aucune tension ou cycle contradictoire n&apos;a été détecté dans la base.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {effectiveTensions.map((t) => {
                  const sensTension = sensitivity?.tensions?.find((st) => st.tension_id === t.id);
                  return (
                    <div
                      key={t.id}
                      className={`p-4 rounded-xl border transition-all ${
                        t.paradoxe_assume
                          ? "bg-slate-900/40 border-slate-800 text-slate-400"
                          : "bg-red-950/10 border-red-500/20 text-slate-200 shadow-md shadow-red-950/10"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-3 text-[10px]">
                        <span className={`font-bold uppercase tracking-wider ${
                          t.paradoxe_assume ? "text-slate-500" : "text-red-400"
                        }`}>
                          {t.type === "conflit_direct" ? "Conflit Direct" : "Cycle Incohérent"}
                        </span>
                        
                        <div className="flex items-center gap-2">
                          {t.paradoxe_assume && (
                            <span className="bg-slate-800 text-slate-400 border border-slate-700 px-1.5 py-0.5 rounded font-medium">
                              Paradoxe Assumé
                            </span>
                          )}
                          <span className={`font-bold px-1.5 py-0.5 rounded ${
                            t.paradoxe_assume ? "bg-slate-800 text-slate-500" : "bg-red-950/50 text-red-400 border border-red-900/30"
                          }`}>
                            Gravité: {Math.round(t.score * 100)}%
                          </span>
                        </div>
                      </div>

                      <div className="space-y-2 mb-3">
                        <h5 className="text-[9px] font-bold text-slate-500 uppercase tracking-widest">Assertions en Conflit</h5>
                        {t.claims.map((claim) => {
                          const isFactual = ["descriptif", "empirique", "definitionnel"].includes(claim.type);
                          const tierInfo = getTierInfo(claim.tier ?? undefined, claim.weight ?? undefined);
                          return (
                            <div key={claim.id} className="p-2.5 rounded bg-slate-950/50 border border-slate-900 text-xs font-medium leading-relaxed flex flex-col gap-1.5">
                              <span>{claim.text}</span>
                              <span className="text-[9px] text-slate-500 font-bold inline-flex items-center gap-1">
                                <span className={`inline-block w-1.5 h-1.5 rounded-full ${tierInfo.color}`} />
                                {isFactual ? "Crédence" : "Engagement"}: {tierInfo.label}
                              </span>
                            </div>
                          );
                        })}
                      </div>

                      {t.ponts.length > 0 && (
                        <div className="space-y-2 mb-4">
                          <h5 className="text-[9px] font-bold text-slate-500 uppercase tracking-widest">Prémisse-Pont Médiatrice</h5>
                          {t.ponts.map((pont) => {
                            const isFactual = ["descriptif", "empirique", "definitionnel"].includes(pont.type);
                            const tierInfo = getTierInfo(pont.tier ?? undefined, pont.weight ?? undefined);
                            return (
                              <div key={pont.id} className="p-2.5 rounded bg-amber-950/10 border border-amber-900/20 text-amber-200/90 text-xs font-medium leading-relaxed flex flex-col gap-1.5">
                                <span>{pont.text}</span>
                                <span className="text-[9px] text-amber-400/80 font-bold inline-flex items-center gap-1">
                                  <span className={`inline-block w-1.5 h-1.5 rounded-full ${tierInfo.color}`} />
                                  {isFactual ? "Crédence" : "Engagement"}: {tierInfo.label}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      )}

                      {/* Sensitivity Robustness Analysis */}
                      {sensTension && (
                        <div className="mt-3.5 pt-3 border-t border-slate-900/60 space-y-2 mb-4">
                          <div className="flex items-center justify-between">
                            <span className="text-[9px] text-slate-500 font-bold uppercase tracking-wider">Robustesse</span>
                            <span className={`text-[9px] px-2 py-0.5 rounded font-bold uppercase border ${
                              sensTension.robustesse === "robuste"
                                ? "bg-emerald-950/50 text-emerald-400 border-emerald-800"
                                : "bg-amber-950/50 text-amber-400 border-amber-800 animate-pulse"
                            }`}>
                              {sensTension.robustesse === "robuste" ? "Robuste" : "Fragile"}
                            </span>
                          </div>
                          {sensTension.robustesse === "fragile" && (
                            <p className="text-[10px] text-amber-500 bg-amber-950/20 p-2 rounded border border-amber-900/20 leading-normal font-semibold">
                              ⚠️ Repose sur un poids incertain.
                            </p>
                          )}
                          {sensTension.explanation && (
                            <p className="text-[10px] text-slate-400 bg-slate-950/40 p-2 rounded border border-slate-900 leading-normal italic">
                              {sensTension.explanation}
                            </p>
                          )}
                        </div>
                      )}

                      <div className="flex gap-2">
                        <Button
                          onClick={() => {
                            setResolvingTension(t);
                            setResolveDialogOpen(true);
                          }}
                          className="flex-1 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700/50 rounded-lg text-xs py-1.5 transition-colors cursor-pointer h-8"
                        >
                          Résoudre
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <footer className="border-t border-slate-900 py-4 bg-slate-950 text-center text-[10px] text-slate-600">
            Analyse de cohérence graphe en temps réel
          </footer>
        </SheetContent>
      </Sheet>

      {/* Tension Resolution Overlay / Dialog */}
      {resolveDialogOpen && resolvingTension && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-5 relative">
            <div>
              <h4 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-red-500" />
                Résolution de la Tension
              </h4>
              <p className="text-slate-400 text-xs mt-1">
                Choisissez comment vous souhaitez rétablir la cohérence logique dans votre graphe.
              </p>
            </div>

            <div className="space-y-2.5">
              <button
                onClick={async () => {
                  try {
                    const result = await resolveTensionMutation.mutateAsync({
                      action: "reviser_node",
                      node_id: resolvingTension.claims[0].id
                    });
                    setDiffData(result);
                    setDiffDialogOpen(true);
                  } catch (e) {
                    console.error("Resolve failed:", e);
                  }
                  setResolveDialogOpen(false);
                  setResolvingTension(null);
                }}
                disabled={resolveTensionMutation.isPending}
                className="w-full text-left p-3.5 rounded-xl border border-slate-800 bg-slate-950/30 hover:bg-slate-950/60 hover:border-indigo-500/50 transition-all cursor-pointer group"
              >
                <div className="text-[10px] font-bold text-indigo-400 uppercase tracking-wide mb-1">Réviser l&apos;Assertion A</div>
                <div className="text-xs font-semibold text-slate-200 line-clamp-2 leading-relaxed group-hover:text-white">
                  &quot;{resolvingTension.claims[0].text}&quot;
                </div>
              </button>

              {resolvingTension.claims[1] && (
                <button
                  onClick={async () => {
                    try {
                      const result = await resolveTensionMutation.mutateAsync({
                        action: "reviser_node",
                        node_id: resolvingTension.claims[1].id
                      });
                      setDiffData(result);
                      setDiffDialogOpen(true);
                    } catch (e) {
                      console.error("Resolve failed:", e);
                    }
                    setResolveDialogOpen(false);
                    setResolvingTension(null);
                  }}
                  disabled={resolveTensionMutation.isPending}
                  className="w-full text-left p-3.5 rounded-xl border border-slate-800 bg-slate-950/30 hover:bg-slate-950/60 hover:border-indigo-500/50 transition-all cursor-pointer group"
                >
                  <div className="text-[10px] font-bold text-indigo-400 uppercase tracking-wide mb-1">Réviser l&apos;Assertion B</div>
                  <div className="text-xs font-semibold text-slate-200 line-clamp-2 leading-relaxed group-hover:text-white">
                    &quot;{resolvingTension.claims[1].text}&quot;
                  </div>
                </button>
              )}

              {resolvingTension.ponts.map((pont) => (
                <button
                  key={pont.id}
                  onClick={async () => {
                    try {
                      const result = await resolveTensionMutation.mutateAsync({
                        action: "reviser_node",
                        node_id: pont.id
                      });
                      setDiffData(result);
                      setDiffDialogOpen(true);
                    } catch (e) {
                      console.error("Resolve failed:", e);
                    }
                    setResolveDialogOpen(false);
                    setResolvingTension(null);
                  }}
                  disabled={resolveTensionMutation.isPending}
                  className="w-full text-left p-3.5 rounded-xl border border-amber-900/30 bg-amber-950/5 hover:bg-amber-950/10 hover:border-amber-500/50 transition-all cursor-pointer group"
                >
                  <div className="text-[10px] font-bold text-amber-400 uppercase tracking-wide mb-1">Rejeter la Prémisse-Pont</div>
                  <div className="text-xs font-semibold text-amber-200 line-clamp-2 leading-relaxed group-hover:text-white">
                    &quot;{pont.text}&quot;
                  </div>
                </button>
              ))}

              {resolvingTension.scheme_id && !resolvingTension.paradoxe_assume && (
                <button
                  onClick={async () => {
                    try {
                      const result = await resolveTensionMutation.mutateAsync({
                        action: "accepter_paradoxe",
                        scheme_id: resolvingTension.scheme_id
                      });
                      setDiffData(result);
                      setDiffDialogOpen(true);
                    } catch (e) {
                      console.error("Resolve failed:", e);
                    }
                    setResolveDialogOpen(false);
                    setResolvingTension(null);
                  }}
                  disabled={resolveTensionMutation.isPending}
                  className="w-full text-left p-3.5 rounded-xl border border-slate-800 bg-slate-950/20 hover:bg-slate-950/40 hover:border-emerald-500/50 transition-all cursor-pointer group"
                >
                  <div className="text-[10px] font-bold text-emerald-400 uppercase tracking-wide mb-1">Accepter comme Paradoxe Assumé</div>
                  <div className="text-xs text-slate-300 group-hover:text-white leading-relaxed">
                    Taguer cette contradiction en base de données et la masquer du statut d&apos;alerte.
                  </div>
                </button>
              )}
            </div>

            <div className="flex justify-end pt-2">
              <Button
                onClick={() => {
                  setResolveDialogOpen(false);
                  setResolvingTension(null);
                }}
                disabled={resolveTensionMutation.isPending}
                className="bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-800 px-4 py-2 rounded-lg text-xs"
              >
                Annuler
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* "Ce qui a bougé" / Tension Resolution Diff Dialog */}
      {diffDialogOpen && diffData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-5 relative">
            <div>
              <h4 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                ⚖️ Ce qui a bougé (Ajustement Réalisé)
              </h4>
              <p className="text-slate-400 text-xs mt-1">
                La base de croyances s&apos;est réorganisée pour restaurer la cohérence logique. Voici l&apos;impact de votre décision :
              </p>
            </div>

            <div className="space-y-4 max-h-96 overflow-y-auto pr-1">
              {/* Resolved Tensions */}
              <div className="space-y-2">
                <h5 className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider">
                  Tensions Résolues ({diffData.tensions_resolues.length})
                </h5>
                {diffData.tensions_resolues.length === 0 ? (
                  <p className="text-xs text-slate-500 italic">Aucune tension résolue directement.</p>
                ) : (
                  <div className="space-y-2">
                    {diffData.tensions_resolues.map((t) => (
                      <div key={t.id} className="p-3 rounded-lg bg-emerald-950/10 border border-emerald-500/20 text-xs text-slate-300">
                        <span className="font-bold text-emerald-400 block mb-1">
                          {t.type === "conflit_direct" ? "Conflit Direct Résolu" : "Cycle Incohérent Résolu"}
                        </span>
                        <div className="space-y-1">
                          {t.claims.map((c) => (
                            <div key={c.id} className="text-[11px] text-slate-400">• {c.text}</div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* New Tensions */}
              <div className="space-y-2">
                <h5 className="text-[10px] font-bold text-amber-400 uppercase tracking-wider">
                  Nouvelles Tensions Apparues ({diffData.tensions_nouvelles.length})
                </h5>
                {diffData.tensions_nouvelles.length === 0 ? (
                  <p className="text-xs text-slate-500 italic">Aucune nouvelle tension créée. Félicitations !</p>
                ) : (
                  <div className="space-y-2">
                    {diffData.tensions_nouvelles.map((t) => (
                      <div key={t.id} className="p-3 rounded-lg bg-amber-950/10 border border-amber-500/20 text-xs text-slate-300">
                        <span className="font-bold text-amber-400 block mb-1">
                          {t.type === "conflit_direct" ? "Nouveau Conflit Direct" : "Nouveau Cycle Incohérent"}
                        </span>
                        <div className="space-y-1">
                          {t.claims.map((c) => (
                            <div key={c.id} className="text-[11px] text-slate-400">• {c.text}</div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Affected Claims */}
              <div className="space-y-2">
                <h5 className="text-[10px] font-bold text-indigo-400 uppercase tracking-wider">
                  Claims Réévalués dans la Composante Affectée ({diffData.claims_affectes.length})
                </h5>
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-1 max-h-36 overflow-y-auto">
                  {diffData.claims_affectes.map((c) => (
                    <div key={c.id} className="text-[11px] text-slate-300 flex justify-between items-center gap-2">
                      <span className="truncate">{c.text}</span>
                      {(() => {
                        const w = c.weight ?? c.confidence ?? 0;
                        const isAccepted = w > 0.0;
                        const tierInfo = getTierInfo(c.tier ?? undefined, w);
                        return (
                          <span className={`font-mono text-[10px] px-1.5 py-0.5 rounded font-bold ${
                            isAccepted ? "text-indigo-400 bg-indigo-950/40" : "text-rose-400 bg-rose-950/40"
                          }`}>
                            {isAccepted ? `Accepté (${tierInfo.label})` : "Exclu / Révisé"}
                          </span>
                        );
                      })()}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <Button
                onClick={() => {
                  setDiffDialogOpen(false);
                  setDiffData(null);
                }}
                className="bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2.5 rounded-xl text-xs font-semibold cursor-pointer border border-transparent h-10"
              >
                Fermer
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Snapshot Diff Dialog */}
      {renderSnapshotDiffModal()}

      {/* Domain Manager Modal */}
      {domainManagerOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-xl w-full p-6 shadow-2xl space-y-5 flex flex-col max-h-[85vh]">
            <div>
              <h4 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                📂 Gestionnaire de Branches (Domaines)
              </h4>
              <p className="text-slate-400 text-xs mt-1">
                Créez, modifiez ou supprimez des branches pour classer vos croyances. La suppression réaffectera les claims associés.
              </p>
            </div>

            {/* Create Domain Form */}
            <div className="bg-slate-950/40 p-4 rounded-xl border border-slate-800 space-y-3">
              <h5 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Créer une nouvelle branche</h5>
              <div className="flex flex-col sm:flex-row gap-3">
                <input
                  type="text"
                  placeholder="Nom de la branche (ex: éducation)"
                  value={newDomainName}
                  onChange={(e) => setNewDomainName(e.target.value)}
                  className="flex-1 bg-slate-900 border border-slate-800 text-xs rounded-xl px-3.5 py-2 text-slate-200 outline-none focus:border-indigo-500 transition-colors"
                />
                <select
                  value={newDomainParentId}
                  onChange={(e) => setNewDomainParentId(e.target.value)}
                  className="bg-slate-900 border border-slate-800 text-xs rounded-xl px-3.5 py-2 text-slate-200 outline-none focus:border-indigo-500 transition-colors max-w-xs"
                >
                  <option value="">Aucun parent (Racine)</option>
                  {domains?.map((dom) => (
                    <option key={dom.id} value={dom.id}>
                      {dom.name}
                    </option>
                  ))}
                </select>
                <Button
                  onClick={async () => {
                    if (!newDomainName.trim()) return;
                    try {
                      await createDomainMutation.mutateAsync({
                        name: newDomainName.trim().toLowerCase(),
                        parent_id: newDomainParentId || null
                      });
                      setNewDomainName("");
                      setNewDomainParentId("");
                    } catch (e) {
                      console.error(e);
                    }
                  }}
                  disabled={createDomainMutation.isPending}
                  className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold px-4 cursor-pointer h-9 flex items-center justify-center gap-1.5"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Ajouter</span>
                </Button>
              </div>
            </div>

            {/* List and Update/Delete Domains */}
            <div className="flex-1 overflow-y-auto space-y-2.5 pr-1">
              <h5 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Branches Existantes</h5>
              {domains?.length === 0 ? (
                <p className="text-xs text-slate-500 italic py-4">Aucune branche enregistrée.</p>
              ) : (
                <div className="space-y-2">
                  {domains?.map((dom) => (
                    <div
                      key={dom.id}
                      className="p-3.5 rounded-xl border border-slate-900 bg-slate-950/20 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
                    >
                      <div className="flex flex-col gap-1">
                        <span className="text-xs font-bold text-slate-200">{dom.name}</span>
                        {dom.parent_id && (
                          <span className="text-[10px] text-slate-500">
                            Parent: {domains.find(d => d.id === dom.parent_id)?.name || "Inconnu"}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        {/* Edit Inline Button */}
                        <Button
                          onClick={async () => {
                            const newName = prompt("Modifier le nom de la branche:", dom.name);
                            if (newName === null) return;
                            const nameVal = newName.trim().toLowerCase();
                            if (!nameVal) return;
                            try {
                              await updateDomainMutation.mutateAsync({
                                id: dom.id,
                                payload: { name: nameVal, parent_id: dom.parent_id }
                              });
                            } catch (e) {
                              console.error(e);
                            }
                          }}
                          className="bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] font-bold rounded-lg px-2.5 py-1.5 cursor-pointer h-8"
                        >
                          Renommer
                        </Button>

                        {/* Delete Button */}
                        <Button
                          onClick={async () => {
                            if (confirm(`Supprimer la branche "${dom.name}" ? Les claims associés seront réaffectés à sa branche parente ou à "général".`)) {
                              try {
                                await deleteDomainMutation.mutateAsync(dom.id);
                              } catch (e) {
                                console.error(e);
                              }
                            }
                          }}
                          disabled={deleteDomainMutation.isPending}
                          className="bg-rose-950/20 border border-rose-800/30 hover:border-rose-500/50 text-rose-400 text-[10px] font-bold rounded-lg px-2.5 py-1.5 cursor-pointer h-8"
                        >
                          Supprimer
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="flex justify-end pt-3 border-t border-slate-800">
              <Button
                onClick={() => setDomainManagerOpen(false)}
                className="bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2 rounded-lg text-xs font-semibold cursor-pointer border border-transparent h-9"
              >
                Fermer
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Import / Export Modal */}
      {importExportDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-xl w-full p-6 shadow-2xl space-y-5 flex flex-col max-h-[85vh]">
            <div>
              <h4 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                🔄 Import / Export
              </h4>
              <p className="text-slate-400 text-xs mt-1">
                Exportez le graphe de croyances ou importez des formats standards (AIF / SADFace / GraphML / DOT).
              </p>
            </div>

            {/* Export Links */}
            <div className="grid grid-cols-2 gap-3">
              <a
                href={`${API_BASE}/export/aif`}
                target="_blank"
                rel="noreferrer"
                className="p-3 rounded-xl border border-slate-805 bg-slate-950/20 hover:border-indigo-500/50 hover:bg-slate-900/40 text-center transition-all block border decoration-none"
              >
                <span className="text-xs font-bold text-slate-200 block">AIF JSON</span>
                <span className="text-[10px] text-slate-500">Argument Interchange Format</span>
              </a>
              <a
                href={`${API_BASE}/export/sadface`}
                target="_blank"
                rel="noreferrer"
                className="p-3 rounded-xl border border-slate-805 bg-slate-950/20 hover:border-indigo-500/50 hover:bg-slate-900/40 text-center transition-all block border decoration-none"
              >
                <span className="text-xs font-bold text-slate-200 block">SADFace JSON</span>
                <span className="text-[10px] text-slate-500">Structured Argument Data format</span>
              </a>
              <a
                href={`${API_BASE}/export/graphml`}
                target="_blank"
                rel="noreferrer"
                className="p-3 rounded-xl border border-slate-805 bg-slate-950/20 hover:border-indigo-500/50 hover:bg-slate-900/40 text-center transition-all block border decoration-none"
              >
                <span className="text-xs font-bold text-slate-200 block">GraphML</span>
                <span className="text-[10px] text-slate-500">Gephi & Cytoscape XML format</span>
              </a>
              <a
                href={`${API_BASE}/export/dot`}
                target="_blank"
                rel="noreferrer"
                className="p-3 rounded-xl border border-slate-805 bg-slate-950/20 hover:border-indigo-500/50 hover:bg-slate-900/40 text-center transition-all block border decoration-none"
              >
                <span className="text-xs font-bold text-slate-200 block">DOT format</span>
                <span className="text-[10px] text-slate-500">Graphviz layout definition</span>
              </a>
            </div>

            {/* Import Block */}
            <div className="flex-1 flex flex-col gap-3 min-h-[200px]">
              <h5 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Importer des données</h5>
              <div className="flex gap-3 text-xs mb-1">
                <button
                  onClick={() => setImportFormat("native")}
                  className={`px-3 py-1.5 rounded-lg border font-semibold cursor-pointer ${
                    importFormat === "native"
                      ? "bg-indigo-600/20 border-indigo-500 text-indigo-300"
                      : "bg-slate-950 border-slate-800 text-slate-400"
                  }`}
                >
                  Format Natif
                </button>
                <button
                  onClick={() => setImportFormat("aif")}
                  className={`px-3 py-1.5 rounded-lg border font-semibold cursor-pointer ${
                    importFormat === "aif"
                      ? "bg-indigo-600/20 border-indigo-500 text-indigo-300"
                      : "bg-slate-950 border-slate-800 text-slate-400"
                  }`}
                >
                  AIF JSON
                </button>
                <button
                  onClick={() => setImportFormat("sadface")}
                  className={`px-3 py-1.5 rounded-lg border font-semibold cursor-pointer ${
                    importFormat === "sadface"
                      ? "bg-indigo-600/20 border-indigo-500 text-indigo-300"
                      : "bg-slate-950 border-slate-800 text-slate-400"
                  }`}
                >
                  SADFace JSON
                </button>
              </div>

              <textarea
                value={importPayloadText}
                onChange={(e) => setImportPayloadText(e.target.value)}
                placeholder={
                  importFormat === "native"
                    ? "Collez ici le JSON natif (Second Brain) à importer..."
                    : `Collez ici le JSON ${importFormat.toUpperCase()} à importer...`
                }
                className="flex-1 w-full bg-slate-950 border border-slate-800 text-xs rounded-xl p-3.5 text-slate-200 font-mono outline-none focus:border-indigo-500 transition-colors resize-none"
              />

              {importError && (
                <div className="text-xs text-rose-400 font-semibold p-2.5 rounded-lg bg-rose-950/20 border border-rose-900/30">
                  ❌ {importError}
                </div>
              )}

              <Button
                onClick={async () => {
                  if (!importPayloadText.trim()) return;
                  setImportError("");
                  try {
                    const parsed = JSON.parse(importPayloadText);
                    const endpoint =
                      importFormat === "native"
                        ? "import"
                        : importFormat === "aif"
                        ? "import/aif"
                        : "import/sadface";
                    const res = await fetch(`${API_BASE}/${endpoint}`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify(parsed),
                    });
                    if (!res.ok) {
                      const errData = await res.json().catch(() => ({}));
                      throw new Error(errData.detail || "Erreur de format ou de validation lors de l'import");
                    }
                    queryClient.invalidateQueries({ queryKey: ["graph"] });
                    queryClient.invalidateQueries({ queryKey: ["tensions"] });
                    queryClient.invalidateQueries({ queryKey: ["domains"] });
                    alert("Importation réussie avec succès !");
                    setImportPayloadText("");
                    setImportExportDialogOpen(false);
                  } catch (e) {
                    setImportError((e as Error).message || "JSON Invalide");
                  }
                }}
                className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold px-4 cursor-pointer h-9 flex items-center justify-center gap-1.5"
              >
                <span>Lancer l&apos;Importation</span>
              </Button>
            </div>

            <div className="flex justify-end pt-3 border-t border-slate-800">
              <Button
                onClick={() => setImportExportDialogOpen(false)}
                className="bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-800 px-5 py-2 rounded-lg text-xs font-semibold cursor-pointer h-9"
              >
                Fermer
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Note de Synthèse Modal */}
      {noteModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 shadow-2xl space-y-5 flex flex-col max-h-[85vh]">
            <div>
              <h4 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                ✍️ Générateur de Notes de Synthèse
              </h4>
              <p className="text-slate-400 text-xs mt-1">
                Compilez les résultats du solveur et du réseau causal pour une branche ou une thèse et produisez une note de synthèse structurée en Markdown.
              </p>
            </div>

            {/* Selection Options */}
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="flex-1 flex flex-col gap-1">
                <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Par Branche (Domaine)</span>
                <select
                  defaultValue=""
                  onChange={(e) => {
                    const val = e.target.value;
                    if (val) {
                      generateNoteMutation.mutate(
                        { domain: val, node_id: null },
                        {
                          onSuccess: (res) => setGeneratedNoteText(res.note),
                          onError: (err) => setGeneratedNoteText(`Erreur : ${err.message}`),
                        }
                      );
                    }
                  }}
                  className="bg-slate-900 border border-slate-800 text-xs rounded-xl px-3 py-2 text-slate-200 outline-none focus:border-indigo-500 transition-colors"
                >
                  <option value="">Sélectionnez une branche</option>
                  {domains?.map((dom) => (
                    <option key={dom.id} value={dom.name}>
                      {dom.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex-1 flex flex-col gap-1">
                <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Par Thèse (Claim)</span>
                <select
                  defaultValue=""
                  onChange={(e) => {
                    const val = e.target.value;
                    if (val) {
                      generateNoteMutation.mutate(
                        { domain: null, node_id: val },
                        {
                          onSuccess: (res) => setGeneratedNoteText(res.note),
                          onError: (err) => setGeneratedNoteText(`Erreur : ${err.message}`),
                        }
                      );
                    }
                  }}
                  className="bg-slate-900 border border-slate-800 text-xs rounded-xl px-3 py-2 text-slate-200 outline-none focus:border-indigo-500 transition-colors"
                >
                  <option value="">Sélectionnez une proposition</option>
                  {graphData?.nodes.map((node) => (
                    <option key={node.id} value={node.id}>
                      {node.text.substring(0, 50)}...
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Note text viewer */}
            <div className="flex-1 overflow-y-auto min-h-[250px] bg-slate-950 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
              {generateNoteMutation.isPending ? (
                <div className="flex-1 flex flex-col items-center justify-center gap-2 text-slate-500">
                  <RefreshCw className="w-8 h-8 animate-spin text-indigo-500" />
                  <span className="text-xs font-semibold">Génération de la note en cours...</span>
                </div>
              ) : generatedNoteText ? (
                <div className="flex-1 flex flex-col justify-between">
                  <div className="text-xs text-slate-300 font-mono leading-relaxed whitespace-pre-wrap select-text max-h-[350px] overflow-y-auto pr-1">
                    {generatedNoteText}
                  </div>
                  <div className="mt-4 pt-3 border-t border-slate-900/60 flex justify-end">
                    <Button
                      onClick={() => {
                        navigator.clipboard.writeText(generatedNoteText);
                        alert("Note copiée dans le presse-papiers !");
                      }}
                      className="bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold px-4 cursor-pointer h-8 flex items-center gap-1.5"
                    >
                      Copier la note
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center text-slate-500 py-12">
                  <BookOpen className="w-8 h-8 text-slate-700 mb-2" />
                  <p className="text-xs">Sélectionnez une branche ou une proposition ci-dessus pour générer une note.</p>
                </div>
              )}
            </div>

            <div className="flex justify-end pt-3 border-t border-slate-800">
              <Button
                onClick={() => setNoteModalOpen(false)}
                className="bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-800 px-5 py-2 rounded-lg text-xs font-semibold cursor-pointer h-9"
              >
                Fermer
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="border-t border-slate-900 py-4 bg-slate-950 text-center text-[10px] text-slate-600">
        <div className="max-w-7xl mx-auto px-6">
          Graph Visualization Engine • React Flow & Cytoscape.js Integration • Second Brain
        </div>
      </footer>
    </div>
  );
}
