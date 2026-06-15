"""
Tests for A9 ERSCalibrationAgent — fully deterministic, no mocks needed.
Covers: formula weights, penalty tracks, band thresholds, confidence band, edge cases.
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.agents.a9_ers_calibration import ERSCalibrationAgent
from backend.models.schemas import (
    ApplicabilityFlag, ApplicabilityReport,
    ContradictionEdge, ContradictionGraph,
    ERSBand, RelationType,
)


@pytest.fixture
def agent():
    return ERSCalibrationAgent()


@pytest.fixture
def empty_graph():
    return ContradictionGraph(edges=[])


@pytest.fixture
def empty_applicability():
    return ApplicabilityReport(flags=[], overall_applicable=True)


# ─── Formula weight tests ─────────────────────────────────────────────────────

class TestFormula:
    def test_weights_sum_to_one(self, agent):
        total = agent.W_SOURCE + agent.W_CONSENSUS + agent.W_RETRIEVAL
        assert abs(total - 1.0) < 1e-9

    def test_perfect_sources_no_penalty(self, agent, empty_graph, empty_applicability):
        result = agent.run(1.0, 1.0, 1.0, empty_graph, empty_applicability, [])
        assert result.score == 1.0
        assert result.band == ERSBand.HIGH

    def test_zero_inputs_give_zero(self, agent, empty_graph, empty_applicability):
        result = agent.run(0.0, 0.0, 0.0, empty_graph, empty_applicability, [])
        assert result.score == 0.0
        assert result.band == ERSBand.LOW

    def test_formula_arithmetic(self, agent, empty_graph, empty_applicability):
        # ERS = 0.45×0.8 + 0.35×0.6 + 0.20×0.5 = 0.360 + 0.210 + 0.100 = 0.670
        result = agent.run(0.8, 0.6, 0.5, empty_graph, empty_applicability, [])
        expected_base = 0.45 * 0.8 + 0.35 * 0.6 + 0.20 * 0.5
        assert abs(result.score - round(expected_base, 4)) < 0.001

    def test_formula_trace_populated(self, agent, empty_graph, empty_applicability):
        result = agent.run(0.7, 0.6, 0.8, empty_graph, empty_applicability, [])
        assert result.formula_trace is not None
        assert "0.45" in result.formula_trace
        assert "0.35" in result.formula_trace
        assert "0.20" in result.formula_trace


# ─── Band threshold tests ─────────────────────────────────────────────────────

class TestBandThresholds:
    def test_high_band_at_exactly_0_70(self, agent, empty_graph, empty_applicability):
        # Need inputs that produce exactly 0.70 base with no penalties
        # 0.45×a + 0.35×b + 0.20×c = 0.70 → use a=b=c=0.70
        result = agent.run(0.70, 0.70, 0.70, empty_graph, empty_applicability, [])
        assert result.band == ERSBand.HIGH

    def test_medium_band(self, agent, empty_graph, empty_applicability):
        # 0.45×0.5 + 0.35×0.4 + 0.20×0.6 = 0.225 + 0.140 + 0.120 = 0.485
        result = agent.run(0.5, 0.4, 0.6, empty_graph, empty_applicability, [])
        assert result.band == ERSBand.MEDIUM

    def test_low_band(self, agent, empty_graph, empty_applicability):
        result = agent.run(0.2, 0.3, 0.1, empty_graph, empty_applicability, [])
        assert result.band == ERSBand.LOW

    def test_score_at_boundary_medium_low(self, agent, empty_graph, empty_applicability):
        # Score of exactly 0.40 should be MEDIUM
        result = agent.run(0.40, 0.40, 0.40, empty_graph, empty_applicability, [])
        assert result.band == ERSBand.MEDIUM


# ─── Contradiction penalty tests ──────────────────────────────────────────────

class TestContradictionPenalty:
    def test_one_hard_contradiction_costs_0_10(self, agent, empty_applicability):
        graph = ContradictionGraph(edges=[
            ContradictionEdge(
                claim_a_id="a", claim_b_id="b",
                relation=RelationType.CONTRADICTS,
                explanation="direct conflict"
            )
        ])
        result = agent.run(1.0, 1.0, 1.0, graph, empty_applicability, [])
        assert abs(result.contradiction_penalty - 0.10) < 0.001

    def test_one_partial_contradiction_costs_0_05(self, agent, empty_applicability):
        graph = ContradictionGraph(edges=[
            ContradictionEdge(
                claim_a_id="a", claim_b_id="b",
                relation=RelationType.PARTIAL_CONTRADICTION,
                explanation="partial conflict"
            )
        ])
        result = agent.run(1.0, 1.0, 1.0, graph, empty_applicability, [])
        assert abs(result.contradiction_penalty - 0.05) < 0.001

    def test_supports_edge_no_penalty(self, agent, empty_applicability):
        graph = ContradictionGraph(edges=[
            ContradictionEdge(
                claim_a_id="a", claim_b_id="b",
                relation=RelationType.SUPPORTS,
                explanation="agreement"
            )
        ])
        result = agent.run(1.0, 1.0, 1.0, graph, empty_applicability, [])
        assert result.contradiction_penalty == 0.0

    def test_contradiction_penalty_capped_at_0_30(self, agent, empty_applicability):
        # 10 hard contradictions × 0.10 = 1.00, capped at 0.30
        edges = [
            ContradictionEdge(
                claim_a_id=f"a{i}", claim_b_id=f"b{i}",
                relation=RelationType.CONTRADICTS,
                explanation="conflict"
            )
            for i in range(10)
        ]
        graph = ContradictionGraph(edges=edges)
        result = agent.run(1.0, 1.0, 1.0, graph, empty_applicability, [])
        assert abs(result.contradiction_penalty - 0.30) < 0.001

    def test_mixed_contradictions(self, agent, empty_applicability):
        # 2 hard (0.20) + 2 partial (0.10) = 0.30, at cap
        edges = [
            ContradictionEdge(claim_a_id="a1", claim_b_id="b1", relation=RelationType.CONTRADICTS, explanation="conflict"),
            ContradictionEdge(claim_a_id="a2", claim_b_id="b2", relation=RelationType.CONTRADICTS, explanation="conflict"),
            ContradictionEdge(claim_a_id="a3", claim_b_id="b3", relation=RelationType.PARTIAL_CONTRADICTION, explanation="partial"),
            ContradictionEdge(claim_a_id="a4", claim_b_id="b4", relation=RelationType.PARTIAL_CONTRADICTION, explanation="partial"),
        ]
        graph = ContradictionGraph(edges=edges)
        result = agent.run(1.0, 1.0, 1.0, graph, empty_applicability, [])
        assert abs(result.contradiction_penalty - 0.30) < 0.001


# ─── Applicability penalty tests ─────────────────────────────────────────────

class TestApplicabilityPenalty:
    def test_all_applicable_no_penalty(self, agent, empty_graph):
        report = ApplicabilityReport(flags=[
            ApplicabilityFlag(source_id="s1", population_match=True, timeframe_match=True, outcome_match=True),
            ApplicabilityFlag(source_id="s2", population_match=True, timeframe_match=True, outcome_match=True),
        ])
        result = agent.run(1.0, 1.0, 1.0, empty_graph, report, [])
        assert result.applicability_penalty == 0.0

    def test_half_inapplicable(self, agent, empty_graph):
        report = ApplicabilityReport(flags=[
            ApplicabilityFlag(source_id="s1", population_match=True, timeframe_match=True, outcome_match=True),
            ApplicabilityFlag(source_id="s2", population_match=False, timeframe_match=True, outcome_match=True),  # population mismatch
        ])
        result = agent.run(1.0, 1.0, 1.0, empty_graph, report, [])
        # (1/2) × 0.20 = 0.10
        assert abs(result.applicability_penalty - 0.10) < 0.001

    def test_all_inapplicable_capped_at_0_20(self, agent, empty_graph):
        report = ApplicabilityReport(flags=[
            ApplicabilityFlag(source_id="s1", population_match=False, timeframe_match=False, outcome_match=False),
            ApplicabilityFlag(source_id="s2", population_match=False, timeframe_match=False, outcome_match=False),
            ApplicabilityFlag(source_id="s3", population_match=False, timeframe_match=False, outcome_match=False),
        ])
        result = agent.run(1.0, 1.0, 1.0, empty_graph, report, [])
        assert abs(result.applicability_penalty - 0.20) < 0.001

    def test_empty_flags_no_penalty(self, agent, empty_graph, empty_applicability):
        result = agent.run(1.0, 1.0, 1.0, empty_graph, empty_applicability, [])
        assert result.applicability_penalty == 0.0

    def test_partial_outcome_mismatch_penalised(self, agent, empty_graph):
        # outcome_match=False counts as inapplicable
        report = ApplicabilityReport(flags=[
            ApplicabilityFlag(source_id="s1", population_match=True, timeframe_match=True, outcome_match=False),  # outcome mismatch
        ])
        result = agent.run(1.0, 1.0, 1.0, empty_graph, report, [])
        # (1/1) × 0.20 = 0.20
        assert abs(result.applicability_penalty - 0.20) < 0.001


# ─── Uncertainty penalty tests ────────────────────────────────────────────────

class TestUncertaintyPenalty:
    def test_no_uncertainties_no_penalty(self, agent, empty_graph, empty_applicability):
        result = agent.run(1.0, 1.0, 1.0, empty_graph, empty_applicability, [])
        assert result.uncertainty_penalty == 0.0

    def test_one_uncertainty_costs_0_03(self, agent, empty_graph, empty_applicability):
        result = agent.run(1.0, 1.0, 1.0, empty_graph, empty_applicability, ["unknown population"])
        assert abs(result.uncertainty_penalty - 0.03) < 0.001

    def test_five_uncertainties(self, agent, empty_graph, empty_applicability):
        uncertainties = [f"uncertainty {i}" for i in range(5)]
        result = agent.run(1.0, 1.0, 1.0, empty_graph, empty_applicability, uncertainties)
        # 5 × 0.03 = 0.15, at cap
        assert abs(result.uncertainty_penalty - 0.15) < 0.001

    def test_uncertainty_penalty_capped_at_0_15(self, agent, empty_graph, empty_applicability):
        uncertainties = [f"uncertainty {i}" for i in range(20)]
        result = agent.run(1.0, 1.0, 1.0, empty_graph, empty_applicability, uncertainties)
        assert abs(result.uncertainty_penalty - 0.15) < 0.001


# ─── Confidence band tests ────────────────────────────────────────────────────

class TestConfidenceBand:
    def test_band_contains_score(self, agent, empty_graph, empty_applicability):
        result = agent.run(0.7, 0.6, 0.8, empty_graph, empty_applicability, [])
        assert result.confidence_lower <= result.score <= result.confidence_upper

    def test_base_margin_is_0_05(self, agent, empty_graph, empty_applicability):
        result = agent.run(0.7, 0.7, 0.7, empty_graph, empty_applicability, [])
        margin = (result.confidence_upper - result.confidence_lower) / 2
        assert abs(margin - 0.05) < 0.01  # base margin ≈ 0.05

    def test_contradictions_widen_band(self, agent, empty_applicability):
        graph_no = ContradictionGraph(edges=[])
        graph_yes = ContradictionGraph(edges=[
            ContradictionEdge(claim_a_id="a", claim_b_id="b", relation=RelationType.CONTRADICTS, explanation="x")
        ])
        r_no  = agent.run(0.7, 0.7, 0.7, graph_no,  empty_applicability, [])
        r_yes = agent.run(0.7, 0.7, 0.7, graph_yes, empty_applicability, [])
        margin_no  = r_no.confidence_upper  - r_no.confidence_lower
        margin_yes = r_yes.confidence_upper - r_yes.confidence_lower
        assert margin_yes > margin_no

    def test_band_clamped_to_valid_range(self, agent, empty_graph, empty_applicability):
        result = agent.run(0.0, 0.0, 0.0, empty_graph, empty_applicability, [])
        assert result.confidence_lower >= 0.0
        assert result.confidence_upper <= 1.0

    def test_high_reliability_narrows_band(self, agent, empty_graph, empty_applicability):
        r_no  = agent.run(0.7, 0.7, 0.7, empty_graph, empty_applicability, [], high_reliability_count=0)
        r_yes = agent.run(0.7, 0.7, 0.7, empty_graph, empty_applicability, [], high_reliability_count=5)
        margin_no  = r_no.confidence_upper  - r_no.confidence_lower
        margin_yes = r_yes.confidence_upper - r_yes.confidence_lower
        assert margin_yes <= margin_no


# ─── Audit trail tests ────────────────────────────────────────────────────────

class TestAuditTrail:
    def test_penalty_breakdown_present(self, agent, empty_graph, empty_applicability):
        result = agent.run(0.7, 0.6, 0.8, empty_graph, empty_applicability, ["x"])
        assert result.penalty_breakdown is not None
        assert result.penalty_breakdown.uncertainty_count == 1

    def test_penalty_breakdown_totals_correct(self, agent, empty_applicability):
        graph = ContradictionGraph(edges=[
            ContradictionEdge(claim_a_id="a", claim_b_id="b", relation=RelationType.CONTRADICTS, explanation="c")
        ])
        report = ApplicabilityReport(flags=[
            ApplicabilityFlag(source_id="s1", population_match=False, timeframe_match=True, outcome_match=True),  # pop mismatch
        ])
        result = agent.run(0.8, 0.7, 0.9, graph, report, ["u1"])
        bd = result.penalty_breakdown
        assert abs(bd.total_penalty - (bd.contradiction_penalty + bd.applicability_penalty + bd.uncertainty_penalty)) < 0.001

    def test_score_is_clamped(self, agent, empty_graph, empty_applicability):
        # Very low inputs with maximum penalties → should not go negative
        result = agent.run(0.0, 0.0, 0.0, empty_graph, empty_applicability, ["a"] * 10)
        assert result.score >= 0.0
        assert result.score <= 1.0
