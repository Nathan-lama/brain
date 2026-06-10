import { useQuery } from "@tanstack/react-query";
import { components } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type NodeOut = components["schemas"]["NodeOut"];
export type NodeType = components["schemas"]["NodeType"];

export type SchemeStrength = "deductif" | "defaisable_fort" | "defaisable_faible";

export type SchemeNodeOut = {
  id: string;
  scheme: "inference" | "conflit" | "preference";
  weight: number;
  strength?: SchemeStrength | null;
  metadata?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type FlatEdge = {
  id: string;
  source: string;
  target: string;
  relation: string;
  scheme_id: string;
  strength?: SchemeStrength | null;
  weight?: number | null;
};

export type GraphResponse = {
  nodes: NodeOut[];
  edges: FlatEdge[];
};

export type NodeDetailResponse = components["schemas"]["NodeDetailResponse"];
export type RelatedNodeResponse = components["schemas"]["RelatedNodeResponse"];
export type NodeNeighbor = components["schemas"]["NodeNeighbor"];

export function useGraph(domain?: string, type?: NodeType | "") {
  return useQuery<GraphResponse>({
    queryKey: ["graph", domain, type],
    queryFn: async () => {
      const url = new URL(`${API_BASE}/graph`);
      if (domain) url.searchParams.append("domain", domain);
      if (type) url.searchParams.append("type", type);

      const res = await fetch(url.toString());
      if (!res.ok) {
        throw new Error("Failed to fetch graph data");
      }
      return res.json();
    },
  });
}

export function useNode(id: string | null) {
  return useQuery<NodeDetailResponse>({
    queryKey: ["node", id],
    queryFn: async () => {
      if (!id) throw new Error("No node ID provided");
      const res = await fetch(`${API_BASE}/nodes/${id}`);
      if (!res.ok) {
        throw new Error(`Failed to fetch details for node ${id}`);
      }
      return res.json();
    },
    enabled: !!id,
  });
}

export function useRelated(id: string | null, k = 8) {
  return useQuery<RelatedNodeResponse[]>({
    queryKey: ["related", id, k],
    queryFn: async () => {
      if (!id) throw new Error("No node ID provided");
      const res = await fetch(`${API_BASE}/nodes/${id}/related?k=${k}`);
      if (!res.ok) {
        throw new Error(`Failed to fetch related suggestions for node ${id}`);
      }
      return res.json();
    },
    enabled: !!id,
  });
}

export type TensionOut = {
  id: string;
  type: "conflit_direct" | "cycle_incoherent" | "liaison_rompue";
  claims: NodeOut[];
  ponts: NodeOut[];
  score: number;
  poids?: number | null;
  scheme_id: string | null;
  paradoxe_assume: boolean;
};

export type TensionResolveRequest = {
  action: "reviser_node" | "accepter_paradoxe";
  node_id?: string | null;
  scheme_id?: string | null;
};

import { useMutation, useQueryClient } from "@tanstack/react-query";

export function useTensions() {
  return useQuery<TensionOut[]>({
    queryKey: ["tensions"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/tensions`);
      if (!res.ok) {
        throw new Error("Failed to fetch tensions");
      }
      return res.json();
    },
    refetchInterval: 5000,
  });
}

export type TensionDiffOut = {
  tensions_resolues: TensionOut[];
  tensions_nouvelles: TensionOut[];
  claims_affectes: NodeOut[];
};

export type EventPayload = {
  text?: string | null;
  scheme?: string | null;
  role?: string | null;
  tier?: string | null;
  confidence?: number | null;
  weight?: number | null;
  metadata?: {
    paradoxe_assume?: boolean;
    [key: string]: unknown;
  } | null;
  [key: string]: unknown;
};

export type EventOut = {
  id: string;
  entity_type: string;
  entity_id: string;
  op: "create" | "update" | "delete";
  before: EventPayload | null;
  after: EventPayload | null;
  created_at: string;
};

export type SnapshotOut = {
  id: string;
  label: string;
  created_at: string;
  payload: unknown;
};

export type SnapshotDiffOut = {
  claims_ajoutes: NodeOut[];
  claims_supprimes: NodeOut[];
  claims_modifies: NodeOut[];
  edges_ajoutes: FlatEdge[];
  edges_supprimes: FlatEdge[];
  tensions_resolues: TensionOut[];
  tensions_nouvelles: TensionOut[];
};

export function useResolveTension() {
  const queryClient = useQueryClient();
  return useMutation<TensionDiffOut, Error, TensionResolveRequest>({
    mutationFn: async (payload: TensionResolveRequest) => {
      const res = await fetch(`${API_BASE}/tensions/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        throw new Error("Failed to resolve tension");
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["graph"] });
      queryClient.invalidateQueries({ queryKey: ["tensions"] });
      queryClient.invalidateQueries({ queryKey: ["node"] });
      queryClient.invalidateQueries({ queryKey: ["events"] });
      queryClient.invalidateQueries({ queryKey: ["commitment-derivation"] });
    },
  });
}

