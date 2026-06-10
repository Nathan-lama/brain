import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.abspath("backend"))

from sqlalchemy import select
from src.database import AsyncSessionLocal
from src.models import Node, SchemeNode, Edge, SourceTargetKind

def resolve_uuid(val):
    if not val:
        return uuid.uuid4()
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(val)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_DNS, val)

async def inspect():
    ra6_id = resolve_uuid("ra6")
    print(f"ra6 UUID: {ra6_id}")
    
    async with AsyncSessionLocal() as session:
        # Query SchemeNode
        res = await session.execute(select(SchemeNode).filter(SchemeNode.id == ra6_id))
        s_node = res.scalar_one_or_none()
        if not s_node:
            print("Scheme node ra6 not found in DB!")
            return
            
        print(f"SchemeNode found: id={s_node.id}, scheme={s_node.scheme}, strength={s_node.strength}")
        
        # Query incoming and outgoing edges
        res_edges = await session.execute(select(Edge).filter((Edge.source_id == ra6_id) | (Edge.target_id == ra6_id)))
        edges = res_edges.scalars().all()
        print(f"Found {len(edges)} edges linked to ra6:")
        
        for edge in edges:
            print(f"  Edge: {edge.id}")
            print(f"    Source: id={edge.source_id}, kind={edge.source_kind}, role={edge.role}")
            print(f"    Target: id={edge.target_id}, kind={edge.target_kind}")
            
            # Find the linked node
            if edge.source_kind == SourceTargetKind.NODE:
                n_res = await session.execute(select(Node).filter(Node.id == edge.source_id))
                node = n_res.scalar_one_or_none()
                if node:
                    print(f"      Node (Premise): [{node.type}] (Tier: {node.tier}) - {node.text}")
            elif edge.target_kind == SourceTargetKind.NODE:
                n_res = await session.execute(select(Node).filter(Node.id == edge.target_id))
                node = n_res.scalar_one_or_none()
                if node:
                    print(f"      Node (Conclusion): [{node.type}] (Tier: {node.tier}) - {node.text}")

if __name__ == "__main__":
    asyncio.run(inspect())
