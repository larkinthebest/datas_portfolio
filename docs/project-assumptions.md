# Project assumptions

- Google Drive is the source of original documents; this repository never mutates those originals.
- The known root folder ID is configured with `GOOGLE_DRIVE_ROOT_FOLDER_ID`, never in domain code.
- Most documents are German and users ask questions in Russian.
- PostgreSQL owns facts, calculations, status and audit. Pinecone owns vectors and compact metadata only.
- Missing external credentials must not block local tests. Fake providers are first-class test adapters.
- Initial synchronization is a dry run. A human must inspect inventory and a sample before full indexing.
- OCR is a PDF-only fallback and remains disabled by default.
- Legal and declaration outputs remain drafts until a human explicitly approves them.
- The system helps prepare accounting evidence; it is not tax or legal advice and never files a return.

