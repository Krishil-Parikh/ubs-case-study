"""A4 Reliability — two-pass source credibility + evidence quality scoring.

Pass 1 (deterministic):
  - Source-type base score (evidence hierarchy)
  - Recency exponential decay (with soft floor guardrail)
  - Domain blocklist for obvious CoI

Pass 2 (LLM escalation):
  - Conflict-of-interest detection for edge cases
  - Study design classification from methods section / methodological caveats (with fuzzy enum mapping)

Output: ReliabilityScore[] — one per source document (NOT per claim).
        Downstream join: claim.source_id == reliability.source_id
"""
import math
import re
import json
import logging
from datetime import datetime
from typing import Optional

from backend.models.schemas import (
    Claim,
    ClaimType,
    CoISeverity,
    ReliabilityScore,
    SourceType,
    StudyDesign,
)
from backend.services.gemini_service import gemini_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Evidence hierarchy — base scores by source type
# ---------------------------------------------------------------------------
SOURCE_TYPE_BASE_SCORES: dict[str, float] = {
    # Research tiers
    SourceType.RESEARCH_PAPER.value: 0.80,
    # News & blogs
    SourceType.NEWS_ARTICLE.value: 0.40,
    SourceType.BLOG.value: 0.30,
    SourceType.UNKNOWN.value: 0.20,
}

# Study design multipliers applied ON TOP of the research_paper base score
STUDY_DESIGN_MULTIPLIERS: dict[StudyDesign, float] = {
    StudyDesign.META_ANALYSIS: 1.25,
    StudyDesign.SYSTEMATIC_REVIEW: 1.20,
    StudyDesign.RCT: 1.10,
    StudyDesign.COHORT: 1.00,
    StudyDesign.CASE_CONTROL: 0.90,
    StudyDesign.CASE_REPORT: 0.75,
    StudyDesign.NARRATIVE_REVIEW: 0.70,
    StudyDesign.OPINION: 0.60,
    StudyDesign.NOT_APPLICABLE: 1.00,
}


# ---------------------------------------------------------------------------
# Recency decay configuration
# ---------------------------------------------------------------------------
CURRENT_YEAR = datetime.now().year
RECENCY_HALF_LIFE_YEARS = 5  # evidence half-life — tune per domain
RECENCY_SCORE_FLOOR = 0.3     # Soft constraint: landmark older studies don't decay to 0


# ---------------------------------------------------------------------------
# CoI domain blocklist — known promotional / vendor domains
# ---------------------------------------------------------------------------
COI_DOMAIN_BLOCKLIST = frozenset([
    "supplementcompany.com",
    "vendorhealth.com",
    "affiliatelink.io",
    "naturalcures.com",
    "promohealth.net",
])


# ---------------------------------------------------------------------------
# Optimized LLM prompts
# ---------------------------------------------------------------------------

COI_DETECTION_PROMPT = """Analyze the following source metadata and text snippet for commercial conflict of interest (CoI).

Determine if there is promotional language, sponsor influence, vendor bias, or sales intent.
Output a JSON object with:
- "has_coi": true if a conflict of interest or strong promotional bias is detected, false otherwise.
- "severity": "none", "low" (minor promotional tone/affiliate mention), or "high" (direct vendor store, sponsored post, or extreme bias).
- "reason": concise explanation of the finding.

Do not include markdown formatting or extra text. Output valid JSON only.

Source metadata: {metadata}
Text snippet (first 2000 chars):
{text_snippet}
"""

