import asyncio
import uuid

from sqlalchemy import delete

from src.database import AsyncSessionLocal
from src.models import (
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

# Fixed UUIDs for determinism
IDS = {
    # Nodes
    "d1": uuid.UUID("d1111111-1111-1111-1111-111111111111"),
    "d2": uuid.UUID("d2222222-2222-2222-2222-222222222222"),
    "b1": uuid.UUID("b1111111-1111-1111-1111-111111111111"),
    "c1": uuid.UUID("c1111111-1111-1111-1111-111111111111"),
    "p1": uuid.UUID("f1111111-1111-1111-1111-111111111111"),
    # Scheme Nodes
    "ra1": uuid.UUID("a1111111-1111-1111-1111-111111111111"),
    "ca1": uuid.UUID("a2222222-2222-2222-2222-222222222222"),
    # Edges
    "e1": uuid.UUID("e1111111-1111-1111-1111-111111111111"),
    "e2": uuid.UUID("e2222222-2222-2222-2222-222222222222"),
    "e3": uuid.UUID("e3333333-3333-3333-3333-333333333333"),
    "e4": uuid.UUID("e4444444-4444-4444-4444-444444444444"),
    "e5": uuid.UUID("e5555555-5555-5555-5555-555555555555"),
    "e6": uuid.UUID("e6666666-6666-6666-6666-666666666666"),
}


async def seed(session=None):
    if session is not None:
        await _run_seed(session)
    else:
        async with AsyncSessionLocal() as active_session:
            await _run_seed(active_session)


async def _run_seed(session):
    # Clear existing data
    await session.execute(delete(Edge))
    await session.execute(delete(SchemeNode))
    await session.execute(delete(Node))

    # Insert Nodes
    nodes = [
        Node(
            id=IDS["d1"],
            type=NodeType.DESCRIPTIF,
            domain="climat",
            text="Les émissions de CO2 réchauffent l'atmosphère.",
            tier=TierKind.CERTAIN,
            weight_kind=WeightKind.CREDENCE,
            weight=0.95,
            embedding=None,
            metadata_={"source": "IPCC"},
        ),
        Node(
            id=IDS["d2"],
            type=NodeType.DESCRIPTIF,
            domain="climat",
            text="Les activités humaines produisent de grandes quantités de CO2.",
            tier=TierKind.CERTAIN,
            weight_kind=WeightKind.CREDENCE,
            weight=0.95,
            embedding=None,
            metadata_={"source": "IEA"},
        ),
        Node(
            id=IDS["b1"],
            type=NodeType.PONT_NORMATIF,
            domain="ethique",
            text="Si nos activités nuisent à l'atmosphère, nous devez les réduire.",
            tier=TierKind.FORT,
            weight_kind=WeightKind.ENGAGEMENT,
            weight=0.80,
            embedding=None,
            metadata_={},
        ),
        Node(
            id=IDS["c1"],
            type=NodeType.NORMATIF_CONCLUSION,
            domain="politique",
            text="Nous devons réduire nos émissions de CO2 industrielles.",
            tier=TierKind.FORT,
            weight_kind=WeightKind.ENGAGEMENT,
            weight=0.80,
            embedding=None,
            metadata_={},
        ),
        Node(
            id=IDS["p1"],
            type=NodeType.NORMATIF_POSITION,
            domain="economie",
            text="Nous devons maintenir la croissance économique à tout prix.",
            tier=TierKind.MOYEN,
            weight_kind=WeightKind.ENGAGEMENT,
            weight=0.60,
            embedding=None,
            metadata_={},
        ),
    ]

    # Insert Scheme Nodes
    scheme_nodes = [
        SchemeNode(
            id=IDS["ra1"],
            scheme=SchemeType.INFERENCE,
            strength=SchemeStrength.DEFAISABLE_FAIBLE,
            weight=1.0,
            metadata_={"description": "Inférence d'action collective"},
        ),
        SchemeNode(
            id=IDS["ca1"],
            scheme=SchemeType.CONFLIT,
            strength=None,
            weight=1.0,
            metadata_={"description": "Conflit d'intérêts économiques vs écologiques"},
        ),
    ]

    # Insert Edges
    edges = [
        # ra1 inputs (premises)
        Edge(
            id=IDS["e1"],
            source_id=IDS["d1"],
            target_id=IDS["ra1"],
            source_kind=SourceTargetKind.NODE,
            target_kind=SourceTargetKind.SCHEME,
            role=EdgeRole.PREMISE,
        ),
        Edge(
            id=IDS["e2"],
            source_id=IDS["d2"],
            target_id=IDS["ra1"],
            source_kind=SourceTargetKind.NODE,
            target_kind=SourceTargetKind.SCHEME,
            role=EdgeRole.PREMISE,
        ),
        Edge(
            id=IDS["e3"],
            source_id=IDS["b1"],
            target_id=IDS["ra1"],
            source_kind=SourceTargetKind.NODE,
            target_kind=SourceTargetKind.SCHEME,
            role=EdgeRole.PREMISE,
        ),
        # ra1 output (conclusion)
        Edge(
            id=IDS["e4"],
            source_id=IDS["ra1"],
            target_id=IDS["c1"],
            source_kind=SourceTargetKind.SCHEME,
            target_kind=SourceTargetKind.NODE,
            role=EdgeRole.CONCLUSION,
        ),
        # ca1 input (conflicting premise)
        Edge(
            id=IDS["e5"],
            source_id=IDS["p1"],
            target_id=IDS["ca1"],
            source_kind=SourceTargetKind.NODE,
            target_kind=SourceTargetKind.SCHEME,
            role=EdgeRole.CONFLICTING,
        ),
        # ca1 output (conflicted target)
        Edge(
            id=IDS["e6"],
            source_id=IDS["ca1"],
            target_id=IDS["c1"],
            source_kind=SourceTargetKind.SCHEME,
            target_kind=SourceTargetKind.NODE,
            role=EdgeRole.CONFLICTED,
        ),
    ]

    session.add_all(nodes)
    session.add_all(scheme_nodes)
    session.add_all(edges)
    await session.commit()
    print("Database successfully seeded with deterministic argument graph.")


if __name__ == "__main__":
    asyncio.run(seed())
