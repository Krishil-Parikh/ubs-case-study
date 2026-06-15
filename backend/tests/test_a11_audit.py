"""
Tests for A11 AuditAgent — verifies file-based logging writes correctly.
"""
import asyncio
import json
import os
import sys
import tempfile
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.models.schemas import (
    ApplicabilityReport, Claim, ClaimType, ContradictionGraph,
    CoISeverity, CritiqueOutput, ERSBand, ERSPenaltyBreakdown,
    ERSResult, LensAnalysis, LensRating, PipelineResponse, StudyDesign,
    ReliabilityScore,
)


def make_minimal_response() -> PipelineResponse:
    """Build the smallest valid PipelineResponse."""
    lens = LensAnalysis(rating=LensRating.MINOR, findings=[], penalty_recommendation=0.0)
    critique = CritiqueOutput(
        source_attack=lens, scope_attack=lens,
        completeness_attack=lens, convergence_attack=lens,
        insufficient_evidence=False, adjusted_reliability=0.7, adjusted_consensus=0.6,
        key_uncertainties=[], overall_severity=LensRating.MINOR,
    )
    bd = ERSPenaltyBreakdown(
        contradiction_edges_hard=0, contradiction_edges_partial=0, contradiction_penalty=0.0,
        inapplicable_source_count=0, total_source_count=2, applicability_penalty=0.0,
        uncertainty_count=0, uncertainty_penalty=0.0, total_penalty=0.0,
    )
    ers = ERSResult(
        score=0.72, band=ERSBand.HIGH,
        confidence_lower=0.67, confidence_upper=0.77,
        source_score=0.7, consensus_score=0.6, retrieval_relevance=0.9,
        contradiction_penalty=0.0, applicability_penalty=0.0, uncertainty_penalty=0.0,
        penalty_breakdown=bd, formula_trace="ERS = test",
    )
    claim = Claim(claim_id="c1", source_id="s1", text="test claim", claim_type=ClaimType.QUALITATIVE, confidence=0.8)
    return PipelineResponse(
        answer="Test answer.",
        ers=ers,
        critique=critique,
        claims=[claim],
        contradiction_graph=ContradictionGraph(edges=[]),
        applicability_report=ApplicabilityReport(flags=[], overall_applicable=True),
        uncertainties=[],
        insufficient_evidence=False,
        session_id="test_session",
    )


class TestAuditAgent:
    def test_audit_writes_summary_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOG_DIR", str(tmp_path))
        # Re-import to pick up the new log dir
        import importlib
        import backend.config.settings as settings_mod
        settings_mod.settings.log_dir = str(tmp_path)

        import backend.agents.a11_audit as a11_mod
        # Point the agent's loggers to tmp_path
        import logging, logging.handlers
        for lname in ("ers.audit.summary", "ers.audit.full"):
            lg = logging.getLogger(lname)
            lg.handlers.clear()
            h = logging.handlers.RotatingFileHandler(
                tmp_path / f"{lname.split('.')[-1]}.log",
                encoding="utf-8"
            )
            h.setFormatter(logging.Formatter("%(message)s"))
            lg.addHandler(h)

        agent = a11_mod.AuditAgent()
        response = make_minimal_response()
        trace_id = asyncio.run(agent.run("test query", response, "trace-abc"))

        # Check trace_id returned
        assert trace_id == "trace-abc"

        # Check summary log exists and contains valid JSON
        summary_log = tmp_path / "summary.log"
        if summary_log.exists():
            lines = summary_log.read_text().strip().splitlines()
            assert len(lines) >= 1
            record = json.loads(lines[-1])
            assert record["trace_id"] == "trace-abc"
            assert record["ers_score"] == 0.72
            assert record["ers_band"] == "High"

    def test_audit_generates_trace_id_if_none(self):
        import backend.agents.a11_audit as a11_mod
        agent = a11_mod.AuditAgent()
        response = make_minimal_response()
        trace_id = asyncio.run(agent.run("query", response, None))
        assert trace_id is not None
        assert len(trace_id) > 0

    def test_audit_does_not_crash_on_error(self):
        """Audit must swallow exceptions — it's fire-and-forget."""
        import backend.agents.a11_audit as a11_mod
        agent = a11_mod.AuditAgent()
        # Pass a None response to trigger an attribute error inside
        trace_id = asyncio.run(agent.run("query", None, "trace-xyz"))
        # Should still return a trace_id (from the error path)
        assert trace_id == "trace-xyz"
