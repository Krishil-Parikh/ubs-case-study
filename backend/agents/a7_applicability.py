"""A7 Applicability — checks question population vs. evidence population, timeframe, outcome."""
from backend.models.schemas import ApplicabilityFlag, ApplicabilityReport
from backend.services.gemini_service import gemini_service

APPLICABILITY_PROMPT = """Given the user question and a source document, assess applicability on three dimensions.
Return JSON: {{"population_match": bool, "timeframe_match": bool, "outcome_match": bool, "flag_reason": "..."}}

Question: {question}
Source: {source}
"""


class ApplicabilityAgent:
    def run(self, query: str, documents: list[dict]) -> ApplicabilityReport:
        import json, re
        flags = []
        for doc in documents:
            prompt = APPLICABILITY_PROMPT.format(
                question=query,
                source=doc.get("payload", {}).get("text", "")[:500],
            )
            try:
                raw = gemini_service.generate(prompt, use_flash=True)
                match = re.search(r"\{.*\}", raw, re.DOTALL)
                data = json.loads(match.group()) if match else {}
                flags.append(ApplicabilityFlag(
                    source_id=str(doc["id"]),
                    population_match=bool(data.get("population_match", True)),
                    timeframe_match=bool(data.get("timeframe_match", True)),
                    outcome_match=bool(data.get("outcome_match", True)),
                    flag_reason=data.get("flag_reason"),
                ))
            except Exception:
                flags.append(ApplicabilityFlag(source_id=str(doc["id"]), population_match=True, timeframe_match=True, outcome_match=True))
        overall = all(f.population_match and f.timeframe_match and f.outcome_match for f in flags)
        return ApplicabilityReport(flags=flags, overall_applicable=overall)
