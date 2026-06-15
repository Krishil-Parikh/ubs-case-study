"""
A9 ERS Calibration
==================
Phase 5 — Adversarial reasoning (second step).

Computes the final Evidence Reliability Score (ERS) using the canonical formula:

    ERS_base = 0.45 × source_score
             + 0.35 × consensus_score
             + 0.20 × retrieval_relevance

Then applies three independent penalty tracks:

    contradiction_penalty  — per hard/partial contradiction edge in the graph
    applicability_penalty  — proportion of inapplicable sources × cap
    uncertainty_penalty    — per key uncertainty emitted by A8 Critique

    ERS = clamp( ERS_base − Σ(penalties) , 0.0, 1.0 )

The confidence band is dynamic, not a fixed ±0.05:
    - Widens with each contradiction and each uncertainty
    - Narrows with high-reliability source coverage
    - Capped in [0.02, 0.20]

Everything is logged and returned in the formula_trace field so any evaluator
can reproduce the exact score from the audit log alone.

No LLM calls — this agent is fully deterministic.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from backend.config.settings import settings
from backend.core.logging_config import get_logger
from backend.models.schemas import (
    ApplicabilityReport,
    ContradictionGraph,
    ERSBand,
    ERSPenaltyBreakdown,
    ERSResult,
    RelationType,
)

logger = get_logger("a9_ers_calibration")


@dataclass(frozen=True)
class _PenaltyComponents:
    """Internal intermediate — keeps the computation transparent."""
    contradiction_hard:    int
    contradiction_partial: int
    contradiction_penalty: float
    inapplicable:          int
    total_sources:         int
    applicability_penalty: float
    uncertainty_count:     int
    uncertainty_penalty:   float

    @property
    def total(self) -> float:
        return self.contradiction_penalty + self.applicability_penalty + self.uncertainty_penalty


class ERSCalibrationAgent:
    """
    A9 — ERS Calibration.

    Fully deterministic.  Receives post-critique scores from A8 and computes
    the final ERS score, band, confidence band, and full audit trail.
    """

    # ── Formula weights (pulled from settings so they're overridable) ─────────
    W_SOURCE    = settings.ers_weight_source
    W_CONSENSUS = settings.ers_weight_consensus
    W_RETRIEVAL = settings.ers_weight_retrieval

    # Band thresholds
    _BAND_HIGH   = 0.70
    _BAND_MEDIUM = 0.40

    # Confidence band — base margin and per-item adjustments
    _MARGIN_BASE          = 0.05
    _MARGIN_PER_HARD_CONTRA  = 0.02
    _MARGIN_PER_UNCERTAINTY  = 0.01
    _MARGIN_PER_HIGH_SRC     = -0.005   # narrows for each source above 0.7
    _MARGIN_MIN           = 0.02
    _MARGIN_MAX           = 0.20

    def __init__(self) -> None:
        # Validate weights sum to 1.0
        total = self.W_SOURCE + self.W_CONSENSUS + self.W_RETRIEVAL
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"ERS formula weights must sum to 1.0, got {total:.6f}")
        logger.info(
            "ERSCalibrationAgent initialised",
            extra={
                "w_source":    self.W_SOURCE,
                "w_consensus": self.W_CONSENSUS,
                "w_retrieval": self.W_RETRIEVAL,
            },
        )

    # ── Public entry point ────────────────────────────────────────────────────

    def run(
        self,
        source_score:         float,
        consensus_score:      float,
        retrieval_relevance:  float,
        contradiction_graph:  ContradictionGraph,
        applicability_report: ApplicabilityReport,
        uncertainties:        list[str],
        high_reliability_count: int = 0,   # # of sources above 0.7 reliability
    ) -> ERSResult:
        """
        Compute and return the final ERSResult.

        Args:
            source_score:           Post-critique adjusted reliability (from A8).
            consensus_score:        Post-critique adjusted consensus (from A8).
            retrieval_relevance:    Average vector search score from A2.
            contradiction_graph:    Output of A6.
            applicability_report:   Output of A7.
            uncertainties:          key_uncertainties list from A8.
            high_reliability_count: Used to narrow the confidence band.
        """
        run_start = time.perf_counter()
        logger.info(
            "A9 ERSCalibrationAgent.run — start",
            extra={
                "source_score":          round(source_score, 4),
                "consensus_score":       round(consensus_score, 4),
                "retrieval_relevance":   round(retrieval_relevance, 4),
                "contradiction_edges":   len(contradiction_graph.edges),
                "applicability_flags":   len(applicability_report.flags),
                "uncertainty_count":     len(uncertainties),
            },
        )

        # ── Step 1: base score ────────────────────────────────────────────
        base = self._compute_base(source_score, consensus_score, retrieval_relevance)
        logger.debug(
            "ERS base computed",
            extra={
                "base": round(base, 4),
                "formula": (
                    f"{self.W_SOURCE}×{source_score:.3f} + "
                    f"{self.W_CONSENSUS}×{consensus_score:.3f} + "
                    f"{self.W_RETRIEVAL}×{retrieval_relevance:.3f}"
                ),
            },
        )

        # ── Step 2: penalties ─────────────────────────────────────────────
        penalties = self._compute_penalties(contradiction_graph, applicability_report, uncertainties)
        logger.debug(
            "ERS penalties computed",
            extra={
                "contradiction_penalty":  round(penalties.contradiction_penalty, 4),
                "applicability_penalty":  round(penalties.applicability_penalty, 4),
                "uncertainty_penalty":    round(penalties.uncertainty_penalty, 4),
                "total_penalty":          round(penalties.total, 4),
            },
        )

        # ── Step 3: final score ───────────────────────────────────────────
        final = round(max(0.0, min(1.0, base - penalties.total)), 4)
        band  = self._band(final)
        logger.debug("ERS final score", extra={"final": final, "band": band.value})

        # ── Step 4: confidence band ───────────────────────────────────────
        margin = self._confidence_margin(
            contradiction_graph    = contradiction_graph,
            uncertainties          = uncertainties,
            high_reliability_count = high_reliability_count,
        )
        lower = round(max(0.0, final - margin), 4)
        upper = round(min(1.0, final + margin), 4)
        logger.debug("ERS confidence band", extra={"lower": lower, "upper": upper, "margin": round(margin, 4)})

        # ── Step 5: build audit trail ─────────────────────────────────────
        formula_trace = (
            f"ERS = {self.W_SOURCE}×{source_score:.3f}(src)"
            f" + {self.W_CONSENSUS}×{consensus_score:.3f}(con)"
            f" + {self.W_RETRIEVAL}×{retrieval_relevance:.3f}(ret)"
            f" = {base:.4f}(base)"
            f" − {penalties.contradiction_penalty:.4f}(contra)"
            f" − {penalties.applicability_penalty:.4f}(applic)"
            f" − {penalties.uncertainty_penalty:.4f}(uncert)"
            f" = {final:.4f}"
        )

        penalty_breakdown = ERSPenaltyBreakdown(
            contradiction_edges_hard    = penalties.contradiction_hard,
            contradiction_edges_partial = penalties.contradiction_partial,
            contradiction_penalty       = round(penalties.contradiction_penalty, 4),
            inapplicable_source_count   = penalties.inapplicable,
            total_source_count          = penalties.total_sources,
            applicability_penalty       = round(penalties.applicability_penalty, 4),
            uncertainty_count           = penalties.uncertainty_count,
            uncertainty_penalty         = round(penalties.uncertainty_penalty, 4),
            total_penalty               = round(penalties.total, 4),
        )

        result = ERSResult(
            score                = final,
            band                 = band,
            confidence_lower     = lower,
            confidence_upper     = upper,
            source_score         = round(source_score, 4),
            consensus_score      = round(consensus_score, 4),
            retrieval_relevance  = round(retrieval_relevance, 4),
            contradiction_penalty = round(penalties.contradiction_penalty, 4),
            applicability_penalty = round(penalties.applicability_penalty, 4),
            uncertainty_penalty   = round(penalties.uncertainty_penalty, 4),
            penalty_breakdown     = penalty_breakdown,
            formula_trace         = formula_trace,
        )

        elapsed = time.perf_counter() - run_start
        logger.info(
            "A9 ERSCalibrationAgent.run — complete",
            extra={
                "elapsed_ms":       round(elapsed * 1000),
                "ers_score":        final,
                "ers_band":         band.value,
                "confidence_lower": lower,
                "confidence_upper": upper,
                "total_penalty":    round(penalties.total, 4),
                "formula_trace":    formula_trace,
            },
        )
        return result

    # ── Formula helpers ───────────────────────────────────────────────────────

    def _compute_base(
        self,
        source_score:        float,
        consensus_score:     float,
        retrieval_relevance: float,
    ) -> float:
        """ERS base = 0.45×src + 0.35×con + 0.20×ret"""
        return (
            self.W_SOURCE    * source_score
            + self.W_CONSENSUS * consensus_score
            + self.W_RETRIEVAL * retrieval_relevance
        )

    def _compute_penalties(
        self,
        contradiction_graph:  ContradictionGraph,
        applicability_report: ApplicabilityReport,
        uncertainties:        list[str],
    ) -> _PenaltyComponents:
        """Compute all three penalty tracks."""

        # ── Contradiction penalty ─────────────────────────────────────────
        hard    = sum(1 for e in contradiction_graph.edges if e.relation == RelationType.CONTRADICTS)
        partial = sum(1 for e in contradiction_graph.edges if e.relation == RelationType.PARTIAL_CONTRADICTION)
        contra_penalty = min(
            hard    * settings.ers_contradiction_penalty_per_hard
            + partial * settings.ers_contradiction_penalty_per_partial,
            settings.ers_contradiction_penalty_cap,
        )

        # ── Applicability penalty ─────────────────────────────────────────
        flags = applicability_report.flags
        if flags:
            inapplicable = sum(
                1 for f in flags
                if not (f.population_match and f.timeframe_match and f.outcome_match)
            )
            applic_penalty = min(
                (inapplicable / len(flags)) * settings.ers_applicability_penalty_cap,
                settings.ers_applicability_penalty_cap,
            )
        else:
            inapplicable   = 0
            applic_penalty = 0.0

        # ── Uncertainty penalty ───────────────────────────────────────────
        n_uncertainties  = len(uncertainties)
        uncert_penalty   = min(
            n_uncertainties * settings.ers_uncertainty_penalty_per_item,
            settings.ers_uncertainty_penalty_cap,
        )

        return _PenaltyComponents(
            contradiction_hard    = hard,
            contradiction_partial = partial,
            contradiction_penalty = round(contra_penalty, 4),
            inapplicable          = inapplicable,
            total_sources         = len(flags),
            applicability_penalty = round(applic_penalty, 4),
            uncertainty_count     = n_uncertainties,
            uncertainty_penalty   = round(uncert_penalty, 4),
        )

    def _band(self, score: float) -> ERSBand:
        if score >= self._BAND_HIGH:
            return ERSBand.HIGH
        if score >= self._BAND_MEDIUM:
            return ERSBand.MEDIUM
        return ERSBand.LOW

    def _confidence_margin(
        self,
        contradiction_graph:    ContradictionGraph,
        uncertainties:          list[str],
        high_reliability_count: int,
    ) -> float:
        """
        Dynamic confidence margin — widens with evidence weakness,
        narrows with evidence strength.
        """
        hard_contras = sum(
            1 for e in contradiction_graph.edges if e.relation == RelationType.CONTRADICTS
        )
        margin = self._MARGIN_BASE
        margin += hard_contras                 * self._MARGIN_PER_HARD_CONTRA
        margin += len(uncertainties)           * self._MARGIN_PER_UNCERTAINTY
        margin += high_reliability_count       * self._MARGIN_PER_HIGH_SRC
        return round(max(self._MARGIN_MIN, min(self._MARGIN_MAX, margin)), 4)
