import ollama

from app.config import settings


def get_embedding(text: str) -> list[float]:
    response = ollama.embeddings(
        model=settings.embedding_model,
        prompt=text,
    )

    return response["embedding"]
