"""A3 Evidence Extraction — converts documents into Claim[] with typed annotations."""
import uuid
from backend.models.schemas import Claim, ClaimType
from backend.services.gemini_service import gemini_service


EXTRACTION_PROMPT = """Extract all distinct claims from the document below.
For each claim output JSON with keys: text, claim_type (quantitative|qualitative|hedged|methodological_caveat), confidence (0.0-1.0).
Return a JSON array only.

Document:
{document}
"""


class ExtractionAgent:
    def run(self, documents: list[dict]) -> list[Claim]:
        claims = []
        for doc in documents:
            raw = gemini_service.generate(EXTRACTION_PROMPT.format(document=doc.get("payload", {}).get("text", "")), use_flash=True)
            claims.extend(self._parse(raw, doc["id"]))
        return claims

    def _parse(self, raw: str, source_id: str) -> list[Claim]:
        import json, re
        try:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            items = json.loads(match.group()) if match else []
            return [
                Claim(
                    claim_id=str(uuid.uuid4()),
                    source_id=str(source_id),
                    text=item["text"],
                    claim_type=ClaimType(item.get("claim_type", "qualitative")),
                    confidence=float(item.get("confidence", 0.5)),
                )
                for item in items
            ]
        except Exception:
            return []
