import uuid

import pytest

from src.models import (
    EdgeRole,
    NodeType,
    SchemeStrength,
    SchemeType,
    SourceTargetKind,
)
from src.services.solver import EdgeRow, GraphData, NodeRow, SchemeRow
from src.services.whatif import WhatIfValidationError, apply_ops


def test_t1_cascade():
    # 3 nodes, 1 inference, 1 conflict sharing a node (n2)
    n1 = uuid.uuid4()
    n2 = uuid.uuid4()
    n3 = uuid.uuid4()
    s_inf = uuid.uuid4()
    s_conf = uuid.uuid4()

    nodes = [
        NodeRow(id=n1, type=NodeType.DESCRIPTIF, tier="fort", weight=0.8, text="n1", metadata_={"imported_id": "n1"}),
        NodeRow(id=n2, type=NodeType.DESCRIPTIF, tier="fort", weight=0.8, text="n2", metadata_={"imported_id": "n2"}),
        NodeRow(id=n3, type=NodeType.DESCRIPTIF, tier="fort", weight=0.8, text="n3", metadata_={"imported_id": "n3"}),
    ]
    schemes = [
        SchemeRow(id=s_inf, scheme=SchemeType.INFERENCE, strength=SchemeStrength.DEFAISABLE_FORT, weight=2.0, metadata_={"imported_id": "ra1"}),
        SchemeRow(id=s_conf, scheme=SchemeType.CONFLIT, strength=None, weight=1.0, metadata_={"imported_id": "ca1"}),
    ]
    edges = [
        # Inference: n1 -> ra1 -> n2
        EdgeRow(source_id=n1, source_kind=SourceTargetKind.NODE, target_id=s_inf, target_kind=SourceTargetKind.SCHEME, role=EdgeRole.PREMISE),
        EdgeRow(source_id=s_inf, source_kind=SourceTargetKind.SCHEME, target_id=n2, target_kind=SourceTargetKind.NODE, role=EdgeRole.CONCLUSION),
        # Conflict: n2 <-> ca1 <-> n3
        EdgeRow(source_id=n2, source_kind=SourceTargetKind.NODE, target_id=s_conf, target_kind=SourceTargetKind.SCHEME, role=EdgeRole.CONFLICTING),
        EdgeRow(source_id=s_conf, source_kind=SourceTargetKind.SCHEME, target_id=n3, target_kind=SourceTargetKind.NODE, role=EdgeRole.CONFLICTED),
    ]

    g = GraphData(nodes=nodes, schemes=schemes, edges=edges, credences={})
    ops = [
        {"op": "remove_node", "target": "n2"}
    ]
    g2, report = apply_ops(g, ops)

    assert "ra1" in report.cascaded_schemes
    assert "ca1" in report.cascaded_schemes
    assert len(g2.nodes) == 2
    assert len(g2.schemes) == 0
    assert len(g2.edges) == 0


def test_t2_ordre():
    # Setup initial graph
    g = GraphData(nodes=[], schemes=[], edges=[], credences={})

    # Order: add_node then add_inference -> OK
    ops_ok = [
        {"op": "add_node", "label_court": "n1", "type": "descriptif", "tier": "fort"},
        {"op": "add_node", "label_court": "n2", "type": "descriptif", "tier": "fort"},
        {"op": "add_inference", "label": "ra1", "premises": ["n1"], "conclusion": "n2", "strength": "defaisable_fort"}
    ]
    g2, report = apply_ops(g, ops_ok)
    assert len(g2.nodes) == 2
    assert len(g2.schemes) == 1

    # Inverse order: add_inference then add_node -> 422 on target resolution
    ops_err = [
        {"op": "add_inference", "label": "ra1", "premises": ["n1"], "conclusion": "n2", "strength": "defaisable_fort"},
        {"op": "add_node", "label_court": "n1", "type": "descriptif", "tier": "fort"},
        {"op": "add_node", "label_court": "n2", "type": "descriptif", "tier": "fort"}
    ]
    with pytest.raises(WhatIfValidationError) as exc:
        apply_ops(g, ops_err)
    assert exc.value.index == 0
    assert "Cible inconnue" in str(exc.value)


