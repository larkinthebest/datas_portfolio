# Security

Documents are untrusted input. The model sees explicit untrusted delimiters and has only allow-listed
tools with call/time limits. API keys use constant-time comparison. Telegram uses explicit allowlists.
Repositories and Pinecone namespaces require tenant IDs. Logs must not contain raw document text,
prompts, credentials, tax IDs or full IBANs. Put credentials in a secret manager or mounted Docker
secret; never in the image or repository.

