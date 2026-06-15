from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class ClaimType(str, Enum):
    QUANTITATIVE = "quantitative"
    QUALITATIVE = "qualitative"
    HEDGED = "hedged"
    METHODOLOGICAL_CAVEAT = "methodological_caveat"


class RelationType(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    PARTIAL_CONTRADICTION = "PARTIAL_CONTRADICTION"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class ERSBand(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class UncertaintyCategory(str, Enum):
    DATA_GAP = "data_gap"
    METHODOLOGY = "methodology"
    SCOPE = "scope"
    TEMPORAL = "temporal"
    POPULATION = "population"


class Claim(BaseModel):
    claim_id: str
    source_id: str
    text: str
    claim_type: ClaimType
    confidence: float = Field(ge=0.0, le=1.0)


class ReliabilityScore(BaseModel):
    source_id: str
    score: float = Field(ge=0.0, le=1.0)
    source_type: str
    recency_score: float
    llm_escalated: bool = False
    escalation_reason: Optional[str] = None


class ContradictionEdge(BaseModel):
    claim_a_id: str
    claim_b_id: str
    relation: RelationType
    explanation: str


class ContradictionGraph(BaseModel):
    edges: list[ContradictionEdge] = []


class ApplicabilityFlag(BaseModel):
    source_id: str
    population_match: bool
    timeframe_match: bool
    outcome_match: bool
    flag_reason: Optional[str] = None


class ApplicabilityReport(BaseModel):
    flags: list[ApplicabilityFlag] = []
    overall_applicable: bool = True


class ERSResult(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    band: ERSBand
    confidence_lower: float
    confidence_upper: float
    source_score: float
    consensus_score: float
    retrieval_relevance: float
    contradiction_penalty: float
    applicability_penalty: float
    uncertainty_penalty: float


# ── Phase 6 Output Models ──────────────────────────────────────────────


class SupportMapEntry(BaseModel):
    """Maps a claim to the answer section it supports."""
    claim_id: str
    source_id: str
    supporting_text: str
    relevance_score: float = Field(ge=0.0, le=1.0, default=1.0)
    answer_section_index: int = 0


class ContradictionManifestEntry(BaseModel):
    """Human-readable contradiction summary for the final output."""
    claim_a_text: str
    claim_b_text: str
    relation: RelationType
    explanation: str
    severity: str = "moderate"  # low, moderate, high


class UncertaintyEntry(BaseModel):
    """Structured uncertainty with category and impact assessment."""
    description: str
    category: UncertaintyCategory = UncertaintyCategory.DATA_GAP
    impact_level: str = "moderate"  # low, moderate, high


class AnswerSection(BaseModel):
    """A discrete section of the synthesized answer with inline citations."""
    heading: str
    content: str
    cited_claim_ids: list[str] = []


class ResponseMetadata(BaseModel):
    """Metadata about the response generation process."""
    source_count: int = 0
    claim_count: int = 0
    contradiction_count: int = 0
    applicability_flags_count: int = 0
    insufficient_evidence: bool = False
    ers_band: str = "Medium"
    generation_model: str = "gemini-1.5-pro"


# ── Request / Response ──────────────────────────────────────────────────


class PipelineRequest(BaseModel):
    query: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    max_sources: int = 10


class PipelineResponse(BaseModel):
    answer: str
    ers: ERSResult
    claims: list[Claim]
    contradiction_graph: ContradictionGraph
    applicability_report: ApplicabilityReport
    uncertainties: list[str]
    insufficient_evidence: bool = False
    session_id: Optional[str] = None
    # Phase 6 structured output fields
    answer_sections: list[AnswerSection] = []
    support_map: list[SupportMapEntry] = []
    contradictions_manifest: list[ContradictionManifestEntry] = []
    structured_uncertainties: list[UncertaintyEntry] = []
    metadata: Optional[ResponseMetadata] = None
