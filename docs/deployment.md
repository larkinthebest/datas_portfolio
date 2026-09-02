# Deployment

Use Docker Compose for a single-host pilot. Apply Alembic before starting API/workers, configure
PostgreSQL backups and validate Pinecone dimension. In production use managed secrets, TLS, private
networking, resource limits and separate worker queues. The OCR image is optional and should be
isolated because rendered PDFs are resource intensive.

