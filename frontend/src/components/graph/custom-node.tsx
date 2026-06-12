"use client";

import React from "react";
import { Handle, Position } from "@xyflow/react";

const TYPE_COLORS: Record<string, { border: string; bg: string; text: string; label: string }> = {
  descriptif: {
    border: "border-indigo-500 shadow-indigo-500/10",
    bg: "bg-indigo-950/30",
    text: "text-indigo-400",
    label: "Descriptif",
  },
  empirique: {
    border: "border-emerald-500 shadow-emerald-500/10",
    bg: "bg-emerald-950/30",
    text: "text-emerald-400",
    label: "Empirique",
  },
  normatif_position: {
    border: "border-purple-500 shadow-purple-500/10",
    bg: "bg-purple-950/30",
    text: "text-purple-400",
    label: "Normatif Position",
  },
  normatif_conclusion: {
    border: "border-pink-500 shadow-pink-500/10",
    bg: "bg-pink-950/30",
    text: "text-pink-400",
    label: "Normatif Conclusion",
  },
  pont_normatif: {
    border: "border-amber-500 shadow-amber-500/10",
    bg: "bg-amber-950/30",
    text: "text-amber-400",
    label: "Pont Normatif",
  },
  definitionnel: {
    border: "border-slate-500 shadow-slate-500/10",
    bg: "bg-slate-950/30",
    text: "text-slate-400",
    label: "Définitionnel",
  },
};

export const TIER_DETAILS = {
  certain: { label: "Certain", color: "bg-emerald-500 shadow-emerald-500/50", text: "text-emerald-400" },
  fort: { label: "Fort", color: "bg-teal-500 shadow-teal-500/50", text: "text-teal-400" },
  moyen: { label: "Moyen", color: "bg-amber-500 shadow-amber-500/50", text: "text-amber-400" },
  faible: { label: "Faible", color: "bg-orange-500 shadow-orange-500/50", text: "text-orange-400" },
  speculatif: { label: "Spéculatif", color: "bg-rose-500 shadow-rose-500/50", text: "text-rose-400" },
};

export const getTierInfo = (tier: string | null | undefined, weight: number | undefined) => {
  if (weight === 0.0) {
    return { label: "Exclu / Révisé", color: "bg-slate-500 shadow-slate-500/50", text: "text-slate-400" };
  }
  if (!tier) {
    if (weight !== undefined) {
      if (weight > 0.875) return TIER_DETAILS.certain;
      if (weight > 0.700) return TIER_DETAILS.fort;
      if (weight > 0.500) return TIER_DETAILS.moyen;
      if (weight > 0.300) return TIER_DETAILS.faible;
      return TIER_DETAILS.speculatif;
    }
    return TIER_DETAILS.moyen;
  }
  return TIER_DETAILS[tier as keyof typeof TIER_DETAILS] || TIER_DETAILS.moyen;
};

export const floatToTierLabel = (val: number) => {
  if (val > 0.875) return "Certain";
  if (val > 0.700) return "Fort";
  if (val > 0.500) return "Moyen";
  if (val > 0.300) return "Faible";
  return "Spéculatif";
};

export interface CustomGraphNodeData {
  text: string;
  type: string;
  domain: string;
  confidence?: number;
  tier?: string | null;
  weight?: number;
  isTension?: boolean;
  isCoherenceActive?: boolean;
  isAccepted?: boolean;
  isRejected?: boolean;
  isDiff?: boolean;
  coherence?: string;
  correspondence?: number | null;
  overcommitted?: boolean;
  gap?: number | null;
  metadata?: { tier?: string | null } | null;
  label_court?: string | null;
}

