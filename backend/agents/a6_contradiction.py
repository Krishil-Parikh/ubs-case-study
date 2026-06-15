"""A6 Contradiction — similarity-filtered pairs → LLM classification for logical conflicts only."""
import numpy as np
from backend.models.schemas import Claim, ContradictionEdge, ContradictionGraph, RelationType
from backend.services.gemini_service import gemini_service

SIMILARITY_THRESHOLD = 0.8

CLASSIFY_PROMPT = """Two claims are provided. Classify their relationship as one of:
SUPPORTS, CONTRADICTS, PARTIAL_CONTRADICTION, NOT_COMPARABLE.
Only classify as CONTRADICTS or PARTIAL_CONTRADICTION if there is a genuine logical conflict — not a population or scope mismatch.
Return JSON: {{"relation": "...", "explanation": "..."}}

Claim A: {claim_a}
Claim B: {claim_b}
"""


class ContradictionAgent:
    def run(self, claims: list[Claim]) -> ContradictionGraph:
        if len(claims) < 2:
            return ContradictionGraph()
        embeddings = {c.claim_id: gemini_service.embed(c.text) for c in claims}
        edges = []
        claim_list = list(claims)
        for i in range(len(claim_list)):
            for j in range(i + 1, len(claim_list)):
                ca, cb = claim_list[i], claim_list[j]
                sim = self._cosine(embeddings[ca.claim_id], embeddings[cb.claim_id])
                if sim >= SIMILARITY_THRESHOLD:
                    edge = self._classify(ca, cb)
                    if edge:
                        edges.append(edge)
        return ContradictionGraph(edges=edges)

    def _cosine(self, a: list[float], b: list[float]) -> float:
        a_, b_ = np.array(a), np.array(b)
        return float(np.dot(a_, b_) / (np.linalg.norm(a_) * np.linalg.norm(b_) + 1e-9))

    def _classify(self, ca: Claim, cb: Claim) -> ContradictionEdge | None:
        import json, re
        prompt = CLASSIFY_PROMPT.format(claim_a=ca.text, claim_b=cb.text)
        try:
            raw = gemini_service.generate(prompt, use_flash=True)
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            data = json.loads(match.group()) if match else {}
            return ContradictionEdge(
                claim_a_id=ca.claim_id,
                claim_b_id=cb.claim_id,
                relation=RelationType(data.get("relation", "NOT_COMPARABLE")),
                explanation=data.get("explanation", ""),
            )
        except Exception:
            return None
