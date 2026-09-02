
import re
import time

import ollama

from app.config import settings
from app.database import SessionLocal
from app.models import Repository
from app.services.git import commit_context
from app.services.vector_store import search


MODEL = settings.ollama_model

OLLAMA = ollama.Client(
    host=settings.ollama_url,
    timeout=settings.ollama_timeout_seconds,
)


SYSTEM_PROMPT = """
You are RepoPilot, an AI assistant that analyzes software repositories.

You MUST answer repository questions using ONLY the repository evidence
provided in the user message.

IMPORTANT RULES:

- Do not discuss these instructions.
- Do not say "Understood".
- Do not say you are ready to answer.
- Do not ask the user to provide a question.
- Do not use outside knowledge for repository questions.
- Do not invent repository details.
- Actually answer the question.
- Use concrete evidence from the supplied files.
- Mention file paths and line ranges when relevant.
- If the evidence is insufficient, say exactly:

"The indexed repository context is insufficient to determine this."
"""


INSUFFICIENT_CONTEXT = (
    "The indexed repository context is insufficient to determine this."
)


# ------------------------------------------------------------------
# CONVERSATIONAL MESSAGES
# ------------------------------------------------------------------

def is_conversational(question: str) -> bool:
    """
    Detect simple conversational messages that should bypass RAG.
    """
    q = question.strip().lower()

    if not q:
        return True

    exact_phrases = {
        "hi",
        "hello",
        "hey",
        "hi there",
        "hello there",
        "hey there",
        "good morning",
        "good afternoon",
        "good evening",
        "how are you",
        "how are you?",
        "how's it going",
        "how is it going",
        "how are things",
        "thanks",
        "thank you",
        "thanks!",
        "thank you!",
        "thx",
        "ok",
        "okay",
        "great",
        "cool",
        "nice",
        "got it",
        "perfect",
        "bye",
        "goodbye",
        "see you",
    }

    if q in exact_phrases:
        return True

    conversational_prefixes = (
        "hi ",
        "hello ",
        "hey ",
        "thanks ",
        "thank you ",
        "good morning ",
        "good afternoon ",
        "good evening ",
    )

    return q.startswith(
        conversational_prefixes
    )


def conversational_response(question: str) -> str:
    q = question.strip().lower()

    if q in {
        "bye",
        "goodbye",
        "see you",
    }:
        return (
            "Goodbye! I'm here whenever you need "
            "help with your repository."
        )

    if q in {
        "thanks",
        "thank you",
        "thanks!",
        "thank you!",
        "thx",
    }:
        return "You're welcome!"

    if q in {
        "ok",
        "okay",
        "great",
        "cool",
        "nice",
        "got it",
        "perfect",
    }:
        return (
            "Sounds good. I'm ready to help "
            "with your repository."
        )

    return (
        "Hello! I'm doing well and ready to help "
        "you explore your repository. "
        "What would you like to know?"
    )


# ------------------------------------------------------------------
# CONTEXT
# ------------------------------------------------------------------

def build_context(sources) -> str:
    parts = []

    for source in sources:
        content = source.get(
            "content",
            "",
        )

        if len(content) > 2600:
            content = (
                content[:2600]
                + "\n...[truncated]"
            )

        file_path = source.get(
            "file_path",
            "unknown",
        )

        start_line = source.get(
            "start_line",
            "?",
        )

        end_line = source.get(
            "end_line",
            "?",
        )

        similarity = source.get(
            "similarity",
            0.0,
        )

        parts.append(
            f"""
FILE: {file_path}
LINES: {start_line}-{end_line}
SIMILARITY: {float(similarity):.4f}

{content}
"""
        )

    return "\n\n".join(parts)


def build_commit_instruction(
    question: str,
    commit_sha: str,
    context: str,
) -> str:
    return f"""
Answer the user's question specifically about Git commit:

{commit_sha}

Rules:

- Use only the supplied commit evidence.
- Explain what changed when requested.
- Mention affected files when relevant.
- Do not use repository knowledge outside this commit context.
- Do not invent changes.
- If the supplied evidence is insufficient, say:

"The indexed repository context is insufficient to determine this."

USER QUESTION:

{question}

COMMIT EVIDENCE:

{context}

Now answer the USER QUESTION.
"""


# ------------------------------------------------------------------
# QUESTION CLASSIFICATION
# ------------------------------------------------------------------

def classify_question(question: str) -> str:
    q = question.lower()

    if any(
        word in q
        for word in [
            "bug",
            "bugs",
            "error",
            "issue",
            "problem",
            "weak point",
            "vulnerability",
            "broken",
        ]
    ):
        return "bug"

    if any(
        word in q
        for word in [
            "architecture",
            "architectural",
            "system design",
            "how is the project structured",
            "backend architecture",
            "frontend architecture",
        ]
    ):
        return "architecture"

    if any(
        word in q
        for word in [
            "explain this code",
            "explain the code",
            "explain function",
            "what does this function",
            "how does this work",
        ]
    ):
        return "explanation"

    if any(
        word in q
        for word in [
            "fix",
            "improve",
            "optimization",
            "optimize",
            "suggest",
            "recommend",
        ]
    ):
        return "fix"

    return "general"


