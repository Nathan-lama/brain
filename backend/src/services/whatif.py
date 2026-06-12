import uuid
from dataclasses import dataclass

from src.models import (
    EdgeRole,
    NodeType,
    SchemeType,
    SourceTargetKind,
    TierKind,
)
from src.services.solver import (
    EdgeRow,
    GraphData,
    NodeRow,
    SchemeRow,
    get_label_court,
    get_strength_weight,
)
from src.services.validation.hume import check_hume


class WhatIfValidationError(Exception):
    """Exception raised when a what-if operation is invalid."""

    def __init__(self, index: int, message: str):
        self.index = index
        self.message = message
        super().__init__(message)


@dataclass
class AppliedReport:
    cascaded_schemes: list[str]
    ops_applied: list[dict]


def get_resolution_map(nodes: list[NodeRow], schemes: list[SchemeRow]) -> dict[str, uuid.UUID]:
    res_map = {}
    for n in nodes:
        lbl = get_label_court(n.id, n.metadata_)
        res_map[lbl.lower()] = n.id
        res_map[str(n.id).lower()] = n.id
    for s in schemes:
        lbl = get_label_court(s.id, s.metadata_)
        res_map[lbl.lower()] = s.id
        res_map[str(s.id).lower()] = s.id
    return res_map


def resolve_target(target_name: str, res_map: dict[str, uuid.UUID], idx: int) -> uuid.UUID:
    if not target_name:
        raise WhatIfValidationError(idx, "Target identifier is empty")
    clean_name = target_name.strip().lower()
    resolved = res_map.get(clean_name)
    if not resolved:
        raise WhatIfValidationError(idx, f"Cible inconnue : '{target_name}'")
    return resolved


