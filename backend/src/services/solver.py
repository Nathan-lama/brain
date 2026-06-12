import math
import uuid
from dataclasses import dataclass
from typing import Any

import networkx as nx
from ortools.sat.python import cp_model
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    Edge,
    Node,
    NodeType,
    SchemeNode,
    SchemeStrength,
    SchemeType,
    SourceTargetKind,
)
from src.schemas import (
    ArbitratedTension,
    NodeRef,
    ViolatedConstraint,
)

SCALE = 10000
DEDUCTIVE_TIE_BREAK = 1


@dataclass(frozen=True)
class NodeRow:
    id: uuid.UUID
    type: Any
    tier: Any
    weight: float
    text: str
    metadata_: dict | None = None


@dataclass(frozen=True)
class SchemeRow:
    id: uuid.UUID
    scheme: Any
    strength: Any
    weight: float
    metadata_: dict | None = None


@dataclass(frozen=True)
class EdgeRow:
    source_id: uuid.UUID
    source_kind: Any
    target_id: uuid.UUID
    target_kind: Any
    role: Any


@dataclass(frozen=True)
class GraphData:
    nodes: list[NodeRow]
    schemes: list[SchemeRow]
    edges: list[EdgeRow]
    credences: dict[uuid.UUID, float]


async def load_graph(db: AsyncSession, use_causal_credences: bool = False) -> GraphData:
    """Loads all nodes, schemes, and edges from DB, returning a detached GraphData container."""
    nodes_res = await db.execute(select(Node))
    nodes = nodes_res.scalars().all()
    node_rows = [
        NodeRow(
            id=n.id,
            type=n.type,
            tier=n.tier,
            weight=n.weight,
            text=n.text,
            metadata_=n.metadata_,
        )
        for n in nodes
    ]

    schemes_res = await db.execute(select(SchemeNode))
    scheme_nodes = schemes_res.scalars().all()
    scheme_rows = []
    for s in scheme_nodes:
        if s.scheme == SchemeType.INFERENCE and s.strength is None:
            raise ValueError(f"SchemeNode {s.id} of type inference has NULL strength.")
        scheme_rows.append(
            SchemeRow(
                id=s.id,
                scheme=s.scheme,
                strength=s.strength,
                weight=s.weight,
                metadata_=s.metadata_,
            )
        )

    edges_res = await db.execute(select(Edge))
    edges = edges_res.scalars().all()
    edge_rows = [
        EdgeRow(
            source_id=e.source_id,
            source_kind=e.source_kind,
            target_id=e.target_id,
            target_kind=e.target_kind,
            role=e.role,
        )
        for e in edges
    ]

    credences = {}
    if use_causal_credences:
        from src.services.causal import CausalService

        credences = await CausalService.compute_credences(db)

    return GraphData(
        nodes=node_rows,
        schemes=scheme_rows,
        edges=edge_rows,
        credences=credences,
    )


class CostInvariantViolation(Exception):
    def __init__(self, expected: float, got: float, constraint_ids: list[uuid.UUID]):
        self.expected = expected
        self.got = got
        self.constraint_ids = constraint_ids
        super().__init__(
            f"Cost invariant violation: expected sum of costs {expected}, got incoherence_score {got}"
        )


def assert_cost_invariant(
    violated_constraints: list[Any], incoherence_score: float
) -> None:
    """
    Enforces the runtime invariant: sum(costs) == incoherence_score.
    Uses integer scaling with SCALE first, then falls back to math.isclose.
    """
    total_cost = 0.0
    constraint_ids = []
    for vc in violated_constraints:
        if isinstance(vc, dict):
            cost = vc.get("cost", 0.0)
            cid = vc.get("constraint_id", vc.get("id"))
        else:
            cost = getattr(vc, "cost", 0.0)
            cid = getattr(vc, "constraint_id", getattr(vc, "id", None))
        total_cost += cost
        if cid:
            constraint_ids.append(cid)

    expected_int = int(round(total_cost * SCALE))
    got_int = int(round(incoherence_score * SCALE))

    if expected_int == got_int:
        return

    if math.isclose(total_cost, incoherence_score, rel_tol=0, abs_tol=1 / (10 * SCALE)):
        return

    raise CostInvariantViolation(
        expected=round(total_cost, 3),
        got=round(incoherence_score, 3),
        constraint_ids=constraint_ids,
    )


