import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Node, NodeType, SchemeType
from src.schemas import ImportNode, ImportRequest
from src.services.embeddings import get_embeddings
from src.services.llm import LLMClient


def get_deterministic_uuid(text: str) -> uuid.UUID:
    # Normalize text by lowercasing and removing duplicate whitespaces
    normalized = " ".join(text.strip().lower().split())
    return uuid.uuid5(uuid.NAMESPACE_DNS, normalized)


async def extract_pipeline(
    text: str, db: AsyncSession, k_neighbors: int = 5
) -> ImportRequest:
    llm_client = LLMClient()

    # Step 1: Extract claims from raw text
    claims_response = await llm_client.extract_claims(text)
    new_claims = claims_response.claims

    if not new_claims:
        return ImportRequest(nodes=[], scheme_nodes=[])

    # Step 2: Fetch embeddings for new claims in batch
    new_texts = [c.text for c in new_claims]
    new_embeddings = await get_embeddings(new_texts)

    # Store candidate existing claims from DB
    existing_claims_map = {}

    # Step 3: Query pgvector for each claim to find nearest neighbors
    for i, claim in enumerate(new_claims):
        emb = new_embeddings[i]
        distance_expr = Node.embedding.cosine_distance(emb)
        stmt = (
            select(Node)
            .filter(Node.embedding.isnot(None))
            .order_by(distance_expr)
            .limit(k_neighbors)
        )
        res = await db.execute(stmt)
        neighbors = res.scalars().all()

        for n in neighbors:
            existing_claims_map[n.id] = {
                "id": str(n.id),
                "type": n.type,
                "domain": n.domain,
                "text": n.text,
                "tier": n.tier,
            }

    # Step 4: Classify relations between new claims and between new & existing claims
    new_claims_list = [
        {
            "temp_id": c.temp_id,
            "type": c.type,
            "domain": c.domain,
            "text": c.text,
            "tier": c.tier,
        }
        for c in new_claims
    ]

    existing_claims_list = list(existing_claims_map.values())

    relations_response = await llm_client.extract_relations(
        new_claims=new_claims_list, existing_claims=existing_claims_list
    )

    # Step 5: Materialize graph elements
    import_nodes = {}
    import_scheme_nodes = []

    # Map from temp_id -> real deterministic UUID
    temp_id_map = {}
    for c in new_claims:
        node_uuid = get_deterministic_uuid(c.text)
        temp_id_map[c.temp_id] = node_uuid

        import_nodes[node_uuid] = ImportNode(
            id=str(node_uuid),
            type=c.type,
            domain=c.domain,
            text=c.text,
            tier=c.tier,
            metadata={"temp_id": c.temp_id},
        )

    def resolve_uuid(id_str: str) -> uuid.UUID:
        if id_str in temp_id_map:
            return temp_id_map[id_str]
        try:
            return uuid.UUID(id_str)
        except ValueError:
            return get_deterministic_uuid(id_str)

    # Process relationships and create scheme nodes
    for rel in relations_response.relations:
        if rel.relation_type == "independant":
            continue

        source_uuid = resolve_uuid(rel.source_id)
        target_uuid = resolve_uuid(rel.target_id)

        # If there is a bridge, create a pont_normatif claim
        if rel.bridge_text:
            bridge_uuid = get_deterministic_uuid(rel.bridge_text)
            bridge_domain = rel.bridge_domain or "ethique"

            # Add bridge claim to nodes list
            if bridge_uuid not in import_nodes:
                import_nodes[bridge_uuid] = ImportNode(
                    id=str(bridge_uuid),
                    type=NodeType.PONT_NORMATIF,
                    domain=bridge_domain,
                    text=rel.bridge_text,
                    tier="fort",  # standard default tier for normative bridges
                    metadata={"source": "LLM Extraction Bridge"},
                )

            if rel.relation_type == "contredit":
                # Connect source -> bridge via conflict
                import_scheme_nodes.append(
                    {
                        "id": str(uuid.uuid4()),
                        "scheme": SchemeType.CONFLIT,
                        "from": str(source_uuid),
                        "to": str(bridge_uuid),
                    }
                )
                # Connect bridge -> target via inference (bridge supports/justifies target, but is attacked)
                import_scheme_nodes.append(
                    {
                        "id": str(uuid.uuid4()),
                        "scheme": SchemeType.INFERENCE,
                        "premises": [str(bridge_uuid)],
                        "conclusion": str(target_uuid),
                    }
                )
            else:
                # Connect source & bridge -> target via inference
                import_scheme_nodes.append(
                    {
                        "id": str(uuid.uuid4()),
                        "scheme": SchemeType.INFERENCE,
                        "premises": [str(source_uuid), str(bridge_uuid)],
                        "conclusion": str(target_uuid),
                    }
                )
        else:
            # Standard relations without bridge
            if rel.relation_type in ("soutient", "implique", "presuppose"):
                scheme_id = str(uuid.uuid4())
                # If presuppose, source presupposes target, which means target is premise and source is conclusion
                if rel.relation_type == "presuppose":
                    import_scheme_nodes.append(
                        {
                            "id": scheme_id,
                            "scheme": SchemeType.INFERENCE,
                            "premises": [str(target_uuid)],
                            "conclusion": str(source_uuid),
                            # Put custom relation type in metadata so frontend overrides it correctly
                            "metadata": {"relation": "presuppose"},
                        }
                    )
                else:
                    import_scheme_nodes.append(
                        {
                            "id": scheme_id,
                            "scheme": SchemeType.INFERENCE,
                            "premises": [str(source_uuid)],
                            "conclusion": str(target_uuid),
                        }
                    )
            elif rel.relation_type == "contredit":
                import_scheme_nodes.append(
                    {
                        "id": str(uuid.uuid4()),
                        "scheme": SchemeType.CONFLIT,
                        "from": str(source_uuid),
                        "to": str(target_uuid),
                    }
                )

    return ImportRequest(
        nodes=list(import_nodes.values()), scheme_nodes=import_scheme_nodes
    )
