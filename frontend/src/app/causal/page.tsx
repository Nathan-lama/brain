"use client";

import React, { useState, useMemo, useCallback } from "react";
import { ReactFlow, Controls, Background, MarkerType, Handle, Position } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  useCausalGraph,
  useAddCausalEdge,
  useDeleteCausalEdge,
  useWhatIf,
  NodeOut,
  CausalEdgeOut,
  WhatIfResponse
} from "@/hooks/use-graph-api";
import { Button } from "@/components/ui/button";
import { getTierInfo, floatToTierLabel } from "@/components/graph/custom-node";
import {
  Sliders,
  Link2,
  Trash2,
  AlertTriangle,
  ArrowLeft,
  Info,
  RefreshCw,
  Zap,
  Play
} from "lucide-react";
import LinkNext from "next/link";

interface CustomCausalNodeData {
  id: string;
  text: string;
  domain: string;
  confidence?: number;
  tier?: string | null;
  weight?: number;
  baselineCredence?: number | null;
  intervenedCredence?: number | null;
  interventionVal?: number;
  setIntervention: (nodeId: string, val: number | undefined) => void;
  metadata?: { tier?: string | null } | null;
}

// Custom Node for Causal DAG
function CustomCausalNode({ data }: { data: CustomCausalNodeData }) {
  const { text, domain, confidence, tier, weight, id, baselineCredence, intervenedCredence, interventionVal, setIntervention } = data;
  const isIntervened = interventionVal !== undefined;

  const actualWeight = weight !== undefined ? weight : (confidence !== undefined ? confidence : 0.6);
  const actualTier = tier || data.metadata?.tier;
  const priorTierInfo = getTierInfo(actualTier, actualWeight);

  const currentCred = intervenedCredence !== undefined ? intervenedCredence : (baselineCredence ?? actualWeight);
  const currentTierLabel = floatToTierLabel(currentCred ?? 0.6);
  const currentTierInfo = getTierInfo(null, currentCred ?? 0.6);

  return (
    <div className="relative group">
      <Handle
        type="target"
        position={Position.Top}
        className="opacity-0 group-hover:opacity-100 transition-opacity !bg-indigo-500 !w-2 !h-2"
      />

      <div
        className={`w-72 border backdrop-blur-xl rounded-xl p-4 shadow-xl transition-all duration-300 ${
          isIntervened
            ? "border-purple-500 shadow-purple-500/10 bg-purple-950/20"
            : "border-slate-800 bg-slate-900/30 hover:border-slate-700/50"
        }`}
      >
        {/* Accent Bar */}
        <div
          className={`absolute top-0 left-0 right-0 h-1 rounded-t-xl bg-gradient-to-r ${
            isIntervened ? "from-purple-500 to-indigo-500" : "from-indigo-500 to-cyan-500"
          }`}
        />

        <div className="flex items-center justify-between mb-2 mt-1">
          <span className="text-[9px] font-bold uppercase tracking-wider text-indigo-400">
            Empirique
          </span>
          <span className="text-[9px] px-2 py-0.5 rounded-full bg-slate-950/80 border border-slate-850 text-slate-400 font-semibold uppercase tracking-wide">
            {domain}
          </span>
        </div>

        <p className="text-slate-200 font-semibold text-xs leading-relaxed mb-3 line-clamp-3 select-none">
          {text}
        </p>

        {/* Credence comparison */}
        <div className="space-y-2 border-t border-slate-800/40 pt-2.5 mt-2">
          <div className="flex justify-between items-center text-[10px] text-slate-400 font-medium">
            <span>Prior / Base:</span>
            <span className="font-bold text-slate-300 inline-flex items-center gap-1.5">
              <span className={`inline-block w-1.5 h-1.5 rounded-full ${priorTierInfo.color}`} />
              {priorTierInfo.label}
            </span>
          </div>

          <div className="flex justify-between items-center text-[10px] text-slate-400 font-medium">
            <span>Crédence Actuelle:</span>
            <span className={`font-bold ${isIntervened ? "text-purple-400" : "text-emerald-400"} inline-flex items-center gap-1.5`}>
              <span className={`inline-block w-1.5 h-1.5 rounded-full ${currentTierInfo.color}`} />
              {currentTierLabel}
            </span>
          </div>

          {/* Intervention actions */}
          <div className="flex items-center gap-1.5 pt-1">
            <span className="text-[9px] text-slate-500 font-bold uppercase shrink-0">do() :</span>
            <button
              onClick={() => setIntervention(id, 1)}
              className={`text-[9px] font-bold px-2 py-0.5 rounded cursor-pointer transition-colors ${
                interventionVal === 1
                  ? "bg-purple-600 text-white"
                  : "bg-slate-950 text-slate-400 hover:text-slate-200 border border-slate-850"
              }`}
            >
              do(1)
            </button>
            <button
              onClick={() => setIntervention(id, 0)}
              className={`text-[9px] font-bold px-2 py-0.5 rounded cursor-pointer transition-colors ${
                interventionVal === 0
                  ? "bg-purple-600 text-white"
                  : "bg-slate-950 text-slate-400 hover:text-slate-200 border border-slate-850"
              }`}
            >
              do(0)
            </button>
            {isIntervened && (
              <button
                onClick={() => setIntervention(id, undefined)}
                className="text-[8px] font-bold text-slate-500 hover:text-rose-400 ml-auto"
              >
                Reset
              </button>
            )}
          </div>
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="opacity-0 group-hover:opacity-100 transition-opacity !bg-indigo-500 !w-2 !h-2"
      />
    </div>
  );
}

