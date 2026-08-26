from sqlalchemy import text

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


def upsert_chunks(repository_id: int, chunks):
    """
    Generate embeddings for existing repository chunks
    and update their embedding column.
    """

    ensure_table()

    updated = 0

    with engine.begin() as connection:
        for chunk in chunks:
            content = chunk.content

            if not content or not content.strip():
                continue

            embedding = get_embedding(content)

            if not embedding:
                continue

            if len(embedding) != 768:
                raise ValueError(
                    f"Expected 768-dimensional embedding, got {len(embedding)}"
                )

            connection.execute(
                text(
                    """
                    UPDATE code_chunks
                    SET embedding = CAST(:embedding AS vector)
                    WHERE repository_id = :repository_id
                      AND file_path = :file_path
                      AND start_line = :start_line
                      AND end_line = :end_line
                    """
                ),
                {
                    "repository_id": repository_id,
                    "file_path": chunk.file_path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "embedding": str(embedding),
                },
            )

            updated += 1

    return updated


def _keyword_score(query: str, source: dict) -> float:
    """
    Lightweight lexical ranking on top of vector similarity.
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

    # Package/config files are generally weaker evidence
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


def search(
    query: str,
    repository_id: int,
    limit: int = 8,
):
    ensure_table()

    query_embedding = get_embedding(query)

    if not query_embedding or len(query_embedding) != 768:
        return []

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
                  AND embedding IS NOT NULL
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

        sources = []

        for row in result:
            similarity = row.similarity

            # Protect the agent from None values
            if similarity is None:
                similarity = 0.0

            sources.append(
                {
                    "file_path": row.file_path,
                    "start_line": row.start_line,
                    "end_line": row.end_line,
                    "content": row.content,
                    "similarity": float(similarity),
                }
            )

    # Hybrid ranking
    for source in sources:
        semantic_score = source["similarity"]
        keyword_score = _keyword_score(query, source)

        source["_rank_score"] = (
            semantic_score + keyword_score
        )

    sources.sort(
        key=lambda item: item["_rank_score"],
        reverse=True,
    )

    for source in sources:
        source.pop("_rank_score", None)

    return sources[:limit]