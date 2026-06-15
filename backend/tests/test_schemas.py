"""
Tests for Pydantic schema validation — checks all models instantiate correctly
and enforce constraints.
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pydantic import ValidationError
from backend.models.schemas import (
    Claim, ClaimType, CoISeverity, StudyDesign, SourceType,
    SpanReference, PIOTEntities,
    ReliabilityScore,
    ContradictionEdge, ContradictionGraph, RelationType,
    ApplicabilityFlag, ApplicabilityReport,
    LensRating, LensAnalysis, CritiqueOutput,
    ERSBand, ERSPenaltyBreakdown, ERSResult,
    PipelineRequest, PipelineResponse,
)


class TestClaimSchema:
    def test_valid_claim(self):
        c = Claim(claim_id="1", source_id="s1", text="aspirin reduces risk", claim_type=ClaimType.QUANTITATIVE, confidence=0.9)
        assert c.claim_type == ClaimType.QUANTITATIVE

    def test_confidence_must_be_0_to_1(self):
        with pytest.raises(ValidationError):
            Claim(claim_id="1", source_id="s1", text="x", claim_type=ClaimType.QUALITATIVE, confidence=1.5)

    def test_optional_span_and_piot(self):
        c = Claim(claim_id="1", source_id="s1", text="x", claim_type=ClaimType.HEDGED, confidence=0.5,
                  span=SpanReference(paragraph_index=0, sentence_text="x", char_start=0, char_end=1),
                  piot=PIOTEntities(population="adults", intervention="aspirin", outcome="MI", timeframe="5y"))
        assert c.span.paragraph_index == 0
        assert c.piot.population == "adults"


class TestReliabilityScoreSchema:
    def test_valid_score(self):
        r = ReliabilityScore(source_id="s1", score=0.75, source_type="rct",
                             recency_score=0.9, coi_severity=CoISeverity.NONE,
                             study_design=StudyDesign.RCT)
        assert r.study_design == StudyDesign.RCT

    def test_score_above_1_rejected(self):
        with pytest.raises(ValidationError):
            ReliabilityScore(source_id="s1", score=1.5, source_type="rct", recency_score=0.9)


class TestLensAnalysis:
    def test_penalty_above_0_30_rejected(self):
        with pytest.raises(ValidationError):
            LensAnalysis(rating=LensRating.SEVERE, findings=["x"], penalty_recommendation=0.31)

    def test_valid_lens(self):
        l = LensAnalysis(rating=LensRating.MODERATE, findings=["issue A", "issue B"], penalty_recommendation=0.15)
        assert len(l.findings) == 2

    def test_clear_lens_zero_penalty(self):
        l = LensAnalysis(rating=LensRating.CLEAR, findings=[], penalty_recommendation=0.0)
        assert l.penalty_recommendation == 0.0


class TestERSResult:
    def test_valid_ers_result(self):
        bd = ERSPenaltyBreakdown(
            contradiction_edges_hard=1, contradiction_edges_partial=0,
            contradiction_penalty=0.10,
            inapplicable_source_count=1, total_source_count=3,
            applicability_penalty=0.07,
            uncertainty_count=2, uncertainty_penalty=0.06,
            total_penalty=0.23
        )
        r = ERSResult(
            score=0.55, band=ERSBand.MEDIUM,
            confidence_lower=0.48, confidence_upper=0.62,
            source_score=0.7, consensus_score=0.6, retrieval_relevance=0.8,
            contradiction_penalty=0.10, applicability_penalty=0.07, uncertainty_penalty=0.06,
            penalty_breakdown=bd,
            formula_trace="ERS = 0.45×0.7 + 0.35×0.6 + 0.20×0.8 = ..."
        )
        assert r.band == ERSBand.MEDIUM

    def test_score_above_1_rejected(self):
        with pytest.raises(ValidationError):
            ERSResult(score=1.1, band=ERSBand.HIGH, confidence_lower=0.9, confidence_upper=1.0,
                      source_score=1.0, consensus_score=1.0, retrieval_relevance=1.0,
                      contradiction_penalty=0.0, applicability_penalty=0.0, uncertainty_penalty=0.0)


class TestEnums:
    def test_source_type_values(self):
        assert SourceType.RESEARCH_PAPER.value == "research_paper"
        assert SourceType.NEWS_ARTICLE.value   == "news_article"
        assert SourceType.BLOG.value           == "blog"
        assert SourceType.UNKNOWN.value        == "unknown"

    def test_study_design_values(self):
        assert StudyDesign.META_ANALYSIS.value     == "meta_analysis"
        assert StudyDesign.SYSTEMATIC_REVIEW.value == "systematic_review"
        assert StudyDesign.RCT.value               == "rct"
        assert StudyDesign.NOT_APPLICABLE.value    == "not_applicable"

    def test_coi_severity_values(self):
        assert CoISeverity.NONE.value == "none"
        assert CoISeverity.LOW.value  == "low"
        assert CoISeverity.HIGH.value == "high"

    def test_lens_rating_values(self):
        assert LensRating.SEVERE.value   == "severe"
        assert LensRating.MODERATE.value == "moderate"
        assert LensRating.MINOR.value    == "minor"
        assert LensRating.CLEAR.value    == "clear"

    def test_ers_band_values(self):
        assert ERSBand.HIGH.value   == "High"
        assert ERSBand.MEDIUM.value == "Medium"
        assert ERSBand.LOW.value    == "Low"


class TestPipelineRequest:
    def test_valid_request(self):
        r = PipelineRequest(query="Does aspirin work?")
        assert r.max_sources == 10

    def test_empty_query_allowed(self):
        r = PipelineRequest(query="")
        assert r.query == ""
