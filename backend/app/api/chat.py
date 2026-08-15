from fastapi import APIRouter, HTTPException
from app.schemas import ChatRequest, ChatResponse
from app.services.agent import answer_question
router = APIRouter(prefix="/chat", tags=["chat"])
@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest):
    try:
        answer, sources = answer_question(payload.message, payload.repository_id)
        return {"answer": answer, "sources": sources}
    except Exception as exc:
        raise HTTPException(500, str(exc))