const nodeTypes = {
  customCausal: CustomCausalNode,
};

// Layout positioning helper
function layoutCausalNodes(nodes: NodeOut[], edges: CausalEdgeOut[]) {
  const inDegree: Record<string, number> = {};
  nodes.forEach(n => inDegree[n.id] = 0);
  edges.forEach(e => {
    if (inDegree[e.effect_id] !== undefined) {
      inDegree[e.effect_id]++;
    }
  });

  const columns: Record<number, NodeOut[]> = { 0: [], 1: [], 2: [], 3: [] };
  nodes.forEach(node => {
    const deg = inDegree[node.id] || 0;
    const col = Math.min(deg, 3);
    columns[col].push(node);
  });

  const colWidth = 350;
  const rowHeight = 180;

  return nodes.map(node => {
    const deg = inDegree[node.id] || 0;
    const col = Math.min(deg, 3);
    const list = columns[col];
    const index = list.findIndex(n => n.id === node.id);
    const totalHeight = list.length * rowHeight;
    const yOffset = -totalHeight / 2 + 90;

    return {
      id: node.id,
      type: "customCausal",
      data: node,
      position: {
        x: col * colWidth + 50,
        y: yOffset + index * rowHeight
      }
    };
  });
}

export default function CausalPage() {
  const { data: causalGraph, isLoading } = useCausalGraph();
  const addCausalEdgeMutation = useAddCausalEdge();
  const deleteCausalEdgeMutation = useDeleteCausalEdge();
  const whatifMutation = useWhatIf();

  // Interventions state: Record<node_id, state_value (0 or 1)>
  const [interventions, setInterventions] = useState<Record<string, number>>({});
  const [whatifResult, setWhatifResult] = useState<WhatIfResponse | null>(null);

  // Form states
  const [causeId, setCauseId] = useState<string>("");
  const [effectId, setEffectId] = useState<string>("");
  const [strength, setStrength] = useState<number>(0.5);
  const [formError, setFormError] = useState<string>("");

  const setIntervention = useCallback((nodeId: string, val: number | undefined) => {
    setInterventions((prev) => {
      const updated = { ...prev };
      if (val === undefined) {
        delete updated[nodeId];
      } else {
        updated[nodeId] = val;
      }
      return updated;
    });
  }, []);

  const handleRunWhatIf = async () => {
    try {
      const res = await whatifMutation.mutateAsync({ interventions });
      setWhatifResult(res);
    } catch (err) {
      console.error(err);
    }
  };

  const handleResetInterventions = () => {
    setInterventions({});
    setWhatifResult(null);
  };

  const handleAddEdge = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");
    if (!causeId || !effectId) {
      setFormError("Veuillez sélectionner une cause et un effet.");
      return;
    }
    if (causeId === effectId) {
      setFormError("La cause et l'effet ne peuvent pas être le même claim.");
      return;
    }

    try {
      await addCausalEdgeMutation.mutateAsync({
        cause_id: causeId,
        effect_id: effectId,
        strength
      });
      setCauseId("");
      setEffectId("");
      setStrength(0.5);
    } catch (err) {
      setFormError((err as Error).message || "Erreur de création de lien causal.");
    }
  };

  // Map backend elements to React Flow
  const reactFlowNodes = useMemo(() => {
    if (!causalGraph?.nodes) return [];
    const laidOut = layoutCausalNodes(causalGraph.nodes, causalGraph.edges);
    return laidOut.map(n => ({
      ...n,
      data: {
        ...n.data,
        baselineCredence: whatifResult ? undefined : undefined, // can be extended
        intervenedCredence: whatifResult?.credences[n.id],
        interventionVal: interventions[n.id],
        setIntervention
      }
    }));
  }, [causalGraph, interventions, whatifResult, setIntervention]);

  const reactFlowEdges = useMemo(() => {
    if (!causalGraph?.edges) return [];
    return causalGraph.edges.map(e => ({
      id: e.id,
      source: e.cause_id,
      target: e.effect_id,
      style: {
        stroke: "#a78bfa", // Purple edge color
        strokeWidth: 2.5,
      },
      animated: true,
      label: `w = ${e.strength.toFixed(2)}`,
      labelStyle: { fill: "#a78bfa", fontWeight: 700, fontSize: 9 },
      labelBgPadding: [4, 4] as [number, number],
      labelBgBorderRadius: 4,
      labelBgStyle: { fill: "#090d16", fillOpacity: 0.85, stroke: "#1e1b4b", strokeWidth: 1 },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: "#a78bfa",
        width: 14,
        height: 14,
      },
    }));
  }, [causalGraph]);

  const nodeMap = useMemo(() => {
    if (!causalGraph?.nodes) return new Map<string, NodeOut>();
    return new Map(causalGraph.nodes.map(n => [n.id, n]));
  }, [causalGraph]);

  return (
    <div className="relative min-h-screen w-full bg-slate-950 text-slate-100 flex flex-col justify-between selection:bg-indigo-500 selection:text-white">
      {/* Background gradients */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(167,139,250,0.03),transparent_50%),radial-gradient(circle_at_bottom_left,rgba(99,102,241,0.03),transparent_50%)] pointer-events-none" />

      {/* Header */}
      <header className="border-b border-slate-900 bg-slate-950/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <LinkNext href="/graph">
              <Button variant="ghost" size="icon-sm" className="text-slate-400 hover:text-slate-200 cursor-pointer">
                <ArrowLeft className="w-4 h-4" />
              </Button>
            </LinkNext>
            <div className="flex items-center gap-2.5">
              <div className="relative flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-purple-500 to-indigo-600 shadow-md shadow-purple-500/20">
                <Zap className="w-4.5 h-4.5 text-white" />
              </div>
              <span className="font-semibold tracking-tight text-base bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-200 to-slate-400">
                Couche Causale (Branches)
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs">
            <span className="text-slate-500">Moteur pgmpy & Pearl</span>
          </div>
        </div>
      </header>

      {/* Epistemic warning bar */}
      <section className="bg-slate-950 py-3 px-6 border-b border-slate-900">
        <div className="bg-amber-950/10 border border-amber-500/20 text-amber-200/90 p-4 rounded-xl flex items-start gap-3.5 text-xs leading-relaxed max-w-7xl mx-auto shadow-md">
          <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5 animate-pulse" />
          <div>
            <span className="font-bold text-amber-400 block mb-0.5">⚠️ Avertissement Épistémique Obligatoire</span>
            Les graphes orientés acycliques (DAG), les probabilités conditionnelles (CPD) et les forces de liaisons causales modélisés ci-dessous sont des <strong>hypothèses de travail</strong> destinées à guider le raisonnement éthique et la délibération. Ils ne sont <strong>pas</strong> issus d&apos;études empiriques réelles ou de prédictions scientifiques. Ne prétendez jamais que ce réseau fournit des prévisions de données empiriques réelles.
          </div>
        </div>
      </section>

      {/* Main Viewport */}
      <main className="flex-1 w-full relative overflow-hidden h-[calc(100vh-14rem)] flex">
        {isLoading ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-slate-950/80 backdrop-blur-xs z-10">
            <span className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500" />
            <span className="text-slate-400 text-xs font-semibold uppercase tracking-wider">
              Chargement du Graphe Causal...
            </span>
          </div>
        ) : !causalGraph || causalGraph.nodes.length === 0 ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-slate-500 z-10 max-w-sm mx-auto text-center">
            <Info className="w-8 h-8 text-slate-600 mb-1" />
            <span className="font-semibold text-sm">Aucun nœud empirique trouvé.</span>
            <span className="text-xs">
              Pour peupler ce réseau bayésien, créez des claims de type <strong>Empirique</strong> dans l&apos;Éditeur de Graphe principal.
            </span>
          </div>
        ) : (
          <div className="flex-1 h-full relative">
            <ReactFlow
              nodes={reactFlowNodes}
              edges={reactFlowEdges}
              nodeTypes={nodeTypes}
              fitView
              minZoom={0.2}
              maxZoom={1.5}
            >
              <Background color="#1e1b4b" gap={20} size={1} />
              <Controls className="!bg-slate-900 !border-slate-800 !text-slate-300" />
            </ReactFlow>
          </div>
        )}

        {/* Sidebar Controls (Causal Links and Interventions) */}
        {!isLoading && causalGraph && causalGraph.nodes.length > 0 && (
          <aside className="w-96 border-l border-slate-900 bg-slate-950/90 backdrop-blur-md p-5 flex flex-col justify-between h-full z-10 overflow-hidden">
            <div className="flex-1 overflow-y-auto space-y-6 pr-1">
              
              {/* Do-calculus control panel */}
              <div className="space-y-3.5 bg-slate-900/10 p-4 rounded-xl border border-slate-900">
                <h3 className="text-xs font-bold text-purple-400 uppercase tracking-wider flex items-center gap-1.5">
                  <Sliders className="w-4 h-4" />
                  Interventions do-Calculus
                </h3>
                <p className="text-[10px] text-slate-400 leading-relaxed">
                  Activez des interventions de type $do(X=1)$ (haute) ou $do(X=0)$ (basse) en cliquant sur les boutons des nœuds, puis lancez le simulateur.
                </p>

                <div className="space-y-2.5 pt-1">
                  {Object.keys(interventions).length === 0 ? (
                    <div className="text-[10px] text-slate-500 italic">Aucune intervention active.</div>
                  ) : (
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(interventions).map(([nid, val]) => {
                        const name = nodeMap.get(nid)?.text || nid;
                        return (
                          <span key={nid} className="text-[9px] font-semibold bg-purple-950/50 border border-purple-800/60 text-purple-300 px-2 py-0.5 rounded flex items-center gap-1 max-w-full truncate">
                            <span className="truncate">{name.substring(0, 16)}...</span>
                            <span className="font-bold font-mono">={val}</span>
                          </span>
                        );
                      })}
                    </div>
                  )}

                  <div className="flex gap-2 pt-1.5">
                    <Button
                      onClick={handleRunWhatIf}
                      disabled={Object.keys(interventions).length === 0 || whatifMutation.isPending}
                      className="flex-1 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-[10px] font-bold h-8 flex items-center gap-1 cursor-pointer"
                    >
                      {whatifMutation.isPending ? (
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Play className="w-3 h-3 fill-current" />
                      )}
                      <span>Simuler do()</span>
                    </Button>

                    <Button
                      onClick={handleResetInterventions}
                      className="bg-slate-900 border border-slate-800 text-slate-400 text-[10px] hover:text-slate-200 rounded-lg h-8 cursor-pointer"
                    >
                      Reset
                    </Button>
                  </div>
                </div>

                {/* Whatif Description Output */}
                {whatifResult && (
                  <div className="mt-4 p-3 bg-purple-950/5 border border-purple-500/20 rounded-lg space-y-2 text-[10px]">
                    <div className="font-bold text-purple-400">Propagation des Effets :</div>
                    <div className="space-y-1 max-h-40 overflow-y-auto font-medium leading-relaxed text-slate-300">
                      {whatifResult.readable_effects.map((line: string, idx: number) => (
                        <div key={idx} className={idx === 0 ? "text-purple-300 font-bold" : ""}>
                          {line}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Form to Add Causal Link */}
              <form onSubmit={handleAddEdge} className="space-y-4 border border-slate-900 p-4 rounded-xl">
                <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                  <Link2 className="w-4 h-4 text-indigo-400" />
                  Créer un Lien Causal
                </h3>

                <div className="space-y-3 text-xs">
                  {/* Cause Dropdown */}
                  <div className="space-y-1">
                    <label className="text-[10px] text-slate-400 font-bold uppercase">Cause (X)</label>
                    <select
                      value={causeId}
                      onChange={e => setCauseId(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-800 text-slate-200 rounded-lg p-2 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 outline-none"
                    >
                      <option value="">Sélectionner la cause...</option>
                      {causalGraph.nodes.map(n => (
                        <option key={n.id} value={n.id}>{n.text.substring(0, 48)}...</option>
                      ))}
                    </select>
                  </div>

                  {/* Effect Dropdown */}
                  <div className="space-y-1">
                    <label className="text-[10px] text-slate-400 font-bold uppercase">Effet (Y)</label>
                    <select
                      value={effectId}
                      onChange={e => setEffectId(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-800 text-slate-200 rounded-lg p-2 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 outline-none"
                    >
                      <option value="">Sélectionner l&apos;effet...</option>
                      {causalGraph.nodes.map(n => (
                        <option key={n.id} value={n.id}>{n.text.substring(0, 48)}...</option>
                      ))}
                    </select>
                  </div>

                  {/* Strength Slider */}
                  <div className="space-y-1.5">
                    <div className="flex justify-between text-[10px] text-slate-400 font-bold uppercase">
                      <span>Force causale (w)</span>
                      <span className="font-mono text-indigo-400 font-bold">{strength.toFixed(2)}</span>
                    </div>
                    <input
                      type="range"
                      min="0.0"
                      max="1.0"
                      step="0.05"
                      value={strength}
                      onChange={e => setStrength(parseFloat(e.target.value))}
                      className="w-full h-1.5 bg-slate-900 rounded-lg appearance-none cursor-pointer accent-indigo-500"
                    />
                  </div>

                  {formError && <div className="text-[10px] text-red-400 font-bold">{formError}</div>}

                  <Button
                    type="submit"
                    disabled={addCausalEdgeMutation.isPending}
                    className="w-full bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-bold text-xs h-9 cursor-pointer"
                  >
                    {addCausalEdgeMutation.isPending ? "Création..." : "Ajouter le lien"}
                  </Button>
                </div>
              </form>

              {/* List of existing links */}
              <div className="space-y-2.5">
                <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
                  Liens causaux existants ({causalGraph.edges.length})
                </h3>
                <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                  {causalGraph.edges.map(edge => {
                    const causeName = nodeMap.get(edge.cause_id)?.text || "Cause";
                    const effectName = nodeMap.get(edge.effect_id)?.text || "Effet";
                    return (
                      <div key={edge.id} className="p-3 bg-slate-900/25 border border-slate-900 rounded-xl flex items-center justify-between gap-4">
                        <div className="flex-1 min-w-0 text-[10px] space-y-1">
                          <div className="font-semibold text-slate-300 truncate">
                            {causeName.substring(0, 32)}...
                          </div>
                          <div className="text-slate-500 font-bold flex items-center gap-1 select-none">
                            <span>➜</span>
                            <span className="text-indigo-400 font-mono">w = {edge.strength}</span>
                          </div>
                          <div className="font-semibold text-slate-300 truncate">
                            {effectName.substring(0, 32)}...
                          </div>
                        </div>
                        <button
                          onClick={async () => {
                            if (confirm("Supprimer ce lien causal ?")) {
                              await deleteCausalEdgeMutation.mutateAsync(edge.id);
                            }
                          }}
                          disabled={deleteCausalEdgeMutation.isPending}
                          className="text-slate-500 hover:text-rose-400 p-1.5 hover:bg-slate-900 rounded transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>

            </div>

            <div className="border-t border-slate-900 pt-3 mt-4 text-center text-[10px] text-slate-600">
              Modélisation décisionnelle Pearl / pgmpy
            </div>
          </aside>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 py-3 bg-slate-950 text-center text-[10px] text-slate-600">
        <div className="max-w-7xl mx-auto px-6">
          Bayesian Network Inference Engine • Second Brain
        </div>
      </footer>
    </div>
  );
}
