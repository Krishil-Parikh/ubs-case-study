"""A10 Response Agent — Phase 6 Output.

Assembles the final structured output: synthesized answer, ERS band,
support map, contradictions manifest, uncertainties list, and
INSUFFICIENT_EVIDENCE flag.  Adapts tone and hedging based on ERS band.
"""
import json
import re
from backend.models.schemas import (
    Claim,
    ReliabilityScore,
    ERSResult,
    ERSBand,
    ContradictionGraph,
    ContradictionEdge,
    ApplicabilityReport,
    RelationType,
    PipelineResponse,
    SupportMapEntry,
    ContradictionManifestEntry,
    UncertaintyEntry,
    UncertaintyCategory,
    AnswerSection,
    ResponseMetadata,
)
from backend.services.gemini_service import gemini_service


# ── System prompts (ERS-adaptive) ───────────────────────────────────────

SYSTEM_PROMPT_BASE = """You are the Response Agent of the ERS Evidence Pipeline.
Your role is to synthesize evidence into a structured, honest, and defensible answer.

RULES:
1. Ground every statement in the provided claims. Use inline citations like [1], [2], etc.
   Each number corresponds to the claim index in the claims list (1-indexed).
2. NEVER fabricate information or go beyond the evidence provided.
3. Explicitly acknowledge contradictions — do not hide conflicting evidence.
4. When evidence is hedged or has methodological caveats, reflect that uncertainty in your language.
5. Structure your answer in clear sections with headings.
6. End with a "Limitations & Uncertainties" section summarizing key gaps.
"""

TONE_HIGH = """CONFIDENCE LEVEL: HIGH (ERS ≥ 0.70)
The evidence is strong and largely convergent. Write with appropriate confidence,
but still cite sources and note any minor caveats."""

TONE_MEDIUM = """CONFIDENCE LEVEL: MEDIUM (ERS 0.40–0.69)
The evidence is mixed or has notable gaps. Use hedged language ("evidence suggests",
"based on available data", "findings indicate but are not conclusive").
Clearly separate well-supported claims from weaker ones."""

TONE_LOW = """CONFIDENCE LEVEL: LOW (ERS < 0.40)
The evidence is weak, contradictory, or largely inapplicable. Use strongly hedged
language throughout. Emphasize what is NOT known. Recommend the user seek
additional authoritative sources before acting on this information."""

INSUFFICIENT_PROMPT = """CRITICAL: The evidence is INSUFFICIENT to support any conclusion.

The upstream Critique Agent has determined that the available evidence cannot
support a reliable answer to this question. Explain WHY the evidence is
insufficient using the critique findings below, and recommend what types of
evidence would be needed to answer this question properly.

Critique findings:
{critique_summary}
"""

ANSWER_PROMPT = """{system_prompt}

{tone}

Question: {question}

Evidence Claims (use [N] citations, 1-indexed):
{claims_formatted}

Contradictions Detected:
{contradictions_formatted}

Applicability Issues:
{applicability_formatted}

Key Uncertainties:
{uncertainties_formatted}

{insufficient_block}

Respond with a multi-section answer. Use markdown headings (##) for sections.
Your FINAL section MUST be "## Limitations & Uncertainties".
"""


# ── Agent class ─────────────────────────────────────────────────────────