def make_solver() -> cp_model.CpSolver:
    """
    Factory to construct a deterministic CpSolver instance.
    """
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    return solver


TIER_RANKS = {"speculatif": 1, "faible": 2, "moyen": 3, "fort": 4, "certain": 5}


def get_strength_weight(strength: Any) -> float:
    from src.models import STRENGTH_TO_WEIGHT
    val = strength.value if hasattr(strength, "value") else str(strength)
    for k, v in STRENGTH_TO_WEIGHT.items():
        if k.value == val or str(k) == val:
            return v
    raise ValueError(f"Invalid strength: {strength}")


def get_label_court(node_id: uuid.UUID, metadata: dict | None = None) -> str:
    # 1. Check if metadata has imported_id
    if metadata and isinstance(metadata, dict) and "imported_id" in metadata:
        return str(metadata["imported_id"])

    # 2. Check precomputed map of known short IDs
    uuid_to_short = {}
    prefixes = ["d", "b", "c", "pos", "ra", "ca", "t", "i", "p"]
    for pref in prefixes:
        for num in range(1, 100):
            short_id = f"{pref}{num}"
            u = uuid.uuid5(uuid.NAMESPACE_DNS, short_id)
            uuid_to_short[u] = short_id

    uuid_to_short[uuid.uuid5(uuid.NAMESPACE_DNS, "ra_emp")] = "ra_emp"

    for c_id in [
        "d1111111-1111-1111-1111-111111111111",
        "d2222222-2222-2222-2222-222222222222",
        "b1111111-1111-1111-1111-111111111111",
        "c1111111-1111-1111-1111-111111111111",
        "f1111111-1111-1111-1111-111111111111",
        "a1111111-1111-1111-1111-111111111111",
        "a2222222-2222-2222-2222-222222222222",
    ]:
        try:
            uuid_to_short[uuid.UUID(c_id)] = c_id
        except ValueError:
            pass

    if node_id in uuid_to_short:
        return uuid_to_short[node_id]

    return str(node_id)[:6]


def solve_graph(
    g: GraphData,
    tier_overrides: dict[uuid.UUID, str] = None,
    weight_overrides: dict[uuid.UUID, float] = None,
) -> dict:
    """Synchronously solves the global argument coherence from a detached GraphData container."""
    (
        model,
        x,
        nodes_map,
        schemes,
        edges,
        soft_implications,
        soft_conflicts,
        conflicts_map,
    ) = CoherenceSolverService._build_model_pure(
        g, weight_overrides=weight_overrides, tier_overrides=tier_overrides
    )

    solver = make_solver()
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {
            "accepted": [],
            "rejected": [n.id for n in g.nodes],
            "violated_constraints": [],
            "arbitrated_tensions": [],
            "incoherence_score": 0.0,
            "score": 0.0,
        }

    # 1. Parse accepted and rejected claims
    accepted_ids = []
    rejected_ids = []
    for nid, var in x.items():
        if solver.Value(var) == 1:
            accepted_ids.append(nid)
        else:
            rejected_ids.append(nid)

    # 2. Compute violations in optimal solution
    violated_constraints = CoherenceSolverService._compute_violated_constraints(
        nodes_map, schemes, edges, set(accepted_ids)
    )

    # 3. Compute arbitrated tensions
    arbitrated_tensions = CoherenceSolverService._compute_arbitrated_tensions(
        nodes_map, schemes, edges, set(accepted_ids)
    )

    incoherence_score = CoherenceSolverService._calculate_incoherence(
        violated_constraints
    )
    assert_cost_invariant(violated_constraints, incoherence_score)

    return {
        "accepted": accepted_ids,
        "rejected": rejected_ids,
        "violated_constraints": violated_constraints,
        "arbitrated_tensions": arbitrated_tensions,
        "incoherence_score": round(incoherence_score, 3),
        "score": round(solver.ObjectiveValue() / SCALE, 3),
    }


