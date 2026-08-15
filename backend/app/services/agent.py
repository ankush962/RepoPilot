import ollama

from app.config import settings
from app.services.vector_store import search


MODEL = settings.ollama_model


SYSTEM_PROMPT = """
You are AI Engineer Copilot, an expert software engineer.

You help developers understand and work with their codebases.

Rules:

1. Answer using the provided repository context.
2. Never invent files, functions, classes, or code.
3. Mention relevant file paths and line ranges.
4. Explain your reasoning clearly.
5. If the context is insufficient, say so.
6. Prefer practical engineering explanations.
7. When appropriate, provide code examples.
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

{source["content"]}
"""
        )

    context = "\n\n".join(context_parts)

    prompt = f"""
Repository context:

{context}

User question:

{question}
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
            "temperature": 0.1,
        },
    )

    answer = response["message"]["content"]

    return answer, sources