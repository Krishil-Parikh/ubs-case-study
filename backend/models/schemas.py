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
