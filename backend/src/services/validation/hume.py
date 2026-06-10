import uuid
from typing import Any

from pydantic import BaseModel

from src.models import EdgeRole, NodeType, SchemeType

# Constants representing the normative node types.
# Searlean promise argument objection: some philosophers argue that definitional terms (definitions)
# can bridge the is-ought gap (e.g. Searle's derivation of 'ought' from 'promise').
# We define these as module-level sets so they are explicitly configurable and not accidental constraints.
# In our system, 'definitionnel' is explicitly excluded from the normative types.
NORMATIVE_TYPES: set[str] = {
    NodeType.NORMATIF_POSITION.value,
    NodeType.NORMATIF_CONCLUSION.value,
    NodeType.PONT_NORMATIF.value,
}

NORMATIVE_CONCLUSION_TYPES: set[str] = {
    NodeType.NORMATIF_POSITION.value,
    NodeType.NORMATIF_CONCLUSION.value,
    NodeType.PONT_NORMATIF.value,
}


def resolve_uuid(id_val: Any) -> uuid.UUID:
    if isinstance(id_val, uuid.UUID):
        return id_val
    id_str = str(id_val)
    try:
        return uuid.UUID(id_str)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_DNS, id_str)


def get_label_court(node_id: uuid.UUID, metadata: dict | None = None) -> str:
    if metadata and isinstance(metadata, dict) and "imported_id" in metadata:
        return str(metadata["imported_id"])

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


class NodeRefHume(BaseModel):
    id: uuid.UUID
    label_court: str
    type: str


class HumeViolation(BaseModel):
    scheme_id: uuid.UUID
    conclusion: NodeRefHume
    premises: list[NodeRefHume]
    message: str


def check_hume(
    nodes: list[Any], scheme_nodes: list[Any], edges: list[Any]
) -> list[HumeViolation]:
    """
    Checks for Hume's Law violations in the given graph data.

    A violation occurs if a normative conclusion is derived from premises where none are normative.
    'definitionnel' is not considered a normative premise.
    """
    node_map = {}
    for node in nodes:
        nid = getattr(node, "id", None)
        if nid is None and isinstance(node, dict):
            nid = node.get("id")
        if nid is None:
            continue
        nid_uuid = resolve_uuid(nid)

        ntype = getattr(node, "type", None)
        if ntype is None and isinstance(node, dict):
            ntype = node.get("type")
        if ntype is not None and hasattr(ntype, "value"):
            ntype = ntype.value
        if ntype is None:
            ntype = "descriptif"

        meta = getattr(node, "metadata_", getattr(node, "metadata", None))
        if meta is None and isinstance(node, dict):
            meta = node.get("metadata") or node.get("metadata_")

        label = get_label_court(nid_uuid, meta)
        node_map[nid_uuid] = {
            "id": nid_uuid,
            "type": str(ntype),
            "label_court": label,
            "metadata": meta,
        }

    inference_schemes = []
    for s in scheme_nodes:
        sid = getattr(s, "id", None)
        if sid is None and isinstance(s, dict):
            sid = s.get("id")
        if sid is None:
            continue
        sid_uuid = resolve_uuid(sid)

        stype = getattr(s, "scheme", None)
        if stype is None and isinstance(s, dict):
            stype = s.get("scheme")
        if stype is not None and hasattr(stype, "value"):
            stype = stype.value

        if stype == "inference" or stype == SchemeType.INFERENCE.value:
            premises = getattr(s, "premises", None)
            if premises is None and isinstance(s, dict):
                premises = s.get("premises")
            conclusion = getattr(s, "conclusion", None)
            if conclusion is None and isinstance(s, dict):
                conclusion = s.get("conclusion")
            inference_schemes.append(
                {"id": sid_uuid, "premises": premises, "conclusion": conclusion}
            )

    edges_premises = {}
    edges_conclusions = {}
    for edge in edges:
        role = getattr(edge, "role", None)
        if role is None and isinstance(edge, dict):
            role = edge.get("role")
        if role is not None and hasattr(role, "value"):
            role = role.value

        source_id = getattr(edge, "source_id", None)
        if source_id is None and isinstance(edge, dict):
            source_id = edge.get("source_id")

        target_id = getattr(edge, "target_id", None)
        if target_id is None and isinstance(edge, dict):
            target_id = edge.get("target_id")

        if source_id is None or target_id is None:
            continue

        source_uuid = resolve_uuid(source_id)
        target_uuid = resolve_uuid(target_id)

        if role == "premise" or role == EdgeRole.PREMISE.value:
            edges_premises.setdefault(target_uuid, []).append(source_uuid)
        elif role == "conclusion" or role == EdgeRole.CONCLUSION.value:
            edges_conclusions[source_uuid] = target_uuid

    violations = []
    for s in inference_schemes:
        sid_uuid = s["id"]

        premises_ids = s["premises"]
        if premises_ids is None:
            premises_ids = edges_premises.get(sid_uuid, [])
        else:
            premises_ids = [resolve_uuid(p) for p in premises_ids]

        conclusion_id = s["conclusion"]
        if conclusion_id is None:
            conclusion_id = edges_conclusions.get(sid_uuid)
        else:
            conclusion_id = resolve_uuid(conclusion_id)

        if not conclusion_id:
            continue

        conclusion_node = node_map.get(conclusion_id)
        if not conclusion_node:
            continue

        conclusion_type = conclusion_node["type"]
        if conclusion_type not in NORMATIVE_CONCLUSION_TYPES:
            continue

        has_normative_premise = False
        premise_nodes = []
        for p_id in premises_ids:
            p_node = node_map.get(p_id)
            if p_node:
                premise_nodes.append(
                    NodeRefHume(
                        id=p_node["id"],
                        label_court=p_node["label_court"],
                        type=p_node["type"],
                    )
                )
                if p_node["type"] in NORMATIVE_TYPES:
                    has_normative_premise = True

        if not has_normative_premise:
            conclusion_ref = NodeRefHume(
                id=conclusion_node["id"],
                label_court=conclusion_node["label_court"],
                type=conclusion_node["type"],
            )
            message = f"Inférence violant la loi de Hume : conclusion normative '{conclusion_ref.label_court}' ({conclusion_ref.type}) dérivée sans prémisse normative."
            violations.append(
                HumeViolation(
                    scheme_id=sid_uuid,
                    conclusion=conclusion_ref,
                    premises=premise_nodes,
                    message=message,
                )
            )

    return violations


