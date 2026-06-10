import uuid
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models import (
    STRENGTH_TO_WEIGHT,
    BeliefSnapshot,
    Domain,
    Edge,
    EdgeRole,
    Node,
    NodeType,
    SchemeNode,
    SchemeStrength,
    SchemeType,
    SourceTargetKind,
)


def resolve_tier_and_weight(
    type_: NodeType, tier_val: str | None, conf_val: float | None
) -> tuple[str | None, float, str | None]:
    tier_str = (
        tier_val.value
        if hasattr(tier_val, "value")
        else (str(tier_val) if tier_val is not None else None)
    )
    if tier_str is None and conf_val is not None:
        conf = float(conf_val)
        if conf > 0.875:
            tier_str = "certain"
        elif conf > 0.700:
            tier_str = "fort"
        elif conf > 0.500:
            tier_str = "moyen"
        elif conf > 0.300:
            tier_str = "faible"
        else:
            tier_str = "speculatif"

    if type_ in (NodeType.DESCRIPTIF, NodeType.EMPIRIQUE, NodeType.DEFINITIONNEL):
        w_kind = "credence"
    else:
        w_kind = "engagement"

    weights = {
        "certain": 0.95,
        "fort": 0.8,
        "moyen": 0.6,
        "faible": 0.4,
        "speculatif": 0.2,
    }
    w_val = weights.get(tier_str, 0.6)
    return tier_str, w_val, w_kind


def resolve_uuid(id_val: Any) -> uuid.UUID:
    if isinstance(id_val, uuid.UUID):
        return id_val
    id_str = str(id_val)
    try:
        return uuid.UUID(id_str)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_DNS, id_str)


from src.schemas import (
    AlternativeSolutionOut,
    CausalEdgeIn,
    CausalEdgeOut,
    CausalGraphResponse,
    DomainIn,
    DomainOut,
    EdgeOut,
    EventOut,
    ExtractRequest,
    GraphExport,
    GraphResponse,
    ImportRequest,
    ImportSchemeConflit,
    ImportSchemeInference,
    NodeDetailResponse,
    NodeOut,
    NodesPaginatedResponse,
    NodeUpdateIn,
    NoteGenerateRequest,
    RelatedNodeResponse,
    SchemeNodeOut,
    SchemeNodeUpdateIn,
    SnapshotDiffOut,
    SnapshotOut,
    SolveResponse,
    TensionDiffOut,
    TensionOut,
    TensionResolveRequest,
    WhatIfRequest,
    WhatIfResponse,
)
from src.services.causal import CausalService
from src.services.embeddings import get_embeddings
from src.services.extraction import extract_pipeline
from src.services.solver import CoherenceSolverService
from src.services.tensions import TensionService
from src.services.validation.hume import check_hume, validate_import_hume
from src.services.versioning import VersioningService, to_dict

app = FastAPI(title="Second Brain Backend", version="0.1.0")

# Configure CORS
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
)


from fastapi.responses import JSONResponse

from src.services.solver import CostInvariantViolation


@app.exception_handler(CostInvariantViolation)
async def cost_invariant_violation_handler(request, exc: CostInvariantViolation):
    return JSONResponse(
        status_code=500,
        content={
            "expected": exc.expected,
            "got": exc.got,
            "constraint_ids": [str(cid) for cid in exc.constraint_ids],
        },
    )


@app.on_event("startup")
async def startup_event():
    from src.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        default_names = [
            "justice",
            "économie",
            "santé",
            "éducation",
            "environnement",
            "institutions",
            "climat",
            "ethique",
            "politique",
            "général",
        ]
        res = await session.execute(select(Domain))
        existing = res.scalars().all()
        if not existing:
            for name in default_names:
                session.add(Domain(name=name))
            await session.commit()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/domains", response_model=list[DomainOut])
async def list_domains(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Domain).order_by(Domain.name))
    return res.scalars().all()


@app.post("/domains", response_model=DomainOut)
async def create_domain(payload: DomainIn, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Domain).filter(Domain.name == payload.name))
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Domain already exists")
    domain = Domain(name=payload.name, parent_id=payload.parent_id)
    db.add(domain)
    await db.commit()
    await db.refresh(domain)
    return domain


@app.put("/domains/{id}", response_model=DomainOut)
async def update_domain(
    id: UUID, payload: DomainIn, db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(Domain).filter(Domain.id == id))
    domain = res.scalar_one_or_none()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    old_name = domain.name
    new_name = payload.name

    domain.name = new_name
    domain.parent_id = payload.parent_id
    await db.flush()

    if old_name != new_name:
        await db.execute(
            update(Node).where(Node.domain == old_name).values(domain=new_name)
        )
        await db.flush()

    await db.commit()
    await db.refresh(domain)
    return domain


@app.delete("/domains/{id}")
async def delete_domain(id: UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Domain).filter(Domain.id == id))
    domain = res.scalar_one_or_none()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    fallback_name = "général"
    if domain.parent_id:
        res_parent = await db.execute(
            select(Domain).filter(Domain.id == domain.parent_id)
        )
        parent = res_parent.scalar_one_or_none()
        if parent:
            fallback_name = parent.name

    res_fallback = await db.execute(select(Domain).filter(Domain.name == fallback_name))
    if not res_fallback.scalar_one_or_none():
        db.add(Domain(name=fallback_name))
        await db.flush()

    await db.execute(
        update(Node).where(Node.domain == domain.name).values(domain=fallback_name)
    )

    await db.execute(
        update(Domain).where(Domain.parent_id == id).values(parent_id=domain.parent_id)
    )

    await db.delete(domain)
    await db.commit()
    return {"status": "ok"}


