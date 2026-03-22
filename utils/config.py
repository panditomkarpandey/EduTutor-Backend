"""
Environment Configuration Validator
=====================================
Called at startup to validate all required environment variables.
Fails fast with a clear error message rather than crashing at runtime.

Usage (in main.py lifespan):
    from utils.config import validate_config, settings
    validate_config()
"""

import sys
import logging
from pydantic import field_validator
from pydantic_settings import BaseSettings

log = logging.getLogger("config")


class Settings(BaseSettings):
    """All application settings with validation and defaults."""

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "education_tutor"

    # JWT
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION"
    jwt_expire_minutes: int = 1440

    # Groq / LLM
    groq_api_key: str = ""
    groq_model: str = "llama3-8b-8192"
    llm_timeout: int = 120

    # RAG tuning
    top_k_chunks: int = 10
    max_context_tokens: int = 1500
    prune_similarity: float = 0.45
    similarity_threshold: float = 0.35

    # File upload
    max_pdf_size_mb: int = 50

    # Security
    allowed_origins: str = "http://localhost"

    # Seeding
    seed_admin_email: str = "admin@edututor.in"
    seed_admin_pass: str = "Admin@123"

    # Logging
    log_level: str = "INFO"
    log_format: str = "console"

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if v in ("CHANGE_ME_IN_PRODUCTION", "change-this-in-production-please", ""):
            log.warning(
                "⚠️  JWT_SECRET_KEY is using default value. "
                "Set a strong secret in production!"
            )
        if len(v) < 16:
            raise ValueError("JWT_SECRET_KEY must be at least 16 characters")
        return v

    @field_validator("prune_similarity", "similarity_threshold")
    @classmethod
    def validate_float_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("Similarity values must be between 0.0 and 1.0")
        return v

    @field_validator("top_k_chunks")
    @classmethod
    def validate_top_k(cls, v: int) -> int:
        if not 1 <= v <= 50:
            raise ValueError("TOP_K_CHUNKS must be between 1 and 50")
        return v

    @field_validator("max_context_tokens")
    @classmethod
    def validate_context_tokens(cls, v: int) -> int:
        if not 100 <= v <= 8000:
            raise ValueError("MAX_CONTEXT_TOKENS must be between 100 and 8000")
        return v

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def max_pdf_size_bytes(self) -> int:
        return self.max_pdf_size_mb * 1024 * 1024

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


# Singleton — import `settings` everywhere
try:
    settings = Settings()
except Exception as e:
    log.critical(f"Configuration error: {e}")
    sys.exit(1)


def validate_config() -> None:
    """
    Run at startup. Logs a summary and warns about insecure defaults.
    Does NOT exit on warnings — only on hard errors (handled by pydantic above).
    """
    log.info("Configuration loaded:")
    log.info(f"  DB          : {settings.mongodb_db} @ {_mask_uri(settings.mongodb_uri)}")
    log.info(f"  LLM         : Groq/{settings.groq_model}")
    log.info(f"  RAG         : top_k={settings.top_k_chunks}  max_tokens={settings.max_context_tokens}  prune={settings.prune_similarity}")
    log.info(f"  Origins     : {settings.allowed_origins_list}")
    log.info(f"  Log level   : {settings.log_level}")

    # Warn if CORS is wide open
    if "*" in settings.allowed_origins:
        log.warning("⚠️  ALLOWED_ORIGINS contains '*' — restrict this in production!")

    # Warn if local MongoDB
    if "localhost" in settings.mongodb_uri or "127.0.0.1" in settings.mongodb_uri:
        log.warning("⚠️  Using local MongoDB. Use MongoDB Atlas in production.")


def _mask_uri(uri: str) -> str:
    """Mask password in MongoDB URI for safe logging."""
    import re
    return re.sub(r':([^@/]+)@', ':****@', uri)