def test_t3_set_strength_conflict():
    # Conflict scheme in graph
    s_conf = uuid.uuid4()
    schemes = [
        SchemeRow(id=s_conf, scheme=SchemeType.CONFLIT, strength=None, weight=1.0, metadata_={"imported_id": "ca1"}),
    ]
    g = GraphData(nodes=[], schemes=schemes, edges=[], credences={})
    ops = [
        {"op": "set_strength", "target": "ca1", "strength": "defaisable_fort"}
    ]
    with pytest.raises(WhatIfValidationError) as exc:
        apply_ops(g, ops)
    assert exc.value.index == 0
    assert "force du conflit" in str(exc.value)


def test_t4_cible_inconnue():
    g = GraphData(nodes=[], schemes=[], edges=[], credences={})
    ops = [
        {"op": "set_tier", "target": "n1", "tier": "fort"}
    ]
    with pytest.raises(WhatIfValidationError) as exc:
        apply_ops(g, ops)
    assert exc.value.index == 0
    assert "n1" in str(exc.value)


def test_t5_hume():
    n1_id = uuid.uuid4()
    n2_id = uuid.uuid4()
    # n1 (descriptive), n2 (normative conclusion)
    nodes = [
        NodeRow(id=n1_id, type=NodeType.DESCRIPTIF, tier="fort", weight=0.8, text="Premise", metadata_={"imported_id": "n1"}),
        NodeRow(id=n2_id, type=NodeType.NORMATIF_CONCLUSION, tier="fort", weight=0.8, text="Normative Conclusion", metadata_={"imported_id": "n2"}),
    ]
    g = GraphData(nodes=nodes, schemes=[], edges=[], credences={})

    # Add inference with descriptive premise and normative conclusion -> Hume violation!
    ops = [
        {"op": "add_inference", "label": "ra1", "premises": ["n1"], "conclusion": "n2", "strength": "defaisable_fort"}
    ]
    with pytest.raises(WhatIfValidationError) as exc:
        apply_ops(g, ops)
    assert exc.value.index == 0
    assert "Hume" in str(exc.value)


def test_t6_immutability():
    # Mini graph
    n1_id = uuid.uuid4()
    nodes = [
        NodeRow(id=n1_id, type=NodeType.DESCRIPTIF, tier="fort", weight=0.8, text="n1", metadata_={"imported_id": "n1"}),
    ]
    g = GraphData(nodes=nodes, schemes=[], edges=[], credences={})

    ops = [
        {"op": "add_node", "label_court": "n2", "type": "descriptif", "tier": "fort"},
    ]
    g2, _ = apply_ops(g, ops)

    # g must remain identical
    assert len(g.nodes) == 1
    assert len(g2.nodes) == 2


def test_t7_idempotence_and_duplication():
    g = GraphData(nodes=[], schemes=[], edges=[], credences={})

    # Two distinct calls with same label_court -> same id
    ops_1 = [{"op": "add_node", "label_court": "n1", "type": "descriptif", "tier": "fort"}]
    g1, _ = apply_ops(g, ops_1)
    g2, _ = apply_ops(g, ops_1)

    assert g1.nodes[0].id == g2.nodes[0].id

    # Duplication in same call -> 422
    ops_dup = [
        {"op": "add_node", "label_court": "n1", "type": "descriptif", "tier": "fort"},
        {"op": "add_node", "label_court": "n1", "type": "descriptif", "tier": "fort"},
    ]
    with pytest.raises(WhatIfValidationError) as exc:
        apply_ops(g, ops_dup)
    assert exc.value.index == 1
    assert "déjà existant" in str(exc.value)
