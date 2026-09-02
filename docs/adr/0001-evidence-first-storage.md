# ADR 0001: Evidence-first split storage

Status: accepted

## Context

Financial questions need semantic discovery, exact identifiers, deterministic sums and an auditable
link to original German documents. A vector database alone cannot provide those guarantees.

## Decision

Google Drive remains the original source. PostgreSQL owns text, versions, structured facts,
calculations, approvals and audit. Pinecone owns external Qwen vectors and compact identifiers only.
Gemini is a bounded interpreter/explainer over selected evidence and approved tools; Python owns
financial arithmetic.

## Consequences

Every Pinecone hit must be hydrated from PostgreSQL. Updates are staged and switched atomically after
new vectors are ready. More infrastructure is required, but stale-vector cleanup, tenant isolation,
manual approval and evidence chains are explicit and testable.

