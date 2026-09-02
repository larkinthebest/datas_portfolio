# Operations runbook

1. Check `/health`, then `/ready` and dependency logs.
2. Run capacity estimate before initial or materially changed corpora.
3. Run a 20-document dry sample, inspect text/transaction/citation quality, then commit that pilot.
4. Enable full sync only after Pinecone/storage and privacy review.
5. On parser/model changes, build a new pending version/index, validate, switch active, then retire old vectors.
6. On failure, preserve the prior active version and inspect audit/correlation ID.
7. Back up PostgreSQL before schema or mass-reindex operations.

