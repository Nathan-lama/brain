import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    BeliefSnapshot,
    Edge,
    EdgeRole,
    Event,
    Node,
    NodeType,
    SchemeNode,
    SchemeType,
    SourceTargetKind,
)
from src.services.tensions import TensionService


def to_dict(model: Any) -> dict[str, Any] | None:
    if model is None:
        return None
    d = {}
    ins = inspect(model)
    for col in model.__table__.columns:
        attr_name = col.name
        if attr_name == "metadata":
            attr_name = "metadata_"

        if attr_name in ins.unloaded or attr_name in ins.expired_attributes:
            val = model.__dict__.get(attr_name, None)
        else:
            val = getattr(model, attr_name)

        if hasattr(val, "tolist"):
            val = val.tolist()

        if isinstance(val, (uuid.UUID, datetime)):
            d[col.name] = str(val)
        elif isinstance(val, enum.Enum):
            d[col.name] = val.value
        else:
            d[col.name] = val
    return d


class VersioningService:
    @staticmethod
    async def log_event(
        db: AsyncSession,
        entity_type: str,
        entity_id: uuid.UUID,
        op: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> Event:
        event = Event(
            entity_type=entity_type,
            entity_id=entity_id,
            op=op,
            before=before,
            after=after,
        )
        db.add(event)
        await db.flush()
        return event

    @staticmethod
    async def get_events(db: AsyncSession) -> list[Event]:
        res = await db.execute(select(Event).order_by(Event.created_at.desc()))
        return list(res.scalars().all())

    @staticmethod
    async def get_snapshots(db: AsyncSession) -> list[BeliefSnapshot]:
        res = await db.execute(
            select(BeliefSnapshot).order_by(BeliefSnapshot.created_at.desc())
        )
        return list(res.scalars().all())

    @staticmethod
    def get_snapshot_diff(from_payload: dict, to_payload: dict) -> dict:
        # 1. Compare Nodes
        from_nodes = {uuid.UUID(str(n["id"])): n for n in from_payload.get("nodes", [])}
        to_nodes = {uuid.UUID(str(n["id"])): n for n in to_payload.get("nodes", [])}

        claims_ajoutes = [to_nodes[nid] for nid in to_nodes if nid not in from_nodes]
        claims_supprimes = [
            from_nodes[nid] for nid in from_nodes if nid not in to_nodes
        ]
        claims_modifies = []
        for nid in to_nodes:
            if nid in from_nodes:
                tn = to_nodes[nid]
                fn = from_nodes[nid]
                # Compare critical visual/logical fields
                if (
                    tn.get("text") != fn.get("text")
                    or tn.get("tier") != fn.get("tier")
                    or tn.get("weight") != fn.get("weight")
                    or tn.get("confidence") != fn.get("confidence")
                    or tn.get("type") != fn.get("type")
                    or tn.get("domain") != fn.get("domain")
                ):
                    claims_modifies.append(tn)

        # 2. Compare Edges
        from_edges = {uuid.UUID(str(e["id"])): e for e in from_payload.get("edges", [])}
        to_edges = {uuid.UUID(str(e["id"])): e for e in to_payload.get("edges", [])}

        edges_ajoutes = [to_edges[eid] for eid in to_edges if eid not in from_edges]
        edges_supprimes = [from_edges[eid] for eid in from_edges if eid not in to_edges]

        # 3. Delta des tensions computed in-memory
        tensions_from = TensionService.get_tensions_from_payload(from_payload)
        tensions_to = TensionService.get_tensions_from_payload(to_payload)

        t_from_map = {t["id"]: t for t in tensions_from}
        t_to_map = {t["id"]: t for t in tensions_to}

        tensions_resolues = [t for tid, t in t_from_map.items() if tid not in t_to_map]
        tensions_nouvelles = [t for tid, t in t_to_map.items() if tid not in t_from_map]

        return {
            "claims_ajoutes": claims_ajoutes,
            "claims_supprimes": claims_supprimes,
            "claims_modifies": claims_modifies,
            "edges_ajoutes": edges_ajoutes,
            "edges_supprimes": edges_supprimes,
            "tensions_resolues": tensions_resolues,
            "tensions_nouvelles": tensions_nouvelles,
        }

    @staticmethod
    async def restore_snapshot(db: AsyncSession, snapshot: BeliefSnapshot) -> None:
        payload = snapshot.payload

        # 1. Restore Nodes
        nodes_res = await db.execute(select(Node))
        current_nodes = {n.id: n for n in nodes_res.scalars().all()}
        snap_nodes = {uuid.UUID(str(n["id"])): n for n in payload.get("nodes", [])}

        # Delete nodes not in snapshot
        for nid, node in current_nodes.items():
            if nid not in snap_nodes:
                before_dict = to_dict(node)
                await db.delete(node)
                await VersioningService.log_event(
                    db, "node", nid, "delete", before_dict, None
                )

        # Create or update nodes
        for nid, n_data in snap_nodes.items():
            emb = n_data.get("embedding")
            if nid in current_nodes:
                # Update
                node = current_nodes[nid]
                before_dict = to_dict(node)
                node.type = NodeType(n_data["type"])
                node.domain = n_data["domain"]
                node.text = n_data["text"]
                if "tier" in n_data:
                    node.tier = n_data["tier"]
                    node.weight = float(n_data.get("weight", 0.6))
                    node.weight_kind = n_data.get("weight_kind")
                else:
                    conf = float(n_data.get("confidence", 0.6))
                    if conf > 0.875:
                        node.tier = "certain"
                        node.weight = 0.95
                    elif conf > 0.700:
                        node.tier = "fort"
                        node.weight = 0.80
                    elif conf > 0.500:
                        node.tier = "moyen"
                        node.weight = 0.60
                    elif conf > 0.300:
                        node.tier = "faible"
                        node.weight = 0.40
                    else:
                        node.tier = "speculatif"
                        node.weight = 0.20

                    if node.type in ("descriptif", "empirique", "definitionnel"):
                        node.weight_kind = "credence"
                    else:
                        node.weight_kind = "engagement"
                node.embedding = emb
                node.metadata_ = n_data.get("metadata", {})
                after_dict = to_dict(node)
                await db.flush()
                if before_dict != after_dict:
                    await VersioningService.log_event(
                        db, "node", nid, "update", before_dict, after_dict
                    )
            else:
                # Create
                tier_val = n_data.get("tier")
                weight_val = n_data.get("weight")
                weight_kind_val = n_data.get("weight_kind")

                if tier_val is None:
                    conf = float(n_data.get("confidence", 0.6))
                    if conf > 0.875:
                        tier_val = "certain"
                        weight_val = 0.95
                    elif conf > 0.700:
                        tier_val = "fort"
                        weight_val = 0.80
                    elif conf > 0.500:
                        tier_val = "moyen"
                        weight_val = 0.60
                    elif conf > 0.300:
                        tier_val = "faible"
                        weight_val = 0.40
                    else:
                        tier_val = "speculatif"
                        weight_val = 0.20

                    ntype = NodeType(n_data["type"])
                    if ntype in ("descriptif", "empirique", "definitionnel"):
                        weight_kind_val = "credence"
                    else:
                        weight_kind_val = "engagement"
                else:
                    weight_val = float(weight_val) if weight_val is not None else 0.6

                node = Node(
                    id=nid,
                    type=NodeType(n_data["type"]),
                    domain=n_data["domain"],
                    text=n_data["text"],
                    tier=tier_val,
                    weight_kind=weight_kind_val,
                    weight=weight_val,
                    embedding=emb,
                    metadata_=n_data.get("metadata", {}),
                )
                db.add(node)
                after_dict = to_dict(node)
                await db.flush()
                await VersioningService.log_event(
                    db, "node", nid, "create", None, after_dict
                )

        # 2. Restore SchemeNodes
        schemes_res = await db.execute(select(SchemeNode))
        current_schemes = {s.id: s for s in schemes_res.scalars().all()}
        snap_schemes = {
            uuid.UUID(str(s["id"])): s for s in payload.get("scheme_nodes", [])
        }

        # Delete schemes not in snapshot
        for sid, scheme in current_schemes.items():
            if sid not in snap_schemes:
                before_dict = to_dict(scheme)
                await db.delete(scheme)
                await VersioningService.log_event(
                    db, "scheme_node", sid, "delete", before_dict, None
                )

        # Create or update schemes
        for sid, s_data in snap_schemes.items():
            if sid in current_schemes:
                # Update
                scheme = current_schemes[sid]
                before_dict = to_dict(scheme)
                scheme.scheme = SchemeType(s_data["scheme"])
                scheme.weight = float(s_data["weight"])
                scheme.metadata_ = s_data.get("metadata", {})
                after_dict = to_dict(scheme)
                await db.flush()
                if before_dict != after_dict:
                    await VersioningService.log_event(
                        db, "scheme_node", sid, "update", before_dict, after_dict
                    )
            else:
                # Create
                scheme = SchemeNode(
                    id=sid,
                    scheme=SchemeType(s_data["scheme"]),
                    weight=float(s_data["weight"]),
                    metadata_=s_data.get("metadata", {}),
                )
                db.add(scheme)
                after_dict = to_dict(scheme)
                await db.flush()
                await VersioningService.log_event(
                    db, "scheme_node", sid, "create", None, after_dict
                )

        # 3. Restore Edges
        edges_res = await db.execute(select(Edge))
        current_edges = {e.id: e for e in edges_res.scalars().all()}
        snap_edges = {uuid.UUID(str(e["id"])): e for e in payload.get("edges", [])}

        # Delete edges not in snapshot
        for eid, edge in current_edges.items():
            if eid not in snap_edges:
                before_dict = to_dict(edge)
                await db.delete(edge)
                await VersioningService.log_event(
                    db, "edge", eid, "delete", before_dict, None
                )

        # Create or update edges
        for eid, e_data in snap_edges.items():
            if eid in current_edges:
                # Update
                edge = current_edges[eid]
                before_dict = to_dict(edge)
                edge.source_id = uuid.UUID(str(e_data["source_id"]))
                edge.target_id = uuid.UUID(str(e_data["target_id"]))
                edge.source_kind = SourceTargetKind(e_data["source_kind"])
                edge.target_kind = SourceTargetKind(e_data["target_kind"])
                edge.role = EdgeRole(e_data["role"])
                after_dict = to_dict(edge)
                await db.flush()
                if before_dict != after_dict:
                    await VersioningService.log_event(
                        db, "edge", eid, "update", before_dict, after_dict
                    )
            else:
                # Create
                edge = Edge(
                    id=eid,
                    source_id=uuid.UUID(str(e_data["source_id"])),
                    target_id=uuid.UUID(str(e_data["target_id"])),
                    source_kind=SourceTargetKind(e_data["source_kind"]),
                    target_kind=SourceTargetKind(e_data["target_kind"]),
                    role=EdgeRole(e_data["role"]),
                )
                db.add(edge)
                after_dict = to_dict(edge)
                await db.flush()
                await VersioningService.log_event(
                    db, "edge", eid, "create", None, after_dict
                )

        await db.commit()
