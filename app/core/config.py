from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _csv_ints(value: str | list[int]) -> list[int]:
    if isinstance(value, list):
        return value
    if not value.strip():
        return []
    try:
        return [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise ValueError(
            "expected comma-separated numeric Telegram user IDs; "
            "@username values are not supported"
        ) from exc


def _csv_strings(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return value
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "gdrive-rag-accounting-bot"
    log_level: str = "INFO"
    api_key: SecretStr = SecretStr("")
    internal_api_url: str = "http://api:8000"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "ragbot"
    postgres_user: str = "ragbot"
    postgres_password: SecretStr = SecretStr("")
    database_url: str | None = None
    redis_url: str = "redis://localhost:6379/0"

    telegram_bot_token: SecretStr = SecretStr("")
    telegram_allowed_user_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    telegram_admin_user_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    telegram_default_tenant_id: UUID | None = None

    google_auth_mode: Literal["service_account", "oauth2"] = "service_account"
    google_service_account_file: Path = Path("credentials/google-service-account.json")
    google_oauth_client_file: Path = Path("credentials/google-oauth-client.json")
    google_oauth_token_file: Path = Path("credentials/google-oauth-token.json")
    google_drive_root_folder_id: str = ""

    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-2.5-flash"
    gemini_fallback_models: Annotated[list[str], NoDecode] = Field(default_factory=list)
    ai_external_processing_enabled: bool = True

    pinecone_api_key: SecretStr = SecretStr("")
    pinecone_index: str = ""
    pinecone_host: str = ""
    pinecone_namespace_prefix: str = "ragbot"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "eu-west-1"
    pinecone_metric: Literal["cosine"] = "cosine"
    pinecone_storage_warning_mb: int = 1500

    embedding_provider: Literal["local_qwen", "http", "fake"] = "local_qwen"
    embedding_http_url: str = ""
    embedding_http_api_key: SecretStr = SecretStr("")
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_device: str = "cpu"
    embedding_dimension: int = 1024
    embedding_batch_size: int = 16
    embedding_max_length: int = 8192
    cache_dir: Path = Path(".cache/ragbot")

    chunk_target_tokens: int = 700
    chunk_overlap_tokens: int = 80
    max_chunks_per_document: int = 2000
    top_k_semantic: int = 20
    top_k_lexical: int = 20
    top_k_rerank: int = 8
    min_relevance_score: float = 0.05

    ocr_enabled: bool = False
    ocr_provider: str = "tesseract"
    ocr_languages: str = "deu+eng"
    ocr_min_text_chars: int = 80
    max_file_size_mb: int = 100
    sync_poll_interval_seconds: int = 300
    initial_sync_dry_run: bool = True

    agent_max_iterations: int = 4
    agent_max_tool_calls: int = 8
    agent_timeout_seconds: int = 45

    @field_validator("telegram_allowed_user_ids", "telegram_admin_user_ids", mode="before")
    @classmethod
    def parse_int_csv(cls, value: str | list[int]) -> list[int]:
        return _csv_ints(value)

    @field_validator("telegram_default_tenant_id", mode="before")
    @classmethod
    def parse_optional_uuid(cls, value: UUID | str | None) -> UUID | str | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("google_drive_root_folder_id", mode="before")
    @classmethod
    def parse_drive_folder_id(cls, value: str) -> str:
        value = value.strip()
        match = re.search(r"/folders/([A-Za-z0-9_-]+)", value)
        return match.group(1) if match else value

    @field_validator("gemini_fallback_models", mode="before")
    @classmethod
    def parse_string_csv(cls, value: str | list[str]) -> list[str]:
        return _csv_strings(value)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        password = self.postgres_password.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def validate_production(self) -> list[str]:
        errors: list[str] = []
        required = {
            "DATABASE_URL or PostgreSQL password": bool(
                self.database_url or self.postgres_password.get_secret_value()
            ),
            "TELEGRAM_BOT_TOKEN": bool(self.telegram_bot_token.get_secret_value()),
            "TELEGRAM_ALLOWED_USER_IDS": bool(self.telegram_allowed_user_ids),
            "GOOGLE_DRIVE_ROOT_FOLDER_ID": bool(self.google_drive_root_folder_id),
            "PINECONE_INDEX": bool(self.pinecone_index),
        }
        for name, valid in required.items():
            if not valid:
                errors.append(f"Missing required production setting: {name}")
        if self.ai_external_processing_enabled and not self.gemini_api_key.get_secret_value():
            errors.append("GEMINI_API_KEY is required when external AI processing is enabled")
        return errors


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