@app.post("/import")
async def import_graph(
    payload: ImportRequest,
    dedup: bool = Query(False),
    allow_hume_violations: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    violations = await validate_import_hume(
        payload, is_sadface=False, dedup=dedup, db=db
    )
    if violations and not allow_hume_violations:
        return JSONResponse(
            status_code=422,
            content={
                "detail": "hume_violations",
                "violations": [v.model_dump(mode="json") for v in violations],
            },
        )

    # 1. Fetch embeddings for all nodes in batch
    texts = [node.text for node in payload.nodes]
    embeddings = await get_embeddings(texts)
    node_embeddings = {
        resolve_uuid(payload.nodes[i].id): embeddings[i]
        for i in range(len(payload.nodes))
    }

    # 2. Keep track of node ID mappings for deduplication merges
    # key: imported_node_id -> value: actual_node_id
    merged_mapping: dict[UUID, UUID] = {}

    created_count = 0
    updated_count = 0
    merged_count = 0

    # Process nodes
    for node in payload.nodes:
        node_uuid = resolve_uuid(node.id)
        emb = node_embeddings[node_uuid]
        similar_node = None

        if dedup:
            # Query for similar node: cosine similarity > 0.92 means cosine distance < 0.08
            stmt = (
                select(Node)
                .filter(Node.embedding.cosine_distance(emb) < 0.08)
                .order_by(Node.embedding.cosine_distance(emb))
                .limit(1)
            )
            res = await db.execute(stmt)
            similar_node = res.scalar_one_or_none()

        tier_val, weight_val, weight_kind_val = resolve_tier_and_weight(
            node.type, node.tier, node.confidence
        )

        if similar_node is not None:
            # Merge: map imported ID to existing similar node's ID
            merged_mapping[node_uuid] = similar_node.id

            # Merge metadata and update tier/weight/weight_kind
            existing_metadata = similar_node.metadata_ or {}
            imported_metadata = node.metadata_ or {}

            before_dict = to_dict(similar_node)
            similar_node.metadata_ = {**existing_metadata, **imported_metadata}
            similar_node.tier = tier_val
            similar_node.weight = weight_val
            similar_node.weight_kind = weight_kind_val
            await db.flush()
            after_dict = to_dict(similar_node)
            if before_dict != after_dict:
                await VersioningService.log_event(
                    db, "node", similar_node.id, "update", before_dict, after_dict
                )

            merged_count += 1
        else:
            # Upsert
            res = await db.execute(select(Node).filter(Node.id == node_uuid))
            existing_node = res.scalar_one_or_none()

            if existing_node is not None:
                # Update
                before_dict = to_dict(existing_node)
                existing_node.type = node.type
                existing_node.domain = node.domain
                existing_node.text = node.text
                existing_node.tier = tier_val
                existing_node.weight = weight_val
                existing_node.weight_kind = weight_kind_val
                existing_node.embedding = emb
                existing_node.metadata_ = node.metadata_ or {}
                await db.flush()
                after_dict = to_dict(existing_node)
                if before_dict != after_dict:
                    await VersioningService.log_event(
                        db, "node", existing_node.id, "update", before_dict, after_dict
                    )
                updated_count += 1
            else:
                # Create
                db_node = Node(
                    id=node_uuid,
                    type=node.type,
                    domain=node.domain,
                    text=node.text,
                    tier=tier_val,
                    weight_kind=weight_kind_val,
                    weight=weight_val,
                    embedding=emb,
                    metadata_=node.metadata_ or {},
                )
                db.add(db_node)
                await db.flush()
                after_dict = to_dict(db_node)
                await VersioningService.log_event(
                    db, "node", db_node.id, "create", None, after_dict
                )
                created_count += 1

            # Default mapping to itself
            merged_mapping[node_uuid] = node_uuid

    # Flush node changes so their foreign keys/ids are valid
    await db.flush()

    # 3. Process scheme nodes and edges
    scheme_count = 0
    for snode in payload.scheme_nodes:
        snode_uuid = resolve_uuid(snode.id)
        # Check if scheme node already exists
        res = await db.execute(select(SchemeNode).filter(SchemeNode.id == snode_uuid))
        existing_snode = res.scalar_one_or_none()

        strength_val = getattr(snode, "strength", None)
        if snode.scheme == SchemeType.INFERENCE:
            if not strength_val:
                strength_val = SchemeStrength.DEFAISABLE_FAIBLE
            weight_val = STRENGTH_TO_WEIGHT[strength_val]
        else:
            strength_val = None
            weight_val = 1.0

        if existing_snode is not None:
            before_dict = to_dict(existing_snode)
            existing_snode.scheme = snode.scheme
            existing_snode.strength = strength_val
            existing_snode.weight = weight_val
            await db.flush()
            after_dict = to_dict(existing_snode)
            if before_dict != after_dict:
                await VersioningService.log_event(
                    db,
                    "scheme_node",
                    existing_snode.id,
                    "update",
                    before_dict,
                    after_dict,
                )
        else:
            db_snode = SchemeNode(
                id=snode_uuid,
                scheme=snode.scheme,
                strength=strength_val,
                weight=weight_val,
                metadata_={},
            )
            db.add(db_snode)
            await db.flush()
            after_dict = to_dict(db_snode)
            await VersioningService.log_event(
                db, "scheme_node", db_snode.id, "create", None, after_dict
            )

        scheme_count += 1

        # Delete existing edges for this scheme node
        stmt = select(Edge).filter(
            or_(Edge.source_id == snode_uuid, Edge.target_id == snode_uuid)
        )
        edges_to_delete_res = await db.execute(stmt)
        edges_to_delete = edges_to_delete_res.scalars().all()
        for e in edges_to_delete:
            before_dict = to_dict(e)
            await VersioningService.log_event(
                db, "edge", e.id, "delete", before_dict, None
            )
            await db.delete(e)
        await db.flush()

        # Map source/target node IDs through merged_mapping
        if isinstance(snode, ImportSchemeInference):
            # Premises to Scheme Node (role: premise)
            for p_id in snode.premises:
                p_uuid = resolve_uuid(p_id)
                mapped_p = merged_mapping.get(p_uuid, p_uuid)
                edge_premise = Edge(
                    source_id=mapped_p,
                    target_id=snode_uuid,
                    source_kind=SourceTargetKind.NODE,
                    target_kind=SourceTargetKind.SCHEME,
                    role=EdgeRole.PREMISE,
                )
                db.add(edge_premise)
                await db.flush()
                after_dict = to_dict(edge_premise)
                await VersioningService.log_event(
                    db, "edge", edge_premise.id, "create", None, after_dict
                )

            # Scheme Node to Conclusion (role: conclusion)
            c_uuid = resolve_uuid(snode.conclusion)
            mapped_c = merged_mapping.get(c_uuid, c_uuid)
            edge_conclusion = Edge(
                source_id=snode_uuid,
                target_id=mapped_c,
                source_kind=SourceTargetKind.SCHEME,
                target_kind=SourceTargetKind.NODE,
                role=EdgeRole.CONCLUSION,
            )
            db.add(edge_conclusion)
            await db.flush()
            after_dict = to_dict(edge_conclusion)
            await VersioningService.log_event(
                db, "edge", edge_conclusion.id, "create", None, after_dict
            )

        elif isinstance(snode, ImportSchemeConflit):
            # Mapped source/target
            from_uuid = resolve_uuid(snode.from_node)
            to_uuid = resolve_uuid(snode.to_node)
            mapped_from = merged_mapping.get(from_uuid, from_uuid)
            mapped_to = merged_mapping.get(to_uuid, to_uuid)

            # From Node to Conflict Scheme Node (role: conflicting)
            edge_conflicting = Edge(
                source_id=mapped_from,
                target_id=snode_uuid,
                source_kind=SourceTargetKind.NODE,
                target_kind=SourceTargetKind.SCHEME,
                role=EdgeRole.CONFLICTING,
            )
            db.add(edge_conflicting)
            await db.flush()
            after_dict = to_dict(edge_conflicting)
            await VersioningService.log_event(
                db, "edge", edge_conflicting.id, "create", None, after_dict
            )

            # Conflict Scheme Node to To Node (role: conflicted)
            edge_conflicted = Edge(
                source_id=snode_uuid,
                target_id=mapped_to,
                source_kind=SourceTargetKind.SCHEME,
                target_kind=SourceTargetKind.NODE,
                role=EdgeRole.CONFLICTED,
            )
            db.add(edge_conflicted)
            await db.flush()
            after_dict = to_dict(edge_conflicted)
            await VersioningService.log_event(
                db, "edge", edge_conflicted.id, "create", None, after_dict
            )

    await db.commit()

    response_data = {
        "nodes_created": created_count,
        "nodes_updated": updated_count,
        "nodes_merged": merged_count,
        "schemes_created_or_updated": scheme_count,
    }
    if violations:
        response_data["warnings"] = {
            "hume_violations": [v.model_dump(mode="json") for v in violations]
        }
    return response_data


@app.post("/snapshot")
async def create_snapshot(
    label: str = Query("Snapshot"),
    db: AsyncSession = Depends(get_db),
):
    # Fetch all nodes
    nodes_res = await db.execute(select(Node))
    nodes = nodes_res.scalars().all()

    # Fetch all scheme nodes
    schemes_res = await db.execute(select(SchemeNode))
    schemes = schemes_res.scalars().all()

    # Fetch all edges
    edges_res = await db.execute(select(Edge))
    edges = edges_res.scalars().all()

    # Export graph structure
    export = GraphExport(
        nodes=[NodeOut.model_validate(n) for n in nodes],
        scheme_nodes=[SchemeNodeOut.model_validate(s) for s in schemes],
        edges=[EdgeOut.model_validate(e) for e in edges],
    )

    # Save snapshot
    snapshot = BeliefSnapshot(
        label=label,
        payload=export.model_dump(mode="json", by_alias=True),
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)

    return {
        "id": snapshot.id,
        "label": snapshot.label,
        "created_at": snapshot.created_at,
    }


async def enrich_nodes(nodes: list[Node], db: AsyncSession):
    if not nodes:
        return
    solver_res = {}
    try:
        solver_res = await CoherenceSolverService.solve(db)
    except Exception:
        pass
    accepted_set = set(solver_res.get("accepted", []))

    credences = {}
    try:
        from src.services.causal import CausalService

        credences = await CausalService.compute_credences(db)
    except Exception:
        pass

    incoherence_score = solver_res.get("incoherence_score", 0.0)
    violated_constraints = solver_res.get("violated_constraints", [])
    violated_node_ids = set()
    if incoherence_score > 0.0:
        for vc in violated_constraints:
            node_refs = (
                vc.node_refs if hasattr(vc, "node_refs") else vc.get("node_refs", [])
            )
            for ref in node_refs:
                ref_id = ref.id if hasattr(ref, "id") else ref.get("id")
                if ref_id:
                    violated_node_ids.add(ref_id)

    for n in nodes:
        if n.id in accepted_set:
            n.coherence = "accepted"
        elif n.id in violated_node_ids:
            n.coherence = "tension_inevitable"
        else:
            n.coherence = "rejete_arbitre"

        if n.type == NodeType.EMPIRIQUE:
            n.correspondence = credences.get(n.id, n.weight)
        else:
            n.correspondence = None


@app.get("/nodes", response_model=NodesPaginatedResponse)
async def list_nodes(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("weight"),
    order: str = Query("desc"),
    domain: str | None = Query(None),
    node_type: NodeType | None = Query(None, alias="type"),
    db: AsyncSession = Depends(get_db),
):
    # Base query for filtering
    stmt = select(Node)
    if domain:
        stmt = stmt.filter(Node.domain == domain)
    if node_type:
        stmt = stmt.filter(Node.type == node_type)

    # Count total query
    count_stmt = select(func.count()).select_from(stmt.subquery())
    count_res = await db.execute(count_stmt)
    total = count_res.scalar_one()

    # Sorting validation and application
    allowed_sort = ["weight", "created_at", "updated_at"]
    if sort_by == "confidence":
        sort_by = "weight"
    if sort_by not in allowed_sort:
        sort_by = "weight"

    col = getattr(Node, sort_by)
    if order == "desc":
        stmt = stmt.order_by(col.desc())
    else:
        stmt = stmt.order_by(col.asc())

    # Pagination
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    res = await db.execute(stmt)
    items = res.scalars().all()

    await enrich_nodes(items, db)

    pages = (total + limit - 1) // limit if total > 0 else 0

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": pages,
        "items": items,
    }