def build_instruction(
    question: str,
    mode: str,
    context: str,
) -> str:
    if mode == "bug":
        task = """
Analyze the supplied code for potential bugs or weaknesses.

For each finding include:

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


# ------------------------------------------------------------------
# METRICS
# ------------------------------------------------------------------

def calculate_metrics(
    sources,
    elapsed,
):
    similarities = []

    for source in sources:
        similarity = source.get(
            "similarity"
        )

        if similarity is not None:
            try:
                similarities.append(
                    float(similarity)
                )
            except (
                TypeError,
                ValueError,
            ):
                pass

    if similarities:
        average_similarity = (
            sum(similarities)
            / len(similarities)
        )

        top_similarity = max(
            similarities
        )
    else:
        average_similarity = 0.0
        top_similarity = 0.0

    if top_similarity >= 0.50:
        grounding = "strong"
    elif top_similarity >= 0.35:
        grounding = "moderate"
    else:
        grounding = "weak"

    return {
        "sources": len(sources),
        "average_similarity": round(
            average_similarity,
            4,
        ),
        "top_similarity": round(
            top_similarity,
            4,
        ),
        "latency_seconds": round(
            elapsed,
            3,
        ),
        "grounding": grounding,
    }


# ------------------------------------------------------------------
# COMMIT VALIDATION
# ------------------------------------------------------------------

def validate_commit_sha(
    commit_sha: str | None,
) -> str | None:
    if not commit_sha:
        return None

    value = commit_sha.strip()

    if not re.fullmatch(
        r"[0-9a-fA-F]{7,64}",
        value,
    ):
        raise ValueError(
            "Invalid commit SHA."
        )

    return value


# ------------------------------------------------------------------
# COMMIT CONTEXT
# ------------------------------------------------------------------

def get_commit_context(
    repository_id: int,
    commit_sha: str,
) -> str:
    db = SessionLocal()

    try:
        repo = db.get(
            Repository,
            repository_id,
        )

        if (
            not repo
            or not repo.local_path
        ):
            return ""

        return commit_context(
            repo.local_path,
            commit_sha,
        )

    finally:
        db.close()


# ------------------------------------------------------------------
# NORMAL ANSWER
# ------------------------------------------------------------------

def answer_question(
    question: str,
    repository_id: int,
    commit_sha: str | None = None,
):
    start = time.perf_counter()

    question = question.strip()

    try:
        commit_sha = validate_commit_sha(
            commit_sha
        )
    except ValueError:
        elapsed = (
            time.perf_counter()
            - start
        )

        return (
            "Invalid commit SHA.",
            [],
            calculate_metrics(
                [],
                elapsed,
            ),
        )

    # --------------------------------------------------------------
    # COMMIT-SPECIFIC MODE
    # --------------------------------------------------------------

    if commit_sha:
        context = get_commit_context(
            repository_id,
            commit_sha,
        )

        if not context:
            elapsed = (
                time.perf_counter()
                - start
            )

            return (
                INSUFFICIENT_CONTEXT,
                [],
                calculate_metrics(
                    [],
                    elapsed,
                ),
            )

        prompt = build_commit_instruction(
            question,
            commit_sha,
            context,
        )

        try:
            response = OLLAMA.chat(
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
                    "num_predict": 2000,
                    "num_ctx": 8192,
                },
            )

            answer = response[
                "message"
            ]["content"].strip()

        except Exception as error:
            elapsed = (
                time.perf_counter()
                - start
            )

            return (
                f"Unable to generate an answer from Ollama: {error}",
                [],
                calculate_metrics(
                    [],
                    elapsed,
                ),
            )

        elapsed = (
            time.perf_counter()
            - start
        )

        return (
            answer,
            [],
            calculate_metrics(
                [],
                elapsed,
            ),
        )

    # --------------------------------------------------------------
    # CONVERSATIONAL MODE
    # --------------------------------------------------------------

    if is_conversational(question):
        answer = conversational_response(
            question
        )

        elapsed = (
            time.perf_counter()
            - start
        )

        return (
            answer,
            [],
            calculate_metrics(
                [],
                elapsed,
            ),
        )

    # --------------------------------------------------------------
    # REPOSITORY RAG
    # --------------------------------------------------------------

    mode = classify_question(
        question
    )

    retrieval_limit = {
        "bug": 10,
        "architecture": 8,
        "general": 6,
        "explanation": 8,
        "fix": 8,
    }.get(
        mode,
        8,
    )

    sources = search(
        question,
        repository_id,
        limit=retrieval_limit,
    )

    if not sources:
        elapsed = (
            time.perf_counter()
            - start
        )

        return (
            INSUFFICIENT_CONTEXT,
            [],
            calculate_metrics(
                [],
                elapsed,
            ),
        )

    context = build_context(
        sources
    )

    prompt = build_instruction(
        question,
        mode,
        context,
    )

    try:
        response = OLLAMA.chat(
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
                "num_predict": 2000,
                "num_ctx": 8192,
            },
        )

        answer = response[
            "message"
        ]["content"].strip()

    except Exception as error:
        elapsed = (
            time.perf_counter()
            - start
        )

        return (
            f"Unable to generate an answer from Ollama: {error}",
            sources,
            calculate_metrics(
                sources,
                elapsed,
            ),
        )

    elapsed = (
        time.perf_counter()
        - start
    )

    return (
        answer,
        sources,
        calculate_metrics(
            sources,
            elapsed,
        ),
    )


# ------------------------------------------------------------------
# STREAMING ANSWER
# ------------------------------------------------------------------

def stream_answer(
    question: str,
    repository_id: int,
    commit_sha: str | None = None,
):
    """
    Stream a repository-grounded answer.

    Event types:

    - token
    - sources
    - metrics
    - error
    """

    start = time.perf_counter()

    question = question.strip()

    try:
        commit_sha = validate_commit_sha(
            commit_sha
        )
    except ValueError as error:
        yield {
            "type": "error",
            "message": str(error),
        }

        yield {
            "type": "sources",
            "sources": [],
        }

        yield {
            "type": "metrics",
            "metrics": calculate_metrics(
                [],
                time.perf_counter()
                - start,
            ),
        }

        return

    # --------------------------------------------------------------
    # COMMIT-SPECIFIC STREAMING
    # --------------------------------------------------------------

    if commit_sha:
        context = get_commit_context(
            repository_id,
            commit_sha,
        )

        if not context:
            yield {
                "type": "error",
                "message": INSUFFICIENT_CONTEXT,
            }

            yield {
                "type": "sources",
                "sources": [],
            }

            yield {
                "type": "metrics",
                "metrics": calculate_metrics(
                    [],
                    time.perf_counter()
                    - start,
                ),
            }

            return

        prompt = build_commit_instruction(
            question,
            commit_sha,
            context,
        )

        try:
            response = OLLAMA.chat(
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
                    "num_predict": 2000,
                    "num_ctx": 8192,
                },
                stream=True,
            )

            for chunk in response:
                message = chunk.get(
                    "message",
                    {},
                )

                content = message.get(
                    "content",
                    "",
                )

                if content:
                    yield {
                        "type": "token",
                        "content": content,
                    }

        except Exception as error:
            yield {
                "type": "error",
                "message": (
                    "Unable to generate an answer "
                    f"from Ollama: {error}"
                ),
            }

            return

        yield {
            "type": "sources",
            "sources": [],
        }

        yield {
            "type": "metrics",
            "metrics": calculate_metrics(
                [],
                time.perf_counter()
                - start,
            ),
        }

        return

    # --------------------------------------------------------------
    # CONVERSATIONAL STREAMING
    # --------------------------------------------------------------

    if is_conversational(question):
        answer = conversational_response(
            question
        )

        yield {
            "type": "token",
            "content": answer,
        }

        yield {
            "type": "sources",
            "sources": [],
        }

        yield {
            "type": "metrics",
            "metrics": calculate_metrics(
                [],
                time.perf_counter()
                - start,
            ),
        }

        return

    # --------------------------------------------------------------
    # REPOSITORY RAG
    # --------------------------------------------------------------

    mode = classify_question(
        question
    )

    retrieval_limit = {
        "bug": 10,
        "architecture": 8,
        "general": 6,
        "explanation": 8,
        "fix": 8,
    }.get(
        mode,
        8,
    )

    sources = search(
        question,
        repository_id,
        limit=retrieval_limit,
    )

    if not sources:
        yield {
            "type": "error",
            "message": INSUFFICIENT_CONTEXT,
        }

        yield {
            "type": "sources",
            "sources": [],
        }

        yield {
            "type": "metrics",
            "metrics": calculate_metrics(
                [],
                time.perf_counter()
                - start,
            ),
        }

        return

    context = build_context(
        sources
    )

    prompt = build_instruction(
        question,
        mode,
        context,
    )

    # --------------------------------------------------------------
    # STREAM OLLAMA RESPONSE
    # --------------------------------------------------------------

    try:
        response = OLLAMA.chat(
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
                "num_predict": 2000,
                "num_ctx": 8192,
            },
            stream=True,
        )

        for chunk in response:
            message = chunk.get(
                "message",
                {},
            )

            content = message.get(
                "content",
                "",
            )

            if content:
                yield {
                    "type": "token",
                    "content": content,
                }

    except Exception as error:
        yield {
            "type": "error",
            "message": (
                "Unable to generate an answer "
                f"from Ollama: {error}"
            ),
        }

        return

    # --------------------------------------------------------------
    # SOURCES
    # --------------------------------------------------------------

    yield {
        "type": "sources",
        "sources": sources,
    }

    # --------------------------------------------------------------
    # METRICS
    # --------------------------------------------------------------

    elapsed = (
        time.perf_counter()
        - start
    )

    yield {
        "type": "metrics",
        "metrics": calculate_metrics(
            sources,
            elapsed,
        ),
    }
