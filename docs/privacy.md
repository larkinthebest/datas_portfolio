# Privacy and data handling

Only selected evidence chunks are sent to Gemini when `AI_EXTERNAL_PROCESSING_ENABLED=true`.
Raw documents stay in Google Drive; normalized chunk text and facts stay in PostgreSQL. Pinecone
receives vectors and compact identifiers, not complete documents. Production logs omit prompt bodies,
document text, API keys, tax identifiers and unmasked IBANs. Turn external processing off to keep
parsing, deterministic extraction and local indexing available without Gemini.

