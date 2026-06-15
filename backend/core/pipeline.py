"""Main pipeline orchestrator — runs all 11 agents in the correct phase order."""
import asyncio
from backend.models.schemas import PipelineRequest, PipelineResponse
from backend.agents.a1_ingestion import IngestionAgent
from backend.agents.a2_retrieval import RetrievalAgent
from backend.agents.a3_extraction import ExtractionAgent
from backend.agents.a4_reliability import ReliabilityAgent
from backend.agents.a5_consensus import ConsensusAgent
from backend.agents.a6_contradiction import ContradictionAgent
from backend.agents.a7_applicability import ApplicabilityAgent
from backend.agents.a8_critique import CritiqueAgent
from backend.agents.a9_ers_calibration import ERSCalibrationAgent
from backend.agents.a10_response import ResponseAgent
from backend.agents.a11_audit import AuditAgent


class EvidencePipeline:
    def __init__(self):
        self.a1 = IngestionAgent()
        self.a2 = RetrievalAgent()
        self.a3 = ExtractionAgent()
        self.a4 = ReliabilityAgent()
        self.a5 = ConsensusAgent()
        self.a6 = ContradictionAgent()
        self.a7 = ApplicabilityAgent()
        self.a8 = CritiqueAgent()
        self.a9 = ERSCalibrationAgent()
        self.a10 = ResponseAgent()
        self.a11 = AuditAgent()

    async def run(self, request: PipelineRequest) -> PipelineResponse:
        # Phase 1 — Ingress
        ingested = self.a1.run(request)
        clean_query = ingested["clean_query"]

        # Phase 2 — Retrieval
        documents = self.a2.run(clean_query)

        # Phase 3 — Extraction
        claims = self.a3.run(documents)

        # Phase 4 — Parallel scoring
        reliability, consensus_score, contradiction_graph, applicability_report = await asyncio.gather(
            asyncio.to_thread(self.a4.run, documents),
            asyncio.to_thread(self.a5.run, claims),
            asyncio.to_thread(self.a6.run, claims),
            asyncio.to_thread(self.a7.run, clean_query, documents),
        )

        # Phase 5 — Adversarial reasoning
        critique = self.a8.run(claims, reliability, contradiction_graph, applicability_report)
        insufficient_evidence = critique.get("insufficient_evidence", False)
        uncertainties = critique.get("key_uncertainties", [])

        source_score = (
            sum(r.score for r in reliability) / len(reliability)
            if reliability else 0.0
        )
        retrieval_relevance = (
            sum(d.get("score", 0.0) for d in documents) / len(documents)
            if documents else 0.0
        )
        ers = self.a9.run(
            source_score=critique.get("adjusted_reliability", source_score),
            consensus_score=critique.get("adjusted_consensus", consensus_score),
            retrieval_relevance=retrieval_relevance,
            contradiction_graph=contradiction_graph,
            applicability_report=applicability_report,
            uncertainties=uncertainties,
        )

        # Phase 6 — Output
        response = self.a10.run(
            query=clean_query,
            claims=claims,
            ers=ers,
            contradiction_graph=contradiction_graph,
            applicability_report=applicability_report,
            uncertainties=uncertainties,
            insufficient_evidence=insufficient_evidence,
            session_id=ingested.get("session_id"),
        )

        # Phase 7 — Async audit (fire and forget)
        asyncio.create_task(self.a11.run(clean_query, response))

        return response


pipeline = EvidencePipeline()
