import uuid

from src.services.derivation import derive_commitments


def test_derivation_hand_calculated():
    # 1. Define nodes sources: d1=certain(5), d2=certain(5), b1=moyen(3), b2=fort(4)
    d1_id = uuid.uuid5(uuid.NAMESPACE_DNS, "d1")
    d2_id = uuid.uuid5(uuid.NAMESPACE_DNS, "d2")
    b1_id = uuid.uuid5(uuid.NAMESPACE_DNS, "b1")
    b2_id = uuid.uuid5(uuid.NAMESPACE_DNS, "b2")
    c1_id = uuid.uuid5(uuid.NAMESPACE_DNS, "c1")
    c2_id = uuid.uuid5(uuid.NAMESPACE_DNS, "c2")
    
    nodes = [
        {"id": d1_id, "type": "descriptif", "tier": "certain", "weight": 0.95, "domain": "test"},
        {"id": d2_id, "type": "descriptif", "tier": "certain", "weight": 0.95, "domain": "test"},
        {"id": b1_id, "type": "pont_normatif", "tier": "moyen", "weight": 0.60, "domain": "test"},
        {"id": b2_id, "type": "pont_normatif", "tier": "fort", "weight": 0.80, "domain": "test"},
        {"id": c1_id, "type": "normatif_conclusion", "tier": "certain", "weight": 0.95, "domain": "test"}, # manual = certain (5)
        {"id": c2_id, "type": "normatif_conclusion", "tier": "faible", "weight": 0.40, "domain": "test"}, # manual = faible (2)
    ]
    
    # Inferences:
    # I1 : d1 ∧ b1 -> c1, strength = defaisable_fort (malus = 1)
    # I2 : d2 -> c1, strength = defaisable_faible (malus = 2)
    # I3 : c1 ∧ b2 -> c2, strength = deductif (malus = 0)
    i1_id = uuid.uuid5(uuid.NAMESPACE_DNS, "I1")
    i2_id = uuid.uuid5(uuid.NAMESPACE_DNS, "I2")
    i3_id = uuid.uuid5(uuid.NAMESPACE_DNS, "I3")
    
    scheme_nodes = [
        {"id": i1_id, "scheme": "inference", "strength": "defaisable_fort", "weight": 2.0},
        {"id": i2_id, "scheme": "inference", "strength": "defaisable_faible", "weight": 1.0},
        {"id": i3_id, "scheme": "inference", "strength": "deductif", "weight": 5.0},
    ]
    
    edges = [
        # I1: d1 & b1 -> c1
        {"source_id": d1_id, "target_id": i1_id, "role": "premise"},
        {"source_id": b1_id, "target_id": i1_id, "role": "premise"},
        {"source_id": i1_id, "target_id": c1_id, "role": "conclusion"},
        
        # I2: d2 -> c1
        {"source_id": d2_id, "target_id": i2_id, "role": "premise"},
        {"source_id": i2_id, "target_id": c1_id, "role": "conclusion"},
        
        # I3: c1 & b2 -> c2
        {"source_id": c1_id, "target_id": i3_id, "role": "premise"},
        {"source_id": b2_id, "target_id": i3_id, "role": "premise"},
        {"source_id": i3_id, "target_id": c2_id, "role": "conclusion"},
    ]
    
    res = derive_commitments(nodes, scheme_nodes, edges)
    
    # Assert c1 derived rank is 3 (moyen) and overcommitted with gap = 2, contributing_scheme_id = I2
    c1_res = next(x for x in res.results if x.node_id == c1_id)
    assert c1_res.derived_rank == 3
    assert c1_res.derived_tier_label == "moyen"
    assert c1_res.overcommitted is True
    assert c1_res.gap == 2
    assert c1_res.undercommitted is False
    assert c1_res.contributing_scheme_id == i2_id
    
    # Assert c2 derived rank is 3 (moyen) and undercommitted is True (since manual level is 2 (faible) < 3)
    c2_res = next(x for x in res.results if x.node_id == c2_id)
    assert c2_res.derived_rank == 3
    assert c2_res.derived_tier_label == "moyen"
    assert c2_res.overcommitted is False
    assert c2_res.gap is None
    assert c2_res.undercommitted is True
    assert c2_res.contributing_scheme_id == i3_id
    
def test_derivation_cycle():
    # Cycle de test séparé : I4 : x1 -> x2, I5 : x2 -> x1
    x1_id = uuid.uuid5(uuid.NAMESPACE_DNS, "x1")
    x2_id = uuid.uuid5(uuid.NAMESPACE_DNS, "x2")
    i4_id = uuid.uuid5(uuid.NAMESPACE_DNS, "I4")
    i5_id = uuid.uuid5(uuid.NAMESPACE_DNS, "I5")
    
    nodes = [
        {"id": x1_id, "type": "normatif_conclusion", "tier": "moyen", "weight": 0.60, "domain": "test"},
        {"id": x2_id, "type": "normatif_conclusion", "tier": "moyen", "weight": 0.60, "domain": "test"},
    ]
    
    scheme_nodes = [
        {"id": i4_id, "scheme": "inference", "strength": "deductif", "weight": 5.0},
        {"id": i5_id, "scheme": "inference", "strength": "deductif", "weight": 5.0},
    ]
    
    edges = [
        {"source_id": x1_id, "target_id": i4_id, "role": "premise"},
        {"source_id": i4_id, "target_id": x2_id, "role": "conclusion"},
        {"source_id": x2_id, "target_id": i5_id, "role": "premise"},
        {"source_id": i5_id, "target_id": x1_id, "role": "conclusion"},
    ]
    
    res = derive_commitments(nodes, scheme_nodes, edges)
    
    # Verify x1 and x2 have cycle detected
    assert len(res.cycles) > 0
    # The set of cycle node IDs must contain x1_id and x2_id
    cycle_nodes = set()
    for cycle in res.cycles:
        cycle_nodes.update(cycle.node_ids)
    assert x1_id in cycle_nodes
    assert x2_id in cycle_nodes
    
    # The individual results for x1 and x2 should have derived_rank = None
    x1_res = next(x for x in res.results if x.node_id == x1_id)
    assert x1_res.derived_rank is None
    assert x1_res.derived_tier_label is None