export function useEvents() {
  return useQuery<EventOut[]>({
    queryKey: ["events"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/events`);
      if (!res.ok) {
        throw new Error("Failed to fetch events");
      }
      return res.json();
    },
  });
}

export function useSnapshots() {
  return useQuery<SnapshotOut[]>({
    queryKey: ["snapshots"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/snapshots`);
      if (!res.ok) {
        throw new Error("Failed to fetch snapshots");
      }
      return res.json();
    },
  });
}

export function useSnapshotDiff(fromId: string | null, toId: string | null) {
  return useQuery<SnapshotDiffOut>({
    queryKey: ["snapshot-diff", fromId, toId],
    queryFn: async () => {
      if (!fromId || !toId) throw new Error("Both snapshot IDs are required");
      const res = await fetch(`${API_BASE}/snapshots/diff?from=${fromId}&to=${toId}`);
      if (!res.ok) {
        throw new Error("Failed to fetch snapshot diff");
      }
      return res.json();
    },
    enabled: !!fromId && !!toId,
  });
}

export function useRestoreSnapshot() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const res = await fetch(`${API_BASE}/snapshots/${id}/restore`, {
        method: "POST",
      });
      if (!res.ok) {
        throw new Error("Failed to restore snapshot");
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["graph"] });
      queryClient.invalidateQueries({ queryKey: ["tensions"] });
      queryClient.invalidateQueries({ queryKey: ["node"] });
      queryClient.invalidateQueries({ queryKey: ["events"] });
      queryClient.invalidateQueries({ queryKey: ["snapshots"] });
      queryClient.invalidateQueries({ queryKey: ["commitment-derivation"] });
    },
  });
}

export function useCreateSnapshot() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (label: string) => {
      const res = await fetch(`${API_BASE}/snapshot?label=${encodeURIComponent(label)}`, {
        method: "POST",
      });
      if (!res.ok) {
        throw new Error("Failed to create snapshot");
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["snapshots"] });
    },
  });
}

// Solve/Coherence types & hooks
export type NodeRef = {
  id: string;
  label_court: string;
  texte: string;
};

export type ViolatedConstraint = {
  constraint_id: string;
  scheme_id: string;
  kind: "inference" | "conflit";
  node_refs: NodeRef[];
  cost: number;
  detail: string;
};

export type ArbitratedTension = {
  id: string;
  scheme_id: string;
  kept_node: NodeRef;
  discarded_node: NodeRef;
  stake_rank: number;
  stake_label: string;
};

export type SolverConfiguration = {
  accepted: string[];
  rejected: string[];
  incoherence_score: number;
  violated_constraints: ViolatedConstraint[];
  arbitrated_tensions: ArbitratedTension[];
  score?: number | null;
  solution_index?: number | null;
  differs_accepted?: string[] | null;
  differs_rejected?: string[] | null;
};

export type SolveResponse = SolverConfiguration;
export type AlternativeSolutionOut = SolverConfiguration;

export function useSolve() {
  return useMutation<SolveResponse, Error, void>({
    mutationFn: async () => {
      const res = await fetch(`${API_BASE}/solve`, {
        method: "POST",
      });
      if (!res.ok) {
        throw new Error("Failed to run solver");
      }
      return res.json();
    },
  });
}

