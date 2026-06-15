"""
A8 Critique / Skeptic
=====================
Phase 5 — Adversarial reasoning (first step).

Receives all Phase 4 outputs and attacks them through four fixed lenses:
  1. Source Attack       — reliability, peer-review status, CoI, sample sizes
  2. Scope Attack        — population match, timeframe, outcome alignment
  3. Completeness Attack — missing evidence, publication bias, systematic gaps
  4. Convergence Attack  — illusory consensus, citation cascades, correlated methodology

Has hard authority to emit INSUFFICIENT_EVIDENCE, blocking the final answer.

Deterministic pre-checks run first (no LLM cost).
If pre-checks pass, Gemini Pro is called with a system instruction that anchors
the adversarial persona at model level (not just in the user prompt).
"""

from __future__ import annotations

import json
import time
from typing import Any

from backend.config.settings import settings
from backend.core.logging_config import get_logger
from backend.models.schemas import (
    ApplicabilityReport,
    Claim,
    ContradictionGraph,
    CritiqueOutput,
    LensAnalysis,
    LensRating,
    ReliabilityScore,
    RelationType,
)
from backend.services.gemini_service import gemini_service

logger = get_logger("a8_critique")


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM INSTRUCTION  (anchored at model level — not part of user content)
# ═══════════════════════════════════════════════════════════════════════════════

_SYSTEM_INSTRUCTION = """\
You are an adversarial evidence critic embedded in a multi-agent evidence \
evaluation pipeline. Your sole mandate is to stress-test the evidence base — \
not to validate it. Assume nothing is reliable until proven otherwise.

You operate through exactly FOUR fixed lenses:

  LENS 1 — SOURCE ATTACK
  Scrutinise: peer-review status, journal impact factor, sample sizes, funding sources,
  conflict-of-interest disclosures, methodological rigour, replication history,
  and publication bias toward positive results.

  LENS 2 — SCOPE / APPLICABILITY ATTACK
  Scrutinise: Does the evidence population match the question population?
  Is the measured timeframe relevant to the question? Are the reported outcomes
  the ones the question actually asks about? Is the intervention/exposure equivalent?

  LENS 3 — COMPLETENESS ATTACK
  Scrutinise: What relevant evidence is absent? Are there known opposing studies not
  represented? Is there a systematic gap (single geography, single time window,
  single research group)? Would the conclusion change if the missing evidence existed?

  LENS 4 — CONVERGENCE ATTACK
  Scrutinise: Is apparent agreement real or illusory?
  Do all "agreeing" sources cite the same upstream study (citation cascade)?
  Are they from the same research group or funded by the same entity?
  Is agreement a product of correlated methodology rather than independent replication?

For each lens you MUST:
  • Identify SPECIFIC, CONCRETE issues — not vague concerns
  • Rate severity: severe | moderate | minor | clear
  • Recommend a numeric penalty (0.00 = no adjustment, 0.30 = maximum deduction)

INSUFFICIENT_EVIDENCE HARD OVERRIDE
You have authority to set insufficient_evidence = true.
This blocks ALL conclusions. Use it when no reliable conclusion is possible.
Mandatory trigger conditions:
  • Fewer than 2 independent claims exist
  • Every source scores below 0.4 reliability
  • Zero sources apply to the question population and context
  • Hard logical contradictions are unresolvable and directionally opposed
  • Publication bias is so systematic that the real effect direction is unknowable

Do not hedge. Do not validate. Find what is wrong.
Output ONLY valid JSON — no markdown fences, no prose outside the JSON object.\
"""


# ═══════════════════════════════════════════════════════════════════════════════
# USER MESSAGE TEMPLATE  (dynamic per request)
# ═══════════════════════════════════════════════════════════════════════════════

