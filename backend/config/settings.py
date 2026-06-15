import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Qdrant
    qdrant_url: str = os.getenv(
        "QDRANT_URL",
        "https://1e14cac1-d310-42c5-a4a9-78b69a22f909.sa-east-1-0.aws.cloud.qdrant.io:6333",
    )
    qdrant_api_key: str = os.getenv("QDRANT_API_KEY", "")
    qdrant_collection: str = "evidence_store"

    # Gemini
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = "gemini-1.5-pro"
    gemini_flash_model: str = "gemini-1.5-flash"
    gemini_temperature: float = 0.2
    gemini_max_output_tokens: int = 4096
    gemini_max_retries: int = 3

    # App
    app_name: str = "ERS Evidence Pipeline"
    debug: bool = False
    max_tokens_per_request: int = 8000
    top_k_documents: int = 10

    # Logging
    log_level: str = "INFO"
    log_dir: str = "logs"

    # Phase 5 — ERS formula weights
    ers_weight_source: float = 0.45
    ers_weight_consensus: float = 0.35
    ers_weight_retrieval: float = 0.20

    # Phase 5 — ERS penalty caps
    ers_contradiction_penalty_per_hard: float = 0.10
    ers_contradiction_penalty_per_partial: float = 0.05
    ers_contradiction_penalty_cap: float = 0.30
    ers_applicability_penalty_cap: float = 0.20
    ers_uncertainty_penalty_per_item: float = 0.03
    ers_uncertainty_penalty_cap: float = 0.15

    # Phase 5 — INSUFFICIENT_EVIDENCE thresholds
    insufficient_min_claims: int = 2
    insufficient_reliability_ceiling: float = 0.4

    class Config:
        env_file = ".env"


settings = Settings()
