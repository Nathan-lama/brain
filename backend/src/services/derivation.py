import uuid
from typing import Any

from pydantic import BaseModel

# Constants matching the codebase's tiers and ranks
TIER_RANKS = {
    "speculatif": 1,
    "faible": 2,
    "moyen": 3,
    "fort": 4,
    "certain": 5
}

RANK_TO_TIER = {
    1: "speculatif",
    2: "faible",
    3: "moyen",
    4: "fort",
    5: "certain"
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

def get_manual_rank(node: Any) -> int:
    tier = getattr(node, "tier", None)
    if tier is None and isinstance(node, dict):
        tier = node.get("tier")
    if tier is not None and hasattr(tier, "value"):
        tier = tier.value
    if not tier:
        return 3
    tier_str = str(tier).lower().strip()
    return TIER_RANKS.get(tier_str, 3)

class DerivationItem(BaseModel):
    node_id: uuid.UUID
    label_court: str
    manual_tier: str | None
    manual_rank: int
    derived_rank: int | None
    derived_tier_label: str | None
    overcommitted: bool
    gap: int | None
    undercommitted: bool
    contributing_scheme_id: uuid.UUID | None
    cycle_detected: bool

class CycleItem(BaseModel):
    node_ids: list[uuid.UUID]

class DerivationResult(BaseModel):
    results: list[DerivationItem]
    cycles: list[CycleItem]
    count_overcommitted: int

def derive_commitments(nodes: list[Any], scheme_nodes: list[Any], edges: list[Any]) -> DerivationResult:
    """
    Derives logical commitments for nodes by propagating from sources to conclusions,
    applying the weakest-link (Theophrastus) rule with a strength-based malus.
    Gracefully handles and flags cycles using topological sorting.
    """
    import networkx as nx

    # 1. Map edges to premises and conclusions
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

        if role == "premise" or (hasattr(role, "value") and role.value == "premise") or str(role) == "premise":
            edges_premises.setdefault(target_uuid, []).append(source_uuid)
        elif role == "conclusion" or (hasattr(role, "value") and role.value == "conclusion") or str(role) == "conclusion":
            edges_conclusions[source_uuid] = target_uuid

    # 2. Filter inference scheme nodes
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

        if stype == "inference" or stype == "INFERENCE":
            strength = getattr(s, "strength", None)
            if strength is None and isinstance(s, dict):
                strength = s.get("strength")
            if strength is not None and hasattr(strength, "value"):
                strength = strength.value

            inference_schemes.append({
                "id": sid_uuid,
                "strength": strength,
            })

    # 3. Build directed dependency graph of claims
    G = nx.DiGraph()
    for n in nodes:
        nid = getattr(n, "id", None)
        if nid is None and isinstance(n, dict):
            nid = n.get("id")
        if nid:
            G.add_node(resolve_uuid(nid))

    node_to_inferences = {}
    for s in inference_schemes:
        sid = s["id"]
        strength = s["strength"]

        premises_ids = edges_premises.get(sid, [])
        conclusion_id = edges_conclusions.get(sid)

        if conclusion_id:
            node_to_inferences.setdefault(conclusion_id, []).append({
                "id": sid,
                "premises": premises_ids,
                "strength": strength,
            })
            for p in premises_ids:
                G.add_edge(p, conclusion_id)

    # 4. Cycle detection
    cycle_nodes = set()
    cycles_list = []
    sccs = list(nx.strongly_connected_components(G))
    for scc in sccs:
        if len(scc) > 1:
            cycles_list.append(list(scc))
            cycle_nodes.update(scc)

    # Check self-loops
    for u, v in G.edges():
        if u == v:
            if not any(u in c for c in cycles_list):
                cycles_list.append([u])
            cycle_nodes.add(u)

    # Propagate cycle affection downstream
    affected_by_cycle = cycle_nodes.copy()
    for x in cycle_nodes:
        affected_by_cycle.update(nx.descendants(G, x))

    # 5. Topological derivation on non-cycle DAG
    non_cycle_nodes = [n for n in G.nodes if n not in affected_by_cycle]
    G_sub = G.subgraph(non_cycle_nodes)
    order = list(nx.topological_sort(G_sub))

    # Read manual ranks and labels
    manual_ranks = {}
    manual_tiers = {}
    node_labels = {}

    for n in nodes:
        nid = getattr(n, "id", None)
        if nid is None and isinstance(n, dict):
            nid = n.get("id")
        if not nid:
            continue
        nid_uuid = resolve_uuid(nid)

        tier = getattr(n, "tier", None)
        if tier is None and isinstance(n, dict):
            tier = n.get("tier")
        if tier is not None and hasattr(tier, "value"):
            tier = tier.value

        manual_tiers[nid_uuid] = tier
        manual_ranks[nid_uuid] = get_manual_rank(n)

        meta = getattr(n, "metadata_", getattr(n, "metadata", None))
        if meta is None and isinstance(n, dict):
            meta = n.get("metadata") or n.get("metadata_")

        node_labels[nid_uuid] = get_label_court(nid_uuid, meta)

    derived_ranks = {}
    contributing_scheme_ids = {}

    for N in order:
        inferences = node_to_inferences.get(N, [])
        if not inferences:
            # Source node, not a conclusion
            derived_ranks[N] = None
            continue

        max_contrib = -1
        best_inference_id = None

        for inf in inferences:
            premises = inf["premises"]
            strength = inf["strength"]

            if not premises:
                contrib = 0
            else:
                p_ranks = []
                for premise_id in premises:
                    p_derived = derived_ranks.get(premise_id)
                    if p_derived is not None:
                        p_ranks.append(p_derived)
                    else:
                        p_ranks.append(manual_ranks.get(premise_id, 3))

                min_p_rank = min(p_ranks)
                malus = 0
                if strength in ("defaisable_fort", "DEFAISABLE_FORT"):
                    malus = 1
                elif strength in ("defaisable_faible", "DEFAISABLE_FAIBLE"):
                    malus = 2

                contrib = min_p_rank - malus

            contrib_clamped = max(1, min(5, contrib))
            if contrib_clamped > max_contrib:
                max_contrib = contrib_clamped
                best_inference_id = inf["id"]

        if max_contrib >= 1:
            derived_ranks[N] = max_contrib
            contributing_scheme_ids[N] = best_inference_id
        else:
            derived_ranks[N] = None

    # 6. Format final results
    results = []
    count_overcommitted = 0

    for N in manual_ranks.keys():
        manual_rank = manual_ranks[N]
        manual_tier = manual_tiers[N]
        label_court = node_labels.get(N, str(N)[:6])

        derived_rank = derived_ranks.get(N)
        if N in affected_by_cycle:
            derived_rank = None

        overcommitted = False
        undercommitted = False
        gap = None
        derived_tier_label = None
        contributing_scheme_id = None

        if derived_rank is not None:
            derived_tier_label = RANK_TO_TIER.get(derived_rank)
            contributing_scheme_id = contributing_scheme_ids.get(N)

            if manual_rank > derived_rank:
                overcommitted = True
                gap = manual_rank - derived_rank
                count_overcommitted += 1
            elif manual_rank < derived_rank:
                undercommitted = True

        cycle_detected = N in affected_by_cycle

        results.append(DerivationItem(
            node_id=N,
            label_court=label_court,
            manual_tier=manual_tier,
            manual_rank=manual_rank,
            derived_rank=derived_rank,
            derived_tier_label=derived_tier_label,
            overcommitted=overcommitted,
            gap=gap,
            undercommitted=undercommitted,
            contributing_scheme_id=contributing_scheme_id,
            cycle_detected=cycle_detected
        ))

    cycles = [CycleItem(node_ids=c) for c in cycles_list]

    return DerivationResult(
        results=results,
        cycles=cycles,
        count_overcommitted=count_overcommitted
    )
