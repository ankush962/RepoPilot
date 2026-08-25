from fastapi import APIRouter, HTTPException

from app.schemas import ChatRequest, ChatResponse
from app.services.agent import answer_question


router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)


@router.post(
    "",
    response_model=ChatResponse,
)
def chat(payload: ChatRequest):
    try:
        answer, sources, metrics = answer_question(
            payload.message,
            payload.repository_id,
        )

        return {
            "answer": answer,
            "sources": sources,
            "metrics": metrics,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )