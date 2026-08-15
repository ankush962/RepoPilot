from fastapi import FastAPI
from sqlalchemy import text
from app.database import engine, Base
from app.models import Repository, CodeChunk, ConversationMessage
from app.api.repositories import router as repository_router
from app.api.chat import router as chat_router

app = FastAPI(title="AI Engineer Copilot", version="1.0.0", description="Agentic codebase intelligence platform.")
app.include_router(repository_router); app.include_router(chat_router)

@app.get("/health")
def health_check(): return {"status":"ok", "service":"ai-engineer-copilot"}

@app.get("/health/database")
def database_health_check():
    with engine.connect() as c: c.execute(text("SELECT 1"))
    return {"status":"ok", "database":"connected"}

@app.on_event("startup")
def create_tables(): Base.metadata.create_all(bind=engine)
