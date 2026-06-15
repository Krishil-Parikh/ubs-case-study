import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Qdrant
    qdrant_url: str = os.getenv("QDRANT_URL", "https://1e14cac1-d310-42c5-a4a9-78b69a22f909.sa-east-1-0.aws.cloud.qdrant.io:6333")
    qdrant_api_key: str = os.getenv("QDRANT_API_KEY", "")
    qdrant_collection: str = "evidence_store"

    # Gemini
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = "gemini-1.5-pro"
    gemini_flash_model: str = "gemini-1.5-flash"

    # App
    app_name: str = "ERS Evidence Pipeline"
    debug: bool = False
    max_tokens_per_request: int = 8000
    top_k_documents: int = 10

    class Config:
        env_file = ".env"


settings = Settings()
