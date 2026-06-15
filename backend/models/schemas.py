from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ─── Shared Enums ─────────────────────────────────────────────────────────────

class ClaimType(str, Enum):
    QUANTITATIVE          = "quantitative"
    QUALITATIVE           = "qualitative"
    HEDGED                = "hedged"
    METHODOLOGICAL_CAVEAT = "methodological_caveat"


class RelationType(str, Enum):
    SUPPORTS              = "SUPPORTS"
    CONTRADICTS           = "CONTRADICTS"
    PARTIAL_CONTRADICTION = "PARTIAL_CONTRADICTION"
    NOT_COMPARABLE        = "NOT_COMPARABLE"


class ERSBand(str, Enum):
    HIGH   = "High"
    MEDIUM = "Medium"
    LOW    = "Low"


class UncertaintyCategory(str, Enum):
    DATA_GAP    = "data_gap"
    METHODOLOGY = "methodology"
    SCOPE       = "scope"
    TEMPORAL    = "temporal"
    POPULATION  = "population"


# ─── A3/A4 domain enums ───────────────────────────────────────────────────────

class SourceType(str, Enum):
    RESEARCH_PAPER = "research_paper"
    NEWS_ARTICLE   = "news_article"
    BLOG           = "blog"
    UNKNOWN        = "unknown"


class StudyDesign(str, Enum):
    META_ANALYSIS     = "meta_analysis"
    SYSTEMATIC_REVIEW = "systematic_review"
    RCT               = "rct"
    COHORT            = "cohort"
    CASE_CONTROL      = "case_control"
    CASE_REPORT       = "case_report"
    NARRATIVE_REVIEW  = "narrative_review"
    OPINION           = "opinion"
    NOT_APPLICABLE    = "not_applicable"


class CoISeverity(str, Enum):
    NONE = "none"
    LOW  = "low"
    HIGH = "high"


# ─── A3 sub-models ────────────────────────────────────────────────────────────

class SpanReference(BaseModel):
    """Span-level attribution: locates a claim within the source document."""
    paragraph_index: Optional[int]  = None
    sentence_text:   Optional[str]  = None
    char_start:      Optional[int]  = None
    char_end:        Optional[int]  = None


class PIOTEntities(BaseModel):
    """PIOT (Population · Intervention · Outcome · Timeframe) extracted per claim."""
    population:   Optional[str] = None
    intervention: Optional[str] = None
    outcome:      Optional[str] = None
    timeframe:    Optional[str] = None


# ─── Phase 3 — Extraction ─────────────────────────────────────────────────────

class Claim(BaseModel):
    claim_id:   str
    source_id:  str
    text:       str
    claim_type: ClaimType
    confidence: float = Field(ge=0.0, le=1.0)

    # Optional enrichment from A3
    span:      Optional[SpanReference] = None
    piot:      Optional[PIOTEntities]  = None
    embedding: Optional[list[float]]   = None


# ─── Phase 4 — Parallel scoring ───────────────────────────────────────────────

class ReliabilityScore(BaseModel):
    source_id:     str
    score:         float = Field(ge=0.0, le=1.0)
    source_type:   str
    recency_score: float

    # A4 extended fields
    base_type_score:   float        = 0.5
    coi_severity:      CoISeverity  = CoISeverity.NONE
    coi_reason:        Optional[str] = None
    study_design:      StudyDesign  = StudyDesign.NOT_APPLICABLE

    # LLM escalation info
    llm_escalated:     bool          = False
    escalation_reason: Optional[str] = None


class ContradictionEdge(BaseModel):
    claim_a_id:  str
    claim_b_id:  str
    relation:    RelationType
    explanation: str


class ContradictionGraph(BaseModel):
    edges: list[ContradictionEdge] = []


class ApplicabilityFlag(BaseModel):
    source_id:        str
    population_match: bool
    timeframe_match:  bool
    outcome_match:    bool
    flag_reason:      Optional[str] = None