export function useSolveAlternatives(n: number = 3) {
  return useQuery<AlternativeSolutionOut[]>({
    queryKey: ["solve-alternatives", n],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/solve/alternatives?n=${n}`);
      if (!res.ok) {
        throw new Error("Failed to fetch alternative solutions");
      }
      return res.json();
    },
  });
}

// Causal Overlay Types & Hooks
export type CausalEdgeOut = {
  id: string;
  cause_id: string;
  effect_id: string;
  strength: number;
};

export type CausalGraphResponse = {
  nodes: NodeOut[];
  edges: CausalEdgeOut[];
};

export type WhatIfRequest = {
  interventions: Record<string, number>;
};

export type WhatIfResponse = {
  credences: Record<string, number>;
  readable_effects: string[];
};

export function useCausalGraph() {
  return useQuery<CausalGraphResponse>({
    queryKey: ["causal-graph"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/causal/graph`);
      if (!res.ok) {
        throw new Error("Failed to fetch causal graph");
      }
      return res.json();
    },
  });
}

export function useAddCausalEdge() {
  const queryClient = useQueryClient();
  return useMutation<CausalEdgeOut, Error, { cause_id: string; effect_id: string; strength: number }>({
    mutationFn: async (payload) => {
      const res = await fetch(`${API_BASE}/causal/edges`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to add causal edge");
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["causal-graph"] });
      queryClient.invalidateQueries({ queryKey: ["graph"] });
      queryClient.invalidateQueries({ queryKey: ["tensions"] });
      queryClient.invalidateQueries({ queryKey: ["commitment-derivation"] });
    },
  });
}

export function useDeleteCausalEdge() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: async (id) => {
      const res = await fetch(`${API_BASE}/causal/edges/${id}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        throw new Error("Failed to delete causal edge");
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["causal-graph"] });
      queryClient.invalidateQueries({ queryKey: ["graph"] });
      queryClient.invalidateQueries({ queryKey: ["tensions"] });
      queryClient.invalidateQueries({ queryKey: ["commitment-derivation"] });
    },
  });
}

export function useWhatIf() {
  return useMutation<WhatIfResponse, Error, WhatIfRequest>({
    mutationFn: async (payload) => {
      const res = await fetch(`${API_BASE}/whatif`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        throw new Error("Failed to calculate what-if scenario");
      }
      return res.json();
    },
  });
}


export type DomainOut = {
  id: string;
  name: string;
  parent_id: string | null;
};

export type DomainIn = {
  name: string;
  parent_id: string | null;
};

export function useDomains() {
  return useQuery<DomainOut[]>({
    queryKey: ["domains"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/domains`);
      if (!res.ok) {
        throw new Error("Failed to fetch domains");
      }
      return res.json();
    },
  });
}

export function useCreateDomain() {
  const queryClient = useQueryClient();
  return useMutation<DomainOut, Error, DomainIn>({
    mutationFn: async (payload) => {
      const res = await fetch(`${API_BASE}/domains`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        throw new Error("Failed to create domain");
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["domains"] });
    },
  });
}

export function useUpdateDomain() {
  const queryClient = useQueryClient();
  return useMutation<DomainOut, Error, { id: string; payload: DomainIn }>({
    mutationFn: async ({ id, payload }) => {
      const res = await fetch(`${API_BASE}/domains/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        throw new Error("Failed to update domain");
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["domains"] });
      queryClient.invalidateQueries({ queryKey: ["graph"] });
    },
  });
}

export function useDeleteDomain() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: async (id) => {
      const res = await fetch(`${API_BASE}/domains/${id}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        throw new Error("Failed to delete domain");
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["domains"] });
      queryClient.invalidateQueries({ queryKey: ["graph"] });
    },
  });
}

export type NoteGenerateRequest = {
  domain?: string | null;
  node_id?: string | null;
};

export type NoteGenerateResponse = {
  note: string;
};

export function useGenerateNote() {
  return useMutation<NoteGenerateResponse, Error, NoteGenerateRequest>({
    mutationFn: async (payload) => {
      const res = await fetch(`${API_BASE}/notes/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        throw new Error("Failed to generate note");
      }
      return res.json();
    },
  });
}

export type SensitivityClaim = {
  claim_id: string;
  verdict: "accepted" | "rejected";
  flip_delta: number | null;
  flip_tier: string | null;
  robustesse: "fragile" | "robuste";
};

export type SensitivityTension = {
  tension_id: string;
  robustesse: "fragile" | "robuste";
  explanation: string;
};

export type SensitivityResponse = {
  claims: SensitivityClaim[];
  tensions: SensitivityTension[];
};

export function useSensitivity() {
  return useQuery<SensitivityResponse>({
    queryKey: ["sensitivity"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/solve/sensitivity`);
      if (!res.ok) {
        throw new Error("Failed to fetch sensitivity analysis");
      }
      return res.json();
    },
    refetchInterval: 5000,
  });
}

