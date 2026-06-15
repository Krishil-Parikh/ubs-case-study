"""A4 Reliability — deterministic source-type + recency scoring, LLM escalation for CoI/study-design edge cases."""
from backend.models.schemas import Claim, ReliabilityScore
from backend.services.gemini_service import gemini_service


SOURCE_TYPE_SCORES = {
    "systematic_review": 1.0,
    "rct": 0.9,
    "cohort": 0.75,
    "case_control": 0.65,
    "expert_opinion": 0.4,
    "unknown": 0.3,
}


class ReliabilityAgent:
    def run(self, documents: list[dict]) -> list[ReliabilityScore]:
        scores = []
        for doc in documents:
            payload = doc.get("payload", {})
            source_type = payload.get("source_type", "unknown")
            year = int(payload.get("year", 2020))
            recency = max(0.0, 1.0 - (2025 - year) * 0.05)
            base_score = SOURCE_TYPE_SCORES.get(source_type, 0.3)
            escalated = False
            reason = None
            if payload.get("conflict_of_interest") or source_type == "unknown":
                base_score, reason = self._llm_escalate(doc)
                escalated = True
            scores.append(ReliabilityScore(
                source_id=str(doc["id"]),
                score=round((base_score + recency) / 2, 3),
                source_type=source_type,
                recency_score=recency,
                llm_escalated=escalated,
                escalation_reason=reason,
            ))
        return scores

    def _llm_escalate(self, doc: dict) -> tuple[float, str]:
        prompt = f"Rate source reliability 0.0-1.0 and explain briefly. Source metadata: {doc.get('payload', {})}"
        try:
            resp = gemini_service.generate(prompt, use_flash=True)
            import re
            match = re.search(r"(\d\.\d+)", resp)
            score = float(match.group()) if match else 0.4
            return min(score, 1.0), resp[:200]
        except Exception:
            return 0.4, "LLM escalation failed"