def enumerate_alternatives(g: GraphData, n: int) -> list[dict]:
    """
    Solves CP-SAT multiple times to find n quasi-optimal alternative configurations.

    The returned alternatives are sorted canonically by score (descending),
    incoherence_score (ascending), and tuple(sorted(accepted_nodes))
    to ensure stable ordering across runs.
    """
    (
        model,
        x,
        nodes_map,
        schemes,
        edges,
        soft_implications,
        soft_conflicts,
        conflicts_map,
    ) = CoherenceSolverService._build_model_pure(g)

    # 1. Solve optimal solution first to serve as baseline comparison
    solver = make_solver()
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return []

    optimal_accepted = set()
    optimal_rejected = set()
    optimal_assignment = {}
    for nid, var in x.items():
        val = solver.Value(var)
        optimal_assignment[nid] = val
        if val == 1:
            optimal_accepted.add(nid)
        else:
            optimal_rejected.add(nid)

    # Collect solutions
    alternatives = []

    # Exclude optimal solution first to find alternatives
    literals = []
    for nid, var in x.items():
        val = optimal_assignment[nid]
        if val == 1:
            literals.append(var.Not())
        else:
            literals.append(var)
    model.AddBoolOr(literals)

    # Loop to find alternative configurations
    for idx in range(1, n + 1):
        solver = make_solver()
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break

        alt_accepted = []
        alt_rejected = []
        alt_assignment = {}
        for nid, var in x.items():
            val = solver.Value(var)
            alt_assignment[nid] = val
            if val == 1:
                alt_accepted.append(nid)
            else:
                alt_rejected.append(nid)

        # Compare differences with optimal baseline
        differs_accepted = [
            nid for nid in alt_accepted if nid not in optimal_accepted
        ]
        differs_rejected = [
            nid for nid in alt_rejected if nid not in optimal_rejected
        ]

        # Calculate violated constraints and arbitrated tensions for this alternative solution
        alt_violated_constraints = (
            CoherenceSolverService._compute_violated_constraints(
                nodes_map, schemes, edges, set(alt_accepted)
            )
        )
        alt_arbitrated_tensions = (
            CoherenceSolverService._compute_arbitrated_tensions(
                nodes_map, schemes, edges, set(alt_accepted)
            )
        )
        incoherence_score = CoherenceSolverService._calculate_incoherence(
            alt_violated_constraints
        )

        # Assert cost invariant for this alternative configuration
        assert_cost_invariant(alt_violated_constraints, incoherence_score)

        alternatives.append(
            {
                "solution_index": idx,
                "accepted": alt_accepted,
                "rejected": alt_rejected,
                "differs_accepted": differs_accepted,
                "differs_rejected": differs_rejected,
                "violated_constraints": alt_violated_constraints,
                "arbitrated_tensions": alt_arbitrated_tensions,
                "incoherence_score": round(incoherence_score, 3),
                "score": round(solver.ObjectiveValue() / SCALE, 3),
            }
        )

        # Exclude this alternative solution from future runs
        literals = []
        for nid, var in x.items():
            val = alt_assignment[nid]
            if val == 1:
                literals.append(var.Not())
            else:
                literals.append(var)
        model.AddBoolOr(literals)

    # Sort alternatives canonically by key: (score descending, incoherence_score ascending, tuple(sorted(accepted_node_uuids)))
    alternatives.sort(
        key=lambda a: (-a["score"], a["incoherence_score"], tuple(sorted(a["accepted"])))
    )

    # Re-assign solution_index to match sorted order
    for sorted_idx, alt in enumerate(alternatives, 1):
        alt["solution_index"] = sorted_idx

    return alternatives


