# AI Engineer Copilot

Portfolio-grade MVP for repository intelligence: GitHub ingestion, code chunking, PostgreSQL metadata, OpenAI embeddings, Qdrant retrieval, grounded LLM answers, and a minimal Next.js UI.

## Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# add OPENAI_API_KEY to .env
uvicorn app.main:app --reload
```

## Qdrant
```bash
docker compose up -d qdrant
```

## PostgreSQL
Use your existing local PostgreSQL and `ai_copilot` database, or the compose service.

## Frontend
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000.

## Workflow
1. Start PostgreSQL and Qdrant.
2. Set `OPENAI_API_KEY` in `backend/.env`.
3. Start FastAPI.
4. Connect a public GitHub repository.
5. Click Index.
6. Ask questions.

## Next production upgrades
Authentication, GitHub OAuth/App, background jobs, Tree-sitter AST parsing, hybrid retrieval, reranking, LangGraph tool calling, sandboxed test execution, evaluation suite, streaming, observability and deployment.