export function CustomGraphNode({ data, selected }: { data: CustomGraphNodeData; selected?: boolean }) {
  const { text, type, domain, confidence, tier, weight, isTension, isCoherenceActive, isAccepted, isRejected, isDiff, coherence, correspondence, overcommitted, gap, label_court } = data;
  const colors = TYPE_COLORS[type] || TYPE_COLORS.descriptif;
  
  const isFactual = ["descriptif", "empirique", "definitionnel"].includes(type);
  const actualTier = tier || data.metadata?.tier;
  const actualWeight = weight !== undefined ? weight : (confidence !== undefined ? confidence : 0.6);
  const tierInfo = getTierInfo(actualTier, actualWeight);

  if (type === "pont_normatif") {
    let diamondBorder = "border-2 " + colors.border;
    let diamondBg = colors.bg;
    let diamondOpacity = "";
    let diamondRing = "";
    const indicatorColor = tierInfo.color;

    if (isCoherenceActive) {
      if (isAccepted) {
        diamondBorder = "border-2 border-emerald-500 shadow-lg shadow-emerald-500/20";
        diamondBg = "bg-emerald-950/30";
      } else if (isRejected) {
        if (isTension) {
          diamondBorder = "border-2 border-rose-500/70 shadow-md shadow-rose-900/10";
          diamondBg = "bg-rose-950/20";
        } else {
          diamondBorder = "border-2 border-slate-800 shadow-slate-950/10";
          diamondBg = "bg-slate-900/20";
        }
        diamondOpacity = "opacity-60 hover:opacity-85 transition-opacity";
      }

      if (isDiff) {
        diamondRing = "ring-2 ring-indigo-500 ring-offset-2 ring-offset-slate-950 animate-pulse shadow-lg shadow-indigo-500/50";
      }
    } else {
      if (selected) {
        diamondRing = "ring-2 ring-indigo-500 ring-offset-2 ring-offset-slate-950";
      }
      if (isTension) {
        diamondRing = diamondRing ? `${diamondRing} ring-2 ring-red-500 border-red-500/80` : "ring-2 ring-red-500 shadow-lg shadow-red-500/30 border-red-500/80";
      }
    }

    return (
      <div className={`relative group ${diamondOpacity}`}>
        <Handle
          type="target"
          position={Position.Top}
          className="opacity-0 group-hover:opacity-100 transition-opacity !bg-amber-500 !w-2 !h-2"
        />

        {overcommitted && (
          <div className="absolute -top-6 left-1/2 -translate-x-1/2 z-10 px-2 py-0.5 rounded bg-amber-500/20 border border-amber-500/40 text-amber-400 text-[8px] font-bold uppercase tracking-wider whitespace-nowrap shadow-md animate-pulse">
            ⚠️ SUR-ENGAGEMENT (+{gap})
          </div>
        )}

        {/* Diamond Container */}
        <div
          className={`w-28 h-28 rotate-45 ${diamondBorder} ${diamondBg} backdrop-blur-xl rounded-xl flex items-center justify-center shadow-lg transition-transform duration-200 group-hover:scale-105 ${diamondRing}`}
        >
          <div className="-rotate-45 text-center p-2.5 flex flex-col items-center justify-center relative group/tooltip w-full h-full">
            <span className="text-[8px] font-bold text-amber-400/80 uppercase tracking-widest leading-none mb-1">
              Pont {label_court ? `• ${label_court.toUpperCase()}` : ""}
            </span>
            <p className="text-[10px] font-semibold text-amber-200 leading-snug max-h-16 overflow-hidden text-ellipsis line-clamp-3">
              {text}
            </p>
            {/* Small pastille dot */}
            <div className="absolute top-1 right-1">
              <span className={`inline-block w-1.5 h-1.5 rounded-full ${indicatorColor}`} />
            </div>
            
            {/* Tooltip */}
            <div className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-32 bg-slate-950 border border-slate-800 text-[9px] text-slate-400 p-1.5 rounded-lg shadow-xl opacity-0 group-hover/tooltip:opacity-100 transition-opacity duration-200 z-50">
              Engagement: <span className="font-bold text-slate-200">{tierInfo.label}</span>
            </div>
          </div>
        </div>

        <Handle
          type="source"
          position={Position.Bottom}
          className="opacity-0 group-hover:opacity-100 transition-opacity !bg-amber-500 !w-2 !h-2"
        />
      </div>
    );
  }

  // Compute borders and background based on Coherence Mode for standard card nodes
  let containerBorder = "border border-slate-800/80";
  let containerBg = colors.bg;
  let opacityClass = "";
  let extraRing = "";

  if (isCoherenceActive) {
    if (isAccepted) {
      containerBorder = "border border-emerald-500 shadow-emerald-500/20 shadow-lg";
      containerBg = "bg-emerald-950/20";
    } else if (isRejected) {
      if (isTension) {
        containerBorder = "border border-rose-500/70 shadow-rose-900/10 shadow-md";
        containerBg = "bg-rose-950/10";
      } else {
        containerBorder = "border border-slate-800 shadow-slate-950/10";
        containerBg = "bg-slate-900/20";
      }
      opacityClass = "opacity-60 hover:opacity-85 transition-opacity";
    }

    if (isDiff) {
      extraRing = "ring-2 ring-indigo-500 ring-offset-2 ring-offset-slate-950 animate-pulse shadow-lg shadow-indigo-500/50";
    }
  } else {
    if (selected) {
      extraRing = "ring-2 ring-indigo-500 ring-offset-2 ring-offset-slate-950";
    }
    if (isTension) {
      extraRing = extraRing ? `${extraRing} ring-2 ring-red-500 border-red-500/80` : "ring-2 ring-red-500 shadow-lg shadow-red-500/20 border-red-500/80";
    }
  }

  return (
    <div className={`relative group ${opacityClass}`}>
      <Handle
        type="target"
        position={Position.Top}
        className="opacity-0 group-hover:opacity-100 transition-opacity !bg-indigo-500 !w-2 !h-2"
      />

      {/* Card Container */}
      <div
        className={`w-64 ${containerBorder} ${containerBg} backdrop-blur-xl rounded-xl p-4 shadow-xl transition-all duration-300 group-hover:border-slate-700/50 hover:shadow-2xl ${extraRing}`}
      >
        {/* Border Accent Line */}
        <div
          className={`absolute top-0 left-0 right-0 h-1 rounded-t-xl bg-gradient-to-r ${
            type === "normatif_conclusion"
              ? "from-pink-500 to-indigo-500"
              : type === "normatif_position"
                ? "from-purple-500 to-indigo-500"
                : type === "descriptif"
                  ? "from-indigo-500 to-cyan-500"
                  : type === "empirique"
                    ? "from-emerald-500 to-teal-500"
                    : "from-slate-500 to-slate-400"
          }`}
        />

        <div className="flex items-center justify-between mb-2 mt-1">
          <div className="flex items-center gap-1.5">
            {label_court && (
              <span className="text-[10px] font-extrabold px-1 py-0.5 rounded bg-slate-950 border border-slate-900 text-slate-300">
                {label_court.toUpperCase()}
              </span>
            )}
            {/* Badge type */}
            <span className={`text-[9px] font-bold uppercase tracking-wider ${colors.text}`}>
              {colors.label}
            </span>
          </div>
          {/* Badge domain */}
          <span className="text-[9px] px-2 py-0.5 rounded-full bg-slate-950/80 border border-slate-850 text-slate-400 font-semibold uppercase tracking-wide">
            {domain}
          </span>
        </div>

        {overcommitted && (
          <div className="mb-2 px-2 py-0.5 rounded bg-amber-500/20 border border-amber-500/40 text-amber-400 text-[9px] font-bold uppercase tracking-wide text-center animate-pulse">
            ⚠️ SUR-ENGAGEMENT (+{gap})
          </div>
        )}

        {/* Text */}
        <p className="text-slate-200 font-semibold text-xs leading-relaxed mb-3 line-clamp-3 select-none">
          {text}
        </p>

        {/* Coherence / Correspondence badges */}
        <div className="flex flex-col gap-1.5 border-t border-slate-800/40 pt-2.5 mt-2.5 mb-2.5">
          <div className="flex items-center justify-between">
            <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">
              Cohérence
            </span>
            <span
              className={`text-[9px] px-2 py-0.5 rounded font-bold uppercase ${
                coherence === "accepted"
                  ? "bg-emerald-950/50 text-emerald-400 border border-emerald-800"
                  : coherence === "rejete_arbitre"
                    ? "bg-slate-900/80 text-slate-400 border border-slate-700"
                    : "bg-rose-950/50 text-rose-400 border border-rose-800"
              }`}
              title="Cohérence : statut de cette croyance dans le système"
            >
              {coherence === "accepted"
                ? "Cohérent"
                : coherence === "rejete_arbitre"
                  ? "Écarté par l'arbitrage"
                  : "En tension"}
            </span>
          </div>

          {type === "empirique" && correspondence !== undefined && correspondence !== null && (
            <div className="flex items-center justify-between">
              <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">
                Correspondance
              </span>
              <span
                className={`text-[9px] px-2 py-0.5 rounded font-bold uppercase ${
                  correspondence >= 0.875
                    ? "bg-emerald-950/50 text-emerald-400 border border-emerald-800"
                    : correspondence >= 0.7
                      ? "bg-teal-950/50 text-teal-400 border border-teal-800"
                      : correspondence >= 0.5
                        ? "bg-amber-950/50 text-amber-400 border border-amber-800"
                        : correspondence >= 0.3
                          ? "bg-orange-950/50 text-orange-400 border border-orange-800"
                          : "bg-rose-950/50 text-rose-400 border border-rose-800"
                }`}
                title="Correspondance : degré de preuve factuelle estimé par le réseau bayésien causal"
              >
                Crédence: {floatToTierLabel(correspondence)}
              </span>
            </div>
          )}
        </div>

        {/* Tier/Weight Indicator */}
        <div className="flex items-center justify-between border-t border-slate-800/40 pt-2.5 mt-2 relative group/tooltip">
          <span className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider cursor-help">
            {isFactual ? "Crédence" : "Engagement"}
          </span>
          <div className="flex items-center gap-2">
            <span className={`inline-block w-2 h-2 rounded-full ${tierInfo.color} shadow-sm animate-pulse`} />
            <span className="text-[10px] text-slate-300 font-bold">
              {tierInfo.label}
            </span>
          </div>
          
          {/* Custom Tooltip */}
          <div className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-52 bg-slate-950 border border-slate-800 text-[10px] text-slate-400 p-2.5 rounded-lg shadow-xl opacity-0 group-hover/tooltip:opacity-100 transition-opacity duration-200 z-50 leading-normal">
            {isFactual 
              ? "Crédence : force de croyance logique/factuelle dans cette affirmation." 
              : "Engagement : intensité de la valeur éthique ou politique accordée à cette action."}
          </div>
        </div>

        {/* Distinction warning footer */}
        <div className="mt-2.5 pt-1.5 border-t border-slate-900/60 flex items-center justify-center text-[8px] text-slate-600 font-medium">
          <span>* Cohérence ≠ Vérité factuelle</span>
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


export function CustomDomainGroupNode({ data }: { data: { label: string } }) {
  const { label } = data;
  return (
    <div className="w-full h-full border border-dashed border-slate-750/50 bg-slate-900/10 backdrop-blur-md rounded-2xl p-4 pointer-events-none">
      <div className="absolute -top-3 left-4 px-3 py-1 rounded-full bg-slate-950 border border-slate-800 text-[10px] font-bold uppercase tracking-wider text-indigo-400">
        📚 Domaine: {label}
      </div>
    </div>
  );
}


