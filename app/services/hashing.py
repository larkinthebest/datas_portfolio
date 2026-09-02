from __future__ import annotations

import hashlib

from app.domain.german import normalize_german_text


def binary_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def normalized_text_sha256(text: str) -> str:
    return hashlib.sha256(normalize_german_text(text).encode("utf-8")).hexdigest()


def duplicate_kind(
    *, binary_hash: str, text_hash: str, existing_binary_hash: str, existing_text_hash: str
) -> str | None:
    if binary_hash == existing_binary_hash:
        return "exact_duplicate"
    if text_hash == existing_text_hash:
        return "content_duplicate"
    return None