@app.get("/graph", response_model=GraphResponse)
async def get_graph(
    domain: str | None = Query(None),
    node_type: NodeType | None = Query(None, alias="type"),
    db: AsyncSession = Depends(get_db),
):
    # Fetch filtered I-nodes
    stmt = select(Node)
    if domain:
        stmt = stmt.filter(Node.domain == domain)
    if node_type:
        stmt = stmt.filter(Node.type == node_type)
    res = await db.execute(stmt)
    nodes = res.scalars().all()
    node_ids = {n.id for n in nodes}

    await enrich_nodes(nodes, db)

    # Fetch all scheme nodes
    res_schemes = await db.execute(select(SchemeNode))
    scheme_nodes = res_schemes.scalars().all()
    scheme_map = {s.id: s for s in scheme_nodes}

    # Fetch all edges
    res_edges = await db.execute(select(Edge))
    edges = res_edges.scalars().all()

    # Group edges by scheme_id
    from collections import defaultdict

    scheme_in_edges = defaultdict(list)
    scheme_out_edges = defaultdict(list)

    for edge in edges:
        if (
            edge.source_kind == SourceTargetKind.NODE
            and edge.target_kind == SourceTargetKind.SCHEME
        ):
            scheme_in_edges[edge.target_id].append(edge)
        elif (
            edge.source_kind == SourceTargetKind.SCHEME
            and edge.target_kind == SourceTargetKind.NODE
        ):
            scheme_out_edges[edge.source_id].append(edge)

    flat_edges = []
    # For each scheme node, unfold connections
    for s_id, s_node in scheme_map.items():
        relation = s_node.metadata_.get("relation") if s_node.metadata_ else None
        if not relation:
            if s_node.scheme == SchemeType.INFERENCE:
                relation = "soutient"
            elif s_node.scheme == SchemeType.CONFLIT:
                relation = "contredit"
            elif s_node.scheme == SchemeType.PREFERENCE:
                relation = "implique"
            else:
                relation = "soutient"

        in_list = scheme_in_edges[s_id]
        out_list = scheme_out_edges[s_id]

        for in_edge in in_list:
            for out_edge in out_list:
                if in_edge.source_id in node_ids and out_edge.target_id in node_ids:
                    # Generate deterministic UUID using namespaces to ensure key stability
                    edge_id = uuid.uuid5(
                        uuid.NAMESPACE_DNS, f"{in_edge.id}-{out_edge.id}"
                    )
                    flat_edges.append(
                        {
                            "id": edge_id,
                            "source": in_edge.source_id,
                            "target": out_edge.target_id,
                            "relation": relation,
                            "scheme_id": s_id,
                            "strength": s_node.strength,
                            "weight": s_node.weight,
                        }
                    )

    return {
        "nodes": nodes,
        "edges": flat_edges,
    }


