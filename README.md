# RepoPilot

> AI code intelligence for real software repositories.

RepoPilot is a full-stack developer workspace that turns a repository into an AI-readable context layer. It combines repository indexing, grounded AI chat, source-aware retrieval, code exploration, architecture intelligence, code quality analysis, and Git workflows in one place.

The goal is simple: **understand the codebase faster, keep the evidence close, and work with more context.**

## What RepoPilot does

### Ask your codebase

Ask repository-specific questions and get answers grounded in indexed code rather than generic AI context.

- Repository-aware chat
- Streaming responses
- Source-backed answers
- File paths and line ranges
- Suggested follow-up questions
- Commit-aware questions

### Explore the repository

Move from an answer to the actual implementation without leaving the workspace.

- Codebase Explorer
- File search
- Source inspection
- Repository-level context
- Direct access to indexed code

### Understand the system

Turn repository evidence into a readable system view.

- Architecture overview
- Major components
- Request flow
- Important modules
- Dependency relationships
- Architecture-oriented questions

### Monitor repository health

The repository dashboard gives a quick operational view of the indexed codebase.

- Files indexed
- Total chunks
- Embedding coverage
- Latest indexed commit
- Repository health
- Indexing job state and history

### Work with Git

Git context stays beside the code and AI workflow.

- Remote repository status
- Automatic sync / re-index support
- Branch comparison
- Commit inspection
- Commit-aware AI analysis
- Pull request analysis

### Review code quality

Use repository context to surface potential weaknesses and understand where improvements may be needed.

- Bug / weakness analysis
- Evidence-backed findings
- Severity-oriented review output
- Suggested fixes
- Repository-aware code analysis

### Collaborate safely

RepoPilot includes application-level controls for multi-user workspaces.

- Authentication
- Workspaces
- Roles and permissions
- Repository access control
- AI usage limits
- Repository disconnect / removal

## Architecture

```text
                    ┌──────────────────────┐
                    │      Next.js UI      │
                    │       + React        │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │     FastAPI API      │
                    │  auth • Git • chat   │
                    │ dashboard • explorer │
                    └───────┬──────┬───────┘
                            │      │
                ┌───────────┘      └────────────┐
                ▼                               ▼
      ┌───────────────────┐           ┌──────────────────┐
      │ PostgreSQL        │           │      Redis       │
      │ + pgvector        │           │ rate limiting /  │
      │ repository data   │           │ shared state     │
      │ + code embeddings │           └──────────────────┘
      └─────────┬─────────┘
                ▲
                │
      ┌─────────┴─────────-┐
      │ Background Worker  │
      │ indexing / retries │
      └─────────┬─────────-┘
                │
                ▼
      ┌────────────────────--┐
      │ Repository ingestion │
      │       GitPython      │
      └─────────┬──────────--┘
                │
                ▼
      ┌────────────────────┐
      │      Ollama        │
      │ Qwen 2.5 Coder 7B  │
      │ nomic-embed-text   │
      └────────────────────┘
```

### Retrieval

RepoPilot combines vector similarity with lightweight lexical signals so repository questions can prefer relevant files, paths, modules, and implementation-specific evidence.

The current vector store uses PostgreSQL + pgvector and stores 768-dimensional embeddings generated from the configured embedding model.

### Request flow

```text
User question
    ↓
Authentication / authorization
    ↓
Repository access check
    ↓
Question classification
    ↓
Vector + lexical retrieval
    ↓
Repository evidence / source context
    ↓
AI response generation
    ↓
Answer + sources + metrics
```

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js + React |
| Backend | FastAPI + Python |
| LLM | Ollama + Qwen 2.5 Coder 7B |
| Embeddings | Ollama + nomic-embed-text |
| Database | PostgreSQL + pgvector |
| Cache / rate limiting | Redis |
| Repository ingestion | GitPython |
| Retrieval | Vector similarity + hybrid lexical ranking |
| Background processing | Python worker + indexed jobs |
| Containers | Docker / Docker Compose |
| Monitoring | Prometheus + Grafana |
| Reverse proxy / TLS | Caddy |
| Testing | Pytest + Playwright |

## Project structure

```text
RepoPilot/
├── backend/
│   ├── app/
│   │   ├── api/              # API routes
│   │   ├── core/             # shared application infrastructure
│   │   ├── models/           # SQLAlchemy models
│   │   ├── services/         # AI, indexing, Git, retrieval, worker logic
│   │   ├── config.py         # application settings
│   │   ├── database.py       # database configuration
│   │   ├── main.py           # FastAPI application
│   │   └── schemas.py        # Pydantic schemas
│   ├── alembic/              # database migrations
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/
│   ├── app/
│   │   └── page.jsx          # main RepoPilot workspace
│   ├── e2e/                  # Playwright end-to-end tests
│   ├── Dockerfile
│   └── package.json
│
├── caddy/                    # local reverse proxy / HTTPS
├── monitoring/               # Prometheus / Grafana configuration
├── ops/                      # backup, restore, and production audit scripts
├── docker-compose.yml        # local production-style stack
├── render.yaml               # Render deployment blueprint
└── README.md
```

