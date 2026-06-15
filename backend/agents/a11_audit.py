"""
A11 Audit — async post-processing, writes full trace to rotating .log files.

Replaces PostgreSQL/LangSmith stubs with a simple, always-working file audit.
Two files are written:
  logs/audit_summary.log   — one-line JSON per request (fast tail/grep)
  logs/audit_full.log      — full PipelineResponse JSON (replay / debugging)

Both files rotate at 50 MB, keeping 10 backups each.
"""

from __future__ import annotations

import asyncio
import json
import logging
import logging.handlers
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config.settings import settings
from backend.models.schemas import PipelineResponse

# ─── Set up two dedicated rotating file handlers ──────────────────────────────

_LOG_DIR = Path(settings.log_dir)
_LOG_DIR.mkdir(parents=True, exist_ok=True)

def _make_handler(filename: str) -> logging.handlers.RotatingFileHandler:
    h = logging.handlers.RotatingFileHandler(
        _LOG_DIR / filename,
        maxBytes   = 50 * 1024 * 1024,  # 50 MB
        backupCount= 10,
        encoding   = "utf-8",
    )
    h.setFormatter(logging.Formatter("%(message)s"))  # raw JSON lines
    return h

_summary_logger = logging.getLogger("ers.audit.summary")
_summary_logger.setLevel(logging.INFO)
_summary_logger.propagate = False          # don't bubble to root
_summary_logger.addHandler(_make_handler("audit_summary.log"))

_full_logger = logging.getLogger("ers.audit.full")
_full_logger.setLevel(logging.INFO)
_full_logger.propagate = False
_full_logger.addHandler(_make_handler("audit_full.log"))

# Main agent logger (goes to the normal pipeline log)
from backend.core.logging_config import get_logger
logger = get_logger("a11_audit")


# ─── Agent ────────────────────────────────────────────────────────────────────

class AuditAgent:
    """
    A11 — fire-and-forget audit logger.

    Writes two records per pipeline run:
      1. Summary line  → audit_summary.log  (timestamp, trace_id, ERS, claim count, …)
      2. Full record   → audit_full.log     (entire PipelineResponse JSON)

    Never raises — any failure is logged to the main pipeline log and swallowed.
    """

    async def run(
        self,
        request_query: str,
        response: PipelineResponse,
        trace_id: str | None = None,
    ) -> str:
        trace_id = trace_id or str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()

        try:
            await asyncio.gather(
                asyncio.to_thread(self._write_summary, trace_id, ts, request_query, response),
                asyncio.to_thread(self._write_full,    trace_id, ts, request_query, response),
            )
            logger.info(
                "A11 audit written",
                extra={
                    "trace_id":  trace_id,
                    "ers_score": response.ers.score,
                    "ers_band":  response.ers.band.value,
                },
            )
        except Exception as exc:
            logger.error("A11 audit failed (non-fatal)", extra={"error": str(exc)})

        return trace_id

    # ── Writers (run in threads so they don't block the event loop) ───────────

    def _write_summary(
        self,
        trace_id: str,
        ts: str,
        query: str,
        response: PipelineResponse,
    ) -> None:
        record: dict[str, Any] = {
            "trace_id":            trace_id,
            "timestamp":           ts,
            "query_preview":       query[:120],
            "ers_score":           response.ers.score,
            "ers_band":            response.ers.band.value,
            "insufficient":        response.insufficient_evidence,
            "claim_count":         len(response.claims),
            "contradiction_count": len(response.contradiction_graph.edges),
            "uncertainty_count":   len(response.uncertainties),
            "formula_trace":       response.ers.formula_trace,
        }
        if response.critique:
            record["critique_severity"] = response.critique.overall_severity.value
        _summary_logger.info(json.dumps(record, default=str))

    def _write_full(
        self,
        trace_id: str,
        ts: str,
        query: str,
        response: PipelineResponse,
    ) -> None:
        record: dict[str, Any] = {
            "trace_id":  trace_id,
            "timestamp": ts,
            "query":     query,
            "response":  response.model_dump(mode="json"),
        }
        _full_logger.info(json.dumps(record, default=str))
