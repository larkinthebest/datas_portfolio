import os

import pytest

from app.core.config import Settings
from app.integrations.embeddings import LocalQwenEmbeddingProvider
from app.integrations.gemini import GeminiProvider
from app.integrations.google_drive import GoogleDriveDocumentSource
from app.integrations.pinecone import PineconeVectorStore

pytestmark = pytest.mark.external


@pytest.mark.asyncio
async def test_real_google_drive_can_list_one_document() -> None:
    settings = Settings()
    if (
        not settings.google_drive_root_folder_id
        or not settings.google_service_account_file.exists()
    ):
        pytest.skip("Google Drive credentials are not configured")
    source = GoogleDriveDocumentSource.from_service_account(
        str(settings.google_service_account_file),
        root_folder_id=settings.google_drive_root_folder_id,
    )
    documents = [document async for document in source.list_documents(limit=1)]
    assert len(documents) <= 1


@pytest.mark.asyncio
async def test_real_pinecone_dimension() -> None:
    settings = Settings()
    if not settings.pinecone_api_key.get_secret_value() or not settings.pinecone_index:
        pytest.skip("Pinecone credentials are not configured")
    store = PineconeVectorStore(
        api_key=settings.pinecone_api_key.get_secret_value(),
        index_name=settings.pinecone_index,
        host=settings.pinecone_host,
        expected_dimension=settings.embedding_dimension,
        namespace_prefix=settings.pinecone_namespace_prefix,
    )
    await store.validate_dimension()


@pytest.mark.asyncio
async def test_real_gemini_structured_response() -> None:
    settings = Settings()
    if not settings.gemini_api_key.get_secret_value():
        pytest.skip("Gemini credentials are not configured")
    provider = GeminiProvider(
        api_key=settings.gemini_api_key.get_secret_value(),
        model=settings.gemini_model,
    )
    try:
        answer = await provider.answer("Ответь, что доказательств нет.", [])
        assert answer.answer
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_real_qwen_dimension() -> None:
    if os.getenv("RUN_QWEN_EXTERNAL") != "true":
        pytest.skip("Set RUN_QWEN_EXTERNAL=true to download/run the local model")
    settings = Settings()
    provider = LocalQwenEmbeddingProvider(
        model_name=settings.embedding_model,
        dimension=settings.embedding_dimension,
        device=settings.embedding_device,
        batch_size=1,
        max_length=settings.embedding_max_length,
    )
    vector = await provider.embed_query("Welche Heizkosten wurden 2025 bezahlt?")
    assert len(vector) == settings.embedding_dimension
