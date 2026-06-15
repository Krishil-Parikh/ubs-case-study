"""
Main pipeline orchestrator — runs all 11 agents in the correct phase order.

Phase execution:
  1  → A1  Ingestion         (sequential)
  2  → A2  Retrieval         (sequential)
  3  → A3  Extraction        (sequential)
  4  → A4/A5/A6/A7           (parallel fan-out)
  5  → A8  Critique          (sequential, receives all Phase 4 outputs)
     → A9  ERS Calibration   (sequential, after A8)
  6  → A10 Response          (sequential)
  7  → A11 Audit             (async fire-and-forget)
"""

from __future__ import annotations

import asyncio
import time

from backend.core.logging_config import get_logger, setup_logging
from backend.models.schemas import PipelineRequest, PipelineResponse
from backend.agents.a1_ingestion       import IngestionAgent
from backend.agents.a2_retrieval       import RetrievalAgent
from backend.agents.a3_extraction      import ExtractionAgent
from backend.agents.a4_reliability     import ReliabilityAgent
from backend.agents.a5_consensus       import ConsensusAgent
from backend.agents.a6_contradiction   import ContradictionAgent
from backend.agents.a7_applicability   import ApplicabilityAgent
from backend.agents.a8_critique        import CritiqueAgent
from backend.agents.a9_ers_calibration import ERSCalibrationAgent
from backend.agents.a10_response       import ResponseAgent
from backend.agents.a11_audit          import AuditAgent

setup_logging()
logger = get_logger("pipeline")


class EvidencePipeline:

    def __init__(self) -> None:
        self.a1  = IngestionAgent()
        self.a2  = RetrievalAgent()
        self.a3  = ExtractionAgent()
        self.a4  = ReliabilityAgent()
        self.a5  = ConsensusAgent()
        self.a6  = ContradictionAgent()
        self.a7  = ApplicabilityAgent()
        self.a8  = CritiqueAgent()
        self.a9  = ERSCalibrationAgent()
        self.a10 = ResponseAgent()
        self.a11 = AuditAgent()
        logger.info("EvidencePipeline ready — all 11 agents initialised")

    async def run(self, request: PipelineRequest) -> PipelineResponse:
        pipeline_start = time.perf_counter()
        logger.info(
            "Pipeline run — start",
            extra={"query_length": len(request.query), "session_id": request.session_id},
        )

        # ── Phase 1 — Ingress ─────────────────────────────────────────────
        t0          = time.perf_counter()
        ingested    = self.a1.run(request)
        clean_query = ingested["clean_query"]
        logger.info("Phase 1 complete", extra={"elapsed_ms": _ms(t0)})

        # ── Phase 2 — Retrieval ───────────────────────────────────────────
        t0        = time.perf_counter()
        documents = self.a2.run(clean_query)
        logger.info("Phase 2 complete", extra={"elapsed_ms": _ms(t0), "docs_retrieved": len(documents)})

        # ── Phase 3 — Extraction ──────────────────────────────────────────
        t0     = time.perf_counter()
        claims = self.a3.run(documents)
        logger.info("Phase 3 complete", extra={"elapsed_ms": _ms(t0), "claims_extracted": len(claims)})

        # ── Phase 4 — Parallel scoring ────────────────────────────────────
        t0 = time.perf_counter()
        reliability, consensus_score, contradiction_graph, applicability_report = await asyncio.gather(
            asyncio.to_thread(self.a4.run, documents, claims),   # claims needed for caveat map
            asyncio.to_thread(self.a5.run, claims),
            asyncio.to_thread(self.a6.run, claims),
            asyncio.to_thread(self.a7.run, clean_query, documents),
        )
        avg_reliability = (
            sum(r.score for r in reliability) / len(reliability) if reliability else 0.0
        )
        logger.info(
            "Phase 4 complete",
            extra={
                "elapsed_ms":          _ms(t0),
                "avg_reliability":     round(avg_reliability, 3),
                "consensus_score":     round(consensus_score, 3),
                "contradiction_edges": len(contradiction_graph.edges),
                "applicability_flags": len(applicability_report.flags),
            },
        )

        # ── Phase 5a — A8 Critique ────────────────────────────────────────
        t0      = time.perf_counter()
        critique = self.a8.run(
            query               = clean_query,
            claims              = claims,
            reliability         = reliability,
            contradiction_graph = contradiction_graph,
            applicability       = applicability_report,
        )
        logger.info(
            "Phase 5a complete (A8 Critique)",
            extra={
                "elapsed_ms":            _ms(t0),
                "insufficient_evidence": critique.insufficient_evidence,
                "overall_severity":      critique.overall_severity.value,
            },
        )

        # ── Phase 5b — A9 ERS Calibration ────────────────────────────────
        t0 = time.perf_counter()
        retrieval_relevance = (
            sum(d.get("score", 0.0) for d in documents) / len(documents)
            if documents else 0.0
        )
        high_rel_count = sum(1 for r in reliability if r.score >= 0.7)

        ers = self.a9.run(
            source_score           = critique.adjusted_reliability,
            consensus_score        = critique.adjusted_consensus,
            retrieval_relevance    = retrieval_relevance,
            contradiction_graph    = contradiction_graph,
            applicability_report   = applicability_report,
            uncertainties          = critique.key_uncertainties,
            high_reliability_count = high_rel_count,
        )
        logger.info(
            "Phase 5b complete (A9 ERS Calibration)",
            extra={
                "elapsed_ms": _ms(t0),
                "ers_score":  ers.score,
                "ers_band":   ers.band.value,
                "formula":    ers.formula_trace,
            },
        )

        # ── Phase 6 — Response ────────────────────────────────────────────
        t0       = time.perf_counter()
        response = self.a10.run(
            query                 = clean_query,
            claims                = claims,
            ers                   = ers,
            contradiction_graph   = contradiction_graph,
            applicability_report  = applicability_report,
            uncertainties         = critique.key_uncertainties,
            insufficient_evidence = critique.insufficient_evidence,
            reliability           = reliability,
            critique              = critique,
            session_id            = ingested.get("session_id"),
        )
        response.critique = critique
        logger.info("Phase 6 complete (Response)", extra={"elapsed_ms": _ms(t0)})

        # ── Phase 7 — Async audit (fire-and-forget) ───────────────────────
        asyncio.create_task(self.a11.run(clean_query, response))

        total_elapsed = time.perf_counter() - pipeline_start
        logger.info(
            "Pipeline run — complete",
            extra={
                "total_elapsed_ms":      round(total_elapsed * 1000),
                "ers_score":             ers.score,
                "ers_band":              ers.band.value,
                "insufficient_evidence": critique.insufficient_evidence,
            },
        )
        return response


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


pipeline = EvidencePipeline()