@app.get("/nodes/{id}", response_model=NodeDetailResponse)
async def get_node_details(
    id: UUID,
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Node).filter(Node.id == id))
    node = res.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    res_schemes = await db.execute(select(SchemeNode))
    scheme_nodes = res_schemes.scalars().all()
    scheme_map = {s.id: s for s in scheme_nodes}

    res_edges = await db.execute(select(Edge))
    edges = res_edges.scalars().all()

    from collections import defaultdict

    scheme_in_edges = defaultdict(list)
    scheme_out_edges = defaultdict(list)
    for edge in edges:
        if (
            edge.source_kind == SourceTargetKind.NODE
            and edge.target_kind == SourceTargetKind.SCHEME
        ):
            scheme_in_edges[edge.target_id].append(edge)
        elif (
            edge.source_kind == SourceTargetKind.SCHEME
            and edge.target_kind == SourceTargetKind.NODE
        ):
            scheme_out_edges[edge.source_id].append(edge)

    res_nodes = await db.execute(select(Node))
    all_nodes = res_nodes.scalars().all()
    nodes_map = {n.id: n for n in all_nodes}

    neighbors = []

    # Outgoing connections (where our node is source, leading to targets via scheme nodes)
    for s_id, in_edges in scheme_in_edges.items():
        if any(e.source_id == id for e in in_edges):
            s_node = scheme_map.get(s_id)
            if s_node:
                relation = (
                    s_node.metadata_.get("relation") if s_node.metadata_ else None
                )
                if not relation:
                    if s_node.scheme == SchemeType.INFERENCE:
                        relation = "soutient"
                    elif s_node.scheme == SchemeType.CONFLIT:
                        relation = "contredit"
                    elif s_node.scheme == SchemeType.PREFERENCE:
                        relation = "implique"
                    else:
                        relation = "soutient"

                for out_edge in scheme_out_edges[s_id]:
                    target_node = nodes_map.get(out_edge.target_id)
                    if target_node and target_node.id != id:
                        neighbors.append(
                            {
                                "node": target_node,
                                "direction": "outgoing",
                                "relation": relation,
                                "scheme_id": s_id,
                            }
                        )

    # Incoming connections (where our node is target, coming from sources via scheme nodes)
    for s_id, out_edges in scheme_out_edges.items():
        if any(e.target_id == id for e in out_edges):
            s_node = scheme_map.get(s_id)
            if s_node:
                relation = (
                    s_node.metadata_.get("relation") if s_node.metadata_ else None
                )
                if not relation:
                    if s_node.scheme == SchemeType.INFERENCE:
                        relation = "soutient"
                    elif s_node.scheme == SchemeType.CONFLIT:
                        relation = "contredit"
                    elif s_node.scheme == SchemeType.PREFERENCE:
                        relation = "implique"
                    else:
                        relation = "soutient"

                for in_edge in scheme_in_edges[s_id]:
                    source_node = nodes_map.get(in_edge.source_id)
                    if source_node and source_node.id != id:
                        neighbors.append(
                            {
                                "node": source_node,
                                "direction": "incoming",
                                "relation": relation,
                                "scheme_id": s_id,
                            }
                        )

    await enrich_nodes([node] + [nb["node"] for nb in neighbors], db)

    return {
        "node": node,
        "neighbors": neighbors,
    }


@app.put("/nodes/{id}", response_model=NodeOut)
async def update_node(
    id: UUID, payload: NodeUpdateIn, db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(Node).filter(Node.id == id))
    node = res.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    before_dict = to_dict(node)

    if payload.text is not None:
        node.text = payload.text
    if payload.domain is not None:
        node.domain = payload.domain
    if payload.tier is not None:
        tier_val, weight_val, weight_kind_val = resolve_tier_and_weight(
            node.type, payload.tier, None
        )
        node.tier = tier_val
        node.weight = weight_val
        node.weight_kind = weight_kind_val

    await db.flush()
    await db.refresh(node)

    after_dict = to_dict(node)
    if before_dict != after_dict:
        await VersioningService.log_event(
            db, "node", node.id, "update", before_dict, after_dict
        )

    await db.commit()
    return node


@app.get("/nodes/{id}/related", response_model=list[RelatedNodeResponse])
async def get_related_nodes(
    id: UUID,
    k: int = Query(8, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Node).filter(Node.id == id))
    node = res.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    if node.embedding is None:
        return []

    res_edges = await db.execute(select(Edge))
    edges = res_edges.scalars().all()

    from collections import defaultdict

    scheme_in_edges = defaultdict(list)
    scheme_out_edges = defaultdict(list)
    for edge in edges:
        if (
            edge.source_kind == SourceTargetKind.NODE
            and edge.target_kind == SourceTargetKind.SCHEME
        ):
            scheme_in_edges[edge.target_id].append(edge)
        elif (
            edge.source_kind == SourceTargetKind.SCHEME
            and edge.target_kind == SourceTargetKind.NODE
        ):
            scheme_out_edges[edge.source_id].append(edge)

    neighbor_ids = set()

    for s_id, in_edges in scheme_in_edges.items():
        if any(e.source_id == id for e in in_edges):
            for out_edge in scheme_out_edges[s_id]:
                neighbor_ids.add(out_edge.target_id)

    for s_id, out_edges in scheme_out_edges.items():
        if any(e.target_id == id for e in out_edges):
            for in_edge in scheme_in_edges[s_id]:
                neighbor_ids.add(in_edge.source_id)

    neighbor_ids.add(id)

    distance_expr = Node.embedding.cosine_distance(node.embedding)
    stmt = (
        select(Node, distance_expr.label("distance"))
        .filter(Node.id.not_in(list(neighbor_ids)))
        .filter(Node.embedding.isnot(None))
        .order_by("distance")
        .limit(k)
    )
    res_related = await db.execute(stmt)
    results = res_related.all()

    output = []
    for item in results:
        r_node, dist = item
        similarity = 1.0 - dist
        output.append(
            {
                "node": r_node,
                "similarity": similarity,
            }
        )

    return output