class ApplicabilityReport(BaseModel):
    flags:              list[ApplicabilityFlag] = []
    overall_applicable: bool                    = True


# ─── Phase 5 — A8 Critique ────────────────────────────────────────────────────

class LensRating(str, Enum):
    SEVERE   = "severe"
    MODERATE = "moderate"
    MINOR    = "minor"
    CLEAR    = "clear"


class LensAnalysis(BaseModel):
    rating:                 LensRating
    findings:               list[str] = Field(description="Specific, concrete issues found")
    penalty_recommendation: float     = Field(ge=0.0, le=0.30)


class CritiqueOutput(BaseModel):
    source_attack:       LensAnalysis
    scope_attack:        LensAnalysis
    completeness_attack: LensAnalysis
    convergence_attack:  LensAnalysis

    insufficient_evidence:        bool
    insufficient_evidence_reason: Optional[str] = None

    adjusted_reliability: float = Field(ge=0.0, le=1.0)
    adjusted_consensus:   float = Field(ge=0.0, le=1.0)

    key_uncertainties: list[str] = []
    overall_severity:  LensRating


# ─── Phase 5 — A9 ERS Calibration ────────────────────────────────────────────

class ERSPenaltyBreakdown(BaseModel):
    contradiction_edges_hard:    int
    contradiction_edges_partial: int
    contradiction_penalty:       float
    inapplicable_source_count:   int
    total_source_count:          int
    applicability_penalty:       float
    uncertainty_count:           int
    uncertainty_penalty:         float
    total_penalty:               float


class ERSResult(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    band:  ERSBand

    confidence_lower: float
    confidence_upper: float

    source_score:        float
    consensus_score:     float
    retrieval_relevance: float

    contradiction_penalty: float
    applicability_penalty: float
    uncertainty_penalty:   float

    penalty_breakdown: Optional[ERSPenaltyBreakdown] = None
    formula_trace:     Optional[str]                 = None


# ─── Phase 6 — Response Output Models ────────────────────────────────────────

class SupportMapEntry(BaseModel):
    claim_id:             str
    source_id:            str
    supporting_text:      str
    relevance_score:      float = Field(ge=0.0, le=1.0, default=1.0)
    answer_section_index: int   = 0


class ContradictionManifestEntry(BaseModel):
    claim_a_text: str
    claim_b_text: str
    relation:     RelationType
    explanation:  str
    severity:     str = "moderate"


class UncertaintyEntry(BaseModel):
    description:  str
    category:     UncertaintyCategory = UncertaintyCategory.DATA_GAP
    impact_level: str                 = "moderate"


class AnswerSection(BaseModel):
    heading:         str
    content:         str
    cited_claim_ids: list[str] = []


class ResponseMetadata(BaseModel):
    source_count:              int  = 0
    claim_count:               int  = 0
    contradiction_count:       int  = 0
    applicability_flags_count: int  = 0
    insufficient_evidence:     bool = False
    ers_band:                  str  = "Medium"
    generation_model:          str  = "gemini-1.5-pro"


# ─── Pipeline request / response ─────────────────────────────────────────────

class PipelineRequest(BaseModel):
    query:       str
    user_id:     Optional[str] = None
    session_id:  Optional[str] = None
    max_sources: int           = 10


class PipelineResponse(BaseModel):
    answer:               str
    ers:                  ERSResult
    critique:             Optional[CritiqueOutput] = None
    claims:               list[Claim]
    contradiction_graph:  ContradictionGraph
    applicability_report: ApplicabilityReport
    uncertainties:        list[str]
    insufficient_evidence: bool         = False
    session_id:           Optional[str] = None

    # Phase 6 structured output
    answer_sections:          list[AnswerSection]              = []
    support_map:              list[SupportMapEntry]            = []
    contradictions_manifest:  list[ContradictionManifestEntry] = []
    structured_uncertainties: list[UncertaintyEntry]           = []
    metadata:                 Optional[ResponseMetadata]       = None
