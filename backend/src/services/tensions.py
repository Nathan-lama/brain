import uuid
from typing import Any

import networkx as nx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    Edge,
    Node,
    NodeType,
    SchemeNode,
    SchemeType,
    SourceTargetKind,
)
from src.schemas import TensionOut


def val(obj: Any, attr: str) -> Any:
    """Helper to access properties from SQLAlchemy models or raw dicts interchangeably."""
    if isinstance(obj, dict):
        if attr == "metadata_" and "metadata" in obj:
            return obj.get("metadata")
        return obj.get(attr)
    if attr == "metadata_":
        return getattr(obj, "metadata_", {}) or {}
    return getattr(obj, attr, None)


class TensionService:
    @staticmethod
    async def get_tensions(db: AsyncSession) -> list[TensionOut]:
        from src.services.solver import CoherenceSolverService

        # Fetch all elements from DB to compute tensions on the active user configuration (weight > 0)
        nodes_res = await db.execute(select(Node))
        nodes = nodes_res.scalars().all()
        nodes_map = {n.id: n for n in nodes}

        schemes_res = await db.execute(select(SchemeNode))
        scheme_nodes = schemes_res.scalars().all()

        edges_res = await db.execute(select(Edge))
        edges = edges_res.scalars().all()

        current_accepted_ids = {
            nid for nid, node in nodes_map.items() if node.weight > 0.0
        }

        # Build support graph for mediators
        G_support = CoherenceSolverService._build_support_graph(
            nodes_map, scheme_nodes, edges
        )

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

        tensions = []
        for s_node in scheme_nodes:
            if s_node.scheme == SchemeType.CONFLIT:
                inputs = scheme_inputs.get(s_node.id, [])
                outputs = scheme_outputs.get(s_node.id, [])
                conflict_nodes = set(inputs + outputs)
                conflict_list = list(conflict_nodes)
                for idx1 in range(len(conflict_list)):
                    for idx2 in range(idx1 + 1, len(conflict_list)):
                        u = conflict_list[idx1]
                        v = conflict_list[idx2]
                        if u in current_accepted_ids and v in current_accepted_ids:
                            mediators = CoherenceSolverService._find_mediator_ponts(
                                G_support, {u, v}, nodes_map
                            )

                            u_weight = float(getattr(nodes_map[u], "weight", 1.0))
                            v_weight = float(getattr(nodes_map[v], "weight", 1.0))
                            weight = float(s_node.weight)

                            # Calculate conflict score
                            score = u_weight * v_weight * weight
                            meta = s_node.metadata_ or {}
                            is_paradox = meta.get("paradoxe_assume", False)

                            u_str, v_str = sorted([str(u), str(v)])
                            tension_id = uuid.uuid5(
                                uuid.NAMESPACE_DNS,
                                f"conflict-{u_str}-{v_str}-{s_node.id}",
                            )

                            tensions.append(
                                TensionOut(
                                    id=tension_id,
                                    type="conflit_direct",
                                    claims=[nodes_map[u], nodes_map[v]],
                                    ponts=mediators,
                                    score=round(score, 3),
                                    poids=s_node.weight,
                                    scheme_id=s_node.id,
                                    paradoxe_assume=is_paradox,
                                )
                            )
        return tensions

    @staticmethod
    def detect_tensions_on_elements(
        active_nodes: dict[uuid.UUID, Any],
        scheme_nodes: dict[uuid.UUID, Any],
        edges: list[Any],
    ) -> list[dict]:
        active_edges = []
        for edge in edges:
            edge_src = uuid.UUID(str(val(edge, "source_id")))
            edge_tgt = uuid.UUID(str(val(edge, "target_id")))
            src_kind = val(edge, "source_kind")
            tgt_kind = val(edge, "target_kind")

            src_ok = (
                (edge_src in active_nodes)
                if src_kind == SourceTargetKind.NODE
                else (edge_src in scheme_nodes)
            )
            tgt_ok = (
                (edge_tgt in active_nodes)
                if tgt_kind == SourceTargetKind.NODE
                else (edge_tgt in scheme_nodes)
            )
            if src_ok and tgt_ok:
                active_edges.append(edge)

        G_support = nx.DiGraph()
        for node_id in active_nodes:
            G_support.add_node(node_id)
        for s_id in scheme_nodes:
            G_support.add_node(s_id)

        for edge in active_edges:
            edge_src = uuid.UUID(str(val(edge, "source_id")))
            edge_tgt = uuid.UUID(str(val(edge, "target_id")))
            src_kind = val(edge, "source_kind")
            tgt_kind = val(edge, "target_kind")

            if (
                src_kind == SourceTargetKind.NODE
                and tgt_kind == SourceTargetKind.SCHEME
            ):
                scheme = scheme_nodes[edge_tgt]
                if val(scheme, "scheme") == SchemeType.INFERENCE:
                    G_support.add_edge(edge_src, edge_tgt)
            elif (
                src_kind == SourceTargetKind.SCHEME
                and tgt_kind == SourceTargetKind.NODE
            ):
                scheme = scheme_nodes[edge_src]
                if val(scheme, "scheme") == SchemeType.INFERENCE:
                    G_support.add_edge(edge_src, edge_tgt)

        def find_mediator_ponts(target_ids: set[uuid.UUID]) -> list[Any]:
            mediators = []
            visited = set()
            all_ancestors = set()
            for tid in target_ids:
                if tid in G_support:
                    all_ancestors.update(nx.ancestors(G_support, tid))
            for node_id in target_ids | all_ancestors:
                if node_id in active_nodes:
                    node = active_nodes[node_id]
                    if (
                        val(node, "type") == NodeType.PONT_NORMATIF
                        and node_id not in visited
                    ):
                        mediators.append(node)
                        visited.add(node_id)
            return mediators

        scheme_inputs = {}
        scheme_outputs = {}
        for edge in active_edges:
            edge_src = uuid.UUID(str(val(edge, "source_id")))
            edge_tgt = uuid.UUID(str(val(edge, "target_id")))
            src_kind = val(edge, "source_kind")
            tgt_kind = val(edge, "target_kind")

            if (
                src_kind == SourceTargetKind.NODE
                and tgt_kind == SourceTargetKind.SCHEME
            ):
                scheme_inputs.setdefault(edge_tgt, []).append(edge_src)
            elif (
                src_kind == SourceTargetKind.SCHEME
                and tgt_kind == SourceTargetKind.NODE
            ):
                scheme_outputs.setdefault(edge_src, []).append(edge_tgt)

        tensions = []
        detected_conflict_keys = set()

        for s_id, scheme in scheme_nodes.items():
            inputs = scheme_inputs.get(s_id, [])
            outputs = scheme_outputs.get(s_id, [])

            if val(scheme, "scheme") == SchemeType.CONFLIT and inputs and outputs:
                conflict_nodes = set(inputs + outputs)
                conflict_list = list(conflict_nodes)
                for idx1 in range(len(conflict_list)):
                    for idx2 in range(idx1 + 1, len(conflict_list)):
                        u = conflict_list[idx1]
                        v = conflict_list[idx2]

                        conflict_key = tuple(sorted([str(u), str(v)]))
                        if conflict_key not in detected_conflict_keys:
                            detected_conflict_keys.add(conflict_key)

                            mediators = find_mediator_ponts({u, v})

                            mediator_weights = [
                                float(val(m, "weight")) for m in mediators
                            ]
                            mediator_factor = (
                                sum(mediator_weights) / len(mediator_weights)
                                if mediator_weights
                                else 1.0
                            )

                            u_weight = float(val(active_nodes[u], "weight"))
                            v_weight = float(val(active_nodes[v], "weight"))
                            weight = float(val(scheme, "weight"))

                            score = u_weight * v_weight * weight * mediator_factor
                            meta = val(scheme, "metadata_") or {}
                            is_paradox = meta.get("paradoxe_assume", False)

                            u_str, v_str = sorted([str(u), str(v)])
                            tensions.append(
                                {
                                    "id": uuid.uuid5(
                                        uuid.NAMESPACE_DNS,
                                        f"conflict-{u_str}-{v_str}-{s_id}",
                                    ),
                                    "type": "conflit_direct",
                                    "claims": [active_nodes[u], active_nodes[v]],
                                    "ponts": mediators,
                                    "score": round(score, 3),
                                    "poids": val(scheme, "weight"),
                                    "scheme_id": s_id,
                                    "paradoxe_assume": is_paradox,
                                }
                            )
        tensions.sort(key=lambda t: t["score"], reverse=True)
        return tensions

    @staticmethod
    def get_tensions_from_payload(payload: dict) -> list[dict]:
        nodes = payload.get("nodes", [])
        scheme_nodes = payload.get("scheme_nodes", [])
        edges = payload.get("edges", [])

        active_nodes = {}
        for n in nodes:
            n_id = uuid.UUID(str(n.get("id")))
            w = n.get("weight") if n.get("weight") is not None else n.get("confidence")
            if float(w if w is not None else 1.0) > 0.0:
                active_nodes[n_id] = n

        schemes = {}
        for s in scheme_nodes:
            s_id = uuid.UUID(str(s.get("id")))
            schemes[s_id] = s

        return TensionService.detect_tensions_on_elements(active_nodes, schemes, edges)

    @staticmethod
    async def get_tensions_incremental(
        db: AsyncSession, edited_entity_id: uuid.UUID, before_state_tensions: list[dict]
    ) -> dict:
        all_nodes_res = await db.execute(select(Node))
        all_nodes = {n.id: n for n in all_nodes_res.scalars().all()}

        scheme_nodes_res = await db.execute(select(SchemeNode))
        scheme_nodes = {s.id: s for s in scheme_nodes_res.scalars().all()}

        edges_res = await db.execute(select(Edge))
        edges = edges_res.scalars().all()

        U = nx.Graph()
        for node_id in all_nodes:
            U.add_node(node_id)
        for s_id in scheme_nodes:
            U.add_node(s_id)

        for edge in edges:
            U.add_edge(edge.source_id, edge.target_id)

        component_ids = set()
        if edited_entity_id in U:
            component_ids = nx.node_connected_component(U, edited_entity_id)
        else:
            component_ids = {edited_entity_id}

        claims_affectes = [all_nodes[nid] for nid in component_ids if nid in all_nodes]

        tensions_before_comp = []
        for tension in before_state_tensions:
            claims = val(tension, "claims") or []
            t_claim_ids = {uuid.UUID(str(val(c, "id"))) for c in claims}
            if t_claim_ids & component_ids:
                tensions_before_comp.append(tension)

        after_state_tensions = await TensionService.get_tensions(db)
        tensions_after_comp = []
        for tension in after_state_tensions:
            claims = val(tension, "claims") or []
            t_claim_ids = {uuid.UUID(str(val(c, "id"))) for c in claims}
            if t_claim_ids & component_ids:
                tensions_after_comp.append(tension)

        t_before_map = {uuid.UUID(str(val(t, "id"))): t for t in tensions_before_comp}
        t_after_map = {uuid.UUID(str(val(t, "id"))): t for t in tensions_after_comp}

        tensions_resolues = [
            t for tid, t in t_before_map.items() if tid not in t_after_map
        ]
        tensions_nouvelles = [
            t for tid, t in t_after_map.items() if tid not in t_before_map
        ]

        return {
            "tensions_resolues": tensions_resolues,
            "tensions_nouvelles": tensions_nouvelles,
            "claims_affectes": claims_affectes,
        }
