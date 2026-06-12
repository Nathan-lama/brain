from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models import (
    EdgeRole,
    NodeType,
    SchemeStrength,
    SchemeType,
    SourceTargetKind,
    TierKind,
    WeightKind,
)


# Node Schemas
class NodeIn(BaseModel):
    type: NodeType
    domain: str
    text: str
    tier: TierKind | None = None
    confidence: float | None = None
    embedding: list[float] | None = None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata")

    model_config = ConfigDict(
        populate_by_name=True,
    )


class NodeUpdateIn(BaseModel):
    tier: str | None = None
    text: str | None = None
    domain: str | None = None


class NodeOut(BaseModel):
    id: UUID
    type: NodeType
    domain: str
    text: str
    tier: TierKind | None = None
    weight_kind: WeightKind | None = None
    weight: float
    confidence: float | None = None
    embedding: list[float] | None = None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata")
    created_at: datetime
    updated_at: datetime
    coherence: str | None = None
    correspondence: float | None = None
    label_court: str | None = None

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    @model_validator(mode="before")
    @classmethod
    def resolve_metadata(cls, data: Any) -> Any:
        if hasattr(data, "__table__"):
            from src.services.solver import get_label_court
            return {
                "id": data.id,
                "type": data.type,
                "domain": data.domain,
                "text": data.text,
                "tier": data.tier,
                "weight_kind": data.weight_kind,
                "weight": data.weight,
                "confidence": data.weight,
                "embedding": data.embedding,
                "metadata": data.metadata_,
                "created_at": data.created_at,
                "updated_at": data.updated_at,
                "coherence": getattr(data, "coherence", None),
                "correspondence": getattr(data, "correspondence", None),
                "label_court": get_label_court(data.id, data.metadata_),
            }
        elif isinstance(data, dict):
            if "label_court" not in data:
                from src.services.solver import get_label_court
                node_id = data.get("id")
                if isinstance(node_id, str):
                    try:
                        node_id = UUID(node_id)
                    except ValueError:
                        pass
                if isinstance(node_id, UUID):
                    data["label_court"] = get_label_court(node_id, data.get("metadata"))
        return data


# SchemeNode Schemas
class SchemeNodeIn(BaseModel):
    scheme: SchemeType
    weight: float = Field(..., ge=0.0, le=5.0)
    metadata_: dict[str, Any] | None = Field(None, alias="metadata")

    model_config = ConfigDict(
        populate_by_name=True,
    )

    @model_validator(mode="after")
    def validate_inference_weight(self) -> "SchemeNodeIn":
        if self.scheme == SchemeType.INFERENCE and self.weight not in (1.0, 2.0, 5.0):
            raise ValueError("Inference weight must be 1.0, 2.0, or 5.0")
        return self


class SchemeNodeUpdateIn(BaseModel):
    strength: SchemeStrength


class SchemeNodeOut(BaseModel):
    id: UUID
    scheme: SchemeType
    weight: float
    strength: SchemeStrength | None = None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    @model_validator(mode="before")
    @classmethod
    def resolve_metadata(cls, data: Any) -> Any:
        if hasattr(data, "__table__"):
            return {
                "id": data.id,
                "scheme": data.scheme,
                "weight": data.weight,
                "strength": getattr(data, "strength", None),
                "metadata": data.metadata_,
                "created_at": data.created_at,
                "updated_at": data.updated_at,
            }
        return data


# Edge Schemas
class EdgeIn(BaseModel):
    source_id: UUID
    target_id: UUID
    source_kind: SourceTargetKind
    target_kind: SourceTargetKind
    role: EdgeRole


class EdgeOut(BaseModel):
    id: UUID
    source_id: UUID
    target_id: UUID
    source_kind: SourceTargetKind
    target_kind: SourceTargetKind
    role: EdgeRole

    model_config = ConfigDict(
        from_attributes=True,
    )


# Graph Export Schema
class GraphExport(BaseModel):
    nodes: list[NodeOut]
    scheme_nodes: list[SchemeNodeOut]
    edges: list[EdgeOut]


# Import Schemas for JSON import endpoint
class ImportNode(BaseModel):
    id: str
    type: NodeType
    domain: str
    text: str
    tier: TierKind | None = None
    confidence: float | None = None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata")

    model_config = ConfigDict(
        populate_by_name=True,
    )


class ImportSchemeInference(BaseModel):
    id: str
    scheme: Literal[SchemeType.INFERENCE]
    premises: list[str]
    conclusion: str
    strength: SchemeStrength | None = None
    weight: float | None = None



class ImportSchemeConflit(BaseModel):
    id: str
    scheme: Literal[SchemeType.CONFLIT]
    from_node: str = Field(..., alias="from")
    to_node: str = Field(..., alias="to")

    model_config = ConfigDict(
        populate_by_name=True,
    )


ImportSchemeNode = Annotated[
    ImportSchemeInference | ImportSchemeConflit,
    Field(discriminator="scheme"),
]


class ImportRequest(BaseModel):
    nodes: list[ImportNode]
    scheme_nodes: list[ImportSchemeNode]


# Flat Edge Schema (I-node to I-node direct connection)
class FlatEdge(BaseModel):
    id: UUID
    source_id: UUID = Field(..., alias="source")
    target_id: UUID = Field(..., alias="target")
    relation: str
    scheme_id: UUID
    strength: SchemeStrength | None = None
    weight: float | None = None
    scheme_label: str | None = None

    model_config = ConfigDict(
        populate_by_name=True,
    )


# Graph Response Schema (directly consumable by UI)
class GraphResponse(BaseModel):
    nodes: list[NodeOut]
    edges: list[FlatEdge]


