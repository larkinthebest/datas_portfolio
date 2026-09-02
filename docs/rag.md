# RAG design

The query record preserves original Russian text, normalized text and German expansion terms. Exact
identifiers are searched first; lexical and semantic rankings are fused with reciprocal-rank fusion.
Pinecone results carry IDs, then PostgreSQL returns the authoritative original chunk text. The answer
schema requires sources, warnings and missing information. Quotes remain German.

