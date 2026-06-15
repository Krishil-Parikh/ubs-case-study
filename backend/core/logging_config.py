"""Structured logging — JSON to file, coloured readable output to console."""
import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path

from backend.config.settings import settings

_CONFIGURED = False


# ─── Formatters ──────────────────────────────────────────────────────────────

class _JSONFormatter(logging.Formatter):
    """Newline-delimited JSON for log ingestion pipelines."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Any extra= kwargs passed to the logger call
        for key, val in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and not key.startswith("_"):
                payload[key] = val
        return json.dumps(payload, default=str)


class _ConsoleFormatter(logging.Formatter):
    """Human-readable, colour-coded output for terminal."""

    _LEVEL_COLOURS = {
        "DEBUG":    "\033[36m",   # cyan
        "INFO":     "\033[32m",   # green
        "WARNING":  "\033[33m",   # yellow
        "ERROR":    "\033[31m",   # red
        "CRITICAL": "\033[35m",   # magenta
    }
    _RESET = "\033[0m"
    _DIM   = "\033[2m"
    _BOLD  = "\033[1m"

    def format(self, record: logging.LogRecord) -> str:
        colour = self._LEVEL_COLOURS.get(record.levelname, "")
        ts     = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        # Shorten logger name: ers.a8_critique → A8
        short  = record.name.split(".")[-1].upper() if "." in record.name else record.name

        header = (
            f"{self._DIM}[{ts}]{self._RESET} "
            f"{colour}{self._BOLD}[{record.levelname:8}]{self._RESET} "
            f"{self._DIM}[{short:20}]{self._RESET}"
        )
        msg = record.getMessage()

        # Inline key=value extras for readability
        extras = {
            k: v for k, v in record.__dict__.items()
            if k not in logging.LogRecord.__dict__ and not k.startswith("_")
        }
        if extras:
            kv = "  " + "  ".join(f"{self._DIM}{k}{self._RESET}={colour}{v}{self._RESET}" for k, v in extras.items())
        else:
            kv = ""

        lines = [f"{header}  {msg}{kv}"]
        if record.exc_info:
            lines.append(self.formatException(record.exc_info))
        return "\n".join(lines)


# ─── Public API ───────────────────────────────────────────────────────────────

def setup_logging() -> None:
    """Call once at application start-up."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    level = logging.DEBUG if settings.debug else getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)           # capture everything; handlers filter

    # ── Console ──
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(_ConsoleFormatter())
    root.addHandler(console)

    # ── Rotating JSON file ──
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "ers_pipeline.jsonl",
        maxBytes=50 * 1024 * 1024,         # 50 MB
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(_JSONFormatter())
    root.addHandler(file_handler)

    # ── Silence noisy third-party loggers ──
    for lib in ("httpx", "httpcore", "urllib3", "google", "grpc", "asyncio"):
        logging.getLogger(lib).setLevel(logging.WARNING)

    _CONFIGURED = True
    logging.getLogger("ers.logging_config").info("Logging initialised", extra={"level": settings.log_level, "log_dir": str(log_dir)})


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger: ers.<name>"""
    return logging.getLogger(f"ers.{name}")
