# RepoPilot Productionization Status

## Completed in this pass

- Persistent PostgreSQL-backed indexing jobs.
- Safe concurrent job claiming with `FOR UPDATE SKIP LOCKED`.
- Retry handling for failed indexing jobs.
- Separate worker container/process support.
- Local development auto-starts one background worker when `WORKER_ENABLED=true`.
- Incremental chunk reconciliation with SHA-256 content hashes.
- Removal of chunks for deleted source files.
- Python AST-aware symbol chunking with fallback line chunks.
- Vector embedding only for chunks missing embeddings.
- Expanded retrieval candidates, lexical signals and file diversity.
- SSE streaming chat endpoint.
- Request IDs and latency logging.
- Database and Ollama readiness endpoints.
- Lightweight operational metrics endpoint.
- Optional JWT authentication.
- GitHub HTTPS-only repository validation and branch validation.
- Input validation and generic production API errors.
- Alembic migration foundation.
- Dockerized API and worker.
- Frontend polling for persistent indexing jobs.
- Frontend authentication prompt when authentication is enabled.
- Focus-visible and reduced-motion accessibility improvements.
- Basic unit-test foundation.

## Still required before calling this a public SaaS

These are deliberately not represented as complete:

1. GitHub OAuth/App installation and private-repository credential exchange.
2. Multi-user/team tenancy and authorization.
3. Production secret management and rotation.
4. External queue if PostgreSQL-backed jobs become insufficient at scale.
5. Distributed rate limiting.
6. Full OpenTelemetry tracing/metrics.
7. Formal retrieval and answer evaluation dataset with CI gates.
8. Reranker model with measured quality improvement.
9. AST parsers for additional languages.
10. Sandboxed execution tooling, if desired.
11. Production reverse proxy/TLS/WAF and backup/restore runbooks.
12. Full browser, API, database and worker integration test suites.

The current release is a significantly hardened production-oriented foundation, not a claim that every SaaS-scale control has been implemented.