# Node Neighbor Schema
class NodeNeighbor(BaseModel):
    node: NodeOut
    direction: Literal["incoming", "outgoing"]
    relation: str
    scheme_id: UUID


# Node Details Schema
class NodeDetailResponse(BaseModel):
    node: NodeOut
    neighbors: list[NodeNeighbor]


# Related Node Suggestion Schema
class RelatedNodeResponse(BaseModel):
    node: NodeOut
    similarity: float


# Paginated Nodes Schema
class NodesPaginatedResponse(BaseModel):
    total: int
    page: int
    limit: int
    pages: int
    items: list[NodeOut]


class ExtractRequest(BaseModel):
    text: str


class TensionOut(BaseModel):
    id: UUID
    type: Literal["conflit_direct", "cycle_incoherent", "liaison_rompue"]
    claims: list[NodeOut]
    ponts: list[NodeOut]
    score: float
    poids: float | None = None
    scheme_id: UUID | None = None
    paradoxe_assume: bool = False


class TensionResolveRequest(BaseModel):
    action: Literal["reviser_node", "accepter_paradoxe"]
    node_id: UUID | None = None
    scheme_id: UUID | None = None


class EventOut(BaseModel):
    id: UUID
    entity_type: str
    entity_id: UUID
    op: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class TensionDiffOut(BaseModel):
    tensions_resolues: list[TensionOut]
    tensions_nouvelles: list[TensionOut]
    claims_affectes: list[NodeOut]


class SnapshotOut(BaseModel):
    id: UUID
    label: str
    created_at: datetime
    payload: dict[str, Any]

    model_config = ConfigDict(
        from_attributes=True,
    )


class SnapshotDiffOut(BaseModel):
    claims_ajoutes: list[NodeOut]
    claims_supprimes: list[NodeOut]
    claims_modifies: list[NodeOut]
    edges_ajoutes: list[EdgeOut]
    edges_supprimes: list[EdgeOut]
    tensions_resolues: list[TensionOut]
    tensions_nouvelles: list[TensionOut]


class NodeRef(BaseModel):
    id: UUID
    label_court: str
    texte: str


class ViolatedConstraint(BaseModel):
    constraint_id: UUID
    scheme_id: UUID
    kind: Literal["inference", "conflit"]
    node_refs: list[NodeRef]
    cost: float
    detail: str


class ArbitratedTension(BaseModel):
    id: UUID
    scheme_id: UUID
    kept_node: NodeRef
    discarded_node: NodeRef
    stake_rank: int
    stake_label: str


class SolverConfiguration(BaseModel):
    accepted: list[UUID]
    rejected: list[UUID]
    incoherence_score: float
    violated_constraints: list[ViolatedConstraint]
    arbitrated_tensions: list[ArbitratedTension]
    score: float | None = Field(
        None,
        description="Valeur d'objectif interne du solveur divisée par SCALE, incluant les ticks de tie-break déductifs, non directement comparable entre versions.",
    )
    solution_index: int | None = None
    differs_accepted: list[UUID] | None = None
    differs_rejected: list[UUID] | None = None


SolveResponse = SolverConfiguration
AlternativeSolutionOut = SolverConfiguration


class CausalEdgeIn(BaseModel):
    cause_id: UUID
    effect_id: UUID
    strength: float = Field(..., ge=0.0, le=1.0)


class CausalEdgeOut(BaseModel):
    id: UUID
    cause_id: UUID
    effect_id: UUID
    strength: float

    model_config = ConfigDict(
        from_attributes=True,
    )


class CausalGraphResponse(BaseModel):
    nodes: list[NodeOut]
    edges: list[CausalEdgeOut]


class WhatIfRequest(BaseModel):
    interventions: dict[UUID, int]


class WhatIfResponse(BaseModel):
    credences: dict[UUID, float]
    readable_effects: list[str]


# Domain Schemas
class DomainIn(BaseModel):
    name: str
    parent_id: UUID | None = None


class DomainOut(BaseModel):
    id: UUID
    name: str
    parent_id: UUID | None = None

    model_config = ConfigDict(
        from_attributes=True,
    )


class DomainHierarchyNode(BaseModel):
    id: UUID
    name: str
    parent_id: UUID | None = None
    children: list["DomainHierarchyNode"] = []
    node_count: int = 0


class NoteGenerateRequest(BaseModel):
    domain: str | None = None
    node_id: UUID | None = None


class WhatIfOp(BaseModel):
    op: Literal["set_strength", "set_tier", "remove_node", "add_node", "add_inference", "add_conflict"]
    target: str | None = None
    strength: str | None = None
    tier: str | None = None
    label_court: str | None = None
    text: str | None = None
    type: str | None = None
    label: str | None = None
    premises: list[str] | None = None
    conclusion: str | None = None
    a: str | None = None
    b: str | None = None


class StructuralWhatIfRequest(BaseModel):
    ops: list[WhatIfOp]


class StructuralWhatIfBaseline(BaseModel):
    score: float
    incoherence_score: float


class StructuralWhatIfFlips(BaseModel):
    accepted_to_rejected: list[str]
    rejected_to_accepted: list[str]


class StructuralWhatIfConstraintChange(BaseModel):
    scheme: str
    before: Literal["violated", "satisfied"]
    after: Literal["violated", "satisfied"]


class StructuralWhatIfDiff(BaseModel):
    score_delta: float
    incoherence_delta: float
    flips: StructuralWhatIfFlips
    constraints_changed: list[StructuralWhatIfConstraintChange]
    cascaded_schemes: list[str]
    ops_applied: list[WhatIfOp]


class StructuralWhatIfResponse(BaseModel):
    verdict: SolveResponse
    baseline: StructuralWhatIfBaseline
    diff: StructuralWhatIfDiff