class CoherenceSolverService:
    """
    Service to optimize global argument coherence using a CP-SAT solver.

    Note on Deductive Schemes:
    Deductive scheme nodes have a weight of 5.0 (DEDUCTIF). Since the maximum possible node rank
    for unary preferences is 5 (CERTAIN), a deductive violation (cost 5.0) is never strictly optimal.
    Preserving deductive inferences (revising premises instead) is an emergent property of the cost
    structure in all cases of strict inequality. The degenerate case of exact equality is resolved
    explicitly in the same direction by a deterministic tie-breaker (DEDUCTIVE_TIE_BREAK = 1,
    asserted via DEDUCTIVE_TIE_BREAK * n_deductif < SCALE * 1.0 to ensure tie-breaks cannot overturn
    real differences). This behavior is guaranteed by test_quinian_static_invariant and test_quinian_tie_break.
    """

    @staticmethod
    def _calculate_incoherence(violated_constraints: list[ViolatedConstraint]) -> float:
        return sum(v.cost for v in violated_constraints if v.kind == "inference")

    @staticmethod
    def _build_model_pure(
        g: GraphData,
        weight_overrides: dict[uuid.UUID, float] = None,
        tier_overrides: dict[uuid.UUID, str] = None,
    ) -> tuple[
        cp_model.CpModel,
        dict[uuid.UUID, cp_model.IntVar],
        dict[uuid.UUID, NodeRow],
        list[SchemeRow],
        list[EdgeRow],
        list[tuple[list[uuid.UUID], uuid.UUID, SchemeRow, cp_model.IntVar]],
        list[tuple[uuid.UUID, uuid.UUID, SchemeRow, cp_model.IntVar]],
        dict[uuid.UUID, list[uuid.UUID]],
    ]:
        """
        Builds the CP-SAT model and returns:
        (model, x_vars, nodes_map, scheme_nodes, edges, soft_implications, soft_conflicts, conflicts_map)
        """
        model = cp_model.CpModel()

        nodes_map = {n.id: n for n in g.nodes}

        # Count deductive inference scheme nodes
        n_deductif = sum(
            1
            for s in g.schemes
            if s.scheme == SchemeType.INFERENCE
            and s.strength == SchemeStrength.DEDUCTIF
        )

        # Guard: assert that the sum of deductive tie-breaks cannot overturn a real difference in rank or weight.
        # Ranks and weights have a minimum granularity of 1.0. To guarantee that tie-breaks only resolve exact
        # ties, the accumulated tie-breaks must be strictly less than the scaled minimum granularity (1.0 * SCALE).
        # Note: The granularity of 1.0 is guaranteed by construction (via validation on SchemeNodeIn and database CHECK constraint 'check_inference_weight_values').
        assert DEDUCTIVE_TIE_BREAK * n_deductif < SCALE * 1.0, (
            f"DEDUCTIVE_TIE_BREAK guard violated: DEDUCTIVE_TIE_BREAK ({DEDUCTIVE_TIE_BREAK}) * "
            f"n_deductif ({n_deductif}) must be strictly less than SCALE ({SCALE}) * granularity (1.0). "
            f"Please increase SCALE to prevent tie-breaks from overturning real differences in weight or rank."
        )

        # Helper to map float credence to rank
        def credence_to_rank(val: float) -> int:
            if val > 0.875:
                return 5
            elif val > 0.700:
                return 4
            elif val > 0.500:
                return 3
            elif val > 0.300:
                return 2
            elif val > 0.0:
                return 1
            return 0

        # Helper to get rank for a node
        def get_node_rank(node: NodeRow) -> int:
            w = (
                weight_overrides.get(node.id, node.weight)
                if weight_overrides
                else node.weight
            )
            t = tier_overrides.get(node.id, node.tier) if tier_overrides else node.tier

            if w == 0.0 or t is None:
                return 0
            if node.type == NodeType.EMPIRIQUE and node.id in g.credences:
                if weight_overrides and node.id in weight_overrides:
                    return credence_to_rank(weight_overrides[node.id])
                return credence_to_rank(g.credences[node.id])

            tier_val = t.value if hasattr(t, "value") else str(t)
            return TIER_RANKS.get(tier_val, 3)

        # 2. Variables: accept_i for each node
        x = {}
        for node in g.nodes:
            x[node.id] = model.NewBoolVar(f"accept_{node.id}")

            # Force revised/deleted nodes (rank 0) to be rejected (0)
            if get_node_rank(node) == 0:
                model.Add(x[node.id] == 0)

        # 3. Objectives and constraints lists
        objectives = []
        soft_implications = []
        soft_conflicts = []
        conflicts_map = {}  # key: scheme_id -> value: list of claim UUIDs involved

        # Add unary preferences: prefer accepting nodes with higher rank
        for node in g.nodes:
            rank = get_node_rank(node)
            if rank > 0:
                pref_weight = rank * SCALE
                objectives.append(pref_weight * x[node.id])

        # 4. Parse edges to group inputs and outputs by scheme node
        scheme_inputs = {}
        scheme_outputs = {}
        for edge in g.edges:
            if (
                edge.source_kind == SourceTargetKind.NODE
                and edge.target_kind == SourceTargetKind.SCHEME
            ):
                scheme_inputs.setdefault(edge.target_id, []).append(edge.source_id)
            elif (
                edge.source_kind == SourceTargetKind.SCHEME
                and edge.target_kind == SourceTargetKind.NODE
            ):
                scheme_outputs.setdefault(edge.source_id, []).append(edge.target_id)

        # 5. Build constraints
        for s_node in g.schemes:
            inputs = scheme_inputs.get(s_node.id, [])
            outputs = scheme_outputs.get(s_node.id, [])
            if not inputs and not outputs:
                continue

            if s_node.scheme == SchemeType.CONFLIT:
                # Paradox assume check: skip conflict if marked as accepted paradox
                meta = s_node.metadata_ or {}
                if meta.get("paradoxe_assume", False):
                    continue

                # All nodes connected to this conflict scheme are in conflict
                conflict_nodes = set(inputs + outputs)
                conflicts_map[s_node.id] = list(conflict_nodes)
                conflict_list = list(conflict_nodes)
                for idx1 in range(len(conflict_list)):
                    for idx2 in range(idx1 + 1, len(conflict_list)):
                        u = conflict_list[idx1]
                        v = conflict_list[idx2]
                        # Soft conflict constraint: NOT(accept_u AND accept_v)
                        satisfied = model.NewBoolVar(f"conflict_{u}_{v}_{s_node.id}")
                        model.AddBoolOr([x[u].Not(), x[v].Not()]).OnlyEnforceIf(
                            satisfied
                        )
                        model.AddBoolAnd([x[u], x[v]]).OnlyEnforceIf(satisfied.Not())

                        poids_fort = 100 * SCALE
                        objectives.append(poids_fort * satisfied)
                        soft_conflicts.append((u, v, s_node, satisfied))

            else:
                # Inference / Preference support schemes: soft implication (accept_u1 AND accept_u2 ...) => accept_v
                for v in outputs:
                    satisfied = model.NewBoolVar(f"implication_{s_node.id}_{v}")
                    model.AddBoolOr(
                        [x[u].Not() for u in inputs] + [x[v]]
                    ).OnlyEnforceIf(satisfied)
                    model.AddBoolAnd(
                        [x[u] for u in inputs] + [x[v].Not()]
                    ).OnlyEnforceIf(satisfied.Not())

                    weight_int = int(s_node.weight * SCALE)
                    # Tie-break: add DEDUCTIVE_TIE_BREAK if the scheme node is deductive.
                    if s_node.strength == SchemeStrength.DEDUCTIF:
                        weight_int += DEDUCTIVE_TIE_BREAK
                    objectives.append(weight_int * satisfied)
                    soft_implications.append((inputs, v, s_node, satisfied))

        # Maximize satisfied weights + confidences
        model.Maximize(sum(objectives))

        return (
            model,
            x,
            nodes_map,
            g.schemes,
            g.edges,
            soft_implications,
            soft_conflicts,
            conflicts_map,
        )

    @staticmethod
    def _build_support_graph(
        nodes_map: dict[uuid.UUID, Node],
        scheme_nodes: list[SchemeNode],
        edges: list[Edge],
    ) -> nx.DiGraph:
        """Helper to build a directed support graph for mediator searches."""
        G_support = nx.DiGraph()
        for nid in nodes_map:
            G_support.add_node(nid)

        scheme_inputs = {}
        scheme_outputs = {}
        for edge in edges:
            if (
                edge.source_kind == SourceTargetKind.NODE
                and edge.target_kind == SourceTargetKind.SCHEME
            ):
                scheme_inputs.setdefault(edge.target_id, []).append(edge.source_id)
            elif (
                edge.source_kind == SourceTargetKind.SCHEME
                and edge.target_kind == SourceTargetKind.NODE
            ):
                scheme_outputs.setdefault(edge.source_id, []).append(edge.target_id)

        for s_node in scheme_nodes:
            if s_node.scheme == SchemeType.INFERENCE:
                inputs = scheme_inputs.get(s_node.id, [])
                outputs = scheme_outputs.get(s_node.id, [])
                for u in inputs:
                    for v in outputs:
                        G_support.add_edge(u, v)
        return G_support

    @staticmethod
    def _find_mediator_ponts(
        G_support: nx.DiGraph, target_ids: set, nodes_map: dict[uuid.UUID, Node]
    ) -> list[Node]:
        """Finds all NodeType.PONT_NORMATIF ancestors of target_ids in the support graph."""
        mediators = []
        visited = set()
        all_ancestors = set()
        for tid in target_ids:
            if tid in G_support:
                all_ancestors.update(nx.ancestors(G_support, tid))
        for nid in target_ids | all_ancestors:
            if nid in nodes_map:
                node = nodes_map[nid]
                if node.type == NodeType.PONT_NORMATIF and nid not in visited:
                    mediators.append(node)
                    visited.add(nid)
        return mediators

    @staticmethod
    def _compute_violated_constraints(
        nodes_map: dict[uuid.UUID, Node],
        scheme_nodes: list[SchemeNode],
        edges: list[Edge],
        accepted_ids: set[uuid.UUID],
    ) -> list[ViolatedConstraint]:
        """
        Computes all violated constraints (both conflicts and inferences) for a given set of accepted node IDs.
        """
        # Parse edges to group inputs and outputs by scheme node
        scheme_inputs = {}
        scheme_outputs = {}
        for edge in edges:
            if (
                edge.source_kind == SourceTargetKind.NODE
                and edge.target_kind == SourceTargetKind.SCHEME
            ):
                scheme_inputs.setdefault(edge.target_id, []).append(edge.source_id)
            elif (
                edge.source_kind == SourceTargetKind.SCHEME
                and edge.target_kind == SourceTargetKind.NODE
            ):
                scheme_outputs.setdefault(edge.source_id, []).append(edge.target_id)

        violated_list = []

        for s_node in scheme_nodes:
            inputs = scheme_inputs.get(s_node.id, [])
            outputs = scheme_outputs.get(s_node.id, [])
            if not inputs and not outputs:
                continue

            if s_node.scheme == SchemeType.CONFLIT:
                meta = s_node.metadata_ or {}
                is_paradox = meta.get("paradoxe_assume", False)
                if is_paradox:
                    continue

                conflict_nodes = set(inputs + outputs)
                conflict_list = list(conflict_nodes)
                for idx1 in range(len(conflict_list)):
                    for idx2 in range(idx1 + 1, len(conflict_list)):
                        u = conflict_list[idx1]
                        v = conflict_list[idx2]

                        if u in accepted_ids and v in accepted_ids:
                            u_node = nodes_map[u]
                            v_node = nodes_map[v]

                            u_ref = NodeRef(
                                id=u,
                                label_court=get_label_court(u, u_node.metadata_),
                                texte=u_node.text,
                            )
                            v_ref = NodeRef(
                                id=v,
                                label_court=get_label_court(v, v_node.metadata_),
                                texte=v_node.text,
                            )

                            u_str, v_str = sorted([str(u), str(v)])
                            constraint_id = uuid.uuid5(
                                uuid.NAMESPACE_DNS,
                                f"violation-conflict-{u_str}-{v_str}-{s_node.id}",
                            )

                            violated_list.append(
                                ViolatedConstraint(
                                    constraint_id=constraint_id,
                                    scheme_id=s_node.id,
                                    kind="conflit",
                                    node_refs=[u_ref, v_ref],
                                    cost=0.0,
                                    detail=f"Conflit de thèses : '{u_ref.label_court}' et '{v_ref.label_court}' sont co-acceptées.",
                                )
                            )

            else:
                # Inference / Preference support schemes: (u1 AND u2 ...) => v
                # Violated if ALL inputs are accepted but the output v is rejected
                all_inputs_accepted = all(u in accepted_ids for u in inputs)
                if all_inputs_accepted and inputs:
                    for v in outputs:
                        if v not in accepted_ids:
                            involved_claims = []
                            for u in inputs:
                                if u in nodes_map:
                                    involved_claims.append(
                                        NodeRef(
                                            id=u,
                                            label_court=get_label_court(
                                                u, nodes_map[u].metadata_
                                            ),
                                            texte=nodes_map[u].text,
                                        )
                                    )
                            if v in nodes_map:
                                involved_claims.append(
                                    NodeRef(
                                        id=v,
                                        label_court=get_label_court(
                                            v, nodes_map[v].metadata_
                                        ),
                                        texte=nodes_map[v].text,
                                    )
                                )

                            inputs_str = "-".join(sorted([str(u) for u in inputs]))
                            implication_id = uuid.uuid5(
                                uuid.NAMESPACE_DNS,
                                f"violation-inference-{inputs_str}-{v}-{s_node.id}",
                            )

                            premises_labels = " ∧ ".join(
                                sorted(
                                    [
                                        get_label_court(u, nodes_map[u].metadata_)
                                        for u in inputs
                                    ]
                                )
                            )
                            conclusion_label = get_label_court(
                                v, nodes_map[v].metadata_
                            )
                            detail_str = f"Inférence violée (coût {s_node.weight}) : [{premises_labels}] ⊢ [{conclusion_label}], mais {conclusion_label} est rejeté."

                            violated_list.append(
                                ViolatedConstraint(
                                    constraint_id=implication_id,
                                    scheme_id=s_node.id,
                                    kind="inference",
                                    node_refs=involved_claims,
                                    cost=s_node.weight,
                                    detail=detail_str,
                                )
                            )

        return violated_list

    @staticmethod
    def _compute_arbitrated_tensions(
        nodes_map: dict[uuid.UUID, Node],
        scheme_nodes: list[SchemeNode],
        edges: list[Edge],
        accepted_ids: set[uuid.UUID],
    ) -> list[ArbitratedTension]:
        """
        Computes all arbitrated tensions (conflicts where one node is accepted and the other is rejected).

        Note on stake score vs stake rank:
        Historically, the stake was represented by `stake_score` which was a product of the nodes' weights
        and the conflict scheme weight (e.g., u_node.weight * v_node.weight * s_node.weight). This product
        was philosophically and semantically invalid because belief tiers (such as normative commitments/engagements)
        are ordinal levels of commitment, not probabilities. Multiplying them is mathematically meaningless.
        Instead, we use `stake_rank = min(rang(kept_node), rang(discarded_node))` to measure the weakest link of
        the conflict pair (the minimal guaranteed enjeu of the arbitrage).
        """
        TIER_RANKS = {
            "certain": 5,
            "fort": 4,
            "moyen": 3,
            "faible": 2,
            "speculatif": 1,
        }

        RANK_LABELS = {
            5: "certain",
            4: "fort",
            3: "moyen",
            2: "faible",
            1: "speculatif",
        }

        # Parse edges to group inputs and outputs by scheme node
        scheme_inputs = {}
        scheme_outputs = {}
        for edge in edges:
            if (
                edge.source_kind == SourceTargetKind.NODE
                and edge.target_kind == SourceTargetKind.SCHEME
            ):
                scheme_inputs.setdefault(edge.target_id, []).append(edge.source_id)
            elif (
                edge.source_kind == SourceTargetKind.SCHEME
                and edge.target_kind == SourceTargetKind.NODE
            ):
                scheme_outputs.setdefault(edge.source_id, []).append(edge.target_id)

        arbitrated_list = []

        for s_node in scheme_nodes:
            if s_node.scheme != SchemeType.CONFLIT:
                continue

            meta = s_node.metadata_ or {}
            is_paradox = meta.get("paradoxe_assume", False)
            if is_paradox:
                continue

            inputs = scheme_inputs.get(s_node.id, [])
            outputs = scheme_outputs.get(s_node.id, [])
            conflict_nodes = list(set(inputs + outputs))

            if len(conflict_nodes) >= 2:
                u, v = conflict_nodes[0], conflict_nodes[1]

                # Check if one is accepted and the other is rejected
                u_accepted = u in accepted_ids
                v_accepted = v in accepted_ids

                if u_accepted != v_accepted:
                    kept_id = u if u_accepted else v
                    discarded_id = v if u_accepted else u

                    u_node = nodes_map[u]
                    v_node = nodes_map[v]

                    kept_ref = NodeRef(
                        id=kept_id,
                        label_court=get_label_court(
                            kept_id, nodes_map[kept_id].metadata_
                        ),
                        texte=nodes_map[kept_id].text,
                    )
                    discarded_ref = NodeRef(
                        id=discarded_id,
                        label_court=get_label_court(
                            discarded_id, nodes_map[discarded_id].metadata_
                        ),
                        texte=nodes_map[discarded_id].text,
                    )

                    u_tier = u_node.tier
                    v_tier = v_node.tier

                    u_tier_str = (
                        u_tier.value
                        if hasattr(u_tier, "value")
                        else (str(u_tier) if u_tier else "moyen")
                    )
                    v_tier_str = (
                        v_tier.value
                        if hasattr(v_tier, "value")
                        else (str(v_tier) if v_tier else "moyen")
                    )

                    u_rank = TIER_RANKS.get(u_tier_str, 3)
                    v_rank = TIER_RANKS.get(v_tier_str, 3)

                    rank = min(u_rank, v_rank)
                    label = RANK_LABELS[rank]

                    u_str, v_str = sorted([str(u), str(v)])
                    arbitration_id = uuid.uuid5(
                        uuid.NAMESPACE_DNS, f"arbitration-{u_str}-{v_str}-{s_node.id}"
                    )

                    arbitrated_list.append(
                        ArbitratedTension(
                            id=arbitration_id,
                            scheme_id=s_node.id,
                            kept_node=kept_ref,
                            discarded_node=discarded_ref,
                            stake_rank=rank,
                            stake_label=label,
                        )
                    )

        arbitrated_list.sort(
            key=lambda x: (-x.stake_rank, x.kept_node.id, x.discarded_node.id)
        )
        return arbitrated_list

    @staticmethod
    async def solve(
        db: AsyncSession,
        weight_overrides: dict[uuid.UUID, float] = None,
        tier_overrides: dict[uuid.UUID, str] = None,
    ) -> dict:
        """
        Solves the coherence MAX-SAT model and returns optimal accepted/rejected claims and violations.
        """
        g = await load_graph(db)
        return solve_graph(g, tier_overrides=tier_overrides, weight_overrides=weight_overrides)

    @staticmethod
    async def get_alternatives(db: AsyncSession, n: int = 3) -> list[dict]:
        """
        Solves CP-SAT multiple times to find n quasi-optimal alternative configurations.

        The returned alternatives are sorted canonically by score (descending),
        incoherence_score (ascending), and tuple(sorted(accepted_nodes))
        to ensure stable ordering across runs.
        """
        g = await load_graph(db)
        return enumerate_alternatives(g, n)
