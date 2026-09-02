import ollama

from app.config import settings


# nomic-embed-text produces 768-dimensional embeddings.
EMBEDDING_DIMENSIONS = 768

# Keep comfortably below the embedding model's context limit.
MAX_EMBED_CHARS = 1500


OLLAMA = ollama.Client(
    host=settings.ollama_url,
    timeout=settings.ollama_timeout_seconds,
)


def get_embedding(text: str) -> list[float]:
    """
    Generate a 768-dimensional embedding using Ollama.

    The function validates the input, limits the text size, calls
    the configured embedding model, and validates the returned vector.
    """

    if not text or not text.strip():
        raise ValueError("Cannot embed empty text.")

    text = text.strip()

    if len(text) > MAX_EMBED_CHARS:
        text = text[:MAX_EMBED_CHARS]

    response = OLLAMA.embeddings(
        model=settings.embedding_model,
        prompt=text,
    )

    embedding = response.get("embedding")

    if not embedding:
        raise ValueError("Ollama returned an empty embedding.")

    if len(embedding) != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"Expected {EMBEDDING_DIMENSIONS}-dimensional embedding, "
            f"got {len(embedding)}"
        )

    return embedding