"""A10 Response — assembles final structured output."""
from backend.models.schemas import (
    Claim, ERSResult, ContradictionGraph, ApplicabilityReport, PipelineResponse
)
from backend.services.gemini_service import gemini_service

ANSWER_PROMPT = """You are a precise evidence synthesizer. Answer the question based ONLY on the claims provided.
Acknowledge contradictions and uncertainties. Be factual and concise.

Question: {question}
Claims: {claims}
Uncertainties: {uncertainties}
ERS Score: {ers_score} ({ers_band})
Insufficient Evidence: {insufficient}

Provide a clear, structured answer.
"""


class ResponseAgent:
    def run(
        self,
        query: str,
        claims: list[Claim],
        ers: ERSResult,
        contradiction_graph: ContradictionGraph,
        applicability_report: ApplicabilityReport,
        uncertainties: list[str],
        insufficient_evidence: bool,
        session_id: str | None = None,
    ) -> PipelineResponse:
        answer = self._generate_answer(query, claims, ers, uncertainties, insufficient_evidence)
        return PipelineResponse(
            answer=answer,
            ers=ers,
            claims=claims,
            contradiction_graph=contradiction_graph,
            applicability_report=applicability_report,
            uncertainties=uncertainties,
            insufficient_evidence=insufficient_evidence,
            session_id=session_id,
        )

    def _generate_answer(self, query, claims, ers, uncertainties, insufficient) -> str:
        prompt = ANSWER_PROMPT.format(
            question=query,
            claims=[c.text for c in claims[:15]],
            uncertainties=uncertainties,
            ers_score=ers.score,
            ers_band=ers.band.value,
            insufficient=insufficient,
        )
        return gemini_service.generate(prompt)
