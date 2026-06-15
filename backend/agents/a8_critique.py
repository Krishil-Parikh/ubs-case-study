"""A8 Critique/Skeptic — four fixed lenses, authority to emit INSUFFICIENT_EVIDENCE."""
from backend.models.schemas import (
    Claim, ReliabilityScore, ContradictionGraph, ApplicabilityReport
)
from backend.services.gemini_service import gemini_service

CRITIQUE_PROMPT = """You are an adversarial evidence critic. Evaluate the evidence using FOUR lenses:
1. SOURCE ATTACK — are sources reliable, peer-reviewed, free of conflict of interest?
2. SCOPE/APPLICABILITY ATTACK — does evidence apply to the specific question context?
3. COMPLETENESS ATTACK — is there missing evidence, publication bias, or important omissions?
4. CONVERGENCE ATTACK — does apparent consensus reflect genuine agreement or correlated sources?

If evidence is too weak to support any conclusion, emit INSUFFICIENT_EVIDENCE=true.

Claims: {claims}
Reliability Scores: {reliability}
Contradiction Graph: {contradictions}
Applicability Report: {applicability}

Return JSON: {{
  "source_attack": "...",
  "scope_attack": "...",
  "completeness_attack": "...",
  "convergence_attack": "...",
  "insufficient_evidence": bool,
  "adjusted_reliability": float (0.0-1.0),
  "adjusted_consensus": float (0.0-1.0),
  "key_uncertainties": ["..."]
}}
"""


class CritiqueAgent:
    def run(
        self,
        claims: list[Claim],
        reliability: list[ReliabilityScore],
        contradiction_graph: ContradictionGraph,
        applicability: ApplicabilityReport,
    ) -> dict:
        import json, re
        prompt = CRITIQUE_PROMPT.format(
            claims=[c.model_dump() for c in claims[:20]],
            reliability=[r.model_dump() for r in reliability],
            contradictions=contradiction_graph.model_dump(),
            applicability=applicability.model_dump(),
        )
        raw = gemini_service.generate(prompt)
        try:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            return json.loads(match.group()) if match else self._fallback()
        except Exception:
            return self._fallback()

    def _fallback(self) -> dict:
        return {
            "source_attack": "",
            "scope_attack": "",
            "completeness_attack": "",
            "convergence_attack": "",
            "insufficient_evidence": False,
            "adjusted_reliability": 0.5,
            "adjusted_consensus": 0.5,
            "key_uncertainties": [],
        }
