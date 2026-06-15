"""
Tests for A8 CritiqueAgent — deterministic pre-checks and output structure.
LLM path is mocked so tests run without API keys.
"""
import json
import pytest
import sys
import os
from unittest.mock import MagicMock, patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.agents.a8_critique import CritiqueAgent
from backend.models.schemas import (
    ApplicabilityFlag, ApplicabilityReport,
    Claim, ClaimType,
    ContradictionEdge, ContradictionGraph,
    CoISeverity, StudyDesign,
    LensRating, LensAnalysis, CritiqueOutput,
    ReliabilityScore, RelationType,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def make_claim(i: int, claim_type=ClaimType.QUALITATIVE, confidence=0.8) -> Claim:
    return Claim(
        claim_id=f"claim_{i}",
        source_id=f"src_{i}",
        text=f"Evidence claim number {i} about the research topic.",
        claim_type=claim_type,
        confidence=confidence,
    )

def make_reliability(source_id: str, score: float) -> ReliabilityScore:
    return ReliabilityScore(
        source_id=source_id,
        score=score,
        source_type="cohort",
        recency_score=0.8,
        base_type_score=score,
        coi_severity=CoISeverity.NONE,
        study_design=StudyDesign.COHORT,
    )

@pytest.fixture
def agent():
    # Patch Gemini at the service level so no real API call is made
    with patch("backend.agents.a8_critique.gemini_service") as mock_svc:
        mock_model = MagicMock()
        mock_svc.build_model_with_system.return_value = mock_model
        yield CritiqueAgent(), mock_model

@pytest.fixture
def good_claims():
    return [make_claim(i) for i in range(5)]

@pytest.fixture
def good_reliability():
    return [make_reliability(f"src_{i}", 0.75) for i in range(5)]

@pytest.fixture
def empty_graph():
    return ContradictionGraph(edges=[])

@pytest.fixture
def empty_applicability():
    return ApplicabilityReport(flags=[], overall_applicable=True)


# ─── Pre-check tests (deterministic, no LLM call) ─────────────────────────────

class TestPreChecks:
    def test_insufficient_when_zero_claims(self, agent, good_reliability, empty_graph, empty_applicability):
        critique_agent, _ = agent
        result = critique_agent.run("What are the effects?", [], good_reliability, empty_graph, empty_applicability)
        assert result.insufficient_evidence is True
        assert "thin" in result.insufficient_evidence_reason.lower()

    def test_insufficient_when_one_claim(self, agent, good_reliability, empty_graph, empty_applicability):
        critique_agent, _ = agent
        result = critique_agent.run("What?", [make_claim(1)], good_reliability, empty_graph, empty_applicability)
        assert result.insufficient_evidence is True

    def test_two_claims_passes_precheck(self, agent, empty_graph, empty_applicability):
        critique_agent, mock_model = agent
        # Make model return valid JSON
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "source_attack": {"rating": "minor", "findings": ["minor issue"], "penalty_recommendation": 0.05},
            "scope_attack": {"rating": "clear", "findings": [], "penalty_recommendation": 0.0},
            "completeness_attack": {"rating": "minor", "findings": ["some gap"], "penalty_recommendation": 0.05},
            "convergence_attack": {"rating": "clear", "findings": [], "penalty_recommendation": 0.0},
            "insufficient_evidence": False,
            "insufficient_evidence_reason": None,
            "adjusted_reliability": 0.72,
            "adjusted_consensus": 0.65,
            "key_uncertainties": ["minor concern"],
            "overall_severity": "minor",
        })
        mock_model.generate_content.return_value = mock_response
        reliability = [make_reliability(f"src_{i}", 0.75) for i in range(2)]
        result = critique_agent.run("Q?", [make_claim(1), make_claim(2)], reliability, empty_graph, empty_applicability)
        # Should NOT be insufficient (2 claims is enough)
        assert result.insufficient_evidence is False

    def test_insufficient_all_low_reliability(self, agent, good_claims, empty_graph, empty_applicability):
        critique_agent, _ = agent
        low_reliability = [make_reliability(f"src_{i}", 0.30) for i in range(5)]
        result = critique_agent.run("Q?", good_claims, low_reliability, empty_graph, empty_applicability)
        assert result.insufficient_evidence is True
        assert "0.4" in result.insufficient_evidence_reason

    def test_reliability_at_threshold_not_triggered(self, agent, empty_graph, empty_applicability):
        critique_agent, mock_model = agent
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "source_attack": {"rating": "moderate", "findings": ["issue"], "penalty_recommendation": 0.1},
            "scope_attack": {"rating": "clear", "findings": [], "penalty_recommendation": 0.0},
            "completeness_attack": {"rating": "clear", "findings": [], "penalty_recommendation": 0.0},
            "convergence_attack": {"rating": "clear", "findings": [], "penalty_recommendation": 0.0},
            "insufficient_evidence": False,
            "insufficient_evidence_reason": None,
            "adjusted_reliability": 0.4,
            "adjusted_consensus": 0.5,
            "key_uncertainties": [],
            "overall_severity": "moderate",
        })
        mock_model.generate_content.return_value = mock_response
        # Score of exactly 0.4 — NOT below 0.4, so pre-check should NOT trigger
        reliability = [make_reliability(f"src_{i}", 0.40) for i in range(3)]
        claims = [make_claim(i) for i in range(3)]
        result = critique_agent.run("Q?", claims, reliability, empty_graph, empty_applicability)
        assert result.insufficient_evidence is False

    def test_insufficient_all_inapplicable(self, agent, good_claims, good_reliability, empty_graph):
        critique_agent, _ = agent
        report = ApplicabilityReport(flags=[
            ApplicabilityFlag(source_id=f"src_{i}", population_match=False, timeframe_match=False, outcome_match=False) for i in range(5)
        ], overall_applicable=False)
        result = critique_agent.run("Q?", good_claims, good_reliability, empty_graph, report)
        assert result.insufficient_evidence is True
        assert "inapplicable" in result.insufficient_evidence_reason.lower()

    def test_insufficient_many_contradictions_few_claims(self, agent, good_reliability, empty_applicability):
        critique_agent, _ = agent
        claims = [make_claim(i) for i in range(3)]  # < 5 claims
        edges = [
            ContradictionEdge(claim_a_id=f"a{i}", claim_b_id=f"b{i}", relation=RelationType.CONTRADICTS, explanation="conflict")
            for i in range(3)  # 3 hard contradictions
        ]
        graph = ContradictionGraph(edges=edges)
        result = critique_agent.run("Q?", claims, good_reliability, graph, empty_applicability)
        assert result.insufficient_evidence is True