@app.post("/extract")
async def extract_arguments(
    payload: ExtractRequest,
    dry_run: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    import_req = await extract_pipeline(payload.text, db)

    if dry_run:
        return import_req

    # Materialize in database using the existing import endpoint logic
    import_result = await import_graph(payload=import_req, dedup=False, db=db)
    return import_result


@app.get("/tensions", response_model=list[TensionOut])
async def get_tensions(db: AsyncSession = Depends(get_db)):
    tensions = await TensionService.get_tensions(db)
    return tensions


@app.post("/tensions/resolve", response_model=TensionDiffOut)
async def resolve_tension(
    payload: TensionResolveRequest, db: AsyncSession = Depends(get_db)
):
    # 1. Fetch current tensions before action
    before_state_tensions = await TensionService.get_tensions(db)

    if payload.action == "reviser_node":
        if not payload.node_id:
            raise HTTPException(
                status_code=400, detail="node_id is required for reviser_node action"
            )
        res = await db.execute(select(Node).filter(Node.id == payload.node_id))
        node = res.scalar_one_or_none()
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")

        before_dict = to_dict(node)
        node.tier = None
        node.weight = 0.0
        after_dict = to_dict(node)
        await db.flush()
        await db.refresh(node)

        if before_dict != after_dict:
            await VersioningService.log_event(
                db, "node", node.id, "update", before_dict, after_dict
            )

        diff = await TensionService.get_tensions_incremental(
            db, payload.node_id, before_state_tensions
        )
        diff_out = TensionDiffOut.model_validate(diff)
        await db.commit()
        return diff_out

    elif payload.action == "accepter_paradoxe":
        if not payload.scheme_id:
            raise HTTPException(
                status_code=400,
                detail="scheme_id is required for accepter_paradoxe action",
            )
        res = await db.execute(
            select(SchemeNode).filter(SchemeNode.id == payload.scheme_id)
        )
        scheme = res.scalar_one_or_none()
        if not scheme:
            raise HTTPException(status_code=404, detail="SchemeNode not found")

        before_dict = to_dict(scheme)
        existing_meta = scheme.metadata_ or {}
        scheme.metadata_ = {**existing_meta, "paradoxe_assume": True}
        after_dict = to_dict(scheme)
        await db.flush()
        await db.refresh(scheme)

        if before_dict != after_dict:
            await VersioningService.log_event(
                db, "scheme_node", scheme.id, "update", before_dict, after_dict
            )

        diff = await TensionService.get_tensions_incremental(
            db, payload.scheme_id, before_state_tensions
        )
        diff_out = TensionDiffOut.model_validate(diff)
        await db.commit()
        return diff_out

    else:
        raise HTTPException(status_code=400, detail="Invalid action")


@app.get("/events", response_model=list[EventOut])
async def list_events(db: AsyncSession = Depends(get_db)):
    return await VersioningService.get_events(db)


@app.get("/snapshots", response_model=list[SnapshotOut])
async def list_snapshots(db: AsyncSession = Depends(get_db)):
    return await VersioningService.get_snapshots(db)


@app.get("/snapshots/diff", response_model=SnapshotDiffOut)
async def get_snapshot_diff(
    from_id: UUID = Query(..., alias="from"),
    to_id: UUID = Query(..., alias="to"),
    db: AsyncSession = Depends(get_db),
):
    res_from = await db.execute(
        select(BeliefSnapshot).filter(BeliefSnapshot.id == from_id)
    )
    snap_from = res_from.scalar_one_or_none()
    res_to = await db.execute(select(BeliefSnapshot).filter(BeliefSnapshot.id == to_id))
    snap_to = res_to.scalar_one_or_none()

    if not snap_from or not snap_to:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    diff = VersioningService.get_snapshot_diff(snap_from.payload, snap_to.payload)
    return diff


@app.post("/snapshots/{id}/restore")
async def restore_snapshot_endpoint(id: UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(BeliefSnapshot).filter(BeliefSnapshot.id == id))
    snapshot = res.scalar_one_or_none()
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    await VersioningService.restore_snapshot(db, snapshot)
    return {"status": "ok", "message": f"Snapshot {id} restored successfully"}


@app.get("/export/aif")
async def export_aif(db: AsyncSession = Depends(get_db)):
    res_nodes = await db.execute(select(Node))
    nodes = res_nodes.scalars().all()
    res_schemes = await db.execute(select(SchemeNode))
    schemes = res_schemes.scalars().all()
    res_edges = await db.execute(select(Edge))
    edges = res_edges.scalars().all()

    aif_nodes = []
    for n in nodes:
        aif_nodes.append(
            {
                "nodeID": str(n.id),
                "text": n.text,
                "type": "I",
                "metadata": {
                    "type": n.type,
                    "domain": n.domain,
                    "tier": n.tier,
                    "weight": n.weight,
                    "confidence": n.weight,
                },
            }
        )
    for s in schemes:
        aif_type = "RA"
        if s.scheme == SchemeType.CONFLIT:
            aif_type = "CA"
        elif s.scheme == SchemeType.PREFERENCE:
            aif_type = "PA"
        aif_nodes.append(
            {
                "nodeID": str(s.id),
                "text": "",
                "type": aif_type,
                "metadata": {
                    "scheme": s.scheme,
                    "weight": s.weight,
                    **(s.metadata_ or {}),
                },
            }
        )

    aif_edges = []
    for e in edges:
        aif_edges.append(
            {"edgeID": str(e.id), "fromID": str(e.source_id), "toID": str(e.target_id)}
        )

    return {"nodes": aif_nodes, "edges": aif_edges}


@app.post("/import/aif")
async def import_aif(payload: dict, db: AsyncSession = Depends(get_db)):
    nodes_to_insert = []
    schemes_to_insert = []
    edges_to_insert = []

    node_ids = set()
    scheme_ids = set()

    for item in payload.get("nodes", []):
        nid = resolve_uuid(item["nodeID"])
        ntype = item.get("type", "I")

        if ntype == "I":
            meta = item.get("metadata", {})
            ntype = meta.get("type", NodeType.DESCRIPTIF)
            tier_val, weight_val, weight_kind_val = resolve_tier_and_weight(
                ntype, meta.get("tier"), meta.get("confidence")
            )
            nodes_to_insert.append(
                Node(
                    id=nid,
                    type=ntype,
                    domain=meta.get("domain", "général"),
                    text=item.get("text", ""),
                    tier=tier_val,
                    weight_kind=weight_kind_val,
                    weight=weight_val,
                    embedding=None,
                    metadata_={},
                )
            )
            node_ids.add(nid)
        else:
            meta = item.get("metadata", {})
            stype = SchemeType.INFERENCE
            if ntype == "CA":
                stype = SchemeType.CONFLIT
            elif ntype == "PA":
                stype = SchemeType.PREFERENCE

            strength_val = None
            if stype == SchemeType.INFERENCE:
                strength_val = meta.get("strength")
                if not strength_val:
                    strength_val = SchemeStrength.DEFAISABLE_FAIBLE
                else:
                    try:
                        strength_val = SchemeStrength(strength_val)
                    except ValueError:
                        strength_val = SchemeStrength.DEFAISABLE_FAIBLE
                weight_val = STRENGTH_TO_WEIGHT[strength_val]
            else:
                weight_val = 1.0

            schemes_to_insert.append(
                SchemeNode(
                    id=nid,
                    scheme=stype,
                    strength=strength_val,
                    weight=weight_val,
                    metadata_={
                        k: v
                        for k, v in meta.items()
                        if k not in ("scheme", "weight", "strength")
                    },
                )
            )
            scheme_ids.add(nid)

    for item in payload.get("edges", []):
        eid = resolve_uuid(item.get("edgeID", str(uuid.uuid4())))
        from_id = resolve_uuid(item["fromID"])
        to_id = resolve_uuid(item["toID"])

        source_kind = (
            SourceTargetKind.NODE if from_id in node_ids else SourceTargetKind.SCHEME
        )
        target_kind = (
            SourceTargetKind.NODE if to_id in node_ids else SourceTargetKind.SCHEME
        )

        role = EdgeRole.PREMISE
        if source_kind == SourceTargetKind.SCHEME:
            role = EdgeRole.CONCLUSION

        edges_to_insert.append(
            Edge(
                id=eid,
                source_id=from_id,
                target_id=to_id,
                source_kind=source_kind,
                target_kind=target_kind,
                role=role,
            )
        )

    for n in nodes_to_insert:
        await db.merge(n)
    for s in schemes_to_insert:
        await db.merge(s)
    for e in edges_to_insert:
        await db.merge(e)

    await db.commit()
    return {
        "status": "ok",
        "nodes_imported": len(nodes_to_insert),
        "edges_imported": len(edges_to_insert),
    }


@app.get("/export/sadface")
async def export_sadface(db: AsyncSession = Depends(get_db)):
    res_nodes = await db.execute(select(Node))
    nodes = res_nodes.scalars().all()
    res_schemes = await db.execute(select(SchemeNode))
    schemes = res_schemes.scalars().all()
    res_edges = await db.execute(select(Edge))
    edges = res_edges.scalars().all()

    sad_nodes = []
    for n in nodes:
        sad_nodes.append(
            {
                "id": str(n.id),
                "text": n.text,
                "type": "atom",
                "metadata": {
                    "type": n.type,
                    "domain": n.domain,
                    "tier": n.tier,
                    "weight": n.weight,
                    "confidence": n.weight,
                },
            }
        )
    for s in schemes:
        metadata = {"weight": s.weight, **(s.metadata_ or {})}
        if s.scheme == SchemeType.INFERENCE:
            metadata["strength"] = s.strength or SchemeStrength.DEFAISABLE_FAIBLE

        sad_nodes.append(
            {"id": str(s.id), "type": "scheme", "name": s.scheme, "metadata": metadata}
        )

    sad_edges = []
    for e in edges:
        sad_edges.append(
            {
                "id": str(e.id),
                "source_id": str(e.source_id),
                "target_id": str(e.target_id),
            }
        )

    return {"nodes": sad_nodes, "edges": sad_edges}


@app.post("/import/sadface")
async def import_sadface(
    payload: dict,
    allow_hume_violations: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    violations = await validate_import_hume(
        payload, is_sadface=True, dedup=False, db=db
    )
    if violations and not allow_hume_violations:
        return JSONResponse(
            status_code=422,
            content={
                "detail": "hume_violations",
                "violations": [v.model_dump(mode="json") for v in violations],
            },
        )

    nodes_to_insert = []
    schemes_to_insert = []
    edges_to_insert = []

    node_ids = set()
    scheme_ids = set()

    for item in payload.get("nodes", []):
        nid = resolve_uuid(item["id"])
        ntype = item.get("type", "atom")

        if ntype == "atom":
            meta = item.get("metadata", {})
            ntype = meta.get("type", NodeType.DESCRIPTIF)
            tier_val, weight_val, weight_kind_val = resolve_tier_and_weight(
                ntype, meta.get("tier"), meta.get("confidence")
            )
            nodes_to_insert.append(
                Node(
                    id=nid,
                    type=ntype,
                    domain=meta.get("domain", "général"),
                    text=item.get("text", ""),
                    tier=tier_val,
                    weight_kind=weight_kind_val,
                    weight=weight_val,
                    embedding=None,
                    metadata_={},
                )
            )
            node_ids.add(nid)
        else:
            meta = item.get("metadata", {})
            scheme_val = item.get("name", SchemeType.INFERENCE)
            strength_val = meta.get("strength")

            if scheme_val == SchemeType.INFERENCE:
                if not strength_val:
                    strength_val = SchemeStrength.DEFAISABLE_FAIBLE
                weight_val = STRENGTH_TO_WEIGHT[strength_val]
            else:
                strength_val = None
                weight_val = meta.get("weight", 1.0)

            schemes_to_insert.append(
                SchemeNode(
                    id=nid,
                    scheme=scheme_val,
                    strength=strength_val,
                    weight=weight_val,
                    metadata_={
                        k: v for k, v in meta.items() if k not in ("weight", "strength")
                    },
                )
            )
            scheme_ids.add(nid)

    for item in payload.get("edges", []):
        eid = resolve_uuid(item.get("id", str(uuid.uuid4())))
        from_id = resolve_uuid(item["source_id"])
        to_id = resolve_uuid(item["target_id"])

        source_kind = (
            SourceTargetKind.NODE if from_id in node_ids else SourceTargetKind.SCHEME
        )
        target_kind = (
            SourceTargetKind.NODE if to_id in node_ids else SourceTargetKind.SCHEME
        )

        role = EdgeRole.PREMISE
        if source_kind == SourceTargetKind.SCHEME:
            role = EdgeRole.CONCLUSION

        edges_to_insert.append(
            Edge(
                id=eid,
                source_id=from_id,
                target_id=to_id,
                source_kind=source_kind,
                target_kind=target_kind,
                role=role,
            )
        )

    for n in nodes_to_insert:
        await db.merge(n)
    for s in schemes_to_insert:
        await db.merge(s)
    for e in edges_to_insert:
        await db.merge(e)

    await db.commit()
    response_data = {
        "status": "ok",
        "nodes_imported": len(nodes_to_insert),
        "edges_imported": len(edges_to_insert),
    }
    if violations:
        response_data["warnings"] = {
            "hume_violations": [v.model_dump(mode="json") for v in violations]
        }
    return response_data


@app.get("/export/graphml")
async def export_graphml(db: AsyncSession = Depends(get_db)):
    res_nodes = await db.execute(select(Node))
    nodes = res_nodes.scalars().all()
    res_schemes = await db.execute(select(SchemeNode))
    schemes = res_schemes.scalars().all()
    res_edges = await db.execute(select(Edge))
    edges = res_edges.scalars().all()

    await enrich_nodes(nodes, db)

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns"',
        '         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        '         xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">',
        '  <key id="label" for="node" attr.name="label" attr.type="string"/>',
        '  <key id="type" for="node" attr.name="type" attr.type="string"/>',
        '  <key id="domain" for="node" attr.name="domain" attr.type="string"/>',
        '  <key id="confidence" for="node" attr.name="confidence" attr.type="double"/>',
        '  <key id="coherence" for="node" attr.name="coherence" attr.type="string"/>',
        '  <key id="correspondence" for="node" attr.name="correspondence" attr.type="double"/>',
        '  <key id="scheme" for="node" attr.name="scheme" attr.type="string"/>',
        '  <key id="weight" for="node" attr.name="weight" attr.type="double"/>',
        '  <graph id="G" edgedefault="directed">',
    ]

    for n in nodes:
        xml_lines.append(f'    <node id="{n.id}">')
        xml_lines.append(f'      <data key="label">{n.text}</data>')
        xml_lines.append(f'      <data key="type">{n.type}</data>')
        xml_lines.append(f'      <data key="domain">{n.domain}</data>')
        xml_lines.append(f'      <data key="confidence">{n.weight}</data>')
        if n.coherence:
            xml_lines.append(f'      <data key="coherence">{n.coherence}</data>')
        if n.correspondence is not None:
            xml_lines.append(
                f'      <data key="correspondence">{n.correspondence}</data>'
            )
        xml_lines.append("    </node>")

    for s in schemes:
        xml_lines.append(f'    <node id="{s.id}">')
        xml_lines.append(f'      <data key="label">[{s.scheme}]</data>')
        xml_lines.append('      <data key="type">scheme</data>')
        xml_lines.append(f'      <data key="scheme">{s.scheme}</data>')
        xml_lines.append(f'      <data key="weight">{s.weight}</data>')
        xml_lines.append("    </node>")

    for e in edges:
        xml_lines.append(
            f'    <edge id="{e.id}" source="{e.source_id}" target="{e.target_id}"/>'
        )

    xml_lines.append("  </graph>")
    xml_lines.append("</graphml>")

    xml_content = "\n".join(xml_lines)
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": "attachment; filename=graph.graphml"},
    )


