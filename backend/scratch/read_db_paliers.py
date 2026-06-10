import asyncio

from sqlalchemy import select

from src.database import AsyncSessionLocal
from src.models import Edge, Node, SchemeNode, SchemeType


async def main():
    async with AsyncSessionLocal() as session:
        # Get all nodes
        res_nodes = await session.execute(select(Node))
        nodes = res_nodes.scalars().all()
        print("--- NODES IN DB ---")
        node_map = {}
        for n in nodes:
            node_map[n.id] = n
            imported_id = n.metadata_.get("imported_id") if n.metadata_ else None
            print(
                f"ID: {n.id} | ImportedID: {imported_id} | Type: {n.type} | Tier: {n.tier} | Text: {n.text[:40]}"
            )

        # Get all conflicts
        res_schemes = await session.execute(
            select(SchemeNode).filter(SchemeNode.scheme == SchemeType.CONFLIT)
        )
        schemes = res_schemes.scalars().all()
        print("\n--- CONFLICT SCHEME NODES ---")

        # Get all edges
        res_edges = await session.execute(select(Edge))
        edges = res_edges.scalars().all()

        # Build connections
        for s in schemes:
            imported_id = s.metadata_.get("imported_id") if s.metadata_ else None
            # Find edges connected to this scheme node
            s_edges = [e for e in edges if e.target_id == s.id or e.source_id == s.id]
            print(f"\nConflict Scheme ID: {s.id} | ImportedID: {imported_id}")
            for e in s_edges:
                print(
                    f"  Edge: {e.role} | Source: {e.source_id} (Type: {node_map.get(e.source_id).type if e.source_id in node_map else 'scheme'}) | Target: {e.target_id} (Type: {node_map.get(e.target_id).type if e.target_id in node_map else 'scheme'})"
                )


if __name__ == "__main__":
    asyncio.run(main())
