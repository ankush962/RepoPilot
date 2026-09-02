from sqlalchemy import text
from app.database import engine


def ensure_schema():
    """Backward-compatible bootstrap for the local MVP database.

    New deployments should run the same statements through migrations; these
    idempotent checks keep existing local installations upgradeable.
    """
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS index_jobs (
                id SERIAL PRIMARY KEY,
                repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                status VARCHAR(32) NOT NULL DEFAULT 'queued',
                progress INTEGER NOT NULL DEFAULT 0,
                stage VARCHAR(255) NOT NULL DEFAULT 'Queued',
                attempts INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                result_chunks INTEGER NOT NULL DEFAULT 0,
                result_vectors INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                started_at TIMESTAMP,
                finished_at TIMESTAMP
            )
        """))
        connection.execute(text("ALTER TABLE code_chunks ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64)"))
        connection.execute(text("ALTER TABLE code_chunks ADD COLUMN IF NOT EXISTS chunk_type VARCHAR(32) DEFAULT 'text'"))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_index_jobs_status_created
            ON index_jobs(status, created_at)
        """))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_code_chunks_repo_hash
            ON code_chunks(repository_id, content_hash)
        """))