## Local development

### Prerequisites

- Docker Desktop
- Git
- Ollama
- Python 3.12+ recommended for the backend environment
- Node.js / npm for frontend development outside Docker

### 1. Start the application stack

From the repository root:

```bash
docker compose up -d --build
```

This starts the application services, database, Redis, worker, reverse proxy, and local observability services defined by the Compose stack.

### 2. Prepare Ollama

Make sure Ollama is running and the configured models are available:

```bash
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text
```

### 3. Open RepoPilot

The local HTTPS entrypoint is:

```text
https://localhost:18443
```

The reverse proxy exposes the application while keeping the API and frontend services behind the proxy.

## Backend development

Create / activate the virtual environment, then run:

```bash
cd backend
source ../.venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API is available at:

```text
http://127.0.0.1:8000
```

## Frontend development

```bash
cd frontend
npm install
npm run dev
```

The development frontend is available at:

```text
http://localhost:3000
```

## Typical workflow

1. Start PostgreSQL, Redis, Ollama, and the application stack.
2. Open RepoPilot.
3. Create or select a workspace.
4. Connect a GitHub repository.
5. Start indexing.
6. Wait for the repository to become indexed and healthy.
7. Ask a codebase question.
8. Follow the returned sources into the Explorer.
9. Use Overview, Architecture, Git, and Code Quality views to continue the investigation.
10. Re-index when the repository changes.

## Configuration

RepoPilot uses environment-based configuration. Common settings include:

```text
DATABASE_URL
REDIS_URL
OLLAMA_URL
OLLAMA_MODEL
EMBEDDING_MODEL
ENVIRONMENT
LOG_LEVEL
FRONTEND_URL
ALLOWED_ORIGINS
GITHUB_TOKEN
SECRET_KEY
```

AI model settings also include controls for temperature, context size, output length, and request timeouts.

For local development, keep secrets in a local `.env` file and never commit credentials to the repository.

## Health and readiness

The API exposes health and readiness endpoints used by the deployment and operational checks:

```text
GET /api/health
GET /api/ready
```

The production-style local stack also includes metrics and service monitoring.

## Testing

### Backend

```bash
cd backend
pytest -q
```

The current verified backend suite contains **17 passing tests**.

### Frontend E2E

```bash
cd frontend
npm run test:e2e
```

The current verified Playwright suite contains **3 passing tests**.

### Production audit

From the repository root:

```bash
./ops/production-audit.sh
```

The audit covers Compose validation, service health, API health/readiness, frontend HTTPS, exposure checks, backups, and restore verification.

## Operations

### Backup

```bash
./ops/backup-postgres.sh
```

### Restore verification

```bash
./ops/verify-restore.sh
```

The restore verification flow checks that the backup can be restored and that expected application tables are present.

## Security posture

RepoPilot includes production-oriented controls around application and repository access.

- Authenticated API access
- Workspace-level authorization
- Role / permission enforcement
- AI usage limits
- Rate limiting
- Secure repository access handling
- Repository indexing isolation
- Error-response sanitization
- CORS configuration
- HTTPS through the reverse proxy
- Health / readiness checks
- Backup and restore verification

Repository ingestion is also designed to avoid treating untrusted repository content as trusted application code.

## Observability

The local production-style stack includes:

- Prometheus metrics
- Grafana dashboards
- API health / readiness checks
- Background job visibility
- Indexing status and history

## Deployment

A Render Blueprint is included at the repository root:

```text
render.yaml
```

The current Blueprint describes the full service topology, including the API, worker, frontend, Ollama, PostgreSQL, and Redis/Key Value resources.

Cloud deployment is intentionally kept separate from the core application architecture so the local-first product remains fully functional during development.

## Product principles

### Repository context first

AI responses should be grounded in the repository being analyzed.

### Evidence over confidence

When the indexed context is insufficient, RepoPilot should say so rather than invent repository details.

### One workspace, multiple views

Chat, repository health, source exploration, architecture, Git, and code quality should work as connected surfaces rather than isolated tools.

### Local-first by default

The default configuration keeps model inference and repository data local, with Ollama and PostgreSQL/pgvector at the center of the development stack.

## Current status

RepoPilot has reached a production-ready software baseline with:

- Full-stack application architecture
- Repository indexing and retrieval
- Grounded AI chat with streaming
- Source inspection and code exploration
- Architecture intelligence
- Git and PR workflows
- Code quality analysis
- Authentication and workspace permissions
- Background jobs and retries
- Rate limiting
- Monitoring and health checks
- Backup and restore verification
- Docker production stack
- Automated backend and E2E testing

## Repository

```text
https://github.com/ankush962/RepoPilot
```

## License

Add the project's chosen license here before publishing the repository publicly.
