from sqlalchemy import text
from app.database import engine
import ollama

from app.config import settings


EMBEDDING_MODEL = settings.embedding_model


def get_embedding(content: str) -> list[float]:
    response = ollama.embed(
        model=EMBEDDING_MODEL,
        input=content,
    )

    return response["embeddings"][0]


def ensure_table():
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS code_chunks (
                    id BIGSERIAL PRIMARY KEY,
                    repository_id BIGINT NOT NULL,
                    file_path TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding VECTOR(768)
                );
                """
            )
        )


def upsert_chunks(chunks):
    ensure_table()

    with engine.begin() as connection:
        for chunk in chunks:
            embedding = get_embedding(chunk.content)

            connection.execute(
                text(
                    """
                    INSERT INTO code_chunks
                    (
                        repository_id,
                        file_path,
                        start_line,
                        end_line,
                        content,
                        embedding
                    )
                    VALUES
                    (
                        :repository_id,
                        :file_path,
                        :start_line,
                        :end_line,
                        :content,
                        CAST(:embedding AS vector)
                    )
                    """
                ),
                {
                    "repository_id": chunk.repository_id,
                    "file_path": chunk.file_path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "content": chunk.content,
                    "embedding": str(embedding),
                },
            )


def search(
    query: str,
    repository_id: int,
    limit: int = 8,
):
    ensure_table()

    query_embedding = get_embedding(query)

    with engine.begin() as connection:
        result = connection.execute(
            text(
                """
                SELECT
                    file_path,
                    start_line,
                    end_line,
                    content,
                    1 - (
                        embedding <=> CAST(:embedding AS vector)
                    ) AS similarity
                FROM code_chunks
                WHERE repository_id = :repository_id
                ORDER BY embedding <=> CAST(:embedding AS vector)
                LIMIT :limit
                """
            ),
            {
                "embedding": str(query_embedding),
                "repository_id": repository_id,
                "limit": limit,
            },
        )

        return [
            {
                "file_path": row.file_path,
                "start_line": row.start_line,
                "end_line": row.end_line,
                "content": row.content,
                "similarity": float(row.similarity),
            }
            for row in result
        ]