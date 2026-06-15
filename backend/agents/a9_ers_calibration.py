"""A9 ERS Calibration — computes ERS with formula and applies penalties."""
from backend.models.schemas import ERSBand, ERSResult, ContradictionGraph, ApplicabilityReport, RelationType


class ERSCalibrationAgent:
    # ERS = 0.45×source_score + 0.35×consensus_score + 0.20×retrieval_relevance
    W_SOURCE = 0.45
    W_CONSENSUS = 0.35
    W_RETRIEVAL = 0.20

    def run(
        self,
        source_score: float,
        consensus_score: float,
        retrieval_relevance: float,
        contradiction_graph: ContradictionGraph,
        applicability_report: ApplicabilityReport,
        uncertainties: list[str],
    ) -> ERSResult:
        base = (
            self.W_SOURCE * source_score
            + self.W_CONSENSUS * consensus_score
            + self.W_RETRIEVAL * retrieval_relevance
        )
        contradiction_penalty = self._contradiction_penalty(contradiction_graph)
        applicability_penalty = self._applicability_penalty(applicability_report)
        uncertainty_penalty = min(len(uncertainties) * 0.03, 0.15)

        final = max(0.0, min(1.0, base - contradiction_penalty - applicability_penalty - uncertainty_penalty))
        band = ERSBand.HIGH if final >= 0.7 else (ERSBand.MEDIUM if final >= 0.4 else ERSBand.LOW)

        return ERSResult(
            score=round(final, 3),
            band=band,
            confidence_lower=round(max(0.0, final - 0.05), 3),
            confidence_upper=round(min(1.0, final + 0.05), 3),
            source_score=source_score,
            consensus_score=consensus_score,
            retrieval_relevance=retrieval_relevance,
            contradiction_penalty=contradiction_penalty,
            applicability_penalty=applicability_penalty,
            uncertainty_penalty=uncertainty_penalty,
        )

    def _contradiction_penalty(self, graph: ContradictionGraph) -> float:
        penalty = 0.0
        for edge in graph.edges:
            if edge.relation == RelationType.CONTRADICTS:
                penalty += 0.10
            elif edge.relation == RelationType.PARTIAL_CONTRADICTION:
                penalty += 0.05
        return min(penalty, 0.30)

    def _applicability_penalty(self, report: ApplicabilityReport) -> float:
        if not report.flags:
            return 0.0
        inapplicable = sum(
            1 for f in report.flags
            if not (f.population_match and f.timeframe_match and f.outcome_match)
        )
        return min((inapplicable / len(report.flags)) * 0.20, 0.20)