def apply_ops(g: GraphData, ops: list[dict]) -> tuple[GraphData, AppliedReport]:
    """Applies a list of what-if operations on the GraphData immutably, returning the new GraphData and a report.

    This function is pure and sync: it performs no database queries or writes and returns a new GraphData.
    """
    # 1. Clone GraphData's components to keep it immutable (T6)
    nodes = list(g.nodes)
    schemes = list(g.schemes)
    edges = list(g.edges)
    credences = dict(g.credences)

    cascaded_schemes = []
    ops_applied = []

    # Valid values for validation checks
    valid_node_types = {e.value for e in NodeType}
    valid_tiers = {e.value for e in TierKind}

    for idx, op_data in enumerate(ops):
        op_type = op_data.get("op")

        res_map = get_resolution_map(nodes, schemes)

        if op_type == "set_strength":
            target = op_data.get("target")
            strength_val = op_data.get("strength")

            scheme_id = resolve_target(target, res_map, idx)
            # Find the scheme
            scheme_idx = next((i for i, s in enumerate(schemes) if s.id == scheme_id), None)
            if scheme_idx is None:
                raise WhatIfValidationError(idx, f"Target '{target}' is not a scheme node")

            s_node = schemes[scheme_idx]
            if s_node.scheme == SchemeType.CONFLIT:
                raise WhatIfValidationError(idx, f"Impossible de modifier la force du conflit '{target}'")

            # Validate strength
            try:
                weight = get_strength_weight(strength_val)
            except ValueError as e:
                raise WhatIfValidationError(idx, f"Force invalide : '{strength_val}'") from e

            # Update strength and weight
            schemes[scheme_idx] = SchemeRow(
                id=s_node.id,
                scheme=s_node.scheme,
                strength=strength_val,
                weight=weight,
                metadata_=s_node.metadata_,
            )

        elif op_type == "set_tier":
            target = op_data.get("target")
            tier_val = op_data.get("tier")

            node_id = resolve_target(target, res_map, idx)
            node_idx = next((i for i, n in enumerate(nodes) if n.id == node_id), None)
            if node_idx is None:
                raise WhatIfValidationError(idx, f"Target '{target}' is not a node")

            n_node = nodes[node_idx]
            if tier_val is not None:
                tier_str = tier_val.value if hasattr(tier_val, "value") else str(tier_val)
                if tier_str not in valid_tiers:
                    raise WhatIfValidationError(idx, f"Tier invalide : '{tier_val}'")
            else:
                tier_str = None

            nodes[node_idx] = NodeRow(
                id=n_node.id,
                type=n_node.type,
                tier=tier_str,
                weight=n_node.weight,
                text=n_node.text,
                metadata_=n_node.metadata_,
            )

        elif op_type == "remove_node":
            target = op_data.get("target")
            node_id = resolve_target(target, res_map, idx)
            node_idx = next((i for i, n in enumerate(nodes) if n.id == node_id), None)
            if node_idx is None:
                raise WhatIfValidationError(idx, f"Target '{target}' is not a node")

            # Find all schemes referencing this node in cascade
            cascaded_ids = set()
            for edge in edges:
                if edge.source_id == node_id and edge.source_kind == SourceTargetKind.NODE:
                    if edge.target_kind == SourceTargetKind.SCHEME:
                        cascaded_ids.add(edge.target_id)
                elif edge.target_id == node_id and edge.target_kind == SourceTargetKind.NODE:
                    if edge.source_kind == SourceTargetKind.SCHEME:
                        cascaded_ids.add(edge.source_id)

            # Record cascaded schemes labels
            for cid in cascaded_ids:
                s_node = next((s for s in schemes if s.id == cid), None)
                if s_node:
                    cascaded_schemes.append(get_label_court(s_node.id, s_node.metadata_))

            # Remove the node
            nodes.pop(node_idx)

            # Remove cascaded scheme nodes
            schemes = [s for s in schemes if s.id not in cascaded_ids]

            # Remove all edges connected to the node or any cascaded scheme nodes
            removed_ids = cascaded_ids | {node_id}
            edges = [e for e in edges if e.source_id not in removed_ids and e.target_id not in removed_ids]

        elif op_type == "add_node":
            label_court = op_data.get("label_court")
            text = op_data.get("text")
            node_type = op_data.get("type")
            tier_val = op_data.get("tier")

            if not label_court:
                raise WhatIfValidationError(idx, "Label court manquant pour le nouveau nœud")

            # Check duplication
            clean_label = label_court.strip().lower()
            if clean_label in res_map:
                raise WhatIfValidationError(idx, f"Label court '{label_court}' déjà existant dans le graphe")

            # Validate type
            type_str = node_type.value if hasattr(node_type, "value") else str(node_type)
            if type_str not in valid_node_types:
                raise WhatIfValidationError(idx, f"Type de nœud invalide : '{node_type}'")

            # Validate tier
            tier_str = tier_val.value if hasattr(tier_val, "value") else str(tier_val) if tier_val else None
            if tier_str is not None and tier_str not in valid_tiers:
                raise WhatIfValidationError(idx, f"Tier invalide : '{tier_val}'")

            node_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, label_court)

            nodes.append(
                NodeRow(
                    id=node_uuid,
                    type=type_str,
                    tier=tier_str,
                    weight=0.6,
                    text=text or label_court,
                    metadata_={"imported_id": label_court},
                )
            )

        elif op_type == "add_inference":
            label = op_data.get("label")
            premises = op_data.get("premises") or []
            conclusion = op_data.get("conclusion")
            strength_val = op_data.get("strength")

            if not label:
                raise WhatIfValidationError(idx, "Label de l'inférence manquant")

            # Check duplication
            clean_label = label.strip().lower()
            if clean_label in res_map:
                raise WhatIfValidationError(idx, f"Label d'inférence '{label}' déjà existant")

            # Resolve premises and conclusion
            premise_uuids = [resolve_target(p, res_map, idx) for p in premises]
            conclusion_uuid = resolve_target(conclusion, res_map, idx)

            # Validate strength and get weight
            try:
                weight = get_strength_weight(strength_val)
            except ValueError as e:
                raise WhatIfValidationError(idx, f"Force d'inférence invalide : '{strength_val}'") from e

            scheme_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, label)

            # Temp add scheme and edges to test Hume's Law
            temp_scheme = SchemeRow(
                id=scheme_uuid,
                scheme=SchemeType.INFERENCE,
                strength=strength_val,
                weight=weight,
                metadata_={"imported_id": label},
            )
            temp_edges = []
            for p_uuid in premise_uuids:
                temp_edges.append(
                    EdgeRow(
                        source_id=p_uuid,
                        source_kind=SourceTargetKind.NODE,
                        target_id=scheme_uuid,
                        target_kind=SourceTargetKind.SCHEME,
                        role=EdgeRole.PREMISE,
                    )
                )
            temp_edges.append(
                EdgeRow(
                    source_id=scheme_uuid,
                    source_kind=SourceTargetKind.SCHEME,
                    target_id=conclusion_uuid,
                    target_kind=SourceTargetKind.NODE,
                    role=EdgeRole.CONCLUSION,
                )
            )

            # Call check_hume on temp graph
            violations = check_hume(nodes, schemes + [temp_scheme], edges + temp_edges)
            my_violation = next((v for v in violations if v.scheme_id == scheme_uuid), None)
            if my_violation:
                raise WhatIfValidationError(idx, my_violation.message)

            # Add to actual collections
            schemes.append(temp_scheme)
            edges.extend(temp_edges)

        elif op_type == "add_conflict":
            label = op_data.get("label")
            a = op_data.get("a")
            b = op_data.get("b")

            if not label:
                raise WhatIfValidationError(idx, "Label du conflit manquant")

            # Check duplication
            clean_label = label.strip().lower()
            if clean_label in res_map:
                raise WhatIfValidationError(idx, f"Label du conflit '{label}' déjà existant")

            a_uuid = resolve_target(a, res_map, idx)
            b_uuid = resolve_target(b, res_map, idx)

            scheme_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, label)

            schemes.append(
                SchemeRow(
                    id=scheme_uuid,
                    scheme=SchemeType.CONFLIT,
                    strength=None,
                    weight=1.0,
                    metadata_={"imported_id": label},
                )
            )

            edges.append(
                EdgeRow(
                    source_id=a_uuid,
                    source_kind=SourceTargetKind.NODE,
                    target_id=scheme_uuid,
                    target_kind=SourceTargetKind.SCHEME,
                    role=EdgeRole.CONFLICTING,
                )
            )
            edges.append(
                EdgeRow(
                    source_id=scheme_uuid,
                    source_kind=SourceTargetKind.SCHEME,
                    target_id=b_uuid,
                    target_kind=SourceTargetKind.NODE,
                    role=EdgeRole.CONFLICTED,
                )
            )

        else:
            raise WhatIfValidationError(idx, f"Opération inconnue : '{op_type}'")

        ops_applied.append(op_data)

    new_g = GraphData(
        nodes=nodes,
        schemes=schemes,
        edges=edges,
        credences=credences,
    )

    return new_g, AppliedReport(
        cascaded_schemes=sorted(set(cascaded_schemes)),
        ops_applied=ops_applied,
    )
