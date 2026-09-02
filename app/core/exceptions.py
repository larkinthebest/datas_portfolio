class RagBotError(Exception):
    """Base expected application error."""


class ConfigurationError(RagBotError):
    """Configuration is missing or inconsistent."""


class DimensionMismatchError(ConfigurationError):
    """Embedding and vector index dimensions are different."""


class UnsupportedDocumentError(RagBotError):
    """The document MIME type is intentionally unsupported."""


class RequiresOCRError(RagBotError):
    """A PDF contains insufficient text and OCR is disabled."""


class AccessDeniedError(RagBotError):
    """Actor is not allowed to perform an action."""
