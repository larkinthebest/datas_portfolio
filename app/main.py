from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.application import router as application_router
from app.api.routes.calculations import router as calculations_router
from app.api.routes.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import create_engine, create_session_factory
from app.integrations.embeddings import create_embedding_provider
from app.integrations.gemini import GeminiProvider
from app.integrations.pinecone import PineconeVectorStore
from app.rag.adapters import PineconeSemanticRetriever


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.app_env != "development")
    engine = create_engine(settings.sqlalchemy_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        app.state.semantic_retriever = None
        app.state.gemini = GeminiProvider(
            api_key=settings.gemini_api_key.get_secret_value(),
            model=settings.gemini_model,
            fallback_models=settings.gemini_fallback_models,
            enabled=settings.ai_external_processing_enabled,
        )
        if settings.pinecone_api_key.get_secret_value() and settings.pinecone_index:
            embeddings = create_embedding_provider(settings)
            vector_store = PineconeVectorStore(
                api_key=settings.pinecone_api_key.get_secret_value(),
                index_name=settings.pinecone_index,
                expected_dimension=embeddings.dimension,
                host=settings.pinecone_host,
                namespace_prefix=settings.pinecone_namespace_prefix,
            )
            await vector_store.validate_dimension()
            app.state.semantic_retriever = PineconeSemanticRetriever(embeddings, vector_store)
        yield
        await app.state.gemini.close()
        await engine.dispose()

    app = FastAPI(
        title="German Accounting RAG API",
        version="0.1.0",
        description="Evidence-first API for German financial documents with Russian answers.",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(application_router)
    app.include_router(calculations_router)
    return app


app = create_app()
