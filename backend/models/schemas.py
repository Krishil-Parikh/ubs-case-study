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


# ─── Phase 3 — Extraction ─────────────────────────────────────────────────────

class Claim(BaseModel):
    claim_id:   str
    source_id:  str
    text:       str
    claim_type: ClaimType
    confidence: float = Field(ge=0.0, le=1.0)


# ─── Phase 4 — Parallel scoring ───────────────────────────────────────────────

class ReliabilityScore(BaseModel):
    source_id:         str
    score:             float = Field(ge=0.0, le=1.0)
    source_type:       str
    recency_score:     float
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
    """Severity of issues found by a single critique lens."""
    SEVERE   = "severe"    # critical issues that heavily degrade trust
    MODERATE = "moderate"  # notable issues with meaningful impact
    MINOR    = "minor"     # minor issues that should be flagged
    CLEAR    = "clear"     # no meaningful issues found


class LensAnalysis(BaseModel):
    """Output of one adversarial lens."""
    rating:                 LensRating
    findings:               list[str] = Field(description="Specific, concrete issues found")
    penalty_recommendation: float     = Field(ge=0.0, le=0.30, description="Recommended score deduction")


class CritiqueOutput(BaseModel):
    """Full structured output from A8 Critique/Skeptic."""

    # Four fixed lenses
    source_attack:       LensAnalysis
    scope_attack:        LensAnalysis
    completeness_attack: LensAnalysis
    convergence_attack:  LensAnalysis

    # Hard override
    insufficient_evidence:        bool
    insufficient_evidence_reason: Optional[str] = None

    # Adjusted component scores after adversarial pressure
    adjusted_reliability: float = Field(ge=0.0, le=1.0)
    adjusted_consensus:   float = Field(ge=0.0, le=1.0)

    # Uncertainties to carry forward to A9
    key_uncertainties: list[str] = []

    # Summary
    overall_severity: LensRating


# ─── Phase 5 — A9 ERS Calibration ────────────────────────────────────────────

class ERSPenaltyBreakdown(BaseModel):
    """Transparent audit trail for every penalty applied in A9."""
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
    """Final ERS score with full audit trail."""

    # Core score
    score: float = Field(ge=0.0, le=1.0)
    band:  ERSBand

    # Dynamic confidence band
    confidence_lower: float
    confidence_upper: float

    # Formula inputs (post-critique)
    source_score:        float
    consensus_score:     float
    retrieval_relevance: float

    # Penalty summary
    contradiction_penalty: float
    applicability_penalty: float
    uncertainty_penalty:   float

    # Detailed breakdown and formula trace
    penalty_breakdown: Optional[ERSPenaltyBreakdown] = None
    formula_trace:     Optional[str]                 = None


# ─── Phase 6 — Response Output Models ────────────────────────────────────────

class SupportMapEntry(BaseModel):
    """Maps a claim to the answer section it supports."""
    claim_id:             str
    source_id:            str
    supporting_text:      str
    relevance_score:      float = Field(ge=0.0, le=1.0, default=1.0)
    answer_section_index: int   = 0


class ContradictionManifestEntry(BaseModel):
    """Human-readable contradiction summary for the final output."""
    claim_a_text: str
    claim_b_text: str
    relation:     RelationType
    explanation:  str
    severity:     str = "moderate"  # low | moderate | high


class UncertaintyEntry(BaseModel):
    """Structured uncertainty with category and impact assessment."""
    description:  str
    category:     UncertaintyCategory = UncertaintyCategory.DATA_GAP
    impact_level: str                 = "moderate"  # low | moderate | high


class AnswerSection(BaseModel):
    """A discrete section of the synthesized answer with inline citations."""
    heading:         str
    content:         str
    cited_claim_ids: list[str] = []


class ResponseMetadata(BaseModel):
    """Metadata about the response generation process."""
    source_count:               int  = 0
    claim_count:                int  = 0
    contradiction_count:        int  = 0
    applicability_flags_count:  int  = 0
    insufficient_evidence:      bool = False
    ers_band:                   str  = "Medium"
    generation_model:           str  = "gemini-1.5-pro"


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

    # Phase 6 structured output fields
    answer_sections:           list[AnswerSection]               = []
    support_map:               list[SupportMapEntry]             = []
    contradictions_manifest:   list[ContradictionManifestEntry]  = []
    structured_uncertainties:  list[UncertaintyEntry]            = []
    metadata:                  Optional[ResponseMetadata]        = None
