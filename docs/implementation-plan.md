# Implementation plan

1. Establish configuration, observability, database session management and health endpoints.
2. Implement recursive Drive discovery and MIME-specific parsers, including explicit OCR state.
3. Normalize German text, money and dates; extract structured bank transactions.
4. Implement document-aware chunking, Qwen embedding providers, Pinecone validation and capacity estimation.
5. Combine exact, PostgreSQL lexical and semantic search with reciprocal-rank fusion.
6. Add grounded Gemini output and a bounded tool layer; keep arithmetic in deterministic Python.
7. Add reconciliation, depreciation, utility allocation, legal-rule and declaration workflows.
8. Expose services through FastAPI, Celery and an allow-listed aiogram bot.
9. Verify with unit/integration/evaluation tests, migrations, Docker and CI.

Progress and intentionally deferred production hardening are recorded in `README.md`.

