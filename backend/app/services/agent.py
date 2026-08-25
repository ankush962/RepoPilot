import ollama

from app.config import settings
from app.services.vector_store import search


MODEL = settings.ollama_model


SYSTEM_PROMPT = """
You are AI Engineer Copilot.

Answer ONLY from the supplied repository context.

STRICT RULES:
1. Never rely on prior knowledge about the project.
2. Never invent files, databases, models, APIs, or architecture.
3. If the context says PostgreSQL + pgvector, DO NOT say Qdrant.
4. If the context says Ollama, DO NOT say OpenAI.
5. Treat the supplied code as the source of truth.
6. If the context is insufficient, explicitly say:
   "The indexed repository context is insufficient to determine this."
7. Always mention the relevant file path and line range.
8. For architecture questions, describe only components actually present in the retrieved context.
"""


def answer_question(
    question: str,
    repository_id: int,
):
    sources = search(
        question,
        repository_id,
        limit=8,
    )

    context_parts = []

    for source in sources:
        context_parts.append(
            f"""
FILE: {source["file_path"]}
LINES: {source["start_line"]}-{source["end_line"]}
SIMILARITY: {source["similarity"]:.4f}

{source["content"]}
"""
        )

    context = "\n\n".join(context_parts)

    prompt = f"""
You must answer the question using ONLY the repository evidence below.

================ REPOSITORY EVIDENCE ================
{context}
=======================================================

QUESTION:
{question}

IMPORTANT:
- The repository evidence is the ONLY source of truth.
- Do not use your general knowledge about this project.
- Do not infer technologies that are not explicitly present.
- If the evidence does not support an answer, say:
  "The indexed repository does not provide enough evidence to answer this."
- Quote or reference the exact file paths and line ranges that support your answer.
"""

    response = ollama.chat(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        options={
            "temperature": 0.0,
            "num_predict": 300,
        },
    )

    answer = response["message"]["content"]

    return answer, sources