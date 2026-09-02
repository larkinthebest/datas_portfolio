# Architecture

```mermaid
flowchart TD
  TG[Telegram / Russian] --> AG[Bounded Gemini agent]
  API[FastAPI] --> AG
  AG --> TL[Approved tool layer]
  TL --> HR[Hybrid retrieval]
  TL --> TX[Transactions]
  TL --> CALC[Decimal calculations]
  TL --> RULES[Versioned legal rules]
  HR --> PC[(Pinecone vectors)]
  HR --> PG[(PostgreSQL facts, text, audit)]
  TX --> PG
  CALC --> PG
  RULES --> PG
  GD[Google Drive originals] --> ING[Versioned ingestion]
  ING --> PARSE[PDF/DOCX/XLSX parsers + OCR fallback]
  PARSE --> PG
  PARSE --> QWEN[Qwen embeddings]
  QWEN --> PC
  REDIS[(Redis)] --> WORKER[Celery worker]
  WORKER --> ING
```

## Trust boundaries

Drive documents are untrusted evidence. Their text is delimited before it reaches Gemini. The model
has no SQL, filesystem or unrestricted vector-store tool. Tenant filters are mandatory at repository
and vector namespace boundaries. A failed reindex leaves the prior active version untouched.

## RAG question sequence

```mermaid
sequenceDiagram
  participant U as Telegram user
  participant A as Agent
  participant R as Hybrid retrieval
  participant P as PostgreSQL
  participant V as Pinecone
  participant G as Gemini
  U->>A: Russian question
  A->>R: normalized query + German expansion + filters
  par exact and lexical
    R->>P: identifiers / FTS
  and semantic
    R->>V: Qwen query vector
  end
  R->>P: authoritative chunk text by IDs
  R-->>A: fused, deduplicated evidence
  A->>G: bounded prompt + untrusted evidence
  G-->>A: validated RagAnswer JSON
  A-->>U: Russian answer + original German citations
```

## Safe document update sequence

```mermaid
sequenceDiagram
  participant D as Drive
  participant W as Worker
  participant P as PostgreSQL
  participant V as Pinecone
  W->>D: read changed revision
  W->>P: create pending version
  W->>W: parse, validate, chunk, embed
  W->>V: upsert versioned vectors
  W->>P: atomically mark new version active
  W->>V: remove prior vectors
  W->>P: append audit event
```

## First and incremental synchronization

```mermaid
sequenceDiagram
  participant C as CLI/Worker
  participant D as Drive API
  participant P as PostgreSQL
  participant V as Pinecone
  C->>D: recursive list(root folder)
  D-->>C: files + logical paths
  loop each supported file
    C->>D: download/export
    C->>C: hash, parse, structure, chunk
    C->>P: stage inactive version/facts
    C->>V: upsert new-version vectors
    C->>P: atomically activate version
  end
  C->>D: getStartPageToken
  Note over C,P: Persist token after baseline
  C->>D: changes.list(page token)
  D-->>C: added / modified / removed
  C->>P: version update or mark deleted
  C->>V: upsert new or delete removed version
```

## Scanned PDF

```mermaid
sequenceDiagram
  participant W as Worker
  participant P as PDF parser
  participant O as OCR worker
  W->>P: PDF bytes
  P-->>W: insufficient text layer
  alt OCR disabled
    W->>W: status = requires_ocr
  else OCR enabled
    W->>O: render pages, Tesseract deu+eng
    O-->>W: page-anchored German text
    W->>W: validate before chunk/index
  end
```

## Reconciliation, calculation and agent tools

```mermaid
sequenceDiagram
  participant U as User
  participant A as Bounded agent
  participant T as Approved tools
  participant P as PostgreSQL
  U->>A: financial question
  A->>T: search_bank_transactions
  T->>P: tenant-scoped records
  P-->>T: Decimal facts + source anchors
  alt deterministic calculation
    A->>T: calculate_depreciation / utility allocation
    T->>T: Decimal formula and rounding
  else reconciliation
    A->>T: score reconciliation candidate
    T->>T: weighted deterministic components
  end
  T-->>A: result + evidence + reasons
  A-->>U: Russian explanation, German citations
  Note over A,T: Tool count and timeout are bounded; approvals remain human-only
```
