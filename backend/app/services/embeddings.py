import ollama

from app.config import settings


# Keep comfortably below nomic-embed-text's context limit.
MAX_EMBED_CHARS = 1500


def get_embedding(text: str) -> list[float]:
    if not text or not text.strip():
        raise ValueError("Cannot embed empty text.")

    text = text.strip()

    # Hard safety limit for Ollama.
    if len(text) > MAX_EMBED_CHARS:
        text = text[:MAX_EMBED_CHARS]

    response = ollama.embeddings(
        model=settings.embedding_model,
        prompt=text,
    )

    embedding = response.get("embedding")

    if not embedding:
        raise ValueError("Ollama returned an empty embedding.")

    if len(embedding) != 768:
        raise ValueError(
            f"Expected 768-dimensional embedding, got {len(embedding)}"
        )

    return embedding
