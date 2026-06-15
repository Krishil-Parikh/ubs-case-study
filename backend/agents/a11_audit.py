"""A11 Audit — async post-processing, writes full trace to PostgreSQL + LangSmith."""
import asyncio
import uuid
from datetime import datetime
from backend.models.schemas import PipelineResponse


class AuditAgent:
    async def run(self, request_query: str, response: PipelineResponse, trace_id: str | None = None):
        trace_id = trace_id or str(uuid.uuid4())
        record = {
            "trace_id": trace_id,
            "timestamp": datetime.utcnow().isoformat(),
            "query": request_query,
            "ers_score": response.ers.score,
            "ers_band": response.ers.band.value,
            "insufficient_evidence": response.insufficient_evidence,
            "claim_count": len(response.claims),
            "contradiction_count": len(response.contradiction_graph.edges),
        }
        await asyncio.gather(
            self._write_postgres(record, response),
            self._write_langsmith(record, response),
        )
        return trace_id

    async def _write_postgres(self, record: dict, response: PipelineResponse):
        # TODO: asyncpg INSERT into audit_traces table
        pass

    async def _write_langsmith(self, record: dict, response: PipelineResponse):
        # TODO: LangSmith client trace logging
        pass
