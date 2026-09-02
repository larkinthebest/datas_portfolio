from prometheus_client import Counter, Histogram

DOCUMENTS_PROCESSED = Counter("documents_processed_total", "Documents processed")
DOCUMENTS_FAILED = Counter("documents_failed_total", "Documents failed")
DOCUMENTS_REQUIRING_OCR = Counter("documents_requiring_ocr_total", "Documents requiring OCR")
CHUNKS_CREATED = Counter("chunks_created_total", "Chunks created")
EMBEDDINGS_CREATED = Counter("embeddings_created_total", "Embeddings created")
PINECONE_UPSERTS = Counter("pinecone_upserts_total", "Pinecone upserts")
QUERIES = Counter("queries_total", "Queries", ["intent"])
QUERY_LATENCY = Histogram("query_latency_seconds", "End-to-end query latency")
RETRIEVAL_LATENCY = Histogram("retrieval_latency_seconds", "Retrieval latency")
GEMINI_LATENCY = Histogram("gemini_latency_seconds", "Gemini latency")
AGENT_TOOL_CALLS = Counter("agent_tool_calls_total", "Agent tool calls", ["tool"])
RECONCILIATION_MATCHES = Counter(
    "reconciliation_matches_total", "Reconciliation matches", ["status"]
)
CALCULATIONS = Counter("calculation_total", "Calculations", ["kind"])
