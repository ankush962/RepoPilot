# RepoPilot — AI Code Intelligence

RepoPilot is a local-first codebase intelligence platform: connect a GitHub repository, build a searchable code index, and ask grounded questions about architecture, implementation, bugs, and specific files.

## Architecture

- **Frontend:** Next.js + React
- **API:** FastAPI + Pydantic
- **Database:** PostgreSQL + pgvector
- **LLM:** Ollama + Qwen 2.5 Coder
- **Embeddings:** Ollama + nomic-embed-text
- **Repository ingestion:** GitPython
- **Indexing:** persistent PostgreSQL-backed jobs with retry support
- **Chunking:** Python AST-aware symbols plus safe line-based fallback
- **Retrieval:** vector similarity + lexical signals + result diversity
- **Responses:** synchronous JSON and SSE streaming
- **Observability:** request IDs, structured request logging, health checks and metrics

## Local development

### 1. Start PostgreSQL

```bash
docker compose up -d postgres
```

### 2. Start Ollama

Make sure these models exist locally:

```bash
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text
```

### 3. Backend

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

For a separate persistent indexing worker:

```bash
cd backend
PYTHONPATH=. python -m app.services.worker
```

For production-like local deployment, run the API and worker as separate processes/containers.

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Production hardening included

- Persistent indexing jobs instead of holding the HTTP request open.
- PostgreSQL row locking with `SKIP LOCKED` so multiple workers can safely claim jobs.
- Automatic index retries.
- Incremental chunk updates using content hashes.
- Deleted/changed source chunks are reconciled on re-index.
- Python symbol-aware chunking using the standard-library AST.
- Retrieval candidate expansion, lexical scoring and file-level diversity.
- Ollama streaming endpoint at `POST /chat/stream`.
- Request IDs and request latency logging.
- Database/Ollama health endpoints.
- Basic application metrics endpoint.
- Optional bearer authentication using JWT.
- Strict GitHub HTTPS URL validation to reduce SSRF risk.
- Input length and branch validation.
- Production-oriented Docker image and worker service.
- Alembic migration foundation.
- Unit-test foundation for chunking and authentication.
- Frontend index-job polling and accessible focus/reduced-motion behavior.

## Authentication

Authentication is disabled by default for local development.

For a deployment, set:

```env
AUTH_ENABLED=true
AUTH_USERNAME=admin
AUTH_PASSWORD=<strong-password>
JWT_SECRET=<long-random-secret>
```

Then authenticate with:

```http
POST /auth/login
```

The frontend can persist the returned bearer token for protected API calls.

## Important production checklist

This repository now has the infrastructure foundation, but a real public SaaS deployment should still add:

- GitHub OAuth/App installation flow and private-repository token exchange.
- Per-user/team tenancy and authorization policies.
- Managed secrets and key rotation.
- Redis/Kafka or another externally managed queue if PostgreSQL jobs are no longer sufficient.
- Distributed rate limiting.
- Full OpenTelemetry tracing/metrics.
- A formal retrieval/answer evaluation dataset and CI quality gates.
- More language-specific AST parsers for JavaScript/TypeScript/Go/Java/etc.
- Reranking with an evaluated reranker model.
- Sandboxed code execution, if execution tools are introduced.
- HTTPS, reverse proxy/WAF and production database backups.
- End-to-end browser/API/integration tests.

The system should not be described as a fully deployed SaaS until those deployment-specific controls are configured and tested.
