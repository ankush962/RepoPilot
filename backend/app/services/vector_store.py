import re

from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.services.embeddings import get_embedding


def ensure_table():
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE EXTENSION IF NOT EXISTS vector;

                CREATE TABLE IF NOT EXISTS code_chunks (
                    id SERIAL PRIMARY KEY,
                    repository_id INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding vector(768)
                );
                """
            )
        )


def get_embedding_for_text(text_value: str):
    return get_embedding(text_value)


def index_chunks(chunks):
    ensure_table()

    with engine.begin() as connection:
        for chunk in chunks:
            embedding = get_embedding(chunk["content"])

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
                    "repository_id": chunk["repository_id"],
                    "file_path": chunk["file_path"],
                    "start_line": chunk["start_line"],
                    "end_line": chunk["end_line"],
                    "content": chunk["content"],
                    "embedding": str(embedding),
                },
            )


def _keyword_score(query: str, source: dict) -> float:
    """
    Lightweight lexical ranking on top of vector similarity.
    This makes repository-level questions prefer documentation,
    entrypoints, APIs and core services over package-lock/config noise.
    """

    q = query.lower()
    path = source["file_path"].lower()
    content = source["content"].lower()

    score = 0.0

    # Repository-level questions
    project_question = any(
        phrase in q
        for phrase in [
            "what does this project do",
            "what does this repository do",
            "what is this project",
            "what is this repository",
            "overview",
            "purpose",
        ]
    )

    if project_question:
        if path == "readme.md":
            score += 0.45

        if path.endswith("/main.py"):
            score += 0.20

        if "/api/" in path:
            score += 0.08

        if "/services/" in path:
            score += 0.08

        if "## stack" in content:
            score += 0.15

        if "## workflow" in content:
            score += 0.15

        if "## privacy" in content:
            score += 0.05

    # Configuration/build artifacts are poor evidence for
    # "what does this project do?"
        if path.endswith("package-lock.json"):
            score -= 0.40

        if path.endswith("tsconfig.json"):
            score -= 0.25

    # Architecture questions
    architecture_question = any(
        phrase in q
        for phrase in [
            "architecture",
            "system design",
            "project structure",
            "how is the project structured",
        ]
    )

    if architecture_question:
        if path == "readme.md":
            score += 0.25

        if "/api/" in path:
            score += 0.15

        if "/services/" in path:
            score += 0.15

        if path.endswith("/main.py"):
            score += 0.15

        if path.endswith("package-lock.json"):
            score -= 0.25

    # Backend questions
    if "backend" in q:
        if path.endswith(".py"):
            score += 0.08

        if "/api/" in path:
            score += 0.12

        if "/services/" in path:
            score += 0.12

        if path.endswith("main.py"):
            score += 0.15

    # Frontend questions
    if "frontend" in q or "ui" in q:
        if path.endswith(".tsx"):
            score += 0.10

        if path.endswith(".css"):
            score += 0.08

        if path.endswith("package.json"):
            score += 0.05

    # Generic code questions
    if any(
        word in q
        for word in [
            "function",
            "implementation",
            "code",
            "where is",
            "how does",
        ]
    ):
        if path.endswith(".py"):
            score += 0.04

        if path.endswith(".tsx"):
            score += 0.04

        if path.endswith("package-lock.json"):
            score -= 0.15

    return score


def upsert_chunks(
    db,
    repository_id: int,
    chunks,
):
    """
    Generate embeddings for repository chunks and persist them.

    Expected chunk format:
    {
        "content": str,
        "start_line": int,
        "end_line": int,
        "file_path": str,
    }
    """

    from app.models import CodeChunk

    inserted = 0

    for chunk in chunks:
        content = chunk["content"]

        embedding = get_embedding(content)

        row = CodeChunk(
            repository_id=repository_id,
            file_path=chunk["file_path"],
            start_line=chunk["start_line"],
            end_line=chunk["end_line"],
            content=content,
            embedding=embedding,
        )

        db.add(row)
        inserted += 1

    db.commit()

    return inserted



def search(
    query: str,
    repository_id: int,
    limit: int = 8,
):
    ensure_table()

    query_embedding = get_embedding(query)

    # Retrieve more candidates than we finally return.
    candidate_limit = max(limit * 3, 30)

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
                LIMIT :candidate_limit
                """
            ),
            {
                "embedding": str(query_embedding),
                "repository_id": repository_id,
                "candidate_limit": candidate_limit,
            },
        )

        sources = [
            {
                "file_path": row.file_path,
                "start_line": row.start_line,
                "end_line": row.end_line,
                "content": row.content,
                "similarity": float(row.similarity),
            }
            for row in result
        ]

    # Hybrid ranking:
    # vector similarity + lightweight repository-aware lexical ranking.
    for source in sources:
        semantic_score = source["similarity"]
        keyword_score = _keyword_score(query, source)

        source["_rank_score"] = semantic_score + keyword_score

    sources.sort(
        key=lambda item: item["_rank_score"],
        reverse=True,
    )

    for source in sources:
        source.pop("_rank_score", None)

    return sources[:limit]