_USER_TEMPLATE = """\
RESEARCH QUESTION:
{query}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CLAIMS UNDER REVIEW  ({claim_count} total):
{claims_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SOURCE RELIABILITY SCORES  ({source_count} sources):
{reliability_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTRADICTION GRAPH  ({contradiction_count} edges):
{contradiction_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
APPLICABILITY REPORT  ({flag_count} source flags):
{applicability_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Apply all four lenses adversarially. Be specific about every finding.

Return this exact JSON — no extra keys, no omissions:
{{
  "source_attack": {{
    "rating": "<severe|moderate|minor|clear>",
    "findings": ["<specific finding 1>", "<specific finding 2>"],
    "penalty_recommendation": <0.00–0.30>
  }},
  "scope_attack": {{
    "rating": "<severe|moderate|minor|clear>",
    "findings": ["<specific finding 1>"],
    "penalty_recommendation": <0.00–0.30>
  }},
  "completeness_attack": {{
    "rating": "<severe|moderate|minor|clear>",
    "findings": ["<specific finding 1>"],
    "penalty_recommendation": <0.00–0.30>
  }},
  "convergence_attack": {{
    "rating": "<severe|moderate|minor|clear>",
    "findings": ["<specific finding 1>"],
    "penalty_recommendation": <0.00–0.30>
  }},
  "insufficient_evidence": <true|false>,
  "insufficient_evidence_reason": "<reason string or null>",
  "adjusted_reliability": <0.00–1.00>,
  "adjusted_consensus": <0.00–1.00>,
  "key_uncertainties": ["<uncertainty 1>", "<uncertainty 2>"],
  "overall_severity": "<severe|moderate|minor|clear>"
}}\
"""


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT
# ═══════════════════════════════════════════════════════════════════════════════