export function useDeleteNode() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: async (id) => {
      const res = await fetch(`${API_BASE}/nodes/${id}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        throw new Error("Failed to delete node");
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["graph"] });
      queryClient.invalidateQueries({ queryKey: ["tensions"] });
      queryClient.invalidateQueries({ queryKey: ["events"] });
      queryClient.invalidateQueries({ queryKey: ["node"] });
      queryClient.invalidateQueries({ queryKey: ["sensitivity"] });
      queryClient.invalidateQueries({ queryKey: ["commitment-derivation"] });
    },
  });
}

export function useUpdateNode() {
  const queryClient = useQueryClient();
  return useMutation<NodeOut, Error, { id: string; payload: { tier?: string; text?: string; domain?: string } }>({
    mutationFn: async ({ id, payload }) => {
      const res = await fetch(`${API_BASE}/nodes/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        throw new Error("Failed to update node");
      }
      return res.json();
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["graph"] });
      queryClient.invalidateQueries({ queryKey: ["tensions"] });
      queryClient.invalidateQueries({ queryKey: ["events"] });
      queryClient.invalidateQueries({ queryKey: ["node", variables.id] });
      queryClient.invalidateQueries({ queryKey: ["sensitivity"] });
      queryClient.invalidateQueries({ queryKey: ["commitment-derivation"] });
    },
  });
}

export function useDeleteEdge() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: async (scheme_id) => {
      const res = await fetch(`${API_BASE}/edges/${scheme_id}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        throw new Error("Failed to delete edge");
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["graph"] });
      queryClient.invalidateQueries({ queryKey: ["tensions"] });
      queryClient.invalidateQueries({ queryKey: ["events"] });
      queryClient.invalidateQueries({ queryKey: ["sensitivity"] });
      queryClient.invalidateQueries({ queryKey: ["commitment-derivation"] });
    },
  });
}


export function useUpdateSchemeNode() {
  const queryClient = useQueryClient();
  return useMutation<SchemeNodeOut, Error, { id: string; payload: { strength: SchemeStrength } }>({
    mutationFn: async ({ id, payload }) => {
      const res = await fetch(`${API_BASE}/scheme_nodes/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        throw new Error("Failed to update scheme node");
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["graph"] });
      queryClient.invalidateQueries({ queryKey: ["tensions"] });
      queryClient.invalidateQueries({ queryKey: ["events"] });
      queryClient.invalidateQueries({ queryKey: ["node"] });
      queryClient.invalidateQueries({ queryKey: ["sensitivity"] });
      queryClient.invalidateQueries({ queryKey: ["hume-validation"] });
      queryClient.invalidateQueries({ queryKey: ["commitment-derivation"] });
    },
  });
}

export type NodeRefHume = {
  id: string;
  label_court: string;
  type: string;
};

export type HumeViolation = {
  scheme_id: string;
  conclusion: NodeRefHume;
  premises: NodeRefHume[];
  message: string;
};

export type HumeValidationResponse = {
  violations: HumeViolation[];
  count: number;
};

export function useHumeValidation() {
  return useQuery<HumeValidationResponse>({
    queryKey: ["hume-validation"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/validate/hume`);
      if (!res.ok) {
        throw new Error("Failed to fetch Hume's Law validation");
      }
      return res.json();
    },
    refetchInterval: 5000,
  });
}

export type DerivationItem = {
  node_id: string;
  label_court: string;
  manual_tier: string | null;
  manual_rank: number;
  derived_rank: number | null;
  derived_tier_label: string | null;
  overcommitted: boolean;
  gap: number | null;
  undercommitted: boolean;
  contributing_scheme_id: string | null;
  cycle_detected: boolean;
};

export type CycleItem = {
  node_ids: string[];
};

export type DerivationResponse = {
  results: DerivationItem[];
  cycles: CycleItem[];
  count_overcommitted: number;
};

export function useCommitmentDerivation() {
  return useQuery<DerivationResponse>({
    queryKey: ["commitment-derivation"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/derive/commitments`);
      if (!res.ok) {
        throw new Error("Failed to fetch commitment derivation");
      }
      return res.json();
    },
  });
}




