from types import SimpleNamespace

import pytest
from google.genai import errors
from pydantic import ValidationError

from app.integrations.gemini import GeminiProvider


class _Models:
    def __init__(self, parsed) -> None:
        self.parsed = parsed

    async def generate_content(self, **kwargs):
        return SimpleNamespace(parsed=self.parsed, text=None)


class _AsyncClient:
    def __init__(self, parsed) -> None:
        self.models = _Models(parsed)

    async def aclose(self) -> None:
        return None


class _Client:
    def __init__(self, parsed) -> None:
        self.aio = _AsyncClient(parsed)


class _FallbackModels:
    def __init__(self, parsed) -> None:
        self.parsed = parsed
        self.calls: list[str] = []

    async def generate_content(self, **kwargs):
        model = kwargs["model"]
        self.calls.append(model)
        if model == "primary":
            raise errors.ServerError(503, {"error": {"message": "busy"}})
        return SimpleNamespace(parsed=self.parsed, text=None)


class _FallbackClient:
    def __init__(self, parsed) -> None:
        self.aio = SimpleNamespace(models=_FallbackModels(parsed))


@pytest.mark.asyncio
async def test_gemini_structured_output_is_validated() -> None:
    provider = GeminiProvider(api_key="", model="test", enabled=False)
    provider.enabled = True
    provider._client = _Client(  # type: ignore[assignment]
        {
            "answer": "Недостаточно данных.",
            "confidence": 0,
            "sources": [],
            "warnings": [],
            "missing_information": ["Нет источников"],
        }
    )
    answer = await provider.answer("вопрос", [])
    assert answer.confidence == 0


@pytest.mark.asyncio
async def test_invalid_gemini_confidence_is_rejected() -> None:
    provider = GeminiProvider(api_key="", model="test", enabled=False)
    provider.enabled = True
    provider._client = _Client(  # type: ignore[assignment]
        {"answer": "unsupported", "confidence": 2, "sources": []}
    )
    with pytest.raises(ValidationError):
        await provider.answer("вопрос", [])


@pytest.mark.asyncio
async def test_temporary_server_error_uses_fallback_model() -> None:
    provider = GeminiProvider(
        api_key="", model="primary", fallback_models=("fallback",), enabled=False
    )
    provider.enabled = True
    provider._client = _FallbackClient(  # type: ignore[assignment]
        {
            "answer": "Ответ из резервной модели.",
            "confidence": 0.5,
            "sources": [],
            "warnings": [],
            "missing_information": [],
        }
    )

    answer = await provider.answer("вопрос", [])

    assert answer.answer == "Ответ из резервной модели."
    assert provider._client.aio.models.calls == ["primary", "fallback"]
