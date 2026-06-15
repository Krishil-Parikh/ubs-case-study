"""Gemini LLM service — Pro/Flash generation, embeddings, retry logic, JSON mode."""
import time
from typing import Optional

import google.generativeai as genai

from backend.config.settings import settings
from backend.core.logging_config import get_logger

logger = get_logger("gemini_service")


class GeminiService:
    """
    Thin wrapper around the google-generativeai SDK.

    Provides:
    - Pro and Flash generation with automatic retry + exponential backoff
    - JSON-mode generation (response_mime_type=application/json)
    - Scoped models with system instructions (for A8)
    - Text embeddings via embedding-001
    """

    _RETRY_DELAYS = [1.0, 3.0, 7.0]   # seconds between attempts 1→2, 2→3, 3→fail

    def __init__(self) -> None:
        genai.configure(api_key=settings.gemini_api_key)

        self._base_config = genai.GenerationConfig(
            temperature=settings.gemini_temperature,
            max_output_tokens=settings.gemini_max_output_tokens,
        )
        self._json_config = genai.GenerationConfig(
            temperature=settings.gemini_temperature,
            max_output_tokens=settings.gemini_max_output_tokens,
            response_mime_type="application/json",
        )

        self.pro   = genai.GenerativeModel(settings.gemini_model,   generation_config=self._base_config)
        self.flash = genai.GenerativeModel(settings.gemini_flash_model, generation_config=self._base_config)

        logger.info(
            "GeminiService ready",
            extra={"pro": settings.gemini_model, "flash": settings.gemini_flash_model},
        )

    # ── Public generation API ─────────────────────────────────────────────────

    def generate(self, prompt: str, *, use_flash: bool = False) -> str:
        """Generate text with retry.  Returns the response string."""
        model = self.flash if use_flash else self.pro
        return self._call(model, prompt, config=self._base_config, label="generate")

    def generate_json(self, prompt: str, *, use_flash: bool = False) -> str:
        """
        Generate text in JSON mode (response_mime_type=application/json).
        Gemini will enforce valid JSON output — use for structured extraction.
        """
        model = self.flash if use_flash else self.pro
        return self._call(model, prompt, config=self._json_config, label="generate_json")

    def build_model_with_system(
        self,
        system_instruction: str,
        *,
        use_flash: bool = False,
        json_mode: bool = True,
    ) -> genai.GenerativeModel:
        """
        Return a model instance that carries a permanent system instruction.
        Used by A8 so the adversarial persona is anchored at model level.
        """
        model_name = settings.gemini_flash_model if use_flash else settings.gemini_model
        config     = self._json_config if json_mode else self._base_config
        return genai.GenerativeModel(
            model_name          = model_name,
            system_instruction  = system_instruction,
            generation_config   = config,
        )

    def embed(self, text: str) -> list[float]:
        """Return a 768-dim embedding via embedding-001."""
        start = time.perf_counter()
        try:
            result = genai.embed_content(
                model     = "models/embedding-001",
                content   = text,
                task_type = "retrieval_document",
            )
            elapsed = time.perf_counter() - start
            logger.debug("embed OK", extra={"chars": len(text), "elapsed_ms": round(elapsed * 1000)})
            return result["embedding"]
        except Exception as exc:
            logger.error("embed FAILED", extra={"error": str(exc)})
            raise

    # ── Internal ──────────────────────────────────────────────────────────────

    def _call(
        self,
        model: genai.GenerativeModel,
        prompt: str,
        config: genai.GenerationConfig,
        label: str,
    ) -> str:
        """Call Gemini with exponential-backoff retry."""
        last_exc: Optional[Exception] = None
        for attempt in range(settings.gemini_max_retries):
            try:
                start    = time.perf_counter()
                response = model.generate_content(prompt, generation_config=config)
                elapsed  = time.perf_counter() - start
                text     = response.text
                logger.debug(
                    f"Gemini {label} OK",
                    extra={
                        "attempt": attempt + 1,
                        "elapsed_ms": round(elapsed * 1000),
                        "output_chars": len(text),
                    },
                )
                return text
            except Exception as exc:
                last_exc = exc
                delay    = self._RETRY_DELAYS[min(attempt, len(self._RETRY_DELAYS) - 1)]
                logger.warning(
                    f"Gemini {label} failed — retrying in {delay}s",
                    extra={"attempt": attempt + 1, "error": str(exc)},
                )
                if attempt < settings.gemini_max_retries - 1:
                    time.sleep(delay)

        logger.error(
            f"Gemini {label} exhausted retries",
            extra={"error": str(last_exc)},
        )
        raise RuntimeError(f"Gemini {label} failed after {settings.gemini_max_retries} attempts: {last_exc}") from last_exc


gemini_service = GeminiService()
