import sys
import uuid
import asyncio

# Add backend to python path
sys.path.insert(0, r"c:\Users\natbo\Documents\buildandburn\brain\backend")

from sqlalchemy import delete
from src.database import AsyncSessionLocal
from src.models import (
    Node,
    Edge,
    SchemeNode,
    CausalEdge,
    NodeType,
    SchemeType,
    SchemeStrength,
    SourceTargetKind,
    EdgeRole,
    TierKind,
    WeightKind,
)

def resolve_uuid(id_val: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, id_val)

async def main():
    async with AsyncSessionLocal() as session:
        # 1. Clean database
        await session.execute(delete(CausalEdge))
        await session.execute(delete(Edge))
        await session.execute(delete(SchemeNode))
        await session.execute(delete(Node))
        await session.commit()
        print("Database cleared.")

        # 2. Define nodes
        p1_id = resolve_uuid("p1")
        p2_id = resolve_uuid("p2")
        cA_id = resolve_uuid("cA")
        cB_id = resolve_uuid("cB")

        p1 = Node(
            id=p1_id,
            type=NodeType.DESCRIPTIF,
            domain="paradoxe",
            text="La physique macroscopique obéit à des lois déterministes.",
            tier=TierKind.CERTAIN,
            weight_kind=WeightKind.CREDENCE,
            weight=0.95,
            metadata_={"imported_id": "p1"}
        )
        p2 = Node(
            id=p2_id,
            type=NodeType.DESCRIPTIF,
            domain="paradoxe",
            text="L'introspection humaine témoigne d'un sentiment d'agence.",
            tier=TierKind.CERTAIN,
            weight_kind=WeightKind.CREDENCE,
            weight=0.95,
            metadata_={"imported_id": "p2"}
        )
        cA = Node(
            id=cA_id,
            type=NodeType.NORMATIF_CONCLUSION,
            domain="paradoxe",
            text="Nous devons abandonner la notion de choix moral ultime.",
            tier=TierKind.MOYEN,
            weight_kind=WeightKind.ENGAGEMENT,
            weight=0.60,
            metadata_={"imported_id": "cA"}
        )
        cB = Node(
            id=cB_id,
            type=NodeType.NORMATIF_CONCLUSION,
            domain="paradoxe",
            text="Nous devons préserver la notion de responsabilité morale rétributive.",
            tier=TierKind.MOYEN,
            weight_kind=WeightKind.ENGAGEMENT,
            weight=0.60,
            metadata_={"imported_id": "cB"}
        )

        session.add_all([p1, p2, cA, cB])
        await session.flush()

        # 3. Define scheme nodes
        inf1_id = resolve_uuid("inf1")
        inf2_id = resolve_uuid("inf2")
        conflit_id = resolve_uuid("conflit")

        inf1 = SchemeNode(
            id=inf1_id,
            scheme=SchemeType.INFERENCE,
            strength=SchemeStrength.DEFAISABLE_FORT,
            weight=2.0,
            metadata_={"imported_id": "inf1"}
        )
        inf2 = SchemeNode(
            id=inf2_id,
            scheme=SchemeType.INFERENCE,
            strength=SchemeStrength.DEFAISABLE_FORT,
            weight=2.0,
            metadata_={"imported_id": "inf2"}
        )
        conflit = SchemeNode(
            id=conflit_id,
            scheme=SchemeType.CONFLIT,
            weight=1.0,
            metadata_={"imported_id": "conflit"}
        )

        session.add_all([inf1, inf2, conflit])
        await session.flush()

        # 4. Define Edges
        edges = [
            # Inference 1: p1 => cA
            Edge(
                id=uuid.uuid4(),
                source_id=p1_id,
                target_id=inf1_id,
                source_kind=SourceTargetKind.NODE,
                target_kind=SourceTargetKind.SCHEME,
                role=EdgeRole.PREMISE
            ),
            Edge(
                id=uuid.uuid4(),
                source_id=inf1_id,
                target_id=cA_id,
                source_kind=SourceTargetKind.SCHEME,
                target_kind=SourceTargetKind.NODE,
                role=EdgeRole.CONCLUSION
            ),
            # Inference 2: p2 => cB
            Edge(
                id=uuid.uuid4(),
                source_id=p2_id,
                target_id=inf2_id,
                source_kind=SourceTargetKind.NODE,
                target_kind=SourceTargetKind.SCHEME,
                role=EdgeRole.PREMISE
            ),
            Edge(
                id=uuid.uuid4(),
                source_id=inf2_id,
                target_id=cB_id,
                source_kind=SourceTargetKind.SCHEME,
                target_kind=SourceTargetKind.NODE,
                role=EdgeRole.CONCLUSION
            ),
            # Conflict: cA vs cB
            Edge(
                id=uuid.uuid4(),
                source_id=cA_id,
                target_id=conflit_id,
                source_kind=SourceTargetKind.NODE,
                target_kind=SourceTargetKind.SCHEME,
                role=EdgeRole.CONFLICTING
            ),
            Edge(
                id=uuid.uuid4(),
                source_id=conflit_id,
                target_id=cB_id,
                source_kind=SourceTargetKind.SCHEME,
                target_kind=SourceTargetKind.NODE,
                role=EdgeRole.CONFLICTED
            )
        ]

        session.add_all(edges)
        await session.commit()
        print("Paradox test graph seeded successfully!")

if __name__ == "__main__":
    asyncio.run(main())