# ─── Output structure tests ───────────────────────────────────────────────────

class TestOutputStructure:
    def test_insufficient_output_has_four_lenses(self, agent, empty_graph, empty_applicability):
        critique_agent, _ = agent
        result = critique_agent.run("Q?", [], [], empty_graph, empty_applicability)
        assert hasattr(result, 'source_attack')
        assert hasattr(result, 'scope_attack')
        assert hasattr(result, 'completeness_attack')
        assert hasattr(result, 'convergence_attack')

    def test_insufficient_output_lens_rating_severe(self, agent, empty_graph, empty_applicability):
        critique_agent, _ = agent
        result = critique_agent.run("Q?", [], [], empty_graph, empty_applicability)
        assert result.source_attack.rating == LensRating.SEVERE
        assert result.overall_severity == LensRating.SEVERE

    def test_fallback_on_bad_json(self, agent, empty_graph, empty_applicability):
        critique_agent, mock_model = agent
        mock_response = MagicMock()
        mock_response.text = "this is not valid json at all!!!"
        mock_model.generate_content.return_value = mock_response
        claims = [make_claim(i) for i in range(5)]
        reliability = [make_reliability(f"src_{i}", 0.75) for i in range(5)]
        result = critique_agent.run("Q?", claims, reliability, empty_graph, empty_applicability)
        # Fallback — should be moderate, not crash
        assert result.overall_severity == LensRating.MODERATE
        assert result.insufficient_evidence is False

    def test_fallback_on_empty_response(self, agent, empty_graph, empty_applicability):
        critique_agent, mock_model = agent
        mock_response = MagicMock()
        mock_response.text = ""
        mock_model.generate_content.return_value = mock_response
        claims = [make_claim(i) for i in range(5)]
        reliability = [make_reliability(f"src_{i}", 0.75) for i in range(5)]
        result = critique_agent.run("Q?", claims, reliability, empty_graph, empty_applicability)
        assert isinstance(result, CritiqueOutput)
        assert result.insufficient_evidence is False

    def test_valid_llm_response_parsed_correctly(self, agent, empty_graph, empty_applicability):
        critique_agent, mock_model = agent
        llm_out = {
            "source_attack": {"rating": "severe", "findings": ["No peer review", "Small n=40"], "penalty_recommendation": 0.25},
            "scope_attack": {"rating": "moderate", "findings": ["Population mismatch"], "penalty_recommendation": 0.15},
            "completeness_attack": {"rating": "minor", "findings": ["Missing negative trials"], "penalty_recommendation": 0.05},
            "convergence_attack": {"rating": "clear", "findings": [], "penalty_recommendation": 0.0},
            "insufficient_evidence": False,
            "insufficient_evidence_reason": None,
            "adjusted_reliability": 0.55,
            "adjusted_consensus": 0.60,
            "key_uncertainties": ["Uncertain about long-term outcomes", "Sample size too small"],
            "overall_severity": "moderate",
        }
        mock_response = MagicMock()
        mock_response.text = json.dumps(llm_out)
        mock_model.generate_content.return_value = mock_response
        claims = [make_claim(i) for i in range(5)]
        reliability = [make_reliability(f"src_{i}", 0.75) for i in range(5)]
        result = critique_agent.run("Q?", claims, reliability, empty_graph, empty_applicability)
        assert result.source_attack.rating == LensRating.SEVERE
        assert len(result.source_attack.findings) == 2
        assert abs(result.adjusted_reliability - 0.55) < 0.001
        assert len(result.key_uncertainties) == 2
        assert result.overall_severity == LensRating.MODERATE

    def test_llm_can_set_insufficient_evidence(self, agent, empty_graph, empty_applicability):
        critique_agent, mock_model = agent
        llm_out = {
            "source_attack": {"rating": "severe", "findings": ["All sources biased"], "penalty_recommendation": 0.30},
            "scope_attack": {"rating": "severe", "findings": ["Wrong population"], "penalty_recommendation": 0.30},
            "completeness_attack": {"rating": "severe", "findings": ["50% evidence missing"], "penalty_recommendation": 0.30},
            "convergence_attack": {"rating": "severe", "findings": ["Citation cascade"], "penalty_recommendation": 0.30},
            "insufficient_evidence": True,
            "insufficient_evidence_reason": "LLM determined evidence is insufficient due to severe bias",
            "adjusted_reliability": 0.1,
            "adjusted_consensus": 0.1,
            "key_uncertainties": ["Everything is uncertain"],
            "overall_severity": "severe",
        }
        mock_response = MagicMock()
        mock_response.text = json.dumps(llm_out)
        mock_model.generate_content.return_value = mock_response
        claims = [make_claim(i) for i in range(5)]
        reliability = [make_reliability(f"src_{i}", 0.75) for i in range(5)]
        result = critique_agent.run("Q?", claims, reliability, empty_graph, empty_applicability)
        assert result.insufficient_evidence is True
        assert "LLM" in result.insufficient_evidence_reason


