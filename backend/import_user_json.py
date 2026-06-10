import json
import sys
import uuid

sys.path.insert(0, r"c:\Users\natbo\Documents\buildandburn\brain\backend")

import asyncio

from sqlalchemy import delete

from src.database import AsyncSessionLocal
from src.models import (
    STRENGTH_TO_WEIGHT,
    Edge,
    EdgeRole,
    Node,
    NodeType,
    SchemeNode,
    SchemeStrength,
    SchemeType,
    SourceTargetKind,
    TierKind,
    WeightKind,
)


# Helper function to get UUID
def resolve_uuid(val):
    if not val:
        return uuid.uuid4()
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(val)
    except ValueError:
        # Generate deterministic UUID from string
        return uuid.uuid5(uuid.NAMESPACE_DNS, val)


# Helper function to resolve tier and weight
def resolve_tier_and_weight(type_str, conf_val):
    conf = float(conf_val) if conf_val is not None else 0.6
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

    if type_str in ("descriptif", "empirique", "definitionnel"):
        weight_kind_val = "credence"
    else:
        weight_kind_val = "engagement"

    return tier_val, weight_val, weight_kind_val


async def main():
    with open(
        r"C:\Users\natbo\.gemini\antigravity\brain\d8fd9b1e-da36-4ee2-b342-0f4b267264fe\scratch\user_import.json",
        encoding="utf-8",
    ) as f:
        data = json.load(f)

    async with AsyncSessionLocal() as session:
        # Clear database
        await session.execute(delete(Edge))
        await session.execute(delete(SchemeNode))
        await session.execute(delete(Node))
        await session.flush()

        # Insert Nodes
        nodes_map = {}
        for n_data in data["nodes"]:
            nid = resolve_uuid(n_data["id"])
            tier, weight, w_kind = resolve_tier_and_weight(
                n_data["type"], n_data.get("confidence")
            )
            node = Node(
                id=nid,
                type=NodeType(n_data["type"]),
                domain=n_data["domain"],
                text=n_data["text"],
                tier=TierKind(tier),
                weight=weight,
                weight_kind=WeightKind(w_kind),
                metadata_={},
            )
            session.add(node)
            nodes_map[n_data["id"]] = nid

        await session.flush()

        # Insert Scheme Nodes and Edges
        for s_data in data["scheme_nodes"]:
            sid = resolve_uuid(s_data["id"])
            stype = SchemeType(s_data["scheme"])

            strength_val = None
            if stype == SchemeType.INFERENCE:
                strength_val = s_data.get("strength")
                if not strength_val:
                    w = float(s_data.get("weight", 1.0))
                    if w == 5.0:
                        strength_val = SchemeStrength.DEDUCTIF
                    elif w == 2.0:
                        strength_val = SchemeStrength.DEFAISABLE_FORT
                    else:
                        strength_val = SchemeStrength.DEFAISABLE_FAIBLE
                weight = STRENGTH_TO_WEIGHT[SchemeStrength(strength_val)]
            else:
                weight = 1.0

            snode = SchemeNode(
                id=sid, scheme=stype, strength=strength_val, weight=weight, metadata_={}
            )
            session.add(snode)
            await session.flush()

            # Create Edges
            if stype == SchemeType.INFERENCE:
                for p_id in s_data.get("premises", []):
                    p_uuid = nodes_map.get(p_id, resolve_uuid(p_id))
                    edge = Edge(
                        source_id=p_uuid,
                        target_id=sid,
                        source_kind=SourceTargetKind.NODE,
                        target_kind=SourceTargetKind.SCHEME,
                        role=EdgeRole.PREMISE,
                    )
                    session.add(edge)
                conclusion_id = s_data.get("conclusion")
                if conclusion_id:
                    c_uuid = nodes_map.get(conclusion_id, resolve_uuid(conclusion_id))
                    edge = Edge(
                        source_id=sid,
                        target_id=c_uuid,
                        source_kind=SourceTargetKind.SCHEME,
                        target_kind=SourceTargetKind.NODE,
                        role=EdgeRole.CONCLUSION,
                    )
                    session.add(edge)
            elif stype == SchemeType.CONFLIT:
                # In user_import.json, conflicts have "from" and "to" (which are node IDs)
                from_id = s_data.get("from")
                to_id = s_data.get("to")
                if from_id and to_id:
                    from_uuid = nodes_map.get(from_id, resolve_uuid(from_id))
                    to_uuid = nodes_map.get(to_id, resolve_uuid(to_id))
                    edge1 = Edge(
                        source_id=from_uuid,
                        target_id=sid,
                        source_kind=SourceTargetKind.NODE,
                        target_kind=SourceTargetKind.SCHEME,
                        role=EdgeRole.CONFLICTING,
                    )
                    edge2 = Edge(
                        source_id=sid,
                        target_id=to_uuid,
                        source_kind=SourceTargetKind.SCHEME,
                        target_kind=SourceTargetKind.NODE,
                        role=EdgeRole.CONFLICTED,
                    )
                    session.add(edge1)
                    session.add(edge2)

        await session.commit()
        print("Data imported successfully!")


if __name__ == "__main__":
    asyncio.run(main())
