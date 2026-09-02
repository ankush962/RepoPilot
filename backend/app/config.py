from __future__ import annotations

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    # ------------------------------------------------------------------
    # ENVIRONMENT
    # ------------------------------------------------------------------

    environment: str = "development"

    log_level: str = "INFO"

    # ------------------------------------------------------------------
    # DATABASE
    # ------------------------------------------------------------------

    database_url: str = (
        "postgresql+psycopg://"
        "ankushsmac@localhost:5432/ai_copilot"
    )

    auto_create_tables: bool = False
    ensure_schema_on_startup: bool = True

    # ------------------------------------------------------------------
    # AUTH / SECURITY
    # ------------------------------------------------------------------

    github_token: str = ""

    api_key: str = ""

    auth_enabled: bool = False

    auth_username: str = "admin"

    auth_password: str = "change-me"

    jwt_secret: str = (
        "change-me-in-production"
    )

    jwt_expire_minutes: int = 720

    session_cookie_name: str = (
        "repopilot_session"
    )

    session_expire_days: int = 7

    # ------------------------------------------------------------------
    # FRONTEND / CORS
    # ------------------------------------------------------------------

    frontend_url: str = (
        "http://localhost:3000"
    )

    allowed_origins: str = ""

    # ------------------------------------------------------------------
    # AI / OLLAMA
    # ------------------------------------------------------------------

    ollama_url: str = (
        "http://127.0.0.1:11434"
    )

    ollama_model: str = (
        "qwen2.5-coder:7b"
    )

    embedding_model: str = (
        "nomic-embed-text"
    )

    ollama_timeout_seconds: float = 120.0

    healthcheck_timeout_seconds: float = 10.0

    # ------------------------------------------------------------------
    # WORKSPACE / INDEXING
    # ------------------------------------------------------------------

    workspace_dir: str = "./workspace"

    worker_enabled: bool = True

    worker_poll_seconds: float = 1.0

    max_index_attempts: int = 3

    stale_job_minutes: int = 30

    max_chat_message_chars: int = 4000

    max_retrieval_limit: int = 12

    # ------------------------------------------------------------------
    # GIT
    # ------------------------------------------------------------------

    git_auto_sync_enabled: bool = True

    git_auto_sync_interval_seconds: int = 60

    git_compare_max_commits: int = 100

    # ------------------------------------------------------------------
    # RATE LIMITING
    # ------------------------------------------------------------------

    rate_limit_enabled: bool = True

    rate_limit_window_seconds: int = 60

    rate_limit_max_requests: int = 120

    # ------------------------------------------------------------------
    # MODEL SETTINGS
    # ------------------------------------------------------------------

    model_temperature: float = 0.0

    model_num_predict: int = 2000

    model_num_ctx: int = 8192

    # ------------------------------------------------------------------
    # PYDANTIC SETTINGS
    # ------------------------------------------------------------------

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------

    @property
    def cors_origins(self) -> list[str]:
        origins: list[str] = []

        # Do not automatically include localhost in production
        # unless explicitly configured.
        if self.frontend_url:
            origins.append(
                self.frontend_url.strip()
            )

        if self.allowed_origins:
            origins.extend(
                origin.strip()
                for origin in (
                    self.allowed_origins.split(",")
                )
                if origin.strip()
            )

        # Development convenience.
        if self.environment.lower() in {
            "development",
            "dev",
            "local",
        }:
            origins.extend(
                [
                    "http://localhost:3000",
                    "http://127.0.0.1:3000",
                ]
            )

        # Remove duplicates while preserving order.
        return list(
            dict.fromkeys(
                origin
                for origin in origins
                if origin
            )
        )


settings = Settings()