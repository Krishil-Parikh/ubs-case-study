"""A1 Ingestion — GLiNER NER, PII redaction, injection filter, token budget, deduplication."""
from backend.models.schemas import PipelineRequest


class IngestionAgent:
    def run(self, request: PipelineRequest) -> dict:
        query = self._redact_pii(request.query)
        query = self._filter_injection(query)
        self._enforce_token_budget(query)
        return {"clean_query": query, "session_id": request.session_id}

    def _redact_pii(self, text: str) -> str:
        # TODO: integrate GLiNER for NER-based PII detection
        return text

    def _filter_injection(self, text: str) -> str:
        # TODO: prompt injection pattern matching
        return text

    def _enforce_token_budget(self, text: str):
        # TODO: count tokens and raise if over budget
        pass