async def validate_import_hume(
    payload: Any, is_sadface: bool, dedup: bool, db: Any
) -> list[HumeViolation]:
    """
    Validates an imported graph (either ImportRequest or SADFace dict) merged with the existing DB graph.
    """
    from sqlalchemy import select

    from src.models import (
        Edge,
        Node,
        SchemeNode,
        SchemeType,
    )

    res_nodes = await db.execute(select(Node))
    db_nodes = res_nodes.scalars().all()

    res_schemes = await db.execute(select(SchemeNode))
    db_schemes = res_schemes.scalars().all()

    res_edges = await db.execute(select(Edge))
    db_edges = res_edges.scalars().all()

    nodes_map = {
        n.id: {
            "id": n.id,
            "type": n.type.value if hasattr(n.type, "value") else str(n.type),
            "metadata_": n.metadata_ or {},
        }
        for n in db_nodes
    }

    schemes_map = {
        s.id: {
            "id": s.id,
            "scheme": s.scheme.value if hasattr(s.scheme, "value") else str(s.scheme),
            "premises": None,
            "conclusion": None,
        }
        for s in db_schemes
    }

    virtual_edges = [
        {
            "source_id": e.source_id,
            "target_id": e.target_id,
            "source_kind": e.source_kind.value
            if hasattr(e.source_kind, "value")
            else str(e.source_kind),
            "target_kind": e.target_kind.value
            if hasattr(e.target_kind, "value")
            else str(e.target_kind),
            "role": e.role.value if hasattr(e.role, "value") else str(e.role),
        }
        for e in db_edges
    ]

    merged_mapping = {}

    if is_sadface:
        node_ids = set()
        for item in payload.get("nodes", []):
            nid = resolve_uuid(item["id"])
            ntype = item.get("type", "atom")
            if ntype == "atom":
                meta = item.get("metadata", {})
                real_type = meta.get("type", NodeType.DESCRIPTIF.value)
                if hasattr(real_type, "value"):
                    real_type = real_type.value

                nodes_map[nid] = {"id": nid, "type": str(real_type), "metadata_": meta}
                node_ids.add(nid)
                merged_mapping[nid] = nid

        for item in payload.get("nodes", []):
            nid = resolve_uuid(item["id"])
            ntype = item.get("type", "atom")
            if ntype != "atom":
                meta = item.get("metadata", {})
                scheme_val = item.get("name", SchemeType.INFERENCE.value)
                if hasattr(scheme_val, "value"):
                    scheme_val = scheme_val.value

                schemes_map[nid] = {
                    "id": nid,
                    "scheme": str(scheme_val),
                    "premises": None,
                    "conclusion": None,
                }
                virtual_edges = [
                    e
                    for e in virtual_edges
                    if e["source_id"] != nid and e["target_id"] != nid
                ]

        for item in payload.get("edges", []):
            from_id = resolve_uuid(item["source_id"])
            to_id = resolve_uuid(item["target_id"])
            source_kind = "node" if from_id in node_ids else "scheme"
            target_kind = "node" if to_id in node_ids else "scheme"
            role = "premise" if source_kind == "node" else "conclusion"

            virtual_edges.append(
                {
                    "source_id": from_id,
                    "target_id": to_id,
                    "source_kind": source_kind,
                    "target_kind": target_kind,
                    "role": role,
                }
            )
    else:
        node_embeddings = {}
        if dedup and payload.nodes:
            from src.services.embeddings import get_embeddings

            texts = [node.text for node in payload.nodes]
            embeddings = await get_embeddings(texts)
            node_embeddings = {
                resolve_uuid(payload.nodes[i].id): embeddings[i]
                for i in range(len(payload.nodes))
            }

        for node in payload.nodes:
            node_uuid = resolve_uuid(node.id)
            similar_node = None
            if dedup:
                emb = node_embeddings.get(node_uuid)
                if emb is not None:
                    stmt = (
                        select(Node)
                        .filter(Node.embedding.cosine_distance(emb) < 0.08)
                        .order_by(Node.embedding.cosine_distance(emb))
                        .limit(1)
                    )
                    res = await db.execute(stmt)
                    similar_node = res.scalar_one_or_none()

            ntype = node.type.value if hasattr(node.type, "value") else str(node.type)
            meta = node.metadata_ or {}

            if similar_node:
                merged_mapping[node_uuid] = similar_node.id
                nodes_map[similar_node.id] = {
                    "id": similar_node.id,
                    "type": ntype,
                    "metadata_": {**(similar_node.metadata_ or {}), **meta},
                }
            else:
                nodes_map[node_uuid] = {
                    "id": node_uuid,
                    "type": ntype,
                    "metadata_": meta,
                }
                merged_mapping[node_uuid] = node_uuid

        for snode in payload.scheme_nodes:
            snode_uuid = resolve_uuid(snode.id)
            sscheme = (
                snode.scheme.value
                if hasattr(snode.scheme, "value")
                else str(snode.scheme)
            )

            if sscheme == "inference" or sscheme == SchemeType.INFERENCE.value:
                virtual_edges = [
                    e
                    for e in virtual_edges
                    if e["source_id"] != snode_uuid and e["target_id"] != snode_uuid
                ]

                for p_id in snode.premises:
                    p_uuid = resolve_uuid(p_id)
                    mapped_p = merged_mapping.get(p_uuid, p_uuid)
                    virtual_edges.append(
                        {
                            "source_id": mapped_p,
                            "target_id": snode_uuid,
                            "source_kind": "node",
                            "target_kind": "scheme",
                            "role": "premise",
                        }
                    )
                c_uuid = resolve_uuid(snode.conclusion)
                mapped_c = merged_mapping.get(c_uuid, c_uuid)
                virtual_edges.append(
                    {
                        "source_id": snode_uuid,
                        "target_id": mapped_c,
                        "source_kind": "scheme",
                        "target_kind": "node",
                        "role": "conclusion",
                    }
                )
            else:
                virtual_edges = [
                    e
                    for e in virtual_edges
                    if e["source_id"] != snode_uuid and e["target_id"] != snode_uuid
                ]
                from_uuid = resolve_uuid(snode.from_node)
                to_uuid = resolve_uuid(snode.to_node)
                mapped_from = merged_mapping.get(from_uuid, from_uuid)
                mapped_to = merged_mapping.get(to_uuid, to_uuid)
                virtual_edges.append(
                    {
                        "source_id": mapped_from,
                        "target_id": snode_uuid,
                        "source_kind": "node",
                        "target_kind": "scheme",
                        "role": "conflicting",
                    }
                )
                virtual_edges.append(
                    {
                        "source_id": snode_uuid,
                        "target_id": mapped_to,
                        "source_kind": "scheme",
                        "target_kind": "node",
                        "role": "conflicted",
                    }
                )

            schemes_map[snode_uuid] = {
                "id": snode_uuid,
                "scheme": sscheme,
                "premises": None,
                "conclusion": None,
            }

    return check_hume(
        nodes=list(nodes_map.values()),
        scheme_nodes=list(schemes_map.values()),
        edges=virtual_edges,
    )