# ─── Adjusted score tests ─────────────────────────────────────────────────────

class TestAdjustedScores:
    def test_adjusted_scores_within_bounds(self, agent, good_claims, good_reliability, empty_graph, empty_applicability):
        critique_agent, mock_model = agent
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "source_attack": {"rating": "minor", "findings": [], "penalty_recommendation": 0.05},
            "scope_attack": {"rating": "clear", "findings": [], "penalty_recommendation": 0.0},
            "completeness_attack": {"rating": "clear", "findings": [], "penalty_recommendation": 0.0},
            "convergence_attack": {"rating": "clear", "findings": [], "penalty_recommendation": 0.0},
            "insufficient_evidence": False,
            "insufficient_evidence_reason": None,
            "adjusted_reliability": 0.70,
            "adjusted_consensus": 0.65,
            "key_uncertainties": [],
            "overall_severity": "minor",
        })
        mock_model.generate_content.return_value = mock_response
        result = critique_agent.run("Q?", good_claims, good_reliability, empty_graph, empty_applicability)
        assert 0.0 <= result.adjusted_reliability <= 1.0
        assert 0.0 <= result.adjusted_consensus <= 1.0

    def test_conservative_fallback_applies_haircut(self, agent, empty_graph, empty_applicability):
        critique_agent, mock_model = agent
        mock_response = MagicMock()
        mock_response.text = "not json"
        mock_model.generate_content.return_value = mock_response
        reliability = [make_reliability(f"src_{i}", 0.80) for i in range(5)]
        claims = [make_claim(i) for i in range(5)]
        result = critique_agent.run("Q?", claims, reliability, empty_graph, empty_applicability)
        # Fallback applies 20% haircut: 0.80 avg → 0.64
        assert result.adjusted_reliability < 0.80
