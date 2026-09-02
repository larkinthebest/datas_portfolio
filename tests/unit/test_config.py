import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_csv_environment_style_lists_are_supported() -> None:
    settings = Settings(
        telegram_allowed_user_ids="123, 456",
        telegram_admin_user_ids="123",
        gemini_fallback_models="model-a,model-b",
    )
    assert settings.telegram_allowed_user_ids == [123, 456]
    assert settings.telegram_admin_user_ids == [123]
    assert settings.gemini_fallback_models == ["model-a", "model-b"]


def test_blank_optional_tenant_uuid_is_treated_as_unset() -> None:
    settings = Settings(
        telegram_allowed_user_ids=[],
        telegram_admin_user_ids=[],
        telegram_default_tenant_id="",
    )

    assert settings.telegram_default_tenant_id is None


def test_telegram_username_has_actionable_validation_error() -> None:
    with pytest.raises(
        ValidationError,
        match="expected comma-separated numeric Telegram user IDs",
    ):
        Settings(
            telegram_allowed_user_ids="@larkinsson",
            telegram_admin_user_ids=[],
            telegram_default_tenant_id=None,
        )


def test_drive_folder_url_is_normalized_to_id() -> None:
    settings = Settings(
        telegram_allowed_user_ids=[],
        telegram_admin_user_ids=[],
        telegram_default_tenant_id=None,
        google_drive_root_folder_id="https://drive.google.com/drive/folders/folder_ID-123?usp=sharing",
    )

    assert settings.google_drive_root_folder_id == "folder_ID-123"