STUDY_DESIGN_PROMPT = """Classify the research methodology of the study based on the methods text and caveat notes.

Select exactly one study design classification from this list:
- meta_analysis
- systematic_review
- rct (Randomized Controlled Trial)
- cohort
- case_control
- case_report
- narrative_review
- opinion

Output a JSON object with:
- "study_design": the exact string from the list above.
- "rationale": concise justification for this classification.

Do not include markdown formatting or extra text. Output valid JSON only.

Methods section / caveats:
{methods_text}
"""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class ReliabilityAgent:
    """A4 — scores source credibility and evidence quality per document.

    IMPORTANT: This agent does NOT assess whether claims are true.
    It assesses the credibility of the source and the rigor of the
    evidence methodology. Truth assessment is downstream at A8.
    """

    def run(
        self,
        documents: list[dict],
        claims: Optional[list[Claim]] = None,
    ) -> list[ReliabilityScore]:
        """Score each document for reliability.

        Args:
            documents: list of dicts with keys:
                - id: unique document identifier (join key)
                - payload: { text, source_type?, year?, url?, ... }
            claims: optional claim list from A3 — used to extract
                    methodological caveats for study design classification.

        Returns:
            List of ReliabilityScore, one per document.
        """
        # Build a lookup: doc_id -> methodological caveat texts from A3
        caveat_map = self._build_caveat_map(claims or [])

        scores: list[ReliabilityScore] = []
        for doc in documents:
            doc_id = str(doc["id"])
            payload = doc.get("payload", {})

            # --- Pass 1: Deterministic scoring --------------------------
            source_type = payload.get("source_type", SourceType.UNKNOWN.value)
            base_type_score = SOURCE_TYPE_BASE_SCORES.get(
                source_type, SOURCE_TYPE_BASE_SCORES[SourceType.UNKNOWN.value]
            )
            recency = self._recency_score(payload)
            coi_severity, coi_reason = self._deterministic_coi(payload)

            # --- Pass 2: LLM escalation ---------------------------------
            llm_escalated = False
            study_design = StudyDesign.NOT_APPLICABLE
            escalation_reason = None

            needs_coi_escalation = (
                coi_severity == CoISeverity.NONE
                and self._should_escalate_coi(payload)
            )
            is_research = source_type == SourceType.RESEARCH_PAPER.value

            if needs_coi_escalation:
                llm_coi_severity, llm_coi_reason = self._llm_coi_detection(payload)
                if llm_coi_severity != CoISeverity.NONE:
                    coi_severity = llm_coi_severity
                    coi_reason = llm_coi_reason
                    llm_escalated = True
                    escalation_reason = f"CoI: {llm_coi_reason}"

            if is_research:
                methods_text = self._get_methods_text(payload, caveat_map.get(doc_id, []))
                if methods_text:
                    study_design = self._llm_study_design(methods_text)
                    llm_escalated = True
                    escalation_reason = (
                        (escalation_reason + " | " if escalation_reason else "")
                        + f"StudyDesign: {study_design.value}"
                    )

            # --- Composite score ----------------------------------------
            # Apply study design multiplier to base type score
            adjusted_base = base_type_score * STUDY_DESIGN_MULTIPLIERS.get(
                study_design, 1.0
            )
            # Cap adjusted base at 1.0
            adjusted_base = min(adjusted_base, 1.0)

            # CoI penalty
            coi_penalty = {
                CoISeverity.NONE: 0.0,
                CoISeverity.LOW: 0.10,
                CoISeverity.HIGH: 0.25,
            }.get(coi_severity, 0.0)

            # Final composite: weighted combination of source quality + recency, minus CoI
            composite = (0.6 * adjusted_base + 0.4 * recency) - coi_penalty
            
            # Guardrail: Clamp composite score between 0.0 and 1.0 and round
            composite = round(max(0.0, min(1.0, composite)), 3)

            scores.append(
                ReliabilityScore(
                    source_id=doc_id,
                    score=composite,
                    source_type=source_type,
                    recency_score=round(recency, 3),
                    base_type_score=round(adjusted_base, 3),
                    coi_severity=coi_severity,
                    coi_reason=coi_reason,
                    study_design=study_design,
                    llm_escalated=llm_escalated,
                    escalation_reason=escalation_reason,
                )
            )

        logger.info("A4 reliability: scored %d documents", len(scores))
        return scores

    def _recency_score(self, payload: dict) -> float:
        """Exponential decay based on publication year.
        
        Guardrails applied:
          - Cap year to CURRENT_YEAR to handle incorrect/future metadata.
          - Apply RECENCY_SCORE_FLOOR so landmark older studies don't score 0.0.
        """
        try:
            year = int(payload.get("year", CURRENT_YEAR))
        except (ValueError, TypeError):
            year = CURRENT_YEAR

        # Guardrail: clamp future years to current year
        if year > CURRENT_YEAR:
            year = CURRENT_YEAR

        age = max(0, CURRENT_YEAR - year)
        raw_recency = math.pow(2, -(age / RECENCY_HALF_LIFE_YEARS))
        
        # Soft constraint: floor value
        return max(RECENCY_SCORE_FLOOR, raw_recency)

    def _deterministic_coi(self, payload: dict) -> tuple[CoISeverity, Optional[str]]:
        """Check for obvious conflict of interest via metadata / domain blocklist."""
        if payload.get("conflict_of_interest"):
            return CoISeverity.HIGH, "Explicit CoI flag in metadata"

        url = payload.get("url", "")
        for blocked in COI_DOMAIN_BLOCKLIST:
            if blocked in url.lower():
                return CoISeverity.HIGH, f"Source domain matched blocklist: {blocked}"

        return CoISeverity.NONE, None

    def _should_escalate_coi(self, payload: dict) -> bool:
        """Heuristic: decide if we should spend an LLM call on CoI detection."""
        source_type = payload.get("source_type", "unknown")
        if source_type in (SourceType.UNKNOWN.value, SourceType.BLOG.value):
            return True

        text_lower = payload.get("text", "").lower()[:3000]
        promotional_keywords = [
            "buy now", "limited offer", "discount", "sponsored",
            "affiliate", "order today", "exclusive deal", "promo code",
        ]
        return any(kw in text_lower for kw in promotional_keywords)

    def _llm_coi_detection(self, payload: dict) -> tuple[CoISeverity, str]:
        """Use LLM to detect subtle CoI that heuristics can't catch."""
        metadata = {
            k: v for k, v in payload.items()
            if k in ("url", "source_type", "author", "publisher", "title")
        }
        text_snippet = payload.get("text", "")[:2000]

        prompt = COI_DETECTION_PROMPT.format(
            metadata=json.dumps(metadata),
            text_snippet=text_snippet,
        )

        try:
            resp = gemini_service.generate(prompt, use_flash=True)
            parsed = self._safe_json_parse(resp)
            if parsed and parsed.get("has_coi"):
                severity_raw = parsed.get("severity", "low").lower()
                try:
                    severity = CoISeverity(severity_raw)
                except ValueError:
                    severity = CoISeverity.LOW
                return severity, parsed.get("reason", "LLM-detected CoI")
            return CoISeverity.NONE, ""
        except Exception as exc:
            logger.warning("LLM CoI detection failed: %s", exc)
            return CoISeverity.NONE, ""

    def _llm_study_design(self, methods_text: str) -> StudyDesign:
        """Classify research methodology from the methods section with fuzzy mapping guardrail."""
        prompt = STUDY_DESIGN_PROMPT.format(methods_text=methods_text[:3000])

        try:
            resp = gemini_service.generate(prompt, use_flash=True)
            parsed = self._safe_json_parse(resp)
            if parsed:
                design_raw = parsed.get("study_design", "").lower().strip()
                return self._fuzzy_map_study_design(design_raw)
        except Exception as exc:
            logger.warning("LLM study design classification failed: %s", exc)

        return StudyDesign.NOT_APPLICABLE

    @staticmethod
    def _fuzzy_map_study_design(design_str: str) -> StudyDesign:
        """Fuzzy enum mapping guardrail for study design classification."""
        # Clean string from punctuation / parentheticals
        cleaned = re.sub(r"[^\w\s_]", "", design_str).replace(" ", "_")
        
        # 1. Exact or normalized matching
        for sd in StudyDesign:
            if sd.value == cleaned:
                return sd

        # 2. Substring matching as a fallback
        if "meta" in cleaned or "systematic" in cleaned:
            if "review" in cleaned and "systematic" in cleaned:
                return StudyDesign.SYSTEMATIC_REVIEW
            return StudyDesign.META_ANALYSIS
        if "rct" in cleaned or "random" in cleaned:
            return StudyDesign.RCT
        if "cohort" in cleaned:
            return StudyDesign.COHORT
        if "control" in cleaned:
            return StudyDesign.CASE_CONTROL
        if "report" in cleaned or "series" in cleaned:
            return StudyDesign.CASE_REPORT
        if "review" in cleaned:
            return StudyDesign.NARRATIVE_REVIEW
        if "opinion" in cleaned or "editorial" in cleaned or "perspective" in cleaned:
            return StudyDesign.OPINION
            
        return StudyDesign.NOT_APPLICABLE

    def _get_methods_text(
        self, payload: dict, methodological_caveats: list[str]
    ) -> str:
        """Build methods text for study design classification."""
        parts = []
        methods = payload.get("methods", "")
        if methods:
            parts.append(f"Methods section:\n{methods}")

        if methodological_caveats:
            parts.append(
                "Methodological caveats from evidence extraction:\n"
                + "\n".join(f"- {c}" for c in methodological_caveats)
            )

        if not parts:
            text = payload.get("text", "")[:2000]
            if text:
                parts.append(f"Document text:\n{text}")

        return "\n\n".join(parts)

    def _build_caveat_map(self, claims: list[Claim]) -> dict[str, list[str]]:
        """Build doc_id -> [caveat_text, ...] lookup from A3 claims."""
        caveat_map: dict[str, list[str]] = {}
        for claim in claims:
            if claim.claim_type == ClaimType.METHODOLOGICAL_CAVEAT:
                caveat_map.setdefault(claim.source_id, []).append(claim.text)
        return caveat_map

    @staticmethod
    def _safe_json_parse(text: str) -> Optional[dict]:
        """Parse JSON from LLM output, stripping markdown fencing."""
        cleaned = re.sub(r"```json\s*", "", text)
        cleaned = re.sub(r"```\s*$", "", cleaned)
        try:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                return json.loads(match.group())
        except (json.JSONDecodeError, AttributeError):
            pass
        return None