class CritiqueAgent:
    """
    A8 — Adversarial Critique / Skeptic.

    Deterministic pre-checks → Gemini Pro with system instruction → structured output.
    """

    def __init__(self) -> None:
        # Build a model instance with the adversarial persona baked into the system instruction.
        # This is separate from user content so the persona cannot be overridden by input data.
        self._model = gemini_service.build_model_with_system(
            system_instruction = _SYSTEM_INSTRUCTION,
            use_flash          = False,   # always Pro for Phase 5
            json_mode          = True,
        )
        logger.info("CritiqueAgent initialised", extra={"model": settings.gemini_model})

    # ── Public entry point ────────────────────────────────────────────────────

    def run(
        self,
        query: str,
        claims: list[Claim],
        reliability: list[ReliabilityScore],
        contradiction_graph: ContradictionGraph,
        applicability: ApplicabilityReport,
    ) -> CritiqueOutput:
        """
        Execute the full critique cycle.

        Returns a validated CritiqueOutput.  Never raises — falls back to a
        conservative output if Gemini is unavailable.
        """
        run_start = time.perf_counter()
        logger.info(
            "A8 CritiqueAgent.run — start",
            extra={
                "query_length":          len(query),
                "claim_count":           len(claims),
                "source_count":          len(reliability),
                "contradiction_edges":   len(contradiction_graph.edges),
                "applicability_flags":   len(applicability.flags),
            },
        )

        # ── Step 1: deterministic pre-checks (free, fast) ─────────────────
        pre = self._pre_check(claims, reliability, contradiction_graph, applicability)
        if pre["triggered"]:
            logger.warning(
                "INSUFFICIENT_EVIDENCE — pre-check triggered (no LLM call)",
                extra={"reason": pre["reason"]},
            )
            result = self._build_insufficient(pre["reason"])
            self._log_result(result, time.perf_counter() - run_start, from_precheck=True)
            return result

        # ── Step 2: build user message ─────────────────────────────────────
        user_msg = self._build_message(query, claims, reliability, contradiction_graph, applicability)
        logger.debug("User message built", extra={"length": len(user_msg)})

        # ── Step 3: call Gemini (retries handled by GeminiService) ────────
        try:
            raw = self._model.generate_content(user_msg).text
            logger.debug("Gemini raw response", extra={"length": len(raw)})
        except Exception as exc:
            logger.error("Gemini call failed — using conservative fallback", extra={"error": str(exc)})
            raw = ""

        # ── Step 4: parse + validate ───────────────────────────────────────
        result = self._parse(raw, reliability)

        elapsed = time.perf_counter() - run_start
        self._log_result(result, elapsed, from_precheck=False)
        return result

    # ── Pre-check (deterministic, no LLM) ────────────────────────────────────

    def _pre_check(
        self,
        claims: list[Claim],
        reliability: list[ReliabilityScore],
        contradiction_graph: ContradictionGraph,
        applicability: ApplicabilityReport,
    ) -> dict[str, Any]:
        """Run deterministic INSUFFICIENT_EVIDENCE conditions before calling Gemini."""

        # Condition 1: evidence base too thin
        if len(claims) < settings.insufficient_min_claims:
            return {
                "triggered": True,
                "reason": (
                    f"Evidence base too thin: only {len(claims)} claim(s) found. "
                    f"Minimum required: {settings.insufficient_min_claims}."
                ),
            }

        # Condition 2: all sources below reliability ceiling
        if reliability and all(r.score < settings.insufficient_reliability_ceiling for r in reliability):
            avg = sum(r.score for r in reliability) / len(reliability)
            return {
                "triggered": True,
                "reason": (
                    f"All {len(reliability)} sources score below the reliability ceiling "
                    f"({settings.insufficient_reliability_ceiling}). "
                    f"Average score: {avg:.3f}."
                ),
            }

        # Condition 3: zero applicable sources
        if applicability.flags:
            all_inapplicable = all(
                not (f.population_match and f.timeframe_match and f.outcome_match)
                for f in applicability.flags
            )
            if all_inapplicable:
                return {
                    "triggered": True,
                    "reason": (
                        f"All {len(applicability.flags)} sources are inapplicable to the "
                        f"question population, timeframe, or outcome."
                    ),
                }

        # Condition 4: unresolvable hard contradictions with no supporting consensus
        hard_contradictions = sum(
            1 for e in contradiction_graph.edges if e.relation == RelationType.CONTRADICTS
        )
        if hard_contradictions >= 3 and len(claims) < 5:
            return {
                "triggered": True,
                "reason": (
                    f"{hard_contradictions} hard contradictions found across only "
                    f"{len(claims)} claims — evidence is directionally ambiguous."
                ),
            }

        return {"triggered": False, "reason": None}

    # ── Message builder ───────────────────────────────────────────────────────

    def _build_message(
        self,
        query: str,
        claims: list[Claim],
        reliability: list[ReliabilityScore],
        contradiction_graph: ContradictionGraph,
        applicability: ApplicabilityReport,
    ) -> str:
        claims_block = "\n".join(
            f"  [{i+1}] [{c.claim_type.value.upper():22}] (conf={c.confidence:.2f}) {c.text}"
            for i, c in enumerate(claims[:25])   # cap at 25 to stay within token budget
        ) or "  (no claims)"

        reliability_block = "\n".join(
            f"  src={r.source_id[:8]}  type={r.source_type:20}  score={r.score:.3f}"
            f"  recency={r.recency_score:.2f}"
            + (f"  ⚠ LLM-escalated: {r.escalation_reason[:60]}" if r.llm_escalated else "")
            for r in reliability
        ) or "  (no reliability data)"

        if contradiction_graph.edges:
            contradiction_block = "\n".join(
                f"  [{e.relation.value:25}] {e.explanation[:120]}"
                for e in contradiction_graph.edges
            )
        else:
            contradiction_block = "  (no contradictions detected)"

        if applicability.flags:
            applicability_block = "\n".join(
                f"  src={f.source_id[:8]}  pop={f.population_match}  time={f.timeframe_match}"
                f"  outcome={f.outcome_match}"
                + (f"  reason: {f.flag_reason}" if f.flag_reason else "")
                for f in applicability.flags
            )
        else:
            applicability_block = "  (no applicability flags)"

        return _USER_TEMPLATE.format(
            query                = query,
            claim_count          = len(claims),
            claims_block         = claims_block,
            source_count         = len(reliability),
            reliability_block    = reliability_block,
            contradiction_count  = len(contradiction_graph.edges),
            contradiction_block  = contradiction_block,
            flag_count           = len(applicability.flags),
            applicability_block  = applicability_block,
        )

    # ── Response parser ───────────────────────────────────────────────────────

    def _parse(self, raw: str, reliability: list[ReliabilityScore]) -> CritiqueOutput:
        """Parse Gemini JSON output into a validated CritiqueOutput."""
        raw = raw.strip()
        if not raw:
            logger.warning("Empty Gemini response — conservative fallback")
            return self._conservative_fallback(reliability)

        # Strip markdown fences if Gemini adds them despite JSON mode
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("JSON parse failed", extra={"error": str(exc), "raw_head": raw[:200]})
            return self._conservative_fallback(reliability)

        try:
            return CritiqueOutput(
                source_attack       = LensAnalysis(**data["source_attack"]),
                scope_attack        = LensAnalysis(**data["scope_attack"]),
                completeness_attack = LensAnalysis(**data["completeness_attack"]),
                convergence_attack  = LensAnalysis(**data["convergence_attack"]),
                insufficient_evidence        = bool(data.get("insufficient_evidence", False)),
                insufficient_evidence_reason = data.get("insufficient_evidence_reason"),
                adjusted_reliability = float(data.get("adjusted_reliability", 0.5)),
                adjusted_consensus   = float(data.get("adjusted_consensus", 0.5)),
                key_uncertainties    = data.get("key_uncertainties", []),
                overall_severity     = LensRating(data.get("overall_severity", "moderate")),
            )
        except Exception as exc:
            logger.error("CritiqueOutput validation failed", extra={"error": str(exc)})
            return self._conservative_fallback(reliability)

    # ── Fallback builders ─────────────────────────────────────────────────────

    def _build_insufficient(self, reason: str) -> CritiqueOutput:
        """Build a CritiqueOutput that signals INSUFFICIENT_EVIDENCE."""
        _severe_lens = LensAnalysis(
            rating                 = LensRating.SEVERE,
            findings               = [reason],
            penalty_recommendation = 0.30,
        )
        return CritiqueOutput(
            source_attack                = _severe_lens,
            scope_attack                 = _severe_lens,
            completeness_attack          = _severe_lens,
            convergence_attack           = _severe_lens,
            insufficient_evidence        = True,
            insufficient_evidence_reason = reason,
            adjusted_reliability         = 0.0,
            adjusted_consensus           = 0.0,
            key_uncertainties            = [reason],
            overall_severity             = LensRating.SEVERE,
        )

    def _conservative_fallback(self, reliability: list[ReliabilityScore]) -> CritiqueOutput:
        """
        Used when Gemini is unavailable or returns unparseable output.
        Returns a moderate-severity output — penalises for the unknown.
        """
        avg_rel = (
            sum(r.score for r in reliability) / len(reliability) if reliability else 0.5
        )
        _unknown_lens = LensAnalysis(
            rating                 = LensRating.MODERATE,
            findings               = ["LLM critique unavailable — applying conservative defaults."],
            penalty_recommendation = 0.10,
        )
        return CritiqueOutput(
            source_attack                = _unknown_lens,
            scope_attack                 = _unknown_lens,
            completeness_attack          = _unknown_lens,
            convergence_attack           = _unknown_lens,
            insufficient_evidence        = False,
            insufficient_evidence_reason = None,
            adjusted_reliability         = round(avg_rel * 0.8, 3),  # 20% haircut for uncertainty
            adjusted_consensus           = 0.5,
            key_uncertainties            = ["Adversarial critique could not be completed."],
            overall_severity             = LensRating.MODERATE,
        )

    # ── Logging helpers ───────────────────────────────────────────────────────

    def _log_result(self, result: CritiqueOutput, elapsed: float, *, from_precheck: bool) -> None:
        logger.info(
            "A8 CritiqueAgent.run — complete",
            extra={
                "source":                  "precheck" if from_precheck else "llm",
                "elapsed_ms":              round(elapsed * 1000),
                "overall_severity":        result.overall_severity.value,
                "insufficient_evidence":   result.insufficient_evidence,
                "adjusted_reliability":    result.adjusted_reliability,
                "adjusted_consensus":      result.adjusted_consensus,
                "uncertainty_count":       len(result.key_uncertainties),
                "source_attack_rating":    result.source_attack.rating.value,
                "scope_attack_rating":     result.scope_attack.rating.value,
                "completeness_rating":     result.completeness_attack.rating.value,
                "convergence_rating":      result.convergence_attack.rating.value,
            },
        )