@app.get("/export/dot")
async def export_dot(db: AsyncSession = Depends(get_db)):
    res_nodes = await db.execute(select(Node))
    nodes = res_nodes.scalars().all()
    res_schemes = await db.execute(select(SchemeNode))
    schemes = res_schemes.scalars().all()
    res_edges = await db.execute(select(Edge))
    edges = res_edges.scalars().all()

    await enrich_nodes(nodes, db)

    dot_lines = [
        "digraph G {",
        "  rankdir=LR;",
        '  node [style=filled, fontname="Arial"];',
    ]

    colors = {
        NodeType.DESCRIPTIF: "lightblue",
        NodeType.EMPIRIQUE: "lightgreen",
        NodeType.NORMATIF_POSITION: "lavender",
        NodeType.NORMATIF_CONCLUSION: "lightpink",
        NodeType.PONT_NORMATIF: "lightyellow",
        NodeType.DEFINITIONNEL: "lightgrey",
    }

    for n in nodes:
        color = colors.get(n.type, "white")
        label = n.text.replace('"', '\\"')
        coherence_info = f"\\n[{n.coherence}]" if n.coherence else ""
        correspondence_info = (
            f"\\nCredence: {n.correspondence}" if n.correspondence is not None else ""
        )
        dot_lines.append(
            f'  "{n.id}" [label="{label}{coherence_info}{correspondence_info}", fillcolor="{color}", shape=box];'
        )

    for s in schemes:
        shape = "diamond" if s.scheme == SchemeType.CONFLIT else "ellipse"
        color = "tomato" if s.scheme == SchemeType.CONFLIT else "orange"
        dot_lines.append(
            f'  "{s.id}" [label="{s.scheme}\\nw={s.weight}", fillcolor="{color}", shape={shape}];'
        )

    for e in edges:
        dot_lines.append(f'  "{e.source_id}" -> "{e.target_id}";')

    dot_lines.append("}")
    dot_content = "\n".join(dot_lines)
    return Response(
        content=dot_content,
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=graph.dot"},
    )


