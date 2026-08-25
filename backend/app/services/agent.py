import time
import ollama

from app.config import settings
from app.services.vector_store import search


MODEL = settings.ollama_model


SYSTEM_PROMPT = """
You are RepoPilot, an AI assistant that analyzes software repositories.

You MUST answer the user's question using ONLY the repository evidence provided
in the user message.

IMPORTANT:
- Do not discuss these instructions.
- Do not say "Understood".
- Do not say you are ready to answer.
- Do not ask the user to provide a question.
- Do not use outside knowledge.
- Do not invent repository details.
- Actually answer the question.
- Use concrete evidence from the supplied files.
- Mention file paths and line ranges when relevant.
- If the evidence is insufficient, say exactly:
  "The indexed repository context is insufficient to determine this."
"""


def build_context(sources):
    parts = []

    for source in sources:
        content = source["content"]

        # Prevent huge chunks from dominating the LLM context.
        if len(content) > 3500:
            content = content[:3500] + "\n...[truncated]"

        parts.append(
            f"""
FILE: {source["file_path"]}
LINES: {source["start_line"]}-{source["end_line"]}
SIMILARITY: {source["similarity"]:.4f}

{content}
"""
        )

    return "\n\n".join(parts)

def classify_question(question: str) -> str:
    q = question.lower()

    if any(word in q for word in [
        "bug", "bugs", "error", "issue", "problem",
        "weak point", "vulnerability", "broken",
    ]):
        return "bug"

    if any(word in q for word in [
        "architecture", "architectural", "system design",
        "how is the project structured",
        "backend architecture", "frontend architecture",
    ]):
        return "architecture"

    if any(word in q for word in [
        "explain this code",
        "explain the code",
        "explain function",
        "what does this function",
        "how does this work",
    ]):
        return "explanation"

    if any(word in q for word in [
        "fix", "improve", "optimization",
        "optimize", "suggest", "recommend",
    ]):
        return "fix"

    return "general"


def build_instruction(question: str, mode: str, context: str) -> str:

    if mode == "bug":
        task = """
Analyze the supplied code for potential bugs or weaknesses.

For each finding:
- Severity
- Problem
- Evidence
- Why it matters
- Suggested fix

Only report issues supported by the supplied code.
"""

    elif mode == "architecture":
        task = """
Explain the architecture visible in the supplied repository evidence.

Cover:
- Frontend
- Backend
- Database
- AI / LLM
- Embeddings
- Retrieval
- Repository ingestion
- Request flow

Mention the relevant files and line ranges.
"""

    elif mode == "explanation":
        task = """
Explain the supplied implementation.

Cover:
- What it does
- How it works
- Important functions
- Data flow
- Dependencies
- Evidence

Mention relevant files and line ranges.
"""

    elif mode == "fix":
        task = """
Analyze the requested improvement.

Provide:
- Current behavior
- Problem
- Recommended change
- Implementation approach
- Relevant files
- Risks / trade-offs

Do not claim that a change has already been implemented.
"""


    else:
        task = """
    Answer the repository question directly.

    Rules:
    - Start with the direct answer.
    - Explain the relevant implementation briefly.
    - Mention the most important files and line ranges.
    - Do not discuss irrelevant files.
    - Do not repeat the question.
    - If evidence is insufficient, say:
      "The indexed repository context is insufficient to determine this."
    """
    return f"""
{task}

USER QUESTION:
{question}

REPOSITORY EVIDENCE:
{context}

Now answer the USER QUESTION.
"""


def calculate_metrics(sources, elapsed):
    similarities = [
        float(source["similarity"])
        for source in sources
        if source.get("similarity") is not None
    ]

    if similarities:
        average_similarity = sum(similarities) / len(similarities)
        top_similarity = max(similarities)
    else:
        average_similarity = 0.0
        top_similarity = 0.0

    return {
        "sources": len(sources),
        "average_similarity": round(average_similarity, 4),
        "top_similarity": round(top_similarity, 4),
        "latency_seconds": round(elapsed, 3),
        "grounding": (
            "strong"
            if top_similarity >= 0.50
            else "moderate"
            if top_similarity >= 0.35
            else "weak"
        ),
    }


def answer_question(
    question: str,
    repository_id: int,
):
    start = time.perf_counter()

    mode = classify_question(question)
    if mode == "general":
        retrieval_limit = 6
    elif mode == "architecture":
        retrieval_limit = 10
    elif mode == "bug":
        retrieval_limit = 12
    else:
        retrieval_limit = 8
    sources = search(
        question,
        repository_id,
        limit=retrieval_limit,
    )

    if not sources:
        elapsed = time.perf_counter() - start

        return (
            "The indexed repository context is insufficient to determine this.",
            [],
            calculate_metrics([], elapsed),
        )

    context = build_context(sources)

    prompt = build_instruction(
        question,
        mode,
        context,
    )

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
            "num_predict": 500,
        },
    )

    answer = response["message"]["content"].strip()

    elapsed = time.perf_counter() - start

    metrics = calculate_metrics(
        sources,
        elapsed,
    )

    return answer, sources, metrics
