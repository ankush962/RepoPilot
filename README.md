# AI Engineer Copilot

A portfolio-grade, local-first AI codebase intelligence platform.

## Stack

- **Frontend:** Next.js + React
- **Backend:** FastAPI + Python
- **LLM:** Ollama + Qwen 2.5 Coder 7B
- **Embeddings:** Ollama + nomic-embed-text
- **Database:** PostgreSQL + pgvector
- **Repository ingestion:** GitPython
- **Retrieval:** PostgreSQL vector similarity search

## Run locally

### Backend

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

The API runs on `http://127.0.0.1:8000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Workflow

1. Start PostgreSQL.
2. Make sure Ollama is running with `qwen2.5-coder:7b` and `nomic-embed-text`.
3. Open the frontend.
4. Connect a public GitHub repository.
5. Index it.
6. Ask Copilot questions about the codebase.
7. Inspect the retrieved source files and line ranges.

## Privacy

The default setup uses local Ollama inference and local PostgreSQL/pgvector. No OpenAI API key is required for the current implementation.

## Production roadmap

Authentication, GitHub OAuth/App, background indexing jobs, AST-aware chunking, hybrid retrieval, reranking, tool calling, sandboxed test execution, evaluation, streaming, observability and deployment.
// Git sync test