class ResponseAgent:
    """A10 — assembles the final structured pipeline output."""

    def run(
        self,
        query: str,
        claims: list[Claim],
        ers: ERSResult,
        contradiction_graph: ContradictionGraph,
        applicability_report: ApplicabilityReport,
        uncertainties: list[str],
        insufficient_evidence: bool,
        reliability: list[ReliabilityScore] | None = None,
        critique: dict | None = None,
        session_id: str | None = None,
    ) -> PipelineResponse:
        """Run the full output assembly pipeline."""

        # 1. Generate the synthesized answer (LLM call)
        answer = self._generate_answer(
            query, claims, ers, contradiction_graph,
            applicability_report, uncertainties,
            insufficient_evidence, critique,
        )

        # 2. Parse answer into sections
        answer_sections = self._parse_answer_sections(answer, claims)

        # 3. Build the support map (claim → answer mapping)
        support_map = self._build_support_map(claims, answer, reliability)

        # 4. Build the contradictions manifest
        contradictions_manifest = self._build_contradictions_manifest(
            contradiction_graph, claims,
        )

        # 5. Structure the uncertainties
        structured_uncertainties = self._structure_uncertainties(
            uncertainties, critique,
        )

        # 6. Assemble metadata
        metadata = ResponseMetadata(
            source_count=len(set(c.source_id for c in claims)),
            claim_count=len(claims),
            contradiction_count=len(contradiction_graph.edges),
            applicability_flags_count=len(applicability_report.flags),
            insufficient_evidence=insufficient_evidence,
            ers_band=ers.band.value,
        )

        return PipelineResponse(
            answer=answer,
            ers=ers,
            claims=claims,
            contradiction_graph=contradiction_graph,
            applicability_report=applicability_report,
            uncertainties=uncertainties,
            insufficient_evidence=insufficient_evidence,
            session_id=session_id,
            answer_sections=answer_sections,
            support_map=support_map,
            contradictions_manifest=contradictions_manifest,
            structured_uncertainties=structured_uncertainties,
            metadata=metadata,
        )

    # ── Answer generation ───────────────────────────────────────────────

    def _generate_answer(
        self,
        query: str,
        claims: list[Claim],
        ers: ERSResult,
        contradiction_graph: ContradictionGraph,
        applicability_report: ApplicabilityReport,
        uncertainties: list[str],
        insufficient_evidence: bool,
        critique: dict | None,
    ) -> str:
        """Build the ERS-adaptive prompt and call the LLM."""

        # Select tone based on ERS band
        tone = {
            ERSBand.HIGH: TONE_HIGH,
            ERSBand.MEDIUM: TONE_MEDIUM,
            ERSBand.LOW: TONE_LOW,
        }.get(ers.band, TONE_MEDIUM)

        # Format claims with indices for citation
        claims_formatted = self._format_claims_for_prompt(claims)

        # Format contradictions
        contradictions_formatted = self._format_contradictions_for_prompt(
            contradiction_graph, claims,
        )

        # Format applicability
        applicability_formatted = self._format_applicability_for_prompt(
            applicability_report,
        )

        # Format uncertainties
        uncertainties_formatted = (
            "\n".join(f"- {u}" for u in uncertainties)
            if uncertainties else "None identified."
        )

        # Insufficient evidence block
        insufficient_block = ""
        if insufficient_evidence:
            critique_summary = ""
            if critique:
                critique_summary = (
                    f"Source Attack: {critique.get('source_attack', 'N/A')}\n"
                    f"Scope Attack: {critique.get('scope_attack', 'N/A')}\n"
                    f"Completeness Attack: {critique.get('completeness_attack', 'N/A')}\n"
                    f"Convergence Attack: {critique.get('convergence_attack', 'N/A')}"
                )
            insufficient_block = INSUFFICIENT_PROMPT.format(
                critique_summary=critique_summary or "No detailed critique available.",
            )

        prompt = ANSWER_PROMPT.format(
            system_prompt=SYSTEM_PROMPT_BASE,
            tone=tone,
            question=query,
            claims_formatted=claims_formatted,
            contradictions_formatted=contradictions_formatted,
            applicability_formatted=applicability_formatted,
            uncertainties_formatted=uncertainties_formatted,
            insufficient_block=insufficient_block,
        )

        return gemini_service.generate(prompt)

    # ── Claims formatting ───────────────────────────────────────────────

    def _format_claims_for_prompt(self, claims: list[Claim]) -> str:
        """Format claims as a numbered list with type and confidence annotations."""
        if not claims:
            return "No evidence claims available."
        lines = []
        for i, c in enumerate(claims[:20], start=1):  # Cap at 20 for token budget
            type_label = c.claim_type.value.upper()
            conf_label = (
                "high" if c.confidence >= 0.7
                else "moderate" if c.confidence >= 0.4
                else "low"
            )
            lines.append(
                f"[{i}] ({type_label}, confidence: {conf_label}) "
                f"{c.text}  [source: {c.source_id}]"
            )
        return "\n".join(lines)

    def _format_contradictions_for_prompt(
        self, graph: ContradictionGraph, claims: list[Claim],
    ) -> str:
        """Format contradictions as human-readable pairs."""
        if not graph.edges:
            return "No contradictions detected."
        claim_map = {c.claim_id: c.text for c in claims}
        lines = []
        for edge in graph.edges:
            a_text = claim_map.get(edge.claim_a_id, "Unknown claim")[:100]
            b_text = claim_map.get(edge.claim_b_id, "Unknown claim")[:100]
            lines.append(
                f"- {edge.relation.value}: \"{a_text}\" vs \"{b_text}\"\n"
                f"  Explanation: {edge.explanation}"
            )
        return "\n".join(lines)

    def _format_applicability_for_prompt(
        self, report: ApplicabilityReport,
    ) -> str:
        """Format applicability flags for the prompt."""
        if not report.flags:
            return "No applicability issues."
        issues = []
        for flag in report.flags:
            problems = []
            if not flag.population_match:
                problems.append("population mismatch")
            if not flag.timeframe_match:
                problems.append("timeframe mismatch")
            if not flag.outcome_match:
                problems.append("outcome mismatch")
            if problems:
                reason = flag.flag_reason or ", ".join(problems)
                issues.append(f"- Source {flag.source_id}: {reason}")
        return "\n".join(issues) if issues else "All sources applicable."

    # ── Answer section parsing ──────────────────────────────────────────

    def _parse_answer_sections(
        self, answer: str, claims: list[Claim],
    ) -> list[AnswerSection]:
        """Parse the markdown answer into discrete AnswerSection objects."""
        # Split on ## headings
        sections_raw = re.split(r"(?m)^##\s+", answer)
        sections = []

        for raw_section in sections_raw:
            raw_section = raw_section.strip()
            if not raw_section:
                continue

            # Extract heading (first line) and content (rest)
            lines = raw_section.split("\n", 1)
            heading = lines[0].strip()
            content = lines[1].strip() if len(lines) > 1 else ""

            # Extract cited claim IDs from [N] references
            citation_indices = [
                int(m) for m in re.findall(r"\[(\d+)\]", raw_section)
            ]
            cited_claim_ids = []
            for idx in citation_indices:
                if 1 <= idx <= len(claims):
                    cited_claim_ids.append(claims[idx - 1].claim_id)

            sections.append(AnswerSection(
                heading=heading,
                content=content,
                cited_claim_ids=list(set(cited_claim_ids)),
            ))

        return sections

    # ── Support map construction ────────────────────────────────────────

    def _build_support_map(
        self,
        claims: list[Claim],
        answer: str,
        reliability: list[ReliabilityScore] | None,
    ) -> list[SupportMapEntry]:
        """Build a map of which claims support the answer.

        Uses citation extraction from the answer text plus reliability
        scores to compute a relevance score for each supporting claim.
        """
        reliability_map = {}
        if reliability:
            reliability_map = {r.source_id: r.score for r in reliability}

        # Find all [N] citations in the answer
        cited_indices = set(int(m) for m in re.findall(r"\[(\d+)\]", answer))

        # Split answer into sections to determine answer_section_index
        sections_raw = re.split(r"(?m)^##\s+", answer)
        # Build index map: citation number → section index
        citation_section_map: dict[int, int] = {}
        for sec_idx, section_text in enumerate(sections_raw):
            for m in re.findall(r"\[(\d+)\]", section_text):
                citation_section_map[int(m)] = sec_idx

        support_map = []
        for idx in sorted(cited_indices):
            if 1 <= idx <= len(claims):
                claim = claims[idx - 1]
                rel_score = reliability_map.get(claim.source_id, 0.5)
                # Relevance = blend of claim confidence and source reliability
                relevance = round(
                    0.6 * claim.confidence + 0.4 * rel_score, 3,
                )
                support_map.append(SupportMapEntry(
                    claim_id=claim.claim_id,
                    source_id=claim.source_id,
                    supporting_text=claim.text[:200],
                    relevance_score=relevance,
                    answer_section_index=citation_section_map.get(idx, 0),
                ))

        return support_map

    # ── Contradictions manifest ─────────────────────────────────────────

    def _build_contradictions_manifest(
        self,
        graph: ContradictionGraph,
        claims: list[Claim],
    ) -> list[ContradictionManifestEntry]:
        """Transform ContradictionGraph edges into human-readable manifest entries."""
        claim_map = {c.claim_id: c for c in claims}
        manifest = []

        for edge in graph.edges:
            claim_a = claim_map.get(edge.claim_a_id)
            claim_b = claim_map.get(edge.claim_b_id)
            if not claim_a or not claim_b:
                continue

            # Determine severity based on relation type and claim confidence
            severity = self._compute_contradiction_severity(edge, claim_a, claim_b)

            manifest.append(ContradictionManifestEntry(
                claim_a_text=claim_a.text[:300],
                claim_b_text=claim_b.text[:300],
                relation=edge.relation,
                explanation=edge.explanation,
                severity=severity,
            ))

        return manifest

    def _compute_contradiction_severity(
        self,
        edge: ContradictionEdge,
        claim_a: Claim,
        claim_b: Claim,
    ) -> str:
        """Compute severity: high if both claims are high-confidence and
        directly contradicting, low for partial contradictions between
        low-confidence claims."""
        avg_confidence = (claim_a.confidence + claim_b.confidence) / 2

        if edge.relation == RelationType.CONTRADICTS:
            if avg_confidence >= 0.7:
                return "high"
            elif avg_confidence >= 0.4:
                return "moderate"
            else:
                return "low"
        elif edge.relation == RelationType.PARTIAL_CONTRADICTION:
            if avg_confidence >= 0.7:
                return "moderate"
            else:
                return "low"
        return "low"

    # ── Uncertainty structuring ─────────────────────────────────────────

    def _structure_uncertainties(
        self,
        uncertainties: list[str],
        critique: dict | None,
    ) -> list[UncertaintyEntry]:
        """Convert raw uncertainty strings into structured UncertaintyEntry objects.

        Uses keyword heuristics to categorize and assess impact.
        """
        entries = []

        for u in uncertainties:
            category = self._classify_uncertainty_category(u)
            impact = self._assess_uncertainty_impact(u, critique)
            entries.append(UncertaintyEntry(
                description=u,
                category=category,
                impact_level=impact,
            ))

        return entries

    def _classify_uncertainty_category(self, text: str) -> UncertaintyCategory:
        """Classify an uncertainty string into a category using keyword matching."""
        text_lower = text.lower()

        if any(kw in text_lower for kw in ["population", "demographic", "age group", "cohort"]):
            return UncertaintyCategory.POPULATION
        if any(kw in text_lower for kw in ["method", "design", "sample size", "rct", "blinding"]):
            return UncertaintyCategory.METHODOLOGY
        if any(kw in text_lower for kw in ["scope", "context", "generalizab", "external validity"]):
            return UncertaintyCategory.SCOPE
        if any(kw in text_lower for kw in ["time", "date", "recen", "outdated", "temporal"]):
            return UncertaintyCategory.TEMPORAL
        # Default: data gap
        return UncertaintyCategory.DATA_GAP

    def _assess_uncertainty_impact(
        self, text: str, critique: dict | None,
    ) -> str:
        """Assess impact level of an uncertainty.

        If the critique flagged insufficient evidence, all uncertainties
        are elevated to high impact.
        """
        if critique and critique.get("insufficient_evidence"):
            return "high"

        text_lower = text.lower()
        if any(kw in text_lower for kw in [
            "no evidence", "no data", "completely unknown", "critical",
            "fundamental", "cannot determine",
        ]):
            return "high"
        if any(kw in text_lower for kw in [
            "limited", "insufficient", "unclear", "conflicting",
            "small sample",
        ]):
            return "moderate"
        return "low"