@app.post("/solve", response_model=SolveResponse)
async def solve_coherence(db: AsyncSession = Depends(get_db)):
    return await CoherenceSolverService.solve(db)


@app.get("/solve/alternatives", response_model=list[AlternativeSolutionOut])
async def get_solve_alternatives(
    n: int = Query(3, ge=1), db: AsyncSession = Depends(get_db)
):
    return await CoherenceSolverService.get_alternatives(db, n)


@app.get("/causal/graph", response_model=CausalGraphResponse)
async def get_causal_graph(db: AsyncSession = Depends(get_db)):
    nodes, edges = await CausalService.get_causal_graph(db)
    return {"nodes": nodes, "edges": edges}


@app.post("/causal/edges", response_model=CausalEdgeOut)
async def add_causal_edge(payload: CausalEdgeIn, db: AsyncSession = Depends(get_db)):
    try:
        edge = await CausalService.add_causal_edge(
            db, payload.cause_id, payload.effect_id, payload.strength
        )
        await db.commit()
        return edge
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.delete("/causal/edges/{id}")
async def delete_causal_edge(id: UUID, db: AsyncSession = Depends(get_db)):
    await CausalService.delete_causal_edge(db, id)
    await db.commit()
    return {"status": "ok"}


@app.delete("/nodes/{id}")
async def delete_node(id: UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Node).filter(Node.id == id))
    node = res.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    stmt = select(Edge).filter(or_(Edge.source_id == id, Edge.target_id == id))
    edges_res = await db.execute(stmt)
    edges = edges_res.scalars().all()

    associated_scheme_ids = set()
    for e in edges:
        if e.source_kind == SourceTargetKind.SCHEME:
            associated_scheme_ids.add(e.source_id)
        if e.target_kind == SourceTargetKind.SCHEME:
            associated_scheme_ids.add(e.target_id)

    for scheme_id in associated_scheme_ids:
        scheme_res = await db.execute(
            select(SchemeNode).filter(SchemeNode.id == scheme_id)
        )
        scheme_node = scheme_res.scalar_one_or_none()
        if scheme_node:
            se_stmt = select(Edge).filter(
                or_(Edge.source_id == scheme_id, Edge.target_id == scheme_id)
            )
            se_res = await db.execute(se_stmt)
            scheme_edges = se_res.scalars().all()
            for se in scheme_edges:
                before_dict = to_dict(se)
                await VersioningService.log_event(
                    db, "edge", se.id, "delete", before_dict, None
                )
                await db.delete(se)

            before_scheme_dict = to_dict(scheme_node)
            await VersioningService.log_event(
                db, "scheme_node", scheme_node.id, "delete", before_scheme_dict, None
            )
            await db.delete(scheme_node)

    for e in edges:
        try:
            before_dict = to_dict(e)
            await VersioningService.log_event(
                db, "edge", e.id, "delete", before_dict, None
            )
            await db.delete(e)
        except Exception:
            pass

    before_node_dict = to_dict(node)
    await VersioningService.log_event(
        db, "node", node.id, "delete", before_node_dict, None
    )
    await db.delete(node)

    await db.commit()
    return {"status": "ok"}


@app.delete("/edges/{scheme_id}")
async def delete_relation(scheme_id: UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(SchemeNode).filter(SchemeNode.id == scheme_id))
    scheme_node = res.scalar_one_or_none()
    if not scheme_node:
        raise HTTPException(status_code=404, detail="SchemeNode not found")

    stmt = select(Edge).filter(
        or_(Edge.source_id == scheme_id, Edge.target_id == scheme_id)
    )
    edges_res = await db.execute(stmt)
    edges = edges_res.scalars().all()
    for e in edges:
        before_dict = to_dict(e)
        await VersioningService.log_event(db, "edge", e.id, "delete", before_dict, None)
        await db.delete(e)

    before_scheme_dict = to_dict(scheme_node)
    await VersioningService.log_event(
        db, "scheme_node", scheme_node.id, "delete", before_scheme_dict, None
    )
    await db.delete(scheme_node)

    await db.commit()
    return {"status": "ok"}


@app.put("/scheme_nodes/{id}", response_model=SchemeNodeOut)
async def update_scheme_node(
    id: UUID, payload: SchemeNodeUpdateIn, db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(SchemeNode).filter(SchemeNode.id == id))
    scheme_node = res.scalar_one_or_none()
    if not scheme_node:
        raise HTTPException(status_code=404, detail="SchemeNode not found")

    before_dict = to_dict(scheme_node)
    scheme_node.strength = payload.strength
    scheme_node.weight = STRENGTH_TO_WEIGHT[payload.strength]

    await db.flush()
    await db.refresh(scheme_node)
    after_dict = to_dict(scheme_node)

    if before_dict != after_dict:
        await VersioningService.log_event(
            db, "scheme_node", scheme_node.id, "update", before_dict, after_dict
        )

    await db.commit()
    return scheme_node


@app.post("/whatif", response_model=WhatIfResponse)
async def post_whatif(payload: WhatIfRequest, db: AsyncSession = Depends(get_db)):
    credences, readable = await CausalService.run_whatif(db, payload.interventions)
    return {"credences": credences, "readable_effects": readable}


@app.post("/notes/generate")
async def generate_note(
    payload: NoteGenerateRequest, db: AsyncSession = Depends(get_db)
):
    res_nodes = await db.execute(select(Node))
    nodes = res_nodes.scalars().all()
    nodes_map = {n.id: n for n in nodes}

    await enrich_nodes(nodes, db)

    # Solve coherence and get alternatives
    solver_res = await CoherenceSolverService.solve(db)
    accepted_set = set(solver_res.get("accepted", []))
    rejected_set = set(solver_res.get("rejected", []))
    violated_constraints = solver_res.get("violated_constraints", [])

    alternatives = await CoherenceSolverService.get_alternatives(db, n=3)

    summary_parts = []

    if payload.node_id:
        target = nodes_map.get(payload.node_id)
        if not target:
            raise HTTPException(status_code=404, detail="Thesis node not found")

        summary_parts.append(
            f'Analyse de la Thèse : "{target.text}" (Type: {target.type}, Domaine: {target.domain})'
        )
        summary_parts.append(
            f"- Statut de Cohérence optimal : {'Accepté' if target.id in accepted_set else 'Rejeté / En tension'}"
        )
        if target.type == NodeType.EMPIRIQUE and target.correspondence is not None:
            summary_parts.append(
                f"- Crédence empirique (Réseau Bayésien) : {target.correspondence * 100:.1f}%"
            )

        # Details on alternatives
        summary_parts.append("\nComportement dans les configurations alternatives :")
        for alt in alternatives:
            alt_idx = alt["solution_index"]
            is_acc = target.id in alt["accepted"]
            summary_parts.append(
                f"  * Alternative {alt_idx} : {'Accepté' if is_acc else 'Rejeté'}"
            )

    elif payload.domain:
        summary_parts.append(f'Analyse du Domaine / Branche : "{payload.domain}"')
        domain_nodes = [n for n in nodes if n.domain.lower() == payload.domain.lower()]

        summary_parts.append("\nThèses acceptées (Majeures) :")
        for n in domain_nodes:
            if n.id in accepted_set:
                cred_str = (
                    f" | Crédence: {n.correspondence * 100:.1f}%"
                    if n.correspondence is not None
                    else ""
                )
                summary_parts.append(
                    f'  - "{n.text}" (Palier: {n.tier}, Poids: {n.weight}{cred_str})'
                )

        summary_parts.append("\nThèses rejetées ou en tension :")
        for n in domain_nodes:
            if n.id in rejected_set:
                cred_str = (
                    f" | Crédence: {n.correspondence * 100:.1f}%"
                    if n.correspondence is not None
                    else ""
                )
                summary_parts.append(
                    f'  - "{n.text}" (Palier: {n.tier}, Poids: {n.weight}{cred_str})'
                )

        # Tensions
        summary_parts.append("\nTensions et conflits recensés dans ce domaine :")
        domain_node_ids = {n.id for n in domain_nodes}
        conflict_count = 0
        for viol in violated_constraints:
            node_refs = (
                viol.node_refs
                if hasattr(viol, "node_refs")
                else viol.get("node_refs", [])
            )
            if any(vc.id in domain_node_ids for vc in node_refs):
                claim_texts = " VS ".join([f'"{vc.texte}"' for vc in node_refs])
                summary_parts.append(
                    f"  - Conflit : {claim_texts} (Poids/Coût: {viol.cost})"
                )
                conflict_count += 1
        if conflict_count == 0:
            summary_parts.append("  - Aucune tension directe active dans ce domaine.")

    else:
        summary_parts.append("Analyse Globale du Graphe de Croyances")
        summary_parts.append(f"- Nombre total de thèses : {len(nodes)}")
        summary_parts.append(f"- Thèses acceptées : {len(accepted_set)}")
        summary_parts.append(f"- Thèses rejetées : {len(rejected_set)}")
        summary_parts.append(f"- Tensions ouvertes : {len(violated_constraints)}")

    # Prompt LLM
    data_context = "\n".join(summary_parts)
    from src.services.llm import LLMClient

    llm = LLMClient()
    markdown_note = await llm.generate_synthesis_note(data_context)
    return {"note": markdown_note}


