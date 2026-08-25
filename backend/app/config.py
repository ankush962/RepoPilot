from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://ankushsmac@localhost:5432/ai_copilot"

    github_token: str = ""

    workspace_dir: str = "./workspace"

    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    embedding_model: str = "nomic-embed-text"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()