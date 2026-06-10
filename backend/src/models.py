import enum
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from src.database import Base


# Enums
class NodeType(enum.StrEnum):
    DESCRIPTIF = "descriptif"
    EMPIRIQUE = "empirique"
    NORMATIF_POSITION = "normatif_position"
    NORMATIF_CONCLUSION = "normatif_conclusion"
    PONT_NORMATIF = "pont_normatif"
    DEFINITIONNEL = "definitionnel"


class SchemeType(enum.StrEnum):
    INFERENCE = "inference"
    CONFLIT = "conflit"
    PREFERENCE = "preference"


class SchemeStrength(enum.StrEnum):
    DEDUCTIF = "deductif"
    DEFAISABLE_FORT = "defaisable_fort"
    DEFAISABLE_FAIBLE = "defaisable_faible"


STRENGTH_TO_WEIGHT = {
    SchemeStrength.DEDUCTIF: 5.0,
    SchemeStrength.DEFAISABLE_FORT: 2.0,
    SchemeStrength.DEFAISABLE_FAIBLE: 1.0,
}


class SourceTargetKind(enum.StrEnum):
    NODE = "node"
    SCHEME = "scheme"


class EdgeRole(enum.StrEnum):
    PREMISE = "premise"
    CONCLUSION = "conclusion"
    CONFLICTING = "conflicting"
    CONFLICTED = "conflicted"
    PREFERRED = "preferred"
    DISPREFERRED = "dispreferred"


class TierKind(enum.StrEnum):
    CERTAIN = "certain"
    FORT = "fort"
    MOYEN = "moyen"
    FAIBLE = "faible"
    SPECULATIF = "speculatif"


class WeightKind(enum.StrEnum):
    CREDENCE = "credence"
    ENGAGEMENT = "engagement"


# Tables
class Node(Base):
    __tablename__ = "nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(Enum(NodeType, native_enum=True), nullable=False)
    domain = Column(String, nullable=False)
    text = Column(String, nullable=False)
    tier = Column(
        Enum(
            TierKind,
            name="tierkind",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=True,
    )
    weight_kind = Column(
        Enum(
            WeightKind,
            name="weightkind",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=True,
    )
    weight = Column(Float, nullable=False, default=0.6, server_default="0.6")
    embedding = Column(Vector(768), nullable=True)  # nomic-embed-text dimension is 768
    metadata_ = Column("metadata", JSONB, nullable=True)
    created_at = Column(
        DateTime, nullable=False, default=func.now(), server_default=func.now()
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
        server_onupdate=func.now(),
    )

    __table_args__ = (
        Index(
            "nodes_embedding_hnsw_idx",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class SchemeNode(Base):
    __tablename__ = "scheme_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scheme = Column(Enum(SchemeType, native_enum=True), nullable=False)
    # weight is used as the inference strength weight (1.0, 2.0, 5.0) for inferences.
    # Note: for conflict nodes, weight is inerte (ignored) in the solver, which uses a hard constant of 100 * SCALE.
    weight = Column(Float, nullable=False)
    strength = Column(
        Enum(
            SchemeStrength,
            name="schemestrength",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=True,
    )
    metadata_ = Column("metadata", JSONB, nullable=True)
    created_at = Column(
        DateTime, nullable=False, default=func.now(), server_default=func.now()
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
        server_onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint("weight >= 0.0 AND weight <= 5.0", name="check_weight_range"),
        CheckConstraint(
            "scheme != 'inference' OR weight IN (1.0, 2.0, 5.0)",
            name="check_inference_weight_values",
        ),
    )


class Edge(Base):
    __tablename__ = "edges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), nullable=False)
    target_id = Column(UUID(as_uuid=True), nullable=False)
    source_kind = Column(Enum(SourceTargetKind, native_enum=True), nullable=False)
    target_kind = Column(Enum(SourceTargetKind, native_enum=True), nullable=False)
    role = Column(Enum(EdgeRole, native_enum=True), nullable=False)

    __table_args__ = (
        CheckConstraint("source_kind != target_kind", name="check_edge_kind_bipartite"),
    )


class BeliefSnapshot(Base):
    __tablename__ = "belief_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label = Column(String, nullable=False)
    created_at = Column(
        DateTime, nullable=False, default=func.now(), server_default=func.now()
    )
    payload = Column(JSONB, nullable=False)


class Event(Base):
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String, nullable=False)  # 'node', 'scheme_node', 'edge'
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    op = Column(String, nullable=False)  # 'create', 'update', 'delete'
    before = Column(JSONB, nullable=True)
    after = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime, nullable=False, default=func.now(), server_default=func.now()
    )


class CausalEdge(Base):
    __tablename__ = "causal_edges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cause_id = Column(
        UUID(as_uuid=True), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False
    )
    effect_id = Column(
        UUID(as_uuid=True), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False
    )
    strength = Column(Float, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "strength >= 0.0 AND strength <= 1.0", name="check_causal_strength_range"
        ),
    )


class Domain(Base):
    __tablename__ = "domains"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("domains.id", ondelete="SET NULL"),
        nullable=True,
    )