@app.get("/solve/sensitivity")
@app.post("/solve/sensitivity")
async def solve_sensitivity(db: AsyncSession = Depends(get_db)):
    # 1. Fetch all active nodes
    nodes_res = await db.execute(select(Node).filter(Node.weight > 0.0))
    nodes = nodes_res.scalars().all()
    nodes_map = {n.id: n for n in nodes}

    # 2. Get baseline optimal solution
    baseline = await CoherenceSolverService.solve(db)
    baseline_accepted = set(baseline.get("accepted", []))

    # TIERS and WEIGHTS
    TIERS = ["speculatif", "faible", "moyen", "fort", "certain"]
    WEIGHTS = [0.20, 0.40, 0.60, 0.80, 0.95]

    # helper val accessor
    def val_local(obj, attr):
        if isinstance(obj, dict):
            return obj.get(attr)
        return getattr(obj, attr, None)

    # 3. Compute sensitivity for each node
    claims_sensitivity = []
    for node in nodes:
        if node.tier is None or node.weight == 0.0:
            continue

        node_id = node.id
        was_accepted = node_id in baseline_accepted
        baseline_verdict = "accepted" if was_accepted else "rejected"

        # Find current tier index
        curr_tier_str = (
            node.tier.value if hasattr(node.tier, "value") else str(node.tier)
        )
        if curr_tier_str not in TIERS:
            continue
        idx_0 = TIERS.index(curr_tier_str)

        flip_delta = None
        flip_tier = None

        # Try shifting tier
        # We want to find the shift with minimum absolute value
        for delta in [1, -1, 2, -2, 3, -3, 4, -4]:
            new_idx = idx_0 + delta
            if 0 <= new_idx < len(TIERS):
                target_tier = TIERS[new_idx]
                target_weight = WEIGHTS[new_idx]

                # Solve with overrides
                overridden_res = await CoherenceSolverService.solve(
                    db,
                    weight_overrides={node_id: target_weight},
                    tier_overrides={node_id: target_tier},
                )
                new_accepted = set(overridden_res.get("accepted", []))
                new_verdict = "accepted" if node_id in new_accepted else "rejected"

                if new_verdict != baseline_verdict:
                    flip_delta = delta
                    flip_tier = target_tier
                    break

        robustesse = (
            "fragile"
            if (flip_delta is not None and abs(flip_delta) <= 1)
            else "robuste"
        )

        claims_sensitivity.append(
            {
                "claim_id": node_id,
                "verdict": baseline_verdict,
                "flip_delta": flip_delta,
                "flip_tier": flip_tier,
                "flip_at_tier": flip_tier,
                "robustesse": robustesse,
            }
        )

    # 4. Compute sensitivity for tensions
    tensions = await TensionService.get_tensions(db)
    tensions_sensitivity = []

    claims_sens_map = {c["claim_id"]: c for c in claims_sensitivity}

    for t in tensions:
        t_id = t.id
        t_type = t.type
        t_claims = t.claims

        robustesse = "robuste"
        explanation = ""

        if t_type == "conflit_direct" and len(t_claims) == 2:
            c_a, c_b = t_claims[0], t_claims[1]
            c_a_id = uuid.UUID(str(val_local(c_a, "id")))
            c_b_id = uuid.UUID(str(val_local(c_b, "id")))

            a_accepted = c_a_id in baseline_accepted
            b_accepted = c_b_id in baseline_accepted

            if a_accepted != b_accepted:
                accepted_node = nodes_map[c_a_id] if a_accepted else nodes_map[c_b_id]
                rejected_node = nodes_map[c_b_id] if a_accepted else nodes_map[c_a_id]

                rej_sens = claims_sens_map.get(rejected_node.id)
                acc_sens = claims_sens_map.get(accepted_node.id)

                is_fragile = False
                if rej_sens and rej_sens["robustesse"] == "fragile":
                    is_fragile = True
                if acc_sens and acc_sens["robustesse"] == "fragile":
                    is_fragile = True

                robustesse = "fragile" if is_fragile else "robuste"

                rejected_tier_fr = {
                    "certain": "Certain",
                    "fort": "Fort",
                    "moyen": "Moyen",
                    "faible": "Faible",
                    "speculatif": "Spéculatif",
                }.get(rejected_node.tier, str(rejected_node.tier))

                kind_fr = (
                    "crédence"
                    if rejected_node.weight_kind == "credence"
                    else "engagement"
                )

                explanation = f"{rejected_node.id} cède face à {accepted_node.id} tant que son {kind_fr} reste {rejected_tier_fr}."
            else:
                explanation = "Conflit inactif ou équilibré."
        elif t_type == "cycle_incoherent":
            is_fragile = False
            for c in t_claims:
                c_id = uuid.UUID(str(val_local(c, "id")))
                c_sens = claims_sens_map.get(c_id)
                if c_sens and c_sens["robustesse"] == "fragile":
                    is_fragile = True
                    break
            robustesse = "fragile" if is_fragile else "robuste"
            explanation = "Le cycle incoherent est fragile et peut être résolu en modifiant le palier d'un des claims."

        tensions_sensitivity.append(
            {"tension_id": t_id, "robustesse": robustesse, "explanation": explanation}
        )

    return {"claims": claims_sensitivity, "tensions": tensions_sensitivity}


@app.get("/validate/hume")
async def get_validate_hume(db: AsyncSession = Depends(get_db)):
    res_nodes = await db.execute(select(Node))
    nodes = res_nodes.scalars().all()

    res_schemes = await db.execute(select(SchemeNode))
    schemes = res_schemes.scalars().all()

    res_edges = await db.execute(select(Edge))
    edges = res_edges.scalars().all()

    violations = check_hume(nodes, schemes, edges)
    return {
        "violations": [v.model_dump(mode="json") for v in violations],
        "count": len(violations),
    }
