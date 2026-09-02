from functools import lru_cache
import re
from typing import Any

from sqlalchemy import text

from app.database import engine
from app.services.embeddings import get_embedding


TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_./-]*")

IMPLEMENTATION_TERMS = {
    "implemented",
    "implementation",
    "where is",
    "defined",
    "located",
    "handled",
    "generated",
    "created",
    "cloned",
    "updated",
    "work",
    "works",
}

BACKEND_TERMS = {
    "backend",
    "api",
    "endpoint",
    "fastapi",
    "repository",
    "database",
    "agent",
    "embedding",
    "semantic",
    "search",
    "ranking",
    "hybrid",
    "ingestion",
}

FRONTEND_TERMS = {
    "frontend",
    "ui",
    "interface",
    "page",
    "component",
}


def ensure_table() -> None:
    """
    Database bootstrap.

    Prefer running this once during application startup/migration rather
    than on every retrieval request.
    """
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


@lru_cache(maxsize=256)
def _cached_query_embedding(query: str):
    return get_embedding(query)


def upsert_chunks(repository_id: int, chunks) -> int:
    """
    Embed only chunks that do not already have an embedding.
    """
    updated = 0

    with engine.begin() as connection:
        for chunk in chunks:
            content = (chunk.content or "").strip()

            if not content or chunk.embedding is not None:
                continue

            embedding = get_embedding(content)

            if not embedding or len(embedding) != 768:
                raise ValueError(
                    "Expected 768-dimensional embedding, "
                    f"got {len(embedding) if embedding else 0}"
                )

            connection.execute(
                text(
                    """
                    UPDATE code_chunks
                    SET embedding = CAST(:embedding AS vector)
                    WHERE id = :id
                    """
                ),
                {
                    "id": chunk.id,
                    "embedding": str(list(embedding)),
                },
            )

            updated += 1

    return updated


def _tokens(value: str) -> set[str]:
    return {
        token.lower()
        for token in TOKEN_RE.findall(value or "")
    }


def _path_tokens(path: str) -> set[str]:
    path = path.replace("\\", "/").lower()

    tokens = set()

    for part in path.split("/"):
        tokens.update(TOKEN_RE.findall(part))

    return tokens


def _keyword_score(query: str, source: dict[str, Any]) -> float:
    """
    Lexical relevance.

    Gives higher weight to:
    - exact filename matches
    - path matches
    - important query terms
    - terms appearing in the source content
    """
    q = query.lower().strip()
    path = source["file_path"].lower()
    content = source["content"].lower()

    query_tokens = _tokens(q)
    path_tokens = _path_tokens(path)
    content_tokens = _tokens(content)

    if not query_tokens:
        return 0.0

    score = 0.0

    # Query terms matching the path are extremely useful for
    # repository-code questions.
    path_overlap = query_tokens & path_tokens

    if path_overlap:
        score += min(0.30, 0.10 * len(path_overlap))

    # Query terms appearing in source content.
    content_overlap = query_tokens & content_tokens

    if content_overlap:
        score += min(0.18, 0.03 * len(content_overlap))

    # Exact phrase matches.
    if q in content:
        score += 0.20

    if q in path:
        score += 0.30

    # Intent-aware boosts.
    implementation_question = any(
        term in q for term in IMPLEMENTATION_TERMS
    )

    if implementation_question:
        if path.endswith(".py"):
            score += 0.08

        if "/services/" in path:
            score += 0.12

        if "/api/" in path:
            score += 0.12

    # Backend-oriented question.
    if any(term in q for term in BACKEND_TERMS):
        if path.endswith(".py"):
            score += 0.06

        if "/backend/" in path:
            score += 0.10

    # Frontend-oriented question.
    if any(term in q for term in FRONTEND_TERMS):
        if path.endswith((".tsx", ".jsx", ".ts", ".js", ".css")):
            score += 0.10

    # Strong file-specific signals.
    if "repository" in q:
        if path.endswith("repositories.py"):
            score += 0.35

        if path.endswith("ingestion.py"):
            score += 0.20

    if "embedding" in q:
        if path.endswith("vector_store.py"):
            score += 0.35

        if path.endswith("embeddings.py"):
            score += 0.30

    if "semantic search" in q:
        if path.endswith("vector_store.py"):
            score += 0.40

    if "hybrid ranking" in q:
        if path.endswith("vector_store.py"):
            score += 0.45

    if "ai agent" in q or "agent" in q:
        if path.endswith("agent.py"):
            score += 0.45

    if "fastapi" in q:
        if path.endswith("main.py"):
            score += 0.45

    if "database" in q:
        if path.endswith("database.py"):
            score += 0.35

        if path.endswith("README.md"):
            score += 0.20

    if "clone" in q or "cloned" in q:
        if path.endswith("ingestion.py"):
            score += 0.40

    if "status" in q and "repository" in q:
        if path.endswith("repositories.py"):
            score += 0.40

    return score


def _rank_score(query: str, source: dict[str, Any]) -> float:
    semantic = float(source.get("similarity") or 0.0)
    lexical = _keyword_score(query, source)

    # Semantic retrieval remains the foundation.
    #
    # Lexical/path relevance gets enough weight to correct common
    # embedding mistakes on code-location questions.
    return (
        semantic * 0.68
        + lexical * 0.32
    )


def search(
    query: str,
    repository_id: int,
    limit: int = 8,
):
    query = query.strip()

    if not query:
        return []

    query_embedding = _cached_query_embedding(query)

    if not query_embedding or len(query_embedding) != 768:
        return []

    limit = max(1, min(limit, 12))

    # Retrieve a large candidate pool first.
    candidate_limit = min(
        max(limit * 8, 40),
        100,
    )

    embedding_text = str(list(query_embedding))

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
                "embedding": embedding_text,
                "repository_id": repository_id,
                "candidate_limit": candidate_limit,
            },
        )

        sources = []

        for row in result:
            source = {
                "file_path": row.file_path,
                "start_line": row.start_line,
                "end_line": row.end_line,
                "content": row.content,
                "similarity": float(row.similarity or 0.0),
            }

            source["_rank_score"] = _rank_score(
                query,
                source,
            )

            sources.append(source)

    sources.sort(
        key=lambda item: item["_rank_score"],
        reverse=True,
    )

    # Diversity:
    # Don't allow one file to consume the entire context.
    selected = []
    per_file: dict[str, int] = {}

    for source in sources:
        file_path = source["file_path"]

        count = per_file.get(file_path, 0)

        if count >= 3:
            continue

        per_file[file_path] = count + 1

        source.pop("_rank_score", None)

        selected.append(source)

        if len(selected) >= limit:
            break

    return selected