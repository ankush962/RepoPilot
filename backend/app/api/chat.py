import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Repository, User
from app.schemas import ChatRequest, ChatResponse
from app.services.agent import answer_question, stream_answer
from app.services.auth import require_user
from app.services.usage import (
    check_limit,
    increment_usage,
)
from app.services.workspaces import (
    get_repository_for_user,
    require_permission,
)

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)


# ------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------

def get_chat_repository(
    db: Session,
    repository_id: int,
    user: User,
) -> Repository:
    """
    Resolve a repository that the authenticated user can access.

    Workspace-backed repositories are resolved through workspace
    membership. Legacy repositories without workspace_id remain
    accessible through the repository ownership rules.
    """
    try:
        repo = get_repository_for_user(
            db,
            repository_id,
            user,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail="Repository not found",
        ) from exc

    if not repo:
        raise HTTPException(
            status_code=404,
            detail="Repository not found",
        )

    return repo


def authorize_ai_question(
    db: Session,
    repo: Repository,
    user: User,
) -> None:
    """
    Authorize an AI question and enforce workspace usage limits.

    For workspace-backed repositories:
    - user must have ask_ai permission
    - workspace AI-question usage limit is checked
    - usage is incremented before the AI call

    Legacy repositories without a workspace continue to work through
    their existing repository access rules.
    """
    if repo.workspace_id is None:
        return

    require_permission(
        db,
        repo.workspace_id,
        user,
        "ask_ai",
    )

    check_limit(
        db,
        repo.workspace_id,
        "ai_questions",
    )

    increment_usage(
        db,
        repo.workspace_id,
        "ai_questions",
    )


# ------------------------------------------------------------------
# NON-STREAMING CHAT
# ------------------------------------------------------------------

@router.post(
    "",
    response_model=ChatResponse,
)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    repo = get_chat_repository(
        db,
        payload.repository_id,
        user,
    )

    authorize_ai_question(
        db,
        repo,
        user,
    )

    try:
        answer, sources, metrics = answer_question(
            payload.message.strip(),
            payload.repository_id,
            commit_sha=payload.commit_sha,
        )

        return {
            "answer": answer,
            "sources": sources,
            "metrics": metrics,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to answer the question.",
        ) from exc


# ------------------------------------------------------------------
# STREAMING CHAT
# ------------------------------------------------------------------

@router.post("/stream")
def chat_stream(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    repo = get_chat_repository(
        db,
        payload.repository_id,
        user,
    )

    authorize_ai_question(
        db,
        repo,
        user,
    )

    def event_stream():
        try:
            for event in stream_answer(
                payload.message.strip(),
                payload.repository_id,
                commit_sha=payload.commit_sha,
            ):
                yield (
                    "data: "
                    f"{json.dumps(event, ensure_ascii=False)}"
                    "\n\n"
                )

            yield "data: [DONE]\n\n"

        except Exception as exc:
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "error",
                        "message": str(exc),
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
